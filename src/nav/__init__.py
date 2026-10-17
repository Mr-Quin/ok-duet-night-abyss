"""游戏界面导航：从任意界面走到指定界面，再把控制交还给调用的功能。

    from src.nav import Nav, Nightbook
    from src.nav.okscript import OkScriptBackend

    Nav(OkScriptBackend(task)).go(Nightbook(65, row=2, auto_rounds=3))

导航层本身不依赖 ok-script，只通过 Backend 取画面、做 OCR 和输入；okscript.py 是
ok-script 上的实现。
"""
from src.nav import edges, handlers  # noqa: F401  导入时登记内置的路线和界面处理方式
from src.nav.backend import Backend, Screen
from src.nav.graph import NavError, NoSuchEntry, WrongMission
from src.nav.nav import Nav, State
from src.nav.targets import (BookSection, CommissionTab, Letter, MainMenu, Menu, Mission, Nightbook, Page,
                             StartScreen, Target, World)

__all__ = ['Backend', 'Screen', 'NavError', 'NoSuchEntry', 'WrongMission', 'Nav', 'State', 'Target', 'StartScreen',
           'World', 'MainMenu', 'Menu', 'BookSection', 'Page', 'CommissionTab', 'Mission', 'Nightbook', 'Letter']
