"""Black out personal details in a captured frame before it is saved anywhere.

Regions are fractions of the frame, chosen per screen kind so they never cover what the
navigator reads. OCR items inside a blacked-out region are dropped as well, since the text
(a UID, a player name, a chat line) would otherwise survive in the saved JSON.
"""

UID = (0.38, 0.955, 0.64, 1.0)
CHAT = (0.0, 0.94, 0.45, 1.0)
WALLET = (0.76, 0.0, 1.0, 0.06)
TEAM_PRESET = (0.72, 0.10, 0.98, 0.21)
PARTY = (0.02, 0.82, 0.16, 0.935)
SKILLS = (0.78, 0.78, 1.0, 0.99)
CHARACTER = (0.30, 0.47, 0.76, 0.93)
QUEST = (0.0, 0.2, 0.2, 0.4)
LEVEL_BANNER = (0.40, 0.09, 0.60, 0.24)
PROFILE = [(0.055, 0.005, 0.335, 0.118), (0.17, 0.13, 0.335, 0.18), (0.20, 0.18, 0.335, 0.21)]
RESULT_TEAM = (0.0, 0.0, 0.64, 0.545)
MENU_TEAM = (0.57, 0.72, 1.0, 0.868)
MAP_PLACES = [(0.82, 0.83, 1.0, 0.905), (0.06, 0.84, 0.2, 0.905)]


def regions(screen, info=None):
    info = info or {}
    out = [UID, WALLET]
    if screen == 'world':
        out += [PARTY, SKILLS, CHARACTER, QUEST]
    elif screen == 'dungeon':
        out += [PARTY, SKILLS, CHARACTER, LEVEL_BANNER]
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
    if screen == 'menu' and info.get('name') == '地图':
        out += MAP_PLACES
    return out


def mask(img, items, screen, info=None):
    """Return a masked copy of img and the OCR items that fall outside the masked regions."""
    out = img.copy()
    H, W = out.shape[:2]
    boxes = regions(screen, info)
    for x0, y0, x1, y1 in boxes:
        out[int(y0 * H):int(y1 * H), int(x0 * W):int(x1 * W)] = 0
    kept = [i for i in items if not any(x0 <= i['x'] <= x1 and y0 <= i['y'] <= y1 for x0, y0, x1, y1 in boxes)]
    return out, kept
