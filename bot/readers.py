"""Pull numbers and icons out of specific screens."""
import re
from dataclasses import dataclass

import cv2
import numpy as np

from . import vision as v

ELEMENTS = ["fire", "water", "air", "light", "dark", "neutral"]
RARITIES = ["bronze", "silver", "gold", "diamond"]
CHARACTERS = ["annie", "beowulf", "bigband", "blackdahlia", "cerebella", "double", "eliza", "filia", "fukua",
              "marie", "msfortune", "painwheel", "parasoul", "peacock", "robofortune", "squigly", "umbrella",
              "valentine"]
ICON_TEMPLATES = [f"f_{e}" for e in ELEMENTS + RARITIES] + [f"c_{c}" for c in CHARACTERS]

# --- score bar / FIGHT button (event pre-fight, prize team page, team picker) ----------------------

BAR_LEFT = (770, 0, 220, 56)
BAR_RIGHT = (1570, 0, 220, 56)
FIGHT_BTN = (2090, 80, 380, 110)


def team_scores(img):
    """(my total, enemy total) from the top bar; enemy is None when it shows '???'."""
    return v.ocr_score(img, BAR_LEFT), v.ocr_score(img, BAR_RIGHT)


def fight_enabled(img):
    return v.is_orange(img, FIGHT_BTN)


# --- requirement icons under the score bar ---------------------------------------------------------

REQ_REGION = (1040, 80, 480, 170)
ICON_BOX = 140


@dataclass
class Requirement:
    kind: str           # "element" | "rarity" | "character"
    value: str          # e.g. "dark", "peacock"
    count: int | None   # None = universal (applies to every fighter)
    excluded: bool      # crossed out = can't be used
    center: tuple
    score: float        # shape-match confidence


def _icon_centers(img):
    sub, ox, oy = v._crop(img, REQ_REGION)
    g = cv2.medianBlur(cv2.cvtColor(sub, cv2.COLOR_BGR2GRAY), 5)
    circles = cv2.HoughCircles(g, cv2.HOUGH_GRADIENT, dp=1.2, minDist=100, param1=100, param2=35,
                               minRadius=50, maxRadius=68)
    if circles is None:
        return []
    pts = [(int(x) + ox, int(y) + oy) for x, y, _ in circles[0]]
    return sorted(p for p in pts if abs(p[1] - 160) < 40)


def _red_mask(icon):
    hsv = cv2.cvtColor(icon, cv2.COLOR_BGR2HSV)
    return ((hsv[:, :, 0] <= 3) | (hsv[:, :, 0] >= 172)) & (hsv[:, :, 1] > 120) & (hsv[:, :, 2] > 60)


def _has_slash(icon):
    """Excluded icons (crossed out) get a red inner ring at radius ~40-48px; normal icons have none.
    An unmet requirement on the team picker flashes red all over (inside ~0.7 red), so the inside must stay
    mostly clear (a real slash leaves it at ~0.1)."""
    n = icon.shape[0]
    yy, xx = np.mgrid[0:n, 0:n]
    d = np.hypot(xx - n / 2, yy - n / 2)
    red = _red_mask(icon)
    return red[(d >= 40) & (d < 48)].mean() > 0.3 and red[d < 38].mean() < 0.3


def _count(img, cx, cy):
    """Digit in the small black badge at the icon's bottom-right; None if there's no badge."""
    sub, _, _ = v._crop(img, (cx + 18, cy + 18, 52, 52))
    hsv = cv2.cvtColor(sub, cv2.COLOR_BGR2HSV)
    val, sat = hsv[:, :, 2], hsv[:, :, 1]
    vmax = int(val.max())
    yy, xx = np.mgrid[0:val.shape[0], 0:val.shape[1]]
    disc = np.hypot(xx - 23, yy - 23) < 18  # inside the black badge only
    digit = disc & (val > max(80, vmax * 0.7)) & (sat < 60)  # relative: the screen may be dimmed
    if (val < 50).mean() < 0.3 or digit.mean() < 0.04:
        return None
    ys, xs = np.nonzero(digit)
    if (xs.max() - xs.min() + 1) / (ys.max() - ys.min() + 1) < 0.6:  # a lone '1' is narrow; OCR mangles it
        return 1
    import pytesseract
    mask = cv2.resize((~digit).astype(np.uint8) * 255, None, fx=4, fy=4, interpolation=cv2.INTER_NEAREST)
    mask = cv2.copyMakeBorder(mask, 20, 20, 20, 20, cv2.BORDER_CONSTANT, value=255)
    m = re.search(r"\d", pytesseract.image_to_string(mask, config="--psm 10 -c tessedit_char_whitelist=0123456789"))
    return int(m.group()) if m else None


def _rarity_by_color(icon):
    """Medals share one shape, so rarity comes from colour (ignoring the red exclusion slash)."""
    n = icon.shape[0]
    hsv = cv2.cvtColor(icon[n // 4:3 * n // 4, n // 4:3 * n // 4], cv2.COLOR_BGR2HSV).reshape(-1, 3)
    bright = hsv[hsv[:, 2] > 70]
    sat = bright[(bright[:, 1] > 60) & (bright[:, 0] >= 6) & (bright[:, 0] <= 165)]
    if len(sat) < 0.15 * max(len(bright), 1):
        return "silver"
    hue = np.median(sat[:, 0])
    return "diamond" if hue > 120 else "gold" if hue > 18 else "bronze"


MIN_ICON_CONFIDENCE = 0.8


def requirements(img):
    """Requirement icons under the score bar. Low-confidence icons get kind='unknown'."""
    reqs = []
    for cx, cy in _icon_centers(img):
        h = ICON_BOX // 2
        icon = img[cy - h:cy + h, cx - h:cx + h]
        excluded = _has_slash(icon)
        clean = icon.copy()
        if excluded:  # blank out the red slash/ring so they don't distort the symbol
            clean[_red_mask(icon)] = 0
        name, score = v.identify_icon(clean, ICON_TEMPLATES)
        value = name[2:]
        if score < MIN_ICON_CONFIDENCE - (0.1 if excluded else 0):  # the slash costs a little confidence
            kind = "unknown"
        elif name.startswith("c_"):
            kind = "character"
        elif value in RARITIES:
            kind, value = "rarity", _rarity_by_color(icon)
        else:
            kind = "element"
        reqs.append(Requirement(kind, value, _count(img, cx, cy), excluded, (cx, cy), score))
    return reqs


TOOLTIP = (930, 70, 700, 110)  # banner that appears under the score bar when a requirement icon is tapped


def tooltip_text(img):
    """Text of the requirement tooltip, e.g. 'NEED GARISH GREMLIN VARIANT' or 'Must have a Dark or Air Fighter'."""
    import pytesseract
    sub, _, _ = v._crop(img, TOOLTIP)
    return " ".join(pytesseract.image_to_string(v._prep(sub, scale=3), config="--psm 6").split())


def variant_from_tooltip(text):
    """'NEED GARISH GREMLIN VARIANT' -> 'garish gremlin'; None for other kinds of tooltip."""
    m = re.search(r"NEED\s+(.+?)\s+VARIANT", text.upper())
    return m.group(1).lower() if m else None


def card_name(img, card):
    """Fighter variant name on the card's name plate (e.g. 'garish gremlin')."""
    ix, iy = card.icon
    return re.sub(r"[^a-z ]", "", v.ocr_text(img, (ix - 40, iy + 390, 380, 72)).lower()).strip()


def names_match(a, b):
    """Fuzzy match of two names (OCR drops/garbles letters): share of letters found in order, both ways."""
    a, b = a.replace(" ", ""), b.replace(" ", "")
    return bool(a and b) and min(_overlap(a, b), _overlap(b, a)) >= 0.75


# --- events / story list and area overview ---------------------------------------------------------

@dataclass
class ListCard:
    play: tuple            # PLAY button centre
    playable: bool         # orange (grey = done / unavailable)
    percent: int | None    # progress of the shown difficulty
    next_arrow: tuple | None


def _percent(text):
    m = re.search(r"(\d{1,3})\s*%", text.replace("O%", "0%"))
    return int(m.group(1)) if m else None


def list_card(img):
    """Centre card of the events / origin stories list; positions are relative to its PLAY button because
    the card sits at different heights on the two lists. The cards beside it have their own PLAY and '›', so
    only a PLAY centred on the screen counts (None while the list is still sliding), and its '›' is looked
    for in a tight box at its fixed offset (+235, -160)."""
    m = v.find(img, "play_text", (1160, 880, 240, 320), 0.6, gray=True)
    if not m or abs(m.center[0] - 1280) > 40:
        return None
    px, py = m.center
    pct = _percent(v.ocr_text(img, (px - 110, py - 152, 220, 62)))
    arrow = v.find(img, "difficulty_next", (px + 175, py - 225, 120, 130), 0.7)
    return ListCard((px, py), v.is_orange(img, (px - 140, py - 25, 280, 50)), pct, arrow.center if arrow else None)


@dataclass
class Area:
    tap: tuple
    percent: int
    current: bool


def _percent_words(img, region, scale, psm=11):
    """(percent, x, y) for every 'NN%' word Tesseract finds in region (full-res coordinates)."""
    import pytesseract
    sub, ox, oy = v._crop(img, region)
    g = cv2.resize(cv2.cvtColor(sub, cv2.COLOR_BGR2GRAY), None, fx=scale, fy=scale)
    data = pytesseract.image_to_data(g, config=f"--psm {psm}", output_type=pytesseract.Output.DICT)
    out = []
    for i, word in enumerate(data["text"]):
        pct = _percent(word)
        if pct is not None and pct <= 100:
            out.append((pct, ox + (data["left"][i] + data["width"][i] / 2) / scale,
                        oy + (data["top"][i] + data["height"][i] / 2) / scale))
    return out


def chapter_arrows(img, area):
    """« / » beside an area panel that has chapters ('MAPLECREST CHAPTER 2 30%'). Returns
    {'prev': (x, y) or None, 'next': ...}: None = no arrow, or greyed out (first / last chapter)."""
    tx, ty = area.tap
    out = {}
    for side, tpl, region in (("prev", "chapter_prev", (tx - 480, ty - 160, 300, 250)),
                              ("next", "chapter_next", (tx + 180, ty - 160, 300, 250))):
        m = v.find(img, tpl, region, 0.6)
        out[side] = None
        if m:
            x, y = m.center
            hsv = cv2.cvtColor(img[y - 30:y + 30, x - 30:x + 30], cv2.COLOR_BGR2HSV)
            gold = (hsv[..., 0] >= 15) & (hsv[..., 0] <= 35) & (hsv[..., 1] > 100) & (hsv[..., 2] > 150)
            if gold.mean() > 0.08:  # lit arrow ~0.18, greyed ~0
                out[side] = m.center
    return out


def areas(img):
    """Area panels on the area overview ('DOWNTOWN 10%'); locked areas show a padlock instead of a %.
    The panel under the gold chevron (current area) is read at full resolution; the rest of the screen at
    half resolution to find other unfinished areas."""
    out = []
    chev = v.find_gold(img, "area_chevron", (0, 0, 2560, 1300), 0.8)
    if chev:
        cx, cy = chev.center
        # block mode reads a panel's text reliably; sparse mode (used for the whole screen) can miss it.
        # The chevron bobs ~55px, and at its highest block mode sometimes reads nothing: try sparse too
        for psm in (6, 11):
            words = _percent_words(img, (cx - 350, cy + 250, 900, 400), 1.0, psm=psm)
            if words:
                pct, x, y = words[0]
                out.append(Area((int(x), int(y - 45)), pct, True))
                break
    for pct, x, y in _percent_words(img, None, 0.5):
        if not any(abs(a.tap[0] - x) < 150 and abs(a.tap[1] + 45 - y) < 80 for a in out):
            out.append(Area((int(x), int(y - 45)), pct, False))  # tap the panel's middle, above the %
    if chev and not any(a.current for a in out):  # the panel % was only found by the whole-screen pass
        below = [a for a in out if abs(a.tap[0] - cx) < 350 and 250 < a.tap[1] - cy < 700]
        if below:
            below[0].current = True
    return out


# --- prize fight lobby -----------------------------------------------------------------------------

LOBBY_PANELS = [  # (total score text, multiplier badge, tap point)
    ((1612, 422, 126, 46), (2276, 358, 120, 124), (1970, 560)),
    ((1566, 742, 136, 46), (2316, 672, 124, 128), (1970, 900)),
    ((1612, 1092, 126, 46), (2276, 1022, 120, 128), (1970, 1230)),
]


@dataclass
class Opponent:
    index: int
    total: int | None
    multiplier: float
    tap: tuple


def lobby_opponents(img):
    out = []
    for i, (score_r, badge_r, tap) in enumerate(LOBBY_PANELS):
        out.append(Opponent(i, v.ocr_score(img, score_r), v.ocr_multiplier(img, badge_r) or 1.0, tap))
    return out


# --- team picker cards -----------------------------------------------------------------------------

CARD_ICON_BAND = (0, 950, 2560, 120)   # the row of element icons at the cards' top-left corners
SLOT_ICON_BAND = (0, 250, 1500, 100)   # same for the team slots at the top
BOLT_FILL = (20, 40)                   # hue range of a full (yellow) energy bolt


@dataclass
class Card:
    icon: tuple          # element icon centre
    score: int | None
    element: str | None
    character: str | None
    energy: int | None   # yellow bolts out of 10; None where cards show no energy row (events)

    @property
    def center(self):
        return self.icon[0] + 170, self.icon[1] + 200


def _band_circles(img, band, rmin, rmax):
    sub, ox, oy = v._crop(img, band)
    g = cv2.medianBlur(cv2.cvtColor(sub, cv2.COLOR_BGR2GRAY), 5)
    c = cv2.HoughCircles(g, cv2.HOUGH_GRADIENT, dp=1.2, minDist=300, param1=100, param2=30,
                         minRadius=rmin, maxRadius=rmax)
    return sorted((int(x) + ox, int(y) + oy) for x, y, _ in (c[0] if c is not None else []))


def _element_at(img, cx, cy, r_in=24, r_out=33):
    """Element of a card/slot icon from its disc colour (cards are always rendered the same way, so colour
    is reliable here — unlike requirement icons, which are drawn differently from the filter icons)."""
    sub = img[cy - r_out:cy + r_out, cx - r_out:cx + r_out]
    yy, xx = np.mgrid[0:sub.shape[0], 0:sub.shape[1]]
    d = np.hypot(xx - r_out, yy - r_out)
    h, s, _ = np.median(cv2.cvtColor(sub, cv2.COLOR_BGR2HSV)[(d > r_in) & (d < r_out)], axis=0)
    if s < 50:
        return "neutral"
    if h < 12 or h > 165:
        return "fire"
    if h < 38:
        return "light"
    if h < 88:
        return "air"
    if h < 122:
        return "water"
    return "dark"


def _character_from_text(text):
    t = re.sub(r"[^a-z]", "", text.lower())
    best = max(CHARACTERS, key=lambda c: _overlap(c, t))
    return best if _overlap(best, t) >= 0.6 else None


def _overlap(a, b):
    """Share of a's characters found in order in b (tolerates OCR noise)."""
    i = 0
    for ch in b:
        if i < len(a) and ch == a[i]:
            i += 1
    return i / len(a)


def _yellow_blobs(img, region, min_area=60):
    """Number of separate yellow (full energy bolt) blobs in region, lined up in one row."""
    sub, _, _ = v._crop(img, region)
    if sub.size == 0:
        return 0
    mask = cv2.inRange(cv2.cvtColor(sub, cv2.COLOR_BGR2HSV), (BOLT_FILL[0], 110, 140), (BOLT_FILL[1], 255, 255))
    n, _, stats, cents = cv2.connectedComponentsWithStats(mask)
    # bolts are small and roughly square; wide blobs are button edges
    ys = [cents[i][1] for i in range(1, n) if stats[i][4] >= min_area and stats[i][2] < 60 and stats[i][3] < 60]
    if not ys:
        return 0
    row = np.median(ys)
    return sum(1 for y in ys if abs(y - row) < 12)


def _energy(img, ix, iy):
    """Yellow bolts in the energy row along the card's bottom edge (out of 10)."""
    if iy + 580 > img.shape[0] or ix + 320 > img.shape[1]:
        return None
    return _yellow_blobs(img, (ix + 5, iy + 525, 320, 55), min_area=40)


CARD_PITCH = 477  # px between neighbouring cards in the picker strip


def _card_icons(img):
    """Element-icon centres of the visible cards. Hough also finds level badges, so fit the even card grid."""
    found = _band_circles(img, CARD_ICON_BAND, 34, 48)
    if not found:
        return []
    best = max(found, key=lambda c: sum(min(abs((f[0] - c[0]) % CARD_PITCH), CARD_PITCH - abs((f[0] - c[0]) % CARD_PITCH)) < 15
                                        for f in found))
    x0 = best[0] % CARD_PITCH
    y = int(np.median([f[1] for f in found]))
    return [(x, y) for x in range(x0, img.shape[1] - 110, CARD_PITCH) if x > 40]


def _card_score(img, ix, iy):
    """Three OCR passes; a score counts only when at least two agree (a wrong fighter costs more than a skip)."""
    box = (ix + 48, iy - 32, 170, 64)
    reads = [v.parse_score(v.ocr_glyphs(img, box, "0123456789,.k", white=True)),
             v.ocr_white_score(img, (ix + 52, iy - 30, 140, 58)),
             v.ocr_score(img, (ix + 52, iy - 30, 140, 58))]
    for val in reads:
        if val is not None and reads.count(val) >= 2:
            return val
    return None


def drop_out_of_order(cards, ascending):
    """The list is sorted, so a score that breaks the order is a misread: blank it rather than trust it."""
    s = [c.score for c in cards]
    for i, c in enumerate(cards):
        if c.score is None:
            continue
        prev = next((s[j] for j in range(i - 1, -1, -1) if s[j] is not None), None)
        nxt = next((s[j] for j in range(i + 1, len(s)) if s[j] is not None), None)
        bad_prev = prev is not None and (c.score < prev if ascending else c.score > prev)
        bad_next = nxt is not None and (c.score > nxt if ascending else c.score < nxt)
        if bad_prev and bad_next or (bad_prev and nxt is None) or (bad_next and prev is None and len(cards) > 2
                                                                    and _consistent(s[i + 1:], ascending)):
            c.score = None
    return cards


def _consistent(seq, ascending):
    vals = [x for x in seq if x is not None]
    return all((a <= b) if ascending else (a >= b) for a, b in zip(vals, vals[1:]))


def picker_cards(img, with_energy=False, with_character=True):
    cards = []
    for ix, iy in _card_icons(img):
        score = _card_score(img, ix, iy)
        character = _character_from_text(v.ocr_text(img, (ix + 20, iy + 465, 300, 55))) if with_character else None
        cards.append(Card((ix, iy), score, _element_at(img, ix, iy), character,
                          _energy(img, ix, iy) if with_energy else None))
    return cards


@dataclass
class Slot:
    icon: tuple
    score: int | None
    element: str

    @property
    def center(self):
        return self.icon[0] + 150, self.icon[1] + 250


def team_slots(img):
    return [Slot((x, y), v.ocr_score(img, (x + 35, y - 28, 140, 56)), _element_at(img, x, y, 16, 24))
            for x, y in _band_circles(img, SLOT_ICON_BAND, 26, 40)]


def fight_energy_cost(img):
    """Number of bolts drawn above the FIGHT button (prize fights); None if there are none."""
    n = _yellow_blobs(img, (2140, 20, 300, 60))
    return n if n >= 3 else None  # real cost plates show 3+ bolts; fewer is stray yellow


# --- fight -----------------------------------------------------------------------------------------

def auto_state(img):
    """'on' (3x badge above brain), 'off' (brain, no badge) or None (not visible)."""
    if v.find(img, "auto_on_badge", (1150, 1250, 260, 200), 0.75):
        return "on"
    if v.find(img, "auto_brain", (1150, 1380, 260, 220), 0.7):
        return "off"
    return None
