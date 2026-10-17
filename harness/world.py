"""A recorded slice of the game UI: the screens seen and how actions moved between them.

world.json holds the states and transitions; states/<id>.jpg and states/<id>.json hold each
screen's masked image and OCR items. A state can also hold the result of an enlarged OCR of
part of the screen (Backend.ocr_region), since the downscaled image cannot reproduce it. A transition is (from state, actions, to state), where
actions is the list of inputs sent between two reads; an empty list means the screen changed
by itself (an animation finishing, a loading screen ending).
"""
import hashlib
import json
import os

import cv2
import numpy as np

from harness import privacy

# signature fields per screen; anything that changes what the navigator does must be in here
KEYS = {
    'commission': ('tab',),
    'book': ('section',),
    'menu': ('name',),
    'page': ('name',),
    'start': ('via', 'mode', 'lv', 'column', 'auto_on', 'auto_rounds'),
    'dungeon': ('to_objective',),
    'dungeon_menu': ('nothing_earned',),
    'round_dialog': ('auto',),
    'manual_popup': ('before_run',),
}
SAVE_WIDTH = 1280
CLICK_TOLERANCE = 0.03


def signature(scr, screen, info):
    from src.nav import screens as S
    parts = [screen] + [str(info.get(k)) for k in KEYS.get(screen, ())]
    if screen == 'commission' and info.get('tab') == '夜航手册':
        parts.append(str(S.selected_level(scr, info.get('levels'))))
        parts.append('|'.join(r['name'] for r in S.nightbook_rows(scr)))
    elif screen == 'commission':
        parts.append('|'.join(sorted(i['t'] for i in scr.items if 0.62 < i['y'] < 0.68)))
    elif screen == 'start':
        parts.append('|'.join(e['mode'] for e in info.get('entries', [])))
    elif screen in ('unknown', 'other_menu'):
        parts.append(dhash(scr.img))
    return '/'.join(parts)


def dhash(img):
    small = cv2.resize(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), (9, 8), interpolation=cv2.INTER_AREA)
    bits = (small[:, 1:] > small[:, :-1]).flatten()
    return '%016x' % int(''.join('1' if b else '0' for b in bits), 2)


def region_key(box):
    return ','.join('%.3f' % v for v in box)


def same_action(a, b):
    if a[0] != b[0]:
        return False
    if a[0] in ('click', 'drag'):
        return all(abs(p - q) <= CLICK_TOLERANCE for p, q in zip(a[1:], b[1:]))
    return a[1:] == b[1:]


class World:
    def __init__(self, root):
        self.root = root
        self.states = {}
        self.transitions = []
        self._cache = {}
        self._atlas = None

    @classmethod
    def load(cls, root):
        world = cls(root)
        path = os.path.join(root, 'world.json')
        if os.path.exists(path):
            with open(path, encoding='utf-8') as f:
                data = json.load(f)
            world.states = data['states']
            world.transitions = [dict(t, actions=[tuple(a) for a in t['actions']]) for t in data['transitions']]
        return world

    def save(self):
        os.makedirs(self.root, exist_ok=True)
        data = {'states': self.states,
                'transitions': [dict(t, actions=[list(a) for a in t['actions']]) for t in self.transitions]}
        with open(os.path.join(self.root, 'world.json'), 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=1)

    def add_state(self, scr, screen, info):
        """Store the screen (masked, downscaled) if it is new; return its id.

        The signature is taken from the stored copy, not the live frame, so replaying the
        world sees exactly what was recorded.
        """
        from src.nav import screens as S
        from src.nav.backend import Screen
        img, items = privacy.mask(scr.img, scr.items, screen, info)
        h = int(img.shape[0] * SAVE_WIDTH / img.shape[1])
        img = cv2.resize(img, (SAVE_WIDTH, h), interpolation=cv2.INTER_AREA)
        data = cv2.imencode('.jpg', img, [cv2.IMWRITE_JPEG_QUALITY, 90])[1]
        stored = Screen(cv2.imdecode(data, cv2.IMREAD_COLOR), items)
        if self._atlas is None:
            self._atlas = S.load_atlas()
        stored_screen, stored_info = S.classify(stored, self._atlas)
        sig = signature(stored, stored_screen, stored_info)
        sid = hashlib.sha1(sig.encode('utf-8')).hexdigest()[:10]
        if sid not in self.states:
            folder = os.path.join(self.root, 'states')
            os.makedirs(folder, exist_ok=True)
            with open(os.path.join(folder, sid + '.jpg'), 'wb') as f:
                f.write(data.tobytes())
            with open(os.path.join(folder, sid + '.json'), 'w', encoding='utf-8') as f:
                json.dump(items, f, ensure_ascii=False, indent=0)
            self.states[sid] = {'screen': stored_screen, 'signature': sig}
        return sid

    def add_transition(self, src, actions, dst):
        for t in self.transitions:
            if t['from'] == src and t['to'] == dst and len(t['actions']) == len(actions) \
                    and all(same_action(a, b) for a, b in zip(t['actions'], actions)):
                t['count'] += 1
                return
        self.transitions.append({'from': src, 'actions': list(actions), 'to': dst, 'count': 1})

    def outcomes(self, src, actions):
        """Every state the recording reached from src with these actions, most frequent first.

        The game sometimes ignores an input (a key pressed while it hitches), so the same input
        from the same screen can have been recorded leading to different screens.
        """
        found = [t for t in self.transitions if t['from'] == src and len(t['actions']) == len(actions)
                 and all(same_action(a, b) for a, b in zip(t['actions'], actions))]
        return [t['to'] for t in sorted(found, key=lambda t: -t['count'])]

    def add_region(self, sid, box, items):
        self.states[sid].setdefault('regions', {}).setdefault(region_key(box), items)

    def region(self, sid, box):
        return self.states[sid].get('regions', {}).get(region_key(box), [])

    def image(self, sid):
        if ('img', sid) not in self._cache:
            data = np.fromfile(os.path.join(self.root, 'states', sid + '.jpg'), dtype=np.uint8)
            self._cache[('img', sid)] = cv2.imdecode(data, cv2.IMREAD_COLOR)
        return self._cache[('img', sid)]

    def items(self, sid):
        if ('items', sid) not in self._cache:
            with open(os.path.join(self.root, 'states', sid + '.json'), encoding='utf-8') as f:
                self._cache[('items', sid)] = json.load(f)
        return self._cache[('items', sid)]
