"""Walk from a 扼守 spawn the way the marker walk does, logging every step and saving frames.

Starts a run of the given level (or uses the spawn the game is already at), identifies the
map, walks, then leaves before the first wave. Run on the game PC with the live service up:

    python -m harness.live.walk_probe harness/probes 40

Frames are full screenshots and show the UID; the output folder is git-ignored.
"""
import json
import os
import sys
import time

import cv2

from src.nav import Mission, Nav
from src.tasks.fullauto.marker_walk import ARRIVED_METRES, MarkerWalk
from src.tasks.fullauto.minimap import MapLibrary, objective_bearing

from harness.live.backend import LiveBackend
from harness.live.collect_maps import MODE, start_run

STEER = 0.03
TIMEOUT = 30
# 鼠标横移一格，标记在画面上大约挪 0.003 个画面宽（角度大了会少一点）
TURN_PER_COUNT = 0.003
MAX_TURN = 150
# 距离这么久没变小就当作卡住了
STUCK_SECONDS = 2.5
ANCHOR = cv2.imread(os.path.join(os.path.dirname(__file__), 'templates', 'anchor.png'))
# 抓钩点模板是从 2560 宽的画面截的；画面里的大小随距离变
ANCHOR_SCALES = (0.75, 1.0)
ANCHOR_MATCH = 0.62


def find_anchor(frame):
    H, W = frame.shape[:2]
    s = W / 2560
    x0, y0 = int(0.2 * W), int(0.05 * H)
    roi = frame[y0:int(0.6 * H), x0:int(0.8 * W)]
    best = (0.0, None)
    for k in ANCHOR_SCALES:
        t = cv2.resize(ANCHOR, None, fx=k * s, fy=k * s, interpolation=cv2.INTER_AREA)
        _, score, _, loc = cv2.minMaxLoc(cv2.matchTemplate(roi, t, cv2.TM_CCOEFF_NORMED))
        if score > best[0]:
            best = (score, ((loc[0] + x0 + t.shape[1] / 2) / W, (loc[1] + y0 + t.shape[0] / 2) / H))
    return best


def grapple_ready(b, frame, at):
    """抓钩点上方出现「F」键提示时才够得着。"""
    H, W = frame.shape[:2]
    x, y = at
    crop = frame[max(0, int((y - 0.09) * H)):int((y - 0.015) * H), max(0, int((x - 0.03) * W)):int((x + 0.03) * W)]
    if crop.size == 0:
        return False
    crop = cv2.resize(crop, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
    return any(i['t'].strip().upper() == 'F' for i in b.ocr(crop))


class Box:
    def __init__(self, name):
        self.name = name


class OcrTask:
    """Just enough of an ok-script task for MarkerWalk.find."""

    def __init__(self, backend):
        self.b = backend

    def ocr(self, frame, threshold=0.5):
        return [Box(i['t']) for i in self.b.ocr(frame)]


ROUTES = os.path.join(os.path.dirname(__file__), 'routes')


def play_route(b, route):
    """按录下的时间线重放按键和镜头转动。"""
    t0, held = time.time(), set()
    try:
        for step in route['steps']:
            wait = step['t'] - (time.time() - t0)
            if wait > 0:
                time.sleep(wait)
            if 'down' in step:
                b.key_down(step['down']); held.add(step['down'])
            elif 'up' in step:
                b.key_up(step['up']); held.discard(step['up'])
            elif 'turn' in step:
                b.turn(step['turn'][0], step['turn'][1], steps=1)
    finally:
        for k in held:
            b.key_up(k)


def probe(b, out, tag, route_only=False):
    folder = os.path.join(out, tag)
    os.makedirs(folder, exist_ok=True)
    walker = MarkerWalk(OcrTask(b))
    frame = b.frame()
    name, score = MapLibrary().identify(frame)
    cv2.imwrite(os.path.join(folder, 'start.jpg'), frame)
    route_path = os.path.join(ROUTES, '%s.json' % name)
    if route_only and not os.path.exists(route_path):
        return {'tag': tag, 'map': name, 'score': round(score, 2), 'result': 'skipped', 'jumps': 0, 'grapples': 0,
                'seconds': 0, 'steps': []}
    played = False
    if os.path.exists(route_path):
        play_route(b, json.load(open(route_path, encoding='utf-8')))
        played = True
    steps, t0, lost_since, result = [], time.time(), None, 'timeout'
    best, best_at, jumps, grapples, grappled_at = None, time.time(), 0, 0, 0.0
    b.key_down('w')
    b.key_down('lshift')
    try:
        while time.time() - t0 < TIMEOUT:
            frame = b.frame()
            seen = walker.find(frame)
            bearing = objective_bearing(frame)
            t = round(time.time() - t0, 2)
            anchor_score, anchor_at = find_anchor(frame)
            ready = anchor_score > ANCHOR_MATCH and grapple_ready(b, frame, anchor_at)
            steps.append({'t': t, 'x': None if seen is None else round(seen[0], 3),
                          'm': None if seen is None else seen[1], 'bearing': None if bearing is None else round(bearing),
                          'anchor': round(anchor_score, 2), 'ready': ready})
            if ready or time.time() - grappled_at < 4 or len(steps) % 3 == 1:
                cv2.imwrite(os.path.join(folder, '%05.1f.jpg' % t), cv2.resize(frame, (960, 540)))
            if ready and not played and time.time() - grappled_at > 4:
                grapples += 1
                grappled_at = time.time()
                steps[-1]['event'] = 'grapple'
                b.tap('f', 0.1)
                time.sleep(1.2)
                b.tap('e', 0.1)
                best_at = time.time()
                continue
            if seen is None:
                lost_since = lost_since or time.time()
                if time.time() - lost_since > 3:
                    result = 'lost'
                    break
                continue
            lost_since = None
            x, metres = seen
            if metres is not None and metres <= ARRIVED_METRES:
                result = 'arrived'
                break
            if metres is not None and (best is None or metres < best):
                best, best_at = metres, time.time()
            elif time.time() - best_at > STUCK_SECONDS:
                jumps += 1
                steps[-1]['event'] = 'jump'
                b.tap('space', 0.1)
                best_at = time.time()
            if abs(x) > STEER:
                dx = max(-MAX_TURN, min(MAX_TURN, round(x / TURN_PER_COUNT)))
                b.turn(dx, 0, steps=4)
    finally:
        b.key_up('lshift')
        b.key_up('w')
    report = {'tag': tag, 'map': name, 'score': round(score, 2), 'result': result, 'jumps': jumps, 'grapples': grapples,
              'route': played,
              'seconds': round(time.time() - t0, 1), 'steps': steps}
    with open(os.path.join(folder, 'probe.json'), 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=0)
    return report


def main():
    out, lv = sys.argv[1], int(sys.argv[2])
    tries = int(sys.argv[3]) if len(sys.argv) > 3 else 1
    route_only = '--route-only' in sys.argv
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, '.gitignore'), 'w') as f:
        f.write('*\n')
    b = LiveBackend()
    nav = Nav(b, cache_path=os.path.join('configs', 'nav_cache.json'))
    for k in range(tries):
        state = nav.where()
        if not (state.screen == 'dungeon' and state.info.get('to_objective')):
            nav.go(Mission(MODE, lv=lv))
            if not start_run(nav):
                print('no spawn view', flush=True)
                continue
        time.sleep(1.0)
        r = probe(b, out, 'lv%d_%s' % (lv, time.strftime('%H%M%S')), route_only)
        if r['result'] == 'skipped':
            print('lv%d %s map=%s(%.2f) skipped' % (lv, r['tag'], r['map'], r['score']), flush=True)
            nav.go(Mission(MODE, lv=lv))
            continue
        metres = [s['m'] for s in r['steps'] if s['m'] is not None]
        print('lv%d %s map=%s(%.2f) %s in %.1fs, metres %s..%s, %d steps, %d jumps' % (
            lv, r['tag'], r['map'], r['score'], r['result'], r['seconds'],
            metres[0] if metres else None, metres[-1] if metres else None, len(r['steps']), r['jumps']), flush=True)
        print('    route %s, grapples %d, best anchor %.2f' % (r['route'], r['grapples'], max((s['anchor'] for s in r['steps']), default=0)), flush=True)
        nav.go(Mission(MODE, lv=lv))


if __name__ == '__main__':
    main()
