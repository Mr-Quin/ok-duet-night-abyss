"""How to move through the commission UI: routes to the built-in targets and the steps between screens."""
import re

from src.nav import graph
from src.nav import screens as S
from src.nav import text_zh as T
from src.nav.backend import Screen
from src.nav.graph import NavError

# pages reached from a book section: name -> (section, button text)
PAGES = dict(T.PAGE_ENTRY)

WORLD = ('world', None)


def route(goal):
    """Nodes from the world down to a goal given as a dict (see navigator.py)."""
    g = goal['screen']
    if g == 'world':
        return [WORLD]
    if g == 'main_menu':
        return [WORLD, ('main_menu', None)]
    if g == 'menu':
        return [WORLD, ('main_menu', None), ('menu', goal['name'])]
    if g == 'book':
        if goal['section'] == T.SECTIONS[1]:
            return [WORLD, ('commission', None)]
        return [WORLD, ('book', goal['section'])]
    if g == 'page':
        return [WORLD, ('book', PAGES[goal['name']][0]), ('page', goal['name'])]
    if g == 'commission':
        return [WORLD, ('commission', goal['tab'])]
    if g == 'start':
        return [WORLD, ('commission', goal['via']), ('start', goal['via'])]
    raise ValueError('unknown goal screen %r' % g)


@graph.edge('world', 'main_menu')
def open_main_menu(nav, scr, here, nxt, info):
    nav.b.key('esc')
    return False


@graph.edge('world', 'book')
@graph.edge('world', 'commission')
def open_book(nav, scr, here, nxt, info):
    nav.b.key('l')
    return False


@graph.edge('main_menu', 'menu')
def open_menu_tile(nav, scr, here, nxt, info):
    tile = scr.find(nxt[1], (0.03, 0.2, 0.33, 0.97), exact=True)
    if not tile:
        if nav.wait(3) is None:
            return None
        raise NavError('no %s tile on the main menu' % nxt[1])
    nav.log('  opening %s' % nxt[1])
    nav.b.click(tile[0]['x'], tile[0]['y'] - 0.04)
    return False


@graph.edge('book', 'page')
def open_page(nav, scr, here, nxt, info):
    button = scr.find(PAGES[nxt[1]][1], (0.3, 0.5, 0.8, 0.8), exact=True)
    if not button:
        return nav.wait(3)
    nav.log('  entering %s' % nxt[1])
    nav.click(button[0])
    return False


@graph.sideways(('book', 'commission'))
def switch_book_page(nav, here, target):
    if target[0] == 'book':
        nav.log('  section %s -> %s' % (here[1], target[1]))
        nav.b.click(S.SECTION_X[T.SECTIONS.index(target[1])], S.SECTION_Y)
    elif here[0] == 'book':
        nav.log('  section %s -> %s' % (here[1], T.SECTIONS[1]))
        nav.b.click(S.SECTION_X[1], S.SECTION_Y)
    else:
        nav.log('  switching tab %s -> %s' % (here[1], target[1]))
        nav.b.click(S.TAB_X[T.TABS.index(target[1])], S.TAB_Y)
    return False


@graph.edge('commission', ('start', T.TABS[0]))
def open_mission_card(nav, scr, here, nxt, info):
    target = nav.goal['mode']
    cards = [i for i in scr.items if 0.62 < i['y'] < 0.68 and i['x'] < 0.75 and i['t'] in T.MISSIONS]
    hit = next((c for c in cards if c['t'] == target), None)
    if hit and 0.05 < hit['x'] < 0.68:
        nav.log('  opening card %s' % target)
        nav.b.click(hit['x'], 0.42)
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
    nav.log('  card %s not in view (%s), scrolling %d' % (target, [c['t'] for c in cards], n))
    nav.b.scroll(0.37, 0.45, n)
    return False


@graph.edge('commission', ('start', T.TABS[2]))
def open_letter(nav, scr, here, nxt, info):
    """Open the 委托密函 column holding the wanted mission; the start screen then picks the entry."""
    heads = {i['t']: i for i in scr.items if 0.37 < i['y'] < 0.42 and i['t'] in T.LETTER_COLUMNS}
    if not heads:
        return nav.wait(3)

    def entries(head):
        return [i for i in scr.items if 0.55 < i['y'] < 0.75 and head['x'] - 0.1 < i['x'] < head['x'] - 0.02
                and not re.search(r'\d', i['t'])]
    cols = [nav.goal['column']] if nav.goal.get('column') else list(heads)
    for col in cols:
        if col not in heads:
            continue
        hit = next((e for e in entries(heads[col]) if nav.goal['mode'] in e['t']), None)
        if hit:
            nav.log('  opening %s / %s' % (col, hit['t']))
            nav.click(hit)
            return False
    offered = {c: [e['t'] for e in entries(h)] for c, h in heads.items()}
    raise NavError('no %s letter mission right now; offered %s' % (nav.goal['mode'], offered))


@graph.edge('commission', ('start', T.TABS[1]))
def open_nightbook_row(nav, scr, here, nxt, info):
    """Select the 夜航手册 level, then the row, then press its 前往."""
    g, st = nav.goal, nav.row_state
    book = g.get('book') or g.get('lv')
    if not info.get('levels'):
        column = Screen(scr.img, nav.b.ocr_region(scr, *S.LEVEL_COLUMN))
        info['levels'] = S.level_positions(column)
    y = (info.get('levels') or {}).get(book)
    if y is None:
        if nav.wait(3) is None:
            return None
        nav.log('  level column not readable')
        return False
    if not 0.2 <= y <= 0.86:
        nav.log('  level %d off the column (y=%.2f), scrolling' % (book, y))
        nav.b.scroll(S.LEVEL_X, 0.5, -3 if y > 0.86 else 3)
        st.pop('level', None)
        return False
    if st.get('level') != book:
        st.update(level=book, names=None, seen=set())
        if S.selected_level(scr, info['levels']) != book:
            nav.log('  selecting level %d' % book)
            nav.b.click(S.LEVEL_X, y)
            return False
    listed = S.nightbook_rows(scr)
    names = [r['name'] for r in listed]
    row = g.get('row', 0)
    known = nav.rows.get('names/%d' % book, [])
    # the row list refreshes a moment after the level ring moves; rows read too early belong to the old level
    stale = names and known[:1] != names[:1] and any(
        k != 'names/%d' % book and k.startswith('names/') and v[:1] == names[:1] for k, v in nav.rows.items())
    # the selected label is usually drawn white, but not always; rows from this level's known list confirm it too
    others = {n for k, v in nav.rows.items() if k.startswith('names/') and k != 'names/%d' % book for n in v}
    confirmed = S.selected_level(scr, info['levels']) == book or (names[:1] and names[0] in known and names[0] not in others)
    if not confirmed or stale:
        if nav.wait(4) is None:
            return None
        st.pop('level', None)
        return False
    named_here = isinstance(row, str) and any(row in n for n in names)
    if st['names'] is None:
        if names and known and names[0] == known[0]:
            st['names'] = list(known)
        elif not named_here:
            # indexes count from the top, and the list keeps its scroll position between visits
            nav.log('  scrolling rows to the top')
            nav.b.scroll(0.4, 0.45, 30)
            st['names'] = []
            return False
        else:
            st['names'] = []
    for n in names:
        if n and n not in st['names']:
            st['names'].append(n)
    if len(st['names']) > len(known) and (not known or st['names'][0] == known[0]):
        nav.rows['names/%d' % book] = list(st['names'])
        nav.save_rows()
    target = st['names'][row] if isinstance(row, int) and row < len(st['names']) else (row if isinstance(row, str) else None)
    idx = next((k for k, n in enumerate(names) if target and target in n), None)
    if idx is None:
        if tuple(names) in st['seen']:
            raise NavError('no row %r on the Lv.%d page; rows are %s' % (row, book, st['names']))
        st['seen'].add(tuple(names))
        nav.log('  row %r not in %s, scrolling down' % (row, names))
        nav.b.scroll(0.4, 0.45, -3)
        return False
    nav.log('  row %r -> %s' % (row, names[idx]))
    nav.click(listed[idx]['button'])
    nav.entered_row = names[idx]
    st.pop('level', None)
    return False
