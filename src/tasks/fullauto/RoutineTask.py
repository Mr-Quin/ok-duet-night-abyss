"""流程：按顺序跑几个任务，每一步可以临时改那个任务的设置，不改它存下来的设置。"""
import json

from qfluentwidgets import FluentIcon

from ok import TaskDisabledException
from ok.core.events import communicate
from src.nav.okscript import OkScriptBackend
from src.routine.preflight import ANTI_CHEAT, Blocked, wait_for_game
from src.routine.runner import StepFailed, run_steps
from src.routine.steps import Step, StepError, dump_steps, parse_steps, spec_of
from src.tasks.BaseDNATask import BaseDNATask

DEFAULT_STEPS = json.dumps(dump_steps([Step('AutoDailyClaimTask')]), ensure_ascii=False, indent=1)


class RoutineTask(BaseDNATask):
    is_routine = True

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.icon = FluentIcon.CALENDAR
        self.name = "流程"
        self.description = "按顺序跑几个任务，每一步可以临时改设置；仅支持简体中文客户端"
        self.group_name = "全自动"
        self.group_icon = FluentIcon.CAFE
        self.support_schedule_task = True
        self.default_config.update({
            "步骤": DEFAULT_STEPS,
            "失败后继续": False,
        })
        self.config_description.update({
            "步骤": "增删、排序步骤，改每一步的设置",
            "失败后继续": "一步失败后接着跑下一步；关掉时一步失败就停",
        })
        self.config_type["步骤"] = {"type": "button", "text": "编辑步骤", "icon": FluentIcon.EDIT,
                                   "callback": self.edit_steps}
        self.add_exit_after_config()

    def edit_steps(self):
        from ok import og
        from src.routine.editor_dialog import RoutineEditor
        RoutineEditor(self, og.main_window).exec()

    def steps(self):
        tasks = {type(t).__name__: t for t in self.executor.onetime_tasks}
        try:
            raw = json.loads(self.config.get("步骤") or "{}")
        except json.JSONDecodeError as e:
            raise Exception(f"步骤不是合法的 JSON：{e}")
        try:
            return parse_steps(raw, {name: spec_of(t) for name, t in tasks.items()}), tasks
        except StepError as e:
            raise Exception(f"步骤有误：{e}")

    def run(self):
        steps, tasks = self.steps()
        if hasattr(self.executor.interaction, 'activate'):
            self.executor.interaction.activate()
        try:
            wait_for_game(OkScriptBackend(self), self.log_info)
        except Blocked as e:
            self.log_info(f"启动时停下：{e}。画面上的文字：{' '.join(e.texts)}", notify=True)
            # 反作弊报错留着给人看，关掉游戏等下次定时任务再开就等于重试了
            if e.reason != ANTI_CHEAT:
                self.close_if_exit()
            raise Exception(f"启动时停下：{e}")
        try:
            results = run_steps(self, steps, tasks, keep_going=self.config.get("失败后继续", False))
        except StepFailed as e:
            self.log_info("流程没跑完：" + "；".join(r.line() for r in e.results), notify=True)
            self.close_if_exit()
            raise Exception(str(e))
        except TaskDisabledException:
            self.log_info("流程已停止")
            raise
        self.log_info(f"流程跑完了：{len(results)} 步", notify=True)

    def close_if_exit(self):
        if self.exit_after_task or self.config.get('Exit After Task'):
            self.log_info("失败后也按设置关掉游戏和 ok-dna")
            self.executor.device_manager.stop_hwnd()
            communicate.quit.emit()
