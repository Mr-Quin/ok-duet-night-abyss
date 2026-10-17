"""Backend that drives the real game through the live control service (service.py)."""
import json
import time
import urllib.error
import urllib.request

import cv2
import numpy as np

from src.nav.backend import Backend

SERVICE = 'http://127.0.0.1:8770'
OCR_WIDTH = 1920
PARK = (0.97, 0.5)


class NotFocused(RuntimeError):
    pass


class LiveBackend(Backend):
    def __init__(self, service=SERVICE):
        self.service = service
        self._ocr = None
        self.client = None

    def _get(self, cmd):
        try:
            with urllib.request.urlopen(self.service + '/' + cmd, timeout=10) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            return dict(json.loads(e.read() or b'{}'), status=e.code)

    def call(self, cmd):
        res = self._get(cmd)
        if res.get('status') == 409:
            # the service refuses input while the game is not the foreground window
            if not self._get('focus').get('foreground'):
                raise NotFocused('the game window is not in the foreground')
            time.sleep(0.3)
            res = self._get(cmd)
        if 'error' in res:
            raise RuntimeError('live service: %s' % res['error'])
        return res

    def size(self):
        if self.client is None:
            self.client = tuple(self.call('status')['client'])
        return self.client

    def raw_frame(self, width, gray=False):
        url = '%s/frame?w=%d%s' % (self.service, width, '&gray=1' if gray else '')
        with urllib.request.urlopen(url, timeout=10) as r:
            shape = tuple(int(v) for v in r.headers['X-Shape'].split(','))
            return np.frombuffer(r.read(), dtype=np.uint8).reshape(shape)

    def frame(self):
        return self.raw_frame(OCR_WIDTH)

    def ocr(self, img):
        if self._ocr is None:
            from onnxocr.onnx_paddleocr import ONNXPaddleOcr
            # the detector shrinks anything longer than det_limit_side_len, which by default
            # (960) turns the enlarged level column into unreadable text
            self._ocr = ONNXPaddleOcr(use_angle_cls=False, use_gpu=False, use_openvino=True,
                                      det_limit_side_len=2000)
        h, w = img.shape[:2]
        items = []
        for box, (text, conf) in (self._ocr.ocr(img)[0] or []):
            if conf < 0.6:
                continue
            xs = [p[0] for p in box]
            ys = [p[1] for p in box]
            items.append({'t': text.strip(), 'x': sum(xs) / 4 / w, 'y': sum(ys) / 4 / h})
        return items

    def _px(self, x, y):
        W, H = self.size()
        return x * W, y * H

    def click(self, x, y):
        px, py = self._px(x, y)
        kx, ky = self._px(*PARK)
        self.call('click?x=%d&y=%d&park_x=%d&park_y=%d' % (px, py, kx, ky))

    def drag(self, x0, y0, x1, y1):
        (a, b), (c, d) = self._px(x0, y0), self._px(x1, y1)
        self.call('drag?x0=%d&y0=%d&x1=%d&y1=%d' % (a, b, c, d))
        self.park()

    def park(self):
        self.call('move?x=%d&y=%d' % self._px(*PARK))

    def key(self, name):
        self.call('key?k=' + name)

    def scroll(self, x, y, notches):
        px, py = self._px(x, y)
        self.call('scroll?x=%d&y=%d&n=%d' % (px, py, notches))

    def thumb(self):
        # the service scales on its side, which is much cheaper than fetching full frames
        t = self.raw_frame(192, gray=True)
        return t[:, :int(t.shape[1] * 0.7)].astype('int16')

    def save_frame(self, path, width=2560):
        img = self.raw_frame(width)
        with open(path, 'wb') as f:
            f.write(cv2.imencode('.png', img)[1].tobytes())
        return img
