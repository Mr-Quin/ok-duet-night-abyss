"""Navigator backend on top of an ok-script task."""
import os

from src.nav.backend import Backend

# where the cursor waits between clicks: hovered tabs and rows are highlighted much like
# selected ones, which would fool the selection checks
PARK = (0.97, 0.5)
ROWS_PATH = os.path.join('configs', 'nav_rows.json')


class OkScriptBackend(Backend):
    def __init__(self, task, ocr_height=1080, threshold=0.6):
        self.task = task
        self.ocr_height = ocr_height
        self.threshold = threshold

    def frame(self):
        return self.task.next_frame()

    def ocr(self, img):
        h, w = img.shape[:2]
        # target_height is absolute, so scale it to this image: a full frame shrinks to ocr_height,
        # an enlarged crop keeps its enlargement
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

    def sleep(self, seconds):
        self.task.sleep(seconds)
