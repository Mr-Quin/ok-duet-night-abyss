# 自动扼守主循环在全自动模式下的行为：刷几次、游戏内自动轮次、闲置时重新导航
import unittest

from ok.test.TaskTestCase import TaskTestCase

from src.config import config
from src.tasks.AutoDefence import AutoDefence
from src.tasks.CommissionsTask import Mission

# 每个元素是一次循环看到的画面
START, POPUP, FIGHT, DIALOG, MANUAL, RESULT, MENU = 'start', 'popup', 'fight', 'dialog', 'manual', 'result', 'menu'


class OutOfScreens(Exception):
    pass


class FakeGame:
    """按脚本依次给出画面，记录主循环对每个画面做了什么。"""

    def __init__(self, screens):
        self.screens = list(screens)
        self.seen = []
        self.pressed = []
        self.walks = 0
        self.waited = 0
        self.ran_out = False

    @property
    def now(self):
        if not self.screens:
            raise OutOfScreens()
        return self.screens[0]

    def advance(self):
        self.seen.append(self.screens.pop(0))


class TestAutoDefenceRuns(TaskTestCase):
    task_class = AutoDefence

    config = config

    def run_loop(self, screens, hands_off=False, run_limit=None, recover=None, round_limit=None, game_auto=None,
                 clock_step=None, countdown=1, status=None):
        task, game = self.task, FakeGame(screens)
        game_auto = hands_off if game_auto is None else game_auto

        # 和 CommissionsTask.handle_mission_interface 一样：点开始或再次进行之后不返回状态，
        # 由随后的手册弹窗返回 Mission.START；游戏开了自动确认时弹窗被跳过，直接进局内
        def handle_mission_interface(stop_func=None):
            screen = game.now
            game.advance()
            if screen in (START, RESULT):
                game.pressed.append('start')
                task.mission_status = Mission.START
                return None
            if screen in (POPUP, MANUAL):
                game.pressed.append('manual:%s' % ('between' if task.mission_status == Mission.CONTINUE else 'start'))
                return task.get_return_status()
            if screen == DIALOG:
                if stop_func():
                    game.pressed.append('retreat')
                    return Mission.STOP
                game.pressed.append('continue')
                task.mission_status = Mission.CONTINUE
                return None
            return False

        def sleep(seconds):
            # 开着游戏内自动轮次时，游戏等 countdown 次之后自己从轮次弹窗继续；没开时弹窗一直等人点
            if game_auto and game.now in (DIALOG, MANUAL):
                game.waited += 1
                if game.waited >= countdown:
                    game.waited = 0
                    game.advance()

        def handle_mission_start():
            game.walks += 1

        patches = {
            'in_team': lambda *a, **k: game.now == FIGHT,
            'is_result_screen': lambda: game.now == RESULT,
            'is_between_rounds': lambda: game.now in (DIALOG, MANUAL),
            'find_action_dialog_continue': lambda *a, **k: game.now == DIALOG,
            'find_action_dialog_retreat': lambda *a, **k: False,
            'handle_mission_interface': handle_mission_interface,
            'handle_mission_start': handle_mission_start,
            'move_on_begin': lambda: False,
            'init_all': lambda: None,
            'init_for_next_round': lambda: None,
            'load_char': lambda: None,
            'wait_until': lambda *a, **k: True,
            'sleep': sleep,
            'log_info': lambda *a, **k: None,
            'info_set': lambda *a, **k: None,
            'stop_func': lambda: False,
            'quit_mission': lambda: None,
        }
        original = {name: getattr(task, name) for name in patches}
        import src.tasks.AutoDefence as module
        original_time = module.time.time
        if clock_step:
            clock = {'now': 0.0}
            module.time.time = lambda: clock.__setitem__('now', clock['now'] + clock_step) or clock['now']
        try:
            for name, fn in patches.items():
                setattr(task, name, fn)
            task.mission_status = status
            task.config_external_movement(lambda delay=0: None, {}, recover=recover, hands_off=hands_off,
                                          run_limit=run_limit, round_limit=round_limit)
            task.do_run()
        except OutOfScreens:
            game.ran_out = True
        finally:
            module.time.time = original_time
            for name, fn in original.items():
                setattr(task, name, fn)
            task.config_external_movement(None, {})
        return game

    def test_stops_on_the_result_screen_after_the_limit(self):
        game = self.run_loop([START, POPUP, FIGHT, RESULT, POPUP, FIGHT, RESULT], run_limit=2)
        # 第一局结算时按了「再次进行」，第二局结算时停下
        self.assertEqual(game.pressed, ['start', 'manual:start', 'start', 'manual:start'])
        self.assertEqual(game.walks, 2)

    def test_runs_start_when_the_game_skips_the_popup(self):
        # 游戏内自动确认会跳过开局前的手册弹窗
        game = self.run_loop([START, FIGHT, RESULT, FIGHT, RESULT], run_limit=2)
        self.assertEqual(game.pressed, ['start', 'start'])
        self.assertEqual(game.walks, 2)

    def test_one_round_runs_start_when_the_game_skips_the_popup(self):
        # 每局一轮、不限局数：没有 run_limit 也要认出新的一局并走位
        game = self.run_loop([START, FIGHT, DIALOG, RESULT, FIGHT, DIALOG], round_limit=1)
        self.assertTrue(game.ran_out)
        self.assertEqual(game.walks, 2)
        self.assertEqual(game.pressed, ['start', 'retreat', 'start', 'retreat'])

    def test_a_new_run_after_giving_up_is_walked(self):
        # 走位失败放弃后回到开始界面重开，这次弹窗被跳过
        game = self.run_loop([START, POPUP, FIGHT, START, FIGHT, RESULT], run_limit=1)
        self.assertEqual(game.walks, 2)
        self.assertFalse(game.ran_out)

    def test_a_start_left_over_from_before_does_not_walk(self):
        game = self.run_loop([FIGHT, RESULT], run_limit=1, status=Mission.START)
        self.assertEqual(game.walks, 0)
        self.assertFalse(game.ran_out)

    def test_a_result_screen_left_from_before_is_not_counted(self):
        game = self.run_loop([RESULT, POPUP, FIGHT, RESULT], run_limit=1)
        self.assertEqual(game.pressed, ['start', 'manual:start'])
        self.assertEqual(game.walks, 1)

    def test_a_result_screen_seen_twice_counts_once(self):
        game = self.run_loop([START, POPUP, FIGHT, RESULT, MENU, RESULT, POPUP, FIGHT, RESULT], run_limit=2)
        self.assertEqual(game.walks, 2)

    def test_round_dialogs_are_left_to_the_game_with_auto_rounds(self):
        game = self.run_loop([START, POPUP, FIGHT, DIALOG, FIGHT, DIALOG, FIGHT, RESULT], hands_off=True, run_limit=1)
        self.assertNotIn('continue', game.pressed)
        self.assertEqual(game.walks, 1)

    def test_round_dialogs_are_handled_without_auto_rounds(self):
        game = self.run_loop([START, POPUP, FIGHT, DIALOG, FIGHT, RESULT], run_limit=1)
        self.assertIn('continue', game.pressed)

    def test_round_limit_retreats_at_that_dialog(self):
        game = self.run_loop([START, POPUP, FIGHT, DIALOG, FIGHT, DIALOG, RESULT], run_limit=1, round_limit=2)
        self.assertEqual(game.pressed, ['start', 'manual:start', 'continue', 'retreat'])

    def test_round_limit_cannot_be_combined_with_hands_off(self):
        with self.assertRaises(ValueError):
            self.task.config_external_movement(lambda delay=0: None, {}, hands_off=True, round_limit=1)
        self.task.config_external_movement(None, {})

    def test_a_dialog_the_game_never_continues_is_retreated_from(self):
        game = self.run_loop([START, POPUP, FIGHT, DIALOG, RESULT], hands_off=True, run_limit=1, game_auto=False,
                             clock_step=5)
        self.assertEqual(game.pressed, ['start', 'manual:start', 'retreat'])

    def test_a_stuck_manual_popup_is_answered_as_a_between_rounds_popup(self):
        game = self.run_loop([START, POPUP, FIGHT, MANUAL, FIGHT, RESULT], hands_off=True, run_limit=1,
                             game_auto=False, clock_step=5)
        self.assertEqual(game.pressed, ['start', 'manual:start', 'manual:between'])
        self.assertEqual(game.walks, 1)

    def test_waiting_on_one_dialog_does_not_shorten_the_next(self):
        # 每个弹窗都要等上十几秒游戏才继续；第二个弹窗的 20 秒要重新算
        game = self.run_loop([START, POPUP, FIGHT, DIALOG, FIGHT, DIALOG, FIGHT, RESULT], hands_off=True,
                             run_limit=1, clock_step=2.5, countdown=4)
        self.assertNotIn('retreat', game.pressed)
        self.assertFalse(game.ran_out)

    def test_waiting_longer_than_the_countdown_retreats(self):
        game = self.run_loop([START, POPUP, FIGHT, DIALOG, RESULT], hands_off=True, run_limit=1,
                             clock_step=2.5, countdown=20)
        self.assertEqual(game.pressed, ['start', 'manual:start', 'retreat'])

    def test_idle_on_a_menu_navigates_back(self):
        calls = []
        self.run_loop([MENU, MENU, MENU, START, POPUP, FIGHT, RESULT], run_limit=1,
                      recover=lambda: calls.append('recover'), clock_step=15)
        self.assertEqual(calls, ['recover'])

    def test_result_screen_is_not_the_between_round_popup(self):
        # 轮次之间手册弹窗的「确认选择」和结算的「再次进行」是同一个金色圆环
        self.set_image('tests/images/result_defence.png')
        self.assertTrue(self.task.is_result_screen())
        self.set_image('tests/images/manual_select_next_round.png')
        self.assertFalse(self.task.is_result_screen())


if __name__ == '__main__':
    unittest.main()
