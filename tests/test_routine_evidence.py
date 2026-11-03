# 流程的检查点记录：每次一个文件夹，记录一行加一张缩小的画面，只留最新的几次，记录出错不影响任务
import os
import tempfile
import time
import unittest

import cv2
import numpy as np

from src.routine.evidence import Evidence, checkpoint

NOON = time.struct_time((2026, 11, 2, 12, 0, 0, 0, 306, -1))


def frame():
    return np.zeros((1440, 2560, 3), np.uint8)


class FakeTask:
    def __init__(self, evidence=None):
        self.evidence = evidence
        self.frame = frame()
        self.logs = []
        self.sent = []

    def log_info(self, message, notify=False, images=None):
        self.logs.append(message)
        if notify:
            self.sent.append((message, images))


class Broken:
    def record(self, slug, text, frame=None):
        raise OSError('磁盘满了')


class TestEvidence(unittest.TestCase):

    def setUp(self):
        self.root = tempfile.mkdtemp()

    def read_report(self, evidence):
        with open(os.path.join(evidence.folder, 'report.txt'), encoding='utf-8') as f:
            return f.read().splitlines()

    def test_each_checkpoint_writes_a_line_and_a_small_jpg(self):
        evidence = Evidence(self.root, clock=lambda: NOON)
        self.assertEqual(os.path.basename(evidence.folder), '20261102-120000')
        evidence.record('run1-start', '第 1 局开始（扼守）', frame())
        evidence.record('note', '没有画面')
        self.assertEqual(self.read_report(evidence),
                         ['12:00:00 01 第 1 局开始（扼守）  [01-run1-start.jpg]', '12:00:00 02 没有画面'])
        with open(os.path.join(evidence.folder, '01-run1-start.jpg'), 'rb') as f:
            img = cv2.imdecode(np.frombuffer(f.read(), np.uint8), cv2.IMREAD_COLOR)
        self.assertEqual(img.shape[:2], (720, 1280))

    def test_two_runs_in_the_same_second_get_separate_folders(self):
        first = Evidence(self.root, clock=lambda: NOON)
        second = Evidence(self.root, clock=lambda: NOON)
        self.assertNotEqual(first.folder, second.folder)

    def test_only_the_newest_runs_are_kept(self):
        for minute in range(4):
            Evidence(self.root, keep=2, clock=lambda: time.struct_time((2026, 11, 2, 12, minute, 0, 0, 306, -1)))
        self.assertEqual(sorted(os.listdir(self.root)), ['20261102-120200', '20261102-120300'])


class TestCheckpoint(unittest.TestCase):

    def test_records_the_task_frame(self):
        evidence = Evidence(tempfile.mkdtemp(), clock=lambda: NOON)
        checkpoint(FakeTask(evidence), 'claims', '领完了：历练')
        self.assertEqual(sorted(os.listdir(evidence.folder)), ['01-claims.jpg', 'report.txt'])

    def test_outside_a_routine_it_only_logs(self):
        task = FakeTask()
        checkpoint(task, 'claims', '领完了：历练')
        self.assertEqual(task.logs, ['领完了：历练'])

    def test_a_notified_checkpoint_sends_the_frame_along(self):
        task = FakeTask()
        checkpoint(task, 'end', '流程跑完了：2 步', notify=True)
        [(message, images)] = task.sent
        self.assertEqual(message, '流程跑完了：2 步')
        self.assertIs(images, task.frame)

    def test_a_recording_error_is_logged_not_raised(self):
        task = FakeTask(Broken())
        checkpoint(task, 'claims', '领完了：历练')
        self.assertEqual(task.logs[0], '领完了：历练')
        self.assertIn('磁盘满了', task.logs[1])


if __name__ == '__main__':
    unittest.main()
