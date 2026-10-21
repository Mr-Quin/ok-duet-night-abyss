# 探险开局：走到装置前按交互键打开机关，再按 F 快速破解
import unittest

from src.run import exploration as X


class FakeTask:
    """shown 按 box 名给出每次 OCR 读到的文字，用完后重复最后一个。"""

    def __init__(self, shown):
        self.shown = {k: list(v) for k, v in shown.items()}
        self.keys = []

    def box_of_screen(self, *args, name=None):
        return name

    def ocr(self, box=None, match=None):
        seq = self.shown.get(box, [''])
        text = seq.pop(0) if len(seq) > 1 else seq[0]
        return [type('Box', (), {'name': text})()] if text else []

    def wait_until(self, condition, time_out=0, post_action=None, raise_if_not_found=False):
        for _ in range(5):
            if condition():
                return True
            post_action()
        return False

    def send_key(self, key, down_time=None):
        self.keys.append(key)

    def get_interact_key(self):
        return 'g'

    def sleep(self, seconds):
        pass

    def log_info(self, msg):
        pass

    def next_frame(self):
        return None


class FakeWalker:
    """seen 是每次 find() 看到的标记，用完后重复最后一个。"""

    def __init__(self, seen=(None,)):
        self.seen = list(seen)
        self.turns = []

    def find(self, frame):
        return self.seen.pop(0) if len(self.seen) > 1 else self.seen[0]

    def face(self, x):
        self.turns.append(x)


def box(text):
    return 'explore_' + text


class TestOperate(unittest.TestCase):

    def test_interacts_then_quick_solves(self):
        task = FakeTask({box(X.PROMPT): ['', X.PROMPT], box(X.QUICK_SOLVE): ['', X.QUICK_SOLVE, X.QUICK_SOLVE, ''],
                         box(X.SOLVED): ['']})
        self.assertTrue(X.Exploration(task).operate(FakeWalker()))
        # 提示没出来时往前挪一步，交互键打开机关，F 快速破解
        self.assertEqual(task.keys, ['w', 'g', 'f'])

    def test_gives_up_when_the_prompt_never_shows(self):
        task = FakeTask({box(X.PROMPT): ['']})
        self.assertFalse(X.Exploration(task).operate(FakeWalker()))
        self.assertEqual(task.keys, ['w'] * X.NUDGES)

    def test_the_markers_own_label_is_not_the_prompt(self):
        task = FakeTask({box(X.PROMPT): ['操作装置']})
        self.assertFalse(X.Exploration(task).operate(FakeWalker()))
        self.assertEqual(task.keys, ['w'] * X.NUDGES)

    def test_turns_to_a_device_beside_the_character_before_stepping(self):
        task = FakeTask({box(X.PROMPT): ['', '', X.PROMPT], box(X.QUICK_SOLVE): ['', X.QUICK_SOLVE, ''],
                         box(X.SOLVED): ['']})
        walker = FakeWalker([(0.4, 2), (0.1, 2), (0.01, 1)])
        self.assertTrue(X.Exploration(task).operate(walker))
        # 偏得多时只转不走，转得差不多了边转边走
        self.assertEqual(walker.turns, [0.4, 0.1])
        self.assertEqual(task.keys[:2], ['w', 'g'])


if __name__ == '__main__':
    unittest.main()
