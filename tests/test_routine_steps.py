# 流程步骤的解析和检查
import unittest

from src.routine.steps import Step, StepError, TaskSpec, dump_steps, parse_steps, spec_of

SPECS = {
    'AutoDailyClaimTask': TaskSpec('AutoDailyClaimTask', '日常领奖', {'历练': True, '声名': True}),
    'AutoNightbookTask': TaskSpec(
        'AutoNightbookTask', '自动夜航手册',
        {'刷几次': 0, '每局轮次': 3, '超时时间': 90.0, '来源': '夜航手册'},
        {'来源': {'type': 'drop_down', 'options': ['夜航手册', '委托']}, '每局轮次': {'min': 1, 'max': 10}}),
    'AutoFishTask': TaskSpec('AutoFishTask', '自动钓鱼', {}),
    'RoutineTask': TaskSpec('RoutineTask', '流程', {}),
}


def steps(*items):
    return {'version': 1, 'steps': list(items)}


class TestParseSteps(unittest.TestCase):

    def check_error(self, raw, *fragments):
        with self.assertRaises(StepError) as ctx:
            parse_steps(raw, SPECS)
        for fragment in fragments:
            self.assertIn(fragment, str(ctx.exception))

    def test_valid_steps_keep_order_and_overrides(self):
        parsed = parse_steps(steps(
            {'task': 'AutoNightbookTask', 'overrides': {'刷几次': 1, '来源': '委托'}},
            {'task': 'AutoDailyClaimTask'},
        ), SPECS)
        self.assertEqual(parsed, [Step('AutoNightbookTask', {'刷几次': 1, '来源': '委托'}),
                                  Step('AutoDailyClaimTask', {})])

    def test_duplicate_steps_are_allowed(self):
        parsed = parse_steps(steps({'task': 'AutoDailyClaimTask'}, {'task': 'AutoDailyClaimTask'}), SPECS)
        self.assertEqual(len(parsed), 2)

    def test_round_trips_through_dump(self):
        parsed = [Step('AutoNightbookTask', {'刷几次': 2}), Step('AutoDailyClaimTask', {})]
        self.assertEqual(parse_steps(dump_steps(parsed), SPECS), parsed)

    def test_int_accepted_for_float_setting(self):
        parsed = parse_steps(steps({'task': 'AutoNightbookTask', 'overrides': {'超时时间': 120}}), SPECS)
        self.assertEqual(parsed[0].overrides['超时时间'], 120.0)

    def test_unknown_task(self):
        self.check_error(steps({'task': 'NoSuchTask'}), '第 1 步', 'NoSuchTask')

    def test_task_not_on_allowlist(self):
        self.check_error(steps({'task': 'AutoFishTask'}), '自动钓鱼', '不能放进流程')

    def test_routine_inside_routine(self):
        self.check_error(steps({'task': 'AutoDailyClaimTask'}, {'task': 'RoutineTask'}), '第 2 步', '不能放进流程')

    def test_unknown_setting(self):
        self.check_error(steps({'task': 'AutoDailyClaimTask', 'overrides': {'协会X': True}}), '协会X', '没有这项设置')

    def test_bad_types(self):
        self.check_error(steps({'task': 'AutoNightbookTask', 'overrides': {'刷几次': '1'}}), '刷几次', 'int')
        self.check_error(steps({'task': 'AutoNightbookTask', 'overrides': {'刷几次': True}}), '刷几次', 'int')
        self.check_error(steps({'task': 'AutoDailyClaimTask', 'overrides': {'历练': 1}}), '历练', 'bool')
        self.check_error(steps({'task': 'AutoNightbookTask', 'overrides': {'来源': 1}}), '来源', 'str')

    def test_option_not_in_drop_down(self):
        self.check_error(steps({'task': 'AutoNightbookTask', 'overrides': {'来源': '密函'}}), '来源', '不在可选项里')

    def test_out_of_range(self):
        self.check_error(steps({'task': 'AutoNightbookTask', 'overrides': {'每局轮次': 0}}), '每局轮次', '超出范围')
        self.check_error(steps({'task': 'AutoNightbookTask', 'overrides': {'每局轮次': 11}}), '每局轮次', '超出范围')

    def test_bad_shape(self):
        self.check_error([], '字典')
        self.check_error({'version': 3, 'steps': []}, '版本')
        self.check_error({'version': 1, 'steps': {}}, '列表')
        self.check_error(steps('AutoDailyClaimTask'), '第 1 步', 'task')
        self.check_error(steps({'task': 'AutoDailyClaimTask', 'overrides': []}), 'overrides')


class TestSpecOf(unittest.TestCase):

    def test_reads_task_attributes(self):
        class AutoDailyClaimTask:
            name = '日常领奖'
            default_config = {'历练': True}
            config_type = None

        spec = spec_of(AutoDailyClaimTask())
        self.assertEqual(spec, TaskSpec('AutoDailyClaimTask', '日常领奖', {'历练': True}, {}))


if __name__ == '__main__':
    unittest.main()
