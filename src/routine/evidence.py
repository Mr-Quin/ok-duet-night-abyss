"""流程每跑一次留一个文件夹：每个检查点一行记录和一张当时的游戏画面，事后能看出到底做了什么。

放在 logs/runs 下（logs 不进 git），只留最新的 KEEP 个。
"""
import os
import shutil
import time

import cv2

ROOT = os.path.join('logs', 'runs')
KEEP = 30
WIDTH = 1280


class Evidence:

    def __init__(self, root=ROOT, keep=KEEP, clock=time.localtime):
        self.clock = clock
        os.makedirs(root, exist_ok=True)
        stamp = time.strftime('%Y%m%d-%H%M%S', clock())
        self.folder = os.path.join(root, stamp)
        n = 1
        while os.path.exists(self.folder):
            n += 1
            self.folder = os.path.join(root, f'{stamp}-{n}')
        os.makedirs(self.folder)
        self.count = 0
        prune(root, keep)

    def record(self, slug, text, frame=None):
        self.count += 1
        line = f'{time.strftime("%H:%M:%S", self.clock())} {self.count:02d} {text}'
        if frame is not None:
            name = f'{self.count:02d}-{slug}.jpg'
            if save_jpg(os.path.join(self.folder, name), frame):
                line += f'  [{name}]'
        with open(os.path.join(self.folder, 'report.txt'), 'a', encoding='utf-8') as f:
            f.write(line + '\n')


def save_jpg(path, frame):
    h, w = frame.shape[:2]
    if w > WIDTH:
        frame = cv2.resize(frame, (WIDTH, round(h * WIDTH / w)), interpolation=cv2.INTER_AREA)
    ok, data = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
    if ok:
        # cv2.imwrite 写不了带中文的路径，自己写字节
        with open(path, 'wb') as f:
            f.write(data.tobytes())
    return ok


def prune(root, keep):
    runs = sorted(d for d in os.listdir(root) if os.path.isdir(os.path.join(root, d)))
    for old in runs[:-keep]:
        shutil.rmtree(os.path.join(root, old), ignore_errors=True)


def checkpoint(task, slug, text, notify=False):
    """写日志；task 在流程里跑时再记一笔，单独跑任务时没有 evidence 就只写日志。记录出错不影响任务本身。"""
    if notify:
        task.log_info(text, notify=True)
    else:
        task.log_info(text)
    evidence = getattr(task, 'evidence', None)
    if evidence is None:
        return
    try:
        evidence.record(slug, text, getattr(task, 'frame', None))
    except Exception as e:
        task.log_info(f'记录检查点出错：{e}')
