"""驱离、驱逐和避险：开局按「挂机模式」处理站位，之后一直放技能，游戏自己结算。

避险要攒满血清，血清是在附近打怪攒的，所以和驱离一样站着打就行。驱逐的敌人有时会卡在地图里
出不来，这是游戏的问题；进度一直不动就放弃这一局重开。
"""
import re
import time

# 任务栏里进度那一行（「已驱逐敌人：24/40」「血清 0%」）
PROGRESS_BOX = (0.0, 0.32, 0.2, 0.38)
PROGRESS_EVERY = 5


class Expulsion:
    name = '驱离'
    names = ('驱离', '驱逐', '避险')
    uses_rounds = False

    def __init__(self, task, clock=time.time):
        self.task = task
        self.clock = clock
        self.since = 0
        self.progress, self.pending, self.read_at = None, None, 0

    def begin(self):
        task = self.task
        task.skill_tick.reset()
        # 刚进局内的一两秒里按 ESC 不出菜单，「开局重置角色位置」会因为找不到菜单报错
        task.sleep(2)
        if not task.apply_afk_mode():
            return False
        self.since = self.clock()
        self.progress, self.pending, self.read_at = None, None, 0
        return True

    def tick(self):
        """超时按进度算：进度在变就一直打，「超时时间」秒都没变才放弃。"""
        task = self.task
        if self.clock() - self.read_at >= PROGRESS_EVERY:
            self.read_at = self.clock()
            reading = self.read_progress()
            # 数字本身读不准（「4/40」会读成 4140），只看它变没变；新的读数连着两次一样才算进度，偶尔读错一次不算
            if reading is not None and reading != self.progress:
                if reading == self.pending:
                    self.progress, self.since, self.pending = reading, self.clock(), None
                else:
                    self.pending = reading
            elif reading == self.progress:
                self.pending = None
        if self.clock() - self.since >= task.config.get("超时时间", 120):
            task.log_info(f"进度停在 {self.progress} 不动，放弃这一局")
            task.exit_mission()
            return False
        task.skill_tick()
        return True

    def read_progress(self):
        task = self.task
        box = task.box_of_screen(*PROGRESS_BOX, name='expulsion_progress')
        texts = task.ocr(box=box, match=re.compile(r'\d'))
        return ''.join(re.findall(r'\d', ''.join(t.name for t in texts))) or None
