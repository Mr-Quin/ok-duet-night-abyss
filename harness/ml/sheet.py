"""Contact sheets for checking recorded labels by eye.

    python -m harness.ml.sheet DATASET_DIR OUT_DIR [per_label]

Picks up to per_label frames for every (source, label), spread over the sessions and biased
towards frames next to a label change, and tiles them 6 x 5 per sheet with a number and the
recorded label on each tile. sheets.json maps the numbers back to files, so a reviewer can
write corrections as {"file path": "right label"} into corrections.json in the dataset folder,
which train.py prefers over the recorded label.
"""
import collections
import glob
import json
import os
import random
import sys

import cv2
import numpy as np

COLS, ROWS = 6, 5
TILE = (320, 180)


def rows_of(root):
    for index in sorted(glob.glob(os.path.join(root, '**', 'labels.jsonl'), recursive=True)):
        folder = os.path.dirname(index)
        with open(index, encoding='utf-8') as f:
            rows = [json.loads(line) for line in f]
        for k, r in enumerate(rows):
            r['path'] = os.path.join(folder, r['file'])
            prev = rows[k - 1] if k else None
            nxt = rows[k + 1] if k + 1 < len(rows) else None
            r['edge'] = any(o and o['source'] == r['source'] and o['label'] != r['label'] for o in (prev, nxt))
            yield r


def pick(rows, per_label, seed=1):
    groups = collections.defaultdict(list)
    for r in rows:
        groups[r['source'], r['label']].append(r)
    rng = random.Random(seed)
    chosen = []
    for key, items in sorted(groups.items(), key=lambda kv: str(kv[0])):
        edges = [r for r in items if r['edge']]
        rest = [r for r in items if not r['edge']]
        rng.shuffle(edges)
        rng.shuffle(rest)
        chosen += (edges[:per_label // 2] + rest)[:per_label]
    return chosen


def main():
    root, out = sys.argv[1], sys.argv[2]
    per_label = int(sys.argv[3]) if len(sys.argv) > 3 else 30
    os.makedirs(out, exist_ok=True)
    chosen = pick(list(rows_of(root)), per_label)
    index = []
    for s in range(0, len(chosen), COLS * ROWS):
        sheet = np.zeros((ROWS * TILE[1], COLS * TILE[0], 3), np.uint8)
        for k, r in enumerate(chosen[s:s + COLS * ROWS]):
            img = cv2.imread(r['path'])
            if img is None:
                continue
            img = cv2.resize(img, TILE)
            n = s + k
            text = '%d %s:%s' % (n, r['source'][0], r['label'])
            cv2.rectangle(img, (0, 0), (TILE[0], 22), (0, 0, 0), -1)
            cv2.putText(img, text, (4, 16), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1)
            y, x = divmod(k, COLS)
            sheet[y * TILE[1]:(y + 1) * TILE[1], x * TILE[0]:(x + 1) * TILE[0]] = img
            index.append({'n': n, 'path': os.path.relpath(r['path'], root), 'source': r['source'], 'label': r['label']})
        cv2.imwrite(os.path.join(out, 'sheet_%03d.jpg' % (s // (COLS * ROWS))), sheet, [cv2.IMWRITE_JPEG_QUALITY, 85])
    with open(os.path.join(out, 'sheets.json'), 'w', encoding='utf-8') as f:
        json.dump(index, f, ensure_ascii=False, indent=0)
    print('%d frames on %d sheets' % (len(index), (len(index) + COLS * ROWS - 1) // (COLS * ROWS)))


if __name__ == '__main__':
    main()
