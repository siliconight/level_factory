"""Which way a building faces: its front door, read off the building.

Level Factory 0.132.0. The walker's land-use guide (`docs/reference/
LAND_PRESSURE_AND_SPATIAL_LOGIC.md`, 5.3 "frontage has a function"), and
the census that measured it (`lot/site_landuse.py`): 67 of 126 fronting
buildings across the lots on disk had a ground door facing their road, and
312 of 920 door walks met a wall with no door. The cause was one line in
`site_variation.site_placements`: every building's yaw was drawn at random
from 0/90/180/270, so a bank's front door faced the street one seed in four.

Deli Counter already says which door is the front. Surveyed over all 134
built buildings (`deli_counter/build/*.gameplay.json`):

    a door TAGGED front (main_entry, front_door, front_customer_entry ...)   66
    no front tag; the widest door that is not a service door                  19
    no front tag; the only door that is not a service door                    7
    a tie between equal widest doors                                          40
    no ground door at all                                                     2

and of the 92 fronts the first three rules find, 88 are on the SOUTH wall,
Deli Counter's own convention; 37 of the 40 ties have a south door among
the widest. So a tie goes to the south wall, then to N, E, W in that order.
132 of 134 buildings get a front; the two with no ground door keep the
random yaw.

`facing_yaw(wall)` is the yaw that turns that wall's outward normal to plan
-y, the side Level Factory's road grammar always runs its through road
(`road_grammar._through_road`: south of the southernmost face). The rotation
is Lot's: a building-local point (x, y) goes to (x cos r - y sin r, x sin r +
y cos r) (`lot/site_enterability._rot`), so S needs 0, W 90, N 180, E 270.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

FRONT_TAG = re.compile(r"main|front|customer|shop|store|lobby|public")
SERVICE_TAG = re.compile(r"service|staff|rear|dock|stock|crew|loading|back|delivery|employee|kitchen")
#: A tie between equal doors goes to the first wall here: Deli Counter puts
#: its fronts on the south wall (88 of 92 identified).
TIE_ORDER = ("S", "N", "E", "W")
#: The yaw, degrees, that turns each wall's outward normal to plan -y.
YAW_TO_SOUTH = {"S": 0, "W": 90, "N": 180, "E": 270}


def _ground_doors(gameplay: dict) -> list:
    out = []
    for o in gameplay.get("openings", []) or []:
        wall = str(o.get("wall", ""))
        if o.get("kind") == "door" and wall.startswith("ext_0_") and wall[-1] in YAW_TO_SOUTH:
            out.append(o)
    return out


def front_wall(gameplay: dict):
    """``(wall letter, reason)`` for a building's front, or ``(None, reason)``."""
    doors = _ground_doors(gameplay)
    if not doors:
        return None, "no ground door"

    def tag(o):
        return str(o.get("tag") or "")
    tagged = [o for o in doors if tag(o) and FRONT_TAG.search(tag(o)) and not SERVICE_TAG.search(tag(o))]
    if tagged:
        pool, reason = tagged, "tagged front"
    else:
        pool = [o for o in doors if not (tag(o) and SERVICE_TAG.search(tag(o)))] or doors
        reason = "widest door" if len(pool) > 1 else "only door"
    widest = max(float(o.get("width") or 0.0) for o in pool)
    best = [o for o in pool if float(o.get("width") or 0.0) == widest]
    walls = {o["wall"][-1] for o in best}
    if len(walls) > 1:
        reason += ", tie to the south" if "S" in walls else ", tie"
    for w in TIE_ORDER:
        if w in walls:
            return w, reason
    return None, "no readable wall"


def front_wall_of(gameplay_path):
    """`front_wall` of a gameplay file on disk; ``(None, reason)`` when it
    cannot be read."""
    try:
        return front_wall(json.loads(Path(gameplay_path).read_text(encoding="utf-8")))
    except (OSError, ValueError, TypeError) as exc:
        return None, f"unreadable: {exc}"


def facing_yaw(wall):
    """The yaw that faces `wall` to plan -y; None for no wall."""
    return YAW_TO_SOUTH.get(wall) if wall else None
