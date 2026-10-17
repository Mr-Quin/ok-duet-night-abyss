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
from src.nav.targets import StartScreen

# auto-round controls on the start screen
ROUNDS_MIN, ROUNDS_MINUS, ROUNDS_PLUS = (0.6117, 0.6819), (0.6477, 0.6819), (0.9188, 0.6819)

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
        nav = Navigator(self.b, target.goal(), log=self.log, atlas=self.atlas, rows_path=self.rows_path)
        if not nav.run(max_steps=max_steps):
            raise NavError('could not reach %s' % (target,))
        if isinstance(target, StartScreen) and target.auto_rounds is not None:
            self.set_auto_rounds(target.auto_rounds)

    def wait_for_run_end(self, max_steps=60):
        """Let a run in progress play its auto rounds, then leave it and return to the world."""
        nav = Navigator(self.b, {'screen': 'world'}, log=self.log, atlas=self.atlas, rows_path=self.rows_path,
                        in_dungeon=True, leave='after_rounds')
        if not nav.run(max_steps=max_steps):
            raise NavError('the run did not end')

    def set_auto_rounds(self, n):
        for _ in range(12):
            state = self.where()
            cur = state.info.get('auto_rounds') if state.screen == 'start' else None
            if cur is None:
                raise NavError('auto-round count not readable on %s' % state.screen)
            if cur == n:
                return
            if cur - n > 8:
                before = self.b.thumb()
                self.b.click(*ROUNDS_MIN)
                self.b.settle(before)
                continue
            for _ in range(min(abs(cur - n), 10)):
                self.b.click(*(ROUNDS_MINUS if cur > n else ROUNDS_PLUS))
                self.b.sleep(0.12)
        raise NavError('could not set auto rounds to %d' % n)
