"""导航层对游戏界面的全部认识，放在几张注册表里，各模块导入时往里登记。

  detector  从一帧认出是哪个界面         @detector(顺序) fn(scr, atlas) -> (界面, 信息) 或 None
  edge      沿路线从一个界面走到下一个   @edge(当前界面, 下一节点) fn(nav, scr, here, nxt, info)
  sideways  同级界面之间直接切换         @sideways(界面集合) fn(nav, here, target)
            （手册顶栏的分区、委托页的页签）
  handler   某个界面无论在哪出现都这样处理 @handler(界面) fn(nav, scr, info)
            （弹窗、局内对话框）

节点是 (界面, 键)，比如 ('commission', '夜航手册')；路线里键为 None 表示任意键都算。
edge / handler 返回 True 表示到达目标，False 表示做了一步操作，None 表示等画面变化，
NotImplemented 表示交给导航器的默认规则。

界面特殊的副本可以在自己的模块里登记界面、路线和处理方式，再写一个给出路线的目标类，
不需要改这里或导航器。
"""

DETECTORS = []
EDGES = {}
SIDEWAYS = []
HANDLERS = {}


class NavError(RuntimeError):
    pass


class NoSuchEntry(NavError):
    """夜航手册该等级的页面上没有要找的那一行。"""

    def __init__(self, level, row, names):
        self.level, self.row, self.names = level, row, names
        wanted = '第 %d 个' % (row + 1) if isinstance(row, int) else repr(row)
        super().__init__('夜航手册 Lv.%d 只有 %d 个关卡 %s，没有%s' % (level, len(names), names, wanted))


class WrongMission(NavError):
    """那一行存在，但进去是另一种委托。"""

    def __init__(self, found, wanted):
        self.found, self.wanted = found, wanted
        super().__init__('这个关卡是 %s，不是 %s' % (found, wanted))


def detector(order):
    def register(fn):
        DETECTORS.append((order, fn))
        DETECTORS.sort(key=lambda d: d[0])
        return fn
    return register


def edge(from_screen, to_node):
    """to_node 为界面名，或者完整节点 (界面, 键)，表示这条路只通向这个键。"""
    def register(fn):
        EDGES[(from_screen, to_node)] = fn
        return fn
    return register


def sideways(screens):
    def register(fn):
        SIDEWAYS.append((frozenset(screens), fn))
        return fn
    return register


def handler(screen):
    def register(fn):
        HANDLERS[screen] = fn
        return fn
    return register


def classify(scr, atlas):
    for _, fn in DETECTORS:
        found = fn(scr, atlas)
        if found:
            return found
    return 'unknown', {}


def find_edge(here, nxt):
    for key in ((here[0], nxt), (here[0], nxt[0])):
        if key in EDGES:
            return EDGES[key]
    return None
