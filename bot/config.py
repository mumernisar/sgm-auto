"""Settings. Defaults below; override any of them in config.json next to run.py."""
import json
import os
from dataclasses import dataclass, fields
from pathlib import Path

# where logs/, config.json and templates/ live: the project folder, or the app's storage (SGM_HOME)
ROOT = Path(os.environ.get("SGM_HOME") or Path(__file__).resolve().parent.parent)


@dataclass
class Config:
    mode: str = "auto"                  # "auto" (detect from the screen) | "event" | "prize"
    backend: str = "adb"                # "adb" (Mac) | "app" (the Android app)
    dry_run: bool = False               # log + annotate only, never tap
    max_minutes: float = 0              # stop after this long (0 = run until stopped)

    # pacing / humanising
    delay: tuple = (1.2, 2.6)           # seconds between loop iterations
    long_pause_chance: float = 0.04     # occasionally idle a bit longer
    long_pause: tuple = (4.0, 9.0)
    tap_jitter: int = 12

    # event mode
    max_event_losses: int = 3           # REMATCH up to this many losses per node, then QUIT

    # prize fights
    max_enemy_total: int = 30000        # never pick opponents above this
    restored_max_enemy_total: int = 10000  # right after a free streak restore
    anchor_range: tuple = (0.8, 1.5)    # anchor score as a fraction of enemy total (first fit wins)
    small_total: int = 3000             # enemy totals up to this may use a stronger anchor ...
    small_total_max: float = 2.0        # ... up to this multiple
    pair_above: int = 5000              # above this enemy total use two anchors ...
    pair_range: tuple = (0.4, 0.75)     # ... each this fraction of the enemy total (together ~0.8-1.5x)
    big_total: int = 15000              # above this enemy total auto battle needs more margin:
    big_pair_range: tuple = (0.6, 0.9)  # ... each anchor this fraction (together ~1.2-1.8x)
    # where to look for an anchor of at least `lo`: (min lo, rarities to filter, ascending sort)
    anchor_search: tuple = ((0, ("silver", "gold", "diamond"), True),
                            (2500, ("gold", "diamond"), False),
                            (9000, ("diamond",), False))
    base_rarities: tuple = ("silver", "gold", "diamond")
    use_energy_refills: bool = False

    # safety / housekeeping
    keep_charging_off: bool = True      # over adb only (USB keeps the tablet charging); the app never touches it
    debug_dir: str = "logs/debug"
    keep_debug_images: int = 400



def load(overrides=None):
    cfg = Config()
    path = ROOT / "config.json"
    data = json.loads(path.read_text()) if path.exists() else {}
    data.update(overrides or {})
    names = {f.name for f in fields(Config)}
    for k, val in data.items():
        if k not in names:
            raise ValueError(f"unknown config key: {k}")
        setattr(cfg, k, tuple(val) if isinstance(val, list) else val)
    return cfg
