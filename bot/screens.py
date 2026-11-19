"""Decide which game screen is showing. Popups are checked first because they sit on top of other screens."""
from . import vision as v

# (screen, template, search region x,y,w,h, threshold) — first hit wins
CHECKS = [
    ("cutscene",       "skip_btn",           (1050, 1300, 460, 240), 0.75),
    # paid offers can pop over any screen (even VICTORY): only ever close them
    ("offer",          "offer_hdr",          (500, 250, 1500, 300), 0.75),
    ("keep_streak",    "keep_streak_hdr",    (1000, 440, 560, 200), 0.75),
    ("energy_refill",  "energy_refill_hdr",  (1050, 500, 460, 200), 0.75),
    ("moves_popup",    "moves_popup_fight",  (1250, 980, 500, 260), 0.8),
    ("paused",         "paused_header",      (1050, 100, 460, 200), 0.75),
    ("victory",        "victory_header",     (900, 100, 760, 260), 0.75),
    ("defeat",         "defeat_header",      (900, 100, 760, 260), 0.75),
    ("filter",         "filter_header",      (100, 220, 450, 220), 0.75),
    ("team_picker",    "drag_banner",        (900, 850, 760, 140), 0.7),
    ("fight",          "pause_btn",          (1150, 0, 260, 180), 0.8),
    ("prize_lobby",    "leaders_btn",        (1000, 1100, 560, 220), 0.75),
    ("prize_team",     "streak_label",       (0, 180, 500, 140), 0.75),
    ("event_prefight", "team_btn",           (1100, 1100, 360, 300), 0.7),
    ("event_areas",    "area_chevron",       (0, 0, 2560, 1300), 0.75),
    ("event_map",      "time_remaining",     (2100, 0, 460, 120), 0.7),
    ("event_list",     "top_rewards",        (1000, 1150, 560, 220), 0.75),
]


def detect(img):
    """Return (screen_name, match) — ('unknown', None) if nothing matched."""
    for screen, tpl, region, thr in CHECKS:
        # the area chevron sits on very different backgrounds (moon, night sky): match its gold shape only
        m = v.find_gold(img, tpl, region, 0.8) if tpl == "area_chevron" else v.find(img, tpl, region, thr)
        if m:
            if screen == "event_prefight":
                from .readers import fight_energy_cost
                if fight_energy_cost(img):  # ⚡ cost plate above FIGHT only exists in prize fights
                    return "prize_team", m
            return screen, m
    from .eventmap import looks_like_map
    if looks_like_map(img):  # story maps have no TIME REMAINING timer
        return "event_map", None
    return "unknown", None
