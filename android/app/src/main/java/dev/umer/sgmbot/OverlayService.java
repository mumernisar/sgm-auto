package dev.umer.sgmbot;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.Service;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.ServiceInfo;
import android.content.res.Configuration;
import android.media.AudioAttributes;
import android.net.Uri;
import android.graphics.Color;
import android.graphics.PixelFormat;
import android.graphics.Rect;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.hardware.display.DisplayManager;
import android.os.Handler;
import android.os.IBinder;
import android.os.Looper;
import android.text.TextUtils;
import android.util.TypedValue;
import android.view.Display;
import android.view.Gravity;
import android.view.MotionEvent;
import android.view.View;
import android.view.WindowManager;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.RadioButton;
import android.widget.RadioGroup;
import android.widget.TextView;

import com.chaquo.python.PyObject;
import com.chaquo.python.Python;

import java.util.ArrayDeque;

/**
 * The floating control: a small translucent pill (current step, play/pause, stop, expand) docked top-left over
 * the game's home button, avatar and the player's name, which the bot never needs. Expanding it shows recent
 * steps and the mode, and pauses the bot so it never taps through or screenshots the open panel.
 *
 * The pill is sized and placed in the game's 2560x1600 frame, so on every device it covers the same spot as on
 * the reference tablet and stays clear of the pause button, the score bar's requirement icons and the back arrow.
 *
 * The bot runs at one of two sizes, picked under ☰: Full (2560x1600) or Fast (1920x1200, the same layout with
 * 56% of the pixels: image work ~40% faster). Default: Full on a 2560x1600 screen (the tablet), Fast elsewhere.
 * A screen not at that size needs ⤢ first: it switches the screen and restarts the game (which keeps drawing at
 * the size it started with). Until then ▶ and ■ are greyed out, and tapping them flashes ⤢. The switch is the
 * user's to make because it restarts the game; it lasts until ⤢ again or Hide the panel. Picking the other size
 * while switched greys ▶ ■ again until ⤢.
 *
 * A finger on the game during a run pauses it ({@link TouchWatcher}): the user is taking over. Touches on the
 * panel itself don't count.
 */
public class OverlayService extends Service implements BotListener, TouchWatcher.Listener {
    private static final String CHANNEL = "overlay";
    private static final String CHANNEL_END = "run_end_aosp"; // AOSP's Antares (res/raw/run_end.ogg)
    private static final int MAX_LINES = 10;
    private static final float REF_WIDTH = 2560f;     // the game frame's long side
    private static final float REF_PX_PER_UNIT = 2.5f; // the reference tablet's density: 1 unit = 1 dp there
    private static final int HOME_X = 150, HOME_Y = 0; // pill's top-left in the game frame: over home/avatar/name
    // two rows: big buttons (⤢ ▶ ■ ☰), then the status line. ~490 wide, so it ends at ~640, well before the player's
    // own score at ~810; ~170 tall, above the STREAK label (~250). Clear of the back arrow and the score bar
    private static final int LAYOUT = 3; // bumped when HOME or the pill's size changes: old saved spots are dropped
    private static final int BUTTON_W = 46, BUTTON_H = 48; // layout units: ~7 mm on the S23, easy to hit
    // text presentation: Samsung otherwise draws ▶ and ⏸ as coloured emoji
    private static final String PLAY = "\u25B6\uFE0E", PAUSE = "\u23F8\uFE0E", STOP = "\u25A0\uFE0E", RESIZE = "\u2922";
    private static final int GREEN = Color.rgb(110, 220, 130), AMBER = Color.rgb(255, 190, 90);

    private final Handler main = new Handler(Looper.getMainLooper());
    private final ArrayDeque<String> lines = new ArrayDeque<>();
    private WindowManager wm;
    private WindowManager.LayoutParams params;
    private SharedPreferences prefs;
    private float scale;  // screen px per game-frame px
    private float unit;   // screen px per layout unit
    private LinearLayout root;
    private TextView status;
    private TextView log;
    private Button playPause;
    private Button stopButton;
    private Button resize;
    private String screen = "native"; // app_main.screen_state(): native / on / off
    private boolean switching;        // ⤢ is restarting the game
    private LinearLayout details;
    private PyObject bot;
    private String mode = "auto";
    private String size;           // "full" / "fast": the screen size the bot runs at (☰)
    private boolean running;
    private boolean paused;
    private boolean pausedByPanel;
    private boolean stopRequested; // ■ pressed: the run ends without the chime
    private String lastNotice;     // the latest '*** ...' line: why the run ended
    private TouchWatcher touches;
    private volatile long panelTouchAt = -10_000; // uptime of the last finger down on the panel

    @Override
    public void onCreate() {
        super.onCreate();
        startInForeground();
        bot = Python.getInstance().getModule("app_main");
        wm = getSystemService(WindowManager.class);
        prefs = getSharedPreferences("overlay", MODE_PRIVATE);
        if (prefs.getInt("layout", 1) < LAYOUT) { // a spot saved for the old, wider pill could cover the score
            prefs.edit().remove("x").remove("y").putInt("layout", LAYOUT).apply();
        }
        size = prefs.getString("size", defaultSize());
        buildView();
        checkScreen();
        touches = new TouchWatcher(this);
        touches.start(); // with the panel, not each run: on the tablet each new su shows Magisk's toast
    }

    @Override
    public void onConfigurationChanged(Configuration config) {
        super.onConfigurationChanged(config);
        main.post(() -> { // the screen size changed (⤢, rotation): resize the pill
            rebuildView();
            checkScreen();
        });
    }

    @Override
    public void onDestroy() {
        if (running) {
            bot.callAttr("stop");
        }
        touches.stop();
        if (screen.equals("on")) { // Hide the panel ends the switched session; the game closes so it reopens right
            new Thread(() -> {
                try {
                    bot.callAttr("screen_off", false);
                } catch (Exception ignored) {
                    // no shell: Reset screen size in the app does it later
                }
            }, "sgm-screen-off").start();
        }
        if (root != null) {
            wm.removeView(root);
        }
        super.onDestroy();
    }

    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }

    // --- bot callbacks (Python thread) ---------------------------------------------------------------------

    @Override
    public void onLine(String line) {
        main.post(() -> {
            int notice = line.indexOf("*** ");
            if (notice >= 0) {
                lastNotice = line.substring(notice + 4);
            }
            lines.addLast(line);
            while (lines.size() > MAX_LINES) {
                lines.removeFirst();
            }
            log.setText(TextUtils.join("\n", lines));
            String shown = line.length() > 9 ? line.substring(9).trim() : line; // drop the timestamp
            status.setText(shown);
        });
    }

    @Override
    public void onFinished() {
        main.post(() -> {
            running = false;
            paused = false;
            if (!stopRequested) {
                notifyRunEnded();
            }
            refresh();
            checkScreen();
        });
    }

    // --- the user touching the game (TouchWatcher, its thread) ------------------------------------------------

    @Override
    public void onTouch(long at) {
        // decided a moment later: the panel's own view sees a touch on it after getevent does
        main.postDelayed(() -> {
            if (!running || paused || Math.abs(at - panelTouchAt) < 500) {
                return;
            }
            bot.callAttr("pause");
            paused = true;
            refresh();
            status.setText(PAUSE + " paused: you touched the screen. " + PLAY + " to continue");
        }, 300);
    }

    @Override
    public void onUnavailable(String why) {
        main.post(() -> {
            lines.addLast(why);
            while (lines.size() > MAX_LINES) {
                lines.removeFirst();
            }
            log.setText(TextUtils.join("\n", lines));
        });
    }

    // --- controls --------------------------------------------------------------------------------------------

    private void onPlayPause() {
        if (needsResize()) { // look again first: the last check may predate the game's restart
            checkScreen(() -> {
                if (needsResize()) {
                    flashResize();
                } else {
                    onPlayPause();
                }
            });
            return;
        }
        if (!running) {
            lines.clear();
            stopRequested = false;
            lastNotice = null;
            running = bot.callAttr("start", mode, size, this).toBoolean();
            touches.start(); // no-op if watching already (retries if Shizuku wasn't up when the panel opened)
            paused = false;
        } else if (paused) {
            bot.callAttr("resume");
            paused = false;
            pausedByPanel = false;
            status.setText(PLAY + " resumed: looking at the screen again");
        } else {
            bot.callAttr("pause");
            paused = true;
            // at once, not when the bot gets there: no touch happens from now on, even mid-calculation
            status.setText(PAUSE + " paused: no taps until " + PLAY);
        }
        refresh();
    }

    private void onStop() {
        if (needsResize()) {
            flashResize();
            return;
        }
        if (running) {
            stopRequested = true;
            bot.callAttr("stop");
            status.setText("stopping after the current step…"); // a map read can take a while on a phone
        }
    }

    private void toggleDetails() {
        boolean open = details.getVisibility() != View.VISIBLE;
        details.setVisibility(open ? View.VISIBLE : View.GONE);
        wm.updateViewLayout(root, params); // measure the window again: open, it's wider than the pill
        if (open && running && !paused) { // never let the bot act while the panel covers the game
            bot.callAttr("pause");
            paused = true;
            pausedByPanel = true;
        } else if (!open && pausedByPanel) {
            bot.callAttr("resume");
            paused = false;
            pausedByPanel = false;
        }
        refresh();
    }

    private void refresh() {
        playPause.setText(running && !paused ? PAUSE : PLAY);
        boolean blocked = needsResize();
        playPause.setAlpha(blocked ? 0.3f : 1f); // shown disabled, but still tappable: a tap points at ⤢
        stopButton.setAlpha(blocked ? 0.3f : 1f);
        resize.setVisibility(screen.equals("native") ? View.GONE : View.VISIBLE);
        resize.setTextColor(screen.equals("on") ? GREEN : Color.WHITE);
        if (!running && !switching) {
            status.setText(blocked ? "tap " + RESIZE + " first: switches the screen to " + sizeLabel()
                    : lines.isEmpty() ? "SGM bot — tap ▶ to start (" + mode + ")" : status.getText());
        }
    }

    // --- screen size (Full / Fast) and its switch (⤢) ---------------------------------------------------------

    /** Full on a 2560x1600 panel (the tablet), Fast elsewhere: the same rule as Device._target in Python. */
    private String defaultSize() {
        Display.Mode m = getSystemService(DisplayManager.class).getDisplay(Display.DEFAULT_DISPLAY).getMode();
        // (the panel's own size, which `wm size` doesn't change)
        int w = Math.max(m.getPhysicalWidth(), m.getPhysicalHeight());
        int h = Math.min(m.getPhysicalWidth(), m.getPhysicalHeight());
        return w == 2560 && h == 1600 ? "full" : "fast";
    }

    private String sizeLabel() {
        return size.equals("full") ? "Full (2560x1600)" : "Fast (1920x1200)";
    }

    private boolean needsResize() {
        return screen.equals("off") && !running;
    }

    private void checkScreen() {
        checkScreen(null);
    }

    /** Ask the device where the screen stands (a shell call, so off the main thread); then, if given, run after on
     * the main thread with the answer in place. */
    private void checkScreen(Runnable after) {
        new Thread(() -> {
            String state;
            try {
                state = bot.callAttr("screen_state", size).toString();
            } catch (Exception e) { // no shell yet (Shizuku stopped): ▶ will say so
                state = "native";
            }
            String result = state;
            main.post(() -> {
                boolean changed = !result.equals(screen);
                screen = result;
                if (changed) {
                    rebuildView(); // ⤢ appears or goes, and the status text gets its width
                }
                refresh();
                if (after != null) {
                    after.run();
                }
            });
        }, "sgm-screen").start();
    }

    private void onResize() {
        if (running) {
            status.setText("stop the bot first (" + STOP + "), then " + RESIZE);
            return;
        }
        if (switching) {
            return;
        }
        boolean on = !screen.equals("on");
        switching = true;
        status.setText(on ? "switching to " + sizeLabel() + ", restarting the game…" : "switching back, restarting the game…");
        new Thread(() -> {
            String msg;
            try {
                if (on) {
                    bot.callAttr("screen_on", size);
                } else {
                    bot.callAttr("screen_off", true);
                }
                msg = on ? sizeLabel() + ": open your event or prize fights, then ▶" : "screen back to normal";
            } catch (Exception e) {
                msg = "couldn't switch: " + e.getMessage();
            }
            String shown = msg;
            main.post(() -> {
                switching = false;
                checkScreen();
                status.setText(shown);
                // the game is still starting: the check above can see its old surface, so look again later
                main.postDelayed(this::checkScreen, 8000);
                main.postDelayed(this::checkScreen, 20000);
            });
        }, "sgm-resize").start();
    }

    /** ▶ or ■ tapped before ⤢: make ⤢ blink so it's obvious what to tap. */
    private void flashResize() {
        status.setText("tap " + RESIZE + " first: switches the screen to " + sizeLabel() + " (restarts the game)");
        for (int i = 0; i < 6; i++) {
            boolean lit = i % 2 == 0;
            main.postDelayed(() -> resize.setBackgroundColor(lit ? AMBER : Color.TRANSPARENT), i * 180L);
        }
    }

    // --- view ----------------------------------------------------------------------------------------------

    /** Layout units (dp on the reference tablet) to screen px, so the pill covers the same part of the game. */
    private int px(float v) {
        return Math.round(v * unit);
    }

    private void textSize(TextView t, float units) {
        t.setTextSize(TypedValue.COMPLEX_UNIT_PX, units * unit);
    }

    private void measureScreen() {
        Rect screen = wm.getMaximumWindowMetrics().getBounds();
        scale = Math.max(screen.width(), screen.height()) / REF_WIDTH;
        unit = REF_PX_PER_UNIT * scale;
    }

    private Button button(String label, View.OnClickListener click) {
        Button b = new Button(this);
        b.setText(label);
        b.setTextColor(Color.WHITE);
        textSize(b, 20);
        b.setBackgroundColor(Color.TRANSPARENT);
        b.setMinWidth(0);
        b.setMinimumWidth(0);
        b.setMinHeight(0);
        b.setMinimumHeight(0);
        b.setPadding(0, 0, 0, 0);
        b.setGravity(Gravity.CENTER);
        b.setOnClickListener(click);
        return b;
    }

    /** Full / Fast. A change applies to the next ▶; if the screen is switched to the other size, ▶ ■ grey out
     * until ⤢ switches it (checkScreen sees the mismatch). */
    private RadioGroup sizeChoice() {
        RadioGroup group = new RadioGroup(this);
        group.setOrientation(RadioGroup.HORIZONTAL);
        String[][] options = {{"full", "Full"}, {"fast", "Fast"}};
        for (String[] o : options) {
            RadioButton rb = new RadioButton(this);
            rb.setText(o[1]);
            rb.setTextColor(Color.WHITE);
            textSize(rb, 14);
            rb.setTag(o[0]);
            rb.setId(View.generateViewId());
            group.addView(rb);
            if (o[0].equals(size)) group.check(rb.getId());
        }
        group.setOnCheckedChangeListener((g, id) -> {
            size = (String) g.findViewById(id).getTag();
            prefs.edit().putString("size", size).apply();
            if (running) {
                lines.addLast("(size takes effect on the next ▶ — press ■, then " + RESIZE + " and ▶)");
            }
            checkScreen();
        });
        return group;
    }

    private void buildView() {
        measureScreen();
        root = new LinearLayout(this) {
            @Override
            public boolean dispatchTouchEvent(MotionEvent e) {
                if (e.getActionMasked() == MotionEvent.ACTION_DOWN) {
                    panelTouchAt = e.getEventTime(); // uptime, like TouchWatcher's: this touch isn't the game's
                }
                return super.dispatchTouchEvent(e);
            }
        };
        root.setOrientation(LinearLayout.VERTICAL);
        GradientDrawable bg = new GradientDrawable();
        bg.setColor(Color.argb(170, 12, 12, 20)); // translucent: the game stays visible underneath
        bg.setCornerRadius(px(14));
        root.setBackground(bg);
        root.setPadding(px(8), px(2), px(4), px(2));

        // row 1: the buttons, big enough to hit; row 2: the current step (drag the panel by it)
        LinearLayout bar = new LinearLayout(this);
        bar.setOrientation(LinearLayout.HORIZONTAL);
        bar.setGravity(Gravity.CENTER_VERTICAL);
        resize = button(RESIZE, v -> onResize());
        playPause = button(PLAY, v -> onPlayPause());
        stopButton = button(STOP, v -> onStop());
        for (Button b : new Button[]{resize, playPause, stopButton, button("☰", v -> toggleDetails())}) {
            bar.addView(b, new LinearLayout.LayoutParams(px(BUTTON_W), px(BUTTON_H)));
        }
        root.addView(bar);
        status = new TextView(this);
        status.setTextColor(Color.WHITE);
        textSize(status, 11);
        status.setSingleLine(true);
        status.setEllipsize(TextUtils.TruncateAt.END);
        status.setPadding(px(4), 0, px(4), px(4));
        root.addView(status, new LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, -2));

        details = new LinearLayout(this);
        details.setOrientation(LinearLayout.VERTICAL);
        details.setVisibility(View.GONE);
        details.setMinimumWidth(px(330)); // its own width, not the pill's: the radio labels stay on one line
        RadioGroup modes = new RadioGroup(this);
        modes.setOrientation(RadioGroup.HORIZONTAL);
        String[][] options = {{"auto", "Auto"}, {"event", "Event"}, {"prize", "Prize"}};
        for (String[] o : options) {
            RadioButton rb = new RadioButton(this);
            rb.setText(o[1]);
            rb.setTextColor(Color.WHITE);
            textSize(rb, 14);
            rb.setTag(o[0]);
            rb.setId(View.generateViewId());  // without ids the group can't uncheck the default
            modes.addView(rb);
            if (o[0].equals(mode)) modes.check(rb.getId());
        }
        modes.setOnCheckedChangeListener((g, id) -> {
            mode = (String) g.findViewById(id).getTag();
            if (running) {
                lines.addLast("(mode takes effect on the next ▶ — press ■ then ▶)");
            }
            refresh();
        });
        details.addView(modes);
        details.addView(sizeChoice());
        log = new TextView(this);
        log.setTextColor(Color.argb(230, 220, 230, 255));
        textSize(log, 10);
        log.setTypeface(Typeface.MONOSPACE);
        log.setWidth(px(420));
        log.setMaxLines(MAX_LINES);
        details.addView(log);
        root.addView(details);

        params = new WindowManager.LayoutParams(
                WindowManager.LayoutParams.WRAP_CONTENT, WindowManager.LayoutParams.WRAP_CONTENT,
                WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY,
                WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE | WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN,
                PixelFormat.TRANSLUCENT);
        params.gravity = Gravity.TOP | Gravity.START;
        params.x = Math.round(prefs.getInt("x", HOME_X) * scale); // dragged there, or over home/avatar/name
        params.y = Math.round(prefs.getInt("y", HOME_Y) * scale);
        status.setOnTouchListener(new Dragger());
        wm.addView(root, params);
        log.setText(TextUtils.join("\n", lines));
        refresh();
    }

    private void rebuildView() {
        CharSequence shown = status.getText();
        boolean open = details.getVisibility() == View.VISIBLE;
        wm.removeView(root);
        buildView();
        status.setText(shown);
        details.setVisibility(open ? View.VISIBLE : View.GONE);
    }

    /** Drag the pill by its status text. */
    private class Dragger implements View.OnTouchListener {
        private float startX, startY;
        private int originX, originY;

        @Override
        public boolean onTouch(View v, MotionEvent e) {
            switch (e.getActionMasked()) {
                case MotionEvent.ACTION_DOWN:
                    startX = e.getRawX();
                    startY = e.getRawY();
                    originX = params.x;
                    originY = params.y;
                    return true;
                case MotionEvent.ACTION_MOVE:
                    params.x = originX + (int) (e.getRawX() - startX);
                    params.y = originY + (int) (e.getRawY() - startY);
                    wm.updateViewLayout(root, params);
                    return true;
                case MotionEvent.ACTION_UP:
                    boolean still = Math.abs(e.getRawX() - startX) < 10 && Math.abs(e.getRawY() - startY) < 10;
                    if (still && e.getEventTime() - e.getDownTime() > 600) { // long press: back to its home spot
                        params.x = Math.round(HOME_X * scale);
                        params.y = Math.round(HOME_Y * scale);
                        wm.updateViewLayout(root, params);
                        prefs.edit().remove("x").remove("y").apply();
                    } else if (still) {
                        toggleDetails(); // a tap (not a drag) on the text opens the panel too
                    } else { // remember the spot, in game-frame px so it holds at any screen size
                        prefs.edit().putInt("x", Math.round(params.x / scale)).putInt("y", Math.round(params.y / scale)).apply();
                    }
                    return true;
            }
            return false;
        }
    }

    /** The run ended by itself (done, a stop rule, an error): chime and say why. */
    private void notifyRunEnded() {
        Notification n = new Notification.Builder(this, CHANNEL_END)
                .setContentTitle("SGM bot stopped")
                .setContentText(lastNotice != null ? lastNotice : "the run ended")
                .setStyle(new Notification.BigTextStyle().bigText(lastNotice != null ? lastNotice : "the run ended"))
                .setSmallIcon(android.R.drawable.ic_media_pause)
                .setAutoCancel(true)
                .build();
        getSystemService(NotificationManager.class).notify(2, n);
    }

    private void startInForeground() {
        NotificationManager nm = getSystemService(NotificationManager.class);
        nm.createNotificationChannel(new NotificationChannel(CHANNEL, "Overlay", NotificationManager.IMPORTANCE_LOW));
        // a channel's sound is fixed once created: change the id to change the sound
        for (String old : new String[]{"run_end", "run_end_antares"}) { // earlier sounds
            nm.deleteNotificationChannel(old);
        }
        NotificationChannel end = new NotificationChannel(CHANNEL_END, "Run ended", NotificationManager.IMPORTANCE_HIGH);
        end.setDescription("A run stopped by itself: finished, a stop rule or an error");
        end.setSound(Uri.parse("android.resource://" + getPackageName() + "/" + R.raw.run_end),
                new AudioAttributes.Builder().setUsage(AudioAttributes.USAGE_NOTIFICATION)
                        .setContentType(AudioAttributes.CONTENT_TYPE_SONIFICATION).build());
        nm.createNotificationChannel(end);
        Notification n = new Notification.Builder(this, CHANNEL)
                .setContentTitle("SGM bot overlay")
                .setContentText("Control panel is showing")
                .setSmallIcon(android.R.drawable.ic_media_play)
                .build();
        startForeground(1, n, ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE);
    }
}
