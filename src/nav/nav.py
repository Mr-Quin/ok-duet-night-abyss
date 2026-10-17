"""导航层对外的接口：不管游戏现在在哪个界面，把它带到目标界面，然后交还控制。

    nav = Nav(OkScriptBackend(task))
    nav.go(Nightbook(65, row=2, auto_rounds=3))   # 从任意界面出发，包括局内
    ...功能从开始界面接手...

路上遇到正在进行的一局时，在不损失奖励的时机离开：轮次弹窗撤离、结算界面退出，
或者在本局还没有任何奖励时放弃。
"""
from dataclasses import dataclass, field

from src.nav import screens as S
from src.nav.graph import NavError
from src.nav.navigator import Navigator

IN_RUN = ('dungeon', 'dungeon_menu', 'round_dialog', 'exit_confirm', 'result')


@dataclass
class State:
    screen: str
    info: dict = field(default_factory=dict)

    @property
    def in_run(self):
        return self.screen in IN_RUN or (self.screen == 'manual_popup' and not self.info.get('before_run'))


class Nav:
    def __init__(self, backend, log=None, rows_path=None):
        """rows_path：缓存夜航手册各等级行名的文件，省掉每次把列表滚到顶部。"""
        self.b = backend
        self.log = log or (lambda msg: None)
        self.rows_path = rows_path
        self.atlas = S.load_atlas()

    def where(self):
        screen, info = S.classify(self.b.read(), self.atlas)
        return State(screen, info)

    def go(self, target, max_steps=40):
        """从任意界面到达 target 并完成设置；做不到时抛出 NavError。"""
        nav = Navigator(self.b, target, log=self.log, atlas=self.atlas, rows_path=self.rows_path)
        if not nav.run(max_steps=max_steps):
            raise NavError('没能到达 %s' % (target,))
        target.setup(self)

    def tap(self, x, y):
        before = self.b.thumb()
        self.b.click(x, y)
        self.b.settle(before)

    def set_auto_rounds(self, n):
        """在开始界面把自动轮次关掉（n=0）或打开并设成 n，并读回确认。

        游戏只在从这个界面开局时保存设置，所以调用方设完要接着开局。
        """
        for _ in range(15):
            state = self.where()
            info = state.info
            if state.screen != 'start' or info.get('auto_on') is None:
                raise NavError('%s 上没有自动轮次设置' % state.screen)
            if info['auto_on'] != (n > 0):
                self.log('  自动轮次%s' % ('打开' if n else '关闭'))
                self.tap(*info['auto_switch'])
                continue
            cur, y = info['auto_rounds'], info['auto_buttons_y']
            if n == 0 or cur == n:
                return
            if cur is None:
                raise NavError('自动轮次已打开但读不出轮次数')
            # 两端的按钮直接跳到 1 或 99，加减按钮每次一轮
            if n == 99 or (n > cur and 99 - n < n - cur):
                self.tap(S.AUTO_MAX_X, y)
            elif n < cur and n - 1 < cur - n:
                self.tap(S.AUTO_MIN_X, y)
            else:
                for _ in range(min(abs(cur - n), 10)):
                    self.b.click(S.AUTO_PLUS_X if n > cur else S.AUTO_MINUS_X, y)
                    self.b.sleep(0.12)
        raise NavError('没能把自动轮次设成 %d' % n)
