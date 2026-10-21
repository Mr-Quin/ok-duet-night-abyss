# 日常领奖：红点识别，界面里关弹窗、按全部领取、点红点的顺序，以及不该点的红点
import unittest

import cv2
import numpy as np

from src.nav import claims as C
from src.nav import text_zh as T
from src.nav.backend import Screen

W, H = 1600, 900


def screen(texts=(), dots=(), blobs=()):
    """texts 为 (文字, x, y)；dots 是红点中心，blobs 是比红点大得多的红色块。"""
    img = np.zeros((H, W, 3), np.uint8)
    for x, y in dots:
        cv2.circle(img, (int(x * W), int(y * H)), 7, (40, 40, 230), -1)
    for x, y in blobs:
        cv2.rectangle(img, (int(x * W), int(y * H)), (int(x * W) + 80, int(y * H) + 40), (40, 40, 230), -1)
    return Screen(img, [{'t': t, 'x': x, 'y': y} for t, x, y in texts])


class FakeBackend:
    def __init__(self, screens):
        self.screens = list(screens)
        self.actions = []

    def read(self):
        return self.screens.pop(0) if len(self.screens) > 1 else self.screens[0]

    def thumb(self):
        return None

    def settle(self, before):
        pass

    def key(self, name):
        self.actions.append(('key', name))


class FakeNav:
    def __init__(self, screens):
        self.b = FakeBackend(screens)

    def tap(self, x, y):
        self.b.actions.append(('tap', round(x, 2), round(y, 2)))


MENU = [('历练', 0.09, 0.58), ('协会', 0.22, 0.70), ('吟游诗集', 0.29, 0.70), ('声名', 0.22, 0.81), ('商店', 0.15, 0.32)]
HINT = [('Space', 0.87, 0.97), ('全部领取', 0.91, 0.97)]
POPUP = [('获得物品', 0.5, 0.23), ('点击空白区域关闭', 0.5, 0.89)]


class TestRedDots(unittest.TestCase):

    def test_finds_dots_and_ignores_larger_red_areas(self):
        scr = screen(dots=[(0.3, 0.2), (0.6, 0.7)], blobs=[(0.1, 0.5)])
        dots = C.red_dots(scr)
        self.assertEqual(len(dots), 2)
        self.assertAlmostEqual(dots[0][0], 0.3, places=2)
        self.assertEqual(C.red_dots(scr, (0.5, 0.5, 1, 1)), dots[1:])

    def test_menu_tiles_with_a_dot_at_the_icons_top_right(self):
        scr = screen(MENU, dots=[(0.121, 0.507), (0.313, 0.621)])
        self.assertEqual([n for n in C.PAGES if C.tile_has_dot(scr, n)], ['历练', '吟游诗集'])


class TestClaimingAPage(unittest.TestCase):

    def claim(self, page, screens):
        nav = FakeNav(screens)
        C.Claimer(nav).claim(page)
        return nav.b.actions

    def test_claims_all_closes_the_popup_then_follows_the_milestone_dot(self):
        tab = [('入门指南', 0.16, 0.17), ('备忘手记', 0.28, 0.17)]
        actions = self.claim(C.PAGES['历练'], [
            screen(tab, dots=[(0.30, 0.155)]),
            screen(tab + HINT),
            screen(POPUP),
            screen(tab + [('200', 0.18, 0.61)], dots=[(0.19, 0.59)]),
            screen(POPUP),
            screen(tab)])
        self.assertEqual(actions, [('tap', 0.29, 0.17), ('key', 'space'), ('tap', 0.5, 0.89),
                                   ('tap', 0.18, 0.6), ('tap', 0.5, 0.89)])

    def test_a_dot_that_stays_is_tapped_twice_then_left(self):
        card = screen([('提交物品', 0.23, 0.71)], dots=[(0.33, 0.684)])
        actions = self.claim(C.Page((), buttons=C.PAGES['声名'].buttons), [card])
        # 红点在按钮右上角，点在按钮里面
        self.assertEqual(actions, [('tap', 0.27, 0.71)] * C.MAX_TAPS)

    def test_the_submit_reward_popup_is_confirmed_not_used(self):
        popup = screen([('获得物品', 0.5, 0.19), ('提交成功', 0.5, 0.33), ('确认', 0.42, 0.81), ('使用消耗品', 0.58, 0.81)])
        actions = self.claim(C.Page((), buttons=C.PAGES['声名'].buttons), [popup, screen()])
        self.assertEqual(actions, [('tap', 0.42, 0.81)])

    def test_dots_outside_the_pages_regions_or_on_go_buttons_are_not_tapped(self):
        bp = [('见闻报酬', 0.22, 0.03), ('转述见闻', 0.34, 0.03), ('解锁精装诗集', 0.88, 0.86), ('购买等级', 0.09, 0.47)]
        actions = self.claim(C.PAGES['吟游诗集'], [screen(bp, dots=[(0.36, 0.02), (0.9, 0.84), (0.1, 0.45)])])
        self.assertEqual(actions, [])
        rows = [('前往', 0.86, 0.86)]
        actions = self.claim(C.PAGES['协会'], [screen(rows, dots=[(0.87, 0.85)])])
        self.assertEqual(actions, [])

    def test_switches_region_until_it_comes_back_to_the_first(self):
        def region(name):
            return screen([(name, 0.14, 0.07), ('惠赠', 0.36, 0.13)])
        actions = self.claim(C.PAGES['声名'], [region('海伯利亚')] * 2 + [region('华胥')] * 3 + [region('海伯利亚')])
        self.assertEqual(actions, [('key', 'e'), ('key', 'e')])


class TestTexts(unittest.TestCase):

    def test_the_reward_popup_is_found_when_ocr_drops_a_character(self):
        self.assertTrue(screen([('点击空区域关闭', 0.5, 0.82)]).find(T.CLOSE_ON_BLANK))


if __name__ == '__main__':
    unittest.main()
