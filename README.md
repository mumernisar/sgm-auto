# SGM Bot

**Skullgirls Mobile plays itself.** Event maps, origin stories and prize fights, right on your phone or tablet.
No root, no PC, no AI, and it never spends a single gem.

[![Latest release](https://img.shields.io/github/v/release/mumernisar/sgm-auto?include_prereleases&label=download&color=e8730c)](../../releases)
![No root needed](https://img.shields.io/badge/root-not%20needed-2ea44f)
![Android 11+](https://img.shields.io/badge/Android-11%2B-3ddc84?logo=android&logoColor=white)
![Phones and tablets](https://img.shields.io/badge/screens-phones%20%26%20tablets-blue)
![Offline](https://img.shields.io/badge/runs-on%20the%20device%2C%20offline-6f42c1)
![Never spends](https://img.shields.io/badge/never%20spends-gems%20%C2%B7%20refills%20%C2%B7%20ads-critical)

https://github.com/user-attachments/assets/e9a1c717-fd89-42b0-a11f-dc0f9e0903a4

## Why you'll like it

- **No root needed.** The free [Shizuku](https://shizuku.rikka.app/) app gives it what it needs: a one-time pairing
  over Wi-Fi, no computer. Rooted (Magisk)? That works too.
- **Any phone or tablet.** One tap (⤢) switches the screen to the layout it knows, and back when you're done.
  Tested on a Galaxy S23 and a Lenovo tablet.
- **Fast on phones.** *Fast* mode runs the game at 1920x1200: a whole event node (map → fight → back) takes
  about a minute, fight included.
- **Builds your team.** It reads node requirements (elements, rarities, characters, even "NEED … VARIANT"
  tooltips), filters your roster and drags the right fighters in.
- **Takes your hands off, gives them back.** Touch the game at any time and it pauses; ▶ carries on.
- **Safe by design.** It never taps gems, purchases, energy refills, ads or equips, and it stops and tells you
  why when it meets a screen it doesn't know.

## Get started (no root)

1. **Install** the APK from [Releases](../../releases) and open **SGM Bot**.
2. **Do its checklist** (first time only): allow *Display over other apps*, install Shizuku and pair it (about
   5 minutes, Wi-Fi only), then allow SGM Bot in Shizuku. Each step has a button that takes you there.
3. Tap **Show the panel and open Skullgirls**.
4. On a phone, tap **⤢** on the panel: the screen switches to the tablet's shape and the game restarts.
5. Open your event or the prize fights and press **▶**.

Step-by-step guide, rooted devices and brand-specific notes: **[`docs/SETUP.md`](docs/SETUP.md)**.

**Needs:** Android 11+ (arm64) and the game in English.

## What it plays

Pick a mode under **☰**, press **▶** and leave it.

| Mode | What it does |
|---|---|
| **Event** | Origin stories and event maps: zooms the map out, finds the next open node, sweeps the map when none is in view, plays the boss last and moves on chapter by chapter, difficulty by difficulty. Rematches a node up to 3 times. |
| **Prize** | Picks the opponent with the best bonus under a power cap, then builds a cheap team: gold fillers plus one anchor sized to the enemy, so your strong fighters stay fresh. Skips fighters without enough energy. |
| **Auto** | Works out which of the two you're on and switches by itself. |

**Tested on:** origin stories, prize fights and monthly events (Lovesick, Gremlin-style maps, Maplecrest).

## The panel

A small translucent panel sits at the top left of the game, over your name, clear of your score.

| | |
|---|---|
| **⤢** | Switch the screen to the tablet's shape (phones; the game restarts). Green = on. |
| **▶ / ⏸** | Start / pause at once (no tap after you press it, even mid-step). |
| **■** | Stop. |
| **☰** | Recent steps, the mode (Auto / Event / Prize) and the size (**Fast** 1920x1200 or **Full** 2560x1600). Pauses the bot while open. |

The line under the buttons shows the current step; when the bot stops on its own, it says why there (and you
get a notification). Drag the panel by that line to move it; hold it to put it back. In an event fight it shows
the tries left on the node: `[fight +++]`, each loss turns a `+` into `✗`.

*Unofficial fan project, not affiliated with Hidden Variable or Autumn Games. Automating the game may break its
terms of service: use it at your own risk.*

---

## For developers

The same Python package (`bot/`, OpenCV + Tesseract) runs inside the Android app (`android/`, via Chaquopy) and
from a Mac over adb. It's tested offline against 75 reference screenshots, at full size and at Fast mode's
1920x1200. The repo is set up for coding agents too: point yours at it (`CLAUDE.md` is the entry point).

Docs: [`FLOW.md`](FLOW.md) (what it does on every screen) · [`docs/DEVELOPMENT.md`](docs/DEVELOPMENT.md) (how it
works) · [`docs/NO-ROOT.md`](docs/NO-ROOT.md) (phones without root) · [`docs/SPEED.md`](docs/SPEED.md) (making it
fast on phones) · [`docs/SETUP.md`](docs/SETUP.md) (setup and other devices).

<details>
<summary><b>Build and install the app (Mac)</b></summary>

```sh
cd android
./gradlew assembleDebug
adb install -r app/build/outputs/apk/debug/app-debug.apk   # stops a running bot
```

Needs JDK 17+, the Android SDK (path in `android/local.properties`) and Python 3.10
(`brew install python@3.10`). The build copies `bot/` and `templates/` into the app automatically.

Log on the device: `/data/data/dev.umer.sgmbot/files/logs/bot.log` (readable with root, or `run-as` on a debug
build).
</details>

<details>
<summary><b>Run from the Mac</b></summary>

```sh
.venv/bin/python run.py look                 # what the bot sees on the current screen
.venv/bin/python run.py auto --minutes 5     # real run, stops after 5 minutes (Ctrl+C any time)
.venv/bin/python run.py event --dry-run      # decide and log, never tap
.venv/bin/python run.py prize --size fast    # force prize fights, at 1920x1200
./snap.sh <label>                            # save the device's screen to shots/ (reference / new screens)
./charge.sh off                              # stop a rooted tablet charging over USB (it re-enables itself)
```

Logs: `logs/bot.log`; an annotated screenshot of every tap and error is saved in `logs/debug/`.
First-time setup: `python3 -m venv .venv && .venv/bin/pip install opencv-python-headless numpy pytesseract`
and `brew install tesseract`.
</details>

<details>
<summary><b>Tests</b></summary>

```sh
.venv/bin/python -m tests.test_screens          # every shot → expected screen
.venv/bin/python -m tests.test_readers          # scores, icons, cards, maps, areas… vs verified values
.venv/bin/python -m tests.test_screens --fast   # the same at 1920x1200
.venv/bin/python -m tests.test_readers --fast
```
</details>

<details>
<summary><b>Settings</b></summary>

Defaults and comments are in `bot/config.py`. Override any of them in `config.json` next to `run.py` (Mac):

```json
{ "max_enemy_total": 25000, "delay": [1.5, 3.0], "screen_size": "fast" }
```
</details>

<details>
<summary><b>Releases</b></summary>

The version is in `VERSION` (`MAJOR.MINOR.PATCH`, or `-beta.N` for pre-releases). To publish one, from a clean
`main` with `gh auth login` done:

```sh
./release.sh 0.1.0-beta.6   # tests, build, tag, push, GitHub pre-release with the APK
./release.sh 0.1.0          # a final release
```
</details>
