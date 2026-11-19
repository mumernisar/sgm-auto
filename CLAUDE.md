# sgm-bot: notes for agents

Skullgirls Mobile automation for the user's rooted Lenovo tablet. A Python bot (OpenCV + Tesseract, no LLM)
runs from the Mac over adb or, normally, **inside the Android app in `android/`** with a floating control panel.

Read first:
1. `FLOW.md`: what the bot does on every screen. **These are the user's rules; change behaviour only when asked.**
2. `docs/DEVELOPMENT.md`: architecture, modules, techniques, device specifics, app internals, testing.
3. `README.md`: how to run and build. `docs/SETUP.md`: requirements, other devices, no-root plan.

Working rules learned with this user:
- Never spend anything: no gems, purchases, energy refills, ads (WATCH AD / REFRESH / GET NOW / EQUIP / FAVORITE).
- Event teams are set by hand for synergy. Only swap fighters when FIGHT is greyed out (requirement unmet),
  never after losses.
- New screens: ask the user to show them (`! ./snap.sh <label>` from the repo folder) or snap them yourself, add a
  template, a `CHECKS` row, a handler and a test case. Then run both tests before any live run.
- Live runs from the Mac: `.venv/bin/python run.py auto --minutes N`, and watch `logs/bot.log`. Don't reinstall
  the app while the user is running it (it kills the run).
- Charging re-enables itself. `./charge.sh off` when the user asks; a run over adb does it every 5 min (the app doesn't).
- The app runs Python 3.10: check with `/opt/homebrew/bin/python3.10 -m py_compile bot/*.py`.
- Edit `bot/` in the repo root. `android/app/src/main/python/bot` is a generated copy.
