"""Walk to the defence objective by following its on-screen marker.

In the 30/65 defence the player spawns facing the objective, so the walk is a straight run:
hold forward and sprint, nudge sideways when the marker drifts off centre, and stop once its
distance label reads a few metres.
"""
import os
import re
import time

import cv2

TEMPLATE = os.path.join(os.path.dirname(__file__), 'marker', 'objective.png')
# the template was cut from a 2560-wide frame
TEMPLATE_WIDTH = 2560
ARRIVED_METRES = 6


class MarkerWalk:
    def __init__(self, task):
        self.task = task
        self.template = cv2.imread(TEMPLATE)

    def find(self, frame):
        """(x offset from centre in [-1, 1], distance in metres or None), or None when no marker is seen."""
        H, W = frame.shape[:2]
        s = W / TEMPLATE_WIDTH
        y0, y1, x0 = int(0.08 * H), int(0.78 * H), int(0.2 * W)
        roi = frame[y0:y1, x0:]
        best = (-1.0, None, None)
        # the marker shrinks with distance
        for scale in (0.6, 0.8, 1.0):
            t = cv2.resize(self.template, None, fx=scale * s, fy=scale * s, interpolation=cv2.INTER_AREA)
            res = cv2.matchTemplate(roi, t, cv2.TM_CCOEFF_NORMED)
            _, score, _, loc = cv2.minMaxLoc(res)
            if score > best[0]:
                best = (score, (loc[0] + t.shape[1] // 2 + x0, loc[1] + t.shape[0] // 2 + y0), t.shape)
        score, centre, _ = best
        if score < 0.8:
            return None
        cx, cy = centre
        # the distance label sits just under the marker, e.g. 51米
        label = frame[cy + int(16 * s):cy + int(60 * s), max(0, cx - int(80 * s)):cx + int(80 * s)]
        boxes = self.task.ocr(frame=label, threshold=0.5) if label.size else []
        m = re.search(r'(\d+)\s*米', ''.join(b.name for b in boxes))
        return (cx - W / 2) / (W / 2), int(m.group(1)) if m else None

    def wait_for_marker(self, timeout=6):
        deadline = time.time() + timeout
        while time.time() < deadline:
            seen = self.find(self.task.next_frame())
            if seen:
                return seen
            self.task.sleep(0.2)
        return None

    def run(self, timeout=30):
        """Walk to the objective; False when the marker was lost or never reached."""
        task = self.task
        seen = self.wait_for_marker()
        if not seen:
            task.log_info("没找到目标标记")
            return False
        task.log_info(f"按标记直线走，距离 {seen[1]} 米")
        dodge = task.get_dodge_key()
        task.send_key_down('w')
        task.send_key_down(dodge)
        try:
            deadline, lost_since = time.time() + timeout, None
            while time.time() < deadline:
                seen = self.find(task.next_frame())
                if seen is None:
                    lost_since = lost_since or time.time()
                    if time.time() - lost_since > 3:
                        task.log_info("目标标记丢失")
                        return False
                    continue
                lost_since = None
                x, metres = seen
                if metres is not None and metres <= ARRIVED_METRES:
                    task.log_info(f"已到达目标，距离 {metres} 米")
                    return True
                if abs(x) > 0.05:
                    task.send_key('d' if x > 0 else 'a', down_time=0.08)
            task.log_info("走到目标超时")
            return False
        finally:
            task.send_key_up(dodge)
            task.send_key_up('w')
