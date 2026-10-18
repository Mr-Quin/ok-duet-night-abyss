"""Send the navigator to the recorded targets in random orders, offline, on the recorded world.

The journey replay in test_world.py checks one fixed order. Here SimBackend lets every order
run: a target the recording has no path for raises Unexplored (a gap in the recording, counted
but not a failure), while a NavError or any other exception is a navigator bug, for example a
repeat loop or a row the navigator cannot find although the recording reached it.

    python -m unittest harness.test_sim_fuzz            (DNA_WORLD picks another recording)
"""
import json
import os
import random
import shutil
import tempfile
import unittest

from src.nav import Nav, NavError
from src.nav import targets

from harness.sim import SimBackend, Unexplored
from harness.world import World

HERE = os.path.dirname(os.path.abspath(__file__))
WORLD = os.environ.get('DNA_WORLD') or os.path.join(HERE, 'world')
ORDERS = int(os.environ.get('DNA_FUZZ_ORDERS', '5'))


@unittest.skipUnless(os.path.exists(os.path.join(WORLD, 'plan.json')), 'no recorded world')
class TestSimFuzz(unittest.TestCase):

    def test_random_target_orders(self):
        world = World.load(WORLD)
        with open(os.path.join(WORLD, 'plan.json'), encoding='utf-8') as f:
            plan = json.load(f)
        reached = [e for e in plan['plan'] if e['outcome'] == 'ok']
        counts = {'ok': 0, 'unexplored': 0}
        bugs = []
        for seed in range(ORDERS):
            tmp = tempfile.mkdtemp()
            try:
                cache = os.path.join(tmp, 'nav_cache.json')
                start_cache = os.path.join(WORLD, 'nav_cache_start.json')
                if os.path.exists(start_cache):
                    shutil.copy(start_cache, cache)
                order = reached[:]
                random.Random(seed).shuffle(order)
                nav = Nav(SimBackend(world, plan['start']), cache_path=cache, log=lambda m: None)
                for entry in order:
                    target = getattr(targets, entry['target'])(**entry['fields'])
                    try:
                        nav.go(target)
                        counts['ok'] += 1
                    except Unexplored:
                        counts['unexplored'] += 1
                        # the simulated game is now somewhere the recording does not continue from
                        nav = Nav(SimBackend(world, plan['start']), cache_path=cache, log=lambda m: None)
                    except NavError as e:
                        bugs.append('seed %d, %s: %s' % (seed, target, e))
            finally:
                shutil.rmtree(tmp, ignore_errors=True)
        print('reached %d, unexplored %d, navigator errors %d' % (counts['ok'], counts['unexplored'], len(bugs)))
        for bug in bugs[:20]:
            print('  ' + bug)
        self.assertEqual(bugs, [])


if __name__ == '__main__':
    unittest.main()
