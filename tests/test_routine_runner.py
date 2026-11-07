# 流程按顺序跑子任务：临时设置不落盘、停止交给流程、失败后停或继续、失败后按设置关游戏、没密函时按设置跳过或等轮换
import json
import sys
import unittest
from unittest import mock

from ok.task.exceptions import FinishedException, TaskDisabledException
from ok.test.TaskTestCase import TaskTestCase

from src.config import config
from src.nav import NoLetters, NotOffered
from src.routine.preflight import ANTI_CHEAT, LOGIN_REQUIRED, Blocked
from src.routine.runner import StepFailed, run_steps
from src.routine.steps import Step
from src.tasks.fullauto import RoutineTask as R
from src.tasks.fullauto.AutoDailyClaimTask import AutoDailyClaimTask
from src.tasks.fullauto.AutoNightbookTask import AutoNightbookTask


class SavedConfig(dict):
    def __init__(self, *args):
        super().__init__(*args)
        self.writes = []

    def __setitem__(self, key, value):
        self.writes.append(key)
        super().__setitem__(key, value)


class FakeRoutine:
    def __init__(self):
        self.info = {}
        self.logs = []

    def log_info(self, message, notify=False, screenshot=False):
        self.logs.append(message)


class FakeChild:
    def __init__(self, name, action=None):
        self.name = name
        self.config = SavedConfig({'刷几次': 0})
        self.info = {'own': True}
        self.action = action
        self.seen = []

    def run(self):
        self.seen.append((dict(self.config), self.info))
        if self.action:
            self.action()


def boom():
    raise Exception('没找到关卡')


class TestRunSteps(unittest.TestCase):

    def setUp(self):
        self.routine = FakeRoutine()

    def test_runs_in_order_with_overrides_that_do_not_persist(self):
        order = []
        book = FakeChild('自动夜航手册', lambda: order.append('book'))
        daily = FakeChild('日常领奖', lambda: order.append('daily'))
        saved = book.config
        results = run_steps(self.routine, [Step('Book', {'刷几次': 1}), Step('Daily')],
                            {'Book': book, 'Daily': daily})
        self.assertEqual(order, ['book', 'daily'])
        self.assertEqual(book.seen[0][0], {'刷几次': 1})
        self.assertIs(book.seen[0][1], self.routine.info)
        self.assertIs(book.config, saved)
        self.assertEqual(saved, {'刷几次': 0})
        self.assertEqual(saved.writes, [])
        self.assertEqual(book.info, {'own': True})
        self.assertTrue(all(r.ok for r in results))
        self.assertIn('第 1 步 自动夜航手册：完成', self.routine.logs)

    def test_config_restored_after_failure(self):
        book = FakeChild('自动夜航手册', boom)
        saved = book.config
        with self.assertRaises(StepFailed):
            run_steps(self.routine, [Step('Book', {'刷几次': 1})], {'Book': book})
        self.assertIs(book.config, saved)
        self.assertEqual(saved, {'刷几次': 0})

    def test_stop_and_finish_end_the_routine_even_with_keep_going(self):
        for exc in (TaskDisabledException, FinishedException):
            daily = FakeChild('日常领奖')

            def raise_exc():
                raise exc()

            with self.assertRaises(exc):
                run_steps(self.routine, [Step('Book'), Step('Daily')],
                          {'Book': FakeChild('自动夜航手册', raise_exc), 'Daily': daily}, keep_going=True)
            self.assertEqual(daily.seen, [])

    def test_failure_stops_by_default(self):
        daily = FakeChild('日常领奖')
        with self.assertRaises(StepFailed) as ctx:
            run_steps(self.routine, [Step('Book'), Step('Daily')],
                      {'Book': FakeChild('自动夜航手册', boom), 'Daily': daily})
        self.assertEqual(daily.seen, [])
        self.assertEqual(str(ctx.exception), '第 1 步 自动夜航手册：失败，没找到关卡')

    def test_keep_going_runs_the_rest_then_reports_failure(self):
        daily = FakeChild('日常领奖')
        with self.assertRaises(StepFailed) as ctx:
            run_steps(self.routine, [Step('Book'), Step('Daily')],
                      {'Book': FakeChild('自动夜航手册', boom), 'Daily': daily}, keep_going=True)
        self.assertEqual(len(daily.seen), 1)
        self.assertEqual([r.ok for r in ctx.exception.results], [False, True])

    def test_each_step_records_into_the_routine_evidence(self):
        self.routine.evidence = FakeEvidence()
        during = []
        book = FakeChild('自动夜航手册')
        book.action = lambda: during.append(book.evidence)
        daily = FakeChild('日常领奖', boom)
        with self.assertRaises(StepFailed):
            run_steps(self.routine, [Step('Book'), Step('Daily')], {'Book': book, 'Daily': daily}, keep_going=True)
        self.assertEqual(during, [self.routine.evidence])
        self.assertIsNone(book.evidence)
        self.assertEqual(self.routine.evidence.slugs, ['step1-start', 'step1-done', 'step2-start', 'step2-failed'])


class FakeEvidence:
    def __init__(self):
        self.slugs = []
        self.folder = 'logs/runs/test'

    def record(self, slug, text, frame=None):
        self.slugs.append(slug)


class FakeRoutineTask(FakeRoutine):
    def __init__(self, steps, tasks, exit_after=False, config_exit=False):
        super().__init__()
        self.config = {'失败后继续': False, 'Exit After Task': config_exit}
        self.exit_after_task = exit_after
        self.executor = mock.Mock()
        self._steps = (steps, tasks)

    def steps(self):
        return self._steps

    close_if_exit = R.RoutineTask.close_if_exit


class TestRoutineTaskRun(unittest.TestCase):

    def run_routine(self, task, preflight=None):
        self.evidence = FakeEvidence()
        with mock.patch.object(R, 'communicate') as communicate, \
                mock.patch.object(R, 'OkScriptBackend'), \
                mock.patch.object(R, 'Evidence', return_value=self.evidence), \
                mock.patch.object(R, 'wait_for_game', side_effect=preflight) as wait:
            try:
                R.RoutineTask.run(task)
            finally:
                self.quit = communicate.quit.emit
                self.waited = wait.called

    def test_a_finished_routine_leaves_its_checkpoints(self):
        self.run_routine(FakeRoutineTask([Step('Book')], {'Book': FakeChild('自动夜航手册')}))
        self.assertEqual(self.evidence.slugs, ['ready', 'step1-start', 'step1-done', 'end'])

    def test_a_blocked_start_is_recorded(self):
        with self.assertRaises(Exception):
            self.run_routine(FakeRoutineTask([Step('Book')], {'Book': FakeChild('自动夜航手册')}),
                             Blocked(LOGIN_REQUIRED, ['邮箱']))
        self.assertEqual(self.evidence.slugs, ['blocked'])

    def failing(self, **kwargs):
        return FakeRoutineTask([Step('Book')], {'Book': FakeChild('自动夜航手册', boom)}, **kwargs)

    def test_preflight_runs_before_the_steps(self):
        book = FakeChild('自动夜航手册')
        self.run_routine(FakeRoutineTask([Step('Book')], {'Book': book}))
        self.assertTrue(self.waited)
        self.assertEqual(len(book.seen), 1)

    def test_blocked_start_skips_steps_and_closes_when_exit_is_set(self):
        book = FakeChild('自动夜航手册')
        task = FakeRoutineTask([Step('Book')], {'Book': book}, exit_after=True)
        with self.assertRaisesRegex(Exception, 'login required'):
            self.run_routine(task, Blocked(LOGIN_REQUIRED, ['邮箱', '验证码']))
        self.assertEqual(book.seen, [])
        task.executor.device_manager.stop_hwnd.assert_called_once()
        self.quit.assert_called_once()
        self.assertTrue(any('邮箱 验证码' in line for line in task.logs))

    def test_anti_cheat_leaves_the_game_open_even_with_exit(self):
        task = FakeRoutineTask([Step('Book')], {'Book': FakeChild('自动夜航手册')}, exit_after=True)
        with self.assertRaisesRegex(Exception, 'anti-cheat'):
            self.run_routine(task, Blocked(ANTI_CHEAT, ['1-1812-4331003']))
        task.executor.device_manager.stop_hwnd.assert_not_called()
        self.quit.assert_not_called()

    def test_failure_closes_game_and_app_when_exit_is_set(self):
        for kwargs in ({'exit_after': True}, {'config_exit': True}):
            task = self.failing(**kwargs)
            with self.assertRaisesRegex(Exception, '没找到关卡'):
                self.run_routine(task)
            task.executor.device_manager.stop_hwnd.assert_called_once()
            self.quit.assert_called_once()

    def test_failure_leaves_game_open_without_exit(self):
        task = self.failing()
        with self.assertRaises(Exception):
            self.run_routine(task)
        task.executor.device_manager.stop_hwnd.assert_not_called()
        self.quit.assert_not_called()

    def test_stop_does_not_close_the_game(self):
        def stop():
            raise TaskDisabledException()

        task = FakeRoutineTask([Step('Book')], {'Book': FakeChild('自动夜航手册', stop)}, exit_after=True)
        with self.assertRaises(TaskDisabledException):
            self.run_routine(task)
        task.executor.device_manager.stop_hwnd.assert_not_called()


class TestStoppingAStep(unittest.TestCase):

    def test_stopping_the_daily_claims_reaches_the_routine(self):
        task = mock.MagicMock(config={})
        with mock.patch.object(sys.modules[AutoDailyClaimTask.__module__], 'Claimer') as claimer:
            claimer.return_value.run.side_effect = TaskDisabledException()
            with self.assertRaises(TaskDisabledException):
                AutoDailyClaimTask.run(task)

    def test_stopping_the_nightbook_reaches_the_routine(self):
        task = mock.MagicMock(config={})
        module = sys.modules[AutoNightbookTask.__module__]
        with mock.patch.object(module, 'RunLoop') as loop, mock.patch.object(module.DNAOneTimeTask, 'run'):
            loop.return_value.run.side_effect = TaskDisabledException()
            with self.assertRaises(TaskDisabledException):
                AutoNightbookTask.run(task)


class TestNoLetters(unittest.TestCase):

    def run_book(self, config, error):
        task = mock.MagicMock(config=config, evidence=None)
        module = sys.modules[AutoNightbookTask.__module__]
        with mock.patch.object(module, 'RunLoop') as loop, mock.patch.object(module.DNAOneTimeTask, 'run'):
            loop.return_value.run.side_effect = error
            AutoNightbookTask.run(task)
        return task

    def test_no_letters_fails_the_step(self):
        with self.assertRaisesRegex(Exception, '密函用完了'):
            self.run_book({}, NoLetters('角色'))

    def test_no_letters_skips_the_step_when_asked(self):
        task = self.run_book({'没有密函就跳过': True}, NoLetters('角色'))
        self.assertIn('跳过', task.log_info.call_args[0][0])

    def test_nothing_offered_skips_the_step_when_asked(self):
        task = self.run_book({'没有密函就跳过': True}, NotOffered(None, '/无尽', {}))
        self.assertIn('跳过', task.log_info.call_args[0][0])


class TestWaitingForLetters(unittest.TestCase):
    OFFERED = {'角色': ['驱逐']}

    def setUp(self):
        self.book = sys.modules[AutoNightbookTask.__module__]
        # 整点后 10 分钟
        self.now = self.book.LETTER_ROTATION * 100 + 600
        self.task = mock.MagicMock(evidence=None)
        self.task.sleep.side_effect = self.pass_time

    def pass_time(self, seconds):
        self.now += seconds

    def wait(self, hours, *results):
        self.task.config = {'等委托最多几小时': hours}
        self.run = mock.MagicMock(side_effect=list(results))
        AutoNightbookTask.until_offered(self.task, self.run, clock=lambda: self.now)

    def not_offered(self, offered=OFFERED):
        return NotOffered(None, '/无尽', offered)

    def test_does_not_wait_by_default(self):
        with self.assertRaises(NotOffered):
            self.wait(0, self.not_offered())
        self.task.sleep.assert_not_called()

    def test_waits_for_the_next_rotation_and_tries_again(self):
        self.wait(2, self.not_offered(), None)
        self.assertEqual(self.run.call_count, 2)
        self.task.sleep.assert_called_once_with(self.book.LETTER_ROTATION - 600 + self.book.ROTATION_GRACE)

    def test_stops_waiting_at_the_limit(self):
        with self.assertRaises(NotOffered):
            self.wait(1, self.not_offered(), self.not_offered(), None)
        self.assertEqual(self.run.call_count, 2)

    def test_does_not_wait_when_no_column_has_letters(self):
        with self.assertRaises(NotOffered):
            self.wait(2, self.not_offered({}))
        self.task.sleep.assert_not_called()


class TestRoutineTaskSteps(TaskTestCase):
    task_class = R.RoutineTask
    config = config

    def setUp(self):
        # 测试用的 ok 不加载 onetime_tasks，这里用真实的两个任务和流程自己顶上
        executor = self.task.executor
        tasks = [AutoDailyClaimTask(executor, None), AutoNightbookTask(executor, None), self.task]
        patcher = mock.patch.object(executor, 'onetime_tasks', tasks)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_default_steps_parse_against_registered_tasks(self):
        steps, tasks = self.steps_from(R.DEFAULT_STEPS)
        self.assertEqual(steps, [Step('AutoDailyClaimTask')])
        self.assertIn('AutoNightbookTask', tasks)

    def steps_from(self, text):
        # 换成普通 dict，免得测试改写真实的 configs/RoutineTask.json
        saved = self.task.config
        self.task.config = {'步骤': text}
        try:
            return self.task.steps()
        finally:
            self.task.config = saved

    def test_nightbook_override_parses_against_its_real_settings(self):
        steps, _ = self.steps_from(json.dumps(
            {'version': 1, 'steps': [{'task': 'AutoNightbookTask', 'overrides': {'刷几次': 1}}]}))
        self.assertEqual(steps, [Step('AutoNightbookTask', {'刷几次': 1})])

    def test_only_the_routine_can_be_scheduled(self):
        scheduled = [type(t).__name__ for t in self.task.executor.onetime_tasks if t.support_schedule_task]
        self.assertEqual(scheduled, ['RoutineTask'])

    def test_bad_json_is_reported(self):
        with self.assertRaisesRegex(Exception, '不是合法的 JSON'):
            self.steps_from('{')


if __name__ == '__main__':
    unittest.main()
