"""日常领奖：主菜单上带红点的界面挨个进去，领完能领的再回大世界。

每个界面里反复做三件事，直到没有可做的：关掉领奖弹窗、看到「Space 全部领取」就按空格、
点一个红点。红点只在各界面列出的区域里点，购买等级、解锁精装诗集这类按钮都不在这些区域里。
"""
from dataclasses import dataclass

import cv2
import numpy as np

from src.nav import MainMenu, World
from src.nav import text_zh as T

MAX_STEPS = 40
# 2560 宽时红点直径约 23 像素
DOT_SIZE = (0.006, 0.013)
# 点两次还在的红点不再点，比如需求物品不够的委托
MAX_TAPS = 2
# 红点在图标或按钮的右上角，往左下挪一点才点在图标上
TAP_OFFSET = (-0.008, 0.012)
HINT_BAR = (0.8, 0.94, 1, 1)
REGION_NAME = (0.08, 0.05, 0.3, 0.09)
NEVER_TAP = ('前往', '购买', '解锁')
MENU_TILES = (0.03, 0.4, 0.35, 0.97)


@dataclass(frozen=True)
class Page:
    dots: tuple
    switch: str = None


PAGES = {
    # 顶部的入门指南、备忘手记页签；左边完成度的奖励，点一个就领完已达成的
    '历练': Page(((0.1, 0.12, 0.36, 0.2), (0.14, 0.22, 0.24, 0.66))),
    # 本周个人活跃入口；每日、每周考察页签；底部活跃宝箱
    '协会': Page(((0, 0.65, 0.2, 0.8), (0.02, 0.14, 0.25, 0.32), (0.3, 0.82, 0.95, 0.9))),
    # 顶栏的见闻报酬、装订报酬，跳过中间的转述见闻
    '吟游诗集': Page(((0.15, 0, 0.29, 0.07), (0.4, 0, 0.52, 0.07))),
    # 惠赠入口（红点有时在图标上，有时在文字右边）；委托卡片的提交物品。E 换到下一个地区
    '声名': Page(((0.62, 0.4, 0.96, 0.6), (0.08, 0.66, 0.92, 0.75)), switch='e'),
}


def red_dots(scr, region=(0, 0, 1, 1)):
    """region 里小红点的中心（比例坐标），从上到下、从左到右。"""
    h, w = scr.img.shape[:2]
    x0, y0, x1, y1 = int(region[0] * w), int(region[1] * h), int(region[2] * w), int(region[3] * h)
    b, g, r = [c.astype(int) for c in cv2.split(scr.img[y0:y1, x0:x1])]
    mask = ((r > 180) & (g < 90) & (b < 90)).astype(np.uint8)
    n, _, stats, centers = cv2.connectedComponentsWithStats(mask)
    lo, hi = DOT_SIZE[0] * w, DOT_SIZE[1] * w
    dots = []
    for (_, _, bw, bh, area), (cx, cy) in zip(stats[1:], centers[1:]):
        if lo <= bw <= hi and lo <= bh <= hi and area >= 0.6 * bw * bh:
            dots.append(((x0 + cx) / w, (y0 + cy) / h))
    return sorted(dots, key=lambda d: (round(d[1], 2), d[0]))


def tile_has_dot(scr, label):
    """主菜单上 label 这个图标右上角有没有红点。"""
    item = scr.first(label, MENU_TILES, exact=True)
    return bool(item) and bool(red_dots(scr, (item['x'], item['y'] - 0.11, item['x'] + 0.06, item['y'] - 0.04)))


def nearest_text(scr, x, y, within=0.05):
    near = [i for i in scr.items if abs(i['x'] - x) <= within and abs(i['y'] - y) <= within]
    return min(near, key=lambda i: (i['x'] - x) ** 2 + (i['y'] - y) ** 2)['t'] if near else ''


class Claimer:
    def __init__(self, nav, log=None):
        self.nav = nav
        self.log = log or (lambda msg: None)

    def run(self, names):
        """依次领 names 里主菜单图标带红点的界面，返回进去过的界面。"""
        self.nav.go(MainMenu())
        scr = self.nav.b.read()
        todo = [n for n in names if tile_has_dot(scr, n)]
        self.log('有红点：%s' % ('、'.join(todo) or '没有'))
        for name in todo:
            # 历练打开的是手册最左边的分区，导航不认这一页，所以从主菜单直接点图标进去
            self.nav.go(MainMenu())
            tile = self.nav.b.read().first(name, MENU_TILES, exact=True)
            if not tile:
                self.log('主菜单上找不到 %s' % name)
                continue
            self.nav.tap(tile['x'], tile['y'] - 0.04)
            self.claim(PAGES[name])
        self.nav.go(World())
        return todo

    def claim(self, page):
        seen = set()
        while True:
            self.claim_here(page)
            if not page.switch:
                return
            seen.add(self.region())
            self.press(page.switch)
            if self.region() in seen:
                return

    def region(self):
        item = self.nav.b.read().items_in(REGION_NAME)
        return item[0]['t'] if item else ''

    def claim_here(self, page):
        taps = {}
        for _ in range(MAX_STEPS):
            scr = self.nav.b.read()
            if scr.find(T.CLOSE_ON_BLANK):
                self.nav.tap(0.5, 0.89)
                continue
            if scr.find(T.CLAIM_ALL, HINT_BAR):
                self.log('  全部领取')
                self.press('space')
                continue
            spot = self.next_dot(scr, page, taps)
            if spot is None:
                return
            key = (round(spot[0], 2), round(spot[1], 2))
            taps[key] = taps.get(key, 0) + 1
            self.log('  点红点 %s' % (nearest_text(scr, *spot) or '(%.2f, %.2f)' % spot))
            self.nav.tap(spot[0] + TAP_OFFSET[0], spot[1] + TAP_OFFSET[1])

    @staticmethod
    def next_dot(scr, page, taps):
        for region in page.dots:
            for x, y in red_dots(scr, region):
                if taps.get((round(x, 2), round(y, 2)), 0) >= MAX_TAPS:
                    continue
                if any(word in nearest_text(scr, x, y) for word in NEVER_TAP):
                    continue
                return x, y
        return None

    def press(self, key):
        before = self.nav.b.thumb()
        self.nav.b.key(key)
        self.nav.b.settle(before)
