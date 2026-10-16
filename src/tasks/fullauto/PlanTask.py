import os
import time

from qfluentwidgets import FluentIcon

from ok import TaskDisabledException
from src.nav.okscript import OkScriptBackend
from src.nav.plan import Gameplay, PlanRunner, parse_plan
from src.tasks.AutoDefence import AutoDefence
from src.tasks.CommissionsTask import Mission
from src.tasks.DNAOneTimeTask import DNAOneTimeTask
from src.tasks.fullauto.Auto65ArtifactTask_Fast import Auto65ArtifactTask_Fast


class DefenceStart(Gameplay):
    """Start a 30/65 defence run with the recorded walk, and stop once the first wave is up."""

    def __init__(self, task):
        self.task = task

    def start_run(self):
        task = self.task
        defence = task.get_task_by_class(AutoDefence)
        defence.config_external_movement(task.walk_to_aim, task.config)
        defence.init_all()
        defence.load_char()
        deadline = time.time() + 60
        while time.time() < deadline:
            # presses start, then picks the commission manual; START comes back once the run loads
            if defence.handle_mission_interface() == Mission.START:
                break
            task.sleep(0.2)
        else:
            return False
        defence.wait_until(defence.in_team, time_out=30)
        defence.init_all()
        defence.handle_mission_start()
        if defence.current_wave == -1:
            if defence.find_esc_menu():
                defence.give_up_mission()
            defence.wait_until(lambda: not defence.in_team(), time_out=30, settle_time=1)
            return False
        # a few passes of the in-run loop cast the opening skills from the skill config
        end = time.time() + 3
        while time.time() < end:
            defence.handle_in_mission()
            task.sleep(0.1)
        return True


class PlanTask(Auto65ArtifactTask_Fast):
    """Farm a list of 夜航手册 30/65 defence entries, each for a set number of rounds."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = "夜航手册计划"
        self.description = "从任意界面出发，按计划依次刷夜航手册扼守"
        self.default_config.update({"计划": "30,0,3; 65,2,3"})
        self.config_description.update({
            "计划": "每项: 夜航手册等级, 第几行(从0开始)或名字, 轮次(0 只导航不开打); 用分号分隔",
        })

    def run(self):
        DNAOneTimeTask.run(self)
        self.move_mouse_to_safe_position(save_current_pos=False)
        self.set_check_monthly_card()
        plan = parse_plan(self.config.get("计划", ""))
        runner = PlanRunner(OkScriptBackend(self), DefenceStart(self), log=self.log_info, nav_log=lambda msg: self.log_info('    nav: ' + msg),
                            rows_path=os.path.join('configs', 'nav_rows.json'),
                            dump_dir=os.path.join('screenshots', 'nav'))
        try:
            results = runner.run(plan)
        except TaskDisabledException:
            return
        failed = [r for r in results if r[2] != 'ok']
        if failed:
            raise Exception('plan stopped at Lv.%d row %s: %s' % failed[0][:3])
