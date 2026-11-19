"""Cut template images out of the reference shots.

Coordinates are full-resolution (2560x1600) x, y, w, h. Re-run after tweaking a box:
    .venv/bin/python tools/crop_templates.py            # crop all + write templates/_sheet.png
    .venv/bin/python tools/crop_templates.py fight_btn  # crop one
"""
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
SHOTS = ROOT / "shots"
OUT = ROOT / "templates"

# name: (shot number, x, y, w, h)
SPEC = {
    # shared buttons / headers
    "back_arrow":        ("010", 24, 24, 112, 112),
    "fight_btn":         ("010", 2170, 85, 230, 100),
    "team_btn":          ("010", 1190, 1190, 180, 150),
    "victory_header":    ("015", 980, 160, 580, 140),
    "defeat_header":     ("017", 1060, 160, 420, 140),
    "continue_btn":      ("015", 1170, 1355, 220, 75),
    "rematch_btn":       ("017", 1780, 1355, 240, 75),
    "quit_btn":          ("017", 590, 1355, 140, 75),
    "favorite_btn":      ("016", 550, 1355, 220, 75),
    # fight
    "pause_btn":         ("011", 1230, 20, 100, 110),
    "paused_header":     ("014", 1140, 140, 280, 100),
    "resume_btn":        ("014", 1560, 1320, 200, 75),
    # event map
    "time_remaining":    ("008", 2220, 30, 300, 50),
    "map_marker":        ("009", 1480, 680, 144, 180),
    "map_check":         ("009", 1624, 945, 84, 76),
    # team picker / filter
    "drag_banner":       ("019", 1040, 900, 480, 40),
    "filter_btn":        ("019", 2412, 826, 96, 94),
    "filter_header":     ("020", 180, 280, 290, 100),
    "filter_clear":      ("020", 494, 274, 102, 102),
    "filter_close":      ("020", 2402, 202, 100, 100),
    "sort_down":         ("020", 1908, 494, 50, 60),
    "sort_up":           ("036", 1908, 494, 50, 60),
    # filter icons (unscrolled grid, shot 020)
    "f_bronze":          ("020", 330, 474, 140, 140),
    "f_silver":          ("020", 520, 474, 140, 140),
    "f_gold":            ("020", 712, 474, 140, 140),
    "f_diamond":         ("020", 904, 474, 140, 140),
    "f_fire":            ("020", 330, 750, 140, 140),
    "f_water":           ("020", 520, 750, 140, 140),
    "f_air":             ("020", 712, 750, 140, 140),
    "f_light":           ("020", 904, 750, 140, 140),
    "f_dark":            ("020", 1096, 750, 140, 140),
    "f_neutral":         ("020", 1290, 750, 140, 140),
    # character emblems (scrolled grid, shot 022) — alphabetical roster order
    "c_annie":           ("022", 330, 800, 140, 140),
    "c_beowulf":         ("022", 520, 800, 140, 140),
    "c_bigband":         ("022", 712, 800, 140, 140),
    "c_blackdahlia":     ("022", 904, 800, 140, 140),
    "c_cerebella":       ("022", 1096, 800, 140, 140),
    "c_double":          ("022", 1290, 800, 140, 140),
    "c_eliza":           ("022", 330, 992, 140, 140),
    "c_filia":           ("022", 520, 992, 140, 140),
    "c_fukua":           ("022", 712, 992, 140, 140),
    "c_marie":           ("022", 904, 992, 140, 140),
    "c_msfortune":       ("022", 1096, 992, 140, 140),
    "c_painwheel":       ("022", 1290, 992, 140, 140),
    "c_parasoul":        ("022", 330, 1186, 140, 140),
    "c_peacock":         ("022", 520, 1186, 140, 140),
    "c_robofortune":     ("022", 712, 1186, 140, 140),
    "c_squigly":         ("022", 904, 1186, 140, 140),
    "c_umbrella":        ("022", 1096, 1186, 140, 140),
    "c_valentine":       ("022", 1290, 1186, 140, 140),
    # prize fight
    "leaders_btn":       ("026", 1110, 1150, 340, 100),
    "lobby_continue":    ("026", 2070, 80, 406, 110),
    "streak_label":      ("033", 50, 230, 235, 60),
    "map_skull":         ("009", 860, 940, 80, 80),
    "top_rewards":       ("048", 1175, 1258, 205, 44),
    "difficulty_next":   ("048", 1482, 822, 66, 82),
    "play_text":         ("050", 1222, 1057, 116, 56),
    "skip_btn":          ("051", 1210, 1380, 140, 70),
    "offer_close":       ("056", 2052, 292, 110, 106),
    "offer_hdr":         ("056", 840, 352, 400, 56),
    "area_chevron":      ("049", 1850, 172, 160, 96),
    "moves_popup_fight": ("027", 1350, 1060, 300, 100),
    "energy_refill_hdr": ("035", 1120, 570, 320, 70),
    "popup_close":       ("035", 1836, 512, 100, 96),
    "keep_streak_hdr":   ("039", 1070, 495, 420, 90),
    "keep_streak_close": ("039", 1870, 456, 100, 96),
}


def shot_path(num):
    return next(p for p in SHOTS.glob(f"{num}_*.png") if not p.name.endswith("_small.png"))


def crop(name):
    num, x, y, w, h = SPEC[name]
    img = cv2.imread(str(shot_path(num)))
    tpl = img[y:y + h, x:x + w]
    cv2.imwrite(str(OUT / f"{name}.png"), tpl)
    return tpl


def contact_sheet(tiles, cols=8, cell=200):
    rows = (len(tiles) + cols - 1) // cols
    sheet = np.full((rows * (cell + 24), cols * cell, 3), 40, np.uint8)
    for i, (name, tpl) in enumerate(tiles):
        r, c = divmod(i, cols)
        h, w = tpl.shape[:2]
        s = min((cell - 8) / w, (cell - 8) / h, 2.0)
        t = cv2.resize(tpl, (max(1, int(w * s)), max(1, int(h * s))))
        y0, x0 = r * (cell + 24) + 22, c * cell + 4
        sheet[y0:y0 + t.shape[0], x0:x0 + t.shape[1]] = t
        cv2.putText(sheet, name[:22], (x0, y0 - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1)
    return sheet


if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    names = sys.argv[1:] or list(SPEC)
    tiles = [(n, crop(n)) for n in names]
    cv2.imwrite(str(OUT / "_sheet.png"), contact_sheet(tiles))
    print(f"cropped {len(tiles)} templates -> templates/_sheet.png")
