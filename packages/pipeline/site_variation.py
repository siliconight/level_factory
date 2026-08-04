"""Turn a candidate seed into a materially different site.

Deli Counter is deterministic on purpose: one preset in, one building out, every
time -- ``new_level.py`` has no seed flag and the adapter says so out loud. The
documented intent is that candidate variation comes from Lot's site assembly
instead, and Lot has the vocabulary for it: a per-building ``rot`` is honoured
all the way through placement, marker rotation, the Godot transforms and the
site audit.

Nothing was using any of it. Every candidate was handed the same evenly-spaced,
zero-rotation row, so five seeds produced five byte-identical sites and the
candidate mechanism was decorative -- five choices that were one choice, offered
to a human as though the choosing meant something.

The variation here is deliberately structural, not cosmetic. Yaw is what changes
a building's relationship to the street: which face carries the entrance, which
side the ladder climbs, whether the approach is across open ground or along a
wall. Stagger changes sightlines down the row. A metre of random jitter would
have made the hashes differ while leaving the level identical to play, which is
precisely the failure this module exists to prevent -- passing a diversity gate
is not the goal, being different levels is.

Pure and dependency-free by design: the builder derives placements from it, the
gate re-derives them to check, and the tests exercise it without a workspace.

The row is centred on the origin, and the ground is sized from the shells that
stand on it. Both of those used to be otherwise, and together they cost a whole
evaluation: placements marched out along +x from the origin while ``ground_size``
returned a symmetric span from the building *count*, so the plate Lot centred on
the origin sat about 66 m west of the row it was supposed to carry. The last
building on ``category5_baie_dore_001`` overhung the plate by 44 m, its ground
hole was clipped out of existence, and the crew spawned on that building's
interior floor as an island. Laser Tag graded the map BROKEN on zero runs.

The plate is still centred on the origin, which is why the row has to be too: a
reader that halves ``size_x`` and a reader that resolves the true extent then
give the same answer, and neither can be wrong on its own. Lot re-derives the
extent from the content regardless (``site_extent.py``) and reports any growth,
so the two sides of the contract check each other rather than trusting one.
"""
from __future__ import annotations

import math
from pathlib import Path

# Cardinal yaws only. A building is a rectangle on a lot, and 15-degree
# increments read as a mistake rather than as a choice; the cardinals rotate
# which facade fronts the street without making the block look damaged.
_YAW = (0, 90, 180, 270)

# Along-row nudge, in metres. It moves origins, so on its own it says nothing
# about whether two shells clear each other -- it closes the gap between a pair
# by up to 12 m, and `row_spacing` is what opens the gap wide enough to absorb
# that. The comment here used to claim the bound made overlap impossible, which
# was true of the origins and false of the buildings.
_ALONG = (-6, -3, 0, 3, 6)

# Across-row stagger. This is the one that changes sightlines: a staggered row
# breaks the single long firing lane a flush row creates.
_ACROSS = (-10, -5, 0, 5, 10)

#: Ground kept outside the outermost shell, in metres. Godot erodes the navmesh
#: by the agent radius (0.4 m) at every geometry edge including the plate rim, so
#: a plate that stops flush with a wall leaves no walkable surface along it. Four
#: metres is a street you can move down; it matches Lot's own ``CLEARANCE`` so
#: the two sides of the contract are asking for the same thing.
CLEARANCE = 4.0

#: Footprint assumed for a shell whose geometry cannot be measured, in metres.
#: Deli Counter's shells run 40-50 m on a side, so this is the top of that range
#: rather than an average: over-sizing the plate lays extra street, under-sizing
#: it drops a building off the edge, and only one of those is recoverable.
DEFAULT_FOOTPRINT = (48.0, 48.0)

#: Clear ground between two neighbouring shells, in metres. Wide enough to move
#: down and to fight across once the navmesh has eroded both edges by the agent
#: radius, and wide enough that the pair reads as two buildings on a street
#: rather than one damaged block.
STREET = 8.0


def _stream(seed: int):
    """A small deterministic integer stream.

    Deliberately not ``random`` -- this has to produce the same site on every
    machine and every Python version, because the cache fingerprint and the
    diversity gate both depend on re-deriving exactly what the builder derived.
    """
    x = (int(seed) * 6364136223846793005 + 1442695040888963407) & ((1 << 64) - 1)
    while True:
        x = (x * 6364136223846793005 + 1442695040888963407) & ((1 << 64) - 1)
        yield x >> 33


#: The deterministic stream, exported so anything else that derives from a
#: candidate seed uses the SAME one. `building_library.pick_lot` does; two
#: streams would make two modules disagree about what seed 5421 means, and the
#: cache fingerprint depends on re-deriving exactly what the builder derived.
stream = _stream


def site_placements(seed: int, count: int, *, spacing: int = 45,
                    footprints=None) -> dict:
    """Deterministic placement + role assignment for one candidate's buildings.

    Returns ``{"buildings": [{"at": [x, y], "rot": deg}, ...], "spawn": id,
    "objective": id, "extraction": id}`` -- the building-role keys Lot reads to
    place the walkable scene's spawn/objective/extraction, which LF was leaving
    unset so every candidate spawned the player at Lot's origin default.

    The row is centred on the origin. It used to start there and march out along
    +x, which put a four-building row at x -6..141 under a plate centred on 0 --
    the defect this module's header describes.
    """
    count = max(1, int(count))
    rng = _stream(seed)
    buildings = []
    # A row of DIFFERENT buildings cannot share one spacing: the gap a stadium
    # needs would strand a deli in forty metres of empty street, and the gap a
    # deli needs would put the stadium through its neighbour. `footprints`
    # (one per building, in row order) switches to per-gap offsets. Absent, the
    # uniform row below is unchanged, which every existing caller relies on.
    offsets = row_offsets(footprints) if footprints else None
    # Whole metres: the offsets are, the spacing is, and a site spec full of
    # x = -67.5 reads as arithmetic having happened to it rather than as a
    # placement someone chose. An even count sits half a space off-centre by
    # `spacing // 2`, which is a metre or two of asymmetry, not a mis-centring.
    origin = (count - 1) * spacing // 2
    for i in range(count):
        rot = _YAW[next(rng) % len(_YAW)]
        along = _ALONG[next(rng) % len(_ALONG)]
        across = _ACROSS[next(rng) % len(_ACROSS)]
        base = offsets[i] if offsets else (i * spacing - origin)
        buildings.append({"at": [base + along, across], "rot": rot})

    # Roles: which building you start at, which one holds the objective, which
    # one you leave from. On a one-building site all three collapse onto it,
    # which is correct rather than degenerate.
    ids = [f"b{i}" for i in range(count)]
    spawn = ids[next(rng) % count]
    objective = ids[next(rng) % count]
    # Prefer an extraction that is not the spawn, so the route crosses the site.
    others = [b for b in ids if b != spawn] or ids
    extraction = others[next(rng) % len(others)]
    return {"buildings": buildings, "spawn": spawn,
            "objective": objective, "extraction": extraction}


def shell_footprint(glb_path) -> tuple[float, float] | None:
    """The shell's collision extent about its own origin, in site XY metres.

    Measured from the ``.glb``'s collider hulls rather than assumed, because a
    plate sized from the building *count* is a plate sized from nothing that is
    standing on it. Returns ``None`` when the geometry cannot be read -- a shell
    that could not be measured is not a shell of size zero, and the caller has to
    be able to tell those apart.

    Reported as the extent *about the origin* (twice the furthest face), not as
    the collider bounding box: Lot places a building by its own origin, so a
    shell modelled off-centre reaches further from ``at`` than its width. Erring
    large here lays street; erring small drops a wall off the plate.

    Godot's glTF space maps to Lot's site space as x -> x, z -> -y, so the two
    horizontal axes carry across and the sign on the second one does not matter
    to an extent.
    """
    try:
        from packages.validation import glb_collision
    except ImportError:                       # pragma: no cover - packaging only
        return None
    path = Path(glb_path)
    reading = glb_collision.collision_solids(path)
    if not reading.read or not reading.solids:
        return None
    half_x = half_y = 0.0
    for solid in reading.solids:
        cx, _cy, cz = solid.centre
        sx, _sy, sz = solid.size
        half_x = max(half_x, abs(cx) + sx / 2.0)
        half_y = max(half_y, abs(cz) + sz / 2.0)
    if half_x <= 0.0 or half_y <= 0.0:
        return None
    return (2.0 * half_x, 2.0 * half_y)


def _reach(footprint: tuple[float, float] | None) -> float:
    """Half a shell's widest horizontal axis.

    The longer axis on BOTH axes, because yaw is a cardinal rotation and a
    quarter turn swaps them -- the same pessimism :func:`overlapping` and
    :func:`uncovered` already apply, named once instead of restated four times.
    """
    fx, fy = footprint or DEFAULT_FOOTPRINT
    return max(float(fx), float(fy)) / 2.0


def row_offsets(footprints, *, street: float = STREET) -> list[int]:
    """X positions for a row of DIFFERENT-SIZED buildings, centred on the origin.

    WHY THIS EXISTS. Everything else in this module sizes the row from ONE
    measurement, on the stated assumption that "every candidate instances the
    same Deli Counter shell, so one measurement covers the row". That is
    roadmap item 37 in arithmetic form: a site is one building N times, so the
    spacing only ever had to be right for one size.

    Deli Counter ships 41 archetypes, and a deli beside a stadium breaks the
    assumption. Not quietly -- :func:`overlapping` and :func:`uncovered` run on
    every spec write and would refuse the build -- but refusing is not placing.

    So each GAP is sized by the two buildings that share it: both reaches, the
    street between them, and the slack for the nudge each neighbour can make
    toward the other. A row of EQUAL shells reproduces the uniform spacing
    exactly, which is the compatibility that matters.

    Whole metres, for the reason ``site_placements`` gives: a spec full of
    x = -67.5 reads as arithmetic having happened to it rather than as a
    placement someone chose.
    """
    reaches = [_reach(f) for f in (footprints or [])]
    if not reaches:
        return []
    slack = max(abs(v) for v in _ALONG)
    xs = [0.0]
    for i in range(1, len(reaches)):
        gap = reaches[i - 1] + reaches[i] + float(street) + 2.0 * slack
        xs.append(xs[-1] + math.ceil(gap))
    span = xs[-1]
    return [int(round(x - span / 2.0)) for x in xs]


def row_spacing(footprint: tuple[float, float] | None = None,
                *, street: float = STREET) -> int:
    """Metres between building origins, wide enough for the shells between them.

    The spacing was a constant 45 while the shells were 44 m wide, so a candidate
    whose nudges pushed two neighbours to the inside of their range put 42 m
    between two 44 m buildings and the pipeline assembled them interpenetrating.
    Nothing objected: Lot compared markers to footprints and footprints to
    bounds, never a footprint to its neighbour.

    Derived instead: a full shell, the widest the two nudges can close the gap,
    and a street between them. Yaw-safe, because a cardinal rotation can present
    the longer axis to the street.
    """
    fx, fy = footprint or DEFAULT_FOOTPRINT
    span = max(float(fx), float(fy))
    return int(math.ceil(span + 2 * max(abs(v) for v in _ALONG) + float(street)))


def ground_size(count: int, *, spacing: int = 45,
                footprint: tuple[float, float] | None = None,
                footprints=None) -> tuple[int, int]:
    """Ground plate big enough for the whole placed row, whatever seed placed it.

    Sized from the shells rather than from the count, and bounded over every
    seed rather than computed for one: the nudge and stagger tables are the widest
    any candidate can be pushed, so all five candidates of a mission get the same
    plate and stay comparable to each other.

    ``footprint`` is the shell's extent about its origin, from
    :func:`shell_footprint`. The larger of its two axes is used on both, because
    yaw is a cardinal rotation and a quarter turn swaps them. ``None`` falls back
    to :data:`DEFAULT_FOOTPRINT`, which is a guess and is documented as one --
    Lot re-derives the extent from the assembled site and extends the plate with
    ``LOT_GROUND_EXTENDED`` if this was wrong, so a bad guess costs a finding
    rather than a level.

    Returns whole metres, rounded up.
    """
    count = max(1, int(count))
    slack = max(abs(v) for v in _ALONG)
    if footprints:
        # Sized from the row this module actually places, building by building:
        # the plate has to reach past whichever shell ends up furthest out, and
        # on a mixed row that is not simply the last one.
        offs = row_offsets(footprints)
        reaches = [_reach(f) for f in footprints]
        half_x = max(abs(o) + slack + r for o, r in zip(offs, reaches))
        half_y = max(abs(v) for v in _ACROSS) + max(reaches)
    else:
        reach = _reach(footprint)
        half_x = (count - 1) * spacing / 2.0 + slack + reach
        half_y = max(abs(v) for v in _ACROSS) + reach
    return (int(math.ceil(2.0 * (half_x + CLEARANCE))),
            int(math.ceil(2.0 * (half_y + CLEARANCE))))


def overlapping(spec: dict, footprint: tuple[float, float] | None = None,
                footprints=None) -> list[str]:
    """Which pairs of buildings in a written spec stand in each other.

    The producer's half of Lot's ``LOT_BUILDINGS_OVERLAP`` gate. Yaw-safe by
    being pessimistic: the square of the footprint's longer axis, so a quarter
    turn cannot turn a clear pair into a colliding one after the check has run.
    """
    rects = []
    for i, b in enumerate(spec.get("buildings") or []):
        # Each building measured as ITSELF. One shared reach would clear a
        # stadium standing on a deli and flag two delis that are metres apart.
        reach = _reach(footprints[i]) if footprints else _reach(footprint)
        at = b.get("at") or [0.0, 0.0]
        rects.append((b.get("id", "?"),
                      (float(at[0]) - reach, float(at[1]) - reach,
                       float(at[0]) + reach, float(at[1]) + reach)))
    out = []
    for i, (aid, a) in enumerate(rects):
        for bid, b in rects[i + 1:]:
            depth = min(min(a[2], b[2]) - max(a[0], b[0]),
                        min(a[3], b[3]) - max(a[1], b[1]))
            if depth > 0.0:
                out.append(f"{aid} and {bid} reach {depth:g} m into each other")
    return out


def uncovered(spec: dict, footprint: tuple[float, float] | None = None,
              footprints=None) -> list[str]:
    """Which buildings in a written site spec stand off its ground plate.

    The producer's own self-check, run before the spec is handed to Lot. It is
    not a second opinion on Lot's ``site_extent`` -- it asks the narrower question
    this module is responsible for: does the plate *this module sized* contain the
    row *this module placed*. Empty means yes.

    Reads ``spec["ground"]["size_x"]``/``size_y`` as a plate centred on the
    origin, which is what Lot's schema means by them and what Lot draws.
    """
    ground = spec.get("ground") or {}
    try:
        hx = float(ground["size_x"]) / 2.0
        hy = float(ground["size_y"]) / 2.0
    except (KeyError, TypeError, ValueError):
        return ["the spec declares no readable ground size"]
    out = []
    for i, b in enumerate(spec.get("buildings") or []):
        reach = _reach(footprints[i]) if footprints else _reach(footprint)
        at = b.get("at") or [0.0, 0.0]
        x0, x1 = float(at[0]) - reach, float(at[0]) + reach
        y0, y1 = float(at[1]) - reach, float(at[1]) + reach
        if x0 < -hx or x1 > hx or y0 < -hy or y1 > hy:
            out.append(
                f"{b.get('id', '?')} at ({at[0]:g}, {at[1]:g}) spans "
                f"x {x0:g}..{x1:g}, y {y0:g}..{y1:g}, outside the declared "
                f"{ground.get('size_x')} x {ground.get('size_y')} m plate "
                f"(x {-hx:g}..{hx:g}, y {-hy:g}..{hy:g})")
    return out
