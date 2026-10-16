"""Go from whatever screen the game is on to a target screen.

The menus form a tree rooted at the open world. A goal becomes a route of nodes from the
root, and each step reads the screen and takes one action: finish if the screen is the goal,
enter the next node if the screen is on the route, switch sideways between book sections
and commission tabs, otherwise back out with Esc. Screens that belong to a run in progress
(round dialogs, results, the in-run menu) have their own rules and never end a run early.

Goals:
  {'screen': 'world'}
  {'screen': 'main_menu'}
  {'screen': 'menu', 'name': '背包'}
  {'screen': 'book', 'section': '梦魔残声'}
  {'screen': 'page', 'name': '迷津'}
  {'screen': 'commission', 'tab': '委托' | '夜航手册' | '委托密函' | '悬赏委托'}
  {'screen': 'start', 'via': '委托', 'mode': '扼守/无尽', 'lv': 60}
  {'screen': 'start', 'via': '夜航手册', 'book': 65, 'row': 3 | '守护野蜂', 'mode': ..., 'lv': ...}
  {'screen': 'start', 'via': '委托密函', 'mode': ..., 'column': '角色' | '武器' | '魔之楔'}
"""
import json
import re
import time

from src.nav import screens as S
from src.nav.backend import Screen
from src.nav import text_zh as T


class NavError(RuntimeError):
    pass


def route(goal):
    """Nodes from the world down to the goal. A node is (screen, key)."""
    g = goal['screen']
    if g == 'world':
        return [('world', None)]
    if g == 'main_menu':
        return [('world', None), ('main_menu', None)]
    if g == 'menu':
        return [('world', None), ('main_menu', None), ('menu', goal['name'])]
    if g == 'book':
        if goal['section'] == T.SECTIONS[1]:
            return [('world', None), ('commission', None)]
        return [('world', None), ('book', goal['section'])]
    if g == 'page':
        return [('world', None), ('book', T.PAGE_ENTRY[goal['name']][0]), ('page', goal['name'])]
    if g == 'commission':
        return [('world', None), ('commission', goal['tab'])]
    if g == 'start':
        return [('world', None), ('commission', goal['via']), ('start', goal['via'])]
    raise ValueError('unknown goal screen %r' % g)


def node_of(screen, info):
    key = {'menu': 'name', 'page': 'name', 'book': 'section', 'commission': 'tab', 'start': 'via'}.get(screen)
    return screen, info.get(key) if key else None


def same_node(a, b):
    # a key of None on the route means any tab or section will do
    return a[0] == b[0] and (b[1] is None or a[1] == b[1])


# screens on the book's top bar, reachable from each other with one click
BOOK_LEVEL = ('book', 'commission')


def start_matches(info, goal):
    if goal.get('via') and info['via'] and goal['via'] != info['via']:
        return False
    if goal.get('mode') and not (info['mode'] and goal['mode'] in info['mode']):
        return False
    if goal.get('lv') and info['lv'] != goal['lv']:
        return None if any(t['lv'] == goal['lv'] for t in info['tiers']) else False
    return True


class Navigator:
    def __init__(self, backend, goal, log=print, in_dungeon=False, atlas=None, rows_path=None, leave='now'):
        # in_dungeon: the caller knows a run is in progress, so unreadable frames (combat effects over
        # the HUD) mean "still in the run", never a menu to back out of.
        # leave: how to get out of a run found on the way. 'after_rounds' lets the game's auto rounds
        # finish; 'now' leaves at the first point where nothing earned is lost.
        self.b, self.goal, self.in_dungeon, self.leave = backend, goal, in_dungeon, leave
        self.route = route(goal)
        self.trace = []

        def log_and_trace(msg):
            self.trace.append(msg)
            log(msg)
        self.log = log_and_trace
        self.atlas = atlas if atlas is not None else S.load_atlas()
        self.rows_path = rows_path
        self.rows = self._load_rows()
        self.row_state = {}
        self.entered_row = None
        self.unsure = 0
        self.dungeon_waits = 0
        self.loading = False
        self.giving_up = False
        self.idle_since = None

    def _load_rows(self):
        if not self.rows_path:
            return {}
        try:
            with open(self.rows_path, encoding='utf-8') as f:
                return json.load(f)
        except (OSError, ValueError):
            return {}

    def _save_rows(self):
        if self.rows_path:
            with open(self.rows_path, 'w', encoding='utf-8') as f:
                json.dump(self.rows, f, ensure_ascii=False)

    def click(self, item):
        self.b.click(item['x'], item['y'])

    def wait(self, limit):
        """Return None (wait for the game) while the screen may still be animating in."""
        self.unsure += 1
        return None if self.unsure <= limit else False

    def step(self):
        scr = self.b.read()
        screen, info = S.classify(scr, self.atlas)
        if self.in_dungeon:
            # the run HUD has the same Lv bar as the world, so only the result screen ends a run
            if screen == 'result':
                self.in_dungeon = False
            elif screen in ('unknown', 'other_menu', 'start', 'world', 'menu', 'page'):
                screen, info = 'dungeon', {}
        shown = {k: v for k, v in info.items() if k not in ('levels', 'tiers', 'retreat', 'resume', 'cancel', 'confirm', 'give_up')}
        self.log('%s %s' % (screen, shown))

        handler = getattr(self, 'on_' + screen, None)
        if handler:
            result = handler(scr, info)
            if result is not NotImplemented:
                return result
        return self.follow_route(scr, screen, info)

    # screens of a run in progress

    def on_round_dialog(self, scr, info):
        if self.leave == 'after_rounds' and info['auto'] and info['auto'][0] < info['auto'][1]:
            # auto rounds still running; the game continues by itself after the countdown
            return self.wait_in_run()
        self.log('  retreating after round %s' % (info['auto'],))
        self.click(info['retreat'][0])
        return False

    def on_result(self, scr, info):
        self.log('  leaving the result screen')
        self.loading = True
        self.b.key('esc')
        return False

    def on_exit_confirm(self, scr, info):
        if self.giving_up and info['confirm']:
            self.log('  confirming: the run has earned nothing yet')
            self.click(info['confirm'])
            self.giving_up, self.in_dungeon, self.loading = False, False, True
            return False
        self.log('  cancelling the exit confirmation')
        if info['cancel']:
            self.click(info['cancel'])
        else:
            self.b.key('esc')
        return False

    def on_dungeon_menu(self, scr, info):
        if self.giving_up and info['nothing_earned']:
            self.log('  giving up: the run has earned nothing yet')
            self.click(info['give_up'])
            return False
        if self.giving_up:
            self.log('  the run has earned something; waiting for the round to end instead')
        self.giving_up = False
        self.log('  resuming from the in-run menu')
        self.click(info['resume'])
        return False

    def on_dungeon(self, scr, info):
        # before the first wave nobody is fighting: either we want out now, or whatever was meant to
        # walk to the objective has stopped. Giving up then loses nothing, and the in-run menu says so.
        if info.get('to_objective'):
            self.idle_since = self.idle_since or time.time()
            if self.leave == 'now' or time.time() - self.idle_since > 45:
                self.log('  run not started (round %s); opening the menu to leave' % info.get('round'))
                self.giving_up, self.idle_since = True, None
                self.b.key('esc')
                return False
        else:
            self.idle_since = None
        # rounds finish on their own; wait for the round dialog or the result screen
        return self.wait_in_run()

    def on_manual_popup(self, scr, info):
        if info.get('before_run'):
            self.log('  closing the commission-manual popup; no run has started')
            self.b.key('esc')
            return False
        return self.wait_in_run()

    def wait_in_run(self):
        self.dungeon_waits += 1
        if self.dungeon_waits < 400:
            return None
        raise NavError('still in the run after waiting; not giving it up automatically')

    def on_unknown(self, scr, info):
        if self.loading and self.dungeon_waits < 400:
            # the loading screen after a run shows tips and art, nothing recognisable
            self.dungeon_waits += 1
            return None
        return self.back_out(scr, info)

    on_other_menu = on_unknown

    def back_out(self, scr, info):
        # often a screen still fading in; give it a moment before backing out
        if self.wait(2) is None:
            return None
        self.b.key('esc')
        return False

    def on_start(self, scr, info):
        if info['via'] is None and info['mode'] is None:
            # start screen still fading in
            result = self.wait(4)
            if result is None:
                return None
        g = self.goal
        if g['screen'] != 'start':
            return NotImplemented
        if g.get('via') == T.TABS[2] and info['via'] == T.TABS[2]:
            return self.adjust_letter_start(info)
        ok = start_matches(info, g)
        if g.get('via') == T.TABS[1] and g.get('row') is not None and self.entered_row is None:
            # the same dungeon is reachable from several rows; only the one we entered counts
            ok = False
        if ok:
            return True
        same_dungeon = (not g.get('via') or info['via'] == g['via']) and \
            (not g.get('mode') or (info['mode'] and g['mode'] in info['mode']))
        if same_dungeon and g.get('lv') and len(info['tiers']) > 1 and \
                not any(t['lv'] == g['lv'] for t in info['tiers']):
            raise NavError('%s has no Lv.%d tier; offered: %s' % (info['mode'], g['lv'], [t['lv'] for t in info['tiers']]))
        if ok is None:
            t = next(t for t in info['tiers'] if t['lv'] == g['lv'])
            self.log('  selecting tier Lv.%d' % g['lv'])
            self.b.click(0.08, t['y'])
            return False
        self.entered_row = None
        self.b.key('esc')
        return False

    def adjust_letter_start(self, info):
        g = self.goal
        if g.get('column') and info['column'] and g['column'] not in info['column']:
            self.log('  wrong column %s' % info['column'])
            self.b.key('esc')
            return False
        if info['mode'] and g['mode'] in info['mode']:
            return True
        entry = next((e for e in info['entries'] if g['mode'] in e['mode']), None)
        if entry is None:
            if g.get('column'):
                raise NavError('%s column offers %s, not %s' % (info['column'], [e['mode'] for e in info['entries']], g['mode']))
            self.log('  %s not in the %s column' % (g['mode'], info['column']))
            self.b.key('esc')
            return False
        self.log('  selecting %s' % entry['mode'])
        self.b.click(0.05, entry['y'])
        return False

    def on_commission(self, scr, info):
        if info['tab'] is None and self.wait(3) is None:
            # tab bar still animating; no label is lit yet
            return None
        return NotImplemented

    # the menu tree

    def follow_route(self, scr, screen, info):
        here = node_of(screen, info)
        path = self.route
        if same_node(here, path[-1]):
            return True
        on = next((k for k, n in enumerate(path) if same_node(here, n)), None)
        if on is not None:
            return self.enter(scr, here, path[on + 1], info)
        if here[0] in BOOK_LEVEL:
            target = next((n for n in path if n[0] in BOOK_LEVEL), None)
            if target:
                return self.switch(here, target)
        self.b.key('esc')
        return False

    def enter(self, scr, here, nxt, info):
        kind = nxt[0]
        if here[0] == 'world':
            self.b.key('esc' if kind == 'main_menu' else 'l')
            return False
        if kind == 'menu':
            tile = scr.find(nxt[1], (0.03, 0.2, 0.33, 0.97), exact=True)
            if not tile:
                if self.wait(3) is None:
                    return None
                raise NavError('no %s tile on the main menu' % nxt[1])
            self.log('  opening %s' % nxt[1])
            self.b.click(tile[0]['x'], tile[0]['y'] - 0.04)
            return False
        if kind == 'page':
            button = scr.find(T.PAGE_ENTRY[nxt[1]][1], (0.3, 0.5, 0.8, 0.8), exact=True)
            if not button:
                return self.wait(3)
            self.log('  entering %s' % nxt[1])
            self.click(button[0])
            return False
        if kind == 'start':
            tab = nxt[1]
            if tab == T.TABS[0]:
                return self.enter_mission_card(scr)
            if tab == T.TABS[2]:
                return self.enter_letter(scr)
            if tab == T.TABS[1]:
                return self.enter_nightbook_row(scr, info)
        raise NavError('no way from %s into %s' % (here, nxt))

    def switch(self, here, target):
        if target[0] == 'book':
            self.log('  section %s -> %s' % (here[1], target[1]))
            self.b.click(S.SECTION_X[T.SECTIONS.index(target[1])], S.SECTION_Y)
        elif here[0] == 'book':
            self.log('  section %s -> %s' % (here[1], T.SECTIONS[1]))
            self.b.click(S.SECTION_X[1], S.SECTION_Y)
        else:
            self.log('  switching tab %s -> %s' % (here[1], target[1]))
            self.b.click(S.TAB_X[T.TABS.index(target[1])], S.TAB_Y)
        return False

    def enter_mission_card(self, scr):
        target = self.goal['mode']
        cards = [i for i in scr.items if 0.62 < i['y'] < 0.68 and i['x'] < 0.75 and i['t'] in T.MISSIONS]
        hit = next((c for c in cards if c['t'] == target), None)
        if hit and 0.05 < hit['x'] < 0.68:
            self.log('  opening card %s' % target)
            self.b.click(hit['x'], 0.42)
            return False
        seen = [T.MISSIONS.index(c['t']) for c in cards]
        want = T.MISSIONS.index(target)
        # about 9 wheel notches move the strip by one card
        if hit:
            n = -4 if hit['x'] >= 0.68 else 4
        elif not seen:
            n = -9
        elif want > max(seen):
            n = -9 * (want - max(seen) + 1)
        else:
            n = 9 * (min(seen) - want + 1)
        self.log('  card %s not in view (%s), scrolling %d' % (target, [c['t'] for c in cards], n))
        self.b.scroll(0.37, 0.45, n)
        return False

    def enter_letter(self, scr):
        """Open the 委托密函 column holding the wanted mission; the start screen then picks the entry."""
        heads = {i['t']: i for i in scr.items if 0.37 < i['y'] < 0.42 and i['t'] in T.LETTER_COLUMNS}
        if not heads:
            return self.wait(3)

        def entries(head):
            return [i for i in scr.items if 0.55 < i['y'] < 0.75 and head['x'] - 0.1 < i['x'] < head['x'] - 0.02
                    and not re.search(r'\d', i['t'])]
        cols = [self.goal['column']] if self.goal.get('column') else list(heads)
        for col in cols:
            if col not in heads:
                continue
            hit = next((e for e in entries(heads[col]) if self.goal['mode'] in e['t']), None)
            if hit:
                self.log('  opening %s / %s' % (col, hit['t']))
                self.click(hit)
                return False
        offered = {c: [e['t'] for e in entries(h)] for c, h in heads.items()}
        raise NavError('no %s letter mission right now; offered %s' % (self.goal['mode'], offered))

    def enter_nightbook_row(self, scr, info):
        """Select the 夜航手册 level, then the row, then press its 前往."""
        g, st = self.goal, self.row_state
        book = g.get('book') or g.get('lv')
        if not info.get('levels'):
            column = Screen(scr.img, self.b.ocr_region(scr, *S.LEVEL_COLUMN))
            info['levels'] = S.level_positions(column)
        y = (info.get('levels') or {}).get(book)
        if y is None:
            result = self.wait(3)
            if result is None:
                return None
            self.log('  level column not readable')
            return False
        if not 0.2 <= y <= 0.86:
            self.log('  level %d off the column (y=%.2f), scrolling' % (book, y))
            self.b.scroll(S.LEVEL_X, 0.5, -3 if y > 0.86 else 3)
            st.pop('level', None)
            return False
        if st.get('level') != book:
            st.update(level=book, names=None, seen=set())
            if S.selected_level(scr, info['levels']) != book:
                self.log('  selecting level %d' % book)
                self.b.click(S.LEVEL_X, y)
                return False
        listed = S.nightbook_rows(scr)
        names = [r['name'] for r in listed]
        row = g.get('row', 0)
        known = self.rows.get('names/%d' % book, [])
        # the row list refreshes a moment after the level ring moves; rows read too early belong to the old level
        stale = names and known[:1] != names[:1] and any(
            k != 'names/%d' % book and k.startswith('names/') and v[:1] == names[:1] for k, v in self.rows.items())
        if S.selected_level(scr, info['levels']) != book or stale:
            if self.wait(4) is None:
                return None
            st.pop('level', None)
            return False
        named_here = isinstance(row, str) and any(row in n for n in names)
        if st['names'] is None:
            if names and known and names[0] == known[0]:
                st['names'] = list(known)
            elif not named_here:
                # indexes count from the top, and the list keeps its scroll position between visits
                self.log('  scrolling rows to the top')
                self.b.scroll(0.4, 0.45, 30)
                st['names'] = []
                return False
            else:
                st['names'] = []
        for n in names:
            if n and n not in st['names']:
                st['names'].append(n)
        if len(st['names']) > len(known) and (not known or st['names'][0] == known[0]):
            self.rows['names/%d' % book] = list(st['names'])
            self._save_rows()
        target = st['names'][row] if isinstance(row, int) and row < len(st['names']) else (row if isinstance(row, str) else None)
        idx = next((k for k, n in enumerate(names) if target and target in n), None)
        if idx is None:
            if tuple(names) in st['seen']:
                raise NavError('no row %r on the Lv.%d page; rows are %s' % (row, book, st['names']))
            st['seen'].add(tuple(names))
            self.log('  row %r not in %s, scrolling down' % (row, names))
            self.b.scroll(0.4, 0.45, -3)
            return False
        self.log('  row %r -> %s' % (row, names[idx]))
        self.click(listed[idx]['button'])
        self.entered_row = names[idx]
        st.pop('level', None)
        return False

    def run(self, max_steps=40):
        seen = {}
        k = waits = 0
        while k < max_steps and waits < 600:
            before = self.b.thumb()
            log_len = len(self.trace)
            result = self.step()
            if result:
                self.log('reached after %d steps' % k)
                return True
            if result is None:
                # waiting on the game (animation, a run still going) does not use up action steps
                waits += 1
                self.b.sleep(0.4)
                continue
            k += 1
            self.unsure = 0
            state = tuple(self.trace[log_len:])
            seen[state] = seen.get(state, 0) + 1
            if seen[state] >= 4:
                raise NavError('stuck repeating: %s' % ' / '.join(state))
            self.b.settle(before)
            if seen[state] >= 2:
                # the game sometimes ignores input while it hitches; give it longer before trying again
                self.b.sleep(1.5 * (seen[state] - 1))
        return False
