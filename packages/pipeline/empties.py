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
measure the near side's building line uses.

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


def terrace(rows, extents, stream, roads, span_x):
    """The Empties of one site: a list of ``{"id", "archetype", "at", "rot",
    "size_x", "size_y", "front"}`` (plan metres; ``front`` the y of the
    Empty's street edge) and the half-depth of plate the row needs south of
    the origin. ``rows`` are the library's Empties (`building_library.
    empty_rows`), ``extents`` {archetype: (x0, x1, y0, y1)} unturned,
    ``stream`` a `site_variation.stream`, ``roads`` the site's road dicts with
    the through road first."""
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
        if in_run >= run_len:
            x += ALLEY
            in_run = 0
            run_len = RUN[0] + next(stream) % (RUN[1] - RUN[0] + 1)
    return out, need
