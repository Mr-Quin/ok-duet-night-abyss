# æŒ‰é˜¶æ®µè·‘å±€ï¼šæ•°å±€æ•°ã€è½®æ¬¡å¼¹çª—æ€Žä¹ˆå¤„ç†ã€æŒ‰å…³å¡ç±»åž‹é€‰æ‰“æ³•ã€å¡ä½æ—¶é‡æ–°å¯¼èˆª
import unittest

from src.run import loop as L
from src.run import observe as O


class FakeTask:
    def __init__(self):
        self.now = 0.0
        self.calls = []
        self.mission_status = None
        self.current_round = 0

    def sleep(self, seconds):
        self.now += seconds

    def log_info(self, msg):
        pass

    def info_set(self, key, value):
        pass

    def send_key(self, key):
        self.calls.append(('key', key))

    def __getattr__(self, name):
        if name in ('start_mission', 'quit_mission', 'continue_mission', 'choose_letter', 'choose_letter_reward'):
            return lambda: self.calls.append(name)
        if name == 'choose_drop_rate':
            return lambda: self.calls.append(('manual', self.mission_status))
        raise AttributeError(name)


class FakeNav:
    def __init__(self, mode, auto_on=False):
        self.mode = mode
        self.auto_on = auto_on
        self.calls = []

    def go(self, target):
        self.calls.append(('go', target))

    def where(self):
        return type('State', (), {'info': {'mode': self.mode, 'auto_on': self.auto_on}})()

    def set_auto_rounds(self, n):
        self.calls.append(('auto', n))


def behaviour(kind_name, rounds, begins=None):
    class Fake:
        name = kind_name
        names = (kind_name,)
        uses_rounds = rounds
        log = []
        results = list(begins or [])

        def __init__(self, task):
            pass

        def begin(self):
            Fake.log.append('begin')
            return Fake.results.pop(0) if Fake.results else True

        def tick(self):
            return True

        def next_round(self):
            Fake.log.append('next_round')
    return Fake


def run(script, job, mode='æ‰¼å®ˆ/æ— å°½', begins=None, hold=1):
    """script é‡Œæ¯ä¸ªé˜¶æ®µè¿žç€çœ‹åˆ° hold æ‹ï¼›ç”¨å®ŒåŽåœåœ¨æœ€åŽä¸€ä¸ªé˜¶æ®µã€‚"""
    task, nav = FakeTask(), FakeNav(mode)
    frames = [s for s in script for _ in range(hold * O.Observer.SETTLE)]
    look = lambda t: frames.pop(0) if len(frames) > 1 else frames[0]
    defence, expulsion = behaviour('æ‰¼å®ˆ', True, begins), behaviour('é©±ç¦»', False, begins)
    loop = L.RunLoop(task, nav, job, observer=O.Observer(task, look), clock=lambda: task.now,
                     behaviours=(defence, expulsion))
    loop.run()
    return task, nav, loop, defence, expulsion


class TestRunLoop(unittest.TestCase):

    def test_counts_runs_and_goes_home_after_the_last(self):
        task, nav, loop, defence, _ = run(
            [O.START, O.IN_RUN, O.ROUND_DIALOG, O.RESULT, O.MANUAL, O.IN_RUN, O.ROUND_DIALOG, O.RESULT],
            L.Job('target', rounds=1, runs=2))
        self.assertEqual(loop.runs_done, 2)
        self.assertEqual(task.calls.count('quit_mission'), 2)
        self.assertEqual(task.calls.count('start_mission'), 2)
        self.assertEqual(nav.calls[1], ('auto', 0))
        self.assertEqual(nav.calls[-1][0], 'go')
        self.assertEqual(defence.log.count('begin'), 2)

    def test_hands_off_waits_for_the_game_then_retreats_from_a_stuck_dialog(self):
        task, nav, loop, _, _ = run([O.IN_RUN, O.ROUND_DIALOG, O.RESULT], L.Job('target', rounds=3, runs=1), hold=120)
        self.assertIn(('auto', 2), nav.calls)
        self.assertEqual(task.calls.count('quit_mission'), 1)
        self.assertNotIn('continue_mission', task.calls)

    def test_hands_off_leaves_a_dialog_that_goes_away_to_the_game(self):
        task, _, loop, _, _ = run([O.IN_RUN, O.ROUND_DIALOG, O.IN_RUN, O.RESULT], L.Job('target', rounds=3, runs=1),
                                  hold=20)
        self.assertNotIn('quit_mission', task.calls)
        self.assertEqual(loop.runs_done, 1)

    def test_picks_the_behaviour_from_the_mission_type(self):
        task, nav, loop, defence, expulsion = run([O.IN_RUN, O.RESULT], L.Job('target', rounds=3, runs=1),
                                                  mode='é©±ç¦»')
        self.assertEqual(expulsion.log, ['begin'])
        self.assertFalse(any(c[0] == 'auto' for c in nav.calls))

    def test_turns_off_the_games_auto_rounds_for_missions_without_rounds(self):
        task, nav = FakeTask(), FakeNav('避险', auto_on=True)
        frames = [O.IN_RUN] * 2 + [O.RESULT] * 2
        look = lambda t: frames.pop(0) if len(frames) > 1 else frames[0]
        hazard = behaviour('避险', False)
        L.RunLoop(task, nav, L.Job('target', rounds=3, runs=1), observer=O.Observer(task, look),
                  clock=lambda: task.now, behaviours=(hazard,)).run()
        self.assertIn(('auto', 0), nav.calls)

    def test_an_unsupported_mission_type_stops_before_doing_anything(self):
        with self.assertRaises(L.UnsupportedMission):
            run([O.IN_RUN], L.Job('target', runs=1), mode='æŽ¢é™©/æ— å°½')

    def test_a_run_that_was_given_up_does_not_count(self):
        task, _, loop, defence, _ = run([O.IN_RUN, O.START, O.IN_RUN, O.ROUND_DIALOG, O.RESULT],
                                        L.Job('target', rounds=1, runs=1), begins=[False, True])
        self.assertEqual(defence.log.count('begin'), 2)
        self.assertEqual(loop.runs_done, 1)

    def test_a_single_frame_of_the_result_screen_mid_run_is_ignored(self):
        task, nav = FakeTask(), FakeNav('æ‰¼å®ˆ')
        frames = [O.IN_RUN] * 4 + [O.RESULT] + [O.IN_RUN] * 4 + [O.ROUND_DIALOG] * 2 + [O.RESULT] * 2
        look = lambda t: frames.pop(0) if len(frames) > 1 else frames[0]
        loop = L.RunLoop(task, nav, L.Job('target', rounds=1, runs=1), observer=O.Observer(task, look),
                         clock=lambda: task.now, behaviours=(behaviour('æ‰¼å®ˆ', True),))
        loop.run()
        self.assertEqual(loop.runs_done, 1)
        self.assertEqual(task.calls.count('quit_mission'), 1)

    def test_the_manual_popup_layout_depends_on_whether_the_run_has_started(self):
        task, _, _, _, _ = run([O.START, O.MANUAL, O.IN_RUN, O.ROUND_DIALOG, O.MANUAL, O.IN_RUN, O.ROUND_DIALOG,
                                O.RESULT], L.Job('target', rounds=2, runs=1))
        manual = [c for c in task.calls if isinstance(c, tuple) and c[0] == 'manual']
        self.assertEqual(manual[0], ('manual', None))
        self.assertEqual(manual[-1][1], L.Mission.CONTINUE)

    def test_an_unrecognised_screen_for_too_long_navigates_back(self):
        task, nav, loop, _, _ = run([O.OTHER, O.IN_RUN, O.RESULT], L.Job('target', runs=1), hold=120)
        self.assertEqual([c for c in nav.calls if c == ('go', 'target')], [('go', 'target')] * 2)


if __name__ == '__main__':
    unittest.main()
