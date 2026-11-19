"""Shared runtime: device, config, logging, debug images and small 'act then wait' helpers."""
import random
import time
from datetime import datetime
from pathlib import Path

import cv2

from . import control, screens
from . import vision as v
from .config import ROOT


class Stop(Exception):
    """Raised to stop the bot cleanly with a reason the user should see."""


class Ctx:
    def __init__(self, dev, cfg):
        self.dev = dev
        self.cfg = cfg
        self.debug_dir = ROOT / cfg.debug_dir
        self.debug_dir.mkdir(parents=True, exist_ok=True)
        (ROOT / "logs").mkdir(exist_ok=True)
        self.log_file = open(ROOT / "logs" / "bot.log", "a", buffering=1)
        self.counter = 0
        self.img = None
        self.screen = None
        dev.log = self.log

    # --- logging -------------------------------------------------------------------------------
    def log(self, msg):
        line = f"{datetime.now():%H:%M:%S} {msg}"
        print(line, flush=True)
        self.log_file.write(line + "\n")
        control.emit(line)

    def debug(self, label, marks=()):
        """Save a small annotated screenshot: marks are (x, y) taps or (x, y, w, h) boxes."""
        if self.img is None:
            return
        img = self.img.copy()
        for m in marks:
            if len(m) == 2:
                cv2.circle(img, (int(m[0]), int(m[1])), 30, (0, 0, 255), 6)
            else:
                x, y, w, h = map(int, m)
                cv2.rectangle(img, (x, y), (x + w, y + h), (0, 255, 0), 4)
        cv2.putText(img, label[:80], (20, 1580), cv2.FONT_HERSHEY_SIMPLEX, 1.4, (0, 255, 255), 3)
        self.counter += 1
        name = f"{datetime.now():%m%d-%H%M%S}_{self.counter:04d}_{label[:40].replace(' ', '_')}.jpg"
        cv2.imwrite(str(self.debug_dir / name), cv2.resize(img, (1280, 800)), [cv2.IMWRITE_JPEG_QUALITY, 70])
        files = sorted(self.debug_dir.glob("*.jpg"))
        for old in files[:-self.cfg.keep_debug_images]:
            old.unlink()

    # --- screen ----------------------------------------------------------------------------------
    def look(self):
        control.checkpoint()  # honour pause / stop from the overlay between actions
        self.img = self.dev.capture()
        self.screen, _ = screens.detect(self.img)
        return self.screen

    def wait_for(self, wanted, timeout=12, interval=0.7):
        """Capture until the screen is one of `wanted`; returns the screen or None on timeout."""
        wanted = (wanted,) if isinstance(wanted, str) else wanted
        end = time.time() + timeout
        while time.time() < end:
            if self.look() in wanted:
                return self.screen
            time.sleep(interval)
        return None

    def settle(self, seconds=1.0):
        """Screens slide/fade in: give them a moment, then capture again."""
        time.sleep(seconds)
        return self.look()

    def wait_change(self, current, timeout=8, interval=0.6):
        """After an action, wait until the screen is no longer one of `current` (popups animate in)."""
        current = (current,) if isinstance(current, str) else current
        end = time.time() + timeout
        while time.time() < end:
            time.sleep(interval)
            if self.look() not in current:
                return self.screen
        return None

    # --- actions ---------------------------------------------------------------------------------
    def tap(self, x, y, why, jitter=None):
        self.debug(why, [(x, y)])
        self.dev.tap(x, y, self.cfg.tap_jitter if jitter is None else jitter, why)
        self.dev.pause(0.5, 1.1)

    def tap_template(self, name, region=None, threshold=0.75, why=None):
        """Find a button by template on the current image and tap it. Returns False if it isn't there."""
        m = v.find(self.img, name, region, threshold)
        if not m:
            self.log(f"  {name} not found")
            return False
        self.tap(*m.center, why or name)
        return True

    def drag(self, a, b, why):
        self.debug(why, [a, b])
        self.dev.drag(*a, *b, why=why)
        self.dev.pause(0.9, 1.5)

    def swipe(self, a, b, ms, why):
        self.dev.swipe(*a, *b, ms=ms, why=why)
        self.dev.pause(0.6, 1.0)

    def idle(self):
        lo, hi = self.cfg.delay
        if random.random() < self.cfg.long_pause_chance:
            lo, hi = self.cfg.long_pause
        time.sleep(random.uniform(lo, hi))
