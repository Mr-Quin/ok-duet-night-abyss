# 流程开跑前等游戏进到能操作的界面：登录、更新后重启、反作弊报错都停下，什么都不点
import unittest

from src.routine import preflight as P


class FakeScreen:
    def __init__(self, name, texts=(), info=None):
        self.name = name
        self.items = [{'t': t, 'x': 0.5, 'y': 0.5} for t in texts]
        self.info = info or {}


class FakeBackend:
    def __init__(self, screens):
        self.screens = list(screens)
        self.actions = []
        self.now = 0.0

    def read(self):
        return self.screens.pop(0) if len(self.screens) > 1 else self.screens[0]

    def click(self, x, y):
        self.actions.append(('click', x, y))

    def key(self, name):
        self.actions.append(('key', name))

    def sleep(self, seconds):
        self.now += seconds


def run(screens):
    backend = FakeBackend(screens)
    logs = []
    result = P.wait_for_game(backend, logs.append, classify=lambda scr: (scr.name, scr.info),
                             clock=lambda: backend.now)
    return result, backend


def blocked(screens):
    backend = FakeBackend(screens)
    try:
        P.wait_for_game(backend, lambda msg: None, classify=lambda scr: (scr.name, scr.info),
                        clock=lambda: backend.now)
    except P.Blocked as e:
        return e, backend
    raise AssertionError('preflight should have stopped')


LOGIN = ['HERO GAMES', '请输入邮箱', '获取验证码', '登录']
PATCH = ['本次更新需要重新启动游戏后生效', '确定']
ANTI_CHEAT = ['An exception occurred when the game security component was running', '1-1812-4331003', '确定']


class TestBlocker(unittest.TestCase):

    def test_each_dialog_has_its_reason(self):
        self.assertEqual(P.blocker(LOGIN), P.LOGIN_REQUIRED)
        self.assertEqual(P.blocker(PATCH), P.NEEDS_RESTART)
        self.assertEqual(P.blocker(ANTI_CHEAT), P.ANTI_CHEAT)

    def test_anti_cheat_wins_over_login_underneath(self):
        self.assertEqual(P.blocker(LOGIN + ANTI_CHEAT), P.ANTI_CHEAT)

    def test_normal_boot_text_is_not_a_blocker(self):
        self.assertIsNone(P.blocker(['HERO', '登录', 'Product Version 1.2.3', '检查更新中']))


class TestWaitForGame(unittest.TestCase):

    def test_waits_through_boot_and_clicks_enter_on_title(self):
        enter = {'t': '点击进入游戏', 'x': 0.5, 'y': 0.8}
        result, backend = run([FakeScreen('unknown'), FakeScreen('boot', ['检查更新中']),
                               FakeScreen('title', info={'enter': enter}), FakeScreen('unknown'),
                               FakeScreen('world')])
        self.assertEqual(result, 'world')
        self.assertEqual(backend.actions, [('click', 0.5, 0.8)])

    def test_already_in_game_returns_at_once(self):
        for name in ('world', 'main_menu', 'dungeon', 'splash'):
            result, backend = run([FakeScreen(name, ['验证码'])])
            self.assertEqual(result, name)
            self.assertEqual(backend.actions, [])

    def test_each_dialog_stops_with_its_reason_and_no_input(self):
        for texts, reason in ((LOGIN, P.LOGIN_REQUIRED), (PATCH, P.NEEDS_RESTART), (ANTI_CHEAT, P.ANTI_CHEAT)):
            e, backend = blocked([FakeScreen('unknown'), FakeScreen('boot', texts)])
            self.assertEqual(e.reason, reason)
            self.assertEqual(e.texts, texts)
            self.assertIn(reason, str(e))
            self.assertEqual(backend.actions, [])

    def test_unlisted_boot_dialog_stops_without_clicking(self):
        e, backend = blocked([FakeScreen('boot_dialog', ['网络连接失败', '重试', '退出'], {'text': '网络连接失败'})])
        self.assertEqual(e.reason, P.STARTUP_DIALOG)
        self.assertEqual(backend.actions, [])

    def test_login_box_flashing_during_auto_login_does_not_stop(self):
        result, _ = run([FakeScreen('boot', LOGIN), FakeScreen('boot', LOGIN), FakeScreen('unknown'),
                         FakeScreen('world')])
        self.assertEqual(result, 'world')

    def test_times_out_without_input_on_unknown_screens(self):
        e, backend = blocked([FakeScreen('unknown', ['某个没见过的界面'])])
        self.assertEqual(e.reason, P.TIMED_OUT)
        self.assertEqual(e.texts, ['某个没见过的界面'])
        self.assertEqual(backend.actions, [])
        self.assertGreaterEqual(backend.now, P.DEADLINE)


if __name__ == '__main__':
    unittest.main()
