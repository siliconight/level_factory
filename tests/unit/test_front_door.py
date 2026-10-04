"""A building faces the street with its front door (Level Factory 0.132.0)."""
from __future__ import annotations
import json

from packages.pipeline import front_door as FD
from packages.pipeline.site_variation import site_placements


def _door(wall, width=1.25, tag=None):
    return {"wall": f"ext_0_{wall}", "kind": "door", "width": width, "tag": tag}


def test_a_tagged_front_wins_over_a_wider_service_door():
    gp = {"openings": [_door("N", 2.4, "loading_dock"), _door("E", 1.25, "main_entry")]}
    assert FD.front_wall(gp) == ("E", "tagged front")


def test_no_tag_the_widest_door_that_is_not_a_service_door():
    gp = {"openings": [_door("N", 3.0, "rear_service"), _door("W", 1.8), _door("S", 1.25)]}
    assert FD.front_wall(gp) == ("W", "widest door")


def test_a_tie_goes_to_the_south_wall():
    gp = {"openings": [_door("N", 1.25), _door("S", 1.25), _door("E", 1.25)]}
    wall, reason = FD.front_wall(gp)
    assert wall == "S" and "tie to the south" in reason


def test_windows_breaches_upper_floors_and_interior_doors_are_not_fronts():
    gp = {"openings": [{"wall": "ext_0_S", "kind": "breach", "width": 1.4},
                       {"wall": "ext_0_S", "kind": "window", "width": 2.0},
                       {"wall": "ext_1_S", "kind": "door", "width": 1.25},
                       {"wall": "int_0_0", "kind": "door", "width": 1.25}]}
    assert FD.front_wall(gp) == (None, "no ground door")


def test_the_yaw_turns_the_front_to_plan_south():
    """Lot's rotation: (x, y) -> (x cos r - y sin r, x sin r + y cos r)."""
    import math
    normals = {"S": (0, -1), "N": (0, 1), "E": (1, 0), "W": (-1, 0)}
    for wall, (nx, ny) in normals.items():
        r = math.radians(FD.facing_yaw(wall))
        out = (nx * math.cos(r) - ny * math.sin(r), nx * math.sin(r) + ny * math.cos(r))
        assert abs(out[0]) < 1e-9 and abs(out[1] + 1.0) < 1e-9, (wall, out)
    assert FD.facing_yaw(None) is None


def test_placements_take_the_front_and_keep_every_other_draw():
    fps = [(20.0, 16.0), (24.0, 30.0), (40.0, 28.0)]
    free = site_placements(9080, 3, footprints=fps)
    faced = site_placements(9080, 3, footprints=fps, fronts=[0, None, 180])
    assert [b["rot"] for b in faced["buildings"]][0] == 0
    assert faced["buildings"][2]["rot"] == 180
    assert faced["buildings"][1]["rot"] == free["buildings"][1]["rot"]       # no front: the draw
    assert [b["at"] for b in faced["buildings"]] == [b["at"] for b in free["buildings"]]
    assert {k: faced[k] for k in ("spawn", "objective", "extraction")} == \
        {k: free[k] for k in ("spawn", "objective", "extraction")}


def test_the_library_s_buildings_nearly_all_have_a_front():
    """Read off Deli Counter's built buildings when they are here; the survey
    that set the rules found a front on 132 of 134."""
    import glob
    import os
    here = os.path.dirname(os.path.abspath(__file__))
    files = glob.glob(os.path.join(here, "..", "..", "..", "deli_counter", "build", "*.gameplay.json"))
    if not files:
        return
    # AN EMPTY HAS NO FRONT DOOR TO FIND (0.137.0): Deli Counter 0.174.0's
    # non-enterable shells record no openings by design, so they are not
    # buildings this rule turns. Skipped by Deli Counter's own word for them.
    def _empty(f):
        v = f.replace(".gameplay.json", ".validation.json")
        try:
            with open(v, encoding="utf-8") as fh:
                return json.load(fh).get("facade") is True
        except (OSError, ValueError):
            return False
    files = [f for f in files if not _empty(f)]
    found = sum(1 for f in files if FD.front_wall_of(f)[0] is not None)
    assert found >= 0.95 * len(files), (found, len(files))
