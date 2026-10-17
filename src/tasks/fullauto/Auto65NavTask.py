"""自动30/65级魔之楔本（导航版）。

从任意界面（大世界、菜单、别的关卡，甚至局内）导航到夜航手册里选定的扼守关卡，设好游戏自带的
自动轮次，按目标标记走到防守点，打完设定的局数后回到大世界。

界面导航读的是简体中文界面上的文字，所以这个任务只支持简体中文客户端；原来的
「自动30/65级魔之楔本」不受影响。
"""
from ok import Logger, TaskDisabledException
from src.nav import Nav, NavError, Nightbook, NoSuchEntry, World, WrongMission
from src.nav.okscript import CACHE_PATH, OkScriptBackend
from src.tasks.AutoDefence import AutoDefence
from src.tasks.DNAOneTimeTask import DNAOneTimeTask
from src.tasks.fullauto.Auto65ArtifactTask_Fast import Auto65ArtifactTask_Fast
from src.tasks.fullauto.marker_walk import MarkerWalk

logger = Logger.get_logger(__name__)

# 夜航手册里进 30/65 扼守的关卡，从上往下
NIGHTBOOK_ENTRIES = {
    30: ['残火暴徒秽兽', '霹雳疾冲秽兽', '枯萎游击秽兽', '凛霜疾冲秽兽'],
    65: ['霜狱野蜂暗箭', '浴血野蜂利刃', '浴血野蜂密探', '掠影野蜂暗箭', '守护野蜂暗箭', '守护野蜂利刃', '转雷野蜂密探',
         '浴血野蜂暗箭', '掠影野蜂利刃', '霜狱野蜂密探'],
}
TARGETS = {f"Lv.{lv} 第{i + 1}个 {name}": (lv, i)
           for lv, names in NIGHTBOOK_ENTRIES.items() for i, name in enumerate(names)}
WALK_MODES = ["按标记直线走", "原录制路线"]


class Auto65NavTask(Auto65ArtifactTask_Fast):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = "自动30/65级魔之楔本（导航版）"
        self.description = "从任意界面导航到夜航手册的关卡；仅支持简体中文客户端"
        self.default_config.update({
            "关卡": next(iter(TARGETS)),
            "每局轮次": 3,
            "刷几次": 0,
            "走位方式": WALK_MODES[0],
        })
        self.config_description.update({
            "关卡": "夜航手册里的扼守关卡，从当前界面自动导航过去",
            "每局轮次": "每局打几轮后结算。大于 1 时交给游戏自带的自动轮次；为 1 时关掉自动轮次，打完第一轮就撤离",
            "刷几次": "一共进本几次，打完回到大世界；1 为不按再次进行，0 为不限",
            "走位方式": "按标记直线走：朝目标标记直走到附近；原录制路线：按录制的按键走完再复位",
        })
        self.config_type["关卡"] = {"type": "drop_down", "options": list(TARGETS)}
        self.config_type["走位方式"] = {"type": "drop_down", "options": WALK_MODES}
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
        defence = self.get_task_by_class(AutoDefence)
        original_info_set = defence.info_set
        try:
            # 即使已经在一局里也先导航：可能是别的关卡，或者自动轮次和设置不一样；导航会在不损失奖励时离开
            self.navigate_to_mission()
            rounds = self.rounds_per_run()
            runs = int(self.config.get("刷几次", 0) or 0)
            defence.config_external_movement(self.walk, self.config, recover=self.return_to_mission,
                                             hands_off=rounds > 1, run_limit=runs or None,
                                             round_limit=None if rounds > 1 else 1)
            defence.info_set = self.info_set
            result = defence.do_run()
            if runs:
                self.nav.go(World())
            return result
        except TaskDisabledException:
            pass
        finally:
            defence.info_set = original_info_set

    def rounds_per_run(self):
        # 游戏的自动轮次最多 99，也就是一局最多 100 轮
        return min(100, max(1, int(self.config.get("每局轮次", 3) or 1)))

    def mission_target(self):
        level, row = TARGETS.get(self.config.get("关卡"), next(iter(TARGETS.values())))
        # 游戏的自动轮次 N 表示打完第一轮后再自动打 N 轮
        return Nightbook(level, row, mode='扼守/无尽', lv=level, auto_rounds=self.rounds_per_run() - 1)

    def navigate_to_mission(self):
        target = self.mission_target()
        self.log_info(f"导航到夜航手册 Lv.{target.level} 第 {target.row + 1} 个关卡")
        try:
            self.nav.go(target)
        except NoSuchEntry as e:
            raise Exception(f"夜航手册 Lv.{e.level} 现在只有 {len(e.names)} 个关卡，选的是第 {target.row + 1} 个，请重新选择关卡")
        except WrongMission as e:
            raise Exception(f"夜航手册 Lv.{target.level} 第 {target.row + 1} 个关卡是 {e.found}，不是扼守，请重新选择关卡")
        except NavError as e:
            raise Exception(f"自动导航失败：{e}")

    def return_to_mission(self):
        state = self.nav.where()
        if not state.in_run and state.screen != 'start':
            self.log_info(f"停在 {state.screen}，重新导航到关卡")
            self.navigate_to_mission()

    def walk(self, delay=0):
        if self.config.get("走位方式", WALK_MODES[0]) != WALK_MODES[0]:
            return self.walk_to_aim(delay)
        self.sleep(delay)
        walker = MarkerWalk(self)
        seen = walker.wait_for_marker()
        if seen is None:
            logger.info("没找到目标标记，改用录制路线")
            return self.walk_to_aim(0)
        if walker.run(seen):
            return
        # 已经走了一段，离目标点旁的复位点最近
        if not self.reset_and_transport():
            logger.info("复位失败，重开任务...")
            self.give_up_mission()
