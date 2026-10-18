# 驱离类关卡按进度算超时：进度在涨就一直打，不动才放弃
import unittest

from src.run import expulsion as E


class FakeTask:
    def __init__(self, readings):
        self.readings = list(readings)
        self.config = {"超时时间": 60}
        self.gave_up = False
        self.skill_tick = type('Tick', (), {'reset': lambda s: None, '__call__': lambda s: None})()

    def box_of_screen(self, *args, **kwargs):
        return None

    def ocr(self, box=None, match=None):
        text = self.readings.pop(0) if len(self.readings) > 1 else self.readings[0]
        return [type('Box', (), {'name': text})()] if text else []

    def log_info(self, msg):
        pass

    def give_up_mission(self):
        self.gave_up = True


class TestExpulsionTimeout(unittest.TestCase):

    def setUp(self):
        self.now = [1000.0]
        self.original = E.time.time
        E.time.time = lambda: self.now[0]

    def tearDown(self):
        E.time.time = self.original

    def play(self, readings, seconds):
        task = FakeTask(readings)
        behaviour = E.Expulsion(task)
        behaviour.since = self.now[0]
        alive = True
        for _ in range(seconds // E.PROGRESS_EVERY):
            self.now[0] += E.PROGRESS_EVERY
            alive = behaviour.tick()
            if not alive:
                break
        return task, alive

    def test_a_slow_run_that_keeps_progressing_is_not_given_up(self):
        readings = ['已驱逐敌人：%d/40' % (k // 3) for k in range(120)]
        task, alive = self.play(readings, 300)
        self.assertTrue(alive)
        self.assertFalse(task.gave_up)

    def test_a_run_stuck_at_the_same_count_is_given_up(self):
        task, alive = self.play(['已驱逐敌人：12/40', '已驱逐敌人：24/40'], 300)
        self.assertFalse(alive)
        self.assertTrue(task.gave_up)

    def test_misread_numbers_do_not_keep_a_stuck_run_alive(self):
        readings = ['血清 30%', '血清 3O%', '', '血清 30%', '2440'] * 30
        task, alive = self.play(readings, 300)
        self.assertTrue(task.gave_up)


if __name__ == '__main__':
    unittest.main()
