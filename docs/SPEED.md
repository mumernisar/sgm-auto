# Speed on phones

On a phone the bot was slow on event maps: on the Galaxy S23 (no root, Shizuku) one map read took 30-46 s in the
app against ~2 s on the Mac, a few reads per node. This records what was changed, what it gained and the
decisions behind it. How each piece works is in `DEVELOPMENT.md`; the rules it follows are in `FLOW.md`.

## Why phones are slow

- The bot's thread runs at 100% of one core; the Shizuku shell is idle. It's computation, not screenshots.
- Samsung's Game Optimizing Service caps the CPU while a game is in front (mid cores 1.4 of 2.8 GHz, prime 1.7 of
  3.36 GHz). Not heat, not power saving. The user chose not to change Samsung's settings.
- So the app's Python is ~15x slower than the Mac on the S23: 0.5 s on the Mac is noticeable on the phone.
  Profile on the Mac (`cProfile` on `eventmap.read`), check on the phone.

## Results (S23, Fast, real runs: 9 event nodes, a boss, a chapter change, 4 prize fights, no losses)

| | Before | Now |
|---|---|---|
| One map read | 30-46 s | ~7-8 s |
| Back on the map → node tap | ~2-2.5 min | 16-46 s (pinch and pans included) |
| A whole event node (map → fight → map) | ~4 min | ~60 s |
| A full sweep of a map (8 swipes) | several minutes | 84 s |

Mac, one map read over the 11 map shots (1.95 s before): new map 1.08 s Full / 0.61 s Fast, a confirmed zoom
0.78 / 0.45 s, a fixed zoom 0.49 / 0.28 s, an unchanged view 0. Screen detection: 149 ms Full, 90 ms Fast.

## What changed, and why

- **Fast mode** (1920x1200, the default off the tablet; ☰ Full / Fast). A frame's scale comes from its own width
  (`frame.k_of`), so nothing has to be kept in step. Detection, `vision`, the map read and touches work at any
  size; `readers` and `team` measure pixel sizes, so they get the frame upscaled to 2560x1600 (`Ctx.img`, once
  per capture, ~3 ms on the Mac). At `k == 1` nothing is resized: the tablet runs the code as measured.
  Lower resolutions were tested: 1920x1200 read 70/70 screens and every reading that matters; 1280x800 misread
  real values, so it isn't offered.
- **Maps are zoomed fully out on every arrival** (the user's idea). The game resets a map's zoom (to 1.0-1.1)
  whenever the map is left; fully zoomed out is 0.75 on every map seen, one pinch away, readable at 1920. One
  known zoom: the next read only confirms it (`eventmap._confirm`), more of the map is in view, and the read at
  the map's own zoom that usually found nothing is gone.
- **Node scores aren't read on maps** (the user: nodes unlock one after another, any open node will do; scores
  only matter in prize fights). OCR was half of a read. The bot takes the open node nearest the screen centre.
- **Boss badges are searched at half size** and confirmed at full size (`vision.find_all_halved`): the same
  hits and scores, a quarter of the work (rough threshold 0.7 Full, 0.65 Fast).
- **The zoom hint is only confirmed, never climbed from**: with a boss in view the boss badge has its own peak at
  ~1.2-1.25x the zoom, and a climb (or a stale hint on that peak) would take it for the zoom. `_confirm` also
  checks hint/1.2 and hint/1.25.
- **An unchanged view reuses the last read** (`EventMode._read_map`): only while no other screen came up since
  (`Ctx.changes`), because after a fight only a ✓ differs, which is under the "didn't move" limit.
- **Story maps at any zoom**: the badge only matches within ~3% of the true zoom, so `looks_like_map` ranks every
  zoom on a half-size frame and checks the best 3 (a fixed list of 12 zooms missed a map at 0.85).
- **Pauses**: touching the game pauses a run (`TouchWatcher`: `getevent` on the touchscreen, the device with
  `INPUT_PROP_DIRECT`; the bot's own injected touches never show there). After any pause the bot forgets what it
  knew about the screen (`Mode.forget_step`).

Every change that claimed "same results" was checked against the previous `eventmap.read` output on every map
shot (positions, states, the pick with every boss / guess setting); both suites also run with `--fast`.

## Dropped

- **A map survey and node tree** (stitch the whole map once per chapter, plan the unlock order, locate the view
  by the background): the user scrapped it. After the changes above, map work per node is ~10-40 s, and the
  survey would cost 1-2 min per chapter plus new failure modes.
- **A partial re-read after a pan** (move known nodes by the measured shift, search only the new strip): no test
  material, and map backgrounds stay put while the node layer slides, so the shift is hard to measure.
- **Searching only the map area** (leave the top bar out): nodes can sit under the bar, where the bot finds them
  and pans them into view.
- **Shrinking templates with INTER_AREA at 1920**: +0.01 in match score, and it would have touched the half-size
  path of Full.
