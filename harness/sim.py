"""Replay a recorded world as a backend, so the navigator can run without the game.

The simulator shows the current state's image and OCR items. Inputs are buffered until the
navigator next looks at the screen (read or settle); the buffered inputs then pick the
transition recorded for them. Inputs that were never recorded from this state raise
Unexplored, which means the navigator took a path the recording does not cover.
"""
import cv2

from src.nav.backend import Backend, Screen

from harness.world import World


class Unexplored(AssertionError):
    def __init__(self, world, state, actions):
        info = world.states.get(state, {})
        super().__init__('no recorded transition from %s (%s) for %s' % (state, info.get('signature'), actions))


class SimBackend(Backend):
    def __init__(self, world, start):
        self.world = world if isinstance(world, World) else World.load(world)
        self.state = start
        self.buffer = []
        self.path = [start]

    def frame(self):
        return self.world.image(self.state)

    def ocr(self, img):
        return self.world.items(self.state)

    def _advance(self):
        if self.buffer:
            nxt = self.world.follow(self.state, self.buffer)
            if nxt is None:
                raise Unexplored(self.world, self.state, self.buffer)
            self.buffer = []
        else:
            # nothing sent: the screen may still move on by itself (a loading screen ending)
            nxt = self.world.follow(self.state, [])
        if nxt and nxt != self.state:
            self.state = nxt
            self.path.append(nxt)

    def read(self):
        self._advance()
        return Screen(self.world.image(self.state), self.world.items(self.state))

    def click(self, x, y):
        self.buffer.append(('click', x, y))

    def key(self, name):
        self.buffer.append(('key', name))

    def scroll(self, x, y, notches):
        self.buffer.append(('scroll', notches))

    def sleep(self, seconds):
        pass

    def thumb(self):
        return cv2.resize(cv2.cvtColor(self.frame(), cv2.COLOR_BGR2GRAY), (32, 18)).astype('int16')

    def settle(self, before, *args, **kwargs):
        self._advance()
        return True

    def screens(self):
        return [self.world.states[s]['screen'] for s in self.path]
