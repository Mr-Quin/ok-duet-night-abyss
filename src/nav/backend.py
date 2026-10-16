"""What the navigator needs from an automation framework: frames, OCR and a few inputs.

Positions are fractions of the game client in both directions, so nothing here depends on
the capture resolution.
"""
import json
import os
import time

import cv2
import numpy as np


class Screen:
    def __init__(self, img, items):
        self.img = img
        # [{'t': text, 'x': centre x, 'y': centre y}]
        self.items = items
        self._gray = None

    @property
    def gray(self):
        if self._gray is None:
            self._gray = cv2.cvtColor(self.img, cv2.COLOR_BGR2GRAY)
        return self._gray

    def find(self, text, region=(0, 0, 1, 1), exact=False):
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
        """Pixels brighter than level; selected labels are drawn white, the rest stay grey."""
        return int((self._crop(x0, y0, x1, y1) > level).sum())

    def brightness(self, x0, y0, x1, y1):
        crop = self._crop(x0, y0, x1, y1)
        return float(crop.mean()) if crop.size else 0.0


class Backend:
    """Subclasses provide frame(), ocr(), click(), key() and scroll()."""

    def frame(self):
        """The current game client image, BGR."""
        raise NotImplementedError

    def ocr(self, img):
        """[{'t', 'x', 'y'}] with x and y as fractions of img."""
        raise NotImplementedError

    def click(self, x, y):
        raise NotImplementedError

    def key(self, name):
        """name is 'esc' or a single letter."""
        raise NotImplementedError

    def scroll(self, x, y, notches):
        """Positive notches scroll up, like the mouse wheel."""
        raise NotImplementedError

    def sleep(self, seconds):
        time.sleep(seconds)

    def read(self):
        img = self.frame()
        return Screen(img, self.ocr(img))

    def dump(self, folder, name):
        """Save the current frame and its OCR items, for looking into a failure afterwards."""
        os.makedirs(folder, exist_ok=True)
        scr = self.read()
        stem = os.path.join(folder, name)
        with open(stem + '.png', 'wb') as f:
            f.write(cv2.imencode('.png', scr.img)[1].tobytes())
        with open(stem + '.json', 'w', encoding='utf-8') as f:
            json.dump(scr.items, f, ensure_ascii=False, indent=1)
        return stem

    def thumb(self):
        img = self.frame()
        small = cv2.resize(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), (192, 108), interpolation=cv2.INTER_AREA)
        # left 70% only: the character model on the right idles constantly
        return small[:, :134].astype('int16')

    def settle(self, before, change_timeout=0.7, stable_timeout=2.5):
        """Wait for the screen to react to an action and then stop animating."""
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
