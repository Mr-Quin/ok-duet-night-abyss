"""从游戏当前所在的任意界面走到目标界面。

每一步读一次画面、做一个动作：画面就是目标则结束；画面在目标路线上则走登记的那条边；
在同级界面之间就直接切换；否则按 Esc 退一层。局内的界面（轮次弹窗、结算、局内菜单）
有单独的处理规则，任何时候都不会丢掉本局已经拿到的奖励。

对界面和操作的认识都在 graph.py 的注册表里，这里只负责照表走。目标见 targets.py。
"""
import json
import time

from src.nav import graph
from src.nav import screens as S
from src.nav import text_zh as T
from src.nav.graph import NavError, NoSuchEntry, WrongMission  # noqa: F401  调用方从这里捕获

# 局内一直等不到弹窗或结算时，最多等这么多次（每次约 0.4 秒加一次识别）
MAX_RUN_WAITS = 400
# 同一个动作做了这么多次界面还没变，就认为卡住了
MAX_REPEATS = 4


def node_of(screen, info):
    key = {'menu': 'name', 'page': 'name', 'book': 'section', 'commission': 'tab', 'start': 'via'}.get(screen)
    return screen, info.get(key) if key else None


def same_node(a, b):
    return a[0] == b[0] and (b[1] is None or a[1] == b[1])


def start_matches(info, goal):
    """开始界面是否就是目标。等级不对但界面上有目标等级可选时返回 None。"""
    if goal.get('via') and info['via'] and goal['via'] != info['via']:
        return False
    if goal.get('mode') and not (info['mode'] and goal['mode'] in info['mode']):
        return False
    if goal.get('lv') and info['lv'] != goal['lv']:
        return None if any(t['lv'] == goal['lv'] for t in info['tiers']) else False
    return True


class Navigator:
    """一次导航。in_dungeon 表示调用方知道正处在局内，认不出的画面（技能特效盖住 HUD）
    一律当作局内，而不是可以退出的菜单。leave 决定路上遇到局内时怎么离开：
    'now' 在第一个不损失奖励的时机离开；'after_rounds' 让游戏的自动轮次打完。
    """

    def __init__(self, backend, target, log=print, in_dungeon=False, atlas=None, rows_path=None, leave='now'):
        self.b, self.in_dungeon, self.leave = backend, in_dungeon, leave
        self.goal, self.route = target.goal(), target.route()
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
        self.run_waits = 0
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
        """画面可能还在淡入时先等等：前 limit 次返回 None（等待），之后返回 False。"""
        self.unsure += 1
        return None if self.unsure <= limit else False

    def step(self):
        scr = self.b.read()
        screen, info = S.classify(scr, self.atlas)
        if self.in_dungeon:
            # 局内 HUD 和大世界一样有 Lv 条，只有结算界面才说明这一局结束了
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

    # 局内界面

    def on_round_dialog(self, scr, info):
        if self.leave == 'after_rounds' and info['auto'] and info['auto'][0] < info['auto'][1]:
            # 自动轮次还没打完，倒计时结束后游戏会自己继续
            return self.wait_in_run()
        self.log('  撤离，轮次 %s' % (info['auto'],))
        self.click(info['retreat'][0])
        return False

    def on_result(self, scr, info):
        self.log('  退出结算界面')
        self.loading = True
        self.b.key('esc')
        return False

    def on_exit_confirm(self, scr, info):
        if self.giving_up and info['confirm']:
            self.log('  确认结束：本局还没有奖励')
            self.click(info['confirm'])
            self.giving_up, self.in_dungeon, self.loading = False, False, True
            return False
        self.log('  取消结束任务的确认')
        if info['cancel']:
            self.click(info['cancel'])
        else:
            self.b.key('esc')
        return False

    def on_dungeon_menu(self, scr, info):
        if self.giving_up and info['nothing_earned']:
            self.log('  放弃挑战：本局还没有奖励')
            self.click(info['give_up'])
            return False
        if self.giving_up:
            self.log('  本局已有奖励，改为等这一轮打完')
        self.giving_up = False
        self.log('  从局内菜单继续游戏')
        self.click(info['resume'])
        return False

    def on_dungeon(self, scr, info):
        # 第一波开始前没有人在打：要么调用方现在就想离开，要么本该走去目标点的逻辑已经停了。
        # 这时放弃不损失任何东西，局内菜单的「无奖励」会再确认一次。
        if info.get('to_objective'):
            self.idle_since = self.idle_since or time.time()
            if self.leave == 'now' or time.time() - self.idle_since > 45:
                self.log('  本局还没开打（轮次 %s），打开菜单离开' % info.get('round'))
                self.giving_up, self.idle_since = True, None
                self.b.key('esc')
                return False
        else:
            self.idle_since = None
        return self.wait_in_run()

    def on_manual_popup(self, scr, info):
        if info.get('before_run'):
            self.log('  关掉开局前的委托手册弹窗，还没开局')
            self.b.key('esc')
            return False
        return self.wait_in_run()

    def wait_in_run(self):
        self.run_waits += 1
        if self.run_waits < MAX_RUN_WAITS:
            return None
        raise NavError('局内等了很久也没有出现轮次弹窗或结算，不会自动放弃这一局')

    def on_unknown(self, scr, info):
        if self.loading and self.run_waits < MAX_RUN_WAITS:
            # 退出副本后的加载画面只有插图和提示，认不出是正常的
            self.run_waits += 1
            return None
        return self.back_out(scr, info)

    on_other_menu = on_unknown

    def back_out(self, scr, info):
        # 多半是还在淡入的界面，先等一下再退
        if self.wait(2) is None:
            return None
        self.b.key('esc')
        return False

    def on_start(self, scr, info):
        if info['via'] is None and info['mode'] is None and self.wait(4) is None:
            return None
        g = self.goal
        if g['screen'] != 'start':
            return NotImplemented
        if g.get('via') == T.TABS[2] and info['via'] == T.TABS[2]:
            return self.adjust_letter_start(info)
        ok = start_matches(info, g)
        if self.entered_row and g.get('mode') and info['mode'] and g['mode'] not in info['mode']:
            raise WrongMission(info['mode'], g['mode'])
        if g.get('via') == T.TABS[1] and g.get('row') is not None and self.entered_row is None:
            # 同一个副本可能出现在好几行里，只有从目标行进来的才算
            ok = False
        if ok:
            return True
        same_dungeon = (not g.get('via') or info['via'] == g['via']) and \
            (not g.get('mode') or (info['mode'] and g['mode'] in info['mode']))
        if same_dungeon and g.get('lv') and len(info['tiers']) > 1 and \
                not any(t['lv'] == g['lv'] for t in info['tiers']):
            raise NavError('%s 没有 Lv.%d，可选 %s' % (info['mode'], g['lv'], [t['lv'] for t in info['tiers']]))
        if ok is None:
            t = next(t for t in info['tiers'] if t['lv'] == g['lv'])
            self.log('  选择 Lv.%d' % g['lv'])
            self.b.click(0.08, t['y'])
            return False
        self.entered_row = None
        self.b.key('esc')
        return False

    def adjust_letter_start(self, info):
        g = self.goal
        if g.get('column') and info['column'] and g['column'] not in info['column']:
            self.log('  栏位不对：%s' % info['column'])
            self.b.key('esc')
            return False
        if info['mode'] and g['mode'] in info['mode']:
            return True
        entry = next((e for e in info['entries'] if g['mode'] in e['mode']), None)
        if entry is None:
            if g.get('column'):
                raise NavError('%s 栏现在是 %s，没有 %s' % (info['column'], [e['mode'] for e in info['entries']], g['mode']))
            self.log('  %s 不在 %s 栏' % (g['mode'], info['column']))
            self.b.key('esc')
            return False
        self.log('  选择 %s' % entry['mode'])
        self.b.click(0.05, entry['y'])
        return False

    def on_commission(self, scr, info):
        if info['tab'] is None:
            # 页签还在动画中，或者鼠标停在某个页签上把它变成了金色
            if self.wait(3) is None:
                if self.unsure == 2:
                    self.b.park()
                return None
        return NotImplemented

    # 菜单树

    def follow_route(self, scr, screen, info):
        here = node_of(screen, info)
        path = self.route
        if same_node(here, path[-1]):
            return True
        on = next((k for k, n in enumerate(path) if same_node(here, n)), None)
        if on is not None:
            step = graph.find_edge(here, path[on + 1])
            if step is None:
                raise NavError('没有从 %s 到 %s 的路' % (here, path[on + 1]))
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
                self.log('%d 步到达' % k)
                return True
            if result is None:
                # 等游戏（动画、局内还在打）不算步数
                waits += 1
                self.b.sleep(0.4)
                continue
            k += 1
            self.unsure = 0
            state = tuple(self.trace[log_len:])
            seen[state] = seen.get(state, 0) + 1
            if seen[state] > MAX_REPEATS:
                raise NavError('一直在重复：%s' % ' / '.join(state))
            self.b.settle(before)
            if seen[state] >= 2:
                # 游戏卡顿时会吞掉输入，重复同一个动作前多等一会儿
                self.b.sleep(1.5 * (seen[state] - 1))
        return False
