"""功能可以请求到达的界面。开始界面类的目标还可以说明到达后要怎么设置。

目标给导航器三样东西：goal（到达时界面应该是什么样）、route（从大世界到它经过的节点）、
setup（到达后执行的设置）。新的目标类型继承 Target，按需重写其中几个。
"""
from dataclasses import dataclass, field
from typing import Optional, Union

from src.nav import edges
from src.nav import text_zh as T


class Target:
    def goal(self):
        raise NotImplementedError

    def route(self):
        return edges.route(self.goal())

    def setup(self, nav):
        pass


@dataclass(frozen=True)
class World(Target):
    def goal(self):
        return {'screen': 'world'}


@dataclass(frozen=True)
class MainMenu(Target):
    def goal(self):
        return {'screen': 'main_menu'}


@dataclass(frozen=True)
class Menu(Target):
    """主菜单图标打开的界面，比如 Menu('背包')。"""
    name: str

    def goal(self):
        return {'screen': 'menu', 'name': self.name}


@dataclass(frozen=True)
class BookSection(Target):
    """手册顶栏的分区，比如 BookSection('梦魔残声')。"""
    name: str

    def goal(self):
        return {'screen': 'book', 'section': self.name}


@dataclass(frozen=True)
class Page(Target):
    """从手册分区进入的页面：'迷津' 或 'boss_map'。"""
    name: str

    def goal(self):
        return {'screen': 'page', 'name': self.name}


@dataclass(frozen=True)
class CommissionTab(Target):
    tab: str

    def goal(self):
        return {'screen': 'commission', 'tab': self.tab}


@dataclass(frozen=True)
class StartScreen(Target):
    """停在某个委托开始界面的目标的基类。

    auto_rounds：离开开始界面前把游戏自带的自动轮次设成什么。None 不动，0 关闭，
    1~99 打开并设成这个数（打完第一轮后游戏自动再打这么多轮）。
    """
    auto_rounds: Optional[int] = field(default=None, kw_only=True)

    def setup(self, nav):
        if self.auto_rounds is not None:
            nav.set_auto_rounds(self.auto_rounds)


@dataclass(frozen=True)
class Mission(StartScreen):
    """委托页的卡片和等级，比如 Mission('扼守/无尽', lv=60)。"""
    mode: str
    lv: Optional[int] = None

    def goal(self):
        return {'screen': 'start', 'via': T.TABS[0], 'mode': self.mode, 'lv': self.lv}


@dataclass(frozen=True)
class Nightbook(StartScreen):
    """夜航手册的一行：等级页加行号（从上往下，0 起）或行名的一部分。

    给了 mode / lv 时会在开始界面上核对。
    """
    level: int
    row: Union[int, str] = 0
    mode: Optional[str] = None
    lv: Optional[int] = None

    def goal(self):
        return {'screen': 'start', 'via': T.TABS[1], 'book': self.level, 'row': self.row,
                'mode': self.mode, 'lv': self.lv}


@dataclass(frozen=True)
class Letter(StartScreen):
    """委托密函里的一个委托，可以限定栏位：'角色'、'武器' 或 '魔之楔'。"""
    mode: str
    column: Optional[str] = None

    def goal(self):
        return {'screen': 'start', 'via': T.TABS[2], 'mode': self.mode, 'column': self.column}
