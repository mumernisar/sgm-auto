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

    def handler(self, screen):
        return getattr(self, screen, None)

    def lives(self):
        """Tries left on the current fight, shown on the [fight] line ('' = no rematches in this mode)."""
        return ""

    def fight(self):
        state = r.auto_state(self.ctx.img)
        if state == "off":
            m = v.find(self.ctx.img, "auto_brain", (1150, 1380, 260, 220), 0.7)
            self.ctx.tap(*m.center, "auto battle on", jitter=6)
            self.ctx.log("  auto battle turned on")

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

    # finger swipes that show more of the map in one direction
    SHOW = {"below": ((1280, 1150), (1280, 550)), "above": ((1280, 450), (1280, 1250)),
            "right": ((1900, 800), (700, 800)), "left": ((700, 800), (1900, 800))}
    # when nothing playable is visible: walk the 8 views around the start (below, below-right, right, ...)
    PANS = ["below", "right", "above", "above", "left", "left", "below", "below"]

    @staticmethod
    def _at_edge(node):
        x, y = node.center
        return y > 1230 or y < 300 or x < 260 or x > 2300

    def event_map(self):
        c = self.ctx
        self.retreat = False
        node = state = None
        zoomed_out = pans = edge_pans = followed = 0
        while True:
            state = eventmap.read(c.img)
            if not state.nodes:
                raise Stop("couldn't read the event map (zoom it so the node numbers are readable)")
            # best first: a node with a visible line; the boss ends the chapter (the game moves on to the next
            # one), so every other node comes first
            node = eventmap.choose(state, self.bad, boss=False, guess=False)
            # maps open zoomed in: before anything else, zoom out (twice at most, not below ~0.6)
            if not node and zoomed_out < 2 and state.scale > 0.65:
                zoomed_out += 1
                c.log(f"  nothing playable in view at zoom {state.scale} -> zooming out")
                self.ctx.dev.pinch((1280, 800), 1200, 350, why="zoom out")
                c.settle(1.0)
                continue
            searched = pans == len(self.PANS)
            if not node:  # the node next to the marker (its line is often hidden under the marker)
                node = eventmap.choose(state, self.bad, boss=False)
            if not node:
                boss = eventmap.choose(state, self.bad)
                # take the boss once nothing else is left in view, or the search below found nothing else.
                # A boss that's only the marker guess (no line seen) waits for the search: a blue line running
                # off screen usually leads to an unfinished node first
                if boss and (searched or (not boss.guess and not eventmap.unfinished(state, self.bad, boss=False))):
                    c.log("  only the boss is left -> fighting it")
                    node = boss
            # a playable node at the screen edge (under the header, number hidden, hard to tap): drag the
            # map so it moves toward the centre — the swipe starts mid-map, a swipe on the header does nothing
            if node and self._at_edge(node) and edge_pans < 2:
                edge_pans += 1
                x, y = node.center
                dx, dy = int((1280 - x) * 0.7), int((800 - y) * 0.7)
                c.swipe((1280 - dx // 2, 800 - dy // 2), (1280 + dx // 2, 800 + dy // 2), 700, "pan node into view")
                c.look()
                continue
            if node or searched:
                break
            # a blue (playable) path running off the screen points the way: follow it before the fixed walk
            if state.exits and followed < 3:
                way, followed = state.exits[0], followed + 1
            else:
                way, pans = self.PANS[pans], pans + 1
            c.log(f"  nothing playable in view -> panning the map ({way})")
            c.swipe(*self.SHOW[way], 700, f"pan map: show {way}")
            c.look()
            if c.screen != "event_map":
                return  # a pan can open something; let the main loop handle it
        summary = ", ".join(f"{n.score if n.score is not None else '???'}{'*' if n.reachable else ''}"
                            f"{' (boss)' if eventmap.is_boss(state, n) else ''}"
                            for n in state.nodes if not n.cleared)
        c.log(f"map (zoom {state.scale}): {summary}  (* = reachable)")
        if not node:
            raise Stop("no usable node left on this map (looked around by panning)")
        self.node, self.node_losses, self.counted, self.built = node.center, 0, False, False
        c.tap(*node.center, f"node {node.score if node.score is not None else '???'}")
        # every tap counts until a pre-fight screen opens (which resets it): a tap that only opens the node's
        # FIGHT MODIFIERS popup (closed by the main loop) must not retry the same node forever
        self.map_taps = getattr(self, "map_taps", 0) + 1
        opened = c.wait_change("event_map", timeout=4)
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
        self.counted, self.map_taps = False, 0
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
                self.bad, self.retreat = [], False  # new map / area
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
                self.bad, self.retreat = [], False
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
                self.bad, self.retreat = [], False
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

    def prize_team(self):
        c = self.ctx
        if not self.built:
            if c.settle(1.2) not in ("prize_team", "team_picker"):
                return
            mine, page_enemy = r.team_scores(c.img)
            # the lobby number is the one we chose by; if the team page disagrees, be safe and use the larger
            enemy = max(x for x in (self.enemy, page_enemy, 0) if x is not None) or None
            if self.enemy and page_enemy and page_enemy != self.enemy:
                c.log(f"  ! team page shows enemy {page_enemy}, lobby said {self.enemy} -> using {enemy}")
            if enemy is None:
                raise Stop("can't read the enemy team total")
            # keep the highest cost seen for this opponent (a partly hidden plate can under-count)
            self.cost = max(r.fight_energy_cost(c.img) or 4, self.cost or 0) + self.refill_hits
            reqs = r.requirements(c.img)
            c.log(f"team page: mine {mine} vs {enemy}, cost {self.cost}, requirements: "
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

    def back(self, why):
        self.current.back(why)
