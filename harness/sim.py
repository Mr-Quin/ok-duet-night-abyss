"""Replay a recorded world as a backend, so the navigator can run without the game.

TraceBackend replays one recorded journey exactly: it shows the screens in the order they were
read and checks that the navigator sends the same inputs it sent live. Any difference raises
Diverged, which is what a regression test wants.

SimBackend treats the world as a graph instead, so the navigator can be sent to targets in an
order that was never recorded. Inputs are buffered until the navigator next looks at the
screen; they then pick a recorded transition, and inputs never recorded from that screen
raise Unexplored, meaning the recording does not cover that path.
"""
import cv2

from src.nav.backend import Backend, Screen

from harness.world import World, region_key, same_action


class Unexplored(AssertionError):
    def __init__(self, world, state, actions):
        info = world.states.get(state, {})
        super().__init__('no recorded transition from %s (%s) for %s' % (state, info.get('signature'), actions))


class Diverged(AssertionError):
    pass


class TraceBackend(Backend):
    def __init__(self, world, trace):
        self.world = world if isinstance(world, World) else World.load(world)
        self.trace = trace
        self.step = -1
        self.buffer = []

    def seen(self, step):
        entry = self.trace[step]
        return entry.get('obs', entry['state'])

    def frame(self):
        return self.world.image(self.seen(max(self.step, 0)))

    def ocr(self, img):
        return self.world.items(self.seen(max(self.step, 0)))

    def ocr_region(self, scr, x0, y0, x1, y1, scale=2.0):
        step = self.trace[self.step]
        key = region_key((x0, y0, x1, y1))
        if key in step.get('regions', {}):
            return step['regions'][key]
        return self.world.region(step['state'], (x0, y0, x1, y1))

    def read(self):
        if self.step >= 0:
            expected = [tuple(a) for a in self.trace[self.step]['actions']]
            if len(expected) != len(self.buffer) or not all(same_action(a, b) for a, b in zip(expected, self.buffer)):
                info = self.world.states[self.trace[self.step]['state']]
                raise Diverged('step %d on %s: sent %s, recorded %s'
                               % (self.step, info['signature'], self.buffer, expected))
        self.step += 1
        self.buffer = []
        if self.step >= len(self.trace):
            raise Diverged('the navigator kept going after the recording ended')
        seen = self.seen(self.step)
        return Screen(self.world.image(seen), self.world.items(seen))

    def click(self, x, y):
        self.buffer.append(('click', x, y))

    def drag(self, x0, y0, x1, y1):
        self.buffer.append(('drag', x0, y0, x1, y1))

    def key(self, name):
        self.buffer.append(('key', name))

    def scroll(self, x, y, notches):
        self.buffer.append(('scroll', notches))

    def sleep(self, seconds):
        pass

    def thumb(self):
        return cv2.resize(cv2.cvtColor(self.frame(), cv2.COLOR_BGR2GRAY), (32, 18)).astype('int16')

    def settle(self, before, *args, **kwargs):
        return True


class SimBackend(Backend):
    def __init__(self, world, start):
        self.world = world if isinstance(world, World) else World.load(world)
        self.state = start
        self.buffer = []
        self.tries = {}
        self.path = [start]

    def frame(self):
        return self.world.image(self.state)

    def ocr(self, img):
        return self.world.items(self.state)

    def _advance(self):
        actions, self.buffer = self.buffer, []
        # with nothing sent, the screen may still move on by itself (a loading screen ending)
        outcomes = self.world.outcomes(self.state, actions)
        if not outcomes:
            if actions:
                raise Unexplored(self.world, self.state, actions)
            return
        # repeating an input that has several recorded outcomes tries them in turn, the way
        # retrying an ignored key in the game eventually gets through
        key = (self.state, repr(actions))
        tries = self.tries.get(key, 0)
        self.tries[key] = tries + 1
        nxt = outcomes[tries % len(outcomes)]
        if nxt != self.state:
            self.state = nxt
            self.path.append(nxt)

    def ocr_region(self, scr, x0, y0, x1, y1, scale=2.0):
        return self.world.region(self.state, (x0, y0, x1, y1))

    def read(self):
        self._advance()
        return Screen(self.world.image(self.state), self.world.items(self.state))

    def click(self, x, y):
        self.buffer.append(('click', x, y))

    def drag(self, x0, y0, x1, y1):
        self.buffer.append(('drag', x0, y0, x1, y1))

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
