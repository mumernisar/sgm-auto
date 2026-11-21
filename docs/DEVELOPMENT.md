# Developer guide

How the bot is built, how to change it safely, and what was learned the hard way. The game rules it follows are
in `FLOW.md` (they're the user's; don't change behaviour without being asked).

## Big picture

```
screenshot ──► screens.detect() ──► screen name ──► mode handler ──► taps / drags / pinch ──► repeat
                 (templates)                          (modes.py)        (device.py)
                      ▲                                   │
                readers.py / eventmap.py  ◄───────────────┘  (numbers, icons, map nodes, cards)
```

- Every coordinate is in **design units: landscape pixels of the tablet's 2560x1600**. Any other screen is
  switched to Full (2560x1600) or Fast (1920x1200, the same layout with 56% of the pixels) with `wm size` and the
  panel's ⤢, and the game restarted in it, so it draws the tablet's layout. Without root the app's shell comes
  from Shizuku: `docs/NO-ROOT.md`.
- **Fast mode** (`bot/frame.py`): a frame's scale is its own width / 2560 (`k`: 1.0 Full, 0.75 Fast, 0.5 for a
  half-size copy), so there's no setting to keep in step. Screen detection, `vision` (regions, templates, OCR
  enlargement) and the map read work on the frame as captured (`Ctx.raw`) and return design units; `Device`
  converts touches with the last frame's `k` (not the root `sendevent` pinch: physical pixels are design units on
  the tablet). Readers and team building measure pixel sizes, so they get `Ctx.img`, the frame upscaled to
  2560x1600 once per capture when first asked for (~3 ms on the Mac). At `k == 1` nothing is resized: the Full
  path is the code as measured. Fast differences, all on smaller frames only: the map's badge cutoff is at most
  0.8 (scores spread more: 008), the half-size boss search's rough threshold is 0.65.
- No LLM, no network. Vision is OpenCV template matching plus Tesseract OCR.
- The same `bot/` package runs in two places, chosen by `cfg.backend`:
  - `adb`: from the Mac over USB (development; `run.py`).
  - `app`: inside the Android app (Chaquopy), the normal way to use it.

## Repository layout

| Path | What |
|---|---|
| `run.py` | Mac CLI: `auto` / `event` / `prize` / `look`, `--minutes N`, `--dry-run` |
| `bot/config.py` | All tunables (`Config` dataclass); `config.json` next to `run.py` overrides any of them. `ROOT` = `$SGM_HOME` or the repo folder |
| `bot/frame.py` | Design units: `k_of(img)` (pixels per design unit, from the frame's width) and `design(img)` (the frame at 2560x1600) |
| `bot/device.py` | `AdbDevice`, `AppDevice`: capture, tap, swipe, drag, **pinch** (`sendevent` on the rooted tablet, else `Pinch.java` via `app_process`), touches in design units; `SIZES` (Full / Fast), `screen_state` / `switch_screen` (`wm size` + game restart; `on` needs the game to draw at the chosen size), `game_buffer` (`dumpsys SurfaceFlinger`); charging off (adb with root) |
| `bot/vision.py` | Template matching (`find`, `find_all`, gray mode, `find_gold`), shape matching for icons, colour helpers, OCR helpers, `parse_score` |
| `bot/screens.py` | `CHECKS` table: which template identifies which screen, checked in order (popups first). Fallback: story maps by skull badges |
| `bot/readers.py` | Reads specific screens: score bar, FIGHT enabled, requirement icons, tooltips, lobby, picker cards and slots, energy cost, list card, areas and chapter arrows, auto state |
| `bot/eventmap.py` | Node map: zoom detection, nodes, cleared, reachable, marker guess, boss nodes, blue paths leaving the screen (`exits`), `choose()` (open node nearest the screen centre; scores aren't read) / `unfinished()` |
| `bot/team.py` | Filter dialog control (tracked state), sort, card list scanning, drag, requirement planning, `build_event_team`, `build_prize_team` |
| `bot/modes.py` | Screen handlers: `Common`, `EventMode`, `PrizeMode`, `AutoMode`; `lives()` gives the `[fight +++]` tries-left mark |
| `bot/runner.py` | Main loop, unknown-screen timeout, error reporting, charging timer (adb only) |
| `bot/core.py` | `Ctx`: log, annotated debug images, `look`, `settle`, `wait_for`, `wait_change`, tap/drag helpers, `Stop` |
| `bot/control.py` | Pause / resume / stop and log feed for the app overlay. `checkpoint()` runs before every touch (`Device`), between template searches (`vision.find_all`, the map zoom search) and in every `look()`: nothing touches the screen while paused, and on resume the interrupted step is dropped (`Resumed`, caught by the runner, which looks again). `pauses` counts every pause request; when it changed, the runner calls `mode.forget_step()` after its next look: map zoom, sweep, tap retries, team built / retreat, auto-battle taps and the filter's tracked state are forgotten (wins / losses, `bad` nodes and the counted result are kept) |
| `templates/` | Cropped reference images, made by `tools/crop_templates.py` (`_sheet.png` = contact sheet) |
| `shots/` | 63 reference screenshots (`NNN_label.png` + `_small` copy). The player name is blurred (`tools/blur_name.py`; `snap.sh` runs it when `shots/.player_name` exists). `notes.txt` (git-ignored) keeps the full labels |
| `tests/` | `test_screens.py` (every shot → expected screen) and `test_readers.py` (verified values); both with `--fast` too (shots shrunk to 1920x1200; positions may be 2 units off, ties between equal map nodes accepted) |
| `tools/blur_name.py` | Blurs your in-game name in shots (OCR on the three places it appears). Name from `shots/.player_name` (git-ignored) or `$SGM_PLAYER_NAME` |
| `snap.sh` | `./snap.sh <label>` saves the tablet's screen into `shots/` (used with `! ./snap.sh …`) |
| `charge.sh` | `./charge.sh off \| on \| status`: tablet battery charging |
| `android/` | The app (see below) |
| `logs/` | `bot.log` (append-only) and `debug/` (annotated JPEG per tap/error, last 400) |

## The main loop (`runner.run`)

1. Over adb, every 5 min: turn charging off (USB keeps the tablet charging). The app skips this.
2. `ctx.look()`: `control.checkpoint()` (pause/stop), capture, `screens.detect()`.
3. `unknown` screens are tolerated for 40 s (loading, animations), then a debug image is saved and it stops.
4. Otherwise `mode.handler(screen)()`. Handlers do **one step** and return; the loop looks again. Some handlers
   run short sequences (team building, panning) and call `ctx.look()` themselves.
5. Handler exceptions get a full traceback and a debug image; 3 in a row stops the run.
6. `Stop("reason")` anywhere ends the run cleanly with that reason (shown in the overlay / log).

`AutoMode` keeps an `EventMode` and a `PrizeMode` (sharing one `Filter`) and switches by screen (see `FLOW.md`).

## Screen detection

`screens.CHECKS` rows are `(screen, template, search region, threshold)`, matched in order. The first hit wins,
so **popups that can sit on top of other screens come first** (cutscene, offer, fight modifiers, keep streak,
energy refill, missing moves, paused). Then:

- `event_prefight` vs `prize_team` share the TEAM button; the ⚡ cost plate above FIGHT means prize
  (`readers.fight_energy_cost` needs ≥3 bolts in a row).
- `area_chevron` is matched with `find_gold` (only saturated gold pixels) because it sits on the moon or a
  dark sky.
- Story maps have no TIME REMAINING: `eventmap.looks_like_map` (≥2 skull badges at any zoom, or one badge plus
  the player marker when zoomed in close).

### Adding a new screen

1. Get the user to show it: `! ./snap.sh <descriptive-label>` (or snap it yourself with
   `./snap.sh`). Read the `_small.png` (1280x800, so multiply coordinates by 2).
2. Add a crop box to `tools/crop_templates.py` `SPEC` (full-res x, y, w, h) and run
   `.venv/bin/python tools/crop_templates.py <name>`; check `templates/_sheet.png`.
3. Add a `CHECKS` row (popup-like screens near the top) and a handler method named after the screen in
   `modes.py` (in `Common` if both modes need it); add the name to `runner.SCREENS`.
4. Add the shot to `tests/test_screens.py` `EXPECTED` and run both tests.
5. Check the new template doesn't fire elsewhere: match it against all shots.

## Vision techniques that worked (and the traps)

- **Template matching** (`TM_CCOEFF_NORMED`) with a tight search region works for fixed UI. Backgrounds
  behind a button can drop the score (the filter funnel scored 0.5 on wood), so for fixed-position buttons on
  a known screen a **fixed tap** is more reliable (`team.FILTER_BTN`).
- **Requirement icons vs filter icons** are drawn differently (colours, rings). `vision.symbol()` extracts the
  bright symbol inside the ring, drops ring arcs, crops to the bounding box, and `iou()` compares blurred
  silhouettes. Scores ~0.96–0.99 for a match, well below 0.65 otherwise. Rarity medals share one shape, so they're
  told apart by colour. An excluded icon has a red ring at radius 40–48 px; red pixels are blanked before matching.
- **Card elements** come from the disc colour (same rendering every time), not shape.
- **OCR** (Tesseract):
  - White text on colour: use `_white_text` (HSV mask), not Otsu.
  - Card scores: three different passes, accept a value only when two agree, then `drop_out_of_order`
    (the list is sorted, so an outlier is a misread).
  - A lone "1" is recognised by its narrow shape (Tesseract reads it as 4).
  - The stylised "FREE!" reads as "FREFI": match `F\s*R` and no digits.
  - Sparse mode (`--psm 11`) misses some text that block mode (`--psm 6`) reads.
- **Map reachability**: blue path lines only lead to playable nodes. A blue component touching the node's
  footprint (double nodes extend right, triangle nodes extend down) counts as playable. Bright uncleared portraits are
  playable too. Failing both, the node nearest the marker. Zoom is the skull scale with the best match (0.5–2.1;
  every scale on a half-size frame, the 3 best at full size), and bosses use 1.15–1.5x of that.
- **Map read speed** (a read was ~2 s on the Mac, ~30 s on the S23; now ~0.3-0.6 s and ~7-8 s in Fast):
  `EventMode.zoom` keeps the last read's zoom (fully zoomed out is the same every time) and the next read only
  confirms it (`eventmap._confirm`: ≥ 0.8 and at least as good as both neighbouring zooms
  and hint/1.2, hint/1.25), else the full search. It isn't a climb toward a better neighbour, and the /1.2 check
  is there because with a boss in view the boss badge has its own peak at ~1.2-1.25x the zoom (044, 047, 062,
  068): a stale hint there would pass as the zoom. Cleared on a new map and after a pause.
  Boss sizes are searched on a half-size frame at 0.7 and confirmed in windows at full size at 0.8
  (`vision.find_all_halved`: half-size badge scores are within 0.07 of full-size ones), so the scores are the
  full-size ones. Both checked against the old `read` output on every map shot, with every scale as the hint.
  Node scores aren't read at all (the user: any open node will do; scores only matter in prize fights): OCR was
  half of a read at a known zoom.
  `EventMode._read_map` reuses the last read while the view hasn't moved (`vision.changed` < `STILL`) and no other
  screen came up since (`Ctx.changes`): after a fight only a ✓ differs, well under `STILL`.
- **Map choice order** (`EventMode.event_map`): first, on every arrival (`Ctx.changes` moved since the last
  zoom-out), one pinch fully out (`_zoom_out`; another, up to twice, while the read shows more than
  `eventmap.FLOOR` = 0.75): the game resets the zoom whenever the map is left, fully zoomed out is 0.75 on every map
  seen, and the zoom is then fixed for the visit. Then a node with a visible blue line (boss excluded) → the node
  next to the marker (`Node.guess`, dropped after 2 failed taps) → pan toward a blue
  line that runs off the screen (`MapState.exits`, up to 3) → sweep `SWEEP_ORDER` (up, left, down, right, up),
  each direction until `vision.changed` between frames is < `STILL` % (the map's edge: backgrounds don't
  move with the nodes, so it counts changed pixels rather than measuring a shift) or 3 swipes → a second
  sweep that also accepts the boss. After zooming out the scale is passed to `eventmap.read(img, scale)`:
  auto-detecting it fails when only a boss is in view (its bigger badge is taken for the zoom). A tap only counts as
  opened when the pre-fight screen shows (`map_taps` resets there), so a popup can't make it loop.
- **Boss nodes** are the same skull badge drawn ~1.35x bigger, and so is their ✓: checkmarks are matched at
  both sizes.
- **Requirement flashing red**: an unmet requirement on the team picker pulses red over the whole icon, which
  once read as "excluded". Excluded = red ring (radius 40–48) **and** a mostly clear inside (<0.3 red).
- **Chapters** (« AREA CHAPTER N », `readers.chapter_arrows`): arrows are matched beside the current area's %;
  lit = ~18% gold pixels, greyed (first / last chapter) = ~0. After an arrow tap the panel and camera slide,
  so `EventMode._chapter_panel` reads until two reads agree. The chevron bobs ~55px: the panel % is read
  in block mode, then sparse mode, then taken from the whole-screen pass. `%` text in the top bar is ignored
  (coins / chevron once read as "4%").
- **Events list**: the neighbouring cards have their own PLAY and ›, which match as well as the real ones
  (0.93 vs 0.99). Only a PLAY centred at x≈1280 counts; its › is searched in a tight box at (+235, −160).
- **Timing**: screens slide in. Always `ctx.settle()` before reading a freshly opened screen, and
  `wait_change()` after FIGHT (popups animate in; re-handling the old frame rebuilt teams twice).

## Device specifics (reference device: Lenovo TB320FC, Android 15, Magisk)

Setting up or porting to another device: `docs/SETUP.md`.


- Screen 2560x1600 landscape, `ROTATION_90`. Touch panel `/dev/input/event5` (NVTCapacitiveTouchScreen),
  axes 0–16000 x 0–25600 in portrait. Landscape (x, y) → panel (`(1600 - y) * 10`, `x * 10`). See
  `Device._to_panel`. The pinch writes multi-touch protocol B events with `sendevent` (root). Every other device
  (and any device without root, where SELinux blocks `/dev/input`) pinches with `Pinch.java`.
- Raw `screencap` output has a 16-byte header (w, h, format, colour space), then RGBA.
- `input draganddrop x1 y1 x2 y2 ms` is what moves cards (a plain swipe scrolls the list instead).
- Charging: `/sys/class/qcom-battery/batt_charge_en` (0 = off, as root). It switches itself back on
  over time and after replugging. **Never touch** `ship_mode_en` in the same folder.
- Each separate `su` call makes Magisk show a "granted superuser" toast over the bottom of the screen,
  which hides card names. Over adb only charging and `svc` use root. The app keeps one persistent root
  shell, so there are no toasts.
- Lenovo's game assistant may pop small "Block notifications / Panoramic sound" boxes at game start. They
  vanish on their own.

## The Android app (`android/`)

- Gradle (wrapper 9.9.1), AGP 9.5.1, Chaquopy 17.2.0 (Python **3.10**, the only version with Chaquopy OpenCV
  wheels: numpy 1.26.2, opencv-python 4.5.1.48), Tesseract4Android 4.9.0 (JitPack), Java only (no Kotlin),
  minSdk 30, target 35, arm64 only.
- Build needs JDK 17+, the Android SDK (`local.properties`: `sdk.dir=/opt/homebrew/share/android-commandlinetools`)
  and a local **Python 3.10** (`brew install python@3.10`; Chaquopy uses it to download the phone's packages).
- `app/build.gradle.kts` copies `../bot` → `app/src/main/python/bot` and `../templates` →
  `app/src/main/assets/templates` before each build (`syncBot`, `syncTemplates`; git-ignored copies).
  **Edit the repo's `bot/`, never those copies.**
- Launcher icon: adaptive icon in `res/mipmap-anydpi-v26` (the player's avatar cut along its gold octagon as
  the foreground PNG, a navy gradient drawable behind it).
- Java side:
  - `App`: unpacks templates + `tessdata/eng.traineddata` to the files dir, `Ocr.init`, starts Python,
    `app_main.init(home)` (sets `SGM_HOME`).
  - `RootShell`: one shell for the app: `su` if `su` is on the PATH (found by looking, so Magisk doesn't ask
    early), else an `sh` from Shizuku (`ShellService`, bound as a Shizuku user service, hands over stdin/stdout
    as pipes). `exec(cmd)` writes the command plus an echo marker and reads until the marker. `screencap()`
    reads the header, then exactly w·h·4 bytes. A dead shell is replaced on the next `get()`. `access()` tells
    the setup screen where the device stands (root / Shizuku missing / stopped / not allowed / ready).
    `openSecond()` opens another shell the same way (the Shizuku service is bound once and asked for more
    shells); `stream(cmd)` `exec`s a command that keeps writing and hands over its output; `close()` ends it.
  - `ShellService` + `IShellService.aidl`: runs in a process Shizuku starts as the shell user.
  - `TouchWatcher`: pauses a run when the user touches the game. The bot's touches are injected into Android's
    input system and never show on the touchscreen device; a finger does. Opened with the panel (not per run:
    each new `su` shows Magisk's toast; ▶ retries it), it finds the device listing `ABS_MT_POSITION_X` in
    `getevent -pl` (with `INPUT_PROP_DIRECT`: the S23 also has a multi-touch `sec_touchpad`, listed first) and reads
    `getevent -ql <device>` in a second shell, which sleeps between events. A new contact
    (`ABS_MT_TRACKING_ID` ≠ ffffffff, or `BTN_TOUCH DOWN`) goes to `OverlayService.onTouch`, which waits 300 ms and
    pauses unless the panel itself was touched within 0.5 s (its root view records each finger down). The
    tablet's root pinch writes to the touchscreen, so `AppDevice._run_script` calls `ignoreFor()` around it. If no
    touchscreen is found or getevent can't read it, the panel's log says so once and runs work as before.
  - `Pinch`: `main()` for `app_process` (`CLASSPATH=<apk> app_process / dev.umer.sgmbot.Pinch cx cy g0 g1 steps ms`).
    Framework classes only, so it loads from the APK without the app.
  - `Ocr`: `text()` / `data()` for the Python `pytesseract.py` shim (PNG bytes in, text / word boxes JSON out).
  - `OverlayService`: foreground service (`specialUse`). The pill has two rows: big buttons (⤢ ▶/⏸ ■ ☰,
    `BUTTON_W` x `BUTTON_H` = 46 x 48 units, ~7 mm on the S23) and under them the status line. ☰ expands recent
    lines, the mode radio and the size radio (Full / Fast, prefs `size`; default from the panel's physical size,
    `Display.Mode`, Full only at 2560x1600) with its own width (`details.setMinimumWidth`; the window is measured
    again on each toggle), and **pauses the bot while open**. Draggable by the status line; the spot is saved
    (prefs `overlay`, in game-frame px); a long press on it puts the pill back home. Docked at x=150, y=0 of the
    2560x1600 frame, over the game's home button, avatar and name, which the bot never needs: ~490 wide, so it ends
    at ~640, well before the player's own score in the team page's top bar (~810), and ~170 tall, above the STREAK
    label; clear of the back arrow, the pause button (fight) and the requirement icons. `LAYOUT` is bumped whenever
    home or the pill's size changes: saved spots from an older layout are dropped (layout 3: two rows; a spot
    saved over the score is gone). Sizes are layout units × 2.5 px (the tablet's density) × screen width / 2560,
    so the pill covers that same spot at any size; it rebuilds itself when the screen size changes. On screens not
    at the chosen size it shows ⤢ (a fourth button; on the tablet at Full it's hidden): `app_main.screen_state(size)`
    gives native / on / off (off too after picking the other size while switched); while `off`, ▶ ■ are drawn at
    30% alpha and a tap blinks ⤢ instead. ⤢ calls `screen_on(size)` / `screen_off(True)` (switch + restart the
    game), refused during a run; Hide the panel
    (onDestroy) calls `screen_off(False)` (switch back, close the game). When a run ends by itself
    (done, a stop rule, an error) it posts a "SGM bot stopped" notification with the last `***` line on the
    `run_end_aosp` channel, which plays `res/raw/run_end.ogg`: AOSP's "Antares" notification sound
    (`platform/frameworks/base/data/sounds/notifications/ogg/Antares.ogg`, Apache-2.0). ■ ends a run silently.
    A channel's sound is fixed once created: give it a new id to change the sound.
  - `MainActivity`: setup checklist (overlay, root or Shizuku install / start / permission, notifications,
    battery), show panel + open the game, hide, reset screen size (`screen_off(False)`), the brand notes and
    the Shizuku pairing guide.
- Python side: `app_main.py` (`start(mode, listener)`, `pause`, `resume`, `stop`, `screen_state`, `screen_on`, `screen_off`) runs `runner.run` in a thread
  with `device.connect("app")`. `pytesseract.py` stands in for the real package.
- Install / update: `./gradlew assembleDebug && adb install -r app/build/outputs/apk/debug/app-debug.apk`.
  **Reinstalling kills a running bot**, so ask first if the user is mid-run. Overlay permission over adb:
  `adb shell appops set dev.umer.sgmbot SYSTEM_ALERT_WINDOW allow`. Root is granted once in Magisk ("Forever").
- App log: `adb shell "su -c 'cat /data/data/dev.umer.sgmbot/files/logs/bot.log'"`; Python stdout also goes
  to `adb logcat | grep python.std`. Debug images: `/data/data/dev.umer.sgmbot/files/logs/debug/`.

## Testing

```sh
.venv/bin/python -m tests.test_screens   # all shots classify as expected (exit 1 on mismatch)
.venv/bin/python -m tests.test_readers   # values verified on the real game (exit 1 on failure)
/opt/homebrew/bin/python3.10 -m py_compile bot/*.py   # the app runs Python 3.10: no 3.11+ syntax
```

Live checks from the Mac: `run.py look` (what the bot sees now), `run.py <mode> --minutes 2` (short real run),
`--dry-run` (decide without tapping). After any live problem: read `logs/bot.log`, look at `logs/debug/`, snap
the screen, add it to the tests, fix, rerun the tests.

## Known limitations and ideas

- All coordinates are 2560x1600 design units; other screens rely on `wm size` (the panel's ⤢) to get the
  tablet's layout at 2560x1600 or 1920x1200. A device that refuses it needs the porting steps in `docs/SETUP.md`.
- An unknown popup stops the bot (by design, no guessing). A generic "close any ✕" rule was considered, but it
  needs checking that it can't hit the filter / keep-streak / refill dialogs.
- Prize fight points per win aren't modelled (opponent choice = highest bonus ≤ cap); logging points per fight
  would allow a better choice.
- Expert-level event nodes lose often: the bot uses the user's hand-set team by design.
