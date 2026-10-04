"""One building line a street: where a building's street edge is, and the line.

Step 3 of `docs/proposals/LAND_USE_DESIGN.md` (the land-pressure guide's
5.7, correlated variation): a street keeps a building line, and a building
leaves it only for a reason. Until 0.135.0 every building on a row took its
own across-the-road draw (`site_variation._ACROSS`, -10..10 m) and stood its
own depth from that, so the line was a residue: measured on the nine
candidates of 0.132.0's before/after, the building line spread 10-24 m
along one road.

A BUILDING'S STREET EDGE is the furthest any of its solids reaches toward the
street, read from the same collider hulls `site_variation.shell_footprint`
measures -- but per side, not as twice the furthest face. That difference is
the point. A gas station's canopy and forecourt stand in front of its store
(`gas_station_a02`: solids from 32 m in front of the origin to 14 m behind;
Deli Counter's declared footprint ends 11 m in front), so a line drawn on the
stores would put every canopy on the sidewalk, and a line drawn on the
symmetric extent would set every off-centre building back by its back yard.
On the street edge, a station's STORE stands back behind its forecourt --
the explained exception the design asks for, by construction rather than by
a table of exceptions.

Plan (x, y), metres; the street is toward -y, where the road grammar puts the
through road. Godot's glTF z is site -y. Lot's rotation is
(x, y) -> (x cos r - y sin r, x sin r + y cos r).

Pure but for `shell_extents`, which reads a GLB.
"""
from __future__ import annotations

import math
from pathlib import Path


def shell_extents(glb_path):
    """``(x_min, x_max, y_min, y_max)`` of a shell's collider hulls about its
    own origin, in site metres; None when the geometry cannot be read."""
    try:
        from packages.validation import glb_collision
    except ImportError:                       # pragma: no cover - packaging only
        return None
    reading = glb_collision.collision_solids(Path(glb_path))
    if not reading.read or not reading.solids:
        return None
    x0 = min(s.centre[0] - s.size[0] / 2.0 for s in reading.solids)
    x1 = max(s.centre[0] + s.size[0] / 2.0 for s in reading.solids)
    z0 = min(s.centre[2] - s.size[2] / 2.0 for s in reading.solids)
    z1 = max(s.centre[2] + s.size[2] / 2.0 for s in reading.solids)
    return (x0, x1, -z1, -z0)


def south_reach(extents, rot):
    """How far the building reaches from its origin toward the street (-y)
    once turned by ``rot`` degrees; None when ``extents`` is."""
    if extents is None:
        return None
    x0, x1, y0, y1 = extents
    r = math.radians(float(rot or 0))
    s, c = math.sin(r), math.cos(r)
    return round(max(-(x * s + y * c) for x in (x0, x1) for y in (y0, y1)), 4)


def line_ys(reaches):
    """The origin ``y`` of each building that puts every street edge on one
    line, centred so the row's origins straddle 0 as `site_variation` keeps
    them. ``None`` in, ``None`` out: a building whose reach is unknown keeps
    the place it was given."""
    known = [r for r in reaches if r is not None]
    if not known:
        return [None] * len(reaches)
    line = -(max(known) + min(known)) / 2.0
    return [None if r is None else round(line + r, 2) for r in reaches]
