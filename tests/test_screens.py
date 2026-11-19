"""Run the screen detector over every reference shot and compare with the expected screen.

    .venv/bin/python -m tests.test_screens
"""
import sys
import time
from pathlib import Path

import cv2

from bot.screens import detect

SHOTS = Path(__file__).resolve().parent.parent / "shots"

EXPECTED = {
    **{f"{n:03d}": "unknown" for n in range(1, 8)},  # collection pages
    "008": "event_map", "009": "event_map", "010": "event_prefight",
    "011": "fight", "012": "fight", "013": "fight", "014": "paused",
    "015": "victory", "016": "victory", "017": "defeat", "018": "event_prefight",
    "019": "team_picker", "020": "filter", "021": "filter", "022": "filter", "023": "filter", "024": "filter",
    "025": "team_picker", "026": "prize_lobby", "027": "moves_popup",
    "028": "victory", "029": "victory", "030": "victory", "031": "victory",
    "032": "prize_lobby", "033": "prize_team", "034": "prize_team", "035": "energy_refill",
    "036": "filter", "037": "defeat", "038": "defeat", "039": "keep_streak", "040": "prize_lobby", "041": "team_picker", "042": "team_picker", "043": "team_picker", "044": "event_map", "045": "team_picker", "046": "event_map", "047": "event_map", "048": "event_list", "049": "event_areas", "050": "event_list", "051": "cutscene", "052": "cutscene", "053": "event_map", "054": "event_areas", "055": "event_areas", "056": "offer", "057": "team_picker", "058": "modifiers", "059": "event_areas", "060": "event_areas", "061": "event_map", "062": "event_map", "063": "event_areas", "064": "event_prefight",
}

if __name__ == "__main__":
    bad = 0
    for p in sorted(SHOTS.glob("*.png")):
        if p.name.endswith("_small.png"):
            continue
        num = p.name[:3]
        if num not in EXPECTED:  # new snaps without a label yet
            continue
        t = time.time()
        got, m = detect(cv2.imread(str(p)))
        ok = got == EXPECTED.get(num)
        bad += not ok
        score = f"{m.score:.2f}" if m else "-"
        print(f"{'ok ' if ok else 'BAD'} {num} expected={EXPECTED.get(num):15} got={got:15} score={score} {time.time()-t:.2f}s")
    print(f"\n{bad} mismatches")
    sys.exit(1 if bad else 0)
