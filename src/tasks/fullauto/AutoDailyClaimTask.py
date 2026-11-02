"""日常领奖：历练的备忘手记、协会活跃、吟游诗集、声名惠赠，主菜单图标带红点的才进去。

界面导航读的是简体中文界面上的文字，所以这个任务只支持简体中文客户端。
"""
from qfluentwidgets import FluentIcon

from ok import TaskDisabledException
from src.nav import Nav, NavError
from src.nav.claims import PAGES, Claimer
from src.nav.okscript import CACHE_PATH, OkScriptBackend
from src.tasks.BaseDNATask import BaseDNATask


class AutoDailyClaimTask(BaseDNATask):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.icon = FluentIcon.COMPLETED
        self.name = "日常领奖"
        self.description = "从任意界面打开主菜单，领取带红点的历练、协会、吟游诗集和声名奖励；仅支持简体中文客户端"
        self.group_name = "全自动"
        self.group_icon = FluentIcon.CAFE
        self.default_config.update({name: True for name in PAGES})
        self.config_description.update({
            "历练": "备忘手记的每日任务和完成度奖励",
            "协会": "每日、每周考察和本周个人活跃宝箱",
            "吟游诗集": "见闻报酬和装订报酬",
            "声名": "惠赠里能提交的委托，会交出需求物品，每个已激活的地区都交",
        })

    def run(self):
        # 不开挂机小动作：它的随机按键会在菜单里乱按
        if hasattr(self.executor.interaction, 'activate'):
            self.executor.interaction.activate()
        self.sleep(0.5)
        self.move_mouse_to_safe_position(save_current_pos=False)
        nav = Nav(OkScriptBackend(self), log=self.log_info, cache_path=CACHE_PATH)
        names = [name for name in PAGES if self.config.get(name, True)]
        try:
            claimed = Claimer(nav, log=self.log_info).run(names)
        except TaskDisabledException:
            return
        except NavError as e:
            raise Exception(f"自动导航失败：{e}")
        self.log_info(f"领完了：{'、'.join(claimed) or '没有可领的'}", notify=True)
