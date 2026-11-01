"""流程：按顺序跑几个任务，每一步可以临时改那个任务的设置，不改它存下来的设置。"""
import json

from qfluentwidgets import FluentIcon

from ok import TaskDisabledException
from ok.core.events import communicate
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
            "步骤": 'JSON：{"version": 1, "steps": [{"task": 任务类名, "overrides": {设置: 值}}]}。'
                    '现在能放的任务：AutoDailyClaimTask（日常领奖）、AutoNightbookTask（自动夜航手册）',
            "失败后继续": "一步失败后接着跑下一步；关掉时一步失败就停",
        })
        self.config_type["步骤"] = {"type": "text_edit"}
        self.add_exit_after_config()

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
        try:
            results = run_steps(self, steps, tasks, keep_going=self.config.get("失败后继续", False))
        except StepFailed as e:
            self.log_info("流程没跑完：" + "；".join(r.line() for r in e.results), notify=True)
            if self.exit_after_task or self.config.get('Exit After Task'):
                self.log_info("失败后也按设置关掉游戏和 ok-dna")
                self.executor.device_manager.stop_hwnd()
                communicate.quit.emit()
            raise Exception(str(e))
        except TaskDisabledException:
            self.log_info("流程已停止")
            raise
        self.log_info(f"流程跑完了：{len(results)} 步", notify=True)
