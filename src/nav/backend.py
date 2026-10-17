"""导航层对自动化框架的全部依赖：截图、OCR 和几种输入。

坐标一律用占游戏画面宽高的比例（0~1），和截图分辨率无关。接入新框架只需要实现
`Backend` 的五个方法，ok-script 的实现见 okscript.py。
"""
import time

import cv2
import numpy as np


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

    def find(self, text, region=(0, 0, 1, 1), exact=False):
        """region 内包含（exact 时等于）text 的文字，按从上到下、从左到右排序。"""
        x0, y0, x1, y1 = region
        hits = [i for i in self.items if x0 <= i['x'] <= x1 and y0 <= i['y'] <= y1
                and (i['t'] == text if exact else text in i['t'])]
        return sorted(hits, key=lambda i: (i['y'], i['x']))

    def find_any(self, texts, region=(0, 0, 1, 1)):
        return [hit for t in texts for hit in self.find(t, region)]

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
        """放大后单独识别画面的一部分；整帧 OCR 漏掉的小字这样能读出来。"""
        H, W = scr.img.shape[:2]
        crop = scr.img[int(y0 * H):int(y1 * H), int(x0 * W):int(x1 * W)]
        crop = cv2.resize(crop, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
        return [dict(i, x=x0 + i['x'] * (x1 - x0), y=y0 + i['y'] * (y1 - y0)) for i in self.ocr(crop)]

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
