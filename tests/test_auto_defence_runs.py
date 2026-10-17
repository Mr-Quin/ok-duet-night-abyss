# 自动扼守主循环在全自动模式下的行为：刷几次、游戏内自动轮次、闲置时重新导航
import unittest

from ok.test.TaskTestCase import TaskTestCase

from src.config import config
from src.tasks.AutoDefence import AutoDefence
from src.tasks.CommissionsTask import Mission

# 每个元素是一次循环看到的画面：in_team / result / between（轮次弹窗或手册弹窗）
START, FIGHT, DIALOG, RESULT, MENU = 'start', 'fight', 'dialog', 'result', 'menu'


class FakeGame:
    """按脚本依次给出画面，记录主循环对每个画面做了什么。"""

    def __init__(self, screens):
        self.screens = list(screens)
        self.seen = []
        self.pressed = []

    @property
    def now(self):
        if not self.screens:
            raise AssertionError('主循环没有停下，画面已经用完；按过：%s' % self.pressed)
        return self.screens[0]

    def advance(self):
        self.seen.append(self.screens.pop(0))


class TestAutoDefenceRuns(TaskTestCase):
    task_class = AutoDefence

    config = config

    def run_loop(self, screens, hands_off=False, run_limit=None, recover=None):
        task, game = self.task, FakeGame(screens)

        def handle_mission_interface(stop_func=None):
            screen = game.now
            game.advance()
            if screen in (START, RESULT):
                game.pressed.append('start')
                return Mission.START
            if screen == DIALOG:
                game.pressed.append('continue')
                return Mission.CONTINUE
            return False

        def sleep(seconds):
            # 开着游戏内自动轮次时，游戏会自己从轮次弹窗继续；没开时弹窗一直等人点
            if hands_off and game.now == DIALOG:
                game.advance()

        patches = {
            'in_team': lambda *a, **k: game.now == FIGHT,
            'is_result_screen': lambda: game.now == RESULT,
            'is_between_rounds': lambda: game.now == DIALOG,
            'handle_mission_interface': handle_mission_interface,
            'handle_mission_start': lambda: None,
            'move_on_begin': lambda: False,
            'init_all': lambda: None,
            'init_for_next_round': lambda: None,
            'load_char': lambda: None,
            'wait_until': lambda *a, **k: True,
            'sleep': sleep,
            'log_info': lambda *a, **k: None,
        }
        original = {name: getattr(task, name) for name in patches}
        try:
            for name, fn in patches.items():
                setattr(task, name, fn)
            task.config_external_movement(lambda delay=0: None, {}, recover=recover, hands_off=hands_off,
                                          run_limit=run_limit)
            task.do_run()
        finally:
            for name, fn in original.items():
                setattr(task, name, fn)
            task.config_external_movement(None, {})
        return game

    def test_stops_on_the_result_screen_after_the_limit(self):
        game = self.run_loop([START, FIGHT, RESULT, FIGHT, RESULT], run_limit=2)
        # 第一局结算时按了「再次进行」，第二局结算时停下
        self.assertEqual(game.pressed, ['start', 'start'])
        self.assertEqual(game.seen, [START, FIGHT, RESULT, FIGHT])

    def test_round_dialogs_are_left_to_the_game_with_auto_rounds(self):
        game = self.run_loop([START, FIGHT, DIALOG, FIGHT, DIALOG, FIGHT, RESULT], hands_off=True, run_limit=1)
        self.assertNotIn('continue', game.pressed)

    def test_round_dialogs_are_handled_without_auto_rounds(self):
        game = self.run_loop([START, FIGHT, DIALOG, FIGHT, RESULT], run_limit=1)
        self.assertIn('continue', game.pressed)

    def test_idle_on_a_menu_navigates_back(self):
        calls = []
        clock = {'now': 0.0}
        import src.tasks.AutoDefence as module
        original_time = module.time.time
        module.time.time = lambda: clock.__setitem__('now', clock['now'] + 15) or clock['now']
        try:
            self.run_loop([MENU, MENU, MENU, START, FIGHT, RESULT], run_limit=1,
                          recover=lambda: calls.append('recover'))
        finally:
            module.time.time = original_time
        self.assertEqual(calls, ['recover'])


if __name__ == '__main__':
    unittest.main()
