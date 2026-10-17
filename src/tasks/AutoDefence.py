from qfluentwidgets import FluentIcon
import time
from typing import Callable

from ok import Logger, TaskDisabledException
from src.tasks.DNAOneTimeTask import DNAOneTimeTask
from src.tasks.BaseCombatTask import BaseCombatTask
from src.tasks.CommissionsTask import CommissionsTask, Mission, QuickAssistTask, _default_movement

logger = Logger.get_logger(__name__)

# 开着游戏的自动轮次时，轮次弹窗倒计时约 10 秒后会自己继续；超过这么久还在，就按没开处理
HANDS_OFF_DIALOG_WAIT = 20


class AutoDefence(DNAOneTimeTask, CommissionsTask, BaseCombatTask):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.icon = FluentIcon.FLAG
        self.name = "自动扼守"
        self.description = "半自动"
        self.group_name = "半自动"
        self.group_icon = FluentIcon.VIEW

        self.setup_commission_config()
        self.setup_mission_start_config()
        self.setup_combat_detection_config()

        self.config_description.update({
            "超时时间": "波次超时后将发出提示",
        })

        self.quick_assist_task = QuickAssistTask(self)
        self.external_movement = _default_movement
        self.external_recover = None
        self.external_hands_off = False
        self.external_run_limit = None
        self.external_round_limit = None
        self.rounds_seen = 0
        self._external_config = None
        self._merged_config_cache = None
        self.skill_tick = self.create_skill_ticker()

    @property
    def config(self):
        if self.external_movement == _default_movement or not self._external_config:
            return getattr(self, '_base_config', None)

        if self._merged_config_cache is None:
            base = getattr(self, '_base_config', {})
            self._merged_config_cache = base.copy() if base else {}
            self._merged_config_cache.update(self._external_config)
        return self._merged_config_cache

    @config.setter
    def config(self, value):
        self._base_config = value
        self._merged_config_cache = None

    def config_external_movement(self, func: Callable, config: dict, recover: Callable = None,
                                 hands_off: bool = False, run_limit: int = None, round_limit: int = None):
        """由全自动任务注入走位和行为；后面几个参数不传时和原来一样。

        recover：局外闲置时调用，用来重新导航回关卡。
        hands_off：游戏自带的自动轮次在打，轮次弹窗和手册弹窗交给游戏处理。
        run_limit：打完这么多局后停在结算界面。
        round_limit：每局看到这么多个轮次弹窗就撤离，不读轮次数字。
        """
        if hands_off and round_limit:
            raise ValueError("hands_off 时轮次交给游戏，不能再用 round_limit")
        self.external_recover = recover
        self.external_hands_off = hands_off
        self.external_run_limit = run_limit
        self.external_round_limit = round_limit
        if callable(func):
            self.external_movement = func
        else:
            self.external_movement = _default_movement
        self._merged_config_cache = None
        self._external_config = config

    def run(self):
        DNAOneTimeTask.run(self)
        self.move_mouse_to_safe_position(save_current_pos=False)
        self.set_check_monthly_card()
        self.external_movement = _default_movement
        self.external_recover = None
        self.external_hands_off = False
        self.external_run_limit = None
        self.external_round_limit = None
        try:
            return self.do_run()
        except TaskDisabledException:
            pass
        except Exception as e:
            logger.error("AutoDefence error", e)
            raise

    def do_run(self):
        self.init_all()
        self.load_char()

        if self.external_movement is not _default_movement and self.in_team():
            self.open_in_mission_menu()

        idle_since = between_since = None
        runs_done, run_live = 0, False
        track_runs = bool(self.external_run_limit or self.external_hands_off or self.external_round_limit)
        stop_func = self.count_round_dialogs if self.external_round_limit else self.stop_func
        self.rounds_seen = 0
        if track_runs:
            self.mission_status = None
        while True:
            if track_runs and self.is_result_screen() and run_live:
                run_live = False
                if self.external_run_limit:
                    runs_done += 1
                    self.log_info(f"已完成 {runs_done}/{self.external_run_limit} 次")
                    if runs_done >= self.external_run_limit:
                        return
            stop = stop_func
            if self.in_team():
                between_since = None
                if track_runs and not run_live:
                    run_live = True
                    if self.mission_status == Mission.START:
                        # 游戏开了自动确认时，中间的手册/密函弹窗被跳过，不会返回 Mission.START
                        self.mission_status = None
                        self.begin_run()
                if self.move_on_begin():
                    self.handle_in_mission()
            elif run_live and self.external_hands_off and self.is_between_rounds():
                between_since = between_since or time.time()
                if time.time() - between_since < HANDS_OFF_DIALOG_WAIT:
                    # 游戏的自动轮次会自己继续，打完后自己结算；这时点「继续挑战」会让这一局一直打下去
                    self.sleep(0.5)
                    continue
                between_since = None
                if self.find_action_dialog_continue() or self.find_action_dialog_retreat():
                    self.log_info("轮次弹窗一直没自动继续，撤离")
                    stop = lambda: True
                else:
                    # 这是局内轮次之间的手册弹窗，要按那一套布局来选
                    self.mission_status = Mission.CONTINUE
            else:
                between_since = None

            _status = self.handle_mission_interface(stop_func=stop)
            if track_runs and (self.mission_status == Mission.START or _status == Mission.GIVE_UP):
                # 点了开始或再次进行、或者放弃了这一局：下一次进局内是新的一局
                run_live = False
            if _status is False and self.external_recover and (not self.in_team() or self.find_esc_menu()):
                # 局外没有能处理的界面（比如走位失败放弃后回到了委托列表），或者停在局内菜单里
                idle_since = idle_since or time.time()
                if time.time() - idle_since > 20:
                    self.external_recover()
                    idle_since = None
            else:
                idle_since = None
            if _status == Mission.START:
                self.begin_run()
                run_live = track_runs and self.in_team()
            elif _status == Mission.STOP:
                self.log_info("任务中止")
                self.quit_mission()
            elif _status == Mission.CONTINUE:
                self.log_info("任务继续")
                self.init_for_next_round()
                self.wait_until(self.in_team, time_out=self.action_timeout)

            self.sleep(0.1)

    def is_result_screen(self):
        """结算界面。轮次之间手册弹窗的「确认选择」和「再次进行」用的是同一个金色圆环，所以还要排除手册弹窗。"""
        return not self.in_team() and bool(self.find_result_again_btn()) and not self.find_manual_select_btn()

    def begin_run(self):
        self.wait_until(self.in_team, time_out=30)
        self.init_all()
        self.handle_mission_start()
        self.rounds_seen = 0

    def count_round_dialogs(self):
        self.rounds_seen += 1
        # 局内轮次之间的手册弹窗按 current_round 选
        self.current_round = self.rounds_seen
        self.info_set("当前轮次", self.rounds_seen)
        return self.rounds_seen >= self.external_round_limit

    def is_between_rounds(self):
        return bool(self.find_action_dialog_continue() or self.find_action_dialog_retreat()
                    or self.find_manual_select_btn())

    def init_all(self):
        self.init_for_next_round()
        self.skill_tick.reset()
        self.current_round = 0
        self._mission_started = False

    def init_for_next_round(self):
        self.init_runtime_state()

    def init_runtime_state(self):
        self.runtime_state = {"wave_start_time": 0, "wave": -1, "wait_next_wave": False}
        self.reset_wave_info()

    def handle_in_mission(self):
        """处理在副本中的逻辑"""
        self.get_wave_info()
        in_combat = self.current_wave != -1
        if in_combat:
            # 如果是新的波次，重置状态
            if self.current_wave != self.runtime_state["wave"]:
                self.runtime_state.update(
                    {"wave": self.current_wave, "wave_start_time": time.time(), "wait_next_wave": False})
                self.quick_assist_task.reset()

            # 检查波次是否超时
            if not self.runtime_state["wait_next_wave"] and self.combat_detection_enabled() and time.time() - self.runtime_state[
                "wave_start_time"] >= self.config.get("超时时间", 120):
                if self.external_movement is not _default_movement:
                    self.log_info("任务超时")
                    self.give_up_mission()
                    return
                else:
                    self.log_info_notify("任务超时")
                    self.soundBeep()
                    self.runtime_state["wait_next_wave"] = True

        else:
            if self.runtime_state["wave"] > 0:
                self.init_runtime_state()
            # 如果不在战斗波次中，执行移动任务
            self.quick_assist_task.run()

        # 战斗侦测关掉时不等波次，局内就按技能
        if not self.runtime_state["wait_next_wave"] and self.skills_ready(in_combat):
            self.skill_tick()

    def handle_mission_start(self):
        """处理任务开始的逻辑"""
        if self.external_movement is not _default_movement:
            self.log_info("任务开始，执行外部移动逻辑")
            self.external_movement(delay=2)
            # 复位失败时 walk_to_aim 会调用 give_up_mission() 退出副本后直接 return，
            # 此时已不在队伍中，应立即返回让主循环重新识别界面并重开任务
            if not self.in_team():
                self.log_info("外部移动后未在队伍中（可能复位失败已退出副本），等待重开任务")
                return
            time_out = self.action_timeout + 10
            self.log_info(f"外部移动执行完毕，等待战斗开始，{time_out}秒后超时")
            if not self.wait_until(lambda: self.current_wave != -1 or self.find_esc_menu(), post_action=self.get_wave_info,
                                   time_out=time_out):
                self.log_info("等待战斗开始超时，重开任务")
                self.open_in_mission_menu()
            else:
                self.log_info("战斗开始")
        else:
            self.sleep(2)
            self.log_info_notify("任务开始")
            self.soundBeep()

    def stop_func(self):
        self.get_round_info()
        n = self.config.get("轮次", 3)
        if self.current_round >= n:
            return True
