# Skullgirls Mobile bot: screen flow and rules

What the bot does on every screen, as agreed with the user. **These are the user's rules: change them only when
the user asks.** Numbers (thresholds, ratios, caps) live in `bot/config.py`. Shot numbers like `026` refer to
`shots/026_*.png` (the filename says what the screen is). How the code implements this:
`docs/DEVELOPMENT.md`.

## Shared

- Screens animate in, so the bot waits for each screen to settle before reading or tapping.
- On first use of the filter in a run, tap 🚫 to clear anything left over from before.
- Front of the team = the **rightmost** slot (it fights first).
- Fight (`shots/011`–`013`, `065`–`067`): auto (Brain Drain) is off = dark brain, no badge; on = lit brain
  with a 1x / 2x / 3x speed badge above it. Keep it on at 3x (`auto_speed`): off → tap the brain; another
  speed → tap the badge (it steps the speed). At most 4 taps per fight.
  The auto state is logged whenever it changes. Never tap pause. On the Paused screen (`014`), tap RESUME, never QUIT.
- Victory (`015`, `016`, milestone `028`–`031`, appears 0..N times): tap CONTINUE while VICTORY shows.
  Never FAVORITE.
- "Missing Moves or Guest Star" popup (`027`): tap FIGHT!, never EQUIP.
- Never spend gems, use energy refills or watch ads.
- In the app, a run that stops by itself (finished, a stop rule, an error) plays the "Antares" sound (from AOSP, bundled) and shows a
  notification with the reason; stopping with ■ is silent.
- Unknown screen for 40s: save a screenshot and stop. Errors are logged with a full traceback and a
  screenshot (`logs/bot.log`, `logs/debug/`). No LLM is involved.
- Over adb from the Mac only: charging is turned off every 5 minutes (`batt_charge_en`; it re-enables itself).
  The app never touches charging.
- Taps get a little random jitter and timing; occasionally a longer idle.
- **Offers** ("LIMITED TIME OFFER", can pop over VICTORY, `056`): tap ✕, never GET NOW.
- **Cutscenes** (`051`, `052`, also mid-fight): tap SKIP.
- **Fight modifiers** popup (`058`, can open from a map node tap): tap ✕. It counts as a node tap that didn't open.
- During an event fight the status line shows the tries left on that node: `[fight +++]`, each loss turns a
  `+` into `✗` (`++✗`, `+✗✗`).
- **Auto mode** (default): prize screens switch to prize handling, maps/areas/lists/cutscenes to event; shared
  screens keep the last mode; a defeat with REMATCH is always event.

## Event mode

1. **Map** (`008`, `009`, `044`, `046`, `047`, story `053`). The zoom level is detected (0.5–1.25x); boss
   nodes are drawn ~1.35x bigger.
   - Playable = uncleared node touched by a blue line (measured to the node's whole footprint: double nodes
     extend right, triangle nodes extend down), or an uncleared node with a bright revealed portrait.
     If none, step one node on from the marker (its line is often under the marker).
   - Cleared = green ✓ at the node's right edge.
   - Pick the lowest score first; `???` last. **The boss** (bigger node) **comes last**: it ends the chapter
     and the game moves on, so it's only fought after a full sweep of the map found nothing else playable
     (other uncleared nodes may be locked).
   - Nothing playable with a visible line: **zoom out first** (two-finger pinch via root sendevent, up to
     twice), then take the node next to the marker if there is one. Else follow a blue line running off the
     screen (up to 3 swipes, before the sweep only), then **sweep**: big swipes up until the map stops moving, then left, down,
     right and up again the same way (at most 3 swipes per direction). The first playable non-boss node ends
     the sweep. If none: sweep again, now taking the boss as soon as it's in view. Nothing at all: stop.
     Each swipe compares the frames before and after, so a direction (or a blue line) whose edge is reached
     isn't swiped again. The zoom is fixed after zooming out (pans don't change it). A playable node at
     the screen edge is panned toward the centre before tapping. A node tap that doesn't open: nudge the map
     (a different direction each time) after 3, skip after 6 (after 2 for the marker guess).
   - Story maps have no TIME REMAINING: recognised by their skull badges (zoom up to 1.25x).
2. **Pre-fight** (`010`, `018`): if FIGHT is orange, fight. **The team is only touched when FIGHT is grey.**
   The user sets event teams by hand for synergy, so never rebuild a working team, not even after losses.
   - Read requirement icons by shape (colour-blind), with count badge (no number = applies to every
     fighter) and red slash = excluded.
   - Tap each character requirement and read its tooltip at once (it closes after ~4s).
     "NEED <name> VARIANT" (`045`) means find that exact card by its name plate and put it in the front slot.
   - Other requirements replace the weakest slots with the strongest matching fighter (descending sort,
     energy ignored). Stop swapping as soon as FIGHT turns orange. Clear the filter before fighting.
   - Still grey after all requirements: back twice to the map, mark the node unusable, pick another.
3. **Defeat** (`017`): REMATCH up to 3 losses in a row on a node, then QUIT, back to the map, mark the
   node unusable.
4. **Events / Origin Stories list** (`048`, `050`): shown difficulty below 100% and PLAY orange → PLAY;
   100% or PLAY grey → › to the next difficulty; no › left → stop. Only the centred card counts (the cards
   beside it have their own PLAY and ›): wait while the list is still sliding.
5. **Area overview** (`049`, `054`, `055`, story events): open the area under the gold chevron (matched by its
   gold shape, any background) if below 100%, else another area below 100% (pan to look); all 100% → back.
   - Areas with chapters (« MAPLECREST CHAPTER 2 » , `059`, `060`): finish chapters **in order**. A boss win
     unlocks the next chapter and the game jumps there even if the earlier one isn't at 100%, so step « back
     to the first chapter (« greyed out), then » forward to the first chapter below 100% and open it.

## Requirements and the team filter (both modes)

- Requirement icons sit under the score bar. Each is a **character** (emblem), **element** or **rarity**
  (medal), optionally with a count badge.
  - With a number = that many fighters must match.
  - Without a number = **every** fighter must match (added to every slot's filter).
  - Red slash = excluded. An excluded element means selecting the other five elements; an excluded character
    means skipping cards whose name plate shows it; an excluded rarity is removed from the rarity filter.
- Tooltips (tap the icon; they close after ~4s): "NEED <name> VARIANT" = one exact card;
  "Must have a Dark **or** Air Fighter" = OR. The FIGHT button colour is always the final word.
- One filter pass fills one slot, with at most one character and one element requirement combined
  (Peacock×1 + Dark×1 → one dark Peacock).
- Filters are inclusive (selecting bronze shows only bronze). The bot tracks which tiles are selected and only
  taps the ones that differ. On the first filter use of a run it taps 🚫 to clear leftovers. Character emblems
  need one scroll of the filter grid. Sort: ▲ next to FIGHTER SCORE = ascending.
- Cards are dragged (`input draganddrop`) from the list onto a slot; dragged cards leave the list.

## Prize fights

Goal: save energy (it refills slowly) by using just enough power to win.

1. **Lobby** (`026`, `032`, `040`): three opponents, each with total `E` and an optional 🔥 bonus.
   Skip `E` > 30k (> 10k right after a free streak restore). Pick the highest bonus, with lower `E` breaking
   ties. Tap the panel, then CONTINUE. If none qualify, stop. REFRESH is an ad, never tap it.
2. **Team** (`033`, `041`): use the lobby `E` (the team page can misread it; take the larger).
   The cost per fighter is the ⚡ count above FIGHT. Fighters with fewer bolts than the cost are skipped.
   - `E` ≤ 5k: one anchor at 0.8–1.5x `E` (up to 2x when `E` ≤ 3k).
   - `E` > 5k: two anchors at 0.4–0.75x `E` each (0.6–0.9x each above 15k, about 1.2–1.8x together).
   - Anchors are never below 1400 (most golds sit under it, so a weaker anchor is never worth the scroll).
   - Anchor search narrows by tier and direction: from 1400 gold only, **descending** (few golds are strong,
     so the strong end is quick to reach); from 9k diamond only, descending. Take the first fighter in range.
   - Fillers: the cheapest gold+ fighters that meet the requirements, ascending, placed on the **left**.
     Anchors go on the right, strongest at the front.
   - Base filter for the mode is gold + diamond (filters are inclusive, so this hides bronze and silver).
     Reset to it before FIGHT. The filter dialog is only opened when its tiles or the sort must change.
   - No anchor with enough energy: stop and report.
3. **Energy Refill popup** (`035`): tap ✕, rebuild demanding one more bolt.
4. **Defeat** (`037`, `038`): no rematch, CONTINUE. **Keep Streak** (`039`): tap CONFIRM only if it says
   FREE (it OCRs as "FREFI"). If it costs gems, tap ✕. Never WATCH AD.
