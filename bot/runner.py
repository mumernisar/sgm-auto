"""Main loop: look at the screen, let the mode handle it, repeat."""
import time
import traceback

from . import control
from .core import Ctx, Stop
from .modes import AutoMode, EventMode, PrizeMode

UNKNOWN_GRACE = 40  # seconds of unrecognised screens (loading, animations) before stopping
SCREENS = ["offer", "modifiers", "gifts_full", "cutscene", "keep_streak", "energy_refill", "moves_popup", "paused", "victory", "defeat", "filter", "team_picker",
           "fight", "prize_lobby", "prize_team", "event_prefight", "event_map", "event_list", "event_areas"]


def notify(ctx, msg):
    """Tell the user: the app's overlay shows every log line (bot.control feed)."""
    ctx.log(f"*** {msg}")


def report_error(ctx, screen, e):
    """Everything needed to find a bug later: traceback in the log, plus the screen it happened on."""
    ctx.log(f"  ! error on {screen}: {type(e).__name__}: {e}")
    for line in traceback.format_exc().rstrip().splitlines():
        ctx.log(f"    {line}")
    ctx.debug(f"error on {screen} {type(e).__name__}")


def run(dev, cfg):
    ctx = Ctx(dev, cfg)
    mode = {"event": EventMode, "prize": PrizeMode}.get(cfg.mode, AutoMode)(ctx)
    ctx.log(f"=== start: mode={cfg.mode} backend={cfg.backend} size={dev.size} dry_run={cfg.dry_run}")
    dev._run("input keyevent KEYCODE_WAKEUP")
    dev._run("svc power stayon true")
    last_charge = 0
    unknown_since = None
    last_screen = None
    errors = 0
    pauses = control.pauses
    deadline = time.time() + cfg.max_minutes * 60 if cfg.max_minutes else None
    try:
        if dev.screen_state() == "off":  # not at the size yet: switching restarts the game, so the user picks when
            if cfg.fit_screen:           # over adb: switch now, the user opens the event and runs again
                dev.switch_screen(True)
                raise Stop("switched the screen size and restarted the game: open your event or prize "
                           "fights, then run again (`adb shell wm size reset` to switch back)")
            raise Stop("the screen isn't at the bot's size yet (☰: Full / Fast): tap ⤢ on the panel first")
        while True:
            if deadline and time.time() > deadline:
                raise Stop(f"time limit of {cfg.max_minutes} min reached")
            if cfg.keep_charging_off and cfg.backend == "adb" and time.time() - last_charge > 300:
                dev.charging_off()
                last_charge = time.time()

            try:
                screen = ctx.look(fresh=True)
                if control.pauses != pauses:  # the user may have changed things in the game meanwhile
                    pauses = control.pauses
                    mode.forget_step()
                    ctx.log("  (after a pause: zoom, sweep, retries and team state are read again)")
                if screen != last_screen:
                    lives = mode.lives() if screen == "fight" else ""
                    ctx.log(f"[{screen} {lives}]" if lives else f"[{screen}]")
                    last_screen = screen

                if screen == "unknown":
                    unknown_since = unknown_since or time.time()
                    if time.time() - unknown_since > UNKNOWN_GRACE:
                        ctx.debug("unknown screen")
                        raise Stop(f"stuck on an unrecognised screen for {UNKNOWN_GRACE}s "
                                   f"(screenshot saved in {cfg.debug_dir})")
                else:
                    unknown_since = None
                    handler = mode.handler(screen)
                    if handler:
                        try:
                            handler()
                            errors = 0
                        except Stop:
                            raise
                        except Exception as e:  # odd frame / misread: log it, look again, give up after 3 in a row
                            errors += 1
                            report_error(ctx, screen, e)
                            if errors >= 3:
                                raise Stop(f"3 errors in a row on {screen}: {type(e).__name__}: {e} (see logs/bot.log)") from e
                    elif screen in SCREENS:
                        ctx.log(f"  ({screen} isn't used in {cfg.mode} mode — going back)")
                        mode.back("wrong mode screen")
            except control.Resumed:  # a pause interrupted the step: the screen may have changed, look again
                ctx.log("  (paused mid-step: looking at the screen again)")
                continue
            ctx.idle()
    except Stop as e:
        notify(ctx, f"stopped: {e}")
    except KeyboardInterrupt:
        ctx.log("=== stopped by user")
    except Exception as e:  # anything outside a handler: log it fully before exiting
        report_error(ctx, last_screen, e)
        notify(ctx, f"crashed: {type(e).__name__}: {e}")
    finally:
        dev._run("svc power stayon false")
        ctx.log(f"=== totals: wins {mode.wins}, losses {mode.losses}")
