"""Soak test for the 30/65 task: run cases through the real ok-dna task on the game PC.

Each case puts the game in a known place with the navigator, starts the task with a config,
waits for the run count to be reached in ok-dna's log, and checks the game is back in the
open world. Run on the game PC with the live service up and the game in the foreground:

    python -m harness.live.soak soak.jsonl            (every case)
    python -m harness.live.soak soak.jsonl sweep       (only cases whose name contains "sweep")

The task is started through a scheduled task, so ok-dna runs in the desktop session even when
this script is started over ssh. The scheduled task must run `main.py -t <n>`, n being the 1-based
position of Auto65NavTask in src/config.py's onetime_tasks, with its output redirected to
logs/run.txt, the way run_plan.cmd does.
"""
import json
import os
import re
import subprocess
import sys
import time

from src.nav import MainMenu, Nav, Nightbook, World
from src.tasks.fullauto.Auto65NavTask import NIGHTBOOK_ENTRIES

from harness.live.backend import LiveBackend

SCHEDULED_TASK = 'okdna_fork'
TASK_CONFIG = os.path.join('configs', 'Auto65NavTask.json')
RUN_LOG = os.path.join('logs', 'run.txt')
CACHE = os.path.join('configs', 'nav_cache.json')
# ok-dna's log says 已完成 n/m after every finished run
DONE = '已完成 %d/%d'
EVENTS = re.compile(r'导航到|按标记直线走|已到达目标|没找到目标标记|标记丢失|走到目标超时|当前轮次|终止任务|已完成 |exception stopped|^Exception')


def entry(lv, i):
    return 'Lv.%d 第%d个 %s' % (lv, i + 1, NIGHTBOOK_ENTRIES[lv][i])


def cfg(target, rounds=2, runs=1, walk='按标记直线走'):
    return {'超时时间': 90, '关卡': target, '每局轮次': rounds, '刷几次': runs, '走位方式': walk}


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
        if os.path.exists(RUN_LOG):
            os.remove(RUN_LOG)
        subprocess.run(['schtasks', '/run', '/tn', SCHEDULED_TASK], capture_output=True, check=True)

    def log_lines(self):
        try:
            with open(RUN_LOG, encoding='utf-8', errors='replace') as f:
                return f.read().splitlines()
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
            time.sleep(15)
            end = self.where()
            status = 'pass' if end == 'world' else 'ended on ' + end
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
        """Stop ok-dna once combat has started, then start the task again from inside the run."""
        self.ensure_world()
        t0 = time.time()
        self.start(cfg(entry(30, 1)))
        self.wait_for('战斗开始', 240)
        self.stop_okdna()
        time.sleep(5)
        self.start(cfg(entry(30, 1)))
        return self.finish(name, self.wait_for(DONE % (1, 1), 600), t0)


def cases(soak):
    for lv in (30, 65):
        for i in range(len(NIGHTBOOK_ENTRIES[lv])):
            yield 'sweep Lv.%d #%d' % (lv, i + 1), lambda lv=lv, i=i: soak.run_case(
                'sweep Lv.%d #%d' % (lv, i + 1), cfg(entry(lv, i)))
    yield 'multi-run Lv.65 #5 2x3', lambda: soak.run_case(
        'multi-run Lv.65 #5 2x3', cfg(entry(65, 4), rounds=3, runs=3), runs=3, timeout=900)
    yield 'from main menu', lambda: soak.run_case(
        'from main menu', cfg(entry(30, 2)), before=lambda nav: nav.go(MainMenu()))
    yield 'from another start screen', lambda: soak.run_case(
        'from another start screen', cfg(entry(30, 0)), before=lambda nav: nav.go(Nightbook(65, 3)))
    yield 'restart inside a run', lambda: soak.restart_inside_run('restart inside a run')
    yield 'one round per run', lambda: soak.run_case(
        'one round per run', cfg(entry(30, 1), rounds=1), timeout=600)


def main():
    out, pick = sys.argv[1], (sys.argv[2] if len(sys.argv) > 2 else '')
    soak = Soak(out)
    results = [case() for name, case in cases(soak) if pick in name]
    soak.ensure_world()
    print('passed %d/%d' % (sum(results), len(results)), flush=True)
    sys.exit(0 if all(results) else 1)


if __name__ == '__main__':
    main()
