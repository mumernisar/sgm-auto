"""Read the event node map: nodes, current position, which nodes are reachable, their enemy scores."""
from dataclasses import dataclass, field

import cv2
import numpy as np

from . import vision as v

SCALES = (1.25, 1.2, 1.15, 1.1, 1.05, 1.0, 0.95, 0.9, 0.85, 0.8, 0.75, 0.7, 0.65, 0.6, 0.55, 0.5)
# offsets measured at zoom scale 1.0 (shot 009), multiplied by the detected scale
SKULL_TO_NODE = (120, 0)
MARKER_TO_NODE = (11, 210)
SCORE_BOX = (-95, 58, 350, 58)   # relative to node centre: x, y, w, h (wide: double nodes' label sits right)
BLUE = ((98, 180, 180), (112, 255, 255))


BOSS_SCALE = 1.35  # boss nodes are drawn this much bigger than normal ones


@dataclass
class Node:
    center: tuple
    score: int | None   # None = '???'
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
    for side, boxes in EDGE_STRIPS.items():
        px = sum(int(np.count_nonzero(mask[y:y + h, x:x + w])) for x, y, w, h in boxes)
        if px > 150:  # a line crossing a 60px strip is several hundred pixels; specks are a few
            out.append((px, side))
    return [side for _, side in sorted(out, reverse=True)]


def _best_scale(img):
    """Map zoom level = template scale with the strongest skull-badge match."""
    best = (0.0, 1.0)
    for s in SCALES:
        tpl = v.template("map_skull")
        tpl = cv2.resize(tpl, None, fx=s, fy=s) if s != 1.0 else tpl
        score = float(cv2.matchTemplate(img, tpl, cv2.TM_CCOEFF_NORMED).max())
        if score > best[0]:
            best = (score, s)
    return best[1], v.find_all(img, "map_skull", None, best[0] - 0.08, scales=(best[1],))


def looks_like_map(img):
    """A node map without the event timer (story / origin maps): several strong skull badges, or (zoomed in
    close) one badge plus the player's marker."""
    for s in (1.2, 1.1, 1.0, 0.9, 0.8, 0.75, 0.7, 0.6):  # fewer zoom steps than read(): this runs on every unknown frame
        n = len(v.find_all(img, "map_skull", None, 0.8, scales=(s,)))
        if n >= 2 or (n == 1 and v.find(img, "map_marker", None, 0.8, scales=(s,))):
            return True
    return False


def _reachable(mask, nodes, s):
    """Blue path lines only ever lead to playable nodes (taken paths are gold, locked ones brown), so an
    uncleared node that a blue line ends at is reachable — no need to know where the marker is."""
    n, labels, stats, _ = cv2.connectedComponentsWithStats(mask)
    if n <= 1:
        return
    for i in range(1, n):  # short blobs (the marker's blue gem, sparkles) aren't path lines
        if max(stats[i][2], stats[i][3]) < 80 * s:
            labels[labels == i] = 0
    yy, xx = np.nonzero(labels)
    if len(xx) == 0:
        return
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
    cx, cy = node.center
    r = int(45 * node.size)
    disc = img[max(0, cy - r):max(0, cy + r), max(0, cx - r):max(0, cx + r)]
    if disc.size == 0:  # node centre off-screen (only its badge is visible)
        return 0.0
    return float(cv2.cvtColor(disc, cv2.COLOR_BGR2HSV)[:, :, 2].mean())


def _label(img, c, s):
    """Enemy score under a node: None for '???' or unreadable.

    The crop is wide (a double node's label sits to the right), so glyphs are grouped into words and only the
    word nearest the node is read. '???' is recognised by its separate dots (a number has at most one comma).
    """
    import pytesseract
    bx, by, bw, bh = (int(o * s) for o in SCORE_BOX)
    sub, _, _ = v._crop(img, (c[0] + bx, c[1] + by, bw, bh))
    if sub.shape[0] < 10 or sub.shape[1] < 10:  # label below the screen's edge
        return None
    k = 3
    g = cv2.resize(cv2.cvtColor(sub, cv2.COLOR_BGR2GRAY), None, fx=k, fy=k, interpolation=cv2.INTER_CUBIC)
    H, W = g.shape
    # labels are always light text on a dark plaque: threshold from the plaque centre, text = bright
    centre = g[:, int(-bx * k * 0.3):int(-bx * k * 1.7)]
    thr, _ = cv2.threshold(centre, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    b = ((g > thr) * 255).astype(np.uint8)
    n, labels, stats, _ = cv2.connectedComponentsWithStats(b)
    tall, small = [], []
    for i in range(1, n):
        x, y, w, h, area = stats[i]
        if x <= 1 or y <= 1 or x + w >= W - 1 or y + h >= H - 1:
            continue  # plaque border
        if 0.4 * H <= h <= 0.95 * H and w <= 0.6 * H and (area / (w * h) >= 0.3 or w < 0.2 * h):
            tall.append(i)  # digits are solid; plaque diagonals are hollow boxes
        elif 0.05 * H <= h < 0.3 * H and w < 0.3 * H:
            small.append(i)
    if not tall:
        return None
    tall.sort(key=lambda i: stats[i][0])
    words, cur = [], [tall[0]]
    for i in tall[1:]:
        prev = cur[-1]
        if stats[i][0] - (stats[prev][0] + stats[prev][2]) < 0.5 * stats[prev][3]:
            cur.append(i)
        else:
            words.append(cur)
            cur = [i]
    words.append(cur)
    expect = (-bx) * k  # node centre in crop coordinates; double nodes' labels sit up to ~80px further right
    word = min(words, key=lambda w: min(abs((stats[w[0]][0] + stats[w[-1]][0] + stats[w[-1]][2]) / 2 - e)
                                        for e in (expect, expect + 80 * s * k)))
    x0, x1 = stats[word[0]][0] - 10, stats[word[-1]][0] + stats[word[-1]][2] + 10
    dots = [i for i in small if x0 <= stats[i][0] <= x1]
    if len(dots) >= 2:
        return None  # '???'
    keep = np.isin(labels, word + dots).astype(np.uint8) * 255
    out = cv2.copyMakeBorder(255 - keep[:, max(0, x0):x1], 30, 30, 30, 30, cv2.BORDER_CONSTANT, value=255)
    return v.parse_score(pytesseract.image_to_string(out, config="--psm 7 -c tessedit_char_whitelist=0123456789,.k"))


def read(img, scale=None):
    """scale: the map's known zoom (panning doesn't change it). Without it the zoom is detected, which goes wrong
    when only a boss is in view (its bigger badge is taken for the zoom and the boss for a normal node)."""
    if scale:
        skulls = v.find_all(img, "map_skull", None, 0.8, scales=(scale,))
    else:
        scale, skulls = _best_scale(img)
    if not skulls:
        return MapState(scale, None, [])
    # boss nodes: same badge, drawn bigger
    # the zoom estimate is only roughly right, so try a range of boss sizes and keep the best
    boss_size, big = BOSS_SCALE, []
    for f in (1.15, 1.2, 1.25, 1.3, 1.35, 1.4, 1.45, 1.5):
        hits = v.find_all(img, "map_skull", None, 0.8, scales=(scale * f,))
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
        nodes.append(Node(c, _label(img, c, s), cleared, size=s))

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
    """Reachable, uncleared, not marked bad: lowest known score first, '???' nodes last.
    boss=False skips boss nodes (they end the chapter, so they're played last); guess=False skips the
    nearest-to-marker guess (worth zooming out / panning for a node with a visible line first)."""
    options = [n for n in unfinished(state, bad, boss) if n.reachable and (guess or not n.guess)]
    options.sort(key=lambda n: (n.score is None, n.score or 0))
    return options[0] if options else None
