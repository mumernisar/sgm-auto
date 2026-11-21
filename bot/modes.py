"""What to do on each screen, per mode. Each handler acts once; the main loop looks again afterwards."""
import re

from . import eventmap
from . import readers as r
from . import team
from . import vision as v
from .core import Stop

BACK = (24, 24, 112, 112)
BOTTOM_BUTTONS = (0, 1280, 2560, 200)


class Common:
    """Screens that behave the same in both modes."""

    def __init__(self, ctx):
        self.ctx = ctx
        self.filt = team.Filter(ctx)
        self.wins = self.losses = 0
        self.auto_seen = None     # auto battle state last logged in this fight
        self.auto_taps = 0        # brain taps in this fight

    def handler(self, screen):
        if screen != "fight":
            self.auto_seen, self.auto_taps = None, 0
        return getattr(self, screen, None)

    def forget_step(self):
        """After a pause (the user may have played meanwhile): drop what's remembered about the screen in front.
        Kept: wins / losses, nodes given up on, which result is already counted."""
        self.auto_seen, self.auto_taps = None, 0
        self.filt.forget()

    def lives(self):
        """Tries left on the current fight, shown on the [fight] line ('' = no rematches in this mode)."""
        return ""

    def fight(self):
        """Keep auto battle on at cfg.auto_speed: off -> tap the brain; on at another speed -> tap the speed
        badge (it steps 1x / 2x / 3x). Read again on the next look; up to 4 taps per fight."""
        c = self.ctx
        state, want = r.auto_state(c.img), c.cfg.auto_speed
        if state != self.auto_seen:
            self.auto_seen = state
            c.log(f"  auto battle: {state or 'button not visible'}")
        if state is None or state == want:
            return
        if self.auto_taps >= 4:
            if self.auto_taps == 4:
                self.auto_taps += 1
                c.log(f"  ! auto battle stays at {state} after 4 taps (want {want}) -- leaving it")
            return
        self.auto_taps += 1
        if state == "off":
            c.tap(*r.AUTO_BRAIN, "auto battle on", jitter=6)
        else:
            c.tap(*r.AUTO_BADGE, f"auto speed {state} -> {want}", jitter=6)

    def offer(self):
        """Shop offer popup: tap its ✕ — never GET NOW."""
        c = self.ctx
        if not c.tap_template("offer_close", (1500, 0, 1060, 900), 0.7, why="close offer (never buy)"):
            raise Stop("an offer popup is showing but its close button wasn't found — close it by hand")

    def modifiers(self):
        """FIGHT MODIFIERS info popup (opens over the map from a node's skull badge): just close it."""
        if not self.ctx.tap_template("modifiers_close", (2000, 100, 400, 400), 0.7, why="close fight modifiers"):
            raise Stop("a fight modifiers popup is showing but its close button wasn't found")

    def cutscene(self):
        self.ctx.tap_template("skip_btn", (1050, 1300, 460, 240), why="skip story")

    def paused(self):
        self.ctx.tap_template("resume_btn", (1300, 1250, 700, 220), why="resume (never quit)")

    def moves_popup(self):
        self.ctx.tap_template("moves_popup_fight", (1250, 980, 500, 260), why="fight anyway (never equip)")

    def back(self, why):
        self.ctx.tap_template("back_arrow", BACK, 0.7, why=why)

    def gifts_full(self):
        """'Maximum number of Gifts reached!' over a VICTORY screen: OK only closes it (gifts are never sent)."""
        if not self.ctx.tap_template("gifts_ok", (1000, 1050, 560, 260), 0.7, why="OK (gift inbox full)"):
            raise Stop("a 'maximum number of gifts' popup is showing but its OK button wasn't found")

    def continue_(self):
        return self.ctx.tap_template("continue_btn", BOTTOM_BUTTONS, why="continue")


class EventMode(Common):
    def __init__(self, ctx):
        super().__init__(ctx)
        self.node = None          # node we tapped (map coordinates)
        self.node_losses = 0
        self.bad = []             # nodes we gave up on
        self.retreat = False      # walk back to the map from the pre-fight screen
        self.counted = False      # result of the current match already counted
        self.built = False        # team already built for the current node
        self.swept = False        # a full sweep of this map found nothing but the boss (kept across retries)
        self.zoom = None          # map zoom of the last read: the next read only confirms it (fully zoomed out is
                                  # the same zoom every time; cleared on a new map and after a pause)
        self.seen = None          # (frame, Ctx.changes, state) of the last map read, reused while nothing moved
        self.zoomed_at = None     # Ctx.changes when the map was last zoomed fully out (redo once a screen came up)

    # finger swipes that show more of the map in one direction
    SHOW = {"below": ((1280, 1150), (1280, 550)), "above": ((1280, 450), (1280, 1250)),
            "right": ((1900, 800), (700, 800)), "left": ((700, 800), (1900, 800))}
    # search sweep when nothing playable is visible: big swipes up to the map's edge, then left, down, right and
    # up again (around the map's border), each direction until the map stops moving
    SWEEP = {"above": ((1280, 380), (1280, 1380)), "below": ((1280, 1380), (1280, 380)),
             "left": ((450, 800), (2150, 800)), "right": ((2150, 800), (450, 800))}
    SWEEP_ORDER = ("above", "left", "below", "right", "above")
    SWEEP_STEPS = 3   # swipes per direction at most
    STILL = 3.0       # a pan that changes less than this % of pixels hit the map's edge (edge bounce < 1.8%)

    def forget_step(self):
        super().forget_step()
        self.zoom, self.swept, self.map_taps, self.seen = None, False, 0, None  # the map may have been moved
        self.zoomed_at = None  # or zoomed
        self.built, self.retreat = False, False  # the team may have changed: FIGHT is checked again

    def _zoom_out(self, why):
        """One pinch out. False if it left the map (the main loop handles what came up). The remembered zoom is
        kept: it's the hint for the next read, and fully zoomed out is the same zoom every time."""
        c = self.ctx
        c.dev.pinch((1280, 800), 1200, 350, why=why)
        self.seen = None
        c.settle(1.0)
        self.zoomed_at = c.changes
        return c.screen == "event_map"

    def _read_map(self, zoom):
        """The map in view. The last read is reused while the view hasn't moved (a pan at the map's edge, a tap
        that opened nothing) and no other screen came up since: after a fight only a ✓ differs, well under STILL."""
        c = self.ctx
        if self.seen:
            frame, changes, state = self.seen
            if changes == c.changes and frame.shape == c.raw.shape and v.changed(frame, c.raw) < self.STILL:
                return state
        state = eventmap.read(c.raw, zoom, hint=self.zoom)
        self.seen = (c.raw, c.changes, state)
        return state

    @staticmethod
    def _at_edge(node):
        x, y = node.center
        return y > 1230 or y < 300 or x < 260 or x > 2300

    def event_map(self):
        c = self.ctx
        self.retreat = False
        node = state = None
        pinches = edge_pans = followed = leg = steps = 0
        searched = self.swept  # one full sweep found nothing but the boss: it may be fought now
        zoom = None       # map zoom, fixed once fully zoomed out (pans don't change it)
        # the game resets the map's zoom whenever it's left: zoom fully out first, every time (more of the map in
        # view, one known zoom; a read at the map's own zoom first was mostly wasted)
        if self.zoomed_at != c.changes and not self._zoom_out("zoom out fully"):
            return
        while True:
            state = self._read_map(zoom)
            if state.nodes:
                self.zoom = state.scale
            if not state.nodes and not zoom:  # (mid-sweep, a view can show no nodes at all)
                raise Stop("couldn't read the event map (zoom it so the node numbers are readable)")
            if not zoom:
                if state.scale > eventmap.FLOOR and pinches < 2:  # zoomed in further (~1.6 after a game restart)
                    pinches += 1
                    if not self._zoom_out(f"zoom {state.scale}: zoom out further"):
                        return
                    continue
                zoom = state.scale
            # best first: a node with a visible line; the boss ends the chapter (the game moves on to the next
            # one), so every other node comes first
            node = eventmap.choose(state, self.bad, boss=False, guess=False)
            if not node:  # the node next to the marker (its line is often hidden under the marker)
                node = eventmap.choose(state, self.bad, boss=False)
            if not node and searched:
                node = eventmap.choose(state, self.bad)
                if node:
                    self.swept = True
                    c.log("  the sweep found nothing but the boss -> fighting it")
            # a playable node at the screen edge (under the header, number hidden, hard to tap): drag the
            # map so it moves toward the centre — the swipe starts mid-map, a swipe on the header does nothing
            if node and self._at_edge(node) and edge_pans < 2:
                edge_pans += 1
                x, y = node.center
                dx, dy = int((1280 - x) * 0.7), int((800 - y) * 0.7)
                before = c.raw
                c.swipe((1280 - dx // 2, 800 - dy // 2), (1280 + dx // 2, 800 + dy // 2), 700, "pan node into view")
                c.look()
                if c.screen != "event_map":
                    return
                if v.changed(before, c.raw) < self.STILL:  # at the map's edge: another pan won't move it either
                    c.log("  the map doesn't move that way -> tapping the node where it is")
                    edge_pans = 2
                continue
            if node:
                break
            if leg == len(self.SWEEP_ORDER):
                if searched:  # second sweep, boss allowed: nothing at all
                    break
                # the whole map was swept without another playable node (the rest are locked): sweep again,
                # this time taking the boss wherever it shows up
                c.log("  the sweep found no other playable node -> looking for the boss")
                searched, leg, steps = True, 0, 0
                continue
            zoom = zoom or state.scale
            # a blue (playable) path running off the screen points the way: follow it before the sweep (not
            # during it: that pulls the map back and forth against the sweep)
            follow = bool(state.exits) and followed < 3 and not (leg or steps or searched)
            if follow:
                way, followed = state.exits[0], followed + 1
            else:
                way, steps = self.SWEEP_ORDER[leg], steps + 1
            c.log(f"  nothing playable in view -> panning the map ({way})")
            before = c.raw
            c.swipe(*(self.SHOW if follow else self.SWEEP)[way], 700, f"pan map: show {way}")
            c.look()
            if c.screen != "event_map":
                return  # a pan can open something; let the main loop handle it
            if v.changed(before, c.raw) < self.STILL:
                c.log(f"  the map doesn't move further {way}")
                if follow:
                    followed = 3  # the line's end is in view already: stop following it
                else:
                    leg, steps = leg + 1, 0
            elif not follow and steps >= self.SWEEP_STEPS:
                leg, steps = leg + 1, 0
        left = [n for n in state.nodes if not n.cleared]
        c.log(f"map (zoom {state.scale}): {len(left)} not cleared, {sum(n.reachable for n in left)} open"
              + (", boss in view" if any(eventmap.is_boss(state, n) for n in left) else ""))
        if not node:
            raise Stop("no usable node left on this map (looked around by panning)")
        self.node, self.node_losses, self.counted, self.built = node.center, 0, False, False
        # every tap counts until a pre-fight screen opens (which resets it): a tap that only opens the node's
        # FIGHT MODIFIERS popup (closed by the main loop) must not retry the same node forever
        self.map_taps = getattr(self, "map_taps", 0) + 1
        # the game swallows the first tap after the map was swiped (even seconds later), so a tap that opens
        # nothing is repeated once right away
        for attempt in range(2):
            c.tap(*node.center, ("boss node" if eventmap.is_boss(state, node) else "node")
                  + (" (guess)" if node.guess else "") + (" (again)" if attempt else ""))
            opened = c.wait_change("event_map", timeout=4)
            if opened:
                break
        if opened and opened != "modifiers":
            return
        # a guessed node (no line seen) is given up on sooner: it's often just not playable yet
        give_up = 2 if node.guess else 6
        if self.map_taps >= give_up:
            c.log(f"  node won't open after {give_up} taps -> skipping it")
            self.bad.append(node.center)
            self.map_taps = 0
        elif self.map_taps >= 3:  # move it a little: something may be covering it (vary the direction)
            way = ("below", "above", "right", "left")[(self.map_taps - 3) % 4]
            a, b = self.SHOW[way]
            c.swipe(a, ((a[0] + b[0]) // 2, (a[1] + b[1]) // 2), 700, f"pan: node tap isn't opening ({way})")

    def lives(self):
        """'+' per rematch try left on this node, '✗' per loss: '+++', '++✗', '+✗✗'."""
        lost = min(self.node_losses, self.ctx.cfg.max_event_losses)
        return "+" * (self.ctx.cfg.max_event_losses - lost) + "✗" * lost

    def event_prefight(self):
        c = self.ctx
        if self.retreat:
            self.back("back to map")
            return
        self.counted, self.map_taps, self.swept = False, 0, False
        if c.settle(1.2) not in ("event_prefight", "team_picker"):
            return  # moved on while settling; the main loop will handle the new screen
        reqs = r.requirements(c.img)
        if reqs:
            c.log("  requirements: " + ", ".join(
                f"{'NOT ' if q.excluded else ''}{q.value}{'' if q.count is None else ' x' + str(q.count)}" for q in reqs))
        # only touch the team when a requirement is unmet (FIGHT greyed out)
        if not self.built and not r.fight_enabled(c.img):
            variants = self.read_variants(reqs)
            ok = team.build_event_team(c, self.filt, reqs, variants)
            if not ok:
                c.log("  can't meet this node's requirements -> back to map")
                self.bad.append(self.node)
                self.retreat = True
                self.back("back to pre-fight")
                return
        self.built = True
        c.look()
        if c.tap_template("fight_btn", (2050, 40, 480, 200), 0.7, why="FIGHT"):
            c.wait_change(("event_prefight", "team_picker"))

    team_picker = event_prefight  # interrupted mid-build: same decision again

    def event_list(self):
        """Events / origin stories list (after a map's boss). Keep playing the shown difficulty until it is 100%,
        then step to the next one with '›'."""
        c = self.ctx
        for _ in range(5):
            c.settle(0.8)
            card = r.list_card(c.img)
            for _ in range(3):  # not centred yet: the list may still be sliding
                if card or c.screen != "event_list":
                    break
                c.settle(1.0)
                card = r.list_card(c.img)
            if c.screen != "event_list":
                return
            if not card:
                raise Stop("events list: can't find the selected card's PLAY button")
            c.log(f"  list: {card.percent}% {'playable' if card.playable else 'not playable'}")
            if card.playable and (card.percent is None or card.percent < 100):
                self.bad, self.retreat, self.swept, self.zoom = [], False, False, None  # new map / area
                c.tap(*card.play, "PLAY")
                c.wait_change("event_list")
                return
            if not card.next_arrow:
                break
            c.tap(*card.next_arrow, "next difficulty", jitter=6)
        raise Stop(f"no playable difficulty left on this event ({self.wins} wins, {self.losses} losses)")

    def event_areas(self):
        """Area overview of a story event: open the current area (gold chevron) unless it's done, else any
        area below 100% (pan to look); all done -> back to the list, which moves on to the next difficulty."""
        c = self.ctx
        pans = [((1900, 800), (700, 800)), ((700, 800), (1900, 800)), ((700, 800), (1900, 800)),
                ((1900, 800), (700, 800))]
        for attempt in range(len(pans) + 1):
            c.settle(0.6)
            found = r.areas(c.img)
            c.log("  areas: " + (", ".join(f"{a.percent}%{'*' if a.current else ''}" for a in found) or "none readable"))
            current = next((a for a in found if a.current), None)
            if current and r.chapter_arrows(c.img, current) != {"prev": None, "next": None}:
                if self.open_chapter(current):
                    return
                found = [a for a in r.areas(c.img) if not a.current]  # every chapter is done
            todo = sorted((a for a in found if a.percent < 100), key=lambda a: not a.current)
            if todo:
                self.bad, self.retreat, self.swept, self.zoom = [], False, False, None
                c.tap(*todo[0].tap, f"open area {todo[0].percent}%")
                c.wait_change("event_areas")
                return
            if attempt < len(pans):
                c.swipe(*pans[attempt], 700, "pan areas")
        c.log("  every area is at 100% -> back to the list")
        self.back("areas done")

    def _chapter_panel(self):
        """(current area, its chapter arrows) once the panel has stopped sliding: after an arrow tap the panel
        and camera move for a moment and an arrow can be missed, so two reads in a row must agree."""
        c = self.ctx
        last = None
        for _ in range(5):
            c.settle(0.6)
            area = next((a for a in r.areas(c.img) if a.current), None)
            arrows = r.chapter_arrows(c.img, area) if area else {"prev": None, "next": None}
            key = (area and area.percent, area and area.tap[0] // 40, bool(arrows["prev"]), bool(arrows["next"]))
            if key == last:
                break
            last = key
        return area, arrows

    def open_chapter(self, area):
        """An area with « CHAPTER N » arrows: finish its chapters in order. After a boss the game jumps to the
        newly unlocked chapter even if the earlier one isn't at 100%, so step « back to chapter 1, then »
        forward to the first chapter below 100% and open it. False if every chapter is done."""
        c = self.ctx
        area, arrows = self._chapter_panel()
        for _ in range(12):
            if not area or not arrows["prev"]:
                break
            c.tap(*arrows["prev"], "previous chapter", jitter=6)
            area, arrows = self._chapter_panel()
        for _ in range(12):
            if not area:  # locked chapter (padlock, no %)
                return False
            c.log(f"  chapter: {area.percent}%")
            if area.percent < 100:
                self.bad, self.retreat, self.swept, self.zoom = [], False, False, None
                c.tap(*area.tap, f"open chapter {area.percent}%")
                c.wait_change("event_areas")
                return True
            if not arrows["next"]:
                return False
            c.tap(*arrows["next"], "next chapter", jitter=6)
            area, arrows = self._chapter_panel()
        return False

    def read_variants(self, reqs):
        """Tap each character requirement and read its tooltip (it closes by itself after ~4s, so capture
        right away). 'NEED <name> VARIANT' means that exact fighter. Returns {character: variant name}."""
        c = self.ctx
        found = {}
        for q in reqs:
            if q.excluded or q.kind != "character":
                continue
            c.tap(*q.center, f"read requirement {q.value}", jitter=4)
            c.settle(0.4)
            text = r.tooltip_text(c.img)
            c.log(f"  tooltip: {text!r}")
            name = r.variant_from_tooltip(text)
            if name:
                found[q.value] = name
        return found

    def filter(self):
        self.filt.close()

    def victory(self):
        if not self.counted:
            self.counted = True
            self.wins += 1
            self.ctx.log(f"VICTORY (wins {self.wins}, losses {self.losses})")
        self.continue_()

    def defeat(self):
        c = self.ctx
        if not self.counted:
            self.counted = True
            self.losses += 1
            self.node_losses += 1
            c.log(f"DEFEAT {self.node_losses}/{c.cfg.max_event_losses} on this node")
        if self.node_losses < c.cfg.max_event_losses and v.find(c.img, "rematch_btn", BOTTOM_BUTTONS, 0.75):
            self.counted = False
            c.tap_template("rematch_btn", BOTTOM_BUTTONS, why="rematch")
        elif v.find(c.img, "quit_btn", BOTTOM_BUTTONS, 0.75):
            self.bad.append(self.node)
            self.retreat = True
            c.tap_template("quit_btn", BOTTOM_BUTTONS, why="quit after losses")
        else:
            self.continue_()


class PrizeMode(Common):
    def __init__(self, ctx):
        super().__init__(ctx)
        self.restored = False     # free streak restore just used -> stricter opponent cap
        self.enemy = None
        self.counted = False
        self.refill_hits = 0
        self.built = False        # team already built for the current opponent
        self.cost = None          # energy cost per fighter for the current opponent

    def forget_step(self):
        super().forget_step()
        self.built = False  # the team may have changed: built again (the energy cost seen is kept)

    def keep_streak(self):
        c = self.ctx
        import pytesseract
        sub, _, _ = v._crop(c.img, (1430, 960, 240, 80))  # bottom line of the green CONFIRM button
        txt = pytesseract.image_to_string(v._white_text(sub), config="--psm 7").upper()
        if re.search(r"F\s*R", txt) and not re.search(r"\d", txt):  # stylised 'FREE!' reads as FREFI; paid shows '25'
            self.restored = True
            c.tap(1500, 965, "keep streak (free)")
        else:
            c.log(f"  keep streak costs gems ({txt!r}) -> close")
            c.tap_template("keep_streak_close", (1820, 400, 220, 220), why="decline paid streak restore")

    def energy_refill(self):
        c = self.ctx
        self.refill_hits += 1
        if self.refill_hits > 2:
            raise Stop("energy refill popup keeps appearing — energy reading is off, check logs/debug")
        c.tap_template("popup_close", (1780, 450, 220, 220), why="close refill (never spend/ads)")
        self.built = False  # rebuild, demanding one more bolt of energy each time this happens

    def prize_lobby(self):
        c = self.ctx
        cap = c.cfg.restored_max_enemy_total if self.restored else c.cfg.max_enemy_total
        opps = r.lobby_opponents(c.img)
        c.log("lobby: " + ", ".join(f"{o.total}{' x' + str(o.multiplier) if o.multiplier > 1 else ''}" for o in opps)
              + f"  (cap {cap})")
        ok = [o for o in opps if o.total is not None and o.total <= cap]
        if not ok:
            raise Stop(f"no opponent at or under {cap}" + (" after the free streak restore" if self.restored else ""))
        pick = max(ok, key=lambda o: (o.multiplier, -o.total))
        self.enemy, self.restored, self.counted, self.refill_hits = pick.total, False, False, 0
        self.built, self.cost = False, None
        c.tap(*pick.tap, f"opponent {pick.total} x{pick.multiplier}")
        c.look()
        c.tap_template("lobby_continue", (2000, 40, 560, 200), 0.7, why="continue to team")

    def _page_enemy(self):
        """The team page's enemy total once two reads in a row agree: it can still be changing as the page opens
        (read once as 163 for 1,763, S23). None if it never settles: the lobby's number is used then."""
        c = self.ctx
        last = r.enemy_total(c.img)
        for _ in range(3):
            if c.settle(0.5) not in ("prize_team", "team_picker"):
                break
            now = r.enemy_total(c.img)
            if now == last:
                return now
            last = now
        return None

    def prize_team(self):
        c = self.ctx
        if not self.built:
            if c.settle(1.2) not in ("prize_team", "team_picker"):
                return
            page_enemy = self._page_enemy()
            # the lobby number is the one we chose by; if the team page disagrees, be safe and use the larger
            enemy = max(x for x in (self.enemy, page_enemy, 0) if x is not None) or None
            if self.enemy and page_enemy and page_enemy != self.enemy:
                c.log(f"  ! team page shows enemy {page_enemy}, lobby said {self.enemy} -> using {enemy}")
            if enemy is None:
                raise Stop("can't read the enemy team total")
            # keep the highest cost seen for this opponent (a partly hidden plate can under-count)
            self.cost = max(r.fight_energy_cost(c.img) or 4, self.cost or 0) + self.refill_hits
            reqs = r.requirements(c.img)
            c.log(f"team page: enemy {enemy}, cost {self.cost}, requirements: "
                  + (", ".join(f"{'NOT ' if q.excluded else ''}{q.value}{'' if q.count is None else ' x' + str(q.count)}"
                               for q in reqs) or "none"))
            if not team.build_prize_team(c, self.filt, reqs, enemy, self.cost):
                raise Stop("couldn't build a team with enough energy for this opponent — see log")
            self.built = True
        c.look()
        if c.tap_template("fight_btn", (2050, 40, 480, 200), 0.7, why="FIGHT"):
            c.wait_change(("prize_team", "team_picker"))

    team_picker = prize_team

    def filter(self):
        self.filt.close()

    def victory(self):
        if not self.counted:
            self.counted = True
            self.wins += 1
            self.ctx.log(f"VICTORY (wins {self.wins}, losses {self.losses})")
        self.continue_()

    def defeat(self):
        if not self.counted:
            self.counted = True
            self.losses += 1
            self.ctx.log(f"DEFEAT (wins {self.wins}, losses {self.losses}) — streak reset")
        self.continue_()


class AutoMode:
    """Works out event vs prize handling from the screen itself.

    Screens unique to one mode switch to it; shared screens (fight, victory, team picker, popups) stay with the
    mode seen last. A defeat with a REMATCH button can only be an event fight.
    """
    PRIZE = {"prize_lobby", "prize_team", "keep_streak", "energy_refill"}  # shared screens keep the mode
    EVENT = {"event_map", "event_prefight", "event_list", "event_areas", "cutscene"}

    def __init__(self, ctx):
        self.ctx = ctx
        self.event = EventMode(ctx)
        self.prize = PrizeMode(ctx)
        self.prize.filt = self.event.filt  # one real filter dialog, so one tracked state
        self.current = self.event

    @property
    def wins(self):
        return self.event.wins + self.prize.wins

    @property
    def losses(self):
        return self.event.losses + self.prize.losses

    def handler(self, screen):
        before = self.current
        if screen in self.PRIZE:
            self.current = self.prize
        elif screen in self.EVENT:
            self.current = self.event
        elif screen == "defeat" and v.find(self.ctx.img, "rematch_btn", BOTTOM_BUTTONS, 0.75):
            self.current = self.event
        if self.current is not before:
            self.ctx.log(f"  mode: {'prize fights' if self.current is self.prize else 'event'}")
        return self.current.handler(screen)

    def lives(self):
        return self.current.lives()

    def forget_step(self):
        self.event.forget_step()
        self.prize.forget_step()

    def back(self, why):
        self.current.back(why)
