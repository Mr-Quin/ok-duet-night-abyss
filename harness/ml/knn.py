"""Few-shot screen recognition: nearest neighbours on frozen ImageNet features, no training.

    python -m harness.ml.knn DATASET_DIR SOURCE [shots]

Answers two questions for the "what happens with a new screen" problem:
1. With only `shots` labelled frames per class, how accurate is nearest-centroid / 1-NN on
   held-out sessions? (Adding a screen would mean adding a few frames, not retraining.)
2. Can distance flag a screen it has never seen? Each class in turn is left out of the
   references; its test frames should land farther from every reference than known screens
   do. Reported as the share of unseen frames flagged when the threshold lets 95% of known
   frames through.
Uses train.py's loading and split, so the numbers are comparable.
"""
import collections
import random
import sys

import numpy as np
import torch
from torchvision.models import MobileNet_V3_Small_Weights, mobilenet_v3_small

from harness.ml.train import load, tensor


def embedder(device):
    net = mobilenet_v3_small(weights=MobileNet_V3_Small_Weights.DEFAULT)
    net.classifier = torch.nn.Identity()
    return net.eval().to(device)


def embed(net, items, device, batch=64):
    out = []
    with torch.no_grad():
        for k in range(0, len(items), batch):
            x = torch.stack([tensor(p) for p, _ in items[k:k + batch]]).to(device)
            f = net(x)
            out.append(torch.nn.functional.normalize(f, dim=1).cpu().numpy())
    return np.concatenate(out) if out else np.zeros((0, 576), np.float32)


def main():
    root, source = sys.argv[1], sys.argv[2]
    shots = int(sys.argv[3]) if len(sys.argv) > 3 else 5
    train, test = load(root, source)
    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    net = embedder(device)
    rng = random.Random(0)
    by_class = collections.defaultdict(list)
    for item in train:
        by_class[item[1]].append(item)
    refs = []
    for label, items in by_class.items():
        rng.shuffle(items)
        refs += items[:shots]
    classes = sorted(by_class)
    test = [t for t in test if t[1] in by_class]
    R, T = embed(net, refs, device), embed(net, test, device)
    ref_labels = np.array([l for _, l in refs])
    test_labels = np.array([l for _, l in test])
    sims = T @ R.T
    nn_pred = ref_labels[sims.argmax(1)]
    print('%s: %d classes, %d references (%d per class), %d test frames' % (source, len(classes), len(refs), shots, len(test)))
    print('1-NN accuracy %.4f' % (nn_pred == test_labels).mean())
    for c in classes:
        mask = test_labels == c
        if mask.any():
            print('  %-14s %5.3f (%d)' % (c, (nn_pred[mask] == c).mean(), mask.sum()))
    # open set: leave one class out of the references
    flagged = []
    for c in classes:
        keep = ref_labels != c
        unseen = test_labels == c
        if not unseen.any() or unseen.all() or keep.sum() == 0:
            continue
        best = sims[:, keep].max(1)
        threshold = np.quantile(best[~unseen], 0.05)
        rate = (best[unseen] < threshold).mean()
        flagged.append(rate)
        print('  without %-14s unseen flagged %5.3f at 95%% known kept' % (c, rate))
    if flagged:
        print('mean unseen-screen flag rate %.3f' % np.mean(flagged))


if __name__ == '__main__':
    main()
