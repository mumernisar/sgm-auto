"""Pause / resume / stop requests and a status feed, shared with a UI (the app's overlay).

checkpoint() runs before every touch (Device), between template searches (vision) and every time the bot looks
at the screen, so a pause holds the bot within moments and no touch happens while paused. A step that was
interrupted by a pause is dropped on resume (Resumed): the user may have changed the screen meanwhile, so the bot
looks again instead of finishing taps it worked out for the old screen. `pauses` counts every pause (also one that
began and ended while the bot slept between steps), so the runner can clear what the modes remember about the
screen (Mode.forget_step). A stop ends the run at the same points.
Without a UI nothing ever pauses and the feed has no listeners.
"""
import threading

_resume = threading.Event()
_resume.set()
_stop_reason = None
_listeners = []
pauses = 0  # pauses requested so far


class Resumed(BaseException):
    """A pause interrupted the current step: drop it and look at the screen again. A BaseException so the
    handlers' `except Exception` (misread frames) doesn't swallow it."""


def pause():
    global pauses
    pauses += 1
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


def checkpoint(fresh=False):
    """Block while paused; raise Stop if a stop was requested. After a pause, raise Resumed unless the caller is
    about to start afresh anyway (fresh=True: the main loop's look at the screen)."""
    from .core import Stop
    if _stop_reason is not None:
        raise Stop(_stop_reason)
    if _resume.is_set():
        return
    emit("⏸ paused")
    _resume.wait()
    if _stop_reason is not None:
        raise Stop(_stop_reason)
    emit("▶ resumed")
    if not fresh:
        raise Resumed()


def subscribe(fn):
    _listeners.append(fn)


def emit(line):
    for fn in list(_listeners):
        try:
            fn(line)
        except Exception:
            pass
