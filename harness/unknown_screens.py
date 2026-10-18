"""List the stretches where the navigator kept looking at a screen it did not recognise.

    python -m harness.unknown_screens DATASET_DIR [OUT_DIR] [min_seconds]

Loading screens are unknown for a few seconds as a matter of course, so only stretches of at
least min_seconds (default 12) count. Each one is printed with its session, start time and
length; with OUT_DIR, one full frame per stretch is tiled onto numbered sheets to look at.
A new popup or a changed screen after a game update shows up here first.
"""
import glob
import json
import os
import sys
import time

import cv2
import numpy as np

COLS, ROWS, TILE = 4, 3, (480, 270)


def stretches(root, min_seconds):
    for index in sorted(glob.glob(os.path.join(root, '*', 'labels.jsonl'))):
        session = os.path.dirname(index)
        rows = []
        with open(index, encoding='utf-8') as f:
            for line in f:
                try:
                    row = json.loads(line)
                except ValueError:
                    continue
                if row.get('source') == 'screen':
                    rows.append(row)
        run = []
        for row in rows + [None]:
            if row is not None and row['label'] == 'unknown':
                run.append(row)
                continue
            if run and run[-1]['t'] - run[0]['t'] >= min_seconds:
                full = [r for r in run if r.get('full')]
                pick = full[len(full) // 2] if full else None
                yield {'session': os.path.basename(session), 'start': run[0]['t'],
                       'seconds': round(run[-1]['t'] - run[0]['t']),
                       'after': rows[rows.index(run[0]) - 1]['label'] if rows.index(run[0]) else None,
                       'then': row['label'] if row else None,
                       'frame': os.path.join(session, 'full', pick['file']) if pick else None}
            run = []


def sheets(found, out):
    os.makedirs(out, exist_ok=True)
    per = COLS * ROWS
    for s in range(0, len(found), per):
        sheet = np.zeros((ROWS * TILE[1], COLS * TILE[0], 3), np.uint8)
        for k, item in enumerate(found[s:s + per]):
            img = cv2.imread(item['frame']) if item['frame'] else None
            if img is None:
                continue
            img = cv2.resize(img, TILE)
            cv2.rectangle(img, (0, 0), (50, 24), (0, 0, 0), -1)
            cv2.putText(img, str(s + k), (4, 18), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 1)
            y, x = divmod(k, COLS)
            sheet[y * TILE[1]:(y + 1) * TILE[1], x * TILE[0]:(x + 1) * TILE[0]] = img
        cv2.imwrite(os.path.join(out, 'unknown_%03d.jpg' % (s // per)), sheet, [cv2.IMWRITE_JPEG_QUALITY, 85])


def main():
    root = sys.argv[1]
    out = sys.argv[2] if len(sys.argv) > 2 else None
    min_seconds = float(sys.argv[3]) if len(sys.argv) > 3 else 12
    found = list(stretches(root, min_seconds))
    for n, item in enumerate(found):
        print('%3d %s %s %4ds  after %-12s then %-12s %s' % (
            n, item['session'], time.strftime('%H:%M:%S', time.localtime(item['start'])), item['seconds'],
            item['after'], item['then'], os.path.basename(item['frame'] or '-')))
    print('%d stretches of %gs or more' % (len(found), min_seconds))
    if out:
        sheets(found, out)


if __name__ == '__main__':
    main()
