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

- Everything is in **full-resolution landscape pixels, 2560x1600** (the tablet). No scaling is done; a
  different resolution needs new templates and coordinates.
- No LLM, no network. Vision is OpenCV template matching plus Tesseract OCR.
- The same `bot/` package runs in two places, chosen by `cfg.backend`:
  - `adb`: from the Mac over USB (development; `run.py`).
  - `app`: inside the Android app (Chaquopy), the normal way to use it.

## Repository layout

| Path | What |
|---|---|
| `run.py` | Mac CLI: `auto` / `event` / `prize` / `look`, `--minutes N`, `--dry-run` |
| `bot/config.py` | All tunables (`Config` dataclass); `config.json` next to `run.py` overrides any of them. `ROOT` = `$SGM_HOME` or the repo folder |
| `bot/device.py` | `AdbDevice`, `AppDevice`: capture, tap, swipe, drag, **pinch**; charging off (adb only) |
| `bot/vision.py` | Template matching (`find`, `find_all`, gray mode, `find_gold`), shape matching for icons, colour helpers, OCR helpers, `parse_score` |
| `bot/screens.py` | `CHECKS` table: which template identifies which screen, checked in order (popups first). Fallback: story maps by skull badges |
| `bot/readers.py` | Reads specific screens: score bar, FIGHT enabled, requirement icons, tooltips, lobby, picker cards and slots, energy cost, list card, areas and chapter arrows, auto state |
| `bot/eventmap.py` | Node map: zoom detection, nodes, cleared, reachable, marker guess, labels, boss nodes, blue paths leaving the screen (`exits`), `choose()` / `unfinished()` |
| `bot/team.py` | Filter dialog control (tracked state), sort, card list scanning, drag, requirement planning, `build_event_team`, `build_prize_team` |
| `bot/modes.py` | Screen handlers: `Common`, `EventMode`, `PrizeMode`, `AutoMode`; `lives()` gives the `[fight +++]` tries-left mark |
| `bot/runner.py` | Main loop, unknown-screen timeout, error reporting, charging timer (adb only) |
| `bot/core.py` | `Ctx`: log, annotated debug images, `look`, `settle`, `wait_for`, `wait_change`, tap/drag helpers, `Stop` |
| `bot/control.py` | Pause / resume / stop and log feed for the app overlay (`checkpoint()` runs in every `look()`) |
| `templates/` | Cropped reference images, made by `tools/crop_templates.py` (`_sheet.png` = contact sheet) |
| `shots/` | 63 reference screenshots (`NNN_label.png` + `_small` copy). The player name is blurred (`tools/blur_name.py`; `snap.sh` runs it when `shots/.player_name` exists). `notes.txt` (git-ignored) keeps the full labels |
| `tests/` | `test_screens.py` (every shot → expected screen) and `test_readers.py` (verified values) |
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
  - Map labels: threshold from the plaque centre, keep glyph-shaped components, group them into words, take the
    word nearest the node. `???` is detected by its dots.
  - A lone "1" is recognised by its narrow shape (Tesseract reads it as 4).
  - The stylised "FREE!" reads as "FREFI": match `F\s*R` and no digits.
  - Sparse mode (`--psm 11`) misses some text that block mode (`--psm 6`) reads.
- **Map reachability**: blue path lines only lead to playable nodes. A blue component touching the node's
  footprint (double nodes extend right, triangle nodes extend down) counts as playable. Bright uncleared portraits are
  playable too. Failing both, the node nearest the marker. Zoom is the skull scale with the best match (0.5–1.25), and bosses use
  1.15–1.5x of that.
- **Map choice order** (`EventMode.event_map`): a node with a visible blue line (boss excluded) → zoom out
  (up to twice) → the node next to the marker (`Node.guess`, dropped after 2 failed taps) → pan toward a blue
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
  `Device._to_panel`. The pinch writes multi-touch protocol B events with `sendevent` (root).
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
  - `RootShell`: one `su` process. `exec(cmd)` writes the command plus an echo marker and reads until the
    marker. `screencap()` reads the header, then exactly w·h·4 bytes.
  - `Ocr`: `text()` / `data()` for the Python `pytesseract.py` shim (PNG bytes in, text / word boxes JSON out).
  - `OverlayService`: foreground service (`specialUse`). The pill shows status ▶/⏸ ■ ☰; ☰ expands
    recent lines and the mode radio and **pauses the bot while open**. Draggable by the status text. Docked at
    x=150 px, top (over the game's home/chat buttons, which the bot never needs). When a run ends by itself
    (done, a stop rule, an error) it posts a "SGM bot stopped" notification with the last `***` line on the
    `run_end_aosp` channel, which plays `res/raw/run_end.ogg`: AOSP's "Antares" notification sound
    (`platform/frameworks/base/data/sounds/notifications/ogg/Antares.ogg`, Apache-2.0). ■ ends a run silently.
    A channel's sound is fixed once created: give it a new id to change the sound.
  - `MainActivity`: overlay permission and show/hide buttons.
- Python side: `app_main.py` (`start(mode, listener)`, `pause`, `resume`, `stop`) runs `runner.run` in a thread
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

- Only one resolution / device is supported (all coordinates are absolute). Porting steps: `docs/SETUP.md`.
- An unknown popup stops the bot (by design, no guessing). A generic "close any ✕" rule was considered, but it
  needs checking that it can't hit the filter / keep-streak / refill dialogs.
- Prize fight points per win aren't modelled (opponent choice = highest bonus ≤ cap); logging points per fight
  would allow a better choice.
- Expert-level event nodes lose often: the bot uses the user's hand-set team by design.
- The overlay pill covers the player's own score in the top bar; the bot doesn't read it (it uses the lobby
  total). The user wants the pill as it is.
