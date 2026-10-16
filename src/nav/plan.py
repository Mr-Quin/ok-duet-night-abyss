"""Run a farming plan: navigate to each item's start screen, hand over to gameplay, leave when done.

The game's own auto-rounds setting (on the start screen) keeps rounds going without input and
ends on the result screen after N rounds, so gameplay only has to get the first round going:
press start, walk to the objective and wait for combat. Everything after that is menus again.
"""
import time

from src.nav import screens as S
from src.nav import text_zh as T
from src.nav.navigator import Navigator, NavError

# auto-round controls on the start screen
ROUNDS_MIN, ROUNDS_MINUS, ROUNDS_PLUS = (0.6117, 0.6819), (0.6477, 0.6819), (0.9188, 0.6819)


class Gameplay:
    def start_run(self):
        """From the start screen, begin the run and return once combat is underway.

        Return False when the run could not be started; the plan then navigates back to the
        start screen and tries again.
        """
        raise NotImplementedError


def parse_plan(text):
    """'30,0,3; 65,守护野蜂,3' -> [(30, 0, 3), (65, '守护野蜂', 3)]: book level, row, rounds."""
    items = []
    for part in text.replace('；', ';').split(';'):
        if not part.strip():
            continue
        book, row, rounds = [p.strip() for p in part.replace('，', ',').split(',')]
        items.append((int(book), int(row) if row.isdigit() else row, int(rounds)))
    return items


class PlanRunner:
    def __init__(self, backend, gameplay, log=print, nav_log=None, rows_path=None, mode=T.MISSIONS[8]):
        self.b, self.gameplay, self.say = backend, gameplay, log
        self.nav_log = nav_log or (lambda msg: None)
        self.rows_path = rows_path
        self.mode = mode

    def navigate(self, goal, **kw):
        return Navigator(self.b, goal, log=self.nav_log, rows_path=self.rows_path, **kw)

    def set_auto_rounds(self, n):
        for _ in range(12):
            screen, info = S.classify(self.b.read(), {})
            cur = info.get('auto_rounds') if screen == 'start' else None
            if cur is None:
                raise NavError('auto-round count not readable on %s' % screen)
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

    def run_item(self, book, row, rounds, attempts=2):
        goal = {'screen': 'start', 'via': T.TABS[1], 'book': book, 'row': row, 'mode': self.mode, 'lv': book}
        for attempt in range(1, attempts + 1):
            t0 = time.time()
            self.say('navigating to 夜航手册 Lv.%d row %s' % (book, row))
            if not self.navigate(goal).run():
                raise NavError('could not reach the start screen')
            self.set_auto_rounds(rounds)
            self.say('  start screen reached, auto rounds %d, %.1fs' % (rounds, time.time() - t0))
            if self.gameplay.start_run():
                break
            self.say('  gameplay could not start the run (attempt %d)' % attempt)
        else:
            raise NavError('gameplay could not start the run')
        t1 = time.time()
        self.navigate({'screen': 'world'}, in_dungeon=True).run(max_steps=60)
        self.say('  rounds finished, back in the world after %.0fs' % (time.time() - t1))

    def run(self, plan):
        results = []
        for book, row, rounds in plan:
            t0 = time.time()
            try:
                self.run_item(book, row, rounds)
                results.append((book, row, 'ok', time.time() - t0))
            except NavError as e:
                self.say('  FAILED: %s' % e)
                results.append((book, row, 'failed: %s' % e, time.time() - t0))
                break
        for book, row, status, dt in results:
            self.say('Lv.%d row %s: %s (%.0fs)' % (book, row, status, dt))
        return results
