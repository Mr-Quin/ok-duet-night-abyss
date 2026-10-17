# 局内目标标记的识别：位置和标记下方的距离
import unittest

from ok.test.TaskTestCase import TaskTestCase

from src.config import config
from src.tasks.AutoDefence import AutoDefence
from src.tasks.fullauto.marker_walk import MarkerWalk


class TestMarkerWalk(TaskTestCase):
    task_class = AutoDefence

    config = config

    def test_marker_and_distance(self):
        self.set_image('tests/images/nav/dungeon_to_objective.png')
        seen = MarkerWalk(self.task).find(self.task.frame)
        self.assertIsNotNone(seen)
        x, metres = seen
        self.assertLess(abs(x), 0.1)
        self.assertEqual(metres, 29)


if __name__ == '__main__':
    unittest.main()
