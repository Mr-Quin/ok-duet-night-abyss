"""Black out personal details in a captured frame before it is saved anywhere.

Regions are fractions of the frame, chosen per screen kind so they never cover what the
navigator reads. OCR items inside a blacked-out region are dropped as well, since the text
(a UID, a player name, a chat line) would otherwise survive in the saved JSON.

Screens drawn over the open world or a run show the player's characters behind them, so for
those only the panels the navigator reads are kept and everything else is blacked out. Frames
that could not be recognised are blacked out entirely; the navigator only waits on them.
"""

UID = (0.38, 0.955, 0.64, 1.0)
CHAT = (0.0, 0.94, 0.45, 1.0)
WALLET = (0.66, 0.0, 1.0, 0.06)
TEAM_PRESET = (0.72, 0.10, 0.98, 0.21)
PARTY = (0.02, 0.82, 0.16, 0.935)
HP = (0.185, 0.93, 0.3, 0.99)
MANUAL_COUNTS = (0.3, 0.455, 0.72, 0.5)
LETTER_COUNTS = (0.05, 0.415, 0.68, 0.45)
SKILLS = (0.78, 0.78, 1.0, 0.99)
CHARACTER = (0.30, 0.47, 0.76, 0.93)
QUEST = (0.0, 0.2, 0.2, 0.4)
LEVEL_BANNER = (0.40, 0.09, 0.60, 0.24)
PROFILE = [(0.055, 0.005, 0.335, 0.13), (0.17, 0.13, 0.335, 0.18), (0.20, 0.18, 0.335, 0.21)]
RESULT_TEAM = (0.0, 0.0, 0.64, 0.545)
MENU_TEAM = (0.57, 0.72, 1.0, 0.868)
MAP_PLACES = [(0.82, 0.83, 1.0, 0.905), (0.06, 0.84, 0.2, 0.905)]

KEEP = {
    'dungeon_menu': [(0.0, 0.64, 0.2, 0.76), (0.22, 0.83, 0.4, 0.89), (0.57, 0.86, 1.0, 0.97)],
    'result': [(0.0, 0.6, 0.2, 0.7), (0.72, 0.94, 1.0, 1.0), (0.85, 0.03, 1.0, 0.08)],
    'exit_confirm': [(0.23, 0.38, 0.77, 0.64)],
    'round_dialog': [(0.3, 0.0, 0.7, 0.13), (0.11, 0.24, 0.89, 0.76)],
    'manual_popup': [(0.22, 0.26, 0.78, 0.74)],
    'main_menu': [(0.0, 0.0, 0.34, 1.0)],
    'world': [(0.0, 0.9, 0.2, 1.0)],
    'unknown': [],
    'other_menu': [],
}

ALL = [UID, WALLET, CHAT, PARTY, HP, SKILLS, CHARACTER, QUEST, LEVEL_BANNER, TEAM_PRESET, MENU_TEAM] + PROFILE + MAP_PLACES


def regions(screen, info=None):
    info = info or {}
    if screen in ('unknown', 'other_menu'):
        # a frame caught mid-transition can be anything, a fading main menu included
        return ALL
    out = [UID, WALLET]
    if screen == 'world':
        out += [PARTY, HP, SKILLS, CHARACTER, QUEST]
    elif screen == 'dungeon':
        out += [PARTY, HP, SKILLS, CHARACTER, LEVEL_BANNER]
    else:
        out += [CHAT]
    if screen == 'main_menu':
        out += PROFILE
    if screen == 'start':
        out.append(TEAM_PRESET)
    if screen == 'result':
        out.append(RESULT_TEAM)
    if screen == 'dungeon_menu':
        out.append(MENU_TEAM)
    if screen == 'manual_popup':
        out.append(MANUAL_COUNTS)
    if screen == 'commission' and info.get('tab') == '委托密函':
        out.append(LETTER_COUNTS)
    if screen == 'menu' and info.get('name') == '地图':
        out += MAP_PLACES
    return out


def inside(item, boxes):
    return any(x0 <= item['x'] <= x1 and y0 <= item['y'] <= y1 for x0, y0, x1, y1 in boxes)


def visible(items, screen, info=None):
    """The OCR items that mask() would keep."""
    keep = KEEP.get(screen)
    boxes = regions(screen, info)
    return [i for i in items if (keep is None or inside(i, keep)) and not inside(i, boxes)]


def mask(img, items, screen, info=None):
    """Return a masked copy of img and the OCR items that fall outside the masked regions."""
    H, W = img.shape[:2]
    keep = KEEP.get(screen)
    if keep is not None:
        out = img * 0
        for x0, y0, x1, y1 in keep:
            sl = slice(int(y0 * H), int(y1 * H)), slice(int(x0 * W), int(x1 * W))
            out[sl] = img[sl]
    else:
        out = img.copy()
    for x0, y0, x1, y1 in regions(screen, info):
        out[int(y0 * H):int(y1 * H), int(x0 * W):int(x1 * W)] = 0
    return out, visible(items, screen, info)
