from qfluentwidgets import FluentIcon
import time
import win32con

from ok import Logger, TaskDisabledException
from src.tasks.DNAOneTimeTask import DNAOneTimeTask
from src.tasks.CommissionsTask import CommissionsTask, Mission
from src.tasks.BaseCombatTask import BaseCombatTask

from src.tasks.AutoDefence import AutoDefence
from src.nav import text_zh as T
from src.nav.nav import Nav, NavError
from src.nav.navigator import NoSuchEntry, WrongMission
from src.nav.okscript import OkScriptBackend, ROWS_PATH
from src.nav.targets import Nightbook

logger = Logger.get_logger(__name__)

# 夜航手册 entries leading to the 30/65 defence, top to bottom
NIGHTBOOK_ENTRIES = {
    30: ['残火暴徒秽兽', '霹雳疾冲秽兽', '枯萎游击秽兽', '凛霜疾冲秽兽'],
    65: ['霜狱野蜂暗箭', '浴血野蜂利刃', '浴血野蜂密探', '掠影野蜂暗箭', '守护野蜂暗箭', '守护野蜂利刃', '转雷野蜂密探',
         '浴血野蜂暗箭', '掠影野蜂利刃', '霜狱野蜂密探'],
}
NAV_OFF = "关闭"
NAV_TARGETS = {f"Lv.{lv} 第{i + 1}个 {name}": (lv, i)
               for lv, names in NIGHTBOOK_ENTRIES.items() for i, name in enumerate(names)}


class Auto65ArtifactTask_Fast(DNAOneTimeTask, CommissionsTask, BaseCombatTask):
    """
    移动更快的自动30/65级mod，路径参考EMT
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.icon = FluentIcon.FLAG
        self.name = "自动30/65级魔之楔本"
        self.description = "全自动"
        self.group_name = "全自动"
        self.group_icon = FluentIcon.CAFE

        self.setup_commission_config()
        self.default_config.update({
            "游戏内自动轮次": 0,
            "自动导航": NAV_OFF,
        })
        self.config_description.update({
            "轮次": "每次进本打几个轮次后撤离；开了游戏内自动轮次时，每个轮次是一整段自动轮次",
            "游戏内自动轮次": "开打前把游戏自带的自动轮次设成这个数，0 为不修改。每次进本共打 轮次 × 自动轮次 轮",
            "自动导航": "不在副本里时，从当前界面自动导航到夜航手册的这个关卡",
        })
        self.config_type["自动导航"] = {"type": "drop_down", "options": [NAV_OFF] + list(NAV_TARGETS)}

        self.action_timeout = 10

    def run(self):
        """主运行方法"""
        DNAOneTimeTask.run(self)
        self.move_mouse_to_safe_position(save_current_pos=False)
        self.set_check_monthly_card()
        try:
            _to_do_task = self.get_task_by_class(AutoDefence)
            auto_nav = self.mission_target() is not None
            if auto_nav and not self.in_team():
                self.navigate_to_mission()
            config = dict(self.config)
            # AutoDefence counts the rounds actually played and retreats after 轮次 of them, so with the
            # game's auto rounds on, each of our 轮次 is a whole block of auto rounds
            config["轮次"] = int(self.config.get("轮次", 5)) * self.auto_round_block()
            self.log_info(f"每次进本打 {config['轮次']} 轮")
            _to_do_task.config_external_movement(self.walk_to_aim, config,
                                                 recover=self.return_to_mission if auto_nav else None)
            original_info_set = _to_do_task.info_set
            _to_do_task.info_set = self.info_set
            return _to_do_task.do_run()
        except TaskDisabledException:
            pass
        except Exception as e:
            logger.error("AutoMyDungeonTask error", e)
            raise
        finally:
            if _to_do_task is not self:
                _to_do_task.info_set = original_info_set

    # def do_run(self):
    #     """执行任务的核心逻辑"""
    #     # 加载角色信息
    #     self.load_char()

    #     # 初始化变量
    #     _start_time = 0  # 任务开始时间
    #     _skill_time = 0  # 上次释放技能的时间
    #     _count = 0  # 完成次数计数器

    #     # 如果已经在队伍中，先放弃当前任务
    #     if self.in_team():
    #         self.log_info("检测到已在队伍中，先放弃当前任务")
    #         self.give_up_mission()
    #         self.wait_until(lambda: not self.in_team(), time_out=30, settle_time=1)

    #     # 主循环
    #     while True:
    #         # 在队伍中时的逻辑（战斗中）
    #         if self.in_team():
    #             # 第一次进入队伍时记录开始时间
    #             if _start_time == 0:
    #                 _start_time = time.time()
    #                 self.log_info(f"开始第 {_count + 1} 次任务")

    #             # 持续释放技能
    #             _skill_time = self.use_skill(_skill_time)

    #             # 检查是否超时
    #             elapsed = time.time() - _start_time
    #             if elapsed >= self.config.get("超时时间", 180):
    #                 logger.warning(f"任务超时 ({elapsed:.1f}秒)，重新开始...")
    #                 self.give_up_mission()
    #                 self.wait_until(lambda: not self.in_team(), time_out=30, settle_time=1)
    #                 _start_time = 0  # 重置计时器

    #         # 处理任务界面
    #         _status = self.handle_mission_interface()

    #         if _status == Mission.START:
    #             # 任务完成
    #             elapsed = time.time() - _start_time if _start_time > 0 else 0
    #             _count += 1
    #             self.log_info(
    #                 f"任务完成 [{_count}/{self.config.get('刷几次', 999)}] 用时: {elapsed:.1f}秒"
    #             )

    #             # 检查是否达到目标次数
    #             if _count >= self.config.get("刷几次", 999):
    #                 self.log_info(f"已完成全部 {_count} 次任务")
    #                 self.soundBeep()
    #                 return

    #             # 等待重新进入队伍
    #             self.wait_until(self.in_team, time_out=30)

    #             # 重置计时器
    #             _start_time = time.time()

    #             # 走到目标位置
    #             try:
    #                 self.walk_to_aim()
    #             except TaskDisabledException:
    #                 raise
    #             except Exception as e:
    #                 logger.error(f"移动到目标位置失败: {e}")
    #                 self.give_up_mission()
    #                 self.wait_until(lambda: not self.in_team(), time_out=30, settle_time=1)
    #                 _start_time = 0
    #             _skill_time = 0
    #         # 短暂休眠
    #         self.sleep(0.2)

    @property
    def nav(self):
        if getattr(self, '_nav', None) is None:
            self._nav = Nav(OkScriptBackend(self), log=self.log_debug, rows_path=ROWS_PATH)
        return self._nav

    def mission_target(self):
        entry = NAV_TARGETS.get(self.config.get("自动导航", NAV_OFF))
        if entry is None:
            return None
        level, row = entry
        rounds = int(self.config.get("游戏内自动轮次", 0) or 0)
        return Nightbook(level, row, mode=T.MISSIONS[8], lv=level, auto_rounds=rounds or None)

    def auto_round_block(self):
        """How many rounds the game plays on its own between our decisions: the 自动轮次 count, or 1."""
        rounds = int(self.config.get("游戏内自动轮次", 0) or 0)
        if rounds:
            return rounds
        state = self.nav.where()
        if state.screen == 'start' and state.info.get('auto_on'):
            return state.info.get('auto_rounds') or 1
        if state.screen != 'start':
            self.log_info("不在关卡开始界面，读不到游戏内自动轮次，按 1 计")
        return 1

    def navigate_to_mission(self):
        target = self.mission_target()
        self.log_info(f"导航到夜航手册 Lv.{target.level} 第 {target.row + 1} 个关卡")
        try:
            self.nav.go(target)
        except NoSuchEntry as e:
            raise Exception(f"夜航手册 Lv.{e.level} 现在只有 {len(e.names)} 个关卡，选的是第 {target.row + 1} 个，请在「自动导航」里重新选择")
        except WrongMission as e:
            raise Exception(f"夜航手册 Lv.{target.level} 第 {target.row + 1} 个关卡是 {e.found}，不是扼守，请重新选择")
        except NavError as e:
            raise Exception(f"自动导航失败：{e}")

    def return_to_mission(self):
        state = self.nav.where()
        if state.screen in ('commission', 'book', 'world', 'main_menu'):
            self.log_info(f"停在 {state.screen}，重新导航到关卡")
            self.navigate_to_mission()

    def walk_to_aim(self, delay=0):
        """
        从起点走到目标位置的路径
        路径参考: EMT中的扼守-30or65.json，使用复位
        """
        logger.info("开始移动到目标位置")
        move_start = time.time()

        try:
            # ===== 根据扼守-30or65.json录制的路径 =====

            # 0.52s: 开始向前移动
            self.send_key_down("lalt")

            self.sleep(delay)
            self.send_key_down("w")

            # 1.11s: 开始冲刺 (0.59s后)
            self.sleep(0.59)
            self.send_key_down(self.get_dodge_key())

            # 1.33s: 向左移动 (0.22s后)
            self.sleep(0.22)
            self.send_key_down("a")

            # 2.41s: 停止前进 (1.08s后)
            self.sleep(1.08)
            self.send_key_up("w")

            # 3.85s: 再次向前 (1.44s后)
            self.sleep(1.44)
            self.send_key_down("w")

            # 3.94s: 停止向左 (0.09s后)
            self.sleep(0.09)
            self.send_key_up("a")

            # 4.84s: 再次向左 (0.90s后)
            self.sleep(0.90)
            self.send_key_down("a")

            # 5.22s-7.82s: Shift连续切换 (可能在调整位置)
            self.sleep(0.38)
            self.send_key_up(self.get_dodge_key())
            self.sleep(0.24)
            self.send_key(self.get_dodge_key(), down_time=0.35)
            self.sleep(0.79)
            self.send_key(self.get_dodge_key(), down_time=0.41)
            self.sleep(0.80)
            self.send_key_down(self.get_dodge_key())

            # 9.09s: 停止前进 (1.27s后)
            self.sleep(1.27)
            self.send_key_up("w")

            # 9.56s: 短暂前进 (0.47s后)
            self.sleep(0.47)
            self.send_key_down("w")

            # 9.91s: 停止前进 (0.35s后)
            self.sleep(0.35)
            self.send_key_up("w")

            # 10.70s: 跳跃 (0.79s后)
            self.sleep(0.79)
            self.send_key("space", down_time=0.09)

            # 12.83s: 短暂后退调整 (2.04s后)
            self.sleep(2.04)
            self.send_key("s", down_time=0.09)

            # 13.32s: 短暂前进调整 (0.40s后)
            self.sleep(0.40)
            self.send_key("w", down_time=0.10)

            # 13.86s: 再次短暂后退 (0.44s后)
            self.sleep(0.44)
            self.send_key("s", down_time=0.10)

            # 18.89s-18.99s: 释放所有移动键 (4.93s后)
            self.sleep(4.93)
            self.send_key_up(self.get_dodge_key())
            self.sleep(0.10)
            self.send_key_up("a")

            self.send_key_up("lalt")
            # 19.97s: 复位并传送到目标位置
            if not self.reset_and_transport():
                logger.info("复位失败，重开任务...")
                self.give_up_mission()
                return

            # ===== 路径编写结束 =====

            elapsed = time.time() - move_start
            logger.info(f"移动完成，用时 {elapsed:.1f}秒")

        except TaskDisabledException:
            raise
        except Exception as e:
            logger.error("移动过程出错", e)
            raise
        finally:
            # 确保释放所有按键
            self.send_key_up("w")
            self.send_key_up("a")
            self.send_key_up("s")
            self.send_key_up("d")
            self.send_key_up(self.get_dodge_key())
            self.send_key_up("lalt")
