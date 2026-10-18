"""Run a trained screen classifier next to the rules inside ok-dna, without acting on it.

Turned on by pointing DNA_SHADOW at the folder train.py wrote. Every phase the run loop
observes is also classified by the model (OpenVINO on the CPU); disagreements and timings go
to shadow.jsonl in that folder, with the frame saved for a look later.
"""
import json
import os
import time

import cv2
import numpy as np

MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)


class Shadow:
    def __init__(self, folder, source='phase'):
        import openvino as ov
        with open(os.path.join(folder, '%s.json' % source), encoding='utf-8') as f:
            meta = json.load(f)
        self.classes, self.size = meta['classes'], tuple(meta['size'])
        self.model = ov.Core().compile_model(os.path.join(folder, '%s.onnx' % source), 'CPU')
        self.folder = os.path.join(folder, 'shadow_%s' % time.strftime('%Y%m%d_%H%M%S'))
        os.makedirs(self.folder, exist_ok=True)
        self.log = open(os.path.join(self.folder, 'shadow.jsonl'), 'a', encoding='utf-8')
        self.count = 0

    def predict(self, frame):
        small = cv2.resize(frame, self.size, interpolation=cv2.INTER_AREA)
        img = cv2.cvtColor(small, cv2.COLOR_BGR2RGB).astype(np.float32) / 255
        x = ((img - MEAN) / STD).transpose(2, 0, 1)[None]
        logits = self.model(x)[0][0]
        p = np.exp(logits - logits.max())
        p /= p.sum()
        k = int(p.argmax())
        return self.classes[k], float(p[k])

    def check(self, frame, rule):
        t0 = time.perf_counter()
        label, confidence = self.predict(frame)
        row = {'t': round(time.time(), 2), 'rule': rule, 'model': label, 'p': round(confidence, 3),
               'ms': round(1000 * (time.perf_counter() - t0), 1)}
        if label != rule:
            name = '%06d.jpg' % self.count
            self.count += 1
            cv2.imwrite(os.path.join(self.folder, name), cv2.resize(frame, (640, 360)), [cv2.IMWRITE_JPEG_QUALITY, 85])
            row['file'] = name
        self.log.write(json.dumps(row, ensure_ascii=False) + '\n')
        self.log.flush()


def install(observer):
    folder = os.environ.get('DNA_SHADOW')
    if not folder:
        return None
    shadow = Shadow(folder)
    look = observer.look

    def shadowed_look(task):
        phase = look(task)
        if task.frame is not None:
            shadow.check(task.frame, phase)
        return phase

    observer.look = shadowed_look
    return shadow
