"""Replay recorded frames through the rule-based detectors, without the game.

Each full-size frame that harness/dataset.py saved carries the label the live code gave it.
This runs the current observe() and navigator classifier over those frames and reports where
they now disagree, plus how long each look takes. Point DNA_REPLAY at a dataset folder (one
recording session, or a parent of several); with nothing there the test is skipped.

    set DNA_REPLAY=C:\\Users\\H\\projects\\dataset
    python -m unittest harness.test_replay
"""
import collections
import glob
import json
import os
import time
import unittest

from ok.test.TaskTestCase import TaskTestCase

from src.config import config
from src.nav import screens as S
from src.nav.okscript import OkScriptBackend
from src.run.observe import observe
from src.tasks.fullauto.AutoNightbookTask import AutoNightbookTask

ROOT = os.environ.get('DNA_REPLAY', '')
# the live label was itself a rule-based guess; a few disagreements on transition frames are expected
MIN_AGREEMENT = 0.97


def recorded(root):
    for index in sorted(glob.glob(os.path.join(root, '**', 'labels.jsonl'), recursive=True)):
        folder = os.path.dirname(index)
        with open(index, encoding='utf-8') as f:
            for line in f:
                row = json.loads(line)
                if row.get('full'):
                    yield os.path.join(folder, 'full', row['file']), row


@unittest.skipUnless(ROOT and os.path.isdir(ROOT), 'set DNA_REPLAY to a recorded dataset folder')
class TestReplay(TaskTestCase):
    task_class = AutoNightbookTask
    config = config

    def test_detectors_agree_with_the_recorded_labels(self):
        atlas = S.load_atlas()
        counts, misses, timings = collections.Counter(), [], collections.defaultdict(list)
        for path, row in recorded(ROOT):
            if not os.path.exists(path):
                continue
            self.set_image(path)
            t0 = time.perf_counter()
            if row['source'] == 'phase':
                found = observe(self.task)
            else:
                found, _ = S.classify(OkScriptBackend(self.task).read(), atlas)
            timings[row['source']].append(time.perf_counter() - t0)
            counts[row['source'], found == row['label']] += 1
            if found != row['label']:
                misses.append('%s: recorded %s, now %s' % (os.path.relpath(path, ROOT), row['label'], found))
        total = sum(counts.values())
        self.assertGreater(total, 0, 'no full-size frames under %s' % ROOT)
        for source, values in timings.items():
            agree = counts[source, True] / (counts[source, True] + counts[source, False])
            print('%s: %d frames, %.1f%% agree, %.0f ms per look' % (
                source, len(values), 100 * agree, 1000 * sum(values) / len(values)))
        for miss in misses[:40]:
            print('  ' + miss)
        agreement = sum(v for (s, ok), v in counts.items() if ok) / total
        self.assertGreaterEqual(agreement, MIN_AGREEMENT, '%d of %d frames disagree' % (len(misses), total))

    def test_the_book_level_column_reads_on_recorded_book_pages(self):
        from src.nav.backend import Screen
        read = total = 0
        for path, row in recorded(ROOT):
            info = row.get('info') or {}
            if row['source'] != 'screen' or row['label'] != 'commission' or info.get('tab') != '夜航手册':
                continue
            if not os.path.exists(path):
                continue
            self.set_image(path)
            backend = OkScriptBackend(self.task)
            scr = backend.read()
            levels = S.level_positions(Screen(scr.img, backend.ocr_region(scr, *S.LEVEL_COLUMN)))
            total += 1
            read += bool(levels)
        print('level column read on %d of %d book pages' % (read, total))
        if total:
            self.assertGreaterEqual(read / total, 0.95)


if __name__ == '__main__':
    unittest.main()
