package dev.umer.sgmbot;

import android.app.Activity;
import android.content.Intent;
import android.graphics.Color;
import android.net.Uri;
import android.os.Bundle;
import android.provider.Settings;
import android.view.Gravity;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.TextView;

/** Launcher: grant the overlay permission once, then show or hide the floating control. */
public class MainActivity extends Activity {
    private TextView info;

    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        LinearLayout box = new LinearLayout(this);
        box.setOrientation(LinearLayout.VERTICAL);
        box.setGravity(Gravity.CENTER);
        box.setBackgroundColor(Color.rgb(16, 16, 26));
        box.setPadding(64, 64, 64, 64);

        TextView title = new TextView(this);
        title.setText("SGM Bot");
        title.setTextColor(Color.WHITE);
        title.setTextSize(28);
        box.addView(title);

        info = new TextView(this);
        info.setTextColor(Color.LTGRAY);
        info.setTextSize(15);
        info.setPadding(0, 24, 0, 24);
        box.addView(info);

        Button show = new Button(this);
        show.setText("Show overlay, then open the game");
        show.setOnClickListener(v -> {
            if (!Settings.canDrawOverlays(this)) {
                startActivity(new Intent(Settings.ACTION_MANAGE_OVERLAY_PERMISSION, Uri.parse("package:" + getPackageName())));
                return;
            }
            startForegroundService(new Intent(this, OverlayService.class));
            moveTaskToBack(true);
        });
        box.addView(show);

        Button hide = new Button(this);
        hide.setText("Hide overlay (stops the bot)");
        hide.setOnClickListener(v -> stopService(new Intent(this, OverlayService.class)));
        box.addView(hide);

        setContentView(box);
        if (checkSelfPermission("android.permission.POST_NOTIFICATIONS") != 0) {
            requestPermissions(new String[]{"android.permission.POST_NOTIFICATIONS"}, 1);
        }
    }

    @Override
    protected void onResume() {
        super.onResume();
        info.setText(Settings.canDrawOverlays(this)
                ? "Ready. Tap below, switch to Skullgirls, and use ▶ on the floating panel.\n"
                + "The first ▶ asks Magisk for root once — allow it (and tick 'remember')."
                : "Step 1: allow \"Display over other apps\" for SGM Bot (tap the button below).");
    }
}
