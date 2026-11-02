# 计划任务存的是 main.py -t 序号，序号是 onetime_tasks 里的位置（从 1 数）
import unittest

from src.config import config

PINNED = {'AutoNightbookTask': 8, 'AutoDailyClaimTask': 9, 'RoutineTask': 22}


class TestScheduleNumbers(unittest.TestCase):

    def test_scheduled_tasks_keep_their_numbers(self):
        numbers = {name: i for i, (_, name) in enumerate(config['onetime_tasks'], 1)}
        for name, number in PINNED.items():
            self.assertEqual(numbers.get(name), number,
                             f'{name} 不在第 {number} 个了，已有的计划任务会跑错任务。'
                             f'新任务请加在 onetime_tasks 最后')


if __name__ == '__main__':
    unittest.main()
