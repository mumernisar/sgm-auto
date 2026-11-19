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

Git, releases (repo: `git@github.com:mumernisar/sgm-auto.git`, public; `main` tracks `origin/main`):
- Commit and push only when asked; ask before adding a Co-Authored-By trailer. Other players' names in shots
  are fine, but the user's own in-game name must never be public: `snap.sh` blurs it in shots, and any video
  or image for the README / posts needs it blurred too (top bar, prize lobby panel, fight results).
- A release = `./release.sh <version>` from a clean `main` (`gh` is logged in as mumernisar). It runs both
  tests + py_compile, writes `VERSION`, builds the debug APK, commits "Release v<version>" if `VERSION`
  changed, tags `v<version>`, pushes `main` and the tag, and creates the GitHub release with
  `sgm-bot-<version>.apk` (`-beta.N` → pre-release). Notes = commit subjects since the previous tag.
- Versions: `X.Y.Z-beta.N` for betas (bump N each time), `X.Y.Z` for a final. Never reuse one. `VERSION` is
  the single source: Gradle reads it for versionName and derives versionCode
  (`major*1e6 + minor*1e4 + patch*100 + (N or 99)`, so a beta sorts below its final).
- The user chose this local script over GitHub Actions / a release key (too much for a side project): don't
  re-propose it. APKs are signed with this Mac's debug key, which is what lets a release update the installed
  app in place; building on another machine would need an uninstall.
- History: `v0.1.0-beta.1` (first release). Check `gh release list` for the latest before picking a number.
