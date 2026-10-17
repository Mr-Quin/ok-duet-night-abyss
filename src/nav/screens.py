"""Work out which screen a frame shows and read the parameters the navigator acts on."""
import json
import os
import re

import numpy as np

from src.nav import graph
from src.nav import text_zh as T

# tab centres on the commission page and section centres in the book's top bar
TAB_X = [0.137, 0.29, 0.445, 0.6]
TAB_Y = 0.157
SECTION_X = [0.182, 0.302, 0.422, 0.541]
SECTION_Y = 0.027

LEVELS = [20, 30, 40, 50, 55, 60, 65, 70, 75, 80]
LEVEL_X = 0.075
LEVEL_STEP = 0.0731
LEVEL_COLUMN = (0.03, 0.15, 0.11, 0.95)

# 自动轮次 panel on start screens: the switch is on the label's row, the buttons a row below the counter
AUTO_SWITCH_X = 0.9375
AUTO_BUTTONS_DY = 0.039
AUTO_MIN_X, AUTO_MINUS_X, AUTO_PLUS_X, AUTO_MAX_X = 0.612, 0.648, 0.919, 0.955


def load_atlas(path=None):
    path = path or os.path.join(os.path.dirname(__file__), 'atlas_zh.json')
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def selected_tab(scr):
    lit = [scr.lit(x - 0.035, TAB_Y - 0.012, x + 0.035, TAB_Y + 0.012) for x in TAB_X]
    return T.TABS[int(np.argmax(lit))] if max(lit) > 100 else None


def selected_section(scr):
    lit = [scr.lit(x - 0.03, SECTION_Y - 0.012, x + 0.03, SECTION_Y + 0.012) for x in SECTION_X]
    return T.SECTIONS[int(np.argmax(lit))] if max(lit) > 100 else None


def level_positions(scr):
    """Map level -> y of its label in the 夜航手册 column, fitting the fixed spacing so merged OCR boxes still work."""
    pts = []
    for i in scr.items:
        if i['x'] < 0.11 and 0.15 < i['y'] < 0.95:
            nums = [int(n) for n in re.findall(r'\d\d', i['t']) if int(n) in LEVELS]
            if len(nums) == 1:
                pts.append((LEVELS.index(nums[0]), i['y']))
    # OCR sometimes misreads a label (55 as 50), so fit only the labels that agree on the fixed spacing
    offsets = [y - k * LEVEL_STEP for k, y in pts]
    inliers = max(([o for o in offsets if abs(o - ref) < 0.015] for ref in offsets), key=len, default=[])
    if len(inliers) < 2:
        return {}
    top = sorted(inliers)[len(inliers) // 2]
    return {lv: top + k * LEVEL_STEP for k, lv in enumerate(LEVELS)}


def selected_level(scr, levels):
    lit = {lv: scr.lit(0.06, y - 0.02, 0.09, y + 0.02) for lv, y in (levels or {}).items() if 0.2 <= y <= 0.86}
    if not lit:
        return None
    ranked = sorted(lit.items(), key=lambda kv: -kv[1])
    if len(ranked) == 1 or ranked[0][1] > 2 * ranked[1][1] + 20:
        return ranked[0][0]
    return None


def nightbook_rows(scr):
    """Rows on the 夜航手册 page as [{'name', 'button'}], top to bottom."""
    out = []
    for b in scr.find(T.GO, (0.55, 0.2, 0.7, 0.9)):
        names = [i for i in scr.items if 0.1 < i['x'] < 0.3 and abs(i['y'] - b['y']) < 0.03
                 and not any(w in i['t'] for w in T.DROP_WORDS)]
        out.append({'name': names[0]['t'].replace(' ', '') if names else '', 'button': b})
    return out


def start_info(scr):
    items = scr.items
    via = next((i['t'] for i in items if i['x'] < 0.12 and i['y'] < 0.05), None)
    title = next((i['t'] for i in sorted(items, key=lambda i: i['y'])
                  if i['x'] < 0.15 and 0.1 < i['y'] < 0.16), None)
    tiers = []
    for i in items:
        m = re.search(r'[Ll][Vv]\.?\s*(\d+)', i['t'])
        if m and i['x'] < 0.2 and 0.18 < i['y'] < 0.6:
            tiers.append({'lv': int(m.group(1)), 'y': i['y'], 'x': i['x']})
    tiers.sort(key=lambda t: t['y'])
    for t in tiers:
        t['lum'] = scr.brightness(0.03, t['y'] - 0.012, 0.06, t['y'] + 0.012)
    selected = None
    if len(tiers) == 1:
        selected = tiers[0]['lv']
    elif tiers:
        top = max(tiers, key=lambda t: t['lum'])
        rest = sorted(t['lum'] for t in tiers if t is not top)
        if top['lum'] > rest[-1] + 40:
            selected = top['lv']
    # the 夜航手册 variant shows one chip whose text is the mode name
    if len(tiers) == 1:
        chip = [i for i in items if i['x'] < 0.1 and abs(i['y'] - tiers[0]['y']) < 0.02 and 'v' not in i['t'].lower()]
        title = title or (chip[0]['t'] if chip else None)
    # the 委托密函 variant lists the column's missions on the left, each with its own Lv chip
    entries = [{'mode': i['t'], 'y': i['y']} for i in items
               if i['x'] < 0.08 and 0.18 < i['y'] < 0.6 and not re.search(r'\d', i['t'])]
    column = next((i['t'] for i in items if 0.6 < i['x'] < 0.68 and 0.83 < i['y'] < 0.88), None)
    return {'via': via, 'mode': title, 'lv': selected, 'tiers': tiers, 'entries': entries, 'column': column,
            **auto_round_info(scr)}


def auto_round_info(scr):
    """The 自动轮次 panel: a switch on the label's row, and when it is on, a 轮次 N/99 counter below it.

    The panel moves up when it opens, so the controls are placed from the text rather than fixed spots.
    """
    label = next(iter(scr.find(T.AUTO_LABEL, (0.55, 0.4, 0.75, 0.8))), None)
    count = next(((i, re.search(T.AUTO_ROUNDS, i['t'])) for i in scr.items if re.search(T.AUTO_ROUNDS, i['t'])), None)
    return {'auto_on': bool(count) if label else None,
            'auto_rounds': int(count[1].group(1)) if count else None,
            'auto_switch': (AUTO_SWITCH_X, label['y']) if label else None,
            'auto_buttons_y': count[0]['y'] + AUTO_BUTTONS_DY if count else None}


def match_atlas(scr, atlas, prefix):
    """Best atlas screen whose keywords show up at their recorded spots."""
    best, best_score = None, 0.0
    for name, keys in atlas.items():
        if not name.startswith(prefix) or not keys:
            continue
        hits = sum(1 for k in keys if any(i['t'] == k['t'] and abs(i['x'] - k['x']) < 0.05 and abs(i['y'] - k['y']) < 0.05
                                          for i in scr.items))
        if hits >= min(2, len(keys)) and hits / len(keys) > best_score:
            best, best_score = name, hits / len(keys)
    return best[len(prefix):] if best else None


def classify(scr, atlas):
    """Return (screen, info) from the registered detectors, most specific first."""
    return graph.classify(scr, atlas)


# in-run screens come first: the run HUD also has the Lv bar the world check looks for

@graph.detector(10)
def detect_exit_confirm(scr, atlas):
    if scr.find(T.EXIT_CONFIRM):
        return 'exit_confirm', {'cancel': (scr.find(T.CANCEL) or [None])[0], 'confirm': (scr.find(T.CONFIRM) or [None])[-1]}


@graph.detector(20)
def detect_result(scr, atlas):
    if scr.find(T.RESULT) and scr.find_any(T.RESULT_BUTTONS):
        return 'result', {}


@graph.detector(30)
def detect_round_dialog(scr, atlas):
    if scr.find(T.RETREAT) and scr.find(T.CONTINUE):
        # with auto rounds on, the dialog counts down to continuing by itself
        auto = next((re.search(r'(\d+)\s*/\s*(\d+)', i['t']) for i in scr.items
                     if T.AUTO_RUNNING in i['t'] and re.search(r'\d+\s*/\s*\d+', i['t'])), None)
        return 'round_dialog', {'retreat': scr.find(T.RETREAT, exact=True) or scr.find(T.RETREAT),
                                'auto': (int(auto.group(1)), int(auto.group(2))) if auto else None}


@graph.detector(40)
def detect_dungeon_menu(scr, atlas):
    if scr.find(T.GIVE_UP) and scr.find(T.RESUME):
        # the in-run menu lists what the run has earned so far, or 无奖励 when nothing yet
        return 'dungeon_menu', {'resume': scr.find(T.RESUME)[0], 'give_up': scr.find(T.GIVE_UP)[0],
                                'nothing_earned': bool(scr.find(T.NO_REWARD))}


@graph.detector(50)
def detect_manual_popup(scr, atlas):
    # it also has a start-screen button, so it has to be checked before the start screen
    if scr.find(T.MANUAL_SKIP) and scr.find('Space'):
        # before a run the popup has 取消 next to 开始挑战; between rounds it has a single confirm button
        return 'manual_popup', {'before_run': bool(scr.find(T.CANCEL))}


@graph.detector(60)
def detect_start(scr, atlas):
    if scr.find_any(T.START):
        return 'start', start_info(scr)


@graph.detector(70)
def detect_dungeon(scr, atlas):
    hud = (0, 0.15, 0.3, 0.45)
    if any(scr.find(t, hud) for t in T.ROUND_HUD):
        m = next((re.search(T.ROUND_NOW, i['t']) for i in scr.find(T.ROUND_HUD[0], hud) if re.search(T.ROUND_NOW, i['t'])), None)
        return 'dungeon', {'round': int(m.group(1)) if m else None, 'to_objective': bool(scr.find(T.TO_OBJECTIVE, hud))}


@graph.detector(80)
def detect_book(scr, atlas):
    top = (0, 0, 1, 0.06)
    in_book = len([t for t in T.BOOK_MARKERS if scr.find(t, top)]) >= 2 or scr.find(T.BOOK_TITLE, top)
    if not in_book:
        return None
    tabs = [t for t in T.TABS if scr.find(t, (0, 0.12, 0.75, 0.2), exact=True)]
    if len(tabs) >= 3:
        if scr.find(T.GO, (0.55, 0.2, 0.7, 0.7)) and scr.find(T.DROPS):
            return 'commission', {'tab': T.TABS[1], 'levels': level_positions(scr)}
        return 'commission', {'tab': selected_tab(scr)}
    return 'book', {'section': selected_section(scr)}


@graph.detector(90)
def detect_main_menu(scr, atlas):
    if scr.find(T.UID, (0, 0, 0.35, 0.25)) and (scr.find(T.SHOP) or scr.find(T.EVENTS)):
        return 'main_menu', {}


def atlas_screen(scr, atlas):
    for kind in ('menu', 'page'):
        name = match_atlas(scr, atlas, kind + '_')
        if name:
            return kind, {'name': name}
    return None


@graph.detector(100)
def detect_other_menu(scr, atlas):
    if scr.find(T.ESC) or scr.find(T.BACK, (0.9, 0.93, 1, 1)):
        return atlas_screen(scr, atlas) or ('other_menu', {})


@graph.detector(110)
def detect_world(scr, atlas):
    if scr.find(T.LV, (0, 0.9, 0.2, 1)) or scr.find(T.UID, (0.4, 0.95, 0.6, 1)):
        return 'world', {}


@graph.detector(120)
def detect_atlas(scr, atlas):
    return atlas_screen(scr, atlas)
