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

from harness.sheets import tile


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
    chosen = pick(list(rows_of(root)), per_label)
    count = tile([(r['path'], '%d %s:%s' % (n, r['source'][0], r['label'])) for n, r in enumerate(chosen)],
                 out, 'sheet')
    index = [{'n': n, 'path': os.path.relpath(r['path'], root), 'source': r['source'], 'label': r['label']}
             for n, r in enumerate(chosen)]
    with open(os.path.join(out, 'sheets.json'), 'w', encoding='utf-8') as f:
        json.dump(index, f, ensure_ascii=False, indent=0)
    print('%d frames on %d sheets' % (len(index), count))


if __name__ == '__main__':
    main()
