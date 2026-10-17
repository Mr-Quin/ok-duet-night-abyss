"""The navigator's public face: get the game to a screen from wherever it is, then hand over.

    nav = Nav(OkScriptBackend(task))
    nav.go(Nightbook(65, row=2, auto_rounds=3))   # from any screen, including inside a run
    ...the feature takes over from the start screen...

A run found on the way is left without losing anything it has earned: at a round boundary, from
the result screen, or by giving it up while it has earned nothing yet.
"""
from dataclasses import dataclass, field

from src.nav import screens as S
from src.nav.navigator import Navigator, NavError
from src.nav.targets import World

IN_RUN = ('dungeon', 'dungeon_menu', 'round_dialog', 'exit_confirm', 'result')

__all__ = ['Nav', 'NavError', 'State']


@dataclass
class State:
    screen: str
    info: dict = field(default_factory=dict)

    @property
    def in_run(self):
        return self.screen in IN_RUN or (self.screen == 'manual_popup' and not self.info.get('before_run'))


class Nav:
    def __init__(self, backend, log=None, rows_path=None):
        self.b = backend
        self.log = log or (lambda msg: None)
        self.rows_path = rows_path
        self.atlas = S.load_atlas()

    def where(self):
        screen, info = S.classify(self.b.read(), self.atlas)
        return State(screen, info)

    def go(self, target, max_steps=40):
        """Reach target from any screen and set it up; raises NavError when it cannot."""
        nav = Navigator(self.b, target, log=self.log, atlas=self.atlas, rows_path=self.rows_path)
        if not nav.run(max_steps=max_steps):
            raise NavError('could not reach %s' % (target,))
        target.setup(self)

    def wait_for_run_end(self, max_steps=60):
        """Let a run in progress play its auto rounds, then leave it and return to the world."""
        nav = Navigator(self.b, World(), log=self.log, atlas=self.atlas, rows_path=self.rows_path,
                        in_dungeon=True, leave='after_rounds')
        if not nav.run(max_steps=max_steps):
            raise NavError('the run did not end')

    def tap(self, x, y):
        before = self.b.thumb()
        self.b.click(x, y)
        self.b.settle(before)

    def set_auto_rounds(self, n):
        """On a start screen, switch 自动轮次 off (n=0) or on with n rounds, and check it took."""
        for _ in range(15):
            state = self.where()
            info = state.info
            if state.screen != 'start' or info.get('auto_on') is None:
                raise NavError('no 自动轮次 setting on %s' % state.screen)
            if info['auto_on'] != (n > 0):
                self.log('  switching 自动轮次 %s' % ('on' if n else 'off'))
                self.tap(*info['auto_switch'])
                continue
            cur, y = info['auto_rounds'], info['auto_buttons_y']
            if n == 0 or cur == n:
                return
            if cur is None:
                raise NavError('自动轮次 is on but its count is not readable')
            # the end buttons jump to 1 or 99; from there + and - step by one
            if n == 99 or (n > cur and 99 - n < n - cur):
                self.tap(S.AUTO_MAX_X, y)
            elif n < cur and n - 1 < cur - n:
                self.tap(S.AUTO_MIN_X, y)
            else:
                for _ in range(min(abs(cur - n), 10)):
                    self.b.click(S.AUTO_PLUS_X if n > cur else S.AUTO_MINUS_X, y)
                    self.b.sleep(0.12)
        raise NavError('could not set 自动轮次 to %d' % n)
