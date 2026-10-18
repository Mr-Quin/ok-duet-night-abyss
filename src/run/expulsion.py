"""驱离：开局按「挂机模式」处理站位，之后一直放技能，敌人清完游戏自己结算。"""
import time


class Expulsion:
    name = '驱离'
    # 开始界面上的「驱离」偶尔被读成「驱逐」
    names = ('驱离', '驱逐')
    uses_rounds = False

    def __init__(self, task):
        self.task = task
        self.since = 0

    def begin(self):
        task = self.task
        task.skill_tick.reset()
        task._mission_started = False
        if not task.move_on_begin():
            return False
        self.since = time.time()
        return True

    def tick(self):
        task = self.task
        if time.time() - self.since >= task.config.get("超时时间", 120):
            task.log_info("驱离超时，放弃这一局")
            task.give_up_mission()
            return False
        task.skill_tick()
        return True

    def next_round(self):
        self.since = time.time()
