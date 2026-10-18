"""一局里现在处在哪个阶段，只用模板和颜色判断，每一拍都能看。

认不出来的（加载、菜单、别的弹窗）都算 OTHER，交给导航去认。
"""
IN_RUN = 'in_run'
LETTER_REWARD = 'letter_reward'
LETTER = 'letter'
MANUAL = 'manual'
RESULT = 'result'
START = 'start'
ROUND_DIALOG = 'round_dialog'
ESC_MENU = 'esc_menu'
OTHER = 'other'


def observe(task):
    # ESC 菜单开着时 in_team() 也为真，要先认菜单
    if task.find_esc_menu():
        return ESC_MENU
    # 驱逐的开始界面上 in_team() 也会认成局内
    if task.find_start_interface():
        return START
    if task.in_team():
        return IN_RUN
    if task.find_letter_reward_btn():
        return LETTER_REWARD
    if task.find_letter_interface():
        return LETTER
    # 手册弹窗的「确认选择」和结算的「再次进行」是同一个金色圆环，手册要排在结算前面
    if task.find_manual_select_btn():
        return MANUAL
    if task.find_result_again_btn():
        return RESULT
    if task.find_action_dialog_continue() or task.find_action_dialog_retreat():
        return ROUND_DIALOG
    return OTHER


class Observer:
    """连着看到同一个阶段 SETTLE 次才算进了这个阶段，过渡动画里一闪而过的画面不算。"""

    SETTLE = 2

    def __init__(self, task, look=observe):
        self.task = task
        self.look = look
        self.state = None
        self.since = None
        self._seen, self._count = None, 0

    def next(self, now):
        """现在的阶段；这一帧和认定的阶段不一样（画面在变）时返回 None，别按旧阶段做事。"""
        seen = self.look(self.task)
        if seen == self._seen:
            self._count += 1
        else:
            self._seen, self._count = seen, 1
        if self._count >= self.SETTLE and seen != self.state:
            self.state, self.since = seen, now
        return self.state if seen == self.state else None
