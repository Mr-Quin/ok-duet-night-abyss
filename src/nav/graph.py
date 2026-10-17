"""What the navigator knows about the game, kept in tables that modules add to when imported.

  detectors  recognise a screen from a frame:          @detector(order) fn(scr, atlas) -> (screen, info) | None
  edges      take one step from a screen to the next   @edge(from_screen, to_node) fn(nav, scr, here, nxt, info)
             node on a route
  sideways   move between sibling screens directly     @sideways(screens) fn(nav, here, target)
             (book sections, commission tabs)
  handlers   deal with a screen wherever it shows up   @handler(screen) fn(nav, scr, info)
             (popups, in-run dialogs)

A node is (screen, key), e.g. ('commission', '夜航手册'); a key of None on a route matches any key.
Edge and handler functions return True when the target is reached, False after acting, None to
wait for the game, or NotImplemented to fall through to the navigator's own rules.

A mission with its own UI registers its screens, edges and handlers in its own module, and its
target class says the route to it; nothing here or in the navigator needs to change.
"""

DETECTORS = []
EDGES = {}
SIDEWAYS = []
HANDLERS = {}


class NavError(RuntimeError):
    pass


def detector(order):
    def register(fn):
        DETECTORS.append((order, fn))
        DETECTORS.sort(key=lambda d: d[0])
        return fn
    return register


def edge(from_screen, to_node):
    """to_node is a screen name, or a full (screen, key) node for an edge that only leads to that key."""
    def register(fn):
        EDGES[(from_screen, to_node)] = fn
        return fn
    return register


def sideways(screens):
    def register(fn):
        SIDEWAYS.append((frozenset(screens), fn))
        return fn
    return register


def handler(screen):
    def register(fn):
        HANDLERS[screen] = fn
        return fn
    return register


def classify(scr, atlas):
    for _, fn in DETECTORS:
        found = fn(scr, atlas)
        if found:
            return found
    return 'unknown', {}


def find_edge(here, nxt):
    for key in ((here[0], nxt), (here[0], nxt[0]), (None, nxt), (None, nxt[0])):
        if key in EDGES:
            return EDGES[key]
    return None
