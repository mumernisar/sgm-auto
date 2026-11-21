"""Read the event node map: nodes, current position, which nodes are reachable (unlocked), boss nodes. Node scores
aren't read: event nodes unlock one after another and any open one will do (scores only matter in prize fights)."""
from dataclasses import dataclass, field

import cv2
import numpy as np

from . import control
from . import vision as v
from .frame import k_of

# a freshly started game opens maps zoomed in to ~1.6 (shot 069), and fully zoomed in is ~2.0 (070); the bot
# zooms fully out (FLOOR) on every arrival
SCALES = (2.1, 2.0, 1.9, 1.8, 1.7, 1.6, 1.5, 1.4, 1.3, 1.25, 1.2, 1.15, 1.1, 1.05, 1.0, 0.95, 0.9, 0.85, 0.8, 0.75, 0.7, 0.65, 0.6, 0.55, 0.5)
# fully zoomed out: maps don't go below 0.75 (every zoom-out in the logs ended there, 8 of 8, several events; and
# on the S23, more pinches change nothing). Leaving the map resets its zoom to the map's own (1.0-1.1)
FLOOR = 0.75
# offsets measured at zoom scale 1.0 (shot 009), multiplied by the detected scale
SKULL_TO_NODE = (120, 0)
MARKER_TO_NODE = (11, 210)
BLUE = ((98, 180, 180), (112, 255, 255))


BOSS_SCALE = 1.35  # boss nodes are drawn this much bigger than normal ones


@dataclass
class Node:
    center: tuple
    cleared: bool
    reachable: bool = False
    size: float = 1.0   # drawing scale of this node (map zoom x boss factor)
    guess: bool = False  # only "reachable" because it's the nearest node to the marker (no line seen)


@dataclass
class MapState:
    scale: float
    current: Node | None
    nodes: list
    exits: list = field(default_factory=list)  # screen sides a blue (playable) path runs off: "above", ...


# strips along the screen edges, clear of the header (top left), the area title and the % (bottom corners)
EDGE_STRIPS = {"above": [(1160, 0, 1400, 60), (0, 170, 1160, 60)], "below": [(700, 1540, 1500, 60)],
               "left": [(0, 230, 60, 1130)], "right": [(2500, 120, 60, 1300)]}


def _exits(mask):
    """Sides of the screen where a blue path line leaves the view: the playable node is that way."""
    out = []
    k = k_of(mask)
    for side, boxes in EDGE_STRIPS.items():
        px = sum(int(np.count_nonzero(v._crop(mask, box)[0])) for box in boxes)
        if px > 150 * k * k:  # a line crossing a 60px strip is several hundred pixels; specks are a few
            out.append((px, side))
    return [side for _, side in sorted(out, reverse=True)]


def _skull_score(frame, s):
    """Best skull-badge match at zoom s, on a frame of any size."""
    control.checkpoint()
    return float(cv2.matchTemplate(frame, v.scaled("map_skull", s * k_of(frame)), cv2.TM_CCOEFF_NORMED).max())


def _confirm(img, hint):
    """(score, zoom) if the known zoom (the last read's) is still the zoom: a strong match that scores at least as
    well as both neighbouring zooms and the zooms it would be a boss badge of. ~5 full-size matches instead of the
    whole search. Not a climb toward a better neighbour: with a boss in view, a hint 2+ steps above the zoom
    climbs onto the boss badge's own peak (~1.2-1.25x the zoom, shots 044 / 062 / 068 / 047), so anything but the
    hint itself is left to the full search."""
    if hint not in SCALES:
        return None
    i = SCALES.index(hint)
    here = _skull_score(img, hint)
    if here < 0.8:
        return None
    others = {SCALES[j] for j in (i - 1, i + 1) if 0 <= j < len(SCALES)}
    others |= {min(SCALES, key=lambda s: abs(s - hint / f)) for f in (1.2, 1.25)}
    if any(_skull_score(img, s) > here for s in sorted(others - {hint})):
        return None
    return here, hint


def _best_scale(img, half, hint=None):
    """Map zoom level = template scale with the strongest skull-badge match. A known zoom (hint) is only
    confirmed; else every scale is tried on the half-size frame (a quarter of the work: this was most of a map
    read), then the 3 best again at full size."""
    best = hint and _confirm(img, hint)
    if not best:
        rough = sorted(SCALES, key=lambda s: _skull_score(half, s), reverse=True)[:3]
        best = max((_skull_score(img, s), s) for s in rough)
    # every badge close to the best one; on a smaller frame the scores spread more (008 at 1920: best 0.95, real
    # nodes down to 0.83), so there the cutoff is at most the 0.8 a read at a known zoom uses
    cut = best[0] - 0.08 if k_of(img) == 1.0 else min(best[0] - 0.08, 0.8)
    return best[1], v.find_all(img, "map_skull", None, cut, scales=(best[1],))


def looks_like_map(img):
    """A node map without the event timer (story / origin maps, events without TIME REMAINING): several strong
    skull badges, or (zoomed in close) one badge plus the player's marker.
    Every zoom is ranked on a half-size frame (as in _best_scale), then the 3 best are checked at full size. The
    badge match only holds within ~3% of the true zoom, so a coarse list of zooms misses maps between its steps
    (a map at 0.85 against steps 0.8 / 0.9 scored 0.71: seen on the S23). This runs on every unrecognised frame:
    about as long as the old 12-step list."""
    half = cv2.resize(img, None, fx=0.5, fy=0.5, interpolation=cv2.INTER_AREA)
    for s in sorted(SCALES, key=lambda s: _skull_score(half, s), reverse=True)[:3]:
        n = len(v.find_all(img, "map_skull", None, 0.8, scales=(s,)))
        if n >= 2 or (n == 1 and v.find(img, "map_marker", None, 0.8, scales=(s,))):
            return True
    return False


def _reachable(mask, nodes, s):
    """Blue path lines only ever lead to playable nodes (taken paths are gold, locked ones brown), so an
    uncleared node that a blue line ends at is reachable — no need to know where the marker is."""
    k = k_of(mask)  # the mask is in the frame's pixels, nodes in design units
    n, labels, stats, _ = cv2.connectedComponentsWithStats(mask)
    if n <= 1:
        return
    for i in range(1, n):  # short blobs (the marker's blue gem, sparkles) aren't path lines
        if max(stats[i][2], stats[i][3]) < 80 * s * k:
            labels[labels == i] = 0
    yy, xx = np.nonzero(labels)
    if len(xx) == 0:
        return
    if k != 1.0:
        xx, yy = xx / k, yy / k
    for node in nodes:
        if not node.cleared:
            # distance to the node's whole footprint: double nodes extend ~230px right of the skull-based
            # centre, and triangle nodes have two circles hanging ~180px below it
            cx, cy = node.center
            s = node.size
            dx = np.clip(xx, cx - 40 * s, cx + 230 * s) - xx
            dy = np.clip(yy, cy - 40 * s, cy + 180 * s) - yy
            node.reachable = bool((np.hypot(dx, dy) < 170 * s).any())


def _portrait_brightness(img, node):
    """Mean brightness of the node's disc: revealed (playable) portraits ~140, cleared ~45, locked
    silhouettes < 30."""
    k = k_of(img)
    cx, cy = round(node.center[0] * k), round(node.center[1] * k)
    r = int(45 * node.size * k)
    disc = img[max(0, cy - r):max(0, cy + r), max(0, cx - r):max(0, cx + r)]
    if disc.size == 0:  # node centre off-screen (only its badge is visible)
        return 0.0
    return float(cv2.cvtColor(disc, cv2.COLOR_BGR2HSV)[:, :, 2].mean())


def read(img, scale=None, hint=None):
    """scale: the map's known zoom (panning doesn't change it). Without it the zoom is detected, which goes wrong
    when only a boss is in view (its bigger badge is taken for the zoom and the boss for a normal node).
    hint: the zoom of the last read, only confirmed if given (fully zoomed out is the same zoom every time)."""
    half = cv2.resize(img, None, fx=0.5, fy=0.5, interpolation=cv2.INTER_AREA)
    if scale:
        skulls = v.find_all(img, "map_skull", None, 0.8, scales=(scale,))
    else:
        scale, skulls = _best_scale(img, half, hint)
    if not skulls:
        return MapState(scale, None, [])
    # boss nodes: same badge, drawn bigger
    # the zoom estimate is only roughly right, so try a range of boss sizes and keep the best. Boss badges are
    # big: searched at half size, every hit confirmed at full size (same scores as a full-size search)
    boss_size, big = BOSS_SCALE, []
    rough = 0.7 if k_of(img) == 1.0 else 0.65  # half-size scores fall further below full-size on a smaller frame
    for f in (1.15, 1.2, 1.25, 1.3, 1.35, 1.4, 1.45, 1.5):
        hits = v.find_all_halved(img, half, "map_skull", 0.8, scale * f, rough=rough)
        if hits and (not big or hits[0].score > big[0].score):
            boss_size, big = f, hits
    badges = [(m, scale) for m in skulls] + [
        (m, scale * boss_size) for m in big
        if all(np.hypot(m.center[0] - k.center[0], m.center[1] - k.center[1]) > 60 * scale for k in skulls)]
    # a boss node's ✓ is drawn at the boss size too
    checks = {s: v.find_all(img, "map_check", None, 0.75, scales=(s,)) for s in {scale, scale * boss_size}}
    nodes = []
    for m, s in badges:
        sx, sy = m.center
        c = (int(sx + SKULL_TO_NODE[0] * s), int(sy + SKULL_TO_NODE[1] * s))
        # the ✓ sits at the node's right edge: ~100px right of a single node, up to ~340px for a double node
        cleared = any(40 * s < k.center[0] - c[0] < 380 * s and abs(k.center[1] - c[1]) < 50 * s for k in checks[s])
        nodes.append(Node(c, cleared, size=s))

    current = None
    marker = v.find(img, "map_marker", None, 0.7, scales=(scale,))
    if marker:
        mx, my = marker.center
        guess = (mx + MARKER_TO_NODE[0] * scale, my + MARKER_TO_NODE[1] * scale)
        current = min(nodes, key=lambda n: np.hypot(n.center[0] - guess[0], n.center[1] - guess[1]))
    mask = cv2.inRange(cv2.cvtColor(img, cv2.COLOR_BGR2HSV), BLUE[0], BLUE[1])
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))  # drop stray blue specks
    _reachable(mask, nodes, scale)
    for n in nodes:  # a revealed (bright) portrait on an uncleared node is playable even if its line is hidden
        if not n.cleared and not n.reachable and _portrait_brightness(img, n) > 100:
            n.reachable = True
    if marker and not any(n.reachable for n in nodes):
        # nothing visibly playable: step one node on from the character (the line is often under the marker)
        mx, my = marker.center
        ahead = [n for n in nodes if not n.cleared]
        if ahead:
            n = min(ahead, key=lambda n: np.hypot(n.center[0] - mx, n.center[1] - my))
            n.reachable = n.guess = True
    return MapState(scale, current, nodes, _exits(mask))


def is_boss(state, node):
    return node.size > state.scale * 1.1  # boss nodes are drawn BOSS_SCALE bigger


def unfinished(state, bad=(), boss=True):
    """Uncleared nodes not marked bad (reachable or not); boss=False leaves boss nodes out."""
    return [n for n in state.nodes
            if not n.cleared and (boss or not is_boss(state, n))
            and not any(b and np.hypot(n.center[0] - b[0], n.center[1] - b[1]) < 60 for b in bad)]


def choose(state, bad=(), boss=True, guess=True):
    """Reachable (unlocked), uncleared, not marked bad. Nodes unlock one after another and any open one will do,
    so the one nearest the screen centre: it needs no pan into view (each pan costs a map read).
    boss=False skips boss nodes (they end the chapter, so they're played last); guess=False skips the
    nearest-to-marker guess (worth zooming out / panning for a node with a visible line first)."""
    options = [n for n in unfinished(state, bad, boss) if n.reachable and (guess or not n.guess)]
    return min(options, key=lambda n: np.hypot(n.center[0] - 1280, n.center[1] - 800), default=None)
