"""Wrap a live backend and record every screen and transition the navigator goes through."""
import json

from src.nav import screens as S

from harness import privacy
from harness.world import World, region_key


class RecordingBackend:
    def __init__(self, inner, world_root):
        self.inner = inner
        self.world = World.load(world_root)
        self.atlas = S.load_atlas()
        self.start = None
        self.current = None
        self.pending = []
        # every read in order, with the inputs sent before the next one
        self.trace = []

    def __getattr__(self, name):
        return getattr(self.inner, name)

    def read(self):
        scr = self.inner.read()
        screen, info = S.classify(scr, self.atlas)
        sid, oid = self.world.add_state(scr, screen, info)
        self.start = self.start or sid
        if self.current is not None and (self.pending or sid != self.current):
            self.world.add_transition(self.current, self.pending, sid)
        if self.trace:
            self.trace[-1]['actions'] = list(self.pending)
        self.trace.append({'state': sid, 'actions': []} if oid == sid else {'state': sid, 'obs': oid, 'actions': []})
        self.current, self.pending = sid, []
        return scr

    def ocr_region(self, scr, x0, y0, x1, y1, scale=2.0):
        items = self.inner.ocr_region(scr, x0, y0, x1, y1, scale)
        state = self.world.states[self.current]
        visible = privacy.visible(items, state['screen'])
        self.world.add_region(self.current, (x0, y0, x1, y1), visible)
        # the state keeps only the first read, but one state can cover several scroll positions of
        # the level column, so the exact replay needs what this particular read saw
        self.trace[-1].setdefault('regions', {})[region_key((x0, y0, x1, y1))] = visible
        return items

    def click(self, x, y):
        self.pending.append(('click', round(x, 4), round(y, 4)))
        self.inner.click(x, y)

    def drag(self, x0, y0, x1, y1):
        self.pending.append(('drag', round(x0, 4), round(y0, 4), round(x1, 4), round(y1, 4)))
        self.inner.drag(x0, y0, x1, y1)

    def key(self, name):
        self.pending.append(('key', name))
        self.inner.key(name)

    def scroll(self, x, y, notches):
        self.pending.append(('scroll', notches))
        self.inner.scroll(x, y, notches)

    def save(self, trace_path=None):
        self.world.save()
        if trace_path:
            if self.trace:
                self.trace[-1]['actions'] = list(self.pending)
            with open(trace_path, 'w', encoding='utf-8') as f:
                json.dump([dict(step, actions=[list(a) for a in step['actions']]) for step in self.trace], f,
                          ensure_ascii=False, indent=0)
