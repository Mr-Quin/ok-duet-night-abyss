"""读左上角的小地图：认出是哪张图，读出目标菱形的方位。

小地图始终北朝上，同一张图出生时看到的样子都一样，所以拿出生时的小地图和 maps/ 里每张图的
参照比一比就知道是哪张图。参照只截了小地图本身，96×96。
"""
import glob
import math
import os

import cv2
import numpy as np

# 小地图圆心（占画面宽、高的比例）和半径（占画面宽的比例），2560×1440 上量的
CENTER_X, CENTER_Y, RADIUS = 0.0754, 0.1389, 0.0566
SIZE = 96
MAPS_DIR = os.path.join(os.path.dirname(__file__), 'maps')
# 同一张图出生时的相关系数实测都在 0.95 以上，不同的图最高 0.52
SAME_MAP = 0.75


def crop(frame):
    H, W = frame.shape[:2]
    cx, cy, r = int(CENTER_X * W), int(CENTER_Y * H), int(RADIUS * W)
    return cv2.resize(frame[max(0, cy - r):cy + r, max(0, cx - r):cx + r], (SIZE, SIZE),
                      interpolation=cv2.INTER_AREA)


def _gold(hsv):
    return (hsv[..., 0] >= 14) & (hsv[..., 0] <= 32) & (hsv[..., 1] > 70) & (hsv[..., 2] > 150)


def _layout(mini):
    """亮度和可比的像素：圆盘内，去掉中间的箭头和视野锥、金色菱形、右下角的 M 键。"""
    hsv = cv2.cvtColor(mini, cv2.COLOR_BGR2HSV)
    yy, xx = np.mgrid[0:SIZE, 0:SIZE]
    d = np.hypot(xx - SIZE / 2, yy - SIZE / 2) / (SIZE / 2)
    mask = (d < 0.92) & (d > 0.35)
    mask &= ~cv2.dilate(_gold(hsv).astype(np.uint8), np.ones((5, 5), np.uint8)).astype(bool)
    mask[int(0.78 * SIZE):, int(0.78 * SIZE):] = False
    return hsv[..., 2].astype(np.float32), mask


def _similarity(a, b):
    (ga, ma), (gb, mb) = a, b
    m = ma & mb
    if m.sum() < 100:
        return 0.0
    x, y = ga[m], gb[m]
    x = (x - x.mean()) / (x.std() + 1e-6)
    y = (y - y.mean()) / (y.std() + 1e-6)
    return float((x * y).mean())


class MapLibrary:
    def __init__(self, folder=MAPS_DIR):
        self.maps = {}
        for path in sorted(glob.glob(os.path.join(folder, '*.png'))):
            self.maps[os.path.splitext(os.path.basename(path))[0]] = _layout(cv2.imread(path))

    def identify(self, frame):
        """(图名, 相关系数)；和哪张图都不像时图名为 None。"""
        layout = _layout(crop(frame))
        scores = {name: _similarity(layout, ref) for name, ref in self.maps.items()}
        if not scores:
            return None, 0.0
        name = max(scores, key=scores.get)
        return (name if scores[name] >= SAME_MAP else None), scores[name]


def objective_bearing(frame):
    """目标菱形相对小地图圆心的方位（度，北为 0、顺时针）；看不到菱形时为 None。

    目标太远时菱形贴在圆边上，方位依然有效。
    """
    mini = crop(frame)
    hsv = cv2.cvtColor(mini, cv2.COLOR_BGR2HSV)
    yy, xx = np.mgrid[0:SIZE, 0:SIZE]
    dx, dy = xx - SIZE / 2, yy - SIZE / 2
    d = np.hypot(dx, dy) / (SIZE / 2)
    # 箭头也是金色的，但在圆心，也比菱形暗
    gold = _gold(hsv) & (hsv[..., 2] > 180) & (d > 0.22) & (d < 1.0)
    if gold.sum() < 4:
        return None
    a = np.arctan2(dx[gold], -dy[gold])
    return (math.degrees(math.atan2(np.sin(a).mean(), np.cos(a).mean())) + 360) % 360
