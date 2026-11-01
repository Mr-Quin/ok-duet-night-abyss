import os
from ok.test.TaskTestCase import TaskTestCase
from src.config import config
from src.nav import screens as S
from src.nav.okscript import OkScriptBackend
from src.run import observe as O
from src.tasks.fullauto.AutoNightbookTask import AutoNightbookTask
from src.tasks.fullauto.marker_walk import MarkerWalk

FRAMES = r'C:\Users\H\projects\dna-nav\sessions\20261019-043715\frames'
PICK = ['000033', '000050', '000085', '000100', '000110', '000220', '000286', '000290', '000294', '000301', '000312', '000340']


class Probe(TaskTestCase):
    task_class = AutoNightbookTask
    config = config

    def test_probe(self):
        atlas = S.load_atlas()
        for name in PICK:
            path = os.path.join(FRAMES, name + '.jpg')
            self.set_image(path)
            scr = OkScriptBackend(self.task).read()
            screen, info = S.classify(scr, atlas)
            plain = {k: v for k, v in info.items() if isinstance(v, (str, int, bool, type(None)))}
            try:
                phase = O.observe(self.task)
            except Exception as e:
                phase = 'error %s' % e
            seen = MarkerWalk(self.task).find(self.task.frame)
            print('== %s screen=%s phase=%s marker=%s %s' % (name, screen, phase, seen, plain))
            if screen == 'start':
                print('   entries', info.get('entries'), 'tiers', [(t['lv'], round(t['y'], 3)) for t in info.get('tiers', [])])
            keys = ('操作', '快速破解', '破解成功', '调查目标', '制作血清', '血清', '米', '刷新', '无尽', '选择密函', '匹配挑战')
            for i in sorted(scr.items, key=lambda i: (round(i['y'], 2), i['x'])):
                if any(k in i['t'] for k in keys):
                    print('   %.3f %.3f %r' % (i['x'], i['y'], i['t']))
