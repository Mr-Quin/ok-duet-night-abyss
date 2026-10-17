"""Go from whatever screen the game is on to a target screen.

Each step reads the screen and takes one action: finish if the screen is the target, take the
registered edge to the next node if the screen is on the target's route, move sideways between
sibling screens, otherwise back out with Esc. Screens of a run in progress (round dialogs,
results, the in-run menu) have their own rules and never lose what a run has earned.

What the navigator knows about screens and moves lives in graph.py's tables; this module only
walks them. Targets are the classes in targets.py, or goal dicts:
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
import time

from src.nav import edges
from src.nav import graph
from src.nav import screens as S
from src.nav import text_zh as T
from src.nav.graph import NavError  # noqa: F401  callers catch it from here


def node_of(screen, info):
    key = {'menu': 'name', 'page': 'name', 'book': 'section', 'commission': 'tab', 'start': 'via'}.get(screen)
    return screen, info.get(key) if key else None


def same_node(a, b):
    # a key of None on the route means any tab or section will do
    return a[0] == b[0] and (b[1] is None or a[1] == b[1])


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
        self.b, self.in_dungeon, self.leave = backend, in_dungeon, leave
        if isinstance(goal, dict):
            self.goal, self.route = goal, edges.route(goal)
        else:
            self.goal, self.route = goal.goal(), goal.route()
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

    def save_rows(self):
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

        registered = graph.HANDLERS.get(screen)
        handler = (lambda scr, info: registered(self, scr, info)) if registered else getattr(self, 'on_' + screen, None)
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
            step = graph.find_edge(here, path[on + 1])
            if step is None:
                raise NavError('no edge from %s to %s' % (here, path[on + 1]))
            return step(self, scr, here, path[on + 1], info)
        for group, move in graph.SIDEWAYS:
            target = next((n for n in path if n[0] in group), None) if here[0] in group else None
            if target:
                return move(self, here, target)
        self.b.key('esc')
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
