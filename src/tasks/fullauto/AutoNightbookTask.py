"""自动夜航手册。

从任意界面导航到夜航手册里选定的一行（或委托页的扼守），在开始界面读出关卡类型，扼守就走到
防守点再打，驱离就开局放技能，打完设定的局数后回到大世界。

界面导航读的是简体中文界面上的文字，所以这个任务只支持简体中文客户端。
"""
from qfluentwidgets import FluentIcon

from ok import Logger, TaskDisabledException
from src.nav import Mission, Nav, NavError, Nightbook, NoSuchEntry
from src.nav.okscript import CACHE_PATH, OkScriptBackend
from harness import dataset
from harness.ml import shadow
from src.run.loop import Job, RunLoop, UnsupportedMission
from src.run.observe import Observer
from src.tasks.BaseCombatTask import BaseCombatTask
from src.tasks.CommissionsTask import CommissionsTask
from src.tasks.DNAOneTimeTask import DNAOneTimeTask

logger = Logger.get_logger(__name__)

SOURCES = ["夜航手册", "委托 扼守"]
BOOK_LEVELS = [20, 30, 40, 50, 55, 60, 65, 70, 75, 80]
COMMISSION_LEVELS = [40, 50, 60, 70, 80]
MODE = '扼守/无尽'


class AutoNightbookTask(DNAOneTimeTask, CommissionsTask, BaseCombatTask):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.icon = FluentIcon.FLAG
        self.name = "自动夜航手册"
        self.description = "从任意界面导航到夜航手册的关卡，支持扼守和驱离；仅支持简体中文客户端"
        self.group_name = "全自动"
        self.group_icon = FluentIcon.CAFE

        self.setup_commission_config()
        self.setup_mission_start_config()
        self.setup_combat_detection_config()
        self.default_config.pop("轮次", None)
        self.default_config.update({
            "来源": SOURCES[0],
            "等级": f"Lv.{BOOK_LEVELS[1]}",
            "第几个": 1,
            "每局轮次": 3,
            "刷几次": 0,
        })
        self.config_description.update({
            "来源": "夜航手册的一行，或委托页的「扼守/无尽」",
            "等级": "委托 扼守 只有 Lv.40 到 Lv.80",
            "第几个": "夜航手册这个等级里从上往下第几行",
            "每局轮次": "扼守每局打几轮后结算。大于 1 时交给游戏自带的自动轮次；为 1 时关掉自动轮次，打完第一轮就撤离",
            "刷几次": "一共进本几次，打完回到大世界；0 为不限",
            "超时时间": "扼守一个波次、驱离一整局超过这么多秒就放弃重开",
            "挂机模式": "驱离开局时怎么处理站位",
        })
        self.config_type["来源"] = {"type": "drop_down", "options": SOURCES}
        self.config_type["等级"] = {"type": "drop_down", "options": [f"Lv.{lv}" for lv in BOOK_LEVELS]}
        self._nav = None

    @property
    def nav(self):
        if self._nav is None:
            self._nav = Nav(OkScriptBackend(self), log=self.log_debug, cache_path=CACHE_PATH)
        return self._nav

    def run(self):
        DNAOneTimeTask.run(self)
        self.move_mouse_to_safe_position(save_current_pos=False)
        self.set_check_monthly_card()
        self.skill_tick = self.create_skill_ticker()
        self.load_char()
        job = self.job()
        self.log_info(f"导航到{self.describe(job.target)}")
        try:
            observer = Observer(self)
            dataset.install(observer)
            shadow.install(observer)
            RunLoop(self, self.nav, job, observer=observer).run()
        except TaskDisabledException:
            pass
        except NoSuchEntry as e:
            raise Exception(f"夜航手册 Lv.{e.level} 现在只有 {len(e.names)} 行，选的是第 {job.target.row + 1} 行")
        except UnsupportedMission as e:
            raise Exception(f"{self.describe(job.target)}是「{e.mode}」，现在只支持扼守和驱离")
        except NavError as e:
            raise Exception(f"自动导航失败：{e}")

    def job(self):
        level = int(str(self.config.get("等级", BOOK_LEVELS[1])).replace("Lv.", ""))
        rounds = min(100, max(1, int(self.config.get("每局轮次", 3) or 1)))
        runs = int(self.config.get("刷几次", 0) or 0)
        if self.config.get("来源") == SOURCES[1]:
            target = Mission(MODE, lv=level)
        else:
            target = Nightbook(level, max(1, int(self.config.get("第几个", 1) or 1)) - 1)
        return Job(target, rounds=rounds, runs=runs)

    @staticmethod
    def describe(target):
        if isinstance(target, Nightbook):
            return f"夜航手册 Lv.{target.level} 第 {target.row + 1} 行"
        return f"委托 {target.mode} Lv.{target.lv}"
