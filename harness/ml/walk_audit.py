"""Check the defence walker's marker and distance reading against a reviewer's eye.

    python -m harness.ml.walk_audit DATASET_DIR OUT_DIR [samples]
    python -m harness.ml.walk_audit score OUT_DIR

Samples walker looks recorded by harness/dataset.py (crop around the marker plus what the walker
read), spread over sessions, and tiles them 8 x 5 per sheet with only a number on each tile.
A reviewer writes truth.json: {"number": metres as an int, or "none" when no marker is
visible, or "?" when the distance cannot be read}. Scoring reports, for the walker's reading:
correct distance, wrong distance (and how far off), marker missed, and marker seen where
there is none. Wrong distances that are much smaller than the truth are the dangerous ones
(false arrival).
"""
import collections
import glob
import json
import os
import random
import sys

import cv2
import numpy as np

COLS, ROWS, TILE = 8, 5, (240, 135)


def looks(root):
    for index in sorted(glob.glob(os.path.join(root, '**', 'walk', 'walk.jsonl'), recursive=True)):
        folder = os.path.dirname(index)
        with open(index, encoding='utf-8') as f:
            for line in f:
                row = json.loads(line)
                row['path'] = os.path.join(folder, row['file'])
                yield row


def score(out):
    key = json.load(open(os.path.join(out, 'key.json'), encoding='utf-8'))
    truth = json.load(open(os.path.join(out, 'truth.json'), encoding='utf-8'))
    tally, off = collections.Counter(), []
    for n, row in key.items():
        t = truth.get(n)
        if t is None or t == '?':
            continue
        read = row['metres'] if row['seen'] else 'none'
        if t == 'none':
            tally['no marker, walker saw none' if read == 'none' else 'no marker, walker saw one'] += 1
        elif read == 'none':
            tally['marker missed'] += 1
        elif read is None:
            tally['marker seen, distance unread'] += 1
        elif read == t:
            tally['distance right'] += 1
        else:
            tally['distance wrong'] += 1
            off.append((t, read))
    for k, v in sorted(tally.items()):
        print('  %-32s %d' % (k, v))
    for t, read in off:
        print('  truth %s read %s%s' % (t, read, '  <- false arrival risk' if read < t / 2 else ''))


def main():
    if sys.argv[1] == 'score':
        return score(sys.argv[2])
    root, out = sys.argv[1], sys.argv[2]
    samples = int(sys.argv[3]) if len(sys.argv) > 3 else 200
    os.makedirs(out, exist_ok=True)
    rows = list(looks(root))
    random.Random(5).shuffle(rows)
    rows = rows[:samples]
    key = {}
    for s in range(0, len(rows), COLS * ROWS):
        sheet = np.zeros((ROWS * TILE[1], COLS * TILE[0], 3), np.uint8)
        for k, r in enumerate(rows[s:s + COLS * ROWS]):
            n = s + k
            img = cv2.imread(r['path'])
            if img is None:
                continue
            img = cv2.resize(img, TILE)
            cv2.rectangle(img, (0, 0), (44, 20), (0, 0, 0), -1)
            cv2.putText(img, str(n), (3, 15), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1)
            y, x = divmod(k, COLS)
            sheet[y * TILE[1]:(y + 1) * TILE[1], x * TILE[0]:(x + 1) * TILE[0]] = img
            key[str(n)] = {'path': os.path.relpath(r['path'], root), 'seen': r['seen'], 'metres': r['metres']}
        cv2.imwrite(os.path.join(out, 'walk_%03d.jpg' % (s // (COLS * ROWS))), sheet, [cv2.IMWRITE_JPEG_QUALITY, 90])
    with open(os.path.join(out, 'key.json'), 'w', encoding='utf-8') as f:
        json.dump(key, f, ensure_ascii=False, indent=0)
    print('%d walker looks available, %d on sheets' % (len(list(looks(root))), len(key)))


if __name__ == '__main__':
    main()
