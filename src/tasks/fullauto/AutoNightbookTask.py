"""自动夜航手册。

从任意界面导航到夜航手册里选定的一行（或委托页的扼守），在开始界面读出关卡类型，扼守就走到
防守点再打，驱离就开局放技能，打完设定的局数后回到大世界。

界面导航读的是简体中文界面上的文字，所以这个任务只支持简体中文客户端。
"""
from qfluentwidgets import FluentIcon

from ok import TaskDisabledException
from src.nav import Letter, Mission, Nav, NavError, Nightbook, NoSuchEntry, NotOffered
from src.nav import screens as S
from src.nav import text_zh as T
from src.nav.okscript import CACHE_PATH, OkScriptBackend
from src.run.loop import GaveUpTooOften, Job, RunLoop, UnsupportedMission
from src.tasks.BaseCombatTask import BaseCombatTask
from src.tasks.CommissionsTask import CommissionsTask
from src.tasks.DNAOneTimeTask import DNAOneTimeTask

SOURCES = ["夜航手册", "委托 扼守", "委托密函"]
BOOK_LEVELS = S.LEVELS
COMMISSION_LEVELS = [40, 50, 60, 70, 80]
MODE = '扼守/无尽'


class AutoNightbookTask(DNAOneTimeTask, CommissionsTask, BaseCombatTask):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.icon = FluentIcon.FLAG
        self.name = "自动夜航手册"
        self.description = "从任意界面导航到夜航手册、委托或委托密函的关卡，支持扼守、驱离、驱逐、避险和探险；仅支持简体中文客户端"
        self.group_name = "全自动"
        self.group_icon = FluentIcon.CAFE

        self.setup_commission_config()
        self.setup_mission_start_config()
        self.setup_combat_detection_config()
        for unused in ("轮次", "随机游走"):
            self.default_config.pop(unused, None)
            self.config_description.pop(unused, None)
        self.default_config.update({
            "来源": SOURCES[0],
            "等级": f"Lv.{BOOK_LEVELS[1]}",
            "第几个": 1,
            "密函": T.LETTER_COLUMNS[0],
            "每局轮次": 3,
            "刷几次": 0,
        })
        self.config_description.update({
            "来源": "夜航手册的一行、委托页的「扼守/无尽」，或委托密函一栏里的无尽委托",
            "等级": "委托 扼守 只有 Lv.40 到 Lv.80",
            "第几个": "夜航手册这个等级里从上往下第几行",
            "密函": "委托密函的哪一栏；进这一栏里的无尽委托（扼守/无尽、探险/无尽），密函每小时轮换",
            "每局轮次": "扼守每局打几轮后结算。大于 1 时交给游戏自带的自动轮次；为 1 时关掉自动轮次，打完第一轮就撤离",
            "刷几次": "一共进本几次，打完回到大世界；0 为不限",
            "超时时间": "扼守一个波次、驱离一整局超过这么多秒就放弃重开",
            "挂机模式": "驱离开局时怎么处理站位",
        })
        self.config_type["来源"] = {"type": "drop_down", "options": SOURCES}
        self.config_type["密函"] = {"type": "drop_down", "options": list(T.LETTER_COLUMNS)}
        self.config_type["等级"] = {"type": "drop_down", "options": [f"Lv.{lv}" for lv in BOOK_LEVELS]}
        self._nav = None

    @property
    def nav(self):
        if self._nav is None:
            self._nav = Nav(OkScriptBackend(self), log=self.log_info, cache_path=CACHE_PATH)
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
            RunLoop(self, self.nav, job).run()
        except TaskDisabledException:
            pass
        except NoSuchEntry as e:
            raise Exception(f"夜航手册 Lv.{e.level} 现在只有 {len(e.names)} 行，选的是第 {job.target.row + 1} 行")
        except NotOffered as e:
            raise Exception(f"委托密函 {e.column} 栏现在没有无尽委托（有 {e.offered}），密函每小时轮换，过会儿再试")
        except UnsupportedMission as e:
            raise Exception(f"{self.describe(job.target)}是「{e.mode}」，现在只支持扼守、驱离、驱逐、避险和探险")
        except GaveUpTooOften as e:
            raise Exception(f"{self.describe(job.target)}{e}，先停下")
        except NavError as e:
            raise Exception(f"自动导航失败：{e}")

    def job(self):
        level = int(str(self.config.get("等级", BOOK_LEVELS[1])).replace("Lv.", ""))
        rounds = min(100, max(1, int(self.config.get("每局轮次", 3) or 1)))
        runs = int(self.config.get("刷几次", 0) or 0)
        if self.config.get("来源") == SOURCES[1]:
            target = Mission(MODE, lv=level)
        elif self.config.get("来源") == SOURCES[2]:
            target = Letter(T.ENDLESS, column=self.config.get("密函", T.LETTER_COLUMNS[0]))
        else:
            target = Nightbook(level, max(1, int(self.config.get("第几个", 1) or 1)) - 1)
        return Job(target, rounds=rounds, runs=runs)

    @staticmethod
    def describe(target):
        if isinstance(target, Nightbook):
            return f"夜航手册 Lv.{target.level} 第 {target.row + 1} 行"
        if isinstance(target, Letter):
            return f"委托密函 {target.column} 栏的无尽委托"
        return f"委托 {target.mode} Lv.{target.lv}"
