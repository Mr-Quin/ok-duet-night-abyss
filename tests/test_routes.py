# 扼守走位：按标记转镜头走、被挡住时跳和放弃、路线的匹配与重放
import os
import shutil
import tempfile
import unittest

import cv2
import numpy as np

from src.tasks.fullauto import marker_walk as MW
from src.tasks.fullauto import routes as R


class FakeTask:
    def __init__(self):
        self.actions = []

    def get_dodge_key(self):
        return 'lshift'

    def next_frame(self):
        return None

    def log_info(self, msg):
        pass

    def screenshot(self, name, frame=None):
        pass

    def sleep(self, seconds):
        pass

    def send_key_down(self, key):
        self.actions.append(('down', key))

    def send_key_up(self, key):
        self.actions.append(('up', key))

    def send_key(self, key, down_time=0.02):
        self.actions.append(('key', key))

    def move_mouse_relative(self, dx, dy):
        self.actions.append(('turn', dx, dy))


class ScriptedWalk(MW.MarkerWalk):
    """find() 依次给出脚本里的 (标记偏移, 米数)，用完后重复最后一个。"""

    def __init__(self, task, seen):
        self.task, self.seen, self.last_y, self.steps = task, list(seen), 0.3, []

    def find(self, frame):
        return self.seen.pop(0) if len(self.seen) > 1 else self.seen[0]


class TestMarkerWalk(unittest.TestCase):

    def setUp(self):
        self.clock = [0.0]
        self.original_time = MW.time.time
        MW.time.time = lambda: self.clock.__setitem__(0, self.clock[0] + 0.5) or self.clock[0]

    def tearDown(self):
        MW.time.time = self.original_time

    def test_turns_toward_the_marker_and_stops_on_arrival(self):
        task = FakeTask()
        self.assertTrue(ScriptedWalk(task, [(0.3, 40), (0.0, 20), (0.0, 5)]).run((0.3, 40)))
        turns = [a for a in task.actions if a[0] == 'turn']
        # 标记在右边就往右转
        self.assertTrue(turns and turns[0][1] > 0)
        self.assertEqual(task.actions[-2:], [('up', 'lshift'), ('up', 'w')])
        self.assertEqual(task.actions[:2], [('down', 'w'), ('down', 'lshift')])

    def test_jumps_when_stuck_then_gives_up(self):
        task = FakeTask()
        self.assertFalse(ScriptedWalk(task, [(0.0, 23)]).run((0.0, 23)))
        self.assertEqual(task.actions.count(('key', 'space')), MW.MAX_JUMPS)
        self.assertEqual(task.actions[-2:], [('up', 'lshift'), ('up', 'w')])

    def test_a_distance_that_drops_impossibly_fast_is_not_an_arrival(self):
        task = FakeTask()
        walker = ScriptedWalk(task, [(0.0, 3), (0.0, 30), (0.0, 26), (0.0, 5)])
        self.assertTrue(walker.run((0.0, 35)))
        # 35 米后 0.5 秒读到 3 米是读错了，要一直走到真正读到 5 米
        self.assertEqual(walker.seen, [(0.0, 5)])

    def test_a_marker_that_vanishes_up_close_means_the_wave_started(self):
        self.assertTrue(ScriptedWalk(FakeTask(), [(0.0, 5), None]).run((0.0, 9), arrive=2))
        self.assertFalse(ScriptedWalk(FakeTask(), [(0.0, 20), None]).run((0.0, 25)))

    def test_the_walk_is_recorded_as_a_replayable_timeline(self):
        walker = ScriptedWalk(FakeTask(), [(0.3, 40), (0.0, 5)])
        walker.run((0.3, 40))
        self.assertEqual(walker.steps[0]['down'], 'w')
        self.assertTrue(any('turn' in s for s in walker.steps))
        self.assertEqual({s.get('up') for s in walker.steps if 'up' in s}, {'w', 'lshift'})
        first = walker.steps[-1]['t']
        walker.seen = [(0.0, 2)]
        walker.run((0.0, 4), arrive=2)
        self.assertGreater(walker.steps[-1]['t'], first)
        self.assertEqual([s['t'] for s in walker.steps], sorted(s['t'] for s in walker.steps))


class TestRoutes(unittest.TestCase):

    def setUp(self):
        self.folder = tempfile.mkdtemp()
        rng = np.random.default_rng(1)
        self.room = rng.integers(0, 255, (1440, 2560, 3), dtype=np.uint8)
        self.other_room = rng.integers(0, 255, (1440, 2560, 3), dtype=np.uint8)

    def tearDown(self):
        shutil.rmtree(self.folder, ignore_errors=True)

    def test_a_saved_route_is_found_again_only_for_the_same_spawn(self):
        lib = R.RouteLibrary(folders=())
        lib.save(self.room, (0.34, 0.25), [{'t': 0, 'down': 'w'}], folder=self.folder, name='room')
        lib = R.RouteLibrary(folders=(self.folder,))
        self.assertIsNotNone(lib.find(self.room, (0.33, 0.26)))
        # 同一个房间但目标在别处（比如镜像的图），或者别的房间
        self.assertIsNone(lib.find(self.room, (-0.1, 0.4)))
        self.assertIsNone(lib.find(self.other_room, (0.34, 0.25)))

    def test_on_the_same_map_the_view_does_not_have_to_match(self):
        lib = R.RouteLibrary(folders=())
        lib.save(self.room, (0.34, 0.25), [], 'defence_13', folder=self.folder, name='room')
        # 光线不同时同一张图的出生画面也会差很多
        self.assertIsNotNone(lib.find(self.other_room, (0.34, 0.25), 'defence_13'))
        self.assertIsNone(lib.find(self.other_room, (0.34, 0.25), 'defence_05'))
        self.assertIsNone(lib.find(self.other_room, (-0.1, 0.4), 'defence_13'))

    def test_a_route_that_worked_on_another_map_remembers_it(self):
        original = R.LEARNED_DIR
        R.LEARNED_DIR = self.folder
        try:
            lib = R.RouteLibrary(folders=())
            lib.save(self.room, (0.34, 0.25), [], 'defence_14', folder=self.folder, name='room')
            lib.remember_map(lib.routes[-1], 'defence_01')
            lib = R.RouteLibrary(folders=(self.folder,))
            self.assertEqual(lib.routes[0].maps, {'defence_01', 'defence_14'})
            self.assertIsNotNone(lib.find(self.other_room, (0.34, 0.25), 'defence_01'))
        finally:
            R.LEARNED_DIR = original

    def test_a_route_still_matches_at_another_resolution(self):
        lib = R.RouteLibrary(folders=())
        lib.save(self.room, (0.34, 0.25), [], folder=self.folder, name='room')
        self.assertIsNotNone(lib.find(cv2.resize(self.room, (1600, 900)), (0.34, 0.25)))

    def test_play_follows_the_timeline_and_releases_held_keys(self):
        lib = R.RouteLibrary(folders=())
        lib.save(self.room, (0, 0), [{'t': 0, 'down': 'w'}, {'t': 0.1, 'turn': [10, -2]},
                                     {'t': 0.2, 'down': 'shift_l'}, {'t': 0.3, 'down': 'f'}, {'t': 0.4, 'up': 'f'}],
                 folder=self.folder, name='room')
        task = FakeTask()
        R.play(task, lib.routes[-1])
        self.assertEqual(task.actions, [('down', 'w'), ('turn', 10, -2), ('down', 'lshift'), ('down', 'f'), ('up', 'f'),
                                        ('up', 'lshift'), ('up', 'w')])

    def test_play_never_holds_dodge_without_a_direction(self):
        lib = R.RouteLibrary(folders=())
        lib.save(self.room, (0, 0), [{'t': 0, 'down': 'shift_l'}, {'t': 0, 'down': 'w'}, {'t': 0.1, 'down': 'shift_l'},
                                     {'t': 0.2, 'up': 'w'}, {'t': 0.3, 'up': 'shift_l'}],
                 folder=self.folder, name='room')
        task = FakeTask()
        R.play(task, lib.routes[-1])
        self.assertEqual(task.actions, [('down', 'w'), ('down', 'lshift'), ('up', 'lshift'), ('up', 'w')])

    def test_the_shipped_grapple_route_loads(self):
        lib = R.RouteLibrary(folders=(R.SHIPPED_DIR,))
        grapple = next(r for r in lib.routes if r.name == 'grapple_room')
        self.assertIn('defence_08', grapple.maps)


if __name__ == '__main__':
    unittest.main()
