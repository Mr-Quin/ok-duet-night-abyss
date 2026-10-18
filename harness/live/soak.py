"""Soak test for the nightbook task: run cases through the real ok-dna task on the game PC.

Each case puts the game in a known place with the navigator, starts the task with a config,
waits for the run count to be reached in ok-dna's log, and checks the game is back in the
open world. Run on the game PC with the live service up and the game in the foreground:

    python -m harness.live.soak soak.jsonl            (every case)
    python -m harness.live.soak soak.jsonl sweep       (only cases whose name contains "sweep")

The task is started through a scheduled task, so ok-dna runs in the desktop session even when
this script is started over ssh. The scheduled task must run `main.py -t <n>`, n being the 1-based
position of AutoNightbookTask in src/config.py's onetime_tasks, with its output redirected to
logs/run.txt, the way run_plan.cmd does.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import time

from src.nav import MainMenu, Nav, Nightbook, World
from src.tasks.fullauto.AutoNightbookTask import BOOK_LEVELS, COMMISSION_LEVELS, SOURCES

from harness.live.backend import LiveBackend

SCHEDULED_TASK = 'okdna_fork'
TASK_CONFIG = os.path.join('configs', 'AutoNightbookTask.json')
RUN_LOG = os.path.join('logs', 'run.txt')
CACHE = os.path.join('configs', 'nav_cache.json')
# ok-dna's log says 已完成 n/m after every finished run
DONE = '已完成 %d/%d'
EVENTS = re.compile(r'地图 |导航到|局开始|按标记|按路线|没有对上|已到达目标|当作到了|波次没开始|被挡住|没找到目标标记|标记丢失|'
                    r'走到目标超时|复位|超时|撤离|放弃|处理出错|认不出|当前轮次|已完成 |exception stopped|^Exception')


def book(lv, row, rounds=2, runs=1):
    return {'超时时间': 90, '来源': SOURCES[0], '等级': 'Lv.%d' % lv, '第几个': row, '每局轮次': rounds, '刷几次': runs}


def commission(lv, rounds=1, runs=4):
    return {'超时时间': 90, '来源': SOURCES[1], '等级': 'Lv.%d' % lv, '每局轮次': rounds, '刷几次': runs}


def book_rows(lv):
    try:
        with open(CACHE, encoding='utf-8') as f:
            return len(json.load(f).get('names/%d' % lv, []))
    except OSError:
        return 0


class Soak:
    def __init__(self, out):
        self.out = out
        self.nav = Nav(LiveBackend(), cache_path=CACHE, log=lambda m: None)

    def where(self):
        state = self.nav.where()
        return 'world' if state.screen == 'world' and not state.in_run else state.screen

    def ensure_world(self):
        self.stop_okdna()
        if self.where() != 'world':
            self.nav.go(World())
        return self.where()

    def okdna_pids(self):
        out = subprocess.run(['powershell', '-NoProfile', '-Command',
                              "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'main\\.py -t \\d+' } "
                              "| ForEach-Object { $_.ProcessId }"], capture_output=True, text=True).stdout
        return [int(p) for p in out.split()]

    def stop_okdna(self):
        for pid in self.okdna_pids():
            subprocess.run(['taskkill', '/F', '/PID', str(pid)], capture_output=True)

    def start(self, config):
        self.stop_okdna()
        with open(TASK_CONFIG, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False)
        # the ok-dna process just killed can hold the log open for a moment; if it never lets go,
        # read only what this case appends
        self.log_offset = 0
        for _ in range(10):
            try:
                if os.path.exists(RUN_LOG):
                    os.remove(RUN_LOG)
                break
            except PermissionError:
                time.sleep(1)
        else:
            self.log_offset = os.path.getsize(RUN_LOG)
        subprocess.run(['schtasks', '/run', '/tn', SCHEDULED_TASK], capture_output=True, check=True)

    def log_lines(self):
        try:
            with open(RUN_LOG, 'rb') as f:
                f.seek(getattr(self, 'log_offset', 0))
                return f.read().decode('utf-8', errors='replace').splitlines()
        except OSError:
            return []

    def wait_for(self, pattern, timeout):
        deadline = time.time() + timeout
        while time.time() < deadline:
            text = '\n'.join(self.log_lines())
            if 'exception stopped' in text:
                return 'exception'
            if re.search(pattern, text):
                return 'ok'
            time.sleep(5)
        return 'timeout'

    def finish(self, name, status, t0):
        if status == 'ok':
            # going home from the result screen passes through the commission page first
            deadline = time.time() + 60
            end = self.where()
            while end != 'world' and time.time() < deadline:
                time.sleep(5)
                end = self.where()
            status = 'pass' if end == 'world' else 'ended on ' + end
        if os.path.exists(RUN_LOG):
            shutil.copy(RUN_LOG, '%s.%s.log' % (self.out, re.sub(r'\W+', '_', name)))
        events = [l.rstrip()[:140] for l in self.log_lines() if EVENTS.search(l)]
        walks = sum(1 for e in events if '已到达目标' in e)
        row = {'case': name, 'status': status, 'walks': walks, 'seconds': round(time.time() - t0), 'events': events[-40:]}
        with open(self.out, 'a', encoding='utf-8') as f:
            f.write(json.dumps(row, ensure_ascii=False) + '\n')
        print(time.strftime('%H:%M:%S'), name, status, 'walks', walks, flush=True)
        return status == 'pass'

    def run_case(self, name, config, runs=1, timeout=420, before=None):
        self.ensure_world()
        if before:
            before(self.nav)
        t0 = time.time()
        self.start(config)
        return self.finish(name, self.wait_for(DONE % (runs, runs), timeout), t0)

    def restart_inside_run(self, name):
        """Stop ok-dna once a run has started, then start the task again from inside the run."""
        self.ensure_world()
        t0 = time.time()
        self.start(book(30, 2))
        self.wait_for('局开始', 240)
        time.sleep(10)
        self.stop_okdna()
        time.sleep(5)
        self.start(book(30, 2))
        return self.finish(name, self.wait_for(DONE % (1, 1), 600), t0)


def cases(soak):
    # every row the navigator has seen on each book page, one run each
    for lv in BOOK_LEVELS:
        for row in range(1, book_rows(lv) + 1):
            name = 'book Lv.%d #%d' % (lv, row)
            yield name, lambda name=name, lv=lv, row=row: soak.run_case(name, book(lv, row))
    yield 'multi-run Lv.65 #5 3x3', lambda: soak.run_case(
        'multi-run Lv.65 #5 3x3', book(65, 5, rounds=3, runs=3), runs=3, timeout=900)
    yield 'multi-run 驱离 Lv.60 #1 x3', lambda: soak.run_case(
        'multi-run 驱离 Lv.60 #1 x3', book(60, 1, runs=3), runs=3, timeout=900)
    yield 'from main menu', lambda: soak.run_case(
        'from main menu', book(30, 3), before=lambda nav: nav.go(MainMenu()))
    yield 'from another start screen', lambda: soak.run_case(
        'from another start screen', book(30, 1), before=lambda nav: nav.go(Nightbook(65, 3)))
    yield 'restart inside a run', lambda: soak.restart_inside_run('restart inside a run')
    yield 'one round per run', lambda: soak.run_case(
        'one round per run', book(30, 2, rounds=1), timeout=600)
    for lv in COMMISSION_LEVELS:
        # 每次「再次进行」都从这个等级的地图里重新抽一张
        yield 'maps Lv.%d' % lv, lambda lv=lv: soak.run_case(
            'maps Lv.%d' % lv, commission(lv), runs=4, timeout=1200)
    for lv in COMMISSION_LEVELS:
        yield 'pool Lv.%d' % lv, lambda lv=lv: soak.run_case(
            'pool Lv.%d' % lv, commission(lv, runs=10), runs=10, timeout=2400)


def main():
    out, pick = sys.argv[1], (sys.argv[2] if len(sys.argv) > 2 else '')
    soak = Soak(out)
    # "row 60 1 2,row 30 2 2" runs book rows directly: level, row, runs
    rows = [p.split()[1:] for p in pick.split(',') if p.startswith('row ')]
    if rows:
        results = [soak.run_case('row Lv.%s #%s x%s' % (lv, row, runs), book(int(lv), int(row), runs=int(runs)),
                                 runs=int(runs), timeout=600 * int(runs)) for lv, row, runs in rows]
    else:
        results = [case() for name, case in cases(soak) if pick in name]
    soak.ensure_world()
    print('passed %d/%d' % (sum(results), len(results)), flush=True)
    sys.exit(0 if all(results) else 1)


if __name__ == '__main__':
    main()
