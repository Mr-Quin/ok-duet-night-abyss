"""Save small labelled frames while ok-dna runs, for training perception models offline.

Turned on by pointing DNA_DATASET at a folder. The nightbook task then wraps the run loop's
phase observer and the navigator's screen classifier, so every look the code already makes
is saved with the label the rule-based code gave it. Frames show the UID and chat, so the
folder stays on the game PC and out of git.
"""
import json
import os
import time

import cv2

from harness import privacy

SIZE = (320, 180)
# at most this often per label source; the loop looks several times a second
EVERY = 0.5
# full-size frames for replaying the rule-based detectors offline: on every label change, and
# now and then while the label stays the same
FULL_EVERY = 10
# blanked before anything is written, with the same boxes the world recorder uses
MASKS = [privacy.UID, privacy.CHAT]


def masked(frame):
    out = frame.copy()
    H, W = out.shape[:2]
    for x0, y0, x1, y1 in MASKS:
        out[int(y0 * H):int(y1 * H), int(x0 * W):int(x1 * W)] = 0
    return out


class Dataset:
    def __init__(self, root):
        self.dir = os.path.join(root, time.strftime('%Y%m%d_%H%M%S'))
        os.makedirs(os.path.join(self.dir, 'full'), exist_ok=True)
        self.index = open(os.path.join(self.dir, 'labels.jsonl'), 'a', encoding='utf-8')
        self.last = {}
        self.last_full = {}
        self.count = 0

    def save(self, frame, source, label, **extra):
        now = time.time()
        if frame is None or now - self.last.get(source, 0) < EVERY:
            return
        self.last[source] = now
        name = '%06d.jpg' % self.count
        self.count += 1
        frame = masked(frame)
        small = cv2.resize(frame, SIZE, interpolation=cv2.INTER_AREA)
        cv2.imwrite(os.path.join(self.dir, name), small, [cv2.IMWRITE_JPEG_QUALITY, 85])
        row = dict(file=name, t=round(now, 2), source=source, label=label, **extra)
        seen_label, seen_at = self.last_full.get(source, (None, 0))
        if label != seen_label or now - seen_at >= FULL_EVERY:
            self.last_full[source] = (label, now)
            cv2.imwrite(os.path.join(self.dir, 'full', name), frame, [cv2.IMWRITE_JPEG_QUALITY, 90])
            row['full'] = True
        self.index.write(json.dumps(row, ensure_ascii=False) + '\n')
        self.index.flush()


# the functions as they were before any task run wrapped them; a second run in the same
# process must wrap these again, not the previous run's wrappers
_ORIGINALS = {}


def _original(owner, name):
    return _ORIGINALS.setdefault((owner, name), getattr(owner, name))


def install(observer):
    """Record the observer's phases and the navigator's screens; does nothing unless DNA_DATASET is set."""
    root = os.environ.get('DNA_DATASET')
    if not root:
        return None
    dataset = Dataset(root)
    look = observer.look

    def recording_look(task):
        phase = look(task)
        # live: the loop has confirmed a run is going (navigator checked), so in_run here is not the open world
        loop = getattr(dataset, 'loop', None)
        dataset.save(task.frame, 'phase', phase, live=bool(loop and loop.live))
        return phase

    observer.look = recording_look

    from src.nav import graph
    classify = _original(graph, 'classify')

    def recording_classify(scr, atlas):
        screen, info = classify(scr, atlas)
        plain = {k: v for k, v in info.items() if isinstance(v, (str, int, float, bool, type(None)))}
        dataset.save(scr.img, 'screen', screen, info=plain)
        return screen, info

    graph.classify = recording_classify

    # what the defence walker sees: a crop around where it found the marker, and what it read there
    from src.tasks.fullauto import marker_walk
    walk_dir = os.path.join(dataset.dir, 'walk')
    os.makedirs(walk_dir, exist_ok=True)
    walk_index = open(os.path.join(walk_dir, 'walk.jsonl'), 'a', encoding='utf-8')
    find = _original(marker_walk.MarkerWalk, 'find')

    def recording_find(walker, frame):
        seen = find(walker, frame)
        if frame is not None:
            H, W = frame.shape[:2]
            name = '%06d.jpg' % dataset.count
            dataset.count += 1
            if seen:
                cx, cy = int((seen[0] + 1) * W / 2), int(walker.last_y * H)
            else:
                cx, cy = W // 2, int(0.4 * H)
            x0, y0 = max(0, cx - int(0.08 * W)), max(0, cy - int(0.08 * H))
            crop = frame[y0:cy + int(0.08 * H), x0:cx + int(0.08 * W)]
            cv2.imwrite(os.path.join(walk_dir, name), crop, [cv2.IMWRITE_JPEG_QUALITY, 90])
            row = {'file': name, 't': round(time.time(), 2), 'seen': seen is not None,
                   'x': None if not seen else round(seen[0], 4), 'y': walker.last_y, 'metres': None if not seen else seen[1],
                   'crop_origin': [x0 / W, y0 / H]}
            walk_index.write(json.dumps(row) + '\n')
            walk_index.flush()
        return seen

    marker_walk.MarkerWalk.find = recording_find
    return dataset
