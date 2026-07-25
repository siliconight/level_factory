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
"""
from __future__ import annotations

# Cardinal yaws only. A building is a rectangle on a lot, and 15-degree
# increments read as a mistake rather than as a choice; the cardinals rotate
# which facade fronts the street without making the block look damaged.
_YAW = (0, 90, 180, 270)

# Along-row nudge, in metres. Bounded well inside the spacing so two neighbours
# cannot be pushed into each other -- with the default 45 m spacing the closest
# two origins can come is 33 m.
_ALONG = (-6, -3, 0, 3, 6)

# Across-row stagger. This is the one that changes sightlines: a staggered row
# breaks the single long firing lane a flush row creates.
_ACROSS = (-10, -5, 0, 5, 10)


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


def site_placements(seed: int, count: int, *, spacing: int = 45) -> dict:
    """Deterministic placement + role assignment for one candidate's buildings.

    Returns ``{"buildings": [{"at": [x, y], "rot": deg}, ...], "spawn": id,
    "objective": id, "extraction": id}`` -- the building-role keys Lot reads to
    place the walkable scene's spawn/objective/extraction, which LF was leaving
    unset so every candidate spawned the player at Lot's origin default.
    """
    count = max(1, int(count))
    rng = _stream(seed)
    buildings = []
    for i in range(count):
        rot = _YAW[next(rng) % len(_YAW)]
        along = _ALONG[next(rng) % len(_ALONG)]
        across = _ACROSS[next(rng) % len(_ACROSS)]
        buildings.append({"at": [i * spacing + along, across], "rot": rot})

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


def ground_size(count: int, *, spacing: int = 45) -> tuple[int, int]:
    """Ground plate big enough for the placed row plus the stagger and margin."""
    count = max(1, int(count))
    span_x = max(spacing * count, 60) + 2 * max(abs(v) for v in _ALONG) + 40
    span_y = 80 + 2 * max(abs(v) for v in _ACROSS)
    return span_x, span_y
