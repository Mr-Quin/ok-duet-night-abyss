"""Collect the spawn view of every 扼守 map in the plain commission pools.

For each level on the 扼守 card, starts the mission several times, saves the frame at the spawn
(minimap, objective marker and distance are all visible there), and leaves before the first
wave, when there is nothing to lose. The pool is random, so several tries per level are needed
to see every map in it. Run on the game PC with the live service up:

    python -m harness.live.collect_maps harness/maps_raw 6

Frames are full screenshots and show the UID; the output folder is git-ignored.
"""
import json
import os
import sys
import time

from src.nav import Mission, Nav, NavError, World

from harness.live.backend import LiveBackend

MODE = '扼守/无尽'
SPAWN_TIMEOUT = 90
# 放弃之后让游戏把副本卸载干净再开下一局；连续快速进出时游戏崩过一次
COOL_DOWN = 20


def start_button(scr):
    # 「匹配挑战」会去匹配别的玩家，只点「开始挑战」
    hits = scr.find('开始挑战', exact=True)
    return hits[-1] if hits else None


def start_run(nav):
    """在开始界面开局，等到出生点画面（局内、还在去目标点）。"""
    deadline = time.time() + SPAWN_TIMEOUT
    pressed = False
    while time.time() < deadline:
        state = nav.where()
        if state.screen == 'dungeon' and state.info.get('to_objective'):
            return True
        if state.screen == 'start' and not pressed:
            button = start_button(nav.b.read())
            if button:
                nav.tap(button['x'], button['y'])
                pressed = True
        elif state.screen == 'manual_popup' and state.info.get('before_run'):
            nav.b.key('space')
        nav.b.sleep(1.0)
    return False


def main():
    out, tries = sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 6
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, '.gitignore'), 'w') as f:
        f.write('*\n')
    nav = Nav(LiveBackend(), log=print, cache_path=os.path.join('configs', 'nav_cache.json'))
    nav.go(Mission(MODE, lv=60))
    levels = [t['lv'] for t in nav.where().info.get('tiers', [])]
    print('levels on the card:', levels, flush=True)
    index_path = os.path.join(out, 'index.json')
    index = json.load(open(index_path, encoding='utf-8')) if os.path.exists(index_path) else []
    for lv in levels:
        for k in range(tries):
            try:
                name = 'lv%d_%02d.png' % (lv, k)
                if os.path.exists(os.path.join(out, name)):
                    continue
                nav.go(Mission(MODE, lv=lv))
                if not start_run(nav):
                    print('lv%d #%d: no spawn view' % (lv, k), flush=True)
                    nav.go(World())
                    continue
                time.sleep(1.5)
                nav.b.save_frame(os.path.join(out, name))
                index.append({'file': name, 'lv': lv, 'time': time.strftime('%H:%M:%S')})
                print('lv%d #%d saved' % (lv, k), flush=True)
                # 还没开打，导航会打开局内菜单确认「无奖励」后放弃
                nav.go(Mission(MODE, lv=lv))
                time.sleep(COOL_DOWN)
            except NavError as e:
                print('lv%d #%d: %s' % (lv, k, e), flush=True)
                nav.go(World())
            except OSError as e:
                # 拿不到画面：多半是游戏关了或崩了，停下来别乱按
                print('lv%d #%d: lost the game window (%s), stopping' % (lv, k, e), flush=True)
                return
            with open(os.path.join(out, 'index.json'), 'w', encoding='utf-8') as f:
                json.dump(index, f, ensure_ascii=False, indent=1)
    nav.go(World())
    print('done', len(index), flush=True)


if __name__ == '__main__':
    main()
