"""探险：走到「操作装置」，按交互键打开机关，再按 F 快速破解，之后和避险一样打怪攒满血清。

装置只在开局时操作一次；之后每一轮之间只有轮次弹窗和选密函，开着自动轮次时游戏自己处理。
"""
import re
import time

from src.run.expulsion import PROGRESS_BOX, Expulsion
from src.tasks.fullauto.marker_walk import STEER, MarkerWalk

# 走到装置前时右边出现的「F ▸ 操作」提示。标记旁的「操作装置」也会落进这个框，不能算
PROMPT_BOX = (0.55, 0.45, 0.85, 0.55)
PROMPT = '操作'
NOT_PROMPT = '装置'
# 机关界面右下角的「快速破解」按钮，按 F；破解后中间显示「破解成功」
QUICK_SOLVE_BOX = (0.75, 0.82, 0.95, 0.91)
QUICK_SOLVE = '快速破解'
SOLVED_BOX = (0.6, 0.45, 0.85, 0.55)
SOLVED = '破解成功'
# 打开装置后任务栏才有「血清 0%」
SERUM = '血清'
# 标记显示 2 米时提示还没出来，要再往前挪一点
ARRIVE_METRES = 2
NUDGES = 12
# 标记偏得比这还多时只转不走，边走边转会从装置旁边走过去
TURN_ONLY = 0.3
# 走路读错距离时会提前停下，标记还显示这么远就迈大步
FAR_METRES = 4


class Exploration(Expulsion):
    names = ('探险',)
    uses_rounds = True

    def begin(self):
        task = self.task
        task.skill_tick.reset()
        task.sleep(2)
        if self.shows(PROGRESS_BOX, SERUM):
            # 装置已经操作过（比如接手一局打到一半的），直接打怪攒血清
            task.log_info("装置已经打开，接着攒血清")
            self.since = self.clock()
            self.progress, self.pending, self.read_at = None, None, 0
            return True
        walker = MarkerWalk(task, self.clock)
        seen = walker.wait_for_marker(timeout=10)
        if seen is None:
            task.log_info("没找到装置的标记，放弃这一局")
            task.exit_mission()
            return False
        walker.run(seen, arrive=ARRIVE_METRES)
        if not self.operate(walker):
            task.log_info("没能操作装置，放弃这一局")
            task.screenshot("explore_operate_failed")
            task.exit_mission()
            return False
        self.since = self.clock()
        self.progress, self.pending, self.read_at = None, None, 0
        return True

    def operate(self, walker):
        task = self.task
        for _ in range(NUDGES):
            if self.shows(PROMPT_BOX, PROMPT, unless=NOT_PROMPT):
                break
            # 走到时装置常在身侧，直接往前挪会顶着旁边的东西；先把标记转到正前方
            seen = walker.find(task.next_frame())
            if seen and abs(seen[0]) > STEER:
                walker.face(seen[0])
                task.sleep(0.2)
                if abs(seen[0]) > TURN_ONLY:
                    continue
            far = seen and seen[1] is not None and seen[1] > FAR_METRES
            task.send_key('w', down_time=0.8 if far else 0.25)
            task.sleep(0.3)
        else:
            return False
        task.log_info("操作装置")
        if not task.wait_until(lambda: self.shows(QUICK_SOLVE_BOX, QUICK_SOLVE), time_out=6,
                               post_action=lambda: self.press(task.get_interact_key()), raise_if_not_found=False):
            return False
        task.log_info("快速破解")
        return bool(task.wait_until(lambda: self.shows(SOLVED_BOX, SOLVED) or not self.shows(QUICK_SOLVE_BOX, QUICK_SOLVE),
                                    time_out=6, post_action=lambda: self.press('f'), raise_if_not_found=False))

    def press(self, key):
        # wait_until 每读一帧就调一次 post_action，按完要等界面反应
        self.task.send_key(key)
        self.task.sleep(1)

    def shows(self, region, text, unless=None):
        box = self.task.box_of_screen(*region, name='explore_' + text)
        return any(text in t.name and not (unless and unless in t.name)
                   for t in self.task.ocr(box=box, match=re.compile(re.escape(text))))
