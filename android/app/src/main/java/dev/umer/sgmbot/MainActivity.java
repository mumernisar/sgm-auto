package dev.umer.sgmbot;

import android.app.Activity;
import android.content.ActivityNotFoundException;
import android.content.Intent;
import android.graphics.Color;
import android.graphics.Typeface;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.PowerManager;
import android.provider.Settings;
import android.view.Gravity;
import android.view.View;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Toast;

import com.chaquo.python.Python;

import java.util.Locale;

import rikka.shizuku.Shizuku;

/**
 * Launcher: a setup checklist (each step shows ✓ when done and has a button that goes straight to the right
 * place), then show or hide the floating control. Without root the bot gets adb's rights through Shizuku.
 */
public class MainActivity extends Activity {
    private static final String GAME = "com.autumn.skullgirls";
    private static final int GREEN = Color.rgb(110, 220, 130), AMBER = Color.rgb(255, 190, 90);

    private LinearLayout steps;
    private Button show;
    private TextView guide;

    private final Shizuku.OnBinderReceivedListener binderReceived = () -> runOnUiThread(this::refresh);
    private final Shizuku.OnBinderDeadListener binderDead = () -> runOnUiThread(this::refresh);
    private final Shizuku.OnRequestPermissionResultListener permissionResult = (code, result) -> runOnUiThread(this::refresh);

    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        LinearLayout box = new LinearLayout(this);
        box.setOrientation(LinearLayout.VERTICAL);
        box.setPadding(64, 48, 64, 64);

        TextView title = text("SGM Bot  " + BuildConfig.VERSION_NAME, 26, Color.WHITE);
        box.addView(title);
        box.addView(text("Setup: do the steps that aren't ✓ yet, top to bottom.", 15, Color.LTGRAY));

        steps = new LinearLayout(this);
        steps.setOrientation(LinearLayout.VERTICAL);
        steps.setPadding(0, 16, 0, 16);
        box.addView(steps);

        show = new Button(this);
        show.setText("Show the panel and open Skullgirls");
        show.setOnClickListener(v -> showPanel());
        box.addView(show);

        Button hide = new Button(this);
        hide.setText("Hide the panel (stops the bot)");
        hide.setOnClickListener(v -> stopService(new Intent(this, OverlayService.class)));
        box.addView(hide);

        Button reset = new Button(this);
        reset.setText("Reset screen size (closes the game)");
        reset.setOnClickListener(v -> resetScreen());
        box.addView(reset);

        guide = text("", 14, Color.LTGRAY);
        guide.setPadding(0, 32, 0, 0);
        box.addView(guide);

        ScrollView scroll = new ScrollView(this);
        scroll.setBackgroundColor(Color.rgb(16, 16, 26));
        scroll.addView(box);
        setContentView(scroll);

        Shizuku.addBinderReceivedListenerSticky(binderReceived);
        Shizuku.addBinderDeadListener(binderDead);
        Shizuku.addRequestPermissionResultListener(permissionResult);
    }

    @Override
    protected void onDestroy() {
        Shizuku.removeBinderReceivedListener(binderReceived);
        Shizuku.removeBinderDeadListener(binderDead);
        Shizuku.removeRequestPermissionResultListener(permissionResult);
        super.onDestroy();
    }

    @Override
    protected void onResume() {
        super.onResume();
        refresh();
    }

    // --- the checklist ----------------------------------------------------------------------------------------

    private void refresh() {
        steps.removeAllViews();
        int n = 1;
        boolean overlay = Settings.canDrawOverlays(this);
        step(n++, "Allow \"Display over other apps\"", "The bot's control panel floats over the game.",
                overlay, "Allow", () -> startActivity(new Intent(Settings.ACTION_MANAGE_OVERLAY_PERMISSION,
                        Uri.parse("package:" + getPackageName()))));

        RootShell.Access access = RootShell.access(getPackageManager());
        if (access == RootShell.Access.ROOT) {
            step(n++, "Root found", "The first time you press ▶ in the game, Magisk asks once: tap Grant.",
                    true, null, null);
        } else {
            step(n++, "Install Shizuku", "A free app that gives SGM Bot the rights it needs without root.",
                    access != RootShell.Access.NO_SHIZUKU, "Get Shizuku", this::getShizuku);
            step(n++, "Start Shizuku", "Open Shizuku and tap Start. The first time, pair it first: see "
                            + "\"First-time Shizuku setup\" below. After every restart of the device, tap Start again.",
                    access == RootShell.Access.SHIZUKU_NOT_ALLOWED || access == RootShell.Access.SHIZUKU_READY,
                    "Open Shizuku", this::openShizuku);
            step(n++, "Allow SGM Bot in Shizuku", "Tap Allow, then \"Allow all the time\".",
                    access == RootShell.Access.SHIZUKU_READY, "Allow", () -> {
                        if (Shizuku.pingBinder()) {
                            Shizuku.requestPermission(1);
                        } else {
                            Toast.makeText(this, "Start Shizuku first (step above)", Toast.LENGTH_LONG).show();
                        }
                    });
        }

        boolean notifications = checkSelfPermission("android.permission.POST_NOTIFICATIONS") == 0;
        step(n++, "Allow notifications (optional)", "A chime and a message when a run stops by itself.",
                notifications, "Allow",
                () -> requestPermissions(new String[]{"android.permission.POST_NOTIFICATIONS"}, 2));

        boolean battery = getSystemService(PowerManager.class).isIgnoringBatteryOptimizations(getPackageName());
        step(n, "Let it run in the background (optional)", "So Android doesn't stop a long run."
                        + (access == RootShell.Access.ROOT ? "" : " Set Shizuku's battery use to Unrestricted too."),
                battery, "Allow", () -> startActivity(new Intent(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS,
                        Uri.parse("package:" + getPackageName()))));

        boolean ready = overlay && (access == RootShell.Access.ROOT || access == RootShell.Access.SHIZUKU_READY);
        show.setEnabled(ready);
        show.setText(ready ? "Show the panel and open Skullgirls" : "Show the panel (finish the steps above first)");
        String notes = brandNotes();
        guide.setText((notes != null ? notes + "\n\n" : "") + USE
                + (access == RootShell.Access.ROOT ? "" : "\n\n" + SHIZUKU_GUIDE));
    }

    /** The differences that matter on this device's brand (Build.MANUFACTURER), or null for stock Android. */
    private static String brandNotes() {
        String brand = (Build.MANUFACTURER + " " + Build.BRAND).toLowerCase(Locale.ROOT);
        String head = "NOTES FOR YOUR " + Build.MANUFACTURER.toUpperCase(Locale.ROOT) + "\n";
        if (brand.contains("samsung")) {
            return head
                    + "• Installing SGM Bot blocked (\"Unknown app blocked\")? Settings → Security and privacy → "
                    + "Auto Blocker → off. You can turn it back on after installing.\n"
                    + "• Build number: Settings → About phone → Software information.\n"
                    + "• Battery: Settings → Battery → Background usage limits → Never sleeping apps → add "
                    + "SGM Bot and Shizuku.\n"
                    + "• Game Booster: keep it off for Skullgirls (it can lower the game's resolution).";
        }
        if (brand.contains("xiaomi") || brand.contains("redmi") || brand.contains("poco")) {
            return head
                    + "• Developer options: Settings → About phone → tap \"OS version\" (HyperOS) or \"MIUI version\" "
                    + "7 times. They are under Settings → Additional settings → Developer options.\n"
                    + "• In Developer options also turn on \"USB debugging (Security settings)\" (it's separate "
                    + "from \"USB debugging\"; it may ask you to sign in to a Mi account). Without it taps don't work.\n"
                    + "• SGM Bot's app info → Other permissions → allow \"Display pop-up windows while running in "
                    + "the background\".\n"
                    + "• App info of SGM Bot and Shizuku: Autostart on, Battery saver → No restrictions.\n"
                    + "• The Security app's scan can turn Developer options off again: check it if Shizuku stops.";
        }
        if (brand.contains("oppo") || brand.contains("oneplus") || brand.contains("realme")) {
            return head
                    + "• Build number: Settings → About device → Version.\n"
                    + "• Developer options: turn OFF \"Disable permission monitoring\" / \"Permission monitoring\" "
                    + "(the name varies), or Shizuku's rights are limited and taps may not work.\n"
                    + "• Battery: app info of SGM Bot and Shizuku → Battery → Allow background activity.";
        }
        if (brand.contains("vivo") || brand.contains("iqoo")) {
            return head
                    + "• Build number: Settings → About phone → Software version.\n"
                    + "• Battery: Settings → Battery → Background power consumption → allow SGM Bot and Shizuku.";
        }
        if (brand.contains("huawei") || brand.contains("honor")) {
            return head
                    + "• No Play Store? Get Shizuku from github.com/RikkaApps/Shizuku/releases.\n"
                    + "• Battery: Settings → Battery → App launch → SGM Bot and Shizuku → Manage manually, all on.\n"
                    + "Not tested on this brand yet.";
        }
        if (brand.contains("lenovo")) {
            return head
                    + "• Build number: Settings → About tablet (or phone).\n"
                    + "• The game assistant may show \"Block notifications / Panoramic sound\" boxes when the game "
                    + "starts. They go away on their own.";
        }
        return null;
    }

    private void step(int n, String title, String detail, boolean done, String action, Runnable onClick) {
        LinearLayout row = new LinearLayout(this);
        row.setOrientation(LinearLayout.HORIZONTAL);
        row.setGravity(Gravity.CENTER_VERTICAL);
        row.setPadding(0, 12, 0, 12);

        TextView mark = text(done ? "✓" : String.valueOf(n), 22, done ? GREEN : AMBER);
        mark.setTypeface(Typeface.DEFAULT_BOLD);
        mark.setWidth(72);
        row.addView(mark);

        LinearLayout words = new LinearLayout(this);
        words.setOrientation(LinearLayout.VERTICAL);
        TextView t = text(title, 17, done ? Color.GRAY : Color.WHITE);
        words.addView(t);
        words.addView(text(detail, 13, Color.GRAY));
        row.addView(words, new LinearLayout.LayoutParams(0, -2, 1));

        if (!done && action != null) {
            Button b = new Button(this);
            b.setText(action);
            b.setOnClickListener(v -> onClick.run());
            row.addView(b);
        }
        steps.addView(row);
    }

    private TextView text(String s, float size, int color) {
        TextView t = new TextView(this);
        t.setText(s);
        t.setTextSize(size);
        t.setTextColor(color);
        return t;
    }

    // --- actions -----------------------------------------------------------------------------------------------

    private void showPanel() {
        startForegroundService(new Intent(this, OverlayService.class));
        Intent game = getPackageManager().getLaunchIntentForPackage(GAME);
        if (game != null) {
            startActivity(game);
        } else {
            moveTaskToBack(true);
        }
    }

    private void getShizuku() {
        try {
            startActivity(new Intent(Intent.ACTION_VIEW, Uri.parse("market://details?id=" + RootShell.SHIZUKU_PACKAGE)));
        } catch (ActivityNotFoundException e) { // no Play Store: the project's releases
            startActivity(new Intent(Intent.ACTION_VIEW, Uri.parse("https://github.com/RikkaApps/Shizuku/releases")));
        }
    }

    private void openShizuku() {
        Intent shizuku = getPackageManager().getLaunchIntentForPackage(RootShell.SHIZUKU_PACKAGE);
        if (shizuku != null) {
            startActivity(shizuku);
        }
    }

    private void resetScreen() {
        new Thread(() -> {
            String msg;
            try {
                Python.getInstance().getModule("app_main").callAttr("screen_off", false);
                msg = "Screen size is back to normal";
            } catch (Exception e) {
                msg = "Couldn't reset: " + e.getMessage();
            }
            String shown = msg;
            runOnUiThread(() -> Toast.makeText(this, shown, Toast.LENGTH_LONG).show());
        }, "sgm-reset").start();
    }

    private static final String USE =
            "USING IT\n"
            + "1. Tap \"Show the panel and open Skullgirls\".\n"
            + "2. A small dark panel sits at the top left of the game, over your name, clear of your score. Drag it "
            + "by its text if you want it elsewhere (it remembers the spot); hold its text to put it back.\n"
            + "3. On a phone or any screen that isn't 2560x1600: tap ⤢ on the panel first (▶ and ■ stay grey until "
            + "then). It switches the screen to the tablet's shape (black bars on the sides) at the size picked under "
            + "☰: Fast (1920x1200, the default on a phone: the bot works faster) or Full (2560x1600), and restarts "
            + "the game. Open your event or prize fights, then press ▶. ⤢ turns green and stays on for later runs; "
            + "tap it again to switch back (the game restarts). Hiding the panel switches back too.\n"
            + "4. ▶ starts, \u23F8\uFE0E pauses, ■ stops, ☰ shows the recent steps, the mode and the size. Touching the "
            + "game pauses the bot too. When the bot stops by itself, the reason is the last line on the panel.\n"
            + "The game must be in English.";

    private static final String SHIZUKU_GUIDE =
            "FIRST-TIME SHIZUKU SETUP (once, about 5 minutes, needs Wi-Fi)\n"
            + "Tip for any brand: the search box at the top of Settings finds \"Build number\" and "
            + "\"Wireless debugging\".\n"
            + "1. Turn on Developer options: Settings → About phone → tap \"Build number\" 7 times (where it is on "
            + "your brand: see the notes above). It says \"You are now a developer\".\n"
            + "2. Settings → Developer options → turn on \"Wireless debugging\" (accept the prompt). Do the "
            + "extra steps from the notes above too, if there are any.\n"
            + "3. Open Shizuku → under \"Start via Wireless debugging\" tap Pairing. Shizuku shows a notification.\n"
            + "4. Back in Developer options → Wireless debugging → \"Pair device with pairing code\". Type the 6-digit "
            + "code into Shizuku's notification (pull the notification down, tap \"Enter pairing code\").\n"
            + "5. In Shizuku tap Start. It says \"Shizuku is running\".\n"
            + "6. Come back here: the steps above turn ✓.\n"
            + "After a device restart: open Shizuku and tap Start again (no new pairing).";
}
