"""How long navigation takes in recorded ok-dna runs, and how many steps.

    python -m harness.nav_timing LOG [LOG ...]

Reads ok-dna run logs (the copies the soak keeps per case) and prints, for every navigation,
its duration, step count and seconds per step, then totals. Navigation starts at the task's
导航到 line or a 重新导航 retry and ends at the navigator's 步到达 line.
"""
import re
import sys
from datetime import datetime

LINE = re.compile(r'^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d,\d{3}) .*?AutoNightbookTask:(.*)$')


def stamp(text):
    return datetime.strptime(text, '%Y-%m-%d %H:%M:%S,%f')


def navigations(path):
    start = None
    with open(path, encoding='utf-8', errors='replace') as f:
        for line in f:
            m = LINE.match(line)
            if not m:
                continue
            t, msg = stamp(m.group(1)), m.group(2)
            if '导航到' in msg or '重新导航' in msg or '回大世界重来' in msg:
                start = t
            hit = re.search(r'(\d+) 步到达', msg)
            if hit and start:
                yield (t - start).total_seconds(), int(hit.group(1))
                start = None


def main():
    all_rows = []
    for path in sys.argv[1:]:
        for seconds, steps in navigations(path):
            all_rows.append((seconds, steps))
            print('%-50s %6.1f s %3d steps' % (path[-50:], seconds, steps))
    if all_rows:
        total = sum(s for s, _ in all_rows)
        steps = sum(n for _, n in all_rows)
        print('%d navigations, %.0f s total, %.1f s average, %.2f s per step' % (
            len(all_rows), total, total / len(all_rows), total / max(1, steps)))


if __name__ == '__main__':
    main()
