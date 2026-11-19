"""Screen capture and input, either over adb (Mac, for development) or inside the Android app."""
import random
import subprocess
import time

import cv2
import numpy as np


class Device:
    """Base: subclasses implement _run(cmd, binary) to execute a shell command on the tablet."""

    def __init__(self, dry_run=False, log=print):
        self.dry_run = dry_run
        self.log = log

    def _run(self, cmd, binary=False):
        raise NotImplementedError

    def capture(self):
        """Return the current screen as a BGR numpy array (raw screencap, no PNG encode)."""
        raw = self._run("screencap", binary=True)
        w, h = np.frombuffer(raw[:8], np.uint32)
        header = len(raw) - int(w) * int(h) * 4  # 12 bytes on older Android, 16 on newer
        rgba = np.frombuffer(raw[header:], np.uint8).reshape(int(h), int(w), 4)
        return cv2.cvtColor(rgba, cv2.COLOR_RGBA2BGR)

    def tap(self, x, y, jitter=10, why=""):
        x, y = int(x + random.randint(-jitter, jitter)), int(y + random.randint(-jitter, jitter))
        self.log(f"tap ({x},{y}) {why}" + (" [dry-run]" if self.dry_run else ""))
        if not self.dry_run:
            self._run(f"input tap {x} {y}")

    def swipe(self, x1, y1, x2, y2, ms=400, why=""):
        self.log(f"swipe ({x1},{y1})->({x2},{y2}) {ms}ms {why}" + (" [dry-run]" if self.dry_run else ""))
        if not self.dry_run:
            self._run(f"input swipe {int(x1)} {int(y1)} {int(x2)} {int(y2)} {int(ms)}")

    def drag(self, x1, y1, x2, y2, why=""):
        """Drag-and-drop: Unity needs a hold before moving, which `input draganddrop` provides."""
        self.log(f"drag ({x1},{y1})->({x2},{y2}) {why}" + (" [dry-run]" if self.dry_run else ""))
        if not self.dry_run:
            self._run(f"input draganddrop {int(x1)} {int(y1)} {int(x2)} {int(y2)} 1200")

    # --- two-finger pinch (needs root: raw multi-touch events; `input` can only do one finger) -----------
    TOUCH_DEV = "/dev/input/event5"   # NVTCapacitiveTouchScreen
    TOUCH_MAX = (16000, 25600)         # panel axes, in portrait orientation
    PORTRAIT = (1600, 2560)            # portrait screen size in pixels

    def _to_panel(self, x, y):
        """Landscape screen pixel -> touch panel units (display is ROTATION_90)."""
        px, py = self.PORTRAIT[0] - y, x
        return int(px * self.TOUCH_MAX[0] / self.PORTRAIT[0]), int(py * self.TOUCH_MAX[1] / self.PORTRAIT[1])

    def pinch(self, center, start_gap, end_gap, steps=14, why=""):
        """Two fingers on a horizontal line through center, moving from start_gap apart to end_gap apart.
        end_gap < start_gap zooms out; end_gap > start_gap zooms in."""
        self.log(f"pinch {start_gap}->{end_gap} at {center} {why}" + (" [dry-run]" if self.dry_run else ""))
        if self.dry_run:
            return
        cx, cy = center
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

    # adb's shell user can already tap and screencap; root is only needed for these (and each su call makes
    # Magisk show a toast over the bottom of the screen, hiding card names)
    ROOT_ONLY = ("echo ", "svc ")

    def _run(self, cmd, binary=False):
        if binary:
            return subprocess.run(self.prefix + ["exec-out", cmd], capture_output=True, check=True).stdout
        shell_cmd = f"su -c '{cmd}'" if cmd.startswith(self.ROOT_ONLY) else cmd
        out = subprocess.run(self.prefix + ["shell", shell_cmd], capture_output=True, text=True)
        return out.stdout

    CHARGE_NODE = "/sys/class/qcom-battery/batt_charge_en"

    def charging_off(self):
        """Plugged into the Mac's USB the tablet charges all run long; stop that (it re-enables itself)."""
        self._run(f"echo 0 > {self.CHARGE_NODE}")

    def _run_script(self, script):
        """Push a shell script to the tablet and run it as root in one go (fast for many sendevents)."""
        path = "/data/local/tmp/sgm_gesture.sh"
        subprocess.run(self.prefix + ["shell", f"cat > {path}"], input=script, text=True, check=True)
        subprocess.run(self.prefix + ["shell", f"su -c 'sh {path}'"], capture_output=True, text=True)


class AppDevice(Device):
    """Inside the Android app: one persistent root shell owned by the app (RootShell.java), so Magisk asks
    once and shows no toast per command, and frames come back as raw bytes without spawning processes."""

    def __init__(self, **kw):
        super().__init__(**kw)
        from java import jclass  # Chaquopy's Java bridge; only exists inside the app
        self.shell = jclass("dev.umer.sgmbot.RootShell").get()

    def capture(self):
        raw = self.shell.screencap()
        w, h = self.shell.width(), self.shell.height()
        rgba = np.frombuffer(bytes(raw), np.uint8).reshape(h, w, 4)
        return cv2.cvtColor(rgba, cv2.COLOR_RGBA2BGR)

    def _run(self, cmd, binary=False):
        return str(self.shell.exec(cmd))

    def _run_script(self, script):
        self.shell.exec(script)


def connect(backend, dry_run=False, log=print):
    cls = {"adb": AdbDevice, "app": AppDevice}[backend]
    return cls(dry_run=dry_run, log=log)
