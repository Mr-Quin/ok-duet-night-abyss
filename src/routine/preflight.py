"""流程开跑前，先等游戏从启动进到能操作的界面。

启动时有三种界面流程不替用户处理：要手动登录、更新后要重启游戏、反作弊报错。
碰到它们什么都不点、不按 Esc，直接停下并说明原因。导航层遇到认不出的界面会按 Esc，
所以这里不走导航，只认界面、等，以及在标题界面点「进入游戏」。
"""
import time

from src.nav import screens as S

DEADLINE = 180
POLL = 1.0
# 同一个原因连续读到这么多次才停：自动登录时登录框会一闪而过
CONFIRM = 3
STARTING = ('unknown', 'boot', 'title', 'boot_dialog')

LOGIN_REQUIRED = 'login required'
NEEDS_RESTART = 'game update needs restart'
ANTI_CHEAT = 'anti-cheat dialog'
STARTUP_DIALOG = 'startup dialog'
TIMED_OUT = 'startup timed out'

REASON_TEXT = {
    LOGIN_REQUIRED: '要手动登录',
    NEEDS_RESTART: '更新后要重启游戏',
    ANTI_CHEAT: '反作弊报错',
    STARTUP_DIALOG: '启动时弹出对话框',
    TIMED_OUT: '三分钟内没进游戏',
}

# 按顺序判断：反作弊报错可能叠在登录框上面
BLOCKERS = (
    (ANTI_CHEAT, ('4331003', '1-1812', 'security component', '安全组件', '反作弊')),
    (NEEDS_RESTART, ('重新启动游戏', '重启游戏')),
    (LOGIN_REQUIRED, ('验证码', '邮箱', '密码', 'Email', 'email')),
)


class Blocked(Exception):
    def __init__(self, reason, texts):
        self.reason = reason
        self.texts = texts
        super().__init__(f'{reason}（{REASON_TEXT[reason]}）')


def blocker(texts):
    joined = ' '.join(texts)
    for reason, keys in BLOCKERS:
        if any(k in joined for k in keys):
            return reason
    return None


def wait_for_game(backend, log, classify=None, clock=time.monotonic, deadline=DEADLINE):
    """等到游戏进了大世界、菜单或局内，返回那个界面名；停下时抛 Blocked。"""
    if classify is None:
        atlas = S.load_atlas()
        classify = lambda scr: S.classify(scr, atlas)
    end = clock() + deadline
    seen, streak = None, 0
    while True:
        scr = backend.read()
        texts = [i['t'] for i in scr.items]
        screen, info = classify(scr)
        # 进了游戏就交给导航层，游戏里的文字（比如聊天）不该被当成启动时的弹窗
        if screen not in STARTING:
            return screen
        reason = blocker(texts) or (STARTUP_DIALOG if screen == 'boot_dialog' else None)
        streak = streak + 1 if reason and reason == seen else int(bool(reason))
        seen = reason
        if reason and streak >= CONFIRM:
            raise Blocked(reason, texts)
        if not reason and screen == 'title':
            log('  点击进入游戏')
            backend.click(info['enter']['x'], info['enter']['y'])
        if clock() >= end:
            raise Blocked(TIMED_OUT, texts)
        backend.sleep(POLL)
