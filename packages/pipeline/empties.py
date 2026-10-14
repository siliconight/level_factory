"""Empties across the street: a terrace of non-enterable shells (0.137.0).

Roadmap 106. The walker, 2026-10-04: Empties stand around the walkable level
and across its streets, so a street is a street on both sides instead of a
plate's blank perimeter wall. The comps (a Philadelphia rowhouse street, all
of it 1990s) are read off in the factory root's
`docs/reference/EMPTIES_COMPS.md`: a terrace reads as HOUSES because each one
differs, so no two neighbours are the same shell, and an alley breaks the
row every few houses.

WHERE. Along the far side of the through road -- the side the road grammar
leaves to the plate's edge -- every Empty's FRONT EDGE stands on one line,
`FRONTAGE` behind the far sidewalk's back edge, the same 2.0 m the near side
keeps (`road_grammar.FRONTAGE`). Each is turned 180 degrees, so its front
(Deli Counter's south wall) faces the road. No Empty stands across a road
that leaves the through road southward (a crossroads' south arm): that
road's band and its frontage are skipped, and the row resumes past them.

WHAT THEY ARE TO LOT: `blockers` (`lot.py`), which Lot instances from a
shell scene like a building and which no walk, dumpster, field or entry
gate reads. Placement here is plan metres; a building's street edge is read
per side off its collider hulls (`street_line.shell_extents`), the same
measure the near side's building line uses. A rowhome's STOOP is not its
edge (0.195.0): it stands in the strip in front of the line, which is what
the strip is for (`street_line.STOOP_COLLIDERS`, `stoop_reach`).

Pure but for nothing: the extents are measured by the caller.
"""
from __future__ import annotations

import math

#: Behind the far sidewalk's back edge to an Empty's front, metres: the
#: near side's own frontage (`road_grammar.FRONTAGE`), so the street is
#: symmetric.
FRONTAGE = 2.0
#: An alley between two runs of houses, metres: a body passes and it reads
#: as a gap in the row. Chosen, not derived.
ALLEY = 3.0
#: Houses in a run before an alley: drawn per run from this range.
RUN = (5, 8)
#: Clear ground left at the plate's two ends, metres
#: (`site_variation.CLEARANCE`).
CLEARANCE = 4.0


def _turned(extents, rot):
    """``(x0, x1, y0, y1)`` of a shell's hulls once turned by ``rot`` degrees
    about its origin (Lot's rotation)."""
    x0, x1, y0, y1 = extents
    r = math.radians(float(rot))
    c, s = math.cos(r), math.sin(r)
    pts = [(x * c - y * s, x * s + y * c) for x in (x0, x1) for y in (y0, y1)]
    return (min(p[0] for p in pts), max(p[0] for p in pts),
            min(p[1] for p in pts), max(p[1] for p in pts))


def _far_side(through):
    """The y of the far sidewalk's back edge, and the y of the Empties' line."""
    y_road = (float(through["a"][1]) + float(through["b"][1])) / 2.0
    edge = y_road - float(through["width"]) / 2.0 - float(through.get("sidewalk") or 0.0)
    return edge, edge - FRONTAGE


def _blocked(roads, edge):
    """x intervals the row must not stand in: every road but the first that
    runs south past the far side, with its band and the frontage either side."""
    out = []
    for r in roads[1:]:
        (ax, ay), (bx, by) = r["a"], r["b"]
        if abs(float(ax) - float(bx)) > 1e-6:
            continue                              # not a north-south road
        if min(float(ay), float(by)) >= edge:
            continue                              # does not reach the far side
        half = float(r["width"]) / 2.0 + float(r.get("sidewalk") or 0.0) + FRONTAGE
        out.append((float(ax) - half, float(ax) + half))
    return sorted(out)


def _deal(usable, stream, avoid=None):
    """Every design once, in an order shuffled off ``stream`` (Fisher-Yates),
    dealt from the END of the list. If the first one dealt would be ``avoid``
    -- the house just placed -- it trades places with the next, so no two
    neighbours are the same house across two deals either.

    WHY A DEAL (0.142.0). The terrace drew each house uniformly and turned
    away only an immediate repeat. Cold run 9160 doubled the rowhomes to
    twelve expecting a row to show each about twice, and its three
    candidates' rows -- 25, 31 and 29 houses -- used 10, 12 and 10 of the
    designs with the most-repeated shown 5, 6 and 5 times. The library's size
    moved the mean; the spread is the draw's. Dealt, a row of n houses from k
    designs shows each floor(n/k) or one more times, and every design by the
    k-th house."""
    bag = list(usable)
    for i in range(len(bag) - 1, 0, -1):
        j = next(stream) % (i + 1)
        bag[i], bag[j] = bag[j], bag[i]
    if avoid is not None and len(bag) > 1 and bag[-1]["id"] == avoid:
        bag[-1], bag[-2] = bag[-2], bag[-1]
    return bag


def terrace(rows, extents, stream, roads, span_x, continuous=False):
    """The Empties of one site: a list of ``{"id", "archetype", "at", "rot",
    "size_x", "size_y", "front"}`` (plan metres; ``front`` the y of the
    Empty's street edge) and the half-depth of plate the row needs south of
    the origin. ``rows`` are the library's Empties (`building_library.
    empty_rows`), ``extents`` {archetype: (x0, x1, y0, y1)} unturned,
    ``stream`` a `site_variation.stream`, ``roads`` the site's road dicts with
    the through road first.

    ``continuous`` (0.200.0, factory roadmap 241): the urban street's wall,
    with no alley between runs -- one row broken only where a road crosses
    the far side. Off, the terrace draws exactly as it did."""
    usable = [r for r in rows if extents.get(r["id"]) is not None]
    if not usable or not roads:
        return [], 0.0
    edge, line = _far_side(roads[0])
    blocked = _blocked(roads, edge)
    x = -float(span_x) / 2.0 + CLEARANCE
    x_end = float(span_x) / 2.0 - CLEARANCE
    out, prev, in_run = [], None, 0
    run_len = RUN[0] + next(stream) % (RUN[1] - RUN[0] + 1)
    need = 0.0
    bag: list = []
    while True:
        # A DEAL, NOT A DRAW (0.142.0): the next house off a shuffled bag of
        # every design, refilled when empty (`_deal`). A pick a road turns
        # away stays on the bag for the far side of it; only a house that is
        # placed is dealt.
        if not bag:
            bag = _deal(usable, stream, prev)
        pick = bag[-1]
        tx0, tx1, ty0, ty1 = _turned(extents[pick["id"]], 180)
        width = tx1 - tx0
        if x + width > x_end:
            break
        hit = next((b for b in blocked if not (x + width <= b[0] or x >= b[1])), None)
        if hit is not None:
            x, in_run = hit[1], 0
            continue
        at_x = x - tx0
        at_y = line - ty1                          # the street edge on the line
        out.append({"id": f"e{len(out)}", "archetype": pick["id"],
                    "at": [round(at_x, 3), round(at_y, 3)], "rot": 180,
                    "size_x": round(width, 3), "size_y": round(ty1 - ty0, 3),
                    "front": round(at_y + ty1, 3)})
        need = max(need, -(at_y + ty0))
        bag.pop()
        prev = pick["id"]
        x += width
        in_run += 1
        if not continuous and in_run >= run_len:
            x += ALLEY
            in_run = 0
            run_len = RUN[0] + next(stream) % (RUN[1] - RUN[0] + 1)
    return out, need


#: THE NEAR SIDE'S PASSAGE (0.201.0, factory roadmap 241): clear ground kept on each side of every one of the
#: mission's own buildings when the urban street fills the near frontage -- `site_variation.CLEARANCE`, "a
#: street you can move down", so a side door, a side wall's dumpster and the way round to the back stay open.
NEAR_PASSAGE = 4.0


def building_rect(at, rot, footprint):
    """``(x0, x1, y0, y1)`` of a building as `site_variation` measures it: its footprint (width, depth),
    symmetric about ``at``, turned a quarter at a time."""
    w, d = float(footprint[0]), float(footprint[1])
    if int(round(float(rot or 0))) % 180 == 90:
        w, d = d, w
    x, y = float(at[0]), float(at[1])
    return (x - w / 2.0, x + w / 2.0, y - d / 2.0, y + d / 2.0)


def _near_side(through):
    """The y of the near sidewalk's back edge, and the y of the near building line."""
    y_road = (float(through["a"][1]) + float(through["b"][1])) / 2.0
    edge = y_road + float(through["width"]) / 2.0 + float(through.get("sidewalk") or 0.0)
    return edge, edge + FRONTAGE


def _road_band(road):
    """``(x0, x1, y0, y1)`` of a road's band -- carriageway, sidewalks and the frontage either side -- for an
    axis-aligned road; None for one that is not."""
    (ax, ay), (bx, by) = road["a"], road["b"]
    half = float(road["width"]) / 2.0 + float(road.get("sidewalk") or 0.0) + FRONTAGE
    if abs(float(ay) - float(by)) < 1e-6:
        return (min(float(ax), float(bx)), max(float(ax), float(bx)), float(ay) - half, float(ay) + half)
    if abs(float(ax) - float(bx)) < 1e-6:
        return (float(ax) - half, float(ax) + half, min(float(ay), float(by)), max(float(ay), float(by)))
    return None


def _hits(r, s):
    return r[0] < s[1] and s[0] < r[1] and r[2] < s[3] and s[2] < r[3]


def infill(rows, extents, stream, roads, span_x, buildings):
    """The urban street's NEAR side: Empties along the near building line, filling the frontage between the
    mission's own buildings, every front on the line and facing the road (rot 0). A list like `terrace`'s,
    with ids ``n0``..., and the y the plate must reach north of the origin to carry their backs.

    ``buildings`` are the mission's buildings as plan rects (`building_rect`). Each keeps `NEAR_PASSAGE`
    clear on both sides; every road but the through road keeps its band and frontage clear (a side street,
    the service lane); the plate's ends keep `CLEARANCE`. Between those the shells are DEALT as the far side
    deals them (`_deal`), and where the next one is wider than the room left before an obstacle, the next
    narrower one on the bag is tried; a room no shell fits stays open, a gap the street keeps.
    """
    usable = [r for r in rows if extents.get(r["id"]) is not None]
    if not usable or not roads:
        return [], 0.0
    _edge, line = _near_side(roads[0])
    bands = [b for b in (_road_band(r) for r in roads[1:]) if b is not None]
    deepest = max(_turned(extents[r["id"]], 0)[3] - _turned(extents[r["id"]], 0)[2] for r in usable)
    stops = []
    for (x0, x1, y0, y1) in buildings:
        if y1 > line and y0 < line + deepest:
            stops.append((x0 - NEAR_PASSAGE, x1 + NEAR_PASSAGE))
    for (x0, x1, y0, y1) in bands:
        if y1 > line and y0 < line + deepest and (x1 - x0) < (y1 - y0):
            stops.append((x0, x1))                   # a road running north across the frontage
    stops.sort()
    x = -float(span_x) / 2.0 + CLEARANCE
    x_end = float(span_x) / 2.0 - CLEARANCE
    out, prev, bag, need = [], None, [], 0.0
    while x < x_end:
        hit = next((s for s in stops if s[0] <= x < s[1]), None)
        if hit is not None:
            x = hit[1]
            continue
        room = min([x_end] + [s[0] for s in stops if s[0] > x]) - x
        if not bag:
            bag = _deal(usable, stream, prev)
        fits = [i for i in range(len(bag) - 1, -1, -1)
                if _turned(extents[bag[i]["id"]], 0)[1] - _turned(extents[bag[i]["id"]], 0)[0] <= room + 1e-9]
        # no two neighbours the same shell, as across the street, unless only the same one fits
        fits.sort(key=lambda i: bag[i]["id"] == prev)
        placed = None
        for i in fits:
            tx0, tx1, ty0, ty1 = _turned(extents[bag[i]["id"]], 0)
            rect = (x, x + (tx1 - tx0), line, line + (ty1 - ty0))
            if any(_hits(rect, b) for b in bands):
                continue                             # its back would stand in the lane
            placed = (i, tx0, tx1, ty0, ty1)
            break
        if placed is None:
            nxt = [s[1] for s in stops if s[0] > x]
            if not nxt:
                break
            x = min(s[0] for s in stops if s[0] > x)   # this room stays open: on to the next obstacle
            continue
        i, tx0, tx1, ty0, ty1 = placed
        pick = bag.pop(i)
        width = tx1 - tx0
        at_x, at_y = x - tx0, line - ty0               # the street edge (-y, unturned) on the line
        out.append({"id": f"n{len(out)}", "archetype": pick["id"],
                    "at": [round(at_x, 3), round(at_y, 3)], "rot": 0,
                    "size_x": round(width, 3), "size_y": round(ty1 - ty0, 3),
                    "front": round(at_y + ty0, 3)})
        need = max(need, at_y + ty1)
        prev = pick["id"]
        x += width
    return out, need


def stoop_reach(whole, house):
    """How far a shell's stoop reaches in front of its house, metres: the
    street edge (-y, unturned) of every collider (``whole``) less the house's
    own (``house``, `street_line.STOOP_COLLIDERS` skipped); 0.0 for a shell
    with none, None when either is unread. The terrace keeps it inside
    `FRONTAGE` (0.195.0)."""
    if whole is None or house is None:
        return None
    return round(max(0.0, house[2] - whole[2]), 4)
