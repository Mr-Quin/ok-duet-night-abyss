"""Screens a feature can ask for. A start-screen target can also say how the screen should be set up."""
from dataclasses import dataclass, field
from typing import Optional, Union

from src.nav import text_zh as T


@dataclass(frozen=True)
class World:
    def goal(self):
        return {'screen': 'world'}


@dataclass(frozen=True)
class MainMenu:
    def goal(self):
        return {'screen': 'main_menu'}


@dataclass(frozen=True)
class Menu:
    """A screen opened from a main-menu tile, e.g. Menu('背包')."""
    name: str

    def goal(self):
        return {'screen': 'menu', 'name': self.name}


@dataclass(frozen=True)
class BookSection:
    """A section of the book's top bar, e.g. BookSection('梦魔残声')."""
    name: str

    def goal(self):
        return {'screen': 'book', 'section': self.name}


@dataclass(frozen=True)
class Page:
    """A page entered from a book section: '迷津' or 'boss_map'."""
    name: str

    def goal(self):
        return {'screen': 'page', 'name': self.name}


@dataclass(frozen=True)
class CommissionTab:
    tab: str

    def goal(self):
        return {'screen': 'commission', 'tab': self.tab}


@dataclass(frozen=True)
class StartScreen:
    """Base for targets that end on a mission's start screen.

    auto_rounds: the in-game auto-round count to set before handing over; None leaves it as is.
    """
    auto_rounds: Optional[int] = field(default=None, kw_only=True)


@dataclass(frozen=True)
class Mission(StartScreen):
    """A card on the 委托 tab at a given tier, e.g. Mission('扼守/无尽', lv=60)."""
    mode: str = ''
    lv: Optional[int] = None

    def goal(self):
        return {'screen': 'start', 'via': T.TABS[0], 'mode': self.mode, 'lv': self.lv}


@dataclass(frozen=True)
class Nightbook(StartScreen):
    """A 夜航手册 entry: the level page and a row, by index from the top or by part of its name.

    mode and lv, when given, are checked on the start screen.
    """
    level: int = 0
    row: Union[int, str] = 0
    mode: Optional[str] = None
    lv: Optional[int] = None

    def goal(self):
        return {'screen': 'start', 'via': T.TABS[1], 'book': self.level, 'row': self.row,
                'mode': self.mode, 'lv': self.lv}


@dataclass(frozen=True)
class Letter(StartScreen):
    """A 委托密函 mission, optionally from one column: '角色', '武器' or '魔之楔'."""
    mode: str = ''
    column: Optional[str] = None

    def goal(self):
        return {'screen': 'start', 'via': T.TABS[2], 'mode': self.mode, 'column': self.column}
