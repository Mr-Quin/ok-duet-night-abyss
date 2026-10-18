"""委托界面里怎么走：内置目标的路线，以及界面之间的每一步操作。"""
import re

from src.nav import graph
from src.nav import screens as S
from src.nav import text_zh as T
from src.nav.backend import Screen
from src.nav.graph import NavError, NoSuchEntry


WORLD = ('world', None)


def same_name(a, b):
    """同一行两次读出的名字可能差一个错字（枯萎/枯菱）；罗马数字必须一致。"""
    norm = lambda n: n.replace('Ⅲ', 'III').replace('Ⅱ', 'II').replace('Ⅰ', 'I').replace(' ', '')
    a, b = norm(a), norm(b)
    if a == b:
        return True
    if len(a) != len(b):
        return False
    diff = [(x, y) for x, y in zip(a, b) if x != y]
    return len(diff) == 1 and not diff[0][0].isascii() and not diff[0][1].isascii()


def han(name):
    """只留汉字。罗马数字和引号读得不稳：同一个「Ⅱ」会读成 II 或 ⅡI。"""
    return ''.join(c for c in name if '一' <= c <= '鿿')


def align(known, visible):
    """visible 的第一行是 known 里的第几行。

    按汉字逐行对，读不出名字的格子（None）和什么都算对上。看得见的第一行和最后一行常常只露出
    一半，名字会读成别的字（比如「相以」），这两行对不上也不算；其余重叠的行要全部对上，而且
    至少有两行（只重叠一行时一行）真的对上了名字，取重叠最多的。
    """
    best, overlap = None, 0
    for offset in range(len(known)):
        pairs = list(zip(known[offset:], visible))
        last = len(visible) - 1
        matched = 0
        for k, (a, b) in enumerate(pairs):
            if not (a and b):
                continue
            if same_name(han(a), han(b)):
                matched += 1
            elif k not in (0, last):
                break
        else:
            if len(pairs) > overlap and matched >= min(2, len(pairs)):
                best, overlap = offset, len(pairs)
    return best


def route(goal):
    """从大世界到目标的节点列表。goal 是目标类 goal() 返回的字典。"""
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
        return [WORLD, ('book', T.PAGE_ENTRY[goal['name']][0]), ('page', goal['name'])]
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
        raise NavError('主菜单上没有 %s' % nxt[1])
    nav.log('  打开 %s' % nxt[1])
    nav.b.click(tile[0]['x'], tile[0]['y'] - 0.04)
    return False


@graph.edge('book', 'page')
def open_page(nav, scr, here, nxt, info):
    button = scr.find(T.PAGE_ENTRY[nxt[1]][1], (0.3, 0.5, 0.8, 0.8), exact=True)
    if not button:
        return nav.wait(3)
    nav.log('  进入 %s' % nxt[1])
    nav.click(button[0])
    return False


@graph.sideways(('book', 'commission'))
def switch_book_page(nav, here, target):
    if target[0] == 'book':
        nav.log('  分区 %s -> %s' % (here[1], target[1]))
        nav.b.click(S.SECTION_X[T.SECTIONS.index(target[1])], S.SECTION_Y)
    elif here[0] == 'book':
        nav.log('  分区 %s -> %s' % (here[1], T.SECTIONS[1]))
        nav.b.click(S.SECTION_X[1], S.SECTION_Y)
    else:
        nav.log('  页签 %s -> %s' % (here[1], target[1]))
        nav.b.click(S.TAB_X[T.TABS.index(target[1])], S.TAB_Y)
    return False


@graph.edge('commission', ('start', T.TABS[0]))
def open_mission_card(nav, scr, here, nxt, info):
    target = nav.goal['mode']
    cards = [i for i in scr.items if 0.62 < i['y'] < 0.68 and i['x'] < 0.75 and i['t'] in T.MISSIONS]
    hit = next((c for c in cards if c['t'] == target), None)
    if hit and 0.05 < hit['x'] < 0.68:
        nav.log('  打开卡片 %s' % target)
        nav.b.click(hit['x'], 0.42)
        return False
    seen = [T.MISSIONS.index(c['t']) for c in cards]
    want = T.MISSIONS.index(target)
    # 滚轮大约 9 格移动一张卡片
    if hit:
        n = -4 if hit['x'] >= 0.68 else 4
    elif not seen:
        n = -9
    elif want > max(seen):
        n = -9 * (want - max(seen) + 1)
    else:
        n = 9 * (min(seen) - want + 1)
    nav.log('  看不到 %s（当前 %s），滚动 %d' % (target, [c['t'] for c in cards], n))
    nav.b.scroll(0.37, 0.45, n)
    return False


@graph.edge('commission', ('start', T.TABS[2]))
def open_letter(nav, scr, here, nxt, info):
    """打开有目标委托的那一栏密函，具体条目到开始界面再选。"""
    heads = {i['t']: i for i in scr.items if 0.37 < i['y'] < 0.42 and i['t'] in T.LETTER_COLUMNS}
    if not heads:
        return nav.wait(3)

    def entries(head):
        return [i for i in scr.items if 0.55 < i['y'] < 0.75 and head['x'] - 0.1 < i['x'] < head['x'] - 0.02
                and not re.search(r'\d', i['t'])]
    cols = [nav.goal['column']] if nav.goal['column'] else list(heads)
    for col in cols:
        if col not in heads:
            continue
        hit = next((e for e in entries(heads[col]) if nav.goal['mode'] in e['t']), None)
        if hit:
            nav.log('  打开 %s / %s' % (col, hit['t']))
            nav.click(hit)
            return False
    offered = {c: [e['t'] for e in entries(h)] for c, h in heads.items()}
    raise NavError('现在的密函里没有 %s，可选 %s' % (nav.goal['mode'], offered))


# 夜航手册分三步：选中等级，认出这个等级的全部行名，再打开目标行。
# 每一步做不完就返回这一步的结果（None 等待、False 做了一步操作），做完返回 READY。
READY = object()


@graph.edge('commission', ('start', T.TABS[1]))
def open_nightbook_row(nav, scr, here, nxt, info):
    """选夜航手册的等级，再找到那一行，点它的「前往」。"""
    book = nav.goal['book']
    st = nav.state.setdefault('nightbook', {})
    for step in (select_level, learn_rows, open_row):
        result = step(nav, scr, info, book, st)
        if result is not READY:
            return result
    return False


def cached_rows(nav, book):
    return nav.cache.get('names/%d' % book, [])


def other_levels_rows(nav, book):
    return {k: v for k, v in nav.cache.items() if k.startswith('names/') and k != 'names/%d' % book}


def select_level(nav, scr, info, book, st):
    if not info.get('levels'):
        column = Screen(scr.img, nav.b.ocr_region(scr, *S.LEVEL_COLUMN))
        info['levels'] = S.level_positions(column)
    y = (info.get('levels') or {}).get(book)
    if y is None:
        if nav.wait(3) is None:
            return None
        # 什么都不做下一步还是一样的画面；挪一下等级栏换个画面再读
        nav.log('  读不出等级栏，滚动一下再读')
        nav.b.scroll(S.LEVEL_X, 0.5, 3)
        return False
    if not 0.2 <= y <= 0.86:
        nav.log('  Lv.%d 不在可见范围（y=%.2f），滚动' % (book, y))
        nav.b.scroll(S.LEVEL_X, 0.5, -3 if y > 0.86 else 3)
        st.pop('level', None)
        return False
    if st.get('level') != book:
        st.update(level=book, names=None, seen=[], at_top=False, top_read=None)
        if S.selected_level(scr, info['levels']) != book:
            nav.log('  选择 Lv.%d' % book)
            nav.b.click(S.LEVEL_X, y)
            return False
    names = [r['name'] for r in S.nightbook_rows(scr) if r['name']]
    known, others = cached_rows(nav, book), other_levels_rows(nav, book)
    # 等级切换后列表要过一会儿才刷新，太早读到的还是上一个等级的行
    stale = names and known[:1] != names[:1] and any(v[:1] == names[:1] for v in others.values())
    # 选中标记读不出来时，行名属于这个等级已知的列表也算确认
    elsewhere = {n for v in others.values() for n in v}
    confirmed = S.selected_level(scr, info['levels']) == book or (names[:1] and names[0] in known
                                                                    and names[0] not in elsewhere)
    if not confirmed or stale:
        if nav.wait(4) is None:
            return None
        st.pop('level', None)
        return False
    return READY


def learn_rows(nav, scr, info, book, st):
    """按位置记行：st['names'] 是从顶部数起的全部行名，st['offset'] 是现在第一行是第几行。

    同一行两次读出的名字可能不一样，所以不按名字去重，而是把看到的几行和已知的行逐行对齐。
    """
    names = [r['name'] for r in S.nightbook_rows(scr)]
    row, known = nav.goal['row'], cached_rows(nav, book)
    if st['names'] is None:
        if isinstance(row, str) and any(n and row in n for n in names):
            st['names'], st['offset'] = [], None
            return READY
        at_cached_top = names and known and names[0] and known[0] and same_name(han(names[0]), han(known[0]))
        if not at_cached_top and not st.get('at_top'):
            # 行号从顶部数起，而列表会记住上次的滚动位置
            nav.log('  把列表滚到顶部')
            nav.b.scroll(0.4, 0.45, 30)
            st['at_top'] = True
            return False
        # 刚切换等级时列表是一行行出来的
        if len(names) < 3 and nav.wait(3) is None:
            return None
        if st.get('at_top') and (st.get('top_read') is None or align(st['top_read'], names) != 0):
            # 一次滚动只挪几行，长列表要一直往上滚，滚了也不变才是到顶了
            st['top_read'] = names
            nav.log('  继续往上滚，现在第一行是 %s' % names[0])
            nav.b.scroll(0.4, 0.45, 30)
            return False
        st['names'], st['offset'] = list(names), 0
    elif st['offset'] is not None:
        offset = align(st['names'], names)
        if offset is None:
            nav.log('  对不上已经看到的行 %s，重新从顶部数' % names)
            st.update(names=None, at_top=False, seen=[], top_read=None)
            return False
        st['offset'] = offset
        for k, n in enumerate(names[:len(st['names']) - offset]):
            if n and st['names'][offset + k] is None:
                st['names'][offset + k] = n
        st['names'] += names[len(st['names']) - offset:]
    if len(st['names']) > len(known):
        nav.cache['names/%d' % book] = list(st['names'])
        nav.save_cache()
    return READY


def open_row(nav, scr, info, book, st):
    listed = S.nightbook_rows(scr)
    names = [r['name'] for r in listed]
    row = nav.goal['row']
    if isinstance(row, str):
        idx = next((k for k, n in enumerate(names) if n and (row in n or same_name(row, n))), None)
    else:
        idx = row - st['offset']
        if idx < 0:
            nav.b.scroll(0.4, 0.45, 3)
            return False
        if idx >= len(listed):
            idx = None
        elif listed[idx]['button'] is None:
            # 这一格的按钮没认出来：先等几帧，还不行就挪一下列表
            if nav.wait(3) is None:
                return None
            nav.b.scroll(0.4, 0.45, -1)
            return False
    if idx is None:
        # 滚到两组之间时一次滚动有时不动，连着三次都是这几行才算到底
        repeats = st['seen'].count(tuple(names))
        if repeats >= 2:
            raise NoSuchEntry(book, row, st['names'])
        st['seen'].append(tuple(names))
        nav.log('  第 %r 行不在 %s 中，向下滚动' % (row, names))
        nav.b.scroll(0.4, 0.45, -3 - 2 * repeats)
        return False
    nav.log('  第 %r 行 -> %s' % (row, names[idx]))
    nav.click(listed[idx]['button'])
    nav.state['entered_row'] = names[idx]
    st.pop('level', None)
    return False
