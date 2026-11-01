import os
import cv2
import numpy as np
from ok.test.TaskTestCase import TaskTestCase
from src.config import config
from src.nav import screens as S
from src.nav.okscript import OkScriptBackend
from src.tasks.fullauto.AutoNightbookTask import AutoNightbookTask
from harness import privacy

FRAMES = r'C:\Users\H\projects\dna-nav\sessions\20261019-043715\frames'
OUT = r'C:\Users\H\projects\ok-dna-fork\tests\images\letter'
NAV = {'000050': 'letter_tab.png', '000085': 'letter_start.png'}
KEEP = {
    '000100': ('letter_popup.png', [(0.44, 0.3, 0.51, 0.36), (0.445, 0.36, 0.505, 0.5), (0.5, 0.6, 0.9, 0.68)]),
    '000290': ('explore_prompt.png', [(0.55, 0.45, 0.85, 0.55)]),
    '000294': ('explore_quick_solve.png', [(0.75, 0.82, 0.95, 0.91)]),
    '000301': ('explore_solved.png', [(0.6, 0.45, 0.85, 0.55), (0.75, 0.82, 0.95, 0.91)]),
}


def keep_only(img, boxes):
    H, W = img.shape[:2]
    out = np.zeros_like(img)
    for x0, y0, x1, y1 in boxes:
        sl = slice(int(y0 * H), int(y1 * H)), slice(int(x0 * W), int(x1 * W))
        out[sl] = img[sl]
    return out


class Make(TaskTestCase):
    task_class = AutoNightbookTask
    config = config

    def test_make(self):
        os.makedirs(OUT, exist_ok=True)
        for name, out in NAV.items():
            path = os.path.join(FRAMES, name + '.jpg')
            self.set_image(path)
            scr = OkScriptBackend(self.task).read()
            screen, info = S.classify(scr, S.load_atlas())
            img = cv2.imread(path)
            masked, _ = privacy.mask(img, [], screen, info)
            cv2.imwrite(os.path.join(OUT, out), masked)
            print('made', out, screen)
        for name, (out, boxes) in KEEP.items():
            img = cv2.imread(os.path.join(FRAMES, name + '.jpg'))
            cv2.imwrite(os.path.join(OUT, out), keep_only(img, boxes))
            print('made', out)
