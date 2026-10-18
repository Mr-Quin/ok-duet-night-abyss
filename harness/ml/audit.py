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

import torch

from harness.ml.train import load, model_for, tensor
from harness.sheets import tile


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
    count = tile([(p, str(n)) for n, (p, _, _) in enumerate(chosen)], out, 'audit')
    print('%d disagreements, %d agreements sampled, %d sheets' % (len(disagree), min(agreements, len(agree)), count))


if __name__ == '__main__':
    main()
