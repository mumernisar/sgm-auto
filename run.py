"""Skullgirls Mobile bot.

    .venv/bin/python run.py event              # event map mode, over adb from the Mac
    .venv/bin/python run.py prize --dry-run    # prize fights, log + annotate only, no taps
    .venv/bin/python run.py look               # one capture: which screen + what the readers see
"""
import argparse

from bot import config, device


def look(dev):
    import time
    from bot import eventmap, readers as r, screens
    dev._run("input keyevent KEYCODE_WAKEUP")
    time.sleep(1)
    from bot.frame import design
    raw = dev.capture()
    img = design(raw)  # readers measure on 2560x1600; detection and the map read take the frame as captured
    screen, m = screens.detect(raw)
    print("screen:", screen, f"({m.score:.2f})" if m else "")
    if screen in ("event_prefight", "prize_team", "team_picker"):
        print("scores:", r.team_scores(img), "fight enabled:", r.fight_enabled(img), "cost:", r.fight_energy_cost(img))
        for q in r.requirements(img):
            print("requirement:", q)
    if screen == "team_picker":
        for s in r.team_slots(img):
            print("slot:", s)
        for c in r.picker_cards(img, with_energy=True):
            print("card:", c)
    if screen == "prize_lobby":
        for o in r.lobby_opponents(img):
            print("opponent:", o)
    if screen == "event_map":
        st = eventmap.read(raw)
        for n in st.nodes:
            print("node:", n, "<- current" if n is st.current else "")
        print("choose:", eventmap.choose(st))
    if screen == "fight":
        print("auto:", r.auto_state(img))


def main():
    p = argparse.ArgumentParser()
    p.add_argument("mode", choices=["auto", "event", "prize", "look"])
    p.add_argument("--dry-run", action="store_true", help="never tap, just log and save annotated screenshots")
    p.add_argument("--minutes", type=float, default=0, help="stop after this many minutes")
    p.add_argument("--size", choices=["auto", "full", "fast"], help="screen size (default: config screen_size)")
    a = p.parse_args()
    overrides = {"backend": "adb", "dry_run": a.dry_run, "max_minutes": a.minutes}
    if a.size:
        overrides["screen_size"] = a.size
    if a.mode != "look":
        overrides["mode"] = a.mode
    cfg = config.load(overrides)
    dev = device.connect(cfg.backend, dry_run=cfg.dry_run, size=cfg.screen_size)
    if a.mode == "look":
        look(dev)
        return
    from bot.runner import run
    run(dev, cfg)


if __name__ == "__main__":
    main()
