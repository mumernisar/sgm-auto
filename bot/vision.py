"""Template matching, colour checks and OCR. All coordinates are full-res (2560x1600)."""
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np
import pytesseract

from .config import ROOT

TEMPLATES = ROOT / "templates"


@dataclass
class Match:
    name: str
    x: int  # top-left
    y: int
    w: int
    h: int
    score: float

    @property
    def center(self):
        return self.x + self.w // 2, self.y + self.h // 2


@lru_cache(maxsize=None)
def template(name):
    img = cv2.imread(str(TEMPLATES / f"{name}.png"))
    if img is None:
        raise FileNotFoundError(f"template {name}")
    return img


def _crop(img, region):
    if region is None:
        return img, 0, 0
    x, y, w, h = region
    H, W = img.shape[:2]
    x, y = max(0, x), max(0, y)
    return img[y:min(H, y + h), x:min(W, x + w)], x, y


def find(img, name, region=None, threshold=0.8, scales=(1.0,), gray=False):
    """Best match of a template inside region, or None. gray=True ignores colour (e.g. a button's text on
    an orange or a greyed-out background)."""
    hits = find_all(img, name, region, threshold, scales, limit=1, gray=gray)
    return hits[0] if hits else None


def find_all(img, name, region=None, threshold=0.8, scales=(1.0,), limit=50, gray=False):
    sub, ox, oy = _crop(img, region)
    tpl0 = template(name)
    if gray:
        sub, tpl0 = cv2.cvtColor(sub, cv2.COLOR_BGR2GRAY), cv2.cvtColor(tpl0, cv2.COLOR_BGR2GRAY)
    hits = []
    for s in scales:
        tpl = tpl0 if s == 1.0 else cv2.resize(tpl0, None, fx=s, fy=s)
        th, tw = tpl.shape[:2]
        if th > sub.shape[0] or tw > sub.shape[1]:
            continue
        res = cv2.matchTemplate(sub, tpl, cv2.TM_CCOEFF_NORMED)
        ys, xs = np.where(res >= threshold)
        for x, y in zip(xs, ys):
            hits.append(Match(name, int(x + ox), int(y + oy), tw, th, float(res[y, x])))
    return _nms(hits)[:limit]


def _nms(hits):
    """Keep the best hit per overlapping cluster."""
    hits.sort(key=lambda m: -m.score)
    kept = []
    for m in hits:
        if all(abs(m.x - k.x) > k.w // 2 or abs(m.y - k.y) > k.h // 2 for k in kept):
            kept.append(m)
    return kept


GOLD = ((14, 140, 150), (34, 255, 255))


def find_gold(img, name, region=None, threshold=0.7):
    """Match a gold UI element by the shape of its saturated-gold pixels only, so whatever is behind it
    (moon, night sky, wood) doesn't matter."""
    sub, ox, oy = _crop(img, region)
    m_img = cv2.inRange(cv2.cvtColor(sub, cv2.COLOR_BGR2HSV), *GOLD)
    m_tpl = cv2.inRange(cv2.cvtColor(template(name), cv2.COLOR_BGR2HSV), *GOLD)
    m_img = cv2.GaussianBlur(m_img, (5, 5), 0)
    m_tpl = cv2.GaussianBlur(m_tpl, (5, 5), 0)
    res = cv2.matchTemplate(m_img, m_tpl, cv2.TM_CCOEFF_NORMED)
    _, mx, _, loc = cv2.minMaxLoc(res)
    if mx < threshold:
        return None
    th, tw = m_tpl.shape
    return Match(name, loc[0] + ox, loc[1] + oy, tw, th, float(mx))


# --- shape matching (ignores colour / frame differences) -------------------------------------------

def symbol(img, radius_frac, badge=False, size=64):
    """Normalised binary silhouette of the bright symbol inside an icon.

    Only pixels within radius_frac of the centre are considered (drops rings/frames, which differ between
    screens); badge=True also masks the count badge at the bottom-right. The symbol is cropped to its own
    bounding box and padded square, so icon size and colour stop mattering.
    """
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    h, w = g.shape
    mask = np.zeros_like(g)
    cv2.circle(mask, (w // 2, h // 2), int(min(h, w) * radius_frac), 255, -1)
    if badge:
        cv2.circle(mask, (w // 2 + int(w * 0.3), h // 2 + int(h * 0.3)), int(w * 0.2), 0, -1)
    thr, _ = cv2.threshold(g[mask > 0], 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    b = ((g > thr) & (mask > 0)).astype(np.uint8) * 255
    b = cv2.morphologyEx(b, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    # drop thin rings: components spanning most of the circle but mostly hollow
    # and small leftover ring arcs near the edge
    n, labels, stats, cents = cv2.connectedComponentsWithStats(b)
    R = min(h, w) * radius_frac
    biggest = max((stats[i][4] for i in range(1, n)), default=0)
    for i in range(1, n):
        x, y, bw, bh, area = stats[i]
        dist = np.hypot(cents[i][0] - w / 2, cents[i][1] - h / 2)
        if (max(bw, bh) > 1.2 * R and area < 0.2 * bw * bh) or area < 15 \
                or (dist > 0.7 * R and area < 0.25 * biggest):
            b[labels == i] = 0
    ys, xs = np.nonzero(b)
    if len(xs) == 0:
        return np.zeros((size, size), np.uint8)
    b = b[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    side = max(b.shape)
    sq = np.zeros((side, side), np.uint8)
    y0, x0 = (side - b.shape[0]) // 2, (side - b.shape[1]) // 2
    sq[y0:y0 + b.shape[0], x0:x0 + b.shape[1]] = b
    return cv2.resize(sq, (size, size), interpolation=cv2.INTER_AREA) > 127


def iou(a, b):
    """Similarity of two silhouettes: correlation of blurred masks (tolerates stroke-width differences)."""
    fa = cv2.GaussianBlur(a.astype(np.float32), (0, 0), 2.5).ravel()
    fb = cv2.GaussianBlur(b.astype(np.float32), (0, 0), 2.5).ravel()
    fa, fb = fa - fa.mean(), fb - fb.mean()
    return float(fa @ fb / (np.linalg.norm(fa) * np.linalg.norm(fb) or 1))


@lru_cache(maxsize=None)
def template_symbol(name):
    # character emblems sit inside a gold ring; element/rarity tiles fill the tile
    return symbol(template(name), 0.33 if name.startswith("c_") else 0.47)


def identify_icon(icon_img, candidates, radius_frac=0.34):
    """Return (name, score) of the template among candidates whose symbol best matches icon_img."""
    s = symbol(icon_img, radius_frac, badge=True)
    scored = [(n, iou(s, template_symbol(n))) for n in candidates]
    return max(scored, key=lambda t: t[1])


# --- colour helpers --------------------------------------------------------------------------------

def hsv_mean(img, region):
    sub, _, _ = _crop(img, region)
    return cv2.cvtColor(sub, cv2.COLOR_BGR2HSV).reshape(-1, 3).mean(axis=0)


def is_orange(img, region):
    """FIGHT/CONTINUE buttons: orange when active (hue ~28), grey when disabled (saturation ~16)."""
    h, s, v = hsv_mean(img, region)
    return 5 <= h <= 35 and s > 100 and v > 120


def color_fraction(img, region, lo, hi):
    """Fraction of pixels in region whose HSV lies in [lo, hi]."""
    sub, _, _ = _crop(img, region)
    mask = cv2.inRange(cv2.cvtColor(sub, cv2.COLOR_BGR2HSV), np.array(lo), np.array(hi))
    return mask.mean() / 255


# --- OCR ---------------------------------------------------------------------------------------------

def _prep(sub, invert=False, scale=3):
    g = cv2.cvtColor(sub, cv2.COLOR_BGR2GRAY)
    g = cv2.resize(g, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    _, b = cv2.threshold(g, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    if b.mean() < 127:  # tesseract wants dark text on light background
        b = 255 - b
    return 255 - b if invert else b


def ocr_text(img, region, psm=7):
    sub, _, _ = _crop(img, region)
    return pytesseract.image_to_string(_prep(sub), config=f"--psm {psm}").strip()


def parse_score(text):
    """'22.2k' -> 22200, '1,763' / '1.763' -> 1763, '???' / junk -> None."""
    t = text.lower().replace(" ", "").replace("o", "0")
    if "?" in t:
        return None
    m = re.search(r"(\d[\d,.]*)(k?)", t)
    if not m:
        return None
    num, k = m.group(1).strip(",."), m.group(2)
    if k:  # decimal point is real only with a k suffix
        return int(round(float(num.replace(",", ".")) * 1000))
    return int(num.replace(",", "").replace(".", "")) if num else None


def _white_text(sub, scale=3):
    """Black-on-white image of only the white text pixels (for white text on coloured backgrounds)."""
    hsv = cv2.cvtColor(sub, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, (0, 0, 165), (180, 120, 255))
    mask = cv2.resize(mask, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    mask = cv2.dilate((mask > 127).astype(np.uint8) * 255, np.ones((3, 3), np.uint8))
    return cv2.copyMakeBorder(255 - mask, 20, 20, 20, 20, cv2.BORDER_CONSTANT, value=255)


def ocr_score(img, region):
    sub, _, _ = _crop(img, region)
    txt = pytesseract.image_to_string(
        _prep(sub), config="--psm 7 -c tessedit_char_whitelist=0123456789,.k?")
    return parse_score(txt)


def ocr_glyphs(img, region, whitelist="0123456789,.k?", white=False):
    """OCR after keeping only glyph-like pieces: anything touching the crop edge (frames, plaque borders)
    or too small/flat is dropped first. white=True picks white text by colour instead of Otsu."""
    sub, _, _ = _crop(img, region)
    if white:
        hsv = cv2.cvtColor(cv2.resize(sub, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC), cv2.COLOR_BGR2HSV)
        b = cv2.inRange(hsv, (0, 0, 170), (180, 90, 255))
    else:
        b = 255 - _prep(sub, scale=3)  # white glyphs on black
    H, W = b.shape
    n, labels, stats, _ = cv2.connectedComponentsWithStats(b)
    keep = np.zeros_like(b)
    for i in range(1, n):
        x, y, w, h, area = stats[i]
        touches = x <= 1 or y <= 1 or x + w >= W - 1 or y + h >= H - 1
        if not touches and (0.35 * H <= h <= 0.95 * H and w <= 0.6 * H or 0.08 * H <= h < 0.35 * H and w < 0.25 * H):
            keep[labels == i] = 255  # digits, or a comma/decimal point
    if not keep.any():
        return ""
    out = cv2.copyMakeBorder(255 - keep, 30, 30, 30, 30, cv2.BORDER_CONSTANT, value=255)
    return pytesseract.image_to_string(out, config=f"--psm 7 -c tessedit_char_whitelist={whitelist}").strip()


def ocr_white_score(img, region):
    """Score in white text on a coloured/dark box (card corners)."""
    sub, _, _ = _crop(img, region)
    txt = pytesseract.image_to_string(
        _white_text(sub), config="--psm 7 -c tessedit_char_whitelist=0123456789,.k?")
    return parse_score(txt)


def ocr_multiplier(img, region):
    """Red 🔥 badge 'x2.5' -> 2.5; None if no badge."""
    if color_fraction(img, region, (0, 150, 120), (8, 255, 255)) + \
            color_fraction(img, region, (170, 150, 120), (180, 255, 255)) < 0.15:
        return None
    sub, _, _ = _crop(img, region)
    txt = pytesseract.image_to_string(_white_text(sub), config="--psm 7 -c tessedit_char_whitelist=x0123456789.")
    m = re.search(r"(\d)\.?(\d)?", txt)
    if not m:
        return None
    return float(f"{m.group(1)}.{m.group(2)}") if m.group(2) else float(m.group(1))
