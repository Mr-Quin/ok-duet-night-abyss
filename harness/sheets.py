"""Numbered contact sheets, for checking many frames by eye at once."""
import os

import cv2
import numpy as np


def read_image(path):
    """cv2.imread that also works with non-ASCII Windows paths; None when the file is missing."""
    try:
        data = np.fromfile(path, dtype=np.uint8)
    except OSError:
        return None
    return cv2.imdecode(data, cv2.IMREAD_COLOR) if data.size else None


def tile(entries, out, prefix, cols=6, rows=5, size=(320, 180)):
    """entries is [(image path or image, caption)]. Writes out/prefix_000.jpg and so on; returns the sheet count."""
    os.makedirs(out, exist_ok=True)
    per = cols * rows
    for s in range(0, len(entries), per):
        sheet = np.zeros((rows * size[1], cols * size[0], 3), np.uint8)
        for k, (img, caption) in enumerate(entries[s:s + per]):
            img = read_image(img) if isinstance(img, str) else img
            if img is None:
                continue
            img = cv2.resize(img, size)
            cv2.rectangle(img, (0, 0), (min(size[0], 10 + 10 * len(caption)), 22), (0, 0, 0), -1)
            cv2.putText(img, caption, (4, 16), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1)
            y, x = divmod(k, cols)
            sheet[y * size[1]:(y + 1) * size[1], x * size[0]:(x + 1) * size[0]] = img
        cv2.imwrite(os.path.join(out, '%s_%03d.jpg' % (prefix, s // per)), sheet, [cv2.IMWRITE_JPEG_QUALITY, 85])
    return (len(entries) + per - 1) // per
