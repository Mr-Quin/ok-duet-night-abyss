from qfluentwidgets import FluentIcon
import time
from typing import Callable

from ok import Logger, TaskDisabledException
from src.tasks.DNAOneTimeTask import DNAOneTimeTask
from src.tasks.BaseCombatTask import BaseCombatTask
from src.tasks.CommissionsTask import CommissionsTask, Mission, QuickAssistTask, _default_movement

logger = Logger.get_logger(__name__)


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
        self.external_stop = None
        self.external_run_limit = None
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
                                 stop: Callable = None, run_limit: int = None):
        """recover: called when idle on a menu; stop: replaces the 轮次 check at round dialogs;
        run_limit: stop on the result screen after this many finished runs."""
        self.external_recover = recover
        self.external_stop = stop
        self.external_run_limit = run_limit
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
        self.external_stop = None
        self.external_run_limit = None
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

        idle_since = None
        runs_done, was_at_result = 0, False
        while True:
            if self.external_run_limit:
                # each finished run ends on the result screen; stop on the last one instead of pressing 再次进行
                at_result = not self.in_team() and bool(self.find_result_again_btn())
                if at_result and not was_at_result:
                    runs_done += 1
                    self.log_info(f"已完成 {runs_done}/{self.external_run_limit} 次")
                    if runs_done >= self.external_run_limit:
                        return
                was_at_result = at_result
            if self.in_team():
                if self.move_on_begin():
                    self.handle_in_mission()

            _status = self.handle_mission_interface(stop_func=self.stop_func)
            # nothing to act on outside a run, e.g. back on the commission list after a failed walk
            if _status is False and self.external_recover and not self.in_team():
                idle_since = idle_since or time.time()
                if time.time() - idle_since > 20:
                    self.external_recover()
                    idle_since = None
            else:
                idle_since = None
            if _status == Mission.START:
                self.wait_until(self.in_team, time_out=30)
                self.init_all()
                self.handle_mission_start()
            elif _status == Mission.STOP:
                self.log_info("任务中止")
                self.quit_mission()
            elif _status == Mission.CONTINUE:
                self.log_info("任务继续")
                self.init_for_next_round()
                self.wait_until(self.in_team, time_out=self.action_timeout)

            self.sleep(0.1)

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
        if self.external_stop:
            return self.external_stop()
        self.get_round_info()
        n = self.config.get("轮次", 3)
        if self.current_round >= n:
            return True
