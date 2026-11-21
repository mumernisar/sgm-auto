"""Entry points the overlay (OverlayService.java) calls: start / pause / resume / stop the bot, and the 16:10
screen switch (⤢)."""
import os
import threading

_thread = None


def init(home):
    """home: the app's files dir, holding templates/, tessdata/ and logs/. Must run before importing bot."""
    os.environ["SGM_HOME"] = home


def start(mode, size, listener):
    """Run the bot in a background thread. size: the panel's Full / Fast ("full" / "fast" / "auto").
    listener.onLine(str) gets every log line,
    listener.onFinished() is called when the run ends. Returns False if a run is already going."""
    global _thread
    if _thread and _thread.is_alive():
        return False
    from bot import config, control, device
    from bot.runner import run

    control.reset()
    control._listeners.clear()
    control.subscribe(lambda line: listener.onLine(line))

    def go():
        try:
            cfg = config.load({"backend": "app", "mode": mode, "screen_size": size,
                               "fit_screen": False})  # the panel's ⤢ does it
            run(device.connect("app", size=cfg.screen_size), cfg)
        except Exception as e:  # anything before the runner's own handling (e.g. no root)
            listener.onLine(f"*** couldn't start: {type(e).__name__}: {e}")
        finally:
            listener.onFinished()

    _thread = threading.Thread(target=go, name="sgm-bot", daemon=True)
    _thread.start()
    return True


def _device(size="auto"):
    from bot import device
    return device.connect("app", log=lambda line: None, size=size)


def screen_state(size):
    """'native' (already at the size: no ⤢), 'on' (switched, the game draws at it) or 'off' (▶ needs ⤢ first).
    size: the panel's Full / Fast."""
    return _device(size).screen_state()


def screen_on(size):
    """⤢: switch to the panel's size (Full 2560x1600 / Fast 1920x1200) and restart the game in it."""
    _device(size).switch_screen(True)


def screen_off(relaunch):
    """⤢ again, Hide the panel, Reset screen size: back to normal; the game restarts (or just closes)."""
    _device().switch_screen(False, relaunch)


def pause():
    from bot import control
    control.pause()


def resume():
    from bot import control
    control.resume()


def stop():
    from bot import control
    control.stop()
