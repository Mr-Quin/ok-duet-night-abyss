"""Measure how far a relative mouse move turns the camera, in marker offset per mouse count.

Run at a 扼守 spawn (before the first wave) with the live service up.
"""
import sys
import time

from src.nav import Mission, Nav
from src.tasks.fullauto.marker_walk import MarkerWalk

from harness.live.backend import LiveBackend
from harness.live.collect_maps import MODE, start_run
from harness.live.walk_probe import OcrTask


def main():
    b = LiveBackend()
    nav = Nav(b, cache_path='configs/nav_cache.json')
    state = nav.where()
    if not (state.screen == 'dungeon' and state.info.get('to_objective')):
        nav.go(Mission(MODE, lv=int(sys.argv[1]) if len(sys.argv) > 1 else 50))
        start_run(nav)
        time.sleep(1.0)
    walker = MarkerWalk(OcrTask(b))
    def x_now():
        time.sleep(0.4)
        seen = walker.find(b.frame())
        return None if seen is None else seen[0]
    start = x_now()
    print('start x', start, flush=True)
    for dx in (100, 100, -200, 200, -200):
        before = x_now()
        b.turn(dx, 0, steps=10)
        after = x_now()
        if before is not None and after is not None:
            print('turn %+d: x %.3f -> %.3f  (%.5f per count)' % (dx, before, after, (after - before) / dx), flush=True)
        else:
            print('turn %+d: marker not seen (%s -> %s)' % (dx, before, after), flush=True)


if __name__ == '__main__':
    main()
