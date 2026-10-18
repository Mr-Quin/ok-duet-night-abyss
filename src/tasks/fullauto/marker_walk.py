"""跟着屏幕上的目标标记走到扼守的防守点。

按住前进和冲刺，转镜头让标记保持在画面中央，标记下方的距离读到几米以内就停。距离一阵子
不变小就跳一下，跳了两次还不行就放弃，交给调用方复位。走的过程会记成一条时间线
（steps），走到了可以存成路线，下次从同一个出生点直接重放。
"""
import os
import re
import time

import cv2

TEMPLATE = os.path.join(os.path.dirname(__file__), 'marker', 'objective.png')
# 模板是从 2560 宽的画面上截的
TEMPLATE_WIDTH = 2560
ARRIVED_METRES = 6
# 镜头横移一格，标记在画面上挪大约 0.003 个画面宽（转得多了会少一点），一次最多转这么多格
TURN_PER_COUNT = 0.003
MAX_TURN = 150
STEER = 0.03
# 距离这么久没变小就当作被挡住了
STUCK_SECONDS = 2.5
MAX_JUMPS = 2
# 冲刺实测最快约 9 米/秒；距离一下子少得比这还多是 OCR 读错了（比如把 35 读成 3）
MAX_SPEED = 15
MAX_METRES = 500
DODGE_DELAY = 0.1


class MarkerWalk:
    def __init__(self, task, clock=time.time):
        self.task = task
        self.clock = clock
        self.template = cv2.imread(TEMPLATE)
        self.last_y = None
        self.steps = []
        self.t0 = None

    def find(self, frame):
        """(标记相对中央的水平偏移 [-1, 1], 距离米数或 None)，看不到标记时返回 None。"""
        H, W = frame.shape[:2]
        s = W / TEMPLATE_WIDTH
        y0, y1, x0 = int(0.08 * H), int(0.78 * H), int(0.2 * W)
        roi = frame[y0:y1, x0:]
        best = (-1.0, None)
        # 距离越远标记越小
        for scale in (0.6, 0.8, 1.0):
            t = cv2.resize(self.template, None, fx=scale * s, fy=scale * s, interpolation=cv2.INTER_AREA)
            res = cv2.matchTemplate(roi, t, cv2.TM_CCOEFF_NORMED)
            _, score, _, loc = cv2.minMaxLoc(res)
            if score > best[0]:
                best = (score, (loc[0] + t.shape[1] // 2 + x0, loc[1] + t.shape[0] // 2 + y0))
        score, centre = best
        if score < 0.8:
            return None
        cx, cy = centre
        self.last_y = cy / H
        # 距离文字就在标记正下方，比如「51米」
        label = frame[cy + int(16 * s):cy + int(60 * s), max(0, cx - int(80 * s)):cx + int(80 * s)]
        boxes = self.task.ocr(frame=label, threshold=0.5) if label.size else []
        m = re.search(r'(\d+)\s*米', ''.join(b.name for b in boxes))
        metres = int(m.group(1)) if m else None
        # 旁边的数字会被一起读进来，比如 16127
        if metres is not None and metres > MAX_METRES:
            metres = None
        return (cx - W / 2) / (W / 2), metres

    def wait_for_marker(self, timeout=6):
        deadline = self.clock() + timeout
        while self.clock() < deadline:
            seen = self.find(self.task.next_frame())
            if seen:
                return seen
            self.task.sleep(0.2)
        return None

    def run(self, seen, timeout=30, arrive=ARRIVED_METRES):
        """从 wait_for_marker() 看到标记的位置出发走到目标点；走到返回 True，被挡住、标记丢失或超时返回 False。

        再调一次会接着记在同一条时间线上。
        """
        task = self.task
        task.log_info(f"按标记走，距离 {seen[1]} 米")
        dodge = task.get_dodge_key()
        t0 = self.clock()
        if not self.steps:
            self.t0 = t0
        self.record({'down': 'w'})
        task.send_key_down('w')
        try:
            # 闪避键不带方向按下是向后撤，要等前进键先生效
            task.sleep(DODGE_DELAY)
            self.record({'down': dodge})
            task.send_key_down(dodge)
            lost_since, best, best_at, jumps = None, None, self.clock(), 0
            last_metres, last_at = seen[1], self.clock()
            while self.clock() - t0 < timeout:
                frame = task.next_frame()
                seen = self.find(frame)
                if seen is None:
                    lost_since = lost_since or self.clock()
                    if self.clock() - lost_since > 3:
                        # 进了防守范围波次一开始，标记就不显示了
                        if last_metres is not None and last_metres <= ARRIVED_METRES:
                            task.log_info(f"标记在 {last_metres} 米处消失，当作到了")
                            return True
                        task.log_info("目标标记丢失")
                        task.screenshot("walk_lost", frame)
                        return False
                    continue
                lost_since = None
                x, metres = seen
                if metres is not None and last_metres is not None and \
                        last_metres - metres > MAX_SPEED * (self.clock() - last_at) + 2:
                    metres = None
                if metres is not None:
                    last_metres, last_at = metres, self.clock()
                if metres is not None and metres <= arrive:
                    task.log_info(f"已到达目标，距离 {metres} 米，用时 {self.clock() - t0:.1f} 秒")
                    return True
                if metres is not None and (best is None or metres < best):
                    best, best_at = metres, self.clock()
                elif self.clock() - best_at > STUCK_SECONDS:
                    if jumps >= MAX_JUMPS:
                        task.log_info(f"被挡住了，停在 {best} 米")
                        task.screenshot("walk_blocked", frame)
                        return False
                    jumps += 1
                    self.record({'down': 'space'})
                    task.send_key('space', down_time=0.1)
                    self.record({'up': 'space'})
                    best_at = self.clock()
                if abs(x) > STEER:
                    dx = max(-MAX_TURN, min(MAX_TURN, round(x / TURN_PER_COUNT)))
                    self.record({'turn': [dx, 0]})
                    task.move_mouse_relative(dx, 0)
            task.log_info("走到目标超时")
            return False
        finally:
            task.send_key_up(dodge)
            task.send_key_up('w')
            self.record({'up': dodge})
            self.record({'up': 'w'})

    def record(self, step):
        self.steps.append(dict(step, t=round(self.clock() - self.t0, 3)))
