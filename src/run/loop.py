"""按「任务」跑完若干局：导航进关卡，按关卡类型选打法，每一拍认出阶段交给对应的处理。

阶段每一拍都重新从画面认，不靠记忆；记下来的只有画面上看不出的东西：打了几局、这一局看到
几个轮次弹窗、这一局是不是已经开始了。所以中途接手、手动点过、漏看了一次切换都不要紧。
"""
import time
from dataclasses import dataclass

from ok import TaskDisabledException
from src.nav import NavError, NoSuchEntry, World
from src.run import observe as O
from src.run.defence import Defence
from src.run.expulsion import Expulsion
from src.tasks.CommissionsTask import Mission

BEHAVIOURS = (Defence, Expulsion)
# 认不出的画面（加载、菜单、别的弹窗）停留这么久就交给导航重新进关卡
STALL_SECONDS = 20
# 开着游戏的自动轮次时，轮次弹窗倒计时约 10 秒后会自己继续；超过这么久还在，就按没开处理
HANDS_OFF_DIALOG_WAIT = 20
ESC_MENU_WAIT = 3
MAX_FAILURES = 3
RETRY_SECONDS = 10
RUN_HUD_WAIT = 8
# 驱逐的怪偶尔卡在地图里，同一个关卡连着放弃这么多次就停下，不再重开
MAX_GIVE_UPS = 3
LEAVE_WAIT = 60


class GaveUpTooOften(Exception):
    pass


class UnsupportedMission(Exception):
    def __init__(self, mode):
        super().__init__(mode)
        self.mode = mode


@dataclass(frozen=True)
class Job:
    target: object
    rounds: int = 1
    runs: int = 0


class RunLoop:
    def __init__(self, task, nav, job, observer=None, clock=time.time, behaviours=BEHAVIOURS):
        self.task, self.nav, self.job = task, nav, job
        self.behaviours = behaviours
        self.observer = observer or O.Observer(task)
        self.clock = clock
        self.behaviour = None
        self.mode = ''
        self.hands_off = False
        self.runs_done = 0
        self.give_ups = 0
        self.live = False
        self.rounds_seen = 0
        self.counted_dialog = None
        self.acted_on, self.acted_at = None, 0
        self.failures = 0

    def enter(self):
        """导航到关卡的开始界面，读出关卡类型，扼守再设好游戏的自动轮次。"""
        self.nav.go(self.job.target)
        info = self.nav.where().info
        self.mode = info.get('mode') or ''
        kind = next((b for b in self.behaviours if any(n in self.mode for n in b.names)), None)
        if kind is None:
            raise UnsupportedMission(self.mode)
        if not isinstance(self.behaviour, kind):
            self.behaviour = kind(self.task)
        self.hands_off = kind.uses_rounds and self.job.rounds > 1
        if kind.uses_rounds:
            # 游戏的自动轮次 N 表示打完第一轮后再自动打 N 轮，0 就是关掉
            self.nav.set_auto_rounds(self.job.rounds - 1)
        elif info.get('auto_on'):
            # 不按轮次打的关卡开着自动轮次时，游戏会自己一局接一局，和这里数局数、点再次进行抢
            self.nav.set_auto_rounds(0)
        self.live = False

    def run(self):
        self.enter_with_retries()
        last = None
        while True:
            now = self.clock()
            state = self.observer.next(now)
            if state != last:
                self.task.log_info(f"阶段：{state}")
                last = state
            if state is not None:
                try:
                    if getattr(self, 'on_' + state)(now):
                        break
                    self.failures = 0
                except (TaskDisabledException, GaveUpTooOften):
                    raise
                except Exception as e:
                    self.failures += 1
                    if self.failures >= MAX_FAILURES:
                        raise
                    self.task.log_info(f"{state} 处理出错（{e}），重新导航到关卡")
                    self.enter()
            self.task.sleep(0.1)
        self.nav.go(World())

    def enter_with_retries(self):
        for attempt in range(MAX_FAILURES):
            try:
                return self.enter()
            except NoSuchEntry:
                raise
            except NavError as e:
                if attempt == MAX_FAILURES - 1:
                    raise
                self.task.log_info(f"导航出错（{e}），回大世界重来")
                self.nav.go(World())

    def done(self):
        return bool(self.job.runs) and self.runs_done >= self.job.runs

    def on_in_run(self, now):
        if not self.live:
            # in_run 只认得出 HUD，大世界里也有；开局前用导航确认真的在局内，HUD 刚进局时还没画出来，等几秒
            if not self.task.wait_until(lambda: self.nav.where().in_run, time_out=RUN_HUD_WAIT, raise_if_not_found=False):
                self.task.log_info("看着像局内但不是，重新导航到关卡")
                self.enter()
                return
            self.live = True
            self.rounds_seen = 0
            self.task.log_info(f"第 {self.runs_done + 1} 局开始（{self.mode}）")
            if not self.behaviour.begin():
                self.gave_up()
        elif not self.behaviour.tick():
            self.gave_up()

    def gave_up(self):
        self.live = False
        self.give_ups += 1
        if self.give_ups >= MAX_GIVE_UPS:
            raise GaveUpTooOften(f"连续放弃了 {self.give_ups} 局")
        # 放弃后回到手册或大世界，不会回开始界面，等加载完就重新进关卡
        def left():
            state = self.nav.where()
            return state.screen != 'unknown' and not state.in_run
        self.task.wait_until(left, time_out=LEAVE_WAIT, raise_if_not_found=False)
        self.enter()

    def on_round_dialog(self, now):
        if self.counted_dialog != self.observer.since:
            self.counted_dialog = self.observer.since
            self.rounds_seen += 1
            # 局内轮次之间的手册弹窗按 current_round 选
            self.task.current_round = self.rounds_seen
            self.task.info_set("当前轮次", self.rounds_seen)
        if not self.due(now):
            return
        if self.hands_off:
            if now - self.observer.since < HANDS_OFF_DIALOG_WAIT:
                return
            self.task.log_info("轮次弹窗一直没自动继续，撤离")
            self.task.quit_mission()
        elif self.rounds_seen >= self.job.rounds:
            self.task.log_info(f"打完 {self.rounds_seen} 轮，撤离")
            self.task.quit_mission()
        else:
            self.task.continue_mission()
            self.behaviour.next_round()
        self.acted(now)

    def on_manual(self, now):
        # 局内轮次之间和开局前的手册弹窗布局不同，choose_drop_rate 按 mission_status 分
        self.task.mission_status = Mission.CONTINUE if self.live else None
        self.task.choose_drop_rate()

    def on_letter(self, now):
        self.task.mission_status = Mission.CONTINUE if self.live else None
        self.task.choose_letter()

    def on_letter_reward(self, now):
        self.task.choose_letter_reward()

    def on_result(self, now):
        if self.live:
            self.live = False
            self.runs_done += 1
            self.give_ups = 0
            self.task.log_info(f"已完成 {self.runs_done}/{self.job.runs or '不限'} 次")
        if self.done():
            return True
        self.start(now)

    def on_start(self, now):
        if self.done():
            return True
        self.start(now)

    def start(self, now):
        if self.due(now):
            self.task.start_mission()
            self.acted(now)

    def due(self, now):
        """同一次出现只处理一次，过了 RETRY_SECONDS 画面还没变才再处理一次。"""
        return self.acted_on != self.observer.since or now - self.acted_at >= RETRY_SECONDS

    def acted(self, now):
        self.acted_on, self.acted_at = self.observer.since, now

    def on_esc_menu(self, now):
        if now - self.observer.since >= ESC_MENU_WAIT:
            self.task.send_key('esc')

    def on_other(self, now):
        if now - self.observer.since >= STALL_SECONDS:
            self.task.log_info(f"停在认不出的画面 {STALL_SECONDS} 秒，重新导航到关卡")
            self.enter()
            self.observer.since = self.clock()
