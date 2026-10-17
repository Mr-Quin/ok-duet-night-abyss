"""Wrap a live backend and record every screen and transition the navigator goes through."""
from src.nav import screens as S
from src.nav.backend import Backend

from harness.world import World


class RecordingBackend(Backend):
    def __init__(self, inner, world_root):
        self.inner = inner
        self.world = World.load(world_root)
        self.atlas = S.load_atlas()
        self.start = None
        self.current = None
        self.pending = []

    def frame(self):
        return self.inner.frame()

    def ocr(self, img):
        return self.inner.ocr(img)

    def read(self):
        scr = self.inner.read()
        screen, info = S.classify(scr, self.atlas)
        sid = self.world.add_state(scr, screen, info)
        self.start = self.start or sid
        if self.current is not None and (self.pending or sid != self.current):
            self.world.add_transition(self.current, self.pending, sid)
        self.current, self.pending = sid, []
        return scr

    def click(self, x, y):
        self.pending.append(('click', round(x, 4), round(y, 4)))
        self.inner.click(x, y)

    def key(self, name):
        self.pending.append(('key', name))
        self.inner.key(name)

    def scroll(self, x, y, notches):
        self.pending.append(('scroll', notches))
        self.inner.scroll(x, y, notches)

    def park(self):
        self.inner.park()

    def sleep(self, seconds):
        self.inner.sleep(seconds)

    def thumb(self):
        return self.inner.thumb()

    def settle(self, before, *args, **kwargs):
        return self.inner.settle(before, *args, **kwargs)

    def save(self):
        self.world.save()
