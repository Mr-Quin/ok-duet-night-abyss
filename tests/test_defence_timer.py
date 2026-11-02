# 扼守的波次超时：波次数字变了或者进了下一轮都重新计时
import unittest

from src.run.defence import Defence


class FakeTask:
    def __init__(self):
        self.current_wave = 0
        self.current_round = 0
        self.config = {'超时时间': 90}
        self.logs = []
        self.exited = False

    def get_wave_info(self):
        pass

    def combat_detection_enabled(self):
        return True

    def skills_ready(self, in_combat):
        return False

    def log_info(self, message):
        self.logs.append(message)

    def exit_mission(self):
        self.exited = True


def defence(task, clock):
    # 不走 __init__：它会读地图和路线文件，这里只测计时
    d = Defence.__new__(Defence)
    d.task, d.clock = task, clock
    d.wave, d.wave_since, d.round = task.current_wave, clock(), task.current_round
    return d


class TestDefenceTimer(unittest.TestCase):

    def setUp(self):
        self.now = 0
        self.task = FakeTask()
        self.d = defence(self.task, lambda: self.now)

    def test_rounds_with_the_same_wave_number_do_not_time_out(self):
        # 保护目标的扼守每轮都是 0/1
        for round_no in range(1, 8):
            self.now += 60
            self.task.current_round = round_no
            self.assertTrue(self.d.tick())
        self.assertFalse(self.task.exited)

    def test_a_wave_stuck_in_one_round_still_times_out(self):
        self.now += 89
        self.assertTrue(self.d.tick())
        self.now += 1
        self.assertFalse(self.d.tick())
        self.assertIn('波次超时，放弃这一局', self.task.logs)


if __name__ == '__main__':
    unittest.main()
