"""Blind audit of a trained classifier against the recorded labels.

    python -m harness.ml.audit DATASET_DIR SOURCE MODEL_DIR OUT_DIR [agreements]

Predicts the held-out frames (train.py's split) with the saved checkpoint, then tiles every
disagreement plus a random sample of agreements onto numbered sheets showing neither label.
key.json keeps, per number, the recorded label and the prediction, so a reviewer can write
the true label per number into truth.json and score both afterwards:

    python -m harness.ml.audit score OUT_DIR
"""
import collections
import json
import os
import random
import sys

import cv2
import numpy as np
import torch

from harness.ml.train import load, model_for, tensor

COLS, ROWS, TILE = 6, 5, (320, 180)


def predict(model_dir, source, items):
    ck = torch.load(os.path.join(model_dir, '%s.pt' % source), map_location='cpu')
    net = model_for(len(ck['classes']))
    net.load_state_dict(ck['state'])
    net.eval()
    out = []
    with torch.no_grad():
        for k in range(0, len(items), 64):
            x = torch.stack([tensor(p) for p, _ in items[k:k + 64]])
            out += [ck['classes'][i] for i in net(x).argmax(1).tolist()]
    return out


def sheets(items, out):
    for s in range(0, len(items), COLS * ROWS):
        sheet = np.zeros((ROWS * TILE[1], COLS * TILE[0], 3), np.uint8)
        for k, (n, path) in enumerate(items[s:s + COLS * ROWS]):
            img = cv2.resize(cv2.imread(path), TILE)
            cv2.rectangle(img, (0, 0), (60, 22), (0, 0, 0), -1)
            cv2.putText(img, str(n), (4, 16), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 255), 1)
            y, x = divmod(k, COLS)
            sheet[y * TILE[1]:(y + 1) * TILE[1], x * TILE[0]:(x + 1) * TILE[0]] = img
        cv2.imwrite(os.path.join(out, 'audit_%03d.jpg' % (s // (COLS * ROWS))), sheet, [cv2.IMWRITE_JPEG_QUALITY, 85])


def score(out):
    key = json.load(open(os.path.join(out, 'key.json'), encoding='utf-8'))
    truth = json.load(open(os.path.join(out, 'truth.json'), encoding='utf-8'))
    tally = collections.Counter()
    for n, row in key.items():
        if n not in truth:
            continue
        t = truth[n]
        kind = 'disagreement' if row['recorded'] != row['predicted'] else 'agreement'
        tally[kind, 'recorded right'] += row['recorded'] == t
        tally[kind, 'model right'] += row['predicted'] == t
        tally[kind, 'total'] += 1
    for kind in ('disagreement', 'agreement'):
        print('%s: %d checked, recorded label right %d, model right %d' % (
            kind, tally[kind, 'total'], tally[kind, 'recorded right'], tally[kind, 'model right']))


def main():
    if sys.argv[1] == 'score':
        return score(sys.argv[2])
    root, source, model_dir, out = sys.argv[1:5]
    agreements = int(sys.argv[5]) if len(sys.argv) > 5 else 30
    os.makedirs(out, exist_ok=True)
    _, test = load(root, source)
    predicted = predict(model_dir, source, test)
    rows = [(p, label, pred) for (p, label), pred in zip(test, predicted)]
    rng = random.Random(3)
    disagree = [r for r in rows if r[1] != r[2]]
    agree = [r for r in rows if r[1] == r[2]]
    chosen = disagree + rng.sample(agree, min(agreements, len(agree)))
    rng.shuffle(chosen)
    key = {str(n): {'path': os.path.relpath(p, root), 'recorded': label, 'predicted': pred}
           for n, (p, label, pred) in enumerate(chosen)}
    with open(os.path.join(out, 'key.json'), 'w', encoding='utf-8') as f:
        json.dump(key, f, ensure_ascii=False, indent=0)
    sheets([(n, p) for n, (p, _, _) in enumerate(chosen)], out)
    print('%d disagreements, %d agreements sampled, %d sheets' % (len(disagree), min(agreements, len(agree)),
                                                                   (len(chosen) + COLS * ROWS - 1) // (COLS * ROWS)))


if __name__ == '__main__':
    main()
