"""Navigator end to end without the game: replay the recorded world and the screen fixtures.

    python -m unittest harness/test_world.py
"""
import json
import os
import shutil
import tempfile
import unittest

import cv2
import numpy as np

from src.nav import Nav, NavError, targets
from src.nav import screens as S
from src.nav.backend import Screen

from harness.sim import SimBackend
from harness.world import World, signature

HERE = os.path.dirname(os.path.abspath(__file__))
WORLD = os.path.join(HERE, 'world')
FIXTURES = os.path.join(HERE, 'fixtures')

# fixture -> (screen, expected info); the fixtures come from capture_fixtures.py
EXPECTED = {
    'world': ('world', {}),
    'main_menu': ('main_menu', {}),
    'menu_bag': ('menu', {'name': '背包'}),
    'menu_map': ('menu', {'name': '地图'}),
    'menu_forge': ('menu', {'name': '铸造'}),
    'book_today': ('book', {'section': '今日行程'}),
    'book_boss': ('book', {'section': '梦魔残声'}),
    'book_maze': ('book', {'section': '歧路足音'}),
    'page_maze': ('page', {'name': '迷津'}),
    'page_boss': ('page', {'name': 'boss_map'}),
    'commission_tasks': ('commission', {'tab': '委托'}),
    'commission_letters': ('commission', {'tab': '委托密函'}),
    'commission_bounty': ('commission', {'tab': '悬赏委托'}),
    'nightbook_lv30_top': ('commission', {'tab': '夜航手册'}),
    'nightbook_lv65_top': ('commission', {'tab': '夜航手册'}),
    'nightbook_lv65_bottom': ('commission', {'tab': '夜航手册'}),
    'start_nightbook_lv30': ('start', {'via': '夜航手册', 'lv': 30, 'auto_on': True, 'auto_rounds': 1}),
    'start_before_run': ('start', {'via': '夜航手册', 'lv': 30, 'auto_on': True}),
    'start_mission_lv60': ('start', {'via': '委托', 'lv': 60, 'auto_on': False}),
    'start_letter': ('start', {'via': '委托密函', 'mode': '驱逐', 'auto_on': False}),
    'manual_popup_before_run': ('manual_popup', {'before_run': True}),
    'manual_popup_between_rounds': ('manual_popup', {'before_run': False}),
    'loading': ('unknown', {}),
    'dungeon_to_objective': ('dungeon', {'to_objective': True}),
    'dungeon_fighting': ('dungeon', {'to_objective': False}),
    'dungeon_menu_nothing_earned': ('dungeon_menu', {'nothing_earned': True}),
    'exit_confirm': ('exit_confirm', {}),
    'round_dialog_auto': ('round_dialog', {'auto': (1, 1)}),
    'round_dialog_auto_done': ('round_dialog', {'auto': None}),
    'result': ('result', {}),
}
SELECTED_LEVEL = {'nightbook_lv30_top': 30, 'nightbook_lv65_top': 65, 'nightbook_lv65_bottom': 65}


def load_fixture(name):
    img = cv2.imdecode(np.fromfile(os.path.join(FIXTURES, name + '.jpg'), dtype=np.uint8), cv2.IMREAD_COLOR)
    with open(os.path.join(FIXTURES, name + '.json'), encoding='utf-8') as f:
        return Screen(img, json.load(f)['items'])


class TestFixtures(unittest.TestCase):
    def test_every_fixture_classifies(self):
        atlas = S.load_atlas()
        for name, (screen, expected) in EXPECTED.items():
            with self.subTest(fixture=name):
                scr = load_fixture(name)
                found, info = S.classify(scr, atlas)
                self.assertEqual(found, screen)
                for key, value in expected.items():
                    self.assertEqual(info.get(key), value, key)
                if name in SELECTED_LEVEL:
                    self.assertEqual(S.selected_level(scr, info['levels']), SELECTED_LEVEL[name])


@unittest.skipUnless(os.path.exists(os.path.join(WORLD, 'plan.json')), 'no recorded world')
class TestRecordedWorld(unittest.TestCase):
    def setUp(self):
        self.world = World.load(WORLD)
        with open(os.path.join(WORLD, 'plan.json'), encoding='utf-8') as f:
            self.plan = json.load(f)
        self.tmp = tempfile.mkdtemp()
        self.rows = os.path.join(self.tmp, 'nav_rows.json')
        start_rows = os.path.join(WORLD, 'nav_rows_start.json')
        if os.path.exists(start_rows):
            shutil.copy(start_rows, self.rows)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_states_still_classify_the_same(self):
        atlas = S.load_atlas()
        for sid, state in self.world.states.items():
            with self.subTest(state=sid):
                scr = Screen(self.world.image(sid), self.world.items(sid))
                screen, info = S.classify(scr, atlas)
                self.assertEqual(signature(scr, screen, info), state['signature'])

    def test_recorded_journey_replays(self):
        sim = SimBackend(self.world, self.plan['start'])
        nav = Nav(sim, rows_path=self.rows)
        for k, entry in enumerate(self.plan['plan']):
            target = getattr(targets, entry['target'])(**entry['fields'])
            try:
                nav.go(target)
                outcome = 'ok'
            except NavError as e:
                outcome = type(e).__name__
            self.assertEqual(outcome, entry['outcome'], 'step %d: %s' % (k, target))


if __name__ == '__main__':
    unittest.main()
