"""认出当前是哪个界面，并读出导航要用的参数（选中的页签、等级、行、自动轮次等）。"""
import json
import os
import re

import numpy as np

from src.nav import graph
from src.nav import text_zh as T

# 委托页页签中心、手册顶栏分区中心
TAB_X = [0.137, 0.29, 0.445, 0.6]
TAB_Y = 0.157
# 选中页签下面的亮线，比白字暗，所以亮度阈值用 150
TAB_LINE_Y = (0.176, 0.19)
SECTION_X = [0.182, 0.302, 0.422, 0.541]
SECTION_Y = 0.027
# 选中项的白字、亮线或圆圈所占比例在 0.05 以上，未选中的是 0
SELECTED_LIT = 0.03

IN_RUN = ('dungeon', 'dungeon_menu', 'round_dialog', 'exit_confirm', 'result')

LEVELS = [20, 30, 40, 50, 55, 60, 65, 70, 75, 80]
LEVEL_X = 0.075
LEVEL_STEP = 0.0731
LEVEL_COLUMN = (0.03, 0.15, 0.11, 0.95)
# 夜航手册相邻两行「前往」按钮的距离，占画面高度的比例
BOOK_ROW_PITCH = 0.103
# 选中等级外面圆圈的右半边，比白字暗，所以亮度阈值用 120
LEVEL_RING_X = (0.086, 0.095)

# 开始界面的自动轮次面板：开关和标签在同一行，按钮在计数下面一行
AUTO_SWITCH_X = 0.9375
AUTO_BUTTONS_DY = 0.039
AUTO_MIN_X, AUTO_MINUS_X, AUTO_PLUS_X, AUTO_MAX_X = 0.612, 0.648, 0.919, 0.955
# 滑块手柄在轮次 1 时的中心，以及每一轮移动的距离（99 时在 0.894）
AUTO_SLIDER_X, AUTO_SLIDER_STEP = 0.674, 0.00225


def auto_slider_x(rounds):
    return AUTO_SLIDER_X + (rounds - 1) * AUTO_SLIDER_STEP


def load_atlas(path=None):
    path = path or os.path.join(os.path.dirname(__file__), 'atlas_zh.json')
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def selected_tab(scr):
    # 选中页签的字有时会变灰，下面那条亮线一直都在
    lit = [scr.lit(x - 0.06, TAB_LINE_Y[0], x + 0.06, TAB_LINE_Y[1], level=150) for x in TAB_X]
    return T.TABS[int(np.argmax(lit))] if max(lit) > SELECTED_LIT else None


def selected_section(scr):
    lit = [scr.lit(x - 0.03, SECTION_Y - 0.012, x + 0.03, SECTION_Y + 0.012) for x in SECTION_X]
    return T.SECTIONS[int(np.argmax(lit))] if max(lit) > SELECTED_LIT else None


def level_positions(scr):
    """夜航手册左栏 等级 -> 标签 y。按固定间距拟合，OCR 把相邻标签读成一个框时也能定位。"""
    pts = []
    for i in scr.items:
        if i['x'] < 0.11 and 0.15 < i['y'] < 0.95:
            nums = [int(n) for n in re.findall(r'\d\d', i['t']) if int(n) in LEVELS]
            if len(nums) == 1:
                pts.append((LEVELS.index(nums[0]), i['y']))
    # OCR 偶尔会读错标签（55 读成 50），只用间距一致（偏差不到 0.015）的那些点来拟合
    offsets = [y - k * LEVEL_STEP for k, y in pts]
    inliers = max(([o for o in offsets if abs(o - ref) < 0.015] for ref in offsets), key=len, default=[])
    if len(inliers) < 2:
        return {}
    top = sorted(inliers)[len(inliers) // 2]
    return {lv: top + k * LEVEL_STEP for k, lv in enumerate(LEVELS)}


def selected_level(scr, levels):
    # 看选中等级外面那个圈的右半边；圈里的数字在列表滚动过后会变灰
    lit = {lv: scr.lit(LEVEL_RING_X[0], y - 0.03, LEVEL_RING_X[1], y + 0.03, level=120)
           for lv, y in (levels or {}).items() if 0.2 <= y <= 0.86}
    ranked = sorted(lit.items(), key=lambda kv: -kv[1])
    if not ranked or ranked[0][1] < SELECTED_LIT:
        return None
    if len(ranked) == 1 or ranked[0][1] > 2 * ranked[1][1]:
        return ranked[0][0]
    return None


def nightbook_rows(scr):
    """夜航手册页面上的行，[{'name', 'button'}]，从上到下，一格一行。

    行距是固定的，所以按「前往」按钮的高度排格子。只露出一半的行名字读不出来（会读成列表顶上
    的花纹 HTHHHIHRYH），name 为 None；没认出按钮的格子 button 为 None。
    """
    buttons = sorted(scr.find(T.GO, (0.55, 0.2, 0.7, 0.9)), key=lambda b: b['y'])
    if not buttons:
        return []
    slots = {}
    for b in buttons:
        names = [i for i in scr.items if 0.1 < i['x'] < 0.3 and abs(i['y'] - b['y']) < 0.03
                 and not any(w in i['t'] for w in T.DROP_WORDS)]
        name = names[0]['t'].replace(' ', '') if names else ''
        readable = sum('一' <= c <= '鿿' for c in name) >= 2
        slots[round((b['y'] - buttons[0]['y']) / BOOK_ROW_PITCH)] = {'name': name if readable else None, 'button': b}
    return [slots.get(k, {'name': None, 'button': None}) for k in range(max(slots) + 1)]


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
        # 选中行的底色实测在 150 以上，其余在 80 以下
        if top['lum'] > rest[-1] + 40:
            selected = top['lv']
    # 夜航手册进来的开始界面只有一个条目，条目上的字就是委托类型
    if len(tiers) == 1:
        chip = [i for i in items if i['x'] < 0.1 and abs(i['y'] - tiers[0]['y']) < 0.02 and 'v' not in i['t'].lower()]
        title = title or (chip[0]['t'] if chip else None)
    # 委托密函进来的开始界面左侧列出这一栏的几个委托，各带等级
    entries = [{'mode': i['t'], 'y': i['y']} for i in items
               if i['x'] < 0.08 and 0.18 < i['y'] < 0.6 and not re.search(r'\d', i['t'])]
    column = next((i['t'] for i in items if 0.6 < i['x'] < 0.68 and 0.83 < i['y'] < 0.88), None)
    return {'via': via, 'mode': title, 'lv': selected, 'tiers': tiers, 'entries': entries, 'column': column,
            **auto_round_info(scr)}


def auto_round_info(scr):
    """自动轮次面板：标签那一行有开关，打开后下面多出「轮次 N/99」和调节按钮。

    面板打开时会整体上移，所以开关和按钮的位置按文字现找，不用固定坐标。
    """
    label = next(iter(scr.find(T.AUTO_LABEL, (0.55, 0.4, 0.75, 0.8))), None)
    count = next(((i, re.search(T.AUTO_ROUNDS, i['t'])) for i in scr.items if re.search(T.AUTO_ROUNDS, i['t'])), None)
    return {'auto_on': bool(count) if label else None,
            'auto_rounds': int(count[1].group(1)) if count else None,
            'auto_switch': (AUTO_SWITCH_X, label['y']) if label else None,
            'auto_buttons_y': count[0]['y'] + AUTO_BUTTONS_DY if count else None}


def match_atlas(scr, atlas, prefix):
    """关键词出现在记录位置上最多的图鉴界面。"""
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
    """按登记顺序依次尝试各界面判据，返回第一个命中的 (界面, 信息)。"""
    return graph.classify(scr, atlas)


# 启动游戏的画面排在最前面：这些画面上不能按 Esc（左下角就是退出游戏）

@graph.detector(1)
def detect_boot(scr, atlas):
    version = scr.find(T.BOOT_VERSION, (0, 0.9, 0.4, 1))
    if not (version or scr.find_any(T.BOOT_MARKERS)):
        return None
    buttons = [i for b in T.BOOT_DIALOG_BUTTONS for i in scr.find(b, (0.2, 0.3, 0.8, 0.85), exact=True)]
    if buttons:
        text = ' '.join(i['t'] for i in sorted(scr.items, key=lambda i: (i['y'], i['x']))
                        if 0.2 < i['x'] < 0.8 and 0.2 < i['y'] < 0.85)
        return 'boot_dialog', {'text': text}
    enter = scr.find(T.TITLE_ENTER)
    if enter:
        return 'title', {'enter': enter[0]}
    return 'boot', {'login': bool(scr.find(T.LOGIN, (0.3, 0.8, 0.7, 1), exact=True))}


# 局内界面排在前面：局内 HUD 也有大世界判据要找的 Lv 条

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
        # 开着自动轮次时弹窗顶部倒计时自动继续：自动轮次中（x/N）
        auto = next((re.search(r'(\d+)\s*/\s*(\d+)', i['t']) for i in scr.items
                     if T.AUTO_RUNNING in i['t'] and re.search(r'\d+\s*/\s*\d+', i['t'])), None)
        return 'round_dialog', {'retreat': scr.find(T.RETREAT, exact=True) or scr.find(T.RETREAT),
                                'auto': (int(auto.group(1)), int(auto.group(2))) if auto else None}


@graph.detector(40)
def detect_dungeon_menu(scr, atlas):
    if scr.find(T.GIVE_UP) and scr.find(T.RESUME):
        # 局内菜单会列出本局已获得的奖励，什么都没拿到时显示「无奖励」
        return 'dungeon_menu', {'resume': scr.find(T.RESUME)[0], 'give_up': scr.find(T.GIVE_UP)[0],
                                'nothing_earned': bool(scr.find(T.NO_REWARD))}


@graph.detector(50)
def detect_manual_popup(scr, atlas):
    # 手册弹窗上也有开始界面的按钮文字，所以要排在开始界面前面
    if scr.find(T.MANUAL_SKIP) and scr.find('Space'):
        # 开局前的弹窗有「取消」和「开始挑战」，轮次之间的只有一个确认按钮
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
    # 不按轮次打的关卡没有轮次栏，任务栏顶上只写着关卡类型
    title = next((i['t'] for i in scr.items if i['x'] < 0.08 and 0.25 < i['y'] < 0.3 and i['t'] in T.RUN_MODES), None)
    if title:
        return 'dungeon', {'round': None, 'to_objective': False, 'mode': title}


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
