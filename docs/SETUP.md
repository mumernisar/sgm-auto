# Setting it up on your own device

The bot was built and tested on one tablet. It works as-is only on a device that matches the requirements
below. Anything else needs the porting steps further down.

## Requirements

| | Needed | Reference device |
|---|---|---|
| Screen | **2560x1600, played in landscape** (16:10). All templates and tap points are absolute pixels | Lenovo Tab (TB320FC) |
| Android | 11 or newer (app `minSdk` 30), **arm64** | Android 15 |
| Root | **Yes**, through Magisk (see *Without root* for the plan to drop it) | Magisk |
| Game | Skullgirls Mobile in **English** (screens are read by OCR and English templates) | |
| Mac (to build the app or develop) | Homebrew, `adb` (`brew install android-platform-tools`), JDK 17+, Android SDK command-line tools, Python 3.10 (`brew install python@3.10`), Tesseract (`brew install tesseract`) | macOS, Apple silicon |

Check your screen with `adb shell wm size` (it reports portrait, e.g. `1600x2560`).

## Install

1. **Root the device with Magisk.** How depends on the device (unlock the bootloader, patch the boot image).
2. **Build and install the app** from the Mac (see `README.md`):
   ```sh
   cd android && ./gradlew assembleDebug && adb install -r app/build/outputs/apk/debug/app-debug.apk
   ```
   `android/local.properties` must point at your SDK: `sdk.dir=/path/to/android-sdk`.
3. **Open SGM Bot**, allow *Display over other apps*, show the overlay, then open the game.
4. **First ▶:** Magisk asks for root. Allow it and choose *Forever*. The app keeps one root shell open, so
   Magisk asks only once and doesn't show a toast per command.
5. **In the game:** the bot recognises auto battle by the "3x" badge above the brain button (`shots/011`).
   If yours shows something else, the fight screen needs a new template.

## Optional: charging off (adb only)

Over a long run from the Mac, the USB cable keeps the tablet at 100%. The adb backend therefore turns charging off
every 5 minutes, and `./charge.sh off | on | status` does it by hand. The app never touches charging.

The path, `/sys/class/qcom-battery/batt_charge_en`, exists only on some Qualcomm devices. On anything else:
- turn it off with `{ "keep_charging_off": false }` in `config.json`, or
- find your device's switch (`adb shell su -c 'ls /sys/class/power_supply/battery/'`; common names are
  `charging_enabled`, `input_suspend`, `batt_charge_en`) and set `AdbDevice.CHARGE_NODE` in `bot/device.py`
  and `node` in `charge.sh`. **Only write to a node you've identified.** Some, like `ship_mode_en`, switch
  the battery off.

## Porting to another screen or device

Same resolution, different device: only the touch panel (step 4) and charging (above) change.

A different resolution or aspect ratio (most phones are 20:9) needs more. Unity anchors buttons to screen
edges and corners, so on a wider screen they move by different amounts. Scaling everything uniformly only
works on another 16:10 screen.

1. **Reference screenshots.** Put your in-game name in `shots/.player_name` so `snap.sh` blurs it. Then, for every
   screen in `tests/test_screens.py`, open it on your device and run `./snap.sh <label>`. The blur looks for the
   name at the reference device's positions, so on a new layout update `PLACES` in `tools/blur_name.py`. Use the same shot numbers, or update `EXPECTED` and `tools/crop_templates.py`.
2. **Templates.** Re-measure each crop box in `tools/crop_templates.py` `SPEC` for your shots, run
   `.venv/bin/python tools/crop_templates.py`, and check `templates/_sheet.png`.
3. **Coordinates.** Fixed tap points and search regions are absolute pixels in `bot/modes.py`, `bot/screens.py`,
   `bot/team.py`, `bot/readers.py`, `bot/eventmap.py` and `bot/vision.py` (about 50 places). Pixel-size limits in
   the vision code need scaling too: icon ring radius 40–48 px, glyph sizes for OCR, node footprints.
   Rerun both tests until they pass, then do a short `--dry-run`.
4. **Touch panel** (pinch zoom only). Run `adb shell getevent -p` and find the device that lists
   `ABS_MT_POSITION_X` (`0035`) and `ABS_MT_POSITION_Y` (`0036`). Set `Device.TOUCH_DEV` to it, `TOUCH_MAX`
   to those two max values, and `PORTRAIT` to your portrait size. If your display rotation isn't
   `ROTATION_90`, adjust `Device._to_panel`.

A better long-term fix is to make the bot independent of the device: a device profile (resolution, touch
device, charging node), templates matched at several scales (event-map skulls already are), tap points stored
relative to a matched button or a screen edge, and pixel limits scaled to the screen. This isn't built yet.

## Without root (not built yet)

Root is used for screen capture and taps inside the app, the two-finger pinch (`sendevent`) and charging. The
possible routes:

- **Over adb from a computer:** the adb shell can already screenshot, tap, swipe and drag. Only the pinch and
  charging use `su`. The pinch usually works without `su`, because the shell user can normally write to the
  input devices. Untested.
- **In the app with [Shizuku](https://shizuku.rikka.app/)** (least work): Shizuku gives the app a shell with
  adb's rights, started through Wireless debugging. `RootShell.java` would start that shell instead of `su`
  and every command stays the same. Charging can't be done. Shizuku has to be restarted after each reboot.
- **In the app with an Accessibility Service:** Android's gesture API (taps, drag with a hold, multi-finger pinch)
  and `takeScreenshot()` (Android 11+). No restart after a reboot, but the capture and input layer would be
  rewritten in Java, and Unity's handling of injected gestures needs testing.

## Device quirks seen on the reference tablet

- Each separate `su` call over adb makes Magisk show a toast that hides card names, so the adb backend uses `su`
  only for charging, `svc` and the pinch.
- Lenovo's game assistant may show "Block notifications / Panoramic sound" boxes when the game starts. They go
  away on their own.
