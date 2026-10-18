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

from harness.sheets import tile


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
        tile([(item['frame'], str(n)) for n, item in enumerate(found) if item['frame']], out, 'unknown',
             cols=4, rows=3, size=(480, 270))


if __name__ == '__main__':
    main()
