"""Filter dialog control and team building for both modes."""
from dataclasses import dataclass, field

import cv2
import numpy as np

from . import readers as r
from . import vision as v
from .core import Stop

# --- filter dialog layout (full-res) ----------------------------------------------------------------

COLS = [400, 590, 782, 974, 1166, 1360]
UNSCROLLED = {**{name: (COLS[i], 544) for i, name in enumerate(r.RARITIES)},
              **{name: (COLS[i], 820) for i, name in enumerate(r.ELEMENTS)}}
SCROLLED = {**{name: (COLS[i % 6], (870, 1060, 1256)[i // 6]) for i, name in enumerate(r.CHARACTERS)}}
SORT_ARROW_REGION = (1870, 460, 130, 130)
SORT_RADIO = (2340, 524)
FILTER_BTN = (2460, 873)  # funnel on the team picker
SELECTED_V = 75  # tile corner brightness above this = selected

PICKER_SWIPE_Y = 1250
CARDS_START_X = 111  # first card's icon x when the list is scrolled to the start


@dataclass
class Unit:
    """Constraint for one team slot: tiles to select in the filter, characters to skip."""
    tiles: set = field(default_factory=set)
    skip_characters: set = field(default_factory=set)


class Filter:
    def __init__(self, ctx):
        self.ctx = ctx
        self.state = None      # dict tile -> selected, once read
        self.ascending = None  # sort direction, once confirmed

    def open(self):
        c = self.ctx
        if c.look() == "filter":
            return
        for attempt in range(3):
            if c.screen == "filter":  # opened late (after wait_for gave up)
                break
            if c.screen != "team_picker":
                c.settle(0.8)
                continue
            # the funnel always sits at the same spot on the picker; its background varies per arena
            # (blue glow, gold wood), so a fixed tap is more reliable than matching it
            c.tap(*FILTER_BTN, "filter button", jitter=6)
            if c.wait_for("filter", 4):
                break
        else:
            raise Stop(f"filter dialog didn't open (screen: {c.screen})")
        c.settle(0.6)
        if self.state is None:  # first time this run: clear whatever was left selected from before
            if c.tap_template("filter_clear", (100, 150, 1100, 260), 0.6, why="clear leftover filter"):
                c.look()
                self._scroll(down=False)

    def close(self):
        c = self.ctx
        if c.look() == "filter":
            c.tap_template("filter_close", (2330, 130, 230, 230))
            c.wait_for("team_picker", 6)

    def _scrolled(self):
        m = v.find(self.ctx.img, "f_fire", (300, 480, 230, 460), 0.55)
        return m is not None and m.center[1] < 700

    def _scroll(self, down):
        if self._scrolled() != down:
            a, b = ((900, 1250), (900, 450)) if down else ((900, 450), (900, 1250))
            self.ctx.swipe(a, b, 700, "scroll filter " + ("down" if down else "up"))
            self.ctx.look()

    def _selected(self, pos):
        x, y = pos
        return v.hsv_mean(self.ctx.img, (x - 62, y - 62, 14, 14))[2] > SELECTED_V

    def _sync(self, layout, desired):
        for attempt in range(2):
            wrong = [n for n, p in layout.items() if self._selected(p) != (n in desired)]
            for n in wrong:
                self.ctx.tap(*layout[n], f"filter {'select' if n in desired else 'deselect'} {n}", jitter=8)
            self.ctx.look()
            if not wrong:
                break
        self.state = {**(self.state or {}), **{n: self._selected(p) for n, p in layout.items()}}

    def apply(self, desired, need_characters=None):
        """Make exactly `desired` tiles selected. Character tiles need a scroll, so they're only checked when
        a character is wanted or we don't yet know they're all off."""
        known = self.state is not None and all(t in self.state for t in list(UNSCROLLED) + list(SCROLLED))
        if known and {t for t, on in self.state.items() if on} == set(desired):
            return  # already set: don't open the dialog at all
        self.open()
        c = self.ctx
        c.look()
        self._scroll(down=False)
        self._sync(UNSCROLLED, desired)
        chars_wanted = {n for n in desired if n in SCROLLED}
        # read the character tiles once per run, so later calls with the same tiles can skip the dialog
        chars_known_off = (self.state is not None and all(n in self.state for n in SCROLLED)
                           and not any(self.state[n] for n in SCROLLED))
        if chars_wanted or not chars_known_off or need_characters:
            self._scroll(down=True)
            self._sync(SCROLLED, desired)
        c.log(f"  filter = {sorted(desired) or 'none'}")

    def sort(self, ascending):
        if self.ascending == ascending:
            return
        self.open()
        c = self.ctx
        for _ in range(3):
            c.look()
            up = v.find(c.img, "sort_up", SORT_ARROW_REGION, 0.0)
            down = v.find(c.img, "sort_down", SORT_ARROW_REGION, 0.0)
            # the two arrows look alike (each scores ~0.73 on the other), so compare them
            if up and down and max(up.score, down.score) > 0.85 and (up.score > down.score) == ascending:
                self.ascending = ascending
                return
            c.tap(*SORT_RADIO, f"sort {'ascending' if ascending else 'descending'}", jitter=6)
        c.log("  ! couldn't confirm sort direction")


# --- card list -----------------------------------------------------------------------------------

def rewind(ctx):
    """Scroll the card list back to its start."""
    for _ in range(8):
        cards = r.picker_cards(ctx.img, with_character=False)
        if not cards or abs(cards[0].icon[0] - CARDS_START_X) < 20:
            return
        ctx.swipe((300, PICKER_SWIPE_Y), (2450, PICKER_SWIPE_Y), 400, "rewind cards")
        ctx.look()


def scan(ctx, ok, ascending, prefer=None, stop=None, energy=False, characters=False, max_swipes=80,
         need_score=True):
    """Walk the card list a page at a time.

    Returns the first card that is ok() (and prefer(), if given). With stop(), scanning ends at the first card
    for which stop() is true and the last ok() card seen before it is returned instead (e.g. descending
    anchor search: nothing within the preferred range, so take the smallest one above it).
    """
    last = None  # (card, page)
    prev_strip = None
    for page in range(max_swipes):
        if ctx.look() != "team_picker":
            raise Stop(f"left the team picker while scanning ({ctx.screen})")
        # end of list = the card strip didn't move (scores alone repeat: many identical cheap cards)
        strip = cv2.resize(cv2.cvtColor(ctx.img[960:1560], cv2.COLOR_BGR2GRAY), (320, 75)).astype(np.int16)
        if prev_strip is not None and np.abs(strip - prev_strip).mean() < 4:
            break
        prev_strip = strip
        cards = r.drop_out_of_order(r.picker_cards(ctx.img, with_energy=energy, with_character=characters), ascending)
        for card in cards:
            if card.score is None and (need_score or stop):
                continue
            if stop and stop(card):
                if last is None:
                    return None
                card0, p0 = last
                if p0 != page:  # it scrolled off: step back a page and find it again
                    ctx.swipe((300, PICKER_SWIPE_Y), (2450, PICKER_SWIPE_Y), 900, "step back")
                    ctx.look()
                    again = [k for k in r.picker_cards(ctx.img, with_energy=energy, with_character=characters)
                             if k.score == card0.score]
                    return again[-1] if again else None
                return card0
            if ok(card):
                if prefer is None or prefer(card):
                    return card
                last = (card, page)
        ctx.swipe((2450, PICKER_SWIPE_Y), (300, PICKER_SWIPE_Y), 900, "next page")
    return last[0] if last else None


def slot_at(ctx, slots, i):
    """Slot i with a fresh score if it can be re-read now; positions come from the first read (they don't
    move, but a re-read right after a drag can miss a slot while cards animate)."""
    for s in r.team_slots(ctx.img):
        if abs(s.icon[0] - slots[i].icon[0]) < 40:
            return s
    return r.Slot(slots[i].icon, None, slots[i].element)


def place(ctx, card, slot, why):
    ctx.log(f"  {why}: {card.character or '?'} {card.element or '?'} {card.score} (energy {card.energy}) -> slot {slot.icon}")
    ctx.drag(card.center, slot.center, why)


# --- requirements -> per-slot constraints ----------------------------------------------------------

def constraints(reqs, base_rarities):
    """Split requirement icons into (universal tiles, per-slot units, characters to skip, rarities)."""
    universal, units, skip = set(), [], set()
    rarities = set(base_rarities)
    excluded_elements = set()
    for q in reqs:
        if q.kind == "unknown":
            raise Stop(f"unrecognised requirement icon at {q.center} (confidence {q.score:.2f})")
        if q.excluded:
            if q.kind == "character":
                skip.add(q.value)
            elif q.kind == "element":
                excluded_elements.add(q.value)
            else:
                rarities.discard(q.value)
            continue
        if q.count is None:
            universal.add(q.value)
        else:
            units += [q] * q.count
    if excluded_elements and not universal & set(r.ELEMENTS):
        universal |= set(r.ELEMENTS) - excluded_elements  # 'no Fire' = any of the other five
    # one slot can take one character requirement plus one element requirement
    chars = [q.value for q in units if q.kind == "character"]
    elems = [q.value for q in units if q.kind == "element"]
    rars = [q.value for q in units if q.kind == "rarity"]
    slot_units = []
    while chars or elems or rars:
        tiles = set()
        for pool in (chars, elems, rars):
            if pool:
                tiles.add(pool.pop(0))
        slot_units.append(tiles)
    return universal, slot_units, skip, rarities


def _tiles_for(universal, unit_tiles, rarities):
    tiles = set(universal) | set(unit_tiles) | set(rarities)
    # a slot's own element requirement replaces the 'any of these elements' set from an exclusion
    unit_elements = set(unit_tiles) & set(r.ELEMENTS)
    if unit_elements:
        tiles = (tiles - set(r.ELEMENTS)) | unit_elements
    if rarities == set(r.RARITIES):
        tiles -= set(r.RARITIES)  # all rarities = no rarity filter
    return tiles


def open_picker(ctx):
    if ctx.look() == "team_picker":
        return
    if not ctx.tap_template("team_btn", (1100, 1100, 360, 300)):
        raise Stop(f"TEAM button not found on {ctx.screen}")
    if not ctx.wait_for("team_picker", 8):
        raise Stop("team picker didn't open")
    ctx.settle(1.0)


# --- event mode ------------------------------------------------------------------------------------

def build_event_team(ctx, filt, reqs, variants=None):
    """Swap in fighters until the node's requirements are met (only called when FIGHT is greyed out).

    variants: {character: variant name} read from 'NEED <name> VARIANT' tooltips — that exact card is found
    by its name plate and put in the front slot (the rightmost, which fights first). Other requirements
    replace the weakest slots. Stops swapping as soon as FIGHT turns orange. Returns True when it did.
    """
    variants = dict(variants or {})
    universal, slot_units, skip, rarities = constraints(reqs, r.RARITIES)
    open_picker(ctx)
    slots = r.team_slots(ctx.img)
    if not slots:
        raise Stop("no team slots found on the picker")
    ctx.log(f"  event team: {len(slots)} slots, universal={sorted(universal)}, per-slot={slot_units}, "
            f"variants={variants}, skip={sorted(skip)}")
    if len(slot_units) > len(slots):
        ctx.log("  requirements need more slots than the team has")
        return False
    filt.sort(ascending=False)
    front = len(slots) - 1
    free = [i for i in sorted(range(len(slots)), key=lambda i: slots[i].score or 0)]  # weakest first
    # variant requirements first, so they claim the front slot
    slot_units.sort(key=lambda u: not any(t in variants for t in u))

    def done():
        ctx.look()
        return r.fight_enabled(ctx.img)

    enabled = False
    for unit_tiles in slot_units:
        name = next((variants.pop(t) for t in unit_tiles if t in variants), None)
        i = front if name and front in free else free[0]
        free.remove(i)
        filt.apply(_tiles_for(universal, unit_tiles, rarities))
        filt.close()
        ctx.look()
        rewind(ctx)
        if name:
            ok = lambda k: k.character not in skip and r.names_match(r.card_name(ctx.img, k), name)  # noqa: E731
        else:
            ok = lambda k: k.character not in skip  # noqa: E731
        card = scan(ctx, ok, ascending=False, characters=bool(skip), need_score=not name)
        if not card:
            ctx.log(f"  no fighter matches {name or unit_tiles}")
            return False
        place(ctx, card, slot_at(ctx, slots, i), f"requirement {name or ''}".strip())
        if done():
            enabled = True
            break

    # universal requirements / exclusions can still block: refill the other slots with eligible fighters
    if not enabled and free and (universal or skip):
        filt.apply(_tiles_for(universal, set(), rarities))
        filt.close()
        for i in list(free):
            ctx.look()
            rewind(ctx)
            card = scan(ctx, lambda k: k.character not in skip, ascending=False, characters=bool(skip))
            if card:
                place(ctx, card, slot_at(ctx, slots, i), "eligible")
            if done():
                enabled = True
                break
    if filt.state and any(filt.state.values()):  # event mode starts every match with a clean filter
        filt.apply(set())
        filt.close()
    return done()


# --- prize fights ----------------------------------------------------------------------------------

def anchor_targets(cfg, enemy):
    """Score ranges (lo, hi) for the anchor fighter(s): one anchor, or two for bigger enemy teams."""
    if enemy > cfg.pair_above:
        a, b = cfg.big_pair_range if enemy > cfg.big_total else cfg.pair_range
        ranges = [(a * enemy, b * enemy)] * 2
    else:
        top = cfg.small_total_max if enemy <= cfg.small_total else cfg.anchor_range[1]
        ranges = [(cfg.anchor_range[0] * enemy, top * enemy)]
    floor = cfg.anchor_min
    return [(max(lo, floor), max(hi, floor)) for lo, hi in ranges]


def anchor_search(cfg, lo):
    """Rarities to filter and sort direction that reach a fighter of score >= lo quickly."""
    rarities, ascending = cfg.anchor_search[0][1], cfg.anchor_search[0][2]
    for min_lo, rar, asc in cfg.anchor_search:
        if lo >= min_lo:
            rarities, ascending = rar, asc
    return set(rarities), ascending


def build_prize_team(ctx, filt, reqs, enemy, cost):
    """Anchor(s) at ~0.8-1.5x the enemy total, cheapest eligible fillers, everyone with enough energy."""
    cfg = ctx.cfg
    universal, slot_units, skip, rarities = constraints(reqs, cfg.base_rarities)
    open_picker(ctx)
    slots = r.team_slots(ctx.img)
    if not slots:
        raise Stop("no team slots found on the picker")
    targets = anchor_targets(cfg, enemy)[:max(1, len(slots) - 1)]
    fillers = len(slots) - len(targets)
    ctx.log(f"  prize team: enemy {enemy}, anchors {[f'{a:.0f}-{b:.0f}' for a, b in targets]}, cost {cost}, "
            f"per-slot={slot_units}, universal={sorted(universal)}, skip={sorted(skip)}")
    anchor_units = [set() for _ in targets]
    for i in range(len(anchor_units)):  # more requirements than fillers: anchors take the rest
        if len(slot_units) > fillers:
            anchor_units[i] = slot_units.pop()
    if len(slot_units) > fillers:
        ctx.log("  requirements need more slots than the team has")
        return False
    has_energy = lambda k: k.energy is None or k.energy >= cost  # noqa: E731
    usable = lambda k: k.character not in skip and has_energy(k)  # noqa: E731

    # fillers first (cheapest eligible, ascending) -> the last slots
    for n in range(fillers):
        unit_tiles = slot_units[n] if n < len(slot_units) else set()
        filt.sort(ascending=True)
        filt.apply(_tiles_for(universal, unit_tiles, rarities))
        filt.close()
        ctx.look()
        rewind(ctx)
        card = scan(ctx, usable, True, energy=True, characters=bool(skip))
        if not card:
            ctx.log(f"  no filler for {unit_tiles or 'any'} with energy")
            return False
        place(ctx, card, slots[n], "filler")  # fillers on the left (they fight last)

    # anchors -> the right-hand slots (the rightmost fights first), strongest at the very front.
    # A descending search finds the bigger anchor first, an ascending one the smaller.
    anchor_slots = slots[fillers:]
    for n, ((lo, hi), unit_tiles) in enumerate(zip(targets, anchor_units)):
        tier, ascending = anchor_search(cfg, lo)
        slot = anchor_slots[n] if ascending else anchor_slots[-1 - n]
        filt.sort(ascending=ascending)
        filt.apply(_tiles_for(universal, unit_tiles, tier & rarities or rarities))
        filt.close()
        ctx.look()
        rewind(ctx)
        ok = lambda k: usable(k) and k.score >= lo  # noqa: E731
        card = scan(ctx, ok, ascending, prefer=lambda k: k.score <= hi,
                    stop=None if ascending else (lambda k: k.score < lo), energy=True, characters=bool(skip))
        if not card:
            ctx.log(f"  no anchor >= {lo:.0f} with energy")
            return False
        if card.score > hi:
            ctx.log(f"  ! anchor {card.score} above preferred max {hi:.0f} (closest available)")
        place(ctx, card, slot, "anchor")

    # leave only the mode's base filter on for next time
    filt.apply(_tiles_for(set(), set(), set(cfg.base_rarities)))
    filt.close()
    ctx.look()
    return r.fight_enabled(ctx.img)
