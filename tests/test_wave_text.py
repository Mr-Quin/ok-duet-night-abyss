import unittest
from types import SimpleNamespace

from src.tasks.CommissionsTask import read_wave


def texts(*names):
    return [SimpleNamespace(name=n) for n in names]


class TestReadWave(unittest.TestCase):

    def test_plain_count(self):
        self.assertEqual(read_wave(texts('0/2')), 0)
        self.assertEqual(read_wave(texts('3/5')), 3)

    def test_label_tail_in_front_of_the_count(self):
        # 保护目标的扼守标签很长，「波次」的「次」会落进识别框
        self.assertEqual(read_wave(texts('次0/2')), 0)
        self.assertEqual(read_wave(texts('次1/2')), 1)

    def test_count_in_a_later_box(self):
        self.assertEqual(read_wave(texts('次', '1/2')), 1)

    def test_nothing_readable(self):
        self.assertIsNone(read_wave(texts('次')))
        self.assertIsNone(read_wave([]))
        self.assertIsNone(read_wave(None))


if __name__ == '__main__':
    unittest.main()
