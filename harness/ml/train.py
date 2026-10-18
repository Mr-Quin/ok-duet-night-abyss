"""Train a small screen classifier on frames recorded by harness/dataset.py.

    python -m harness.ml.train DATASET_DIR phase OUT_DIR
    python -m harness.ml.train DATASET_DIR screen OUT_DIR

The labels are what the rule-based code said at the time, so the model learns to copy it
(distillation). The last fifth of every recording session is held out for testing: frames a
second apart are near copies, and a random split would only test memory.
Runs in its own venv with torch, torchvision and opencv, not in ok-dna's.
"""
import collections
import glob
import json
import os
import sys
import time

import cv2
import numpy as np
import torch
import torch.nn as nn
from torchvision.models import MobileNet_V3_Small_Weights, mobilenet_v3_small

HOLD_OUT = 0.2
EPOCHS = 8
BATCH = 64
MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)


def load(root, source):
    train, test = [], []
    for index in sorted(glob.glob(os.path.join(root, '**', 'labels.jsonl'), recursive=True)):
        folder = os.path.dirname(index)
        with open(index, encoding='utf-8') as f:
            rows = [json.loads(line) for line in f]
        rows = [r for r in rows if r['source'] == source and r['label'] is not None]
        cut = int(len(rows) * (1 - HOLD_OUT))
        for k, r in enumerate(rows):
            (train if k < cut else test).append((os.path.join(folder, r['file']), r['label']))
    return train, test


def tensor(path):
    img = cv2.cvtColor(cv2.imread(path), cv2.COLOR_BGR2RGB).astype(np.float32) / 255
    return torch.from_numpy(((img - MEAN) / STD).transpose(2, 0, 1))


class Frames(torch.utils.data.Dataset):
    def __init__(self, items, classes):
        self.items, self.classes = items, classes

    def __len__(self):
        return len(self.items)

    def __getitem__(self, k):
        path, label = self.items[k]
        return tensor(path), self.classes.index(label)


def model_for(n):
    net = mobilenet_v3_small(weights=MobileNet_V3_Small_Weights.DEFAULT)
    net.classifier[3] = nn.Linear(net.classifier[3].in_features, n)
    return net


def evaluate(net, loader, device, classes):
    net.eval()
    confusion = collections.Counter()
    with torch.no_grad():
        for x, y in loader:
            pred = net(x.to(device)).argmax(1).cpu()
            for a, b in zip(y.tolist(), pred.tolist()):
                confusion[classes[a], classes[b]] += 1
    right = sum(v for (a, b), v in confusion.items() if a == b)
    return right / max(1, sum(confusion.values())), confusion


def main():
    root, source, out = sys.argv[1], sys.argv[2], sys.argv[3]
    os.makedirs(out, exist_ok=True)
    train, test = load(root, source)
    classes = sorted({label for _, label in train + test})
    print('%s: %d train, %d test, classes %s' % (source, len(train), len(test), classes), flush=True)
    print('train counts', collections.Counter(l for _, l in train).most_common(), flush=True)
    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    net = model_for(len(classes)).to(device)
    loader = torch.utils.data.DataLoader(Frames(train, classes), batch_size=BATCH, shuffle=True, num_workers=0)
    test_loader = torch.utils.data.DataLoader(Frames(test, classes), batch_size=BATCH, num_workers=0)
    opt = torch.optim.AdamW(net.parameters(), lr=1e-3, weight_decay=1e-4)
    loss_fn = nn.CrossEntropyLoss()
    for epoch in range(EPOCHS):
        net.train()
        t0, total = time.time(), 0.0
        for x, y in loader:
            opt.zero_grad()
            loss = loss_fn(net(x.to(device)), y.to(device))
            loss.backward()
            opt.step()
            total += loss.item() * len(y)
        acc, _ = evaluate(net, test_loader, device, classes)
        print('epoch %d loss %.4f test acc %.4f (%.0fs)' % (epoch, total / len(train), acc, time.time() - t0), flush=True)
    acc, confusion = evaluate(net, test_loader, device, classes)
    print('final test acc %.4f' % acc)
    for (a, b), v in sorted(confusion.items()):
        if a != b:
            print('  %s -> %s: %d' % (a, b, v))
    net.eval()
    x = tensor(test[0][0] if test else train[0][0]).unsqueeze(0)
    for dev in [device, 'cpu']:
        m = net.to(dev)
        with torch.no_grad():
            for _ in range(5):
                m(x.to(dev))
            t0 = time.perf_counter()
            for _ in range(50):
                m(x.to(dev))
            if dev == 'cuda':
                torch.cuda.synchronize()
        print('latency on %s: %.1f ms per frame' % (dev, 1000 * (time.perf_counter() - t0) / 50))
    net = net.cpu()
    torch.save({'state': net.state_dict(), 'classes': classes}, os.path.join(out, '%s.pt' % source))
    # ok-dna's own Python has OpenVINO but no torch, so the live shadow check loads ONNX
    torch.onnx.export(net, x.cpu(), os.path.join(out, '%s.onnx' % source), input_names=['frame'],
                      output_names=['logits'], opset_version=17)
    with open(os.path.join(out, '%s.json' % source), 'w', encoding='utf-8') as f:
        json.dump({'classes': classes, 'size': [x.shape[3], x.shape[2]], 'test_acc': acc}, f, ensure_ascii=False)


if __name__ == '__main__':
    main()
