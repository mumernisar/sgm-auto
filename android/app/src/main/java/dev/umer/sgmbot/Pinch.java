package dev.umer.sgmbot;

import android.os.SystemClock;
import android.view.InputDevice;
import android.view.InputEvent;
import android.view.MotionEvent;

import java.lang.reflect.Method;

/**
 * Two-finger pinch injected as the shell user (or root), from a shell, not the app:
 *   CLASSPATH=$(pm path dev.umer.sgmbot | cut -d: -f2) app_process / dev.umer.sgmbot.Pinch cx cy startGap endGap [steps] [stepMs]
 * Coordinates are screen pixels (landscape, as the game sees them, including a `wm size` override). Raw
 * `sendevent` would need root even for the shell user: SELinux blocks /dev/input on stock devices.
 * Uses only the Android framework, so app_process can load it from the APK without the app running.
 */
public class Pinch {
    private static Object im;
    private static Method inject;

    public static void main(String[] a) throws Exception {
        float cx = Float.parseFloat(a[0]), cy = Float.parseFloat(a[1]);
        float g0 = Float.parseFloat(a[2]), g1 = Float.parseFloat(a[3]);
        int steps = a.length > 4 ? Integer.parseInt(a[4]) : 14;
        long stepMs = a.length > 5 ? Long.parseLong(a[5]) : 20;
        init();

        long down = SystemClock.uptimeMillis();
        send(down, MotionEvent.ACTION_DOWN, 1, cx, cy, g0);
        send(down, MotionEvent.ACTION_POINTER_DOWN | (1 << MotionEvent.ACTION_POINTER_INDEX_SHIFT), 2, cx, cy, g0);
        for (int k = 1; k <= steps; k++) {
            Thread.sleep(stepMs);
            send(down, MotionEvent.ACTION_MOVE, 2, cx, cy, g0 + (g1 - g0) * k / steps);
        }
        Thread.sleep(stepMs);
        send(down, MotionEvent.ACTION_POINTER_UP | (1 << MotionEvent.ACTION_POINTER_INDEX_SHIFT), 2, cx, cy, g1);
        send(down, MotionEvent.ACTION_UP, 1, cx, cy, g1);
    }

    private static void init() throws Exception {
        Class<?> c;
        try {
            c = Class.forName("android.hardware.input.InputManagerGlobal");  // Android 14+
        } catch (ClassNotFoundException e) {
            c = Class.forName("android.hardware.input.InputManager");
        }
        im = c.getDeclaredMethod("getInstance").invoke(null);
        inject = c.getMethod("injectInputEvent", InputEvent.class, int.class);
    }

    /** Fingers on a horizontal line through (cx, cy), gap apart; pointer 0 left, pointer 1 right. */
    private static void send(long down, int action, int count, float cx, float cy, float gap) throws Exception {
        MotionEvent.PointerProperties[] props = new MotionEvent.PointerProperties[count];
        MotionEvent.PointerCoords[] coords = new MotionEvent.PointerCoords[count];
        for (int i = 0; i < count; i++) {
            props[i] = new MotionEvent.PointerProperties();
            props[i].id = i;
            props[i].toolType = MotionEvent.TOOL_TYPE_FINGER;
            coords[i] = new MotionEvent.PointerCoords();
            coords[i].x = cx + (i == 0 ? -gap / 2 : gap / 2);
            coords[i].y = cy;
            coords[i].pressure = 1;
            coords[i].size = 1;
        }
        MotionEvent ev = MotionEvent.obtain(down, SystemClock.uptimeMillis(), action, count, props, coords,
                0, 0, 1, 1, 0, 0, InputDevice.SOURCE_TOUCHSCREEN, 0);
        inject.invoke(im, ev, 0);  // INJECT_INPUT_EVENT_MODE_ASYNC
        ev.recycle();
    }
}
