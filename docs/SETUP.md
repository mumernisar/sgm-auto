# Setting it up on your own device

The app runs on any Android 11+ phone or tablet, **with or without root**. On a screen that isn't the tablet's
2560x1600, the panel's **⤢** button switches the screen to that size (black bars on the sides of a phone) and
restarts the game in it, so the bot sees exactly what it was built on.

## Step by step

You need: an Android 11 or newer phone or tablet (64-bit), Skullgirls Mobile **in English**, and Wi-Fi.

**1. Install SGM Bot.** On the device, open the
[latest release](https://github.com/mumernisar/sgm-auto/releases) and download `sgm-bot-<version>.apk`. Open the
download and tap *Install*. Android asks to allow installs from your browser or Files app the first time: allow it.
*Samsung:* if it says "Unknown app blocked", turn off Auto Blocker first (see *Your brand* below).

**2. Open SGM Bot.** It shows a checklist. Do the steps that aren't ✓ yet, top to bottom. Each has a button that
goes straight to the right place; come back to SGM Bot after each one and it turns ✓.

| Step | What you do |
|---|---|
| Display over other apps | *Allow* → find SGM Bot → switch it on → back. |
| Install Shizuku *(no root)* | *Get Shizuku* → Install in the Play Store → back. |
| Start Shizuku *(no root)* | First time only: pair it (step 3 below). Then *Open Shizuku* → *Start*. |
| Allow SGM Bot in Shizuku *(no root)* | *Allow* → *Allow all the time*. |
| Root found *(rooted devices)* | Nothing now. The first ▶ makes Magisk ask once: *Grant* (Forever). |
| Notifications *(optional)* | *Allow*: a chime and a message when a run stops by itself. |
| Run in the background *(optional)* | *Allow*: Android won't stop a long run. Without root, also set Shizuku's battery use to *Unrestricted* (Settings → Apps → Shizuku → Battery). |

**3. First-time Shizuku pairing** (no root only, once, about 5 minutes, needs Wi-Fi).
Tip for any brand: the search box at the top of Settings finds *Build number* and *Wireless debugging*.
1. Turn on Developer options: Settings → About phone → tap **Build number** 7 times (where it is on your brand:
   see *Your brand* below). It says "You are now a developer".
2. Settings → Developer options → turn on **Wireless debugging** and accept. Also do your brand's extra
   developer setting below, if it has one.
3. Open **Shizuku** → under *Start via Wireless debugging* tap **Pairing**. Shizuku shows a notification.
4. Go back to Developer options → **Wireless debugging** → **Pair device with pairing code**. A 6-digit code
   appears. Pull down the notification bar, tap **Enter pairing code** on Shizuku's notification and type it.
5. In Shizuku tap **Start**. It says *Shizuku is running*.
6. Back in SGM Bot the Shizuku steps are ✓.

After a restart of the device, Shizuku stops: open it and tap **Start** again (no new pairing). Wi-Fi must be on
for that. SGM Bot's panel tells you if you forget.

**Your brand.** SGM Bot shows the notes for your device's brand under its checklist too.

| Brand | Build number (step 3.1) | Extra settings |
|---|---|---|
| **Samsung** | About phone → Software information | Installing blocked ("Unknown app blocked"): Settings → Security and privacy → **Auto Blocker** off (turn it back on after installing). Battery: Settings → Battery → Background usage limits → **Never sleeping apps** → add SGM Bot and Shizuku. Keep **Game Booster** off for Skullgirls (it can lower the game's resolution). |
| **Xiaomi / Redmi / POCO** (HyperOS, MIUI) | About phone → tap **OS version** (or *MIUI version*) 7 times; Developer options are in Settings → Additional settings | Developer options → **USB debugging (Security settings)** on: it's separate from *USB debugging* and may ask for a Mi account. Without it taps don't work. SGM Bot's app info → Other permissions → **Display pop-up windows while running in the background**. SGM Bot and Shizuku: **Autostart** on, Battery saver → **No restrictions**. The Security app's scan can switch Developer options off again. |
| **OPPO / OnePlus / Realme** (ColorOS, OxygenOS, realme UI) | About device → Version | Developer options → turn **off** *Disable permission monitoring* / *Permission monitoring* (the name varies), or Shizuku's rights are limited. Battery: app info → Battery → **Allow background activity** for both apps. |
| **Vivo / iQOO** | About phone → Software version | Battery → Background power consumption → allow SGM Bot and Shizuku. |
| **Lenovo** | About tablet (or phone) | The game assistant may show "Block notifications / Panoramic sound" boxes when the game starts; they go away on their own. |
| **Google Pixel, Motorola, Nokia** (stock Android) | About phone | None. |
| **Huawei / Honor** *(untested)* | About phone | No Play Store: Shizuku from [GitHub releases](https://github.com/RikkaApps/Shizuku/releases). Battery → App launch → both apps → Manage manually, all on. |

Other brands' battery killers: [dontkillmyapp.com](https://dontkillmyapp.com) has the steps per brand.

**4. Use it.**
1. In SGM Bot tap **Show the panel and open Skullgirls**.
2. In the game a small dark panel sits at the top left, over your name and clear of your score: its buttons on
   top, the current step under them. Drag it by that text to move it (it remembers the spot); hold the text to
   put it back.
3. **On a phone** (any screen that isn't 2560x1600) the panel has a **⤢** button, and **▶ ■ are grey** until you
   tap it (tapping them makes ⤢ blink). Tap **⤢**: the screen switches to the tablet's shape (black bars on the
   sides) at the size picked under **☰**: **Fast** (1920x1200, the default on a phone: the bot thinks ~40%
   faster and the game draws fewer pixels) or **Full** (2560x1600, the tablet's own size). The game restarts. It opens on the main menu: go to your event or prize fights.
   ⤢ turns green and stays on for every run after that. Tap it again to switch back (the game restarts);
   hiding the panel switches back too. The game has to restart each time because it keeps the size it started
   with. If the screen ever stays in the tablet shape, open SGM Bot and tap **Reset screen size**.
4. Press **▶**. **⏸** pauses, **■** stops, **☰** shows the recent steps and the mode (*Auto*, *Event*, *Prize*)
   and pauses the bot while open. **Touching the game pauses the bot too** (so you can take over at any time);
   **▶** continues. When the bot stops by itself, the reason is the last line on the panel.
   On the tablet (or any 2560x1600 screen) there's no ⤢ at Full (its default): just press ▶. Picking Fast
   there adds ⤢. Changing Full / Fast while ⤢ is green greys ▶ ■ until you tap ⤢ again (another restart).

**If something doesn't work**
- *The panel says "Shizuku isn't running"*: open Shizuku, tap Start, press ▶ again.
- *Taps do nothing, or Shizuku starts but the bot can't act*: your brand's extra developer setting in *Your
  brand* (Xiaomi: USB debugging (Security settings); OPPO / OnePlus / Realme: permission monitoring off).
- *The run stops when the screen is off or after a while*: your brand's battery setting in *Your brand*.
- *The bot stops on an unknown screen right away*: the game must be in English, and on a phone ⤢ must be green
  (if the game looks stretched, tap ⤢ twice: off and on again, which restarts it in the right shape).
- *Wireless debugging turns itself off*: it needs Wi-Fi; on mobile data alone Shizuku can't start.

## Requirements

| | Needed | Reference device |
|---|---|---|
| Screen | Any. Not 2560x1600? The panel's ⤢ switches it to the tablet's shape at 1920x1200 (Fast) or 2560x1600 (Full) (`wm size`), and back | Lenovo Tab (TB320FC), 2560x1600 |
| Android | 11 or newer (app `minSdk` 30), **arm64** | Android 15 |
| Rights | Root (Magisk) **or** [Shizuku](https://shizuku.rikka.app/) (no root) | Magisk |
| Game | Skullgirls Mobile in **English** (screens are read by OCR and English templates) | |
| Mac (to build the app or develop) | Homebrew, `adb` (`brew install android-platform-tools`), JDK 17+, Android SDK command-line tools, Python 3.10 (`brew install python@3.10`), Tesseract (`brew install tesseract`) | macOS, Apple silicon |

Tested without root on a Galaxy S23 (1080x2340, Android 17). How it works: `docs/NO-ROOT.md`.

## Building it yourself (Mac)

```sh
cd android && ./gradlew assembleDebug && adb install -r app/build/outputs/apk/debug/app-debug.apk
```

`android/local.properties` must point at your SDK: `sdk.dir=/path/to/android-sdk`. A device that has the release
APK installed needs an uninstall first: releases are signed with the maintainer's debug key.

The bot also runs from the Mac over adb (`run.py`, see `README.md`) on any device, rooted or not: adb gives it
the rights Shizuku gives the app. Pinch zoom then uses the installed SGM Bot APK (`app_process`), so install
the app on the device too.

In the game the bot reads auto battle from the 1x / 2x / 3x badge above the brain button (`shots/011`, `065`,
`066`), turns it on (brain) and sets 3x (badge). If yours looks different, the fight screen needs new
`templates/auto_*.png`.

## Optional: charging off (adb with root only)

Over a long run from the Mac, the USB cable keeps the tablet at 100%. The adb backend therefore turns charging off
every 5 minutes, and `./charge.sh off | on | status` does it by hand. The app never touches charging, and
without root it can't be done.

The path, `/sys/class/qcom-battery/batt_charge_en`, exists only on some Qualcomm devices. On anything else:
- turn it off with `{ "keep_charging_off": false }` in `config.json`, or
- find your device's switch (`adb shell su -c 'ls /sys/class/power_supply/battery/'`; common names are
  `charging_enabled`, `input_suspend`, `batt_charge_en`) and set `AdbDevice.CHARGE_NODE` in `bot/device.py`
  and `node` in `charge.sh`. **Only write to a node you've identified.** Some, like `ship_mode_en`, switch
  the battery off.

## If the screen can't be switched (`wm size`)

A few devices refuse `wm size`, or a layout could still differ. Then the bot needs its own screenshots and
coordinates for that screen (Unity anchors buttons to screen edges, so only a 16:10 screen scales uniformly):

1. **Reference screenshots.** Put your in-game name in `shots/.player_name` so `snap.sh` blurs it. Then, for every
   screen in `tests/test_screens.py`, open it on your device and run `./snap.sh <label>`. The blur looks for the
   name at the reference device's positions, so on a new layout update `PLACES` in `tools/blur_name.py`. Use the
   same shot numbers, or update `EXPECTED` and `tools/crop_templates.py`.
2. **Templates.** Re-measure each crop box in `tools/crop_templates.py` `SPEC` for your shots, run
   `.venv/bin/python tools/crop_templates.py`, and check `templates/_sheet.png`.
3. **Coordinates.** Fixed tap points and search regions are absolute pixels in `bot/modes.py`, `bot/screens.py`,
   `bot/team.py`, `bot/readers.py`, `bot/eventmap.py` and `bot/vision.py` (about 50 places). Pixel-size limits in
   the vision code need scaling too: icon ring radius 40–48 px, glyph sizes for OCR, node footprints.
   Rerun both tests until they pass, then do a short `--dry-run`, and set `{ "fit_screen": false }`.

## Device quirks

- Each separate `su` call over adb makes Magisk show a toast that hides card names, so the adb backend uses `su`
  only for charging and `svc`, and finds root by looking for `su` instead of calling it.
- Lenovo's game assistant may show "Block notifications / Panoramic sound" boxes when the game starts. They go
  away on their own.
- Samsung: Game Booster can lower the game's resolution; keep it off for Skullgirls.
- Without root, `sendevent` to `/dev/input` is blocked by SELinux even for the shell user, so pinch zoom is
  injected instead (`Pinch.java`).
