"""Regression test: what the readers extract from the reference shots, checked against values verified on the
real game. Run after any change to vision/readers/eventmap:

    .venv/bin/python -m tests.test_readers          # prints each check, exits 1 on any failure

Add a case whenever a new screenshot exposes a bug (snap it with snap.sh, note the right answer here).
"""
import sys
from pathlib import Path

import cv2
import numpy as np

from bot import eventmap
from bot import readers as r

SHOTS = Path(__file__).resolve().parent.parent / "shots"
failures = []


def load(num):
    p = next(p for p in SHOTS.glob(f"{num}_*.png") if not p.name.endswith("_small.png"))
    return cv2.imread(str(p))


def check(label, got, want):
    ok = got == want
    print(f"{'ok ' if ok else 'BAD'} {label}: {got!r}" + ("" if ok else f"  (want {want!r})"))
    if not ok:
        failures.append(label)


def reqs(num):
    return [(q.kind, q.value, q.count, bool(q.excluded)) for q in r.requirements(load(num))]


if __name__ == "__main__":
    # top score bar (mine, enemy) and FIGHT enabled
    for num, scores, enabled in [("010", (24800, 640), True), ("018", (3377, None), False),
                                 ("025", (12000, None), True), ("033", (2615, 1763), True)]:
        img = load(num)
        check(f"{num} score bar", r.team_scores(img), scores)
        check(f"{num} fight enabled", bool(r.fight_enabled(img)), enabled)

    # requirement icons: kind, value, count (None = applies to every fighter), excluded
    check("010 requirements", reqs("010"), [("character", "umbrella", 1, False)])
    check("018 requirements", reqs("018"), [("character", "peacock", 1, False)])
    check("033 requirements", reqs("033"), [("element", "dark", 1, False), ("element", "air", 1, False)])
    check("036 requirements", reqs("036"), [("character", "eliza", 1, False), ("rarity", "bronze", None, True)])
    check("057 unmet requirement flashing red", reqs("057"), [("character", "filia", None, False)])

    # tooltips
    check("045 variant tooltip", r.variant_from_tooltip(r.tooltip_text(load("045"))), "garish gremlin")
    check("034 OR tooltip", r.tooltip_text(load("034")), "Must have a Dark or Air Fighter on your team!")

    # prize lobby: (total, multiplier) per panel
    for num, want in [("026", [(898, 2.5), (1185, 2.0), (13500, 1.0)]),
                      ("032", [(1763, 1.5), (1539, 1.0), (24500, 1.5)]),
                      ("040", [(2879, 1.0), (2807, 1.5), (50800, 1.0)])]:
        check(f"{num} lobby", [(o.total, o.multiplier) for o in r.lobby_opponents(load(num))], want)

    # energy cost plate above FIGHT (prize only)
    for num, want in [("033", 4), ("041", 5), ("010", None), ("018", None)]:
        check(f"{num} energy cost", r.fight_energy_cost(load(num)), want)

    # team picker cards: (score, element, character, energy) and slots
    check("019 cards", [(c.score, c.element, c.character) for c in r.picker_cards(load("019"))],
          [(9184, "fire", "peacock"), (8334, "dark", "peacock"), (6635, "fire", "peacock"),
           (5704, "neutral", "peacock"), (4611, "dark", "peacock")])
    check("025 slots", [(s.score, s.element) for s in r.team_slots(load("025"))], [(2786, "air"), (9184, "fire")])
    check("042 slots (no phantom from opponent art)", [s.icon[0] for s in r.team_slots(load("042"))], [88, 492, 894])
    check("041 cards", [(c.score, c.energy) for c in r.picker_cards(load("041"), with_energy=True, with_character=False)],
          [(172, 10), (173, 10), (173, 10), (173, 10), (173, 10)])

    # fight: auto battle state
    for num, want in [("011", "on"), ("012", "on"), ("013", "off")]:
        check(f"{num} auto", r.auto_state(load(num)), want)

    # event maps: zoom and the node the bot would tap (score, centre)
    for num, scale, pick in [("008", 0.75, (640, (1089, 1306))), ("009", 1.0, (640, (1020, 980))),
                             ("046", 1.1, (1891, (1697, 1014))), ("047", 1.1, (83, (1286, 429))),  # boss
                             ("053", 1.1, (None, (385, 274)))]:  # story map, no timer
        st = eventmap.read(load(num))
        node = eventmap.choose(st)
        check(f"{num} map", (st.scale, node and (node.score, node.center)), (scale, pick))

    # 062: the only open node is the boss, but just as the marker guess (no line), and a blue line runs off the top
    st = eventmap.read(load("062"))
    check("062 boss is a guess", [n.guess for n in st.nodes if eventmap.is_boss(st, n)], [True])
    check("062 blue line exits", st.exits, ["above"])
    check("009 blue line exits", eventmap.read(load("009")).exits, [])

    # boss nodes are played last: (bosses on the map, other unfinished nodes left)
    for num, want in [("044", (1, 10)), ("046", (1, 3)), ("047", (1, 0)), ("009", (0, 5)), ("062", (1, 0))]:
        st = eventmap.read(load(num))
        check(f"{num} boss last", (sum(eventmap.is_boss(st, n) for n in st.nodes),
                                   len(eventmap.unfinished(st, boss=False))), want)

    # area overview: (percent, current)
    for num, want in [("063", [(100, True), (100, False)]), ("059", [(30, True)]), ("060", [(70, True)]), ("049", [(10, True)]), ("054", [(0, True)]), ("055", [(0, True), (100, False)])]:
        check(f"{num} areas", [(a.percent, a.current) for a in r.areas(load(num))], want)

    # chapter arrows beside the current area: (« lit, » lit); greyed = first / last chapter, none = no chapters
    for num, want in [("059", (True, True)), ("060", (False, True)), ("049", (False, False)), ("063", (False, True))]:
        img = load(num)
        arrows = r.chapter_arrows(img, next(a for a in r.areas(img) if a.current))
        check(f"{num} chapter arrows", (bool(arrows["prev"]), bool(arrows["next"])), want)

    # events / origin stories list: (percent, playable, has › arrow)
    for num, want in [("048", (0, False, True)), ("050", (3, True, True))]:
        c = r.list_card(load(num))
        check(f"{num} list card", (c.percent, bool(c.playable), c.next_arrow is not None), want)
    # list slid off-centre: the neighbouring card's PLAY / '›' must not be taken for the selected one
    shifted = cv2.warpAffine(load("050"), np.float32([[1, 0, 330], [0, 1, 0]]), (2560, 1600))
    check("050 shifted list card", r.list_card(shifted), None)

    print(f"\n{len(failures)} failures" + (": " + ", ".join(failures) if failures else ""))
    sys.exit(1 if failures else 0)
