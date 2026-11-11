# 流程里的块：检查、等待、循环、如果，以及步骤写进上下文的结果
import datetime
import unittest

from src.nav import text_zh as T
from src.nav.backend import Screen
from src.routine.game import Game, letter_facts
from src.routine.runner import StepFailed, run_steps
from src.routine.steps import (Check, If, Loop, Step, StepError, TaskSpec, Wait, dump_steps, parse_steps)

SPECS = {
    'AutoDailyClaimTask': TaskSpec('AutoDailyClaimTask', '日常领奖', {'历练': True}),
    'AutoNightbookTask': TaskSpec('AutoNightbookTask', '自动夜航手册', {'刷几次': 0, '每局轮次': 3}),
}
NO_LETTERS = (('密函还有', '否'),)
OFFERED = (('有无尽委托', '是'),)


def v2(*items):
    return {'version': 2, 'steps': list(items)}


class TestParseBlocks(unittest.TestCase):

    def check_error(self, raw, *fragments):
        with self.assertRaises(StepError) as ctx:
            parse_steps(raw, SPECS)
        for fragment in fragments:
            self.assertIn(fragment, str(ctx.exception))

    def test_every_block_round_trips(self):
        parsed = [
            Loop((
                If(NO_LETTERS, '结束循环'),
                Wait(until=OFFERED, most=120),
                Step('AutoNightbookTask', {'刷几次': 1}),
                Wait(minutes=30),
            ), hours=8, until_time='06:00'),
            Check(),
            Loop((Step('AutoDailyClaimTask'),), times=2, until=NO_LETTERS),
            Step('AutoDailyClaimTask'),
        ]
        self.assertEqual(parse_steps(dump_steps(parsed), SPECS), parsed)

    def test_version_one_still_loads(self):
        parsed = parse_steps({'version': 1, 'steps': [{'task': 'AutoDailyClaimTask'}]}, SPECS)
        self.assertEqual(parsed, [Step('AutoDailyClaimTask')])

    def test_a_loop_needs_a_time_limit(self):
        self.check_error(v2({'loop': {'until': [['密函还有', '否']]}, 'steps': [{'task': 'AutoDailyClaimTask'}]}),
                         '第 1 步', '次数、小时或结束时间')

    def test_a_loop_needs_steps(self):
        self.check_error(v2({'loop': {'times': 2}, 'steps': []}), '第 1 步', '里面没有步骤')

    def test_loops_nest_one_level(self):
        inner = {'loop': {'times': 2}, 'steps': [{'task': 'AutoDailyClaimTask'}]}
        parse_steps(v2({'loop': {'times': 2}, 'steps': [inner]}), SPECS)
        self.check_error(v2({'loop': {'times': 2}, 'steps': [{'loop': {'times': 2}, 'steps': [inner]}]}),
                         '第 1.1.1 步', '最多套两层')

    def test_errors_inside_a_loop_name_the_nested_step(self):
        self.check_error(v2({'loop': {'times': 2}, 'steps': [{'task': 'AutoDailyClaimTask'}, {'task': 'Nope'}]}),
                         '第 1.2 步', 'Nope')

    def test_bad_end_time(self):
        self.check_error(v2({'loop': {'until_time': '25:00'}, 'steps': [{'task': 'AutoDailyClaimTask'}]}),
                         '结束时间')

    def test_break_and_next_round_only_inside_a_loop(self):
        self.check_error(v2({'if': [['密函还有', '否']], 'then': '结束循环'}), '第 1 步', '只能放在循环里')
        parse_steps(v2({'check': '委托密函'}, {'if': [['密函还有', '否']], 'then': '结束流程'}), SPECS)

    def test_unknown_condition_and_value(self):
        self.check_error(v2({'check': '委托密函'}, {'if': [['天气', '晴']], 'then': '结束流程'}), '天气')
        self.check_error(v2({'check': '委托密函'}, {'if': [['密函还有', '多']], 'then': '结束流程'}), '多')
        self.check_error(v2({'if': [], 'then': '结束流程'}), '条件')
        self.check_error(v2({'check': '委托密函'}, {'if': [['密函还有', '否']], 'then': '飞走'}), '飞走')

    def test_letter_conditions_need_something_that_reads_letters(self):
        self.check_error(v2({'task': 'AutoDailyClaimTask'}, {'if': [['密函还有', '否']], 'then': '结束流程'}),
                         '密函还有', '没有步骤会读')
        parse_steps(v2({'task': 'AutoNightbookTask'}, {'if': [['密函还有', '否']], 'then': '结束流程'}), SPECS)
        parse_steps(v2({'if': [['上一步结果', '失败']], 'then': '结束流程'}), SPECS)

    def test_wait_is_either_a_time_or_a_condition(self):
        self.check_error(v2({'wait': {}}), '第 1 步', '等多久')
        self.check_error(v2({'wait': {'minutes': 5, 'until': [['有无尽委托', '是']], 'most': 10}}), '等多久')
        self.check_error(v2({'wait': {'until': [['有无尽委托', '是']]}}), '最多等')
        # 等待自己会去看委托密函，只能等那边读得到的
        self.check_error(v2({'wait': {'until': [['上一步结果', '跑了']], 'most': 10}}), '上一步结果')

    def test_unknown_block(self):
        self.check_error(v2({'jump': 3}), '第 1 步', '认不出')


class FakeRoutine:
    def __init__(self, clock):
        self.info = {}
        self.logs = []
        self.clock = clock
        self.sleeps = []

    def log_info(self, message, notify=False, screenshot=False):
        self.logs.append(message)

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.clock.now += seconds


class Clock:
    def __init__(self, hour=7, minute=10):
        self.now = datetime.datetime(2026, 11, 11, hour, minute).timestamp()

    def __call__(self):
        return self.now


class FakeChild:
    def __init__(self, name, runs=None):
        self.name = name
        self.config = {}
        self.info = {}
        self.runs = runs or []
        self.count = 0

    def run(self):
        action = self.runs[self.count] if self.count < len(self.runs) else None
        self.count += 1
        if action:
            action(self)


class FakeGame:
    def __init__(self, clock, boards):
        self.clock = clock
        self.boards = list(boards)
        self.calls = []

    def world(self):
        self.calls.append('world')

    def letters(self):
        self.calls.append('letters')
        return self.boards.pop(0) if len(self.boards) > 1 else self.boards[0]


def skipped_no_letters(child):
    child.routine_facts.update({'上一步结果': '跳过', '密函还有': '否', '有无尽委托': '否'})


def ran(minutes, clock):
    def run(child):
        clock.now += minutes * 60
        child.routine_facts.update({'密函还有': '是', '有无尽委托': '是'})
    return run


def has(endless, left=True):
    return {'有无尽委托': '是' if endless else '否', '密函还有': '是' if left else '否'}


class TestRunBlocks(unittest.TestCase):

    def setUp(self):
        self.clock = Clock()
        self.routine = FakeRoutine(self.clock)

    def run_blocks(self, steps, tasks, boards=(has(True),), keep_going=False):
        self.game = FakeGame(self.clock, boards)
        return run_steps(self.routine, steps, tasks, keep_going=keep_going, game=self.game, clock=self.clock)

    def test_loop_runs_the_given_number_of_times(self):
        daily = FakeChild('日常领奖')
        results = self.run_blocks([Loop((Step('Daily'),), times=3)], {'Daily': daily})
        self.assertEqual(daily.count, 3)
        self.assertEqual(len(results), 3)
        self.assertIn('第 1.1 步 日常领奖：完成', self.routine.logs)

    def test_loop_stops_at_its_hour_limit(self):
        book = FakeChild('自动夜航手册', [ran(25, self.clock)] * 10)
        self.run_blocks([Loop((Step('Book'),), hours=1)], {'Book': book})
        self.assertEqual(book.count, 3)

    def test_loop_stops_at_the_end_time_and_the_wait_is_cut_short(self):
        book = FakeChild('自动夜航手册', [ran(15, self.clock)] * 10)
        self.run_blocks([Loop((Step('Book'), Wait(minutes=30)), until_time='08:00')], {'Book': book})
        # 07:10 跑到 07:25，等到 07:55；再跑到 08:10 已过结束时间，等待一分钟不等
        self.assertEqual(book.count, 2)
        self.assertEqual(datetime.datetime.fromtimestamp(self.clock.now).strftime('%H:%M'), '08:10')

    def test_an_end_time_already_past_today_means_tomorrow(self):
        daily = FakeChild('日常领奖')
        self.run_blocks([Loop((Step('Daily'), Wait(minutes=60)), until_time='06:00')], {'Daily': daily})
        self.assertEqual(daily.count, 23)

    def test_loop_ends_when_its_condition_holds(self):
        book = FakeChild('自动夜航手册', [ran(10, self.clock), ran(10, self.clock), skipped_no_letters])
        after = FakeChild('日常领奖')
        results = self.run_blocks([Loop((Step('Book'),), hours=8, until=NO_LETTERS), Step('After')],
                                  {'Book': book, 'After': after})
        self.assertEqual(book.count, 3)
        self.assertEqual(after.count, 1)
        self.assertIn('第 1.1 步 自动夜航手册：跳过', self.routine.logs)
        self.assertTrue(all(r.ok for r in results))

    def test_if_breaks_out_of_the_loop(self):
        book = FakeChild('自动夜航手册', [ran(10, self.clock), skipped_no_letters])
        daily = FakeChild('日常领奖')
        self.run_blocks([Loop((Step('Book'), If(NO_LETTERS, '结束循环'), Step('Daily')), times=5)],
                        {'Book': book, 'Daily': daily})
        self.assertEqual((book.count, daily.count), (2, 1))

    def test_if_moves_to_the_next_round(self):
        book = FakeChild('自动夜航手册', [skipped_no_letters, ran(10, self.clock), skipped_no_letters])
        daily = FakeChild('日常领奖')
        self.run_blocks([Loop((Step('Book'), If(NO_LETTERS, '下一轮'), Step('Daily')), times=3)],
                        {'Book': book, 'Daily': daily})
        self.assertEqual((book.count, daily.count), (3, 1))

    def test_if_ends_the_routine_without_failing(self):
        daily = FakeChild('日常领奖')
        results = self.run_blocks([Check(), If(NO_LETTERS, '结束流程'), Step('Daily')], {'Daily': daily},
                                  boards=(has(False, left=False),))
        self.assertEqual(daily.count, 0)
        self.assertTrue(all(r.ok for r in results))

    def test_check_writes_what_it_reads(self):
        daily = FakeChild('日常领奖')
        self.run_blocks([Check(), If(OFFERED, '结束流程'), Step('Daily')], {'Daily': daily}, boards=(has(True),))
        self.assertEqual(daily.count, 0)
        self.assertEqual(self.game.calls, ['letters'])

    def test_wait_for_minutes_goes_to_the_world_and_sleeps(self):
        self.run_blocks([Wait(minutes=30)], {})
        self.assertEqual(self.game.calls, ['world'])
        self.assertEqual(sum(self.routine.sleeps), 1800)
        self.assertTrue(all(s <= 60 for s in self.routine.sleeps))

    def test_wait_until_offered_checks_after_each_rotation(self):
        results = self.run_blocks([Wait(until=OFFERED, most=180)], {}, boards=(has(False), has(False), has(True)))
        self.assertEqual(self.game.calls, ['letters', 'world', 'letters', 'world', 'letters'])
        # 07:10 看一次，等到 08:01、09:01 再看
        self.assertEqual(datetime.datetime.fromtimestamp(self.clock.now).strftime('%H:%M'), '09:01')
        self.assertEqual(results[0].outcome, '跑了')

    def test_wait_until_with_a_fixed_interval(self):
        self.run_blocks([Wait(until=OFFERED, every=10, most=60)], {}, boards=(has(False), has(True)))
        self.assertEqual(datetime.datetime.fromtimestamp(self.clock.now).strftime('%H:%M'), '07:20')

    def test_wait_until_gives_up_at_its_limit_and_says_skipped(self):
        daily = FakeChild('日常领奖')
        results = self.run_blocks([Wait(until=OFFERED, most=60), If((('上一步结果', '跳过'),), '结束流程'),
                                   Step('Daily')], {'Daily': daily}, boards=(has(False),))
        self.assertEqual(results[0].outcome, '跳过')
        self.assertEqual(daily.count, 0)
        self.assertLessEqual(self.clock.now - Clock()(), 3600)

    def test_a_failed_step_inside_a_loop_stops_the_routine(self):
        def boom(child):
            raise Exception('没找到关卡')
        daily = FakeChild('日常领奖', [None, boom])
        with self.assertRaises(StepFailed) as raised:
            self.run_blocks([Loop((Step('Daily'),), times=3)], {'Daily': daily})
        self.assertEqual(daily.count, 2)
        self.assertEqual(str(raised.exception), '第 1.1 步 日常领奖：失败，没找到关卡')

    def test_with_keep_going_a_failure_is_seen_by_the_next_condition(self):
        def boom(child):
            raise Exception('没找到关卡')
        daily = FakeChild('日常领奖', [boom])
        with self.assertRaises(StepFailed):
            self.run_blocks([Loop((Step('Daily'), If((('上一步结果', '失败'),), '结束循环')), times=3)],
                            {'Daily': daily}, keep_going=True)
        self.assertEqual(daily.count, 1)

    def test_facts_are_only_handed_to_a_step_while_it_runs(self):
        daily = FakeChild('日常领奖')
        self.run_blocks([Step('Daily')], {'Daily': daily})
        self.assertIsNone(daily.routine_facts)


def board(*texts):
    return Screen(None, [{'t': t, 'x': x, 'y': y} for t, x, y in texts])


class TestReadingLetters(unittest.TestCase):

    def test_endless_in_a_column_that_still_has_letters(self):
        scr = board(('角色', 0.15, 0.4), ('持有数 0', 0.15, 0.43), ('探险/无尽', 0.1, 0.72),
                    ('武器', 0.37, 0.4), ('持有数 188', 0.37, 0.43), ('扼守/无尽', 0.32, 0.72))
        self.assertEqual(letter_facts(scr), {'有无尽委托': '是', '密函还有': '是'})

    def test_endless_only_where_the_letters_ran_out(self):
        scr = board(('角色', 0.15, 0.4), ('持有数 0', 0.15, 0.43), ('探险/无尽', 0.1, 0.72),
                    ('武器', 0.37, 0.4), ('持有数 5', 0.37, 0.43), ('驱离', 0.32, 0.72))
        self.assertEqual(letter_facts(scr), {'有无尽委托': '否', '密函还有': '是'})

    def test_all_columns_empty(self):
        scr = board(*[(c, x, 0.4) for c, x in zip(T.LETTER_COLUMNS, (0.15, 0.37, 0.6))],
                    *[('持有数 0', x, 0.43) for x in (0.15, 0.37, 0.6)])
        self.assertEqual(letter_facts(scr), {'有无尽委托': '否', '密函还有': '否'})

    def test_columns_not_drawn_yet(self):
        self.assertIsNone(letter_facts(board(('委托', 0.1, 0.1))))


class FakeNav:
    def __init__(self, frames):
        self.gone = []
        self.b = self
        self.frames = list(frames)
        self.slept = 0

    def go(self, target):
        self.gone.append(target)

    def read(self):
        return self.frames.pop(0) if len(self.frames) > 1 else self.frames[0]

    def sleep(self, seconds):
        self.slept += seconds


class TestGame(unittest.TestCase):

    def test_letters_opens_the_letter_tab_and_waits_for_the_columns(self):
        from src.nav import CommissionTab
        ready = board(('武器', 0.37, 0.4), ('持有数 3', 0.37, 0.43), ('扼守/无尽', 0.32, 0.72))
        nav = FakeNav([board(), ready])
        self.assertEqual(Game(lambda: nav).letters(), {'有无尽委托': '是', '密函还有': '是'})
        self.assertEqual(nav.gone, [CommissionTab(T.TABS[2])])

    def test_letters_gives_up_when_the_columns_never_show(self):
        from src.nav import NavError
        nav = FakeNav([board()])
        with self.assertRaises(NavError):
            Game(lambda: nav).letters()


if __name__ == '__main__':
    unittest.main()
