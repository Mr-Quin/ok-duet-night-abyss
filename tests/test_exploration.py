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


def box(text):
    return 'explore_' + text


class TestOperate(unittest.TestCase):

    def test_interacts_then_quick_solves(self):
        task = FakeTask({box(X.PROMPT): ['', X.PROMPT], box(X.QUICK_SOLVE): ['', X.QUICK_SOLVE, X.QUICK_SOLVE, ''],
                         box(X.SOLVED): ['']})
        self.assertTrue(X.Exploration(task).operate())
        # 提示没出来时往前挪一步，交互键打开机关，F 快速破解
        self.assertEqual(task.keys, ['w', 'g', 'f'])

    def test_gives_up_when_the_prompt_never_shows(self):
        task = FakeTask({box(X.PROMPT): ['']})
        self.assertFalse(X.Exploration(task).operate())
        self.assertEqual(task.keys, ['w'] * X.NUDGES)


if __name__ == '__main__':
    unittest.main()
