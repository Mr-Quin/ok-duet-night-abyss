# 小地图：认出是哪张扼守地图，读出目标菱形的方位
import glob
import os
import unittest

import cv2
import numpy as np

from src.tasks.fullauto import minimap as M

# 每张图出生时目标菱形的方位（度，北为 0），在 30 次出生画面上量的


def frame_with(mini, width=2560, height=1440):
    """把小地图放回整帧画面里它的位置。"""
    frame = np.zeros((height, width, 3), np.uint8)
    cx, cy, r = int(M.CENTER_X * width), int(M.CENTER_Y * height), int(M.RADIUS * width)
    frame[cy - r:cy + r, cx - r:cx + r] = cv2.resize(mini, (2 * r, 2 * r))
    return frame


class TestMinimap(unittest.TestCase):

    def setUp(self):
        self.library = M.MapLibrary()
        self.refs = {os.path.splitext(os.path.basename(p))[0]: cv2.imread(p)
                     for p in sorted(glob.glob(os.path.join(M.MAPS_DIR, '*.png')))}

    def test_every_map_is_recognised_as_itself(self):
        for name, mini in self.refs.items():
            with self.subTest(map=name):
                self.assertEqual(self.library.identify(frame_with(mini))[0], name)

    def test_maps_are_told_apart_at_other_resolutions(self):
        for name, mini in self.refs.items():
            with self.subTest(map=name):
                self.assertEqual(self.library.identify(frame_with(mini, 1600, 900))[0], name)

    def test_an_empty_minimap_is_no_known_map(self):
        self.assertIsNone(self.library.identify(np.zeros((1440, 2560, 3), np.uint8))[0])


if __name__ == '__main__':
    unittest.main()
