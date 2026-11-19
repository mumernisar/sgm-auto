package dev.umer.sgmbot;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.Service;
import android.content.Intent;
import android.content.pm.ServiceInfo;
import android.graphics.Color;
import android.graphics.PixelFormat;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.os.Handler;
import android.os.IBinder;
import android.os.Looper;
import android.text.TextUtils;
import android.util.TypedValue;
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
 * the game's home/chat buttons, which the bot never needs. Expanding it shows recent steps and the mode, and
 * pauses the bot so it never taps through or screenshots the open panel.
 */
public class OverlayService extends Service implements BotListener {
    private static final String CHANNEL = "overlay";
    private static final int MAX_LINES = 10;

    private final Handler main = new Handler(Looper.getMainLooper());
    private final ArrayDeque<String> lines = new ArrayDeque<>();
    private WindowManager wm;
    private WindowManager.LayoutParams params;
    private LinearLayout root;
    private TextView status;
    private TextView log;
    private Button playPause;
    private LinearLayout details;
    private PyObject bot;
    private String mode = "auto";
    private boolean running;
    private boolean paused;
    private boolean pausedByPanel;

    @Override
    public void onCreate() {
        super.onCreate();
        startInForeground();
        bot = Python.getInstance().getModule("app_main");
        wm = getSystemService(WindowManager.class);
        buildView();
    }

    @Override
    public void onDestroy() {
        if (running) {
            bot.callAttr("stop");
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
            refresh();
        });
    }

    // --- controls --------------------------------------------------------------------------------------------

    private void onPlayPause() {
        if (!running) {
            lines.clear();
            running = bot.callAttr("start", mode, this).toBoolean();
            paused = false;
        } else if (paused) {
            bot.callAttr("resume");
            paused = false;
        } else {
            bot.callAttr("pause");
            paused = true;
        }
        refresh();
    }

    private void onStop() {
        if (running) {
            bot.callAttr("stop");
            status.setText("stopping…");
        }
    }

    private void toggleDetails() {
        boolean open = details.getVisibility() != View.VISIBLE;
        details.setVisibility(open ? View.VISIBLE : View.GONE);
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
        playPause.setText(running && !paused ? "⏸" : "▶");
        if (!running) {
            status.setText(lines.isEmpty() ? "SGM bot — tap ▶ to start (" + mode + ")" : status.getText());
        }
    }

    // --- view ----------------------------------------------------------------------------------------------

    private int dp(float v) {
        return (int) TypedValue.applyDimension(TypedValue.COMPLEX_UNIT_DIP, v, getResources().getDisplayMetrics());
    }

    private Button button(String label, View.OnClickListener click) {
        Button b = new Button(this);
        b.setText(label);
        b.setTextColor(Color.WHITE);
        b.setTextSize(16);
        b.setBackgroundColor(Color.TRANSPARENT);
        b.setMinWidth(0);
        b.setMinimumWidth(0);
        b.setPadding(dp(8), 0, dp(8), 0);
        b.setOnClickListener(click);
        return b;
    }

    private void buildView() {
        root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        GradientDrawable bg = new GradientDrawable();
        bg.setColor(Color.argb(170, 12, 12, 20)); // translucent: the game stays visible underneath
        bg.setCornerRadius(dp(14));
        root.setBackground(bg);
        root.setPadding(dp(8), dp(2), dp(4), dp(2));

        LinearLayout bar = new LinearLayout(this);
        bar.setOrientation(LinearLayout.HORIZONTAL);
        bar.setGravity(Gravity.CENTER_VERTICAL);
        status = new TextView(this);
        status.setTextColor(Color.WHITE);
        status.setTextSize(12);
        status.setSingleLine(true);
        status.setEllipsize(TextUtils.TruncateAt.END);
        status.setWidth(dp(190));
        bar.addView(status);
        playPause = button("▶", v -> onPlayPause());
        bar.addView(playPause);
        bar.addView(button("■", v -> onStop()));
        bar.addView(button("☰", v -> toggleDetails()));
        root.addView(bar, new LinearLayout.LayoutParams(-2, dp(40)));

        details = new LinearLayout(this);
        details.setOrientation(LinearLayout.VERTICAL);
        details.setVisibility(View.GONE);
        RadioGroup modes = new RadioGroup(this);
        modes.setOrientation(RadioGroup.HORIZONTAL);
        String[][] options = {{"auto", "Auto"}, {"event", "Event"}, {"prize", "Prize"}};
        for (String[] o : options) {
            RadioButton rb = new RadioButton(this);
            rb.setText(o[1]);
            rb.setTextColor(Color.WHITE);
            rb.setTag(o[0]);
            rb.setChecked(o[0].equals(mode));
            modes.addView(rb);
        }
        modes.setOnCheckedChangeListener((g, id) -> {
            mode = (String) g.findViewById(id).getTag();
            if (running) {
                lines.addLast("(mode takes effect on the next ▶ — press ■ then ▶)");
            }
            refresh();
        });
        details.addView(modes);
        log = new TextView(this);
        log.setTextColor(Color.argb(230, 220, 230, 255));
        log.setTextSize(10);
        log.setTypeface(Typeface.MONOSPACE);
        log.setWidth(dp(420));
        log.setMaxLines(MAX_LINES);
        details.addView(log);
        root.addView(details);

        params = new WindowManager.LayoutParams(
                WindowManager.LayoutParams.WRAP_CONTENT, WindowManager.LayoutParams.WRAP_CONTENT,
                WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY,
                WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE | WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN,
                PixelFormat.TRANSLUCENT);
        params.gravity = Gravity.TOP | Gravity.START;
        params.x = 150; // right of the game's back arrow, over home/chat (px, landscape)
        params.y = 0;
        status.setOnTouchListener(new Dragger());
        wm.addView(root, params);
        refresh();
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
                    if (Math.abs(e.getRawX() - startX) < 10 && Math.abs(e.getRawY() - startY) < 10) {
                        toggleDetails(); // a tap (not a drag) on the text opens the panel too
                    }
                    return true;
            }
            return false;
        }
    }

    private void startInForeground() {
        NotificationManager nm = getSystemService(NotificationManager.class);
        nm.createNotificationChannel(new NotificationChannel(CHANNEL, "Overlay", NotificationManager.IMPORTANCE_LOW));
        Notification n = new Notification.Builder(this, CHANNEL)
                .setContentTitle("SGM bot overlay")
                .setContentText("Control panel is showing")
                .setSmallIcon(android.R.drawable.ic_media_play)
                .build();
        startForeground(1, n, ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE);
    }
}
