"""Record a world by navigating the live game through a random sequence of targets.

Run on the game PC, with the live service up and the game in the foreground:
    python -m harness.record_world harness/world 60 --seed 7

Writes the masked states and transitions to the world folder, plus plan.json (the targets in
order and how each ended), trace.json (every screen read in order and the inputs sent after it)
and nav_cache_start.json (the cache the navigator started from), which together let
harness/test_world.py replay the same journey without the game.
"""
import argparse
import json
import os
import random
import shutil
from dataclasses import asdict

from src.nav import (BookSection, CommissionTab, MainMenu, Menu, Mission, Nav, NavError, Nightbook, Page, World)
from src.nav import text_zh as T

from harness.live.backend import LiveBackend
from harness.recorder import RecordingBackend

ENTRIES = {30: 4, 65: 10}

# the quests menu is left out: it shows story progress
POOL = [World(), MainMenu(), Menu('背包'), Menu('地图'), Menu('铸造'),
        BookSection('今日行程'), BookSection('梦魔残声'), BookSection('歧路足音'),
        Page('迷津'), Page('boss_map')] \
    + [CommissionTab(t) for t in T.TABS] \
    + [Mission('扼守/无尽', lv=60), Mission('驱离', lv=70)] \
    + [Nightbook(lv, row) for lv, n in ENTRIES.items() for row in range(n)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('world')
    ap.add_argument('count', type=int)
    ap.add_argument('--seed', type=int, default=1)
    ap.add_argument('--cache', default=os.path.join('configs', 'nav_cache.json'))
    args = ap.parse_args()

    os.makedirs(args.world, exist_ok=True)
    cache = os.path.join(args.world, 'nav_cache.json')
    if os.path.exists(args.cache):
        shutil.copy(args.cache, os.path.join(args.world, 'nav_cache_start.json'))
        shutil.copy(args.cache, cache)
    backend = RecordingBackend(LiveBackend(), args.world)
    nav = Nav(backend, cache_path=cache)
    rng = random.Random(args.seed)
    plan, previous = [], None
    try:
        for k in range(args.count):
            target = rng.choice([t for t in POOL if t != previous])
            previous = target
            try:
                nav.go(target)
                outcome = 'ok'
            except NavError as e:
                outcome, detail = type(e).__name__, str(e)
            else:
                detail = ''
            plan.append({'target': type(target).__name__, 'fields': asdict(target), 'outcome': outcome, 'detail': detail})
            print('%3d %-60s %s' % (k, target, outcome), flush=True)
    finally:
        backend.save(os.path.join(args.world, 'trace.json'))
        with open(os.path.join(args.world, 'plan.json'), 'w', encoding='utf-8') as f:
            json.dump({'start': backend.start, 'plan': plan}, f, ensure_ascii=False, indent=1)
        print('states %d, transitions %d' % (len(backend.world.states), len(backend.world.transitions)))


if __name__ == '__main__':
    main()
