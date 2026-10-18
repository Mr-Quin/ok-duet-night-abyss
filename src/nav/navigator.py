"""从游戏当前所在的任意界面走到目标界面。

每一步读一次画面、做一个动作：界面登记了处理方式就照做；画面在目标路线上就走登记的那条边；
在同级界面之间就直接切换；否则按 Esc 退一层。对界面和操作的认识都在 graph.py 的注册表里，
内置的那部分登记在 screens.py、edges.py 和 handlers.py，这里只负责照表走。

处理方式和边拿到的 nav 就是 Navigator，可以用这些：
  b               后端：读画面、OCR、点击、按键、滚动
  goal            目标 goal() 返回的字典
  log(msg)        记一行日志
  click(item)     点 OCR 结果的中心
  wait(limit)     画面可能还在变化时先等几次
  state           这次导航里的临时状态，键名由用到的处理方式和边自己约定
  cache           跨导航保存的数据，改完调用 save_cache() 写回 cache_path
"""
import json

from src.nav import graph
from src.nav import screens as S
from src.nav.graph import NavError

# 同一个动作做了这么多次界面还没变，就认为卡住了
MAX_REPEATS = 4
# 等待（动画、加载、局内还在打）不算步数，但总次数有上限
MAX_WAITS = 600


def node_of(screen, info):
    key = {'menu': 'name', 'page': 'name', 'book': 'section', 'commission': 'tab', 'start': 'via'}.get(screen)
    return screen, info.get(key) if key else None


def same_node(a, b):
    return a[0] == b[0] and (b[1] is None or a[1] == b[1])


class SentInputs:
    """转发给 backend，同时记下这一步发出去的输入。"""

    def __init__(self, inner):
        self.inner = inner
        self.sent = []

    def __getattr__(self, name):
        return getattr(self.inner, name)

    def click(self, x, y):
        self.sent.append(('click', round(x, 3), round(y, 3)))
        self.inner.click(x, y)

    def drag(self, x0, y0, x1, y1):
        self.sent.append(('drag', round(x0, 3), round(y0, 3), round(x1, 3), round(y1, 3)))
        self.inner.drag(x0, y0, x1, y1)

    def key(self, name):
        self.sent.append(('key', name))
        self.inner.key(name)

    def scroll(self, x, y, notches):
        self.sent.append(('scroll', notches))
        self.inner.scroll(x, y, notches)


class Navigator:
    """一次导航。"""

    def __init__(self, backend, target, log=None, atlas=None, cache_path=None):
        self.b = SentInputs(backend)
        self.goal, self.route = target.goal(), target.route()
        self.step_log = []
        log = log or (lambda msg: None)

        def log_step(msg):
            self.step_log.append(msg)
            log(msg)
        self.log = log_step
        self.atlas = atlas if atlas is not None else S.load_atlas()
        self.cache_path = cache_path
        self.cache = self._load_cache()
        self.state = {}
        self.unsure = 0

    def _load_cache(self):
        if not self.cache_path:
            return {}
        try:
            with open(self.cache_path, encoding='utf-8') as f:
                return json.load(f)
        except (OSError, ValueError):
            return {}

    def save_cache(self):
        if not self.cache_path:
            return
        try:
            with open(self.cache_path, 'w', encoding='utf-8') as f:
                json.dump(self.cache, f, ensure_ascii=False)
        except OSError:
            # 只是缓存，存不下来下次重新读一遍
            pass

    def click(self, item):
        self.b.click(item['x'], item['y'])

    def wait(self, limit):
        """画面可能还在淡入时先等等：前 limit 次返回 None（等待），之后返回 False。"""
        self.unsure += 1
        return None if self.unsure <= limit else False

    def step(self):
        scr = self.b.read()
        screen, info = S.classify(scr, self.atlas)
        self.seen_now = (screen, tuple(sorted(i['t'] for i in scr.items)))
        shown = {k: v for k, v in info.items() if isinstance(v, (str, int, float, bool, type(None)))}
        self.log('%s %s' % (screen, shown))
        handler = graph.HANDLERS.get(screen)
        if handler:
            result = handler(self, scr, info)
            if result is not NotImplemented:
                return result
        return self.follow_route(scr, screen, info)

    def follow_route(self, scr, screen, info):
        here = node_of(screen, info)
        path = self.route
        if same_node(here, path[-1]):
            return True
        on = next((k for k, n in enumerate(path) if same_node(here, n)), None)
        if on is not None:
            step = graph.find_edge(here, path[on + 1])
            if step is None:
                raise NavError('没有从 %s 到 %s 的路' % (here, path[on + 1]))
            return step(self, scr, here, path[on + 1], info)
        for group, move in graph.SIDEWAYS:
            target = next((n for n in path if n[0] in group), None) if here[0] in group else None
            if target:
                return move(self, here, target)
        self.b.key('esc')
        return False

    def run(self, max_steps=40):
        seen = {}
        k = waits = 0
        while k < max_steps and waits < MAX_WAITS:
            before = self.b.thumb()
            self.step_log, self.b.sent = [], []
            result = self.step()
            if result:
                self.log('%d 步到达' % k)
                return True
            if result is None:
                waits += 1
                self.b.sleep(0.4)
                continue
            k += 1
            self.unsure = 0
            # 同一个画面上发同样的输入算重复；文字里有在变的（滚动后的行名）就不算
            state = self.seen_now + (tuple(self.b.sent),)
            seen[state] = seen.get(state, 0) + 1
            if seen[state] > MAX_REPEATS:
                raise NavError('一直在重复：%s' % ' / '.join(self.step_log))
            self.b.settle(before)
            if seen[state] >= 2:
                # 游戏卡顿时会吞掉输入，重复同一个动作前多等一会儿
                self.b.sleep(1.5 * (seen[state] - 1))
        return False
