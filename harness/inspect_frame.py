"""Print what the navigator sees on saved frames: screen, info, and the OCR text in a region.

    set DNA_FRAMES=path1.jpg;path2.jpg
    set DNA_REGION=0,0.2,0.3,0.45
    python -m unittest harness.inspect_frame

A unittest only because ok-script's OCR needs its test runner to start.
"""
import os

from ok.test.TaskTestCase import TaskTestCase

from src.config import config
from src.nav import screens as S
from src.nav.okscript import OkScriptBackend
from src.tasks.fullauto.AutoNightbookTask import AutoNightbookTask


class InspectFrames(TaskTestCase):
    task_class = AutoNightbookTask
    config = config

    def test_print(self):
        region = [float(v) for v in os.environ.get('DNA_REGION', '0,0,1,1').split(',')]
        for path in filter(None, os.environ.get('DNA_FRAMES', '').split(';')):
            self.set_image(path)
            scr = OkScriptBackend(self.task).read()
            screen, info = S.classify(scr, S.load_atlas())
            print('== %s -> %s %s' % (path, screen, {k: v for k, v in info.items() if isinstance(v, (str, int, bool))}))
            for i in sorted(scr.items, key=lambda i: (round(i['y'], 2), i['x'])):
                if region[0] <= i['x'] <= region[2] and region[1] <= i['y'] <= region[3]:
                    print('   %.3f %.3f %r' % (i['x'], i['y'], i['t']))
