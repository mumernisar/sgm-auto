"""Blur the player's name in reference shots before they're committed.

The name is in fixed places (2560x1600): the top bar, which sits further right when the avatar shows, and the
player panel in the prize lobby. Each place is OCR'd, and the name's word boxes are blurred only if the text
matches, so other screens are left alone. The small copy is remade with sips.

    .venv/bin/python tools/blur_name.py                  # every shot in shots/
    .venv/bin/python tools/blur_name.py shots/057_x.png  # just these

The name comes from $SGM_PLAYER_NAME or shots/.player_name (git-ignored). snap.sh calls this on each new shot.
"""
import difflib
import os
import subprocess
import sys
from pathlib import Path

import cv2
import pytesseract

ROOT = Path(__file__).resolve().parent.parent
SHOTS = ROOT / "shots"
NAME_FILE = SHOTS / ".player_name"

# x, y, w, h: top bar without avatar (fight results, popups), top bar with avatar, prize lobby player panel
PLACES = ((190, 10, 700, 75), (510, 10, 700, 75), (450, 410, 700, 75))
PAD = 8


def player_name():
    name = os.environ.get("SGM_PLAYER_NAME") or (NAME_FILE.read_text().strip() if NAME_FILE.exists() else "")
    if not name:
        sys.exit(f"set SGM_PLAYER_NAME or write the name to {NAME_FILE}")
    return name


def _norm(s):
    return "".join(ch for ch in s.lower() if ch.isalnum())


def name_box(img, place, name):
    """(x0, y0, x1, y1) of the name inside place, or None if it isn't there."""
    x, y, w, h = place
    crop = cv2.cvtColor(img[y:y + h, x:x + w], cv2.COLOR_BGR2GRAY)
    d = pytesseract.image_to_data(crop, config="--psm 7", output_type=pytesseract.Output.DICT)
    words = [i for i, t in enumerate(d["text"]) if _norm(t)]
    for i in words:
        if difflib.SequenceMatcher(None, _norm(d["text"][i]), _norm(name)).ratio() >= 0.6:
            return (x + d["left"][i] - PAD, y + d["top"][i] - PAD,
                    x + d["left"][i] + d["width"][i] + PAD, y + d["top"][i] + d["height"][i] + PAD)
    return None


def blur(img, box):
    x0, y0, x1, y1 = box
    roi = img[y0:y1, x0:x1]
    small = cv2.resize(roi, (max(1, roi.shape[1] // 24), max(1, roi.shape[0] // 24)), interpolation=cv2.INTER_AREA)
    img[y0:y1, x0:x1] = cv2.GaussianBlur(cv2.resize(small, roi.shape[1::-1]), (31, 31), 0)


def process(path, name):
    img = cv2.imread(str(path))
    boxes = []
    for b in filter(None, (name_box(img, p, name) for p in PLACES)):
        if not any(b[0] < o[2] and o[0] < b[2] and b[1] < o[3] and o[1] < b[3] for o in boxes):  # the two top-bar places overlap
            boxes.append(b)
    for b in boxes:
        blur(img, b)
    if boxes:
        cv2.imwrite(str(path), img, [cv2.IMWRITE_PNG_COMPRESSION, 9])
        small = path.with_name(path.stem + "_small.png")
        if small.exists():
            subprocess.run(["sips", "-Z", "1280", str(path), "--out", str(small)], capture_output=True, check=True)
    return len(boxes)


if __name__ == "__main__":
    name = player_name()
    paths = [Path(p) for p in sys.argv[1:]] or sorted(p for p in SHOTS.glob("*.png") if not p.stem.endswith("_small"))
    for p in paths:
        if process(p, name):
            print(f"blurred the name in {p.name}")
