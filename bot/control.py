"""Pause / resume / stop requests and a status feed, shared with a UI (the app's overlay).

The bot calls checkpoint() every time it looks at the screen, so a pause takes effect after the current action
and a stop ends the run there. Without a UI nothing ever pauses and the feed has no listeners.
"""
import threading

_resume = threading.Event()
_resume.set()
_stop_reason = None
_listeners = []


def pause():
    _resume.clear()


def resume():
    _resume.set()


def stop(reason="stopped from the overlay"):
    global _stop_reason
    _stop_reason = reason
    _resume.set()  # wake a paused bot so it can stop


def reset():
    global _stop_reason
    _stop_reason = None
    _resume.set()


def checkpoint():
    """Block while paused; raise Stop if a stop was requested."""
    from .core import Stop
    if not _resume.is_set():
        emit("⏸ paused")
        _resume.wait()
        if _stop_reason is None:
            emit("▶ resumed")
    if _stop_reason is not None:
        raise Stop(_stop_reason)


def subscribe(fn):
    _listeners.append(fn)


def emit(line):
    for fn in list(_listeners):
        try:
            fn(line)
        except Exception:
            pass
