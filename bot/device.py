"""Screen capture and input, either over adb (Mac, for development) or inside the Android app."""
import random
import re
import subprocess
import time

import cv2
import numpy as np

from . import control
from .frame import k_of

# screen sizes the bot runs at (landscape): templates and tap points are measured on the reference tablet's
# 2560x1600 (design units, see `frame`); Fast is the same 16:10 layout at 56% of the pixels
SIZES = {"full": (2560, 1600), "fast": (1920, 1200)}


class Device:
    """Base: subclasses implement _run(cmd, binary) to execute a shell command on the tablet.
    Touches are given in design units and converted to the screen's pixels with k, the last frame's scale."""

    def __init__(self, dry_run=False, log=print, size="auto"):
        self.dry_run = dry_run
        self.log = log
        self.size = size  # "full" | "fast" | "auto" (full on a 2560x1600 screen, fast elsewhere)
        self.k = 1.0

    def _seen(self, frame):
        self.k = k_of(frame)
        return frame

    def _run(self, cmd, binary=False):
        raise NotImplementedError

    def capture(self):
        """Return the current screen as a BGR numpy array (raw screencap, no PNG encode)."""
        raw = self._run("screencap", binary=True)
        w, h = np.frombuffer(raw[:8], np.uint32)
        header = len(raw) - int(w) * int(h) * 4  # 12 bytes on older Android, 16 on newer
        rgba = np.frombuffer(raw[header:], np.uint8).reshape(int(h), int(w), 4)
        return self._seen(cv2.cvtColor(rgba, cv2.COLOR_RGBA2BGR))

    def _px(self, *vals):
        """Design units -> screen pixels (`input` uses the screen size set by `wm size`)."""
        k = self.k
        return [int(v) for v in vals] if k == 1.0 else [round(v * k) for v in vals]

    def tap(self, x, y, jitter=10, why=""):
        control.checkpoint()  # no touch while paused; a paused step isn't finished
        x, y = self._px(x + random.randint(-jitter, jitter), y + random.randint(-jitter, jitter))
        self.log(f"tap ({x},{y}) {why}" + (" [dry-run]" if self.dry_run else ""))
        if not self.dry_run:
            self._run(f"input tap {x} {y}")

    def swipe(self, x1, y1, x2, y2, ms=400, why=""):
        control.checkpoint()  # no touch while paused; a paused step isn't finished
        x1, y1, x2, y2 = self._px(x1, y1, x2, y2)
        self.log(f"swipe ({x1},{y1})->({x2},{y2}) {ms}ms {why}" + (" [dry-run]" if self.dry_run else ""))
        if not self.dry_run:
            self._run(f"input swipe {x1} {y1} {x2} {y2} {int(ms)}")

    def drag(self, x1, y1, x2, y2, why=""):
        """Drag-and-drop: Unity needs a hold before moving, which `input draganddrop` provides."""
        control.checkpoint()  # no touch while paused; a paused step isn't finished
        x1, y1, x2, y2 = self._px(x1, y1, x2, y2)
        self.log(f"drag ({x1},{y1})->({x2},{y2}) {why}" + (" [dry-run]" if self.dry_run else ""))
        if not self.dry_run:
            self._run(f"input draganddrop {x1} {y1} {x2} {y2} 1200")

    # --- screen size: templates and tap points are in the reference tablet's 2560x1600 --------------------
    # Any other screen is switched to Full (2560x1600) or Fast (1920x1200) with `wm size`, which the shell user may
    # do: the game then draws the tablet's 16:10 layout, with black bars on a wider screen, and nothing needs
    # re-measuring. The game (an old Unity) keeps drawing at the size it started with, stretched, so it has to be
    # restarted after each switch.
    GAME = "com.autumn.skullgirls"

    def screen_sizes(self):
        """(physical (w, h), override (w, h) or None), as `wm size` reports them (portrait on most devices)."""
        out = self._run("wm size")
        sizes = {k: (int(w), int(h)) for k, w, h in re.findall(r"(Physical|Override) size: (\d+)x(\d+)", out)}
        return sizes.get("Physical"), sizes.get("Override")

    def _target(self, physical):
        """The size to run at, in the screen's own orientation: Full on a 2560x1600 screen (the tablet) and Fast
        elsewhere, unless the user picked one."""
        size = self.size
        if size not in SIZES:
            size = "full" if sorted(physical) == sorted(SIZES["full"]) else "fast"
        w, h = SIZES[size]
        return (w, h) if physical[0] > physical[1] else (h, w)

    def game_buffer(self):
        """(w, h) the running game draws at, from SurfaceFlinger; None if it isn't running (or unreadable)."""
        out = self._run(f"dumpsys SurfaceFlinger | grep -A 14 'SurfaceView\\[{self.GAME}'")
        m = (re.search(r"geomBufferSize=\[0 0 (\d+) (\d+)\]", out)            # on screen, Android 13+
             or re.search(r"activeBuffer=\[\s*(\d+)\s*x\s*(\d+)", out)        # on screen, older
             or re.search(r"buffer: (\d+)x(\d+)", out)
             or re.search(rf"SurfaceView\[{re.escape(self.GAME)}[^\n]*w/h:(\d+)x(\d+)", out))  # buffer list (background too)
        return (int(m.group(1)), int(m.group(2))) if m else None

    def screen_state(self):
        """'native': the screen already is the size to run at (the tablet at Full), nothing to do. 'on': switched
        to it and the game draws at that size (or isn't running, so it will). 'off': needs switch_screen(True)
        first (not switched, switched to the other size, or the game started before the switch)."""
        physical, override = self.screen_sizes()
        if not physical:
            return "native"  # unreadable: let the run show what it sees
        target = self._target(physical)
        if physical == target:  # the tablet at Full: native, unless it's still switched to Fast
            return "native" if override in (None, physical) else "off"
        if (override or physical) != target:
            return "off"
        buf = self.game_buffer()
        # started before the switch: stretched (not 16:10), or drawing at the other size (Full <-> Fast)
        if buf and (abs(max(buf) / min(buf) - 1.6) > 0.02 or abs(max(buf) / max(target) - 1) > 0.02):
            return "off"
        return "on"

    def switch_screen(self, on, relaunch=True):
        """Switch to the size to run at (on) or back, and restart the game so it draws at the new size.
        relaunch=False only closes it (from the app's own screen, where opening the game would be unexpected)."""
        physical, _ = self.screen_sizes()
        if not physical:
            return
        target = self._target(physical)
        on = on and physical != target  # the tablet at Full: nothing to switch
        self.log(f"screen -> {target[0]}x{target[1]}, restarting the game" if on else "screen back to normal")
        self._run(f"wm size {target[0]}x{target[1]}" if on else "wm size reset")
        self._run(f"am force-stop {self.GAME}")
        if relaunch:
            self._run(f"monkey -p {self.GAME} -c android.intent.category.LAUNCHER 1")

    # --- two-finger pinch (`input` can only do one finger) ------------------------------------------------
    # Root on the reference tablet: raw multi-touch events with `sendevent`. Anywhere else (and without root,
    # where SELinux blocks /dev/input) the app's Pinch class injects a MotionEvent as the shell user, in screen
    # pixels, so it needs no touch panel details. It runs from the installed SGM Bot APK.
    TOUCH_DEV = "/dev/input/event5"   # NVTCapacitiveTouchScreen
    TOUCH_MAX = (16000, 25600)         # panel axes, in portrait orientation
    PORTRAIT = (1600, 2560)            # portrait screen size in pixels
    APP = "dev.umer.sgmbot"
    _root = None
    _apk = None
    _physical = None

    @property
    def root(self):
        """Whether `su` exists (checked without calling it: each su call over adb shows a Magisk toast)."""
        if self._root is None:
            self._root = bool(self._run("command -v su").strip())
        return self._root

    def _pinch_by_sendevent(self):
        if self._physical is None:
            self._physical = self.screen_sizes()[0]
        return self.root and self._physical == self.PORTRAIT

    def _apk_path(self):
        if self._apk is None:
            m = re.search(r"package:(\S+)", self._run(f"pm path {self.APP}"))
            if not m:
                raise RuntimeError(f"pinch zoom needs the SGM Bot app ({self.APP}) installed on the device")
            self._apk = m.group(1)
        return self._apk

    def _to_panel(self, x, y):
        """Landscape screen pixel -> touch panel units (display is ROTATION_90)."""
        px, py = self.PORTRAIT[0] - y, x
        return int(px * self.TOUCH_MAX[0] / self.PORTRAIT[0]), int(py * self.TOUCH_MAX[1] / self.PORTRAIT[1])

    def pinch(self, center, start_gap, end_gap, steps=14, why=""):
        """Two fingers on a horizontal line through center, moving from start_gap apart to end_gap apart.
        end_gap < start_gap zooms out; end_gap > start_gap zooms in."""
        control.checkpoint()
        self.log(f"pinch {start_gap}->{end_gap} at {center} {why}" + (" [dry-run]" if self.dry_run else ""))
        if self.dry_run:
            return
        cx, cy = center
        if not self._pinch_by_sendevent():  # screen pixels, like `input`
            cx, cy, start_gap, end_gap = self._px(cx, cy, start_gap, end_gap)
            self._run(f"CLASSPATH={self._apk_path()} app_process / {self.APP}.Pinch "
                      f"{cx} {cy} {start_gap} {end_gap} {steps} 20")
            return
        # sendevent (the tablet, root): physical pixels, which are design units on the 2560x1600 panel even when
        # the screen runs at Fast's 1920x1200
        lines = []

        def ev(t, c, val):
            lines.append(f"sendevent {self.TOUCH_DEV} {t} {c} {val}")

        def fingers(gap):
            for slot, sign in ((0, -1), (1, 1)):
                x, y = self._to_panel(cx + sign * gap / 2, cy)
                ev(3, 47, slot)
                ev(3, 53, x)
                ev(3, 54, y)
            ev(0, 0, 0)

        for slot in (0, 1):
            ev(3, 47, slot)
            ev(3, 57, 900 + slot)   # tracking id
            ev(3, 48, 8)            # touch major
            ev(3, 58, 60)           # pressure
        ev(1, 330, 1)               # BTN_TOUCH down
        fingers(start_gap)
        for k in range(1, steps + 1):
            fingers(start_gap + (end_gap - start_gap) * k / steps)
            lines.append("sleep 0.02")
        for slot in (0, 1):
            ev(3, 47, slot)
            ev(3, 57, 4294967295)  # lift
        ev(1, 330, 0)
        ev(0, 0, 0)
        self._run_script("\n".join(lines))

    @staticmethod
    def pause(lo=0.6, hi=1.4):
        time.sleep(random.uniform(lo, hi))


class AdbDevice(Device):
    def __init__(self, serial=None, **kw):
        super().__init__(**kw)
        self.prefix = ["adb"] + (["-s", serial] if serial else [])

    # adb's shell user can already tap and screencap; root is only used for these when the device has it (and
    # each su call makes Magisk show a toast over the bottom of the screen, hiding card names)
    ROOT_ONLY = ("echo ", "svc ")

    def _run(self, cmd, binary=False):
        if binary:
            return subprocess.run(self.prefix + ["exec-out", cmd], capture_output=True, check=True).stdout
        shell_cmd = f"su -c '{cmd}'" if cmd.startswith(self.ROOT_ONLY) and self.root else cmd
        out = subprocess.run(self.prefix + ["shell", shell_cmd], capture_output=True, text=True)
        return out.stdout

    CHARGE_NODE = "/sys/class/qcom-battery/batt_charge_en"

    def charging_off(self):
        """Plugged into the Mac's USB the tablet charges all run long; stop that (it re-enables itself)."""
        if self.root:
            self._run(f"echo 0 > {self.CHARGE_NODE}")

    def _run_script(self, script):
        """Push a shell script to the tablet and run it as root in one go (fast for many sendevents)."""
        path = "/data/local/tmp/sgm_gesture.sh"
        subprocess.run(self.prefix + ["shell", f"cat > {path}"], input=script, text=True, check=True)
        subprocess.run(self.prefix + ["shell", f"su -c 'sh {path}'"], capture_output=True, text=True)


class AppDevice(Device):
    """Inside the Android app: one persistent shell owned by the app (RootShell.java), as root through Magisk or
    as adb's shell user through Shizuku. Magisk asks once and shows no toast per command, and frames come back
    as raw bytes without spawning processes."""

    def __init__(self, **kw):
        super().__init__(**kw)
        from java import jclass  # Chaquopy's Java bridge; only exists inside the app
        self._jclass = jclass
        self.shell = jclass("dev.umer.sgmbot.RootShell").get()

    def capture(self):
        raw = self.shell.screencap()
        w, h = self.shell.width(), self.shell.height()
        rgba = np.frombuffer(bytes(raw), np.uint8).reshape(h, w, 4)
        return self._seen(cv2.cvtColor(rgba, cv2.COLOR_RGBA2BGR))

    def _run(self, cmd, binary=False):
        return str(self.shell.exec(cmd))

    def _run_script(self, script):
        """The root pinch's sendevent script: it writes to the touchscreen itself, so the panel's TouchWatcher is
        told these touches are the bot's (it pauses the run when the user touches the screen)."""
        watcher = self._jclass("dev.umer.sgmbot.TouchWatcher")
        watcher.ignoreFor(3000)  # until it's done (it takes ~0.5 s)
        try:
            self.shell.exec(script)
        finally:
            watcher.ignoreFor(500)  # events still on their way through getevent


def connect(backend, dry_run=False, log=print, size="auto"):
    cls = {"adb": AdbDevice, "app": AppDevice}[backend]
    return cls(dry_run=dry_run, log=log, size=size)
