"""基于 ok-script 任务的导航后端。"""
import os

from src.nav.backend import Backend

# 鼠标在两次点击之间停在这里：悬停的页签和行会高亮得和选中差不多，干扰选中判断
PARK = (0.97, 0.5)
CACHE_PATH = os.path.join('configs', 'nav_cache.json')


class OkScriptBackend(Backend):
    def __init__(self, task, ocr_height=1080, threshold=0.6):
        self.task = task
        self.ocr_height = ocr_height
        self.threshold = threshold

    def frame(self):
        return self.task.next_frame()

    def ocr(self, img):
        h, w = img.shape[:2]
        # target_height 是绝对高度，按游戏窗口高度换算：整帧缩到 ocr_height，放大过的局部保持放大
        target = int(h * self.ocr_height / self.task.height)
        boxes = self.task.ocr(frame=img, target_height=target, threshold=self.threshold)
        return [{'t': b.name.strip(), 'x': (b.x + b.width / 2) / w, 'y': (b.y + b.height / 2) / h}
                for b in boxes if b.name and b.name.strip()]

    def click(self, x, y):
        self.task.click_relative(x, y)
        self.task.sleep(0.15)
        self.park()

    def park(self):
        self.task.move_relative(*PARK)

    def key(self, name):
        self.task.send_key(name)

    def scroll(self, x, y, notches):
        step = 1 if notches > 0 else -1
        for _ in range(abs(notches)):
            self.task.scroll_relative(x, y, step)
            self.task.sleep(0.015)

    def drag(self, x0, y0, x1, y1):
        self.task.swipe_relative(x0, y0, x1, y1, duration=0.4)
        self.park()

    def sleep(self, seconds):
        self.task.sleep(seconds)
