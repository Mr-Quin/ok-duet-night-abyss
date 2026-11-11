"""流程里不属于任何任务的游戏操作：回大世界、看一眼委托密函。"""
from src.nav import CommissionTab, NavError, World
from src.nav import text_zh as T
from src.nav.edges import letter_entries, letter_heads, letters_left
from src.routine.steps import ENDLESS, LETTERS_LEFT

# 切到委托密函页签后，栏位要过一两秒才画出来
READ_TRIES = 6


def yes(flag):
    return '是' if flag else '否'


def letter_facts(scr):
    """委托密函页上还有密函的栏里有没有无尽委托、还有没有密函；栏位还没画出来时为 None。"""
    heads = letter_heads(scr)
    if not heads:
        return None
    open_heads = [h for h in heads.values() if letters_left(scr, h) != 0]
    endless = any(T.ENDLESS in e['t'] for h in open_heads for e in letter_entries(scr, h))
    return {ENDLESS: yes(endless), LETTERS_LEFT: yes(open_heads)}


class Game:
    def __init__(self, make_nav):
        self.make_nav = make_nav
        self._nav = None

    @property
    def nav(self):
        if self._nav is None:
            self._nav = self.make_nav()
        return self._nav

    def world(self):
        self.nav.go(World())

    def letters(self):
        """到委托密函页签读一遍，不进任何委托。"""
        self.nav.go(CommissionTab(T.TABS[2]))
        for _ in range(READ_TRIES):
            facts = letter_facts(self.nav.b.read())
            if facts is not None:
                return facts
            self.nav.b.sleep(1)
        raise NavError('委托密函页上读不出栏位')
