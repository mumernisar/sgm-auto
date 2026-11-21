package dev.umer.sgmbot;

import android.os.SystemClock;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;

/**
 * Notices a finger on the screen, so the panel can pause the bot when the user takes over. The bot's own touches
 * (`input tap / swipe / draganddrop`, the injected pinch) go into Android's input system and never show on the
 * touchscreen device; a finger does. It reads `getevent` on the touchscreen (the device reporting
 * ABS_MT_POSITION_X) in its own shell ({@link RootShell#openSecond()}), which sleeps until there's an event.
 *
 * The tablet's root pinch is the exception: it writes to the touchscreen device itself, so the bot calls
 * {@link #ignoreFor} around it. Touches on the panel are the panel's to filter (it sees them as views).
 */
final class TouchWatcher {
    interface Listener {
        /** A new finger came down, at {@link SystemClock#uptimeMillis()} time (on the watcher's thread). */
        void onTouch(long at);

        /** Watching isn't possible (no touchscreen found, getevent not readable); said once. */
        void onUnavailable(String why);
    }

    private static volatile long ignoreUntil;

    /** The bot is about to write touch events itself (root pinch): not the user's for the next ms. */
    public static void ignoreFor(long ms) {
        ignoreUntil = SystemClock.uptimeMillis() + ms;
    }

    private final Listener listener;
    private volatile RootShell shell;
    private volatile Thread thread;

    TouchWatcher(Listener listener) {
        this.listener = listener;
    }

    /** Starts watching unless it already is; safe to call again (▶ retries if Shizuku wasn't up earlier). */
    synchronized void start() {
        if (thread != null && thread.isAlive()) {
            return;
        }
        thread = new Thread(this::watch, "sgm-touch");
        thread.setDaemon(true);
        thread.start();
    }

    synchronized void stop() {
        Thread t = thread;
        thread = null;
        RootShell s = shell;
        shell = null;
        if (s != null) {
            s.close();
        }
        if (t != null) {
            t.interrupt();
        }
    }

    private void watch() {
        RootShell s;
        String device;
        try {
            s = RootShell.openSecond();
            device = touchscreen(s.exec("getevent -pl"));
        } catch (IOException e) {
            return; // no shell yet (Shizuku not running): the next ▶ tries again, and says why if it fails
        }
        if (device == null) {
            s.close();
            listener.onUnavailable("no touchscreen found in getevent: touching the screen won't pause the bot");
            return;
        }
        shell = s;
        try (BufferedReader in = new BufferedReader(new InputStreamReader(s.stream("getevent -ql " + device),
                StandardCharsets.UTF_8))) {
            for (String line; (line = in.readLine()) != null; ) {
                if (newContact(line) && SystemClock.uptimeMillis() >= ignoreUntil) {
                    listener.onTouch(SystemClock.uptimeMillis());
                }
            }
        } catch (IOException ignored) {
            // closed by stop()
        }
        if (shell == s) { // ended by itself: getevent couldn't read the device
            shell = null;
            s.close();
            listener.onUnavailable("can't read the touchscreen (" + device + "): touching the screen won't pause the bot");
        }
    }

    /** The device whose `getevent -pl` block lists multi-touch positions and INPUT_PROP_DIRECT (on the screen, not
     * a touchpad: the S23 lists `sec_touchpad` before `sec_touchscreen`, both multi-touch); failing that, the first
     * multi-touch device; null if none. */
    static String touchscreen(String list) {
        String current = null;
        String fallback = null;
        boolean multiTouch = false;
        boolean direct = false;
        for (String line : (list + "\nadd device end").split("\n")) {
            line = line.trim();
            if (line.startsWith("add device")) {
                if (current != null && multiTouch && direct) {
                    return current;
                }
                if (current != null && multiTouch && fallback == null) {
                    fallback = current;
                }
                int at = line.indexOf("/dev/input/");
                current = at >= 0 ? line.substring(at).trim() : null;
                multiTouch = direct = false;
            } else if (line.contains("ABS_MT_POSITION_X")) {
                multiTouch = true;
            } else if (line.equals("INPUT_PROP_DIRECT")) {
                direct = true;
            }
        }
        return fallback;
    }

    /** A finger coming down: a tracking id other than ffffffff (lift), or BTN_TOUCH DOWN (one finger can send
     * both: the listener ignores a touch while already paused). */
    static boolean newContact(String line) {
        String[] p = line.trim().split("\\s+");
        if (p.length < 3) {
            return false;
        }
        return p[1].equals("ABS_MT_TRACKING_ID") && !p[2].equalsIgnoreCase("ffffffff")
                || p[1].equals("BTN_TOUCH") && p[2].equals("DOWN");
    }
}
