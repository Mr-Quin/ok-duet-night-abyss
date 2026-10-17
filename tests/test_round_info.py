# 行动抉择弹窗上的轮次读取
import unittest

from ok.test.TaskTestCase import TaskTestCase

from src.config import config
from src.tasks.AutoDefence import AutoDefence


class TestRoundInfo(TaskTestCase):
    task_class = AutoDefence

    config = config

    def test_round_read_from_auto_round_banner(self):
        # 开着游戏内自动轮次时弹窗是三行列表，轮次在顶部横幅「自动轮次中（1/1）」里
        self.set_image('tests/images/nav/round_dialog_auto.png')
        self.task.current_round = 0
        self.task.get_round_info()
        self.assertEqual(self.task.current_round, 1)


if __name__ == '__main__':
    unittest.main()
