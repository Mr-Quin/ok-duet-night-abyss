"""导航层对自动化框架的全部依赖：截图、OCR 和几种输入。

坐标一律用占游戏画面宽高的比例（0~1），和截图分辨率无关。接入新框架只需要实现
`Backend` 的抽象方法，ok-script 的实现见 okscript.py。
"""
import re
import time

import cv2
import numpy as np

# 默认 OCR 检测会把长边超过这个的图缩小
OCR_MAX_SIDE = 960


class Screen:
    """一帧画面和它的 OCR 结果。items 是 [{'t': 文字, 'x': 中心 x, 'y': 中心 y}]，坐标为比例。"""

    def __init__(self, img, items):
        self.img = img
        self.items = items
        self._gray = None

    @property
    def gray(self):
        if self._gray is None:
            self._gray = cv2.cvtColor(self.img, cv2.COLOR_BGR2GRAY)
        return self._gray

    def items_in(self, region=(0, 0, 1, 1), pred=None):
        """region 内（pred 为真）的文字，按从上到下、从左到右排序。"""
        x0, y0, x1, y1 = region
        hits = [i for i in self.items if x0 <= i['x'] <= x1 and y0 <= i['y'] <= y1 and (pred is None or pred(i))]
        return sorted(hits, key=lambda i: (i['y'], i['x']))

    def find(self, text, region=(0, 0, 1, 1), exact=False):
        """region 内包含（exact 时等于）text 的文字。"""
        return self.items_in(region, lambda i: i['t'] == text if exact else text in i['t'])

    def first(self, text, region=(0, 0, 1, 1), exact=False):
        hits = self.find(text, region, exact)
        return hits[0] if hits else None

    def match(self, pattern, region=(0, 0, 1, 1), text=''):
        """region 内第一个含 text、又匹配 pattern 的 (文字, re.Match)，按 OCR 的顺序；没有时为 None。"""
        x0, y0, x1, y1 = region
        for i in self.items:
            if x0 <= i['x'] <= x1 and y0 <= i['y'] <= y1 and text in i['t']:
                m = re.search(pattern, i['t'])
                if m:
                    return i, m
        return None

    def has_any(self, texts, region=(0, 0, 1, 1)):
        return any(self.find(t, region) for t in texts)

    def _crop(self, x0, y0, x1, y1):
        H, W = self.gray.shape
        return self.gray[int(y0 * H):int(y1 * H), int(x0 * W):int(x1 * W)]

    def lit(self, x0, y0, x1, y1, level=200):
        """区域内亮度超过 level 的像素占比。选中的标签是白字，未选中的是灰字，不会过 200。"""
        crop = self._crop(x0, y0, x1, y1)
        return float((crop > level).mean()) if crop.size else 0.0

    def brightness(self, x0, y0, x1, y1):
        crop = self._crop(x0, y0, x1, y1)
        return float(crop.mean()) if crop.size else 0.0


class Backend:
    """子类实现 frame / ocr / click / key / scroll，其余方法有通用实现。"""

    def frame(self):
        """当前游戏画面，BGR。"""
        raise NotImplementedError

    def ocr(self, img):
        """img 上的文字，[{'t', 'x', 'y'}]，坐标为占 img 的比例。"""
        raise NotImplementedError

    def click(self, x, y):
        raise NotImplementedError

    def key(self, name):
        """name 为 'esc' 或单个字母。"""
        raise NotImplementedError

    def scroll(self, x, y, notches):
        """notches 为正时向上滚，和鼠标滚轮一致。"""
        raise NotImplementedError

    def drag(self, x0, y0, x1, y1):
        """按住左键从 (x0, y0) 拖到 (x1, y1) 再松开。"""
        raise NotImplementedError

    def park(self):
        """把鼠标移到不会悬停到按钮的地方；悬停的页签和行看起来和选中一样。"""

    def sleep(self, seconds):
        time.sleep(seconds)

    def read(self):
        img = self.frame()
        return Screen(img, self.ocr(img))

    def ocr_region(self, scr, x0, y0, x1, y1, scale=2.0):
        """放大后单独识别画面的一部分；整帧 OCR 漏掉的小字这样能读出来。

        OCR 会把长边超过 OCR_MAX_SIDE 的图整张缩小，又高又窄的一条（比如夜航手册的等级栏）
        放大后反而被缩没了，所以按长边切成互相重叠的几块分别识别。
        """
        H, W = scr.img.shape[:2]
        crop = scr.img[int(y0 * H):int(y1 * H), int(x0 * W):int(x1 * W)]
        crop = cv2.resize(crop, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
        h, w = crop.shape[:2]
        tall, length = h >= w, max(h, w)
        starts = list(range(0, max(1, length - OCR_MAX_SIDE + 1), int(OCR_MAX_SIDE * 0.8)))
        if starts[-1] + OCR_MAX_SIDE < length:
            starts.append(length - OCR_MAX_SIDE)
        items = []
        for s in starts:
            tile = crop[s:s + OCR_MAX_SIDE] if tall else crop[:, s:s + OCR_MAX_SIDE]
            th, tw = tile.shape[:2]
            for i in self.ocr(tile):
                cx = (i['x'] * tw + (0 if tall else s)) / w
                cy = (i['y'] * th + (s if tall else 0)) / h
                # 重叠的地方会读到两次
                if any(o['t'] == i['t'] and abs(o['x'] - cx) < 0.02 and abs(o['y'] - cy) < 0.02 for o in items):
                    continue
                items.append(dict(i, x=cx, y=cy))
        return [dict(i, x=x0 + i['x'] * (x1 - x0), y=y0 + i['y'] * (y1 - y0)) for i in items]

    def thumb(self):
        """用来判断画面是否还在变化的小灰度图。"""
        img = self.frame()
        small = cv2.resize(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), (192, 108), interpolation=cv2.INTER_AREA)
        # 只取左侧 70%：右边的角色模型一直在做待机动作
        return small[:, :134].astype('int16')

    def settle(self, before, change_timeout=0.7, stable_timeout=2.5):
        """等画面对操作做出反应、再等动画停下。画面一直没变时返回 False。"""
        t0 = time.perf_counter()
        prev, changed = before, False
        while time.perf_counter() - t0 < change_timeout + stable_timeout:
            self.sleep(0.06)
            cur = self.thumb()
            if not changed:
                changed = np.abs(cur - before).mean() > 4
                if not changed and time.perf_counter() - t0 > change_timeout:
                    break
            elif np.abs(cur - prev).mean() < 1.5:
                break
            prev = cur
        return changed
