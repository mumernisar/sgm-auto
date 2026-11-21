# Running without root

The app runs the bot on a non-rooted phone or tablet of any screen size, with no computer attached. This file
records why it works this way, what was tested, and how it's built. User steps: `docs/SETUP.md`.

## Why a non-rooted device needs a helper at all

Inside the app the bot runs as a normal app. A normal app can't screenshot another app, tap inside it, or change
the screen size. On the tablet `su` gives those rights. Without root, something has to give the app the rights of
adb's `shell` user, which is allowed to do all three (`screencap`, `input`, `wm size`, injecting touch events).

| Setup | Who provides the rights | User needs |
|---|---|---|
| Bot on the Mac over USB (works today) | adb from the Mac | Device plugged into the Mac all run |
| App on a rooted device (works today) | `su` | Magisk |
| **App, no root (built)** | **[Shizuku](https://shizuku.rikka.app/)**: an adb shell started on the device through Wireless debugging | Shizuku app, tap *Start* after each reboot |
| App, no root, no Shizuku (later, maybe) | Our app talks to Wireless debugging itself, as Shizuku does | Same pairing and restart, but one app |
| App, no shell at all (not planned) | Accessibility Service + MediaProjection | Capture and input rewritten in Java; can't force 16:10 |

## Different screen sizes: force 16:10 instead of re-measuring

Unity anchors buttons to screen edges, so on a wider screen (most phones are ~20:9) the layout changes and every
template and tap point would need re-measuring per device. Instead the device's logical screen is set to the
tablet's size, by the user with the panel's ⤢ (it needs a game restart, see *What was tested*):

```sh
wm size 1200x1920   # Fast (the default off the tablet): 1920x1200 landscape, the tablet layout at 75%
wm size 1600x2560   # Full: 2560x1600 landscape, the tablet's own size
wm size reset       # back to normal
```

Fast draws and reads 56% of the pixels (image work ~40% faster); coordinates stay in the tablet's units and are
scaled by each frame's width (`bot/frame.py`, `docs/SPEED.md`).

The big game bots do the same (MAA and ALAS require one resolution and tell phone users to run `wm size`).
`screencap` and `input` both work in the overridden size, so templates and coordinates are used unchanged.

## What was tested (2026-11-20, Galaxy S23, Android 17, no root)

Bot run from the Mac over adb, with tablet templates and coordinates and no code changes except the pinch:

| | Result |
|---|---|
| `screencap` under the override | 2560x1600, layout identical to the tablet |
| Screens and OCR | event list, areas, cutscene, map, prefight, fight, victory, requirements |
| `input` tap / swipe / draganddrop | node taps, map panning, team filter, dragging a fighter into a slot |
| Fights | 5 wins, 0 losses, including a boss |
| `svc power stayon` | works without `su` |
| Applying the override | **the game must be restarted**: it keeps drawing into a buffer of the size it started with, which Android stretches (first seen as blurred, unmatched skull badges) |
| **Pinch with `sendevent`** | **blocked**: SELinux denies `/dev/input/event*` to the shell user, although it's in the `input` group |
| **Pinch with `injectInputEvent`** | **works** (`Pinch.java`) |

`android/app/src/main/java/dev/umer/sgmbot/Pinch.java` runs as the shell user (or root) through `app_process`,
loaded from the installed APK. It builds a two-finger `MotionEvent` and calls the hidden
`InputManagerGlobal.injectInputEvent` (`InputManager` before Android 14). It takes screen coordinates in the
overridden size, so it needs no touch device, panel range or letterbox offset, unlike `sendevent`. By hand:

```sh
adb shell 'CLASSPATH=$(pm path dev.umer.sgmbot | cut -d: -f2) app_process / dev.umer.sgmbot.Pinch 1280 800 1200 350'   # zoom out
```

Not seen on the tablet: right after a game restart the events list can rest between two cards (no card enlarged),
so `event_list` isn't detected until a card is centred.

## How it's built

| Part | Where | What it does |
|---|---|---|
| Shell | `RootShell.java` | `su` if the device has it (the tablet, unchanged), else an `sh` from Shizuku. Same stdin/stdout protocol either way, so `AppDevice` and `bot/` don't know which |
| Shizuku service | `ShellService.java`, `IShellService.aidl` | Shizuku runs it as the shell user; it starts `sh` and hands the app its stdin/stdout as two pipes |
| Pinch | `Pinch.java`, `Device.pinch` | `sendevent` only with root on a 2560x1600 screen (the tablet); everywhere else `app_process` + `injectInputEvent` |
| Screen size | `Device.screen_state` / `switch_screen`, the panel's ⤢ and ☰ Full / Fast | The user switches with ⤢: `wm size 1200x1920` (Fast, the default off the tablet) or `1600x2560` (Full) + restart the game, or `wm size reset` + restart. ▶ ■ are grey until the state is `on` |
| Ready check | `Device.game_buffer` | `on` needs the game to *draw* at 16:10 and at the chosen size (2% tolerance; Full ↔ Fast needs a restart too), read from `dumpsys SurfaceFlinger` (the layer's buffer, or the buffer list when it's in the background). The game (old Unity) keeps the buffer size it started with and is stretched otherwise |
| Over adb | `runner.run` | A run on a screen that isn't ready switches it, restarts the game and stops so you can open the event (`fit_screen: false` makes it only stop) |
| Left-over size | *Reset screen size* in the app, Hide the panel | Back to normal and the game closed |
| Panel | `OverlayService.java` | Sized and placed in the 2560x1600 game frame, so it covers the same spot (home, avatar, name) on every screen; a dragged spot is remembered |
| Setup | `MainActivity.java` | Checklist with ✓ per step and a button to the right setting; the Shizuku pairing guide |
| `su`-only commands over adb | `AdbDevice` | `svc` and charging use `su` only when the device has it |

Still open:
- Our own Wireless debugging client instead of Shizuku (one app to install), if Shizuku turns out to be a hurdle.
- The event list resting between two cards after a game restart (see above).

## User flow

First time (once):
1. Install SGM Bot and Shizuku.
2. Settings → About → tap *Build number* 7 times; Developer options → *Wireless debugging* on (needs Wi-Fi).
   Xiaomi / Oppo / Vivo: also the extra input option (*USB debugging (Security settings)* on Xiaomi).
3. Shizuku → *Pairing* → enter the code from *Wireless debugging → Pair device with pairing code* → *Start*.
4. SGM Bot: allow *Display over other apps*, then *Allow all the time* when it asks for Shizuku.

Every session: open SGM Bot's panel and the game. On a phone tap ⤢ once (the screen switches to 16:10, Fast's
1920x1200 unless ☰ says Full, and the game restarts), open the event or prize fights, ▶. ⤢ stays on for later runs; ⤢ again or hiding the panel
switches back.

After a reboot: Shizuku → *Start* again (no new pairing). The panel says so if it isn't running.
