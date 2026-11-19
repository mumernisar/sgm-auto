"""Entry points the overlay (OverlayService.java) calls: start / pause / resume / stop the bot."""
import os
import threading

_thread = None


def init(home):
    """home: the app's files dir, holding templates/, tessdata/ and logs/. Must run before importing bot."""
    os.environ["SGM_HOME"] = home


def start(mode, listener):
    """Run the bot in a background thread. listener.onLine(str) gets every log line,
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
            cfg = config.load({"backend": "app", "mode": mode})
            run(device.connect("app"), cfg)
        except Exception as e:  # anything before the runner's own handling (e.g. no root)
            listener.onLine(f"*** couldn't start: {type(e).__name__}: {e}")
        finally:
            listener.onFinished()

    _thread = threading.Thread(target=go, name="sgm-bot", daemon=True)
    _thread.start()
    return True


def pause():
    from bot import control
    control.pause()


def resume():
    from bot import control
    control.resume()


def stop():
    from bot import control
    control.stop()
