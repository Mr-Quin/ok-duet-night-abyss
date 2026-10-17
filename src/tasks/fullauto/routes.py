"""从出生点走到扼守目标点的录好的路线。

扼守的地图是一块块房间拼起来的，同一个出生房间会出现在好几张图里，转的方向不同、周围的房间
不同，但出生时的画面和目标标记的位置都一样，从那里走过去的路线也一样。所以路线按出生画面
（画面上半部分的场景）加上标记在画面上的位置来认，不按地图认。

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
    def __init__(self, path, data):
        self.path = path
        self.name = os.path.splitext(os.path.basename(path))[0]
        self.steps = data['steps']
        self.marker = tuple(data['marker'])
        self.view = np.array(data['view'], dtype=np.float32).reshape(VIEW_SIZE[1], VIEW_SIZE[0])

    def matches(self, view, marker):
        close = abs(marker[0] - self.marker[0]) < SAME_MARKER and abs(marker[1] - self.marker[1]) < SAME_MARKER
        return close and _similarity(view, self.view) >= SAME_VIEW


class RouteLibrary:
    def __init__(self, folders=(SHIPPED_DIR, LEARNED_DIR)):
        self.routes = []
        for folder in folders:
            for path in sorted(glob.glob(os.path.join(folder, '*.json'))):
                with open(path, encoding='utf-8') as f:
                    self.routes.append(Route(path, json.load(f)))

    def find(self, frame, marker):
        view = view_feature(frame)
        return next((r for r in self.routes if r.matches(view, marker)), None)

    def save(self, frame, marker, steps, folder=LEARNED_DIR, name=None):
        os.makedirs(folder, exist_ok=True)
        name = name or time.strftime('learned_%Y%m%d_%H%M%S')
        path = os.path.join(folder, name + '.json')
        data = {'marker': [round(marker[0], 3), round(marker[1], 3)],
                'view': [round(float(v), 3) for v in view_feature(frame).ravel()], 'steps': steps}
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f)
        self.routes.append(Route(path, data))
        return path


def play(task, route):
    """按时间线重放一条路线，结束时松开所有还按着的键。"""
    t0, held = time.time(), set()
    try:
        for step in route.steps:
            wait = step['t'] - (time.time() - t0)
            if wait > 0:
                task.sleep(wait)
            if 'down' in step:
                key = KEY_NAMES.get(step['down'], step['down'])
                task.send_key_down(key)
                held.add(key)
            elif 'up' in step:
                key = KEY_NAMES.get(step['up'], step['up'])
                task.send_key_up(key)
                held.discard(key)
            elif 'turn' in step:
                task.move_mouse_relative(step['turn'][0], step['turn'][1])
    finally:
        for key in held:
            task.send_key_up(key)
