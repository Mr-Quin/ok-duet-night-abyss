"""Run a farming plan: navigate to each item's start screen, hand over to gameplay, leave when done.

The game's own auto-rounds setting (on the start screen) keeps rounds going without input and
ends on the result screen after N rounds, so gameplay only has to get the first round going:
press start, walk to the objective and wait for combat. Everything after that is menus again.
"""
import time

from src.nav import text_zh as T
from src.nav.nav import Nav, NavError
from src.nav.targets import Nightbook, World


class Gameplay:
    def start_run(self):
        """From the start screen, begin the run and return once combat is underway.

        Return False when the run could not be started; the plan then navigates back to the
        start screen and tries again.
        """
        raise NotImplementedError


def parse_plan(text):
    """'30,0,3; 65,守护野蜂,3' -> [(30, 0, 3), (65, '守护野蜂', 3)]: book level, row, rounds.

    0 rounds only navigates to the start screen and back, without starting a run.
    """
    items = []
    for part in text.replace('；', ';').split(';'):
        if not part.strip():
            continue
        book, row, rounds = [p.strip() for p in part.replace('，', ',').split(',')]
        items.append((int(book), int(row) if row.isdigit() else row, int(rounds)))
    return items


class PlanRunner:
    def __init__(self, backend, gameplay, log=print, nav_log=None, rows_path=None, mode=T.MISSIONS[8], dump_dir=None):
        self.b, self.gameplay, self.say = backend, gameplay, log
        self.nav = Nav(backend, log=nav_log, rows_path=rows_path)
        self.dump_dir = dump_dir
        self.mode = mode

    def run_item(self, book, row, rounds, attempts=2):
        for attempt in range(1, attempts + 1):
            t0 = time.time()
            self.say('navigating to 夜航手册 Lv.%d row %s' % (book, row))
            target = Nightbook(book, row, mode=self.mode, lv=book, auto_rounds=rounds or None)
            self.nav.go(target)
            if rounds == 0:
                self.say('  start screen reached after %.1fs; 0 rounds, leaving' % (time.time() - t0))
                self.nav.go(World())
                return
            self.say('  start screen reached, auto rounds %d, %.1fs' % (rounds, time.time() - t0))
            if self.gameplay.start_run():
                break
            self.say('  gameplay could not start the run (attempt %d)' % attempt)
        else:
            raise NavError('gameplay could not start the run')
        t1 = time.time()
        self.nav.wait_for_run_end()
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
                if self.dump_dir:
                    self.say('  screen saved to %s' % self.b.dump(self.dump_dir, time.strftime('fail_%Y%m%d_%H%M%S')))
                results.append((book, row, 'failed: %s' % e, time.time() - t0))
                break
        for book, row, status, dt in results:
            self.say('Lv.%d row %s: %s (%.0fs)' % (book, row, status, dt))
        return results
