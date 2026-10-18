"""Summarise soak case logs: how runs ended, how defence walks went, what went wrong.

    python -m harness.soak_report LOG_GLOB [LOG_GLOB ...]

Counts, over every ok-dna run log given (the soak keeps one per case):
- runs started and completed, give-ups by reason;
- defence walks by how they got to the objective: route replay, marker walk (route learned),
  or the reset fallback;
- run-loop handler errors, re-navigations and navigation failures.
"""
import collections
import glob
import re
import sys

PATTERNS = [
    ('runs started', r'第 \d+ 局开始'),
    ('runs completed', r'已完成 \d+/'),
    ('walk: route replay', r'按路线 \S+ 走'),
    ('walk: learned new route', r'记下这条路线'),
    ('walk: no marker', r'没找到目标标记'),
    ('walk: wave did not start', r'走到了但波次没开始'),
    ('walk: blocked', r'被挡住了'),
    ('walk: reset failed, gave up', r'复位后也没开始波次'),
    ('give up: wave timeout', r'波次超时，放弃这一局'),
    ('give up: no progress (驱离/驱逐/避险)', r'进度停在 .* 不动'),
    ('stopped: gave up too many runs in a row', r'连续放弃了 \d+ 局'),
    ('round dialog stuck, retreated', r'轮次弹窗一直没自动继续'),
    ('handler error, re-navigated', r'处理出错'),
    ('false in-run, re-navigated', r'看着像局内但不是'),
    ('unrecognised screen, re-navigated', r'停在认不出的画面'),
    ('navigation error, back to world', r'导航出错'),
    ('task stopped with an exception', r'exception stopped'),
]


def main():
    paths = sorted({p for pattern in sys.argv[1:] for p in glob.glob(pattern)})
    totals = collections.Counter()
    for path in paths:
        with open(path, encoding='utf-8', errors='replace') as f:
            text = f.read()
        for name, pattern in PATTERNS:
            totals[name] += len(re.findall(pattern, text))
    print('%d logs' % len(paths))
    for name, _ in PATTERNS:
        print('  %-40s %5d' % (name, totals[name]))


if __name__ == '__main__':
    main()
