"""从出生点走到扼守目标点的录好的路线。

扼守的地图是一块块房间拼起来的，同一个出生房间会出现在好几张图里，转的方向不同、周围的房间
不同，但出生时的画面和目标标记的位置都一样，从那里走过去的路线也一样。所以路线先按标记在
画面上的位置认，再看地图对不对得上；地图没对上时，出生画面（画面上半部分的场景）很像也算，
这样一条路线能用到同一个出生房间的别的图上。只靠画面不行：同一张图每次出生的光线不一样，
画面相关系数能低到 0.2。

一条路线是一串带时间的按键和镜头转动，和 MarkerWalk.steps 的格式相同：
    {'t': 秒, 'down': 键} / {'t': 秒, 'up': 键} / {'t': 秒, 'turn': [dx, dy]}
路线放在 routes/（随程序发布）和 configs/defence_routes/（自动走到之后学来的）。
"""
import glob
import json
import os
import time

import cv2
import numpy as np

SHIPPED_DIR = os.path.join(os.path.dirname(__file__), 'routes')
LEARNED_DIR = os.path.join('configs', 'defence_routes')
VIEW_SIZE = (96, 36)
# 同一个出生房间的画面相关系数实测 0.88 以上（有队友挡住一点时最低），不同房间 0.41 以下
SAME_VIEW = 0.75
# 出生时标记在画面上的位置（占画面宽、高的比例）差这么多以内算同一个目标
SAME_MARKER = 0.05
# 录制工具和 ok-script 对左 Shift 的叫法不同
KEY_NAMES = {'shift_l': 'lshift', 'shift_r': 'rshift'}
MOVE_KEYS = ('w', 'a', 's', 'd')


def view_feature(frame):
    """出生画面的指纹：上半部分的场景（人物在下半部分），缩小后归一化。"""
    H, W = frame.shape[:2]
    view = frame[int(0.08 * H):int(0.45 * H), int(0.18 * W):int(0.82 * W)]
    gray = cv2.cvtColor(cv2.resize(view, VIEW_SIZE, interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2GRAY)
    gray = gray.astype(np.float32)
    return (gray - gray.mean()) / (gray.std() + 1e-6)


def _similarity(a, b):
    return float((a * b).mean())


class Route:
    def __init__(self, path, data, learned):
        self.path = path
        self.data = data
        self.learned = learned
        self.name = os.path.splitext(os.path.basename(path))[0]
        self.steps = data['steps']
        self.marker = tuple(data['marker'])
        self.view = np.array(data['view'], dtype=np.float32).reshape(VIEW_SIZE[1], VIEW_SIZE[0])

    @property
    def maps(self):
        return set(self.data.get('maps', []))

    @property
    def walk_only(self):
        return self.data.get('walk_only', False)

    def matches(self, view, marker, map_name=None):
        close = abs(marker[0] - self.marker[0]) < SAME_MARKER and abs(marker[1] - self.marker[1]) < SAME_MARKER
        return close and (map_name in self.maps or _similarity(view, self.view) >= SAME_VIEW)


class RouteLibrary:
    """随程序发布的路线只读；学来的路线放在 learned_dir，只有这个库写它们。"""

    def __init__(self, shipped_dir=SHIPPED_DIR, learned_dir=LEARNED_DIR):
        self.learned_dir = learned_dir
        self.routes = []
        for folder, learned in ((shipped_dir, False), (learned_dir, True)):
            for path in sorted(glob.glob(os.path.join(folder, '*.json'))) if folder else ():
                with open(path, encoding='utf-8') as f:
                    self.routes.append(Route(path, json.load(f), learned))

    def find(self, frame, marker, map_name=None):
        view = view_feature(frame)
        return next((r for r in self.routes if r.matches(view, marker, map_name)), None)

    def closest(self, frame, marker):
        """(最像的路线, 画面相关系数, 标记位置差)，没对上时用来查是哪一项差得多。"""
        view = view_feature(frame)
        scored = [(r, _similarity(view, r.view), max(abs(marker[0] - r.marker[0]), abs(marker[1] - r.marker[1])))
                  for r in self.routes]
        return max(scored, key=lambda s: s[1] - s[2], default=(None, 0.0, 1.0))

    def save(self, frame, marker, steps, map_name=None, name=None):
        os.makedirs(self.learned_dir, exist_ok=True)
        name = name or time.strftime('learned_%Y%m%d_%H%M%S')
        path = os.path.join(self.learned_dir, name + '.json')
        data = {'marker': [round(marker[0], 3), round(marker[1], 3)], 'maps': [map_name] if map_name else [],
                'view': [round(float(v), 3) for v in view_feature(frame).ravel()], 'steps': steps}
        _write(path, data)
        self.routes.append(Route(path, data, learned=True))
        return path

    def remember_map(self, route, map_name):
        """路线在一张新的图上走通了，记下来，下次这张图光线不同也能认出来。"""
        if not map_name or map_name in route.maps or not route.learned:
            return
        route.data['maps'] = sorted(route.maps | {map_name})
        _write(route.path, route.data)

    def replay_failed(self, route):
        """回放走不到但按标记走得到：留着这条路线认出生点，以后这里只按标记走，不再重新学。"""
        if not route.learned:
            return
        route.data['walk_only'] = True
        _write(route.path, route.data)


def _write(path, data):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f)


def play(task, route):
    """按时间线重放一条路线，结束时松开所有还按着的键。"""
    t0, held, dodge = time.time(), [], task.get_dodge_key()
    try:
        for step in route.steps:
            wait = step['t'] - (time.time() - t0)
            if wait > 0:
                task.sleep(wait)
            if 'down' in step:
                key = KEY_NAMES.get(step['down'], step['down'])
                if key == dodge and not any(k in MOVE_KEYS for k in held):
                    # 不带方向的闪避是向后撤
                    continue
                task.send_key_down(key)
                held.append(key)
            elif 'up' in step:
                key = KEY_NAMES.get(step['up'], step['up'])
                if key in MOVE_KEYS and dodge in held:
                    task.send_key_up(dodge)
                    held.remove(dodge)
                if key in held:
                    task.send_key_up(key)
                    held.remove(key)
            elif 'turn' in step:
                task.move_mouse_relative(step['turn'][0], step['turn'][1])
    finally:
        for key in sorted(held, key=lambda k: k in MOVE_KEYS):
            task.send_key_up(key)
