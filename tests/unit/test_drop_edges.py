"""The gate over undeclared drops: the verdict half, on synthetic instrument reports (0.216.0, factory roadmap 173).

The measurement half is `assets/godot/walkable_edge.gd`, proven on cold runs 9317-9318's packages in the
factory's `docs/findings/drop_edges_173/`; these pin what this module does with a report.

Run: python -m pytest -q tests/unit/test_drop_edges.py
"""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from packages.exporting import drop_edges as D  # noqa: E402

OWNERS = [
    "/root/Mission/Bake/Site/b0/GreyboxBase/slab_col_1",        # 0 a floor
    "/root/Mission/Bake/Site/b0/GreyboxBase/stair1ramp_0",       # 1 a flight
    "/root/Mission/Bake/Site/b0/cartons_r1/CartonStack",         # 2 a thing
    "/root/Mission/Bake/Site/perim_N",                           # 3 the fence
    "/root/Mission/Bake/Site/road_0",                            # 4 the ground
    "/root/Mission/Bake/Site/b0/GreyboxBase/slab_col_0",         # 5 the floor below
]


def _row(x, y, z, drop, indoors, on, to=5):
    return {"x": x, "y": y, "z": z, "drop_m": drop, "indoors": indoors, "on": on, "to": to}


def _report(rows):
    return {"schema": D.SCHEMA, "ok": True, "error": "", "owners": OWNERS, "edges": rows,
            "standable_cells": 1000, "reachable_cells": 900, "drop_edges": len(rows), "guarded": 0,
            "unguarded": len(rows), "links_used": 1, "links_unresolved": 0, "cell_m": 0.5,
            "seed": {"x": 0.0, "y": 0.0, "z": 0.0}}


def _hints(tmp_path, links):
    (tmp_path / "navigation_hints.json").write_text(json.dumps({"links": links}), encoding="utf-8")


#: deli_a01's floor hole as the package carries it: a drop link at storey 1 (3.3 m) whose hole is the cut's
#: rect in the site's frame (Blender XY: Godot x = x, z = -y).
DROP_LINK = {"id": "lot:deli_a01_floor_hole_1_8_-4_navlink", "required_capability": "drop",
             "start_position": [-43.0, 3.3, 1.49], "end_position": [-43.0, 0.0, 1.49], "bidirectional": False,
             "hole": [[-43.75, -2.24], [-42.25, -0.74]]}
#: a ladder from the ground floor to the roof
CLIMB_LINK = {"id": "lot:night_deli_ladder_0_navlink", "required_capability": "climb",
              "start_position": [-43.0, 0.0, 9.49], "end_position": [-43.0, 6.6, 9.49], "bidirectional": True}


def test_floor_like_is_by_owner_not_height():
    assert D._floor_like("GreyboxBase/slab_col_-1") and D._floor_like("GreyboxBase/stair0ramp_1")
    assert D._floor_like("roof_footprint/Roof") and D._floor_like("Site/road_0") and D._floor_like("Site/kerbcut_0L_1")
    assert not D._floor_like("Site/perim_N") and not D._floor_like("cover_3/SimpleCar")
    assert not D._floor_like("GreyboxBase/stair_guard_rail_1_col") and not D._floor_like("GreyboxBase/desk_r1_col")


def test_every_class_claims_its_row(tmp_path):
    _hints(tmp_path, [DROP_LINK, CLIMB_LINK])
    rows = [
        _row(-43.0, 3.3, 1.0, 3.3, True, 0),        # at the declared hole's rim, its storey
        _row(-43.0, 0.0, 9.0, 3.3, True, 0),        # at the ladder's foot, where its hole is
        _row(-60.0, 1.1, -12.5, 1.1, True, 1),      # a flight's own open side
        _row(-54.5, 1.5, -6.0, 1.5, True, 2),       # standing on a carton stack
        _row(10.0, 0.0, 10.0, 999.0, False, 4),     # the plate's rim, under the sky
        _row(-55.0, 3.3, 3.0, 3.3, True, 0),        # a floor, indoors, nothing declares it
    ]
    scan = D.classify(_report(rows), tmp_path)
    assert scan["counts"] == {"declared_drop": 1, "ladder_hole": 1, "stair_side": 1, "top": 1, "outdoors": 1,
                              "undeclared": 1}, scan["counts"]
    assert scan["links"] == {"drop": 1, "climb": 1, "used": 1, "unresolved": 0}
    assert scan["undeclared"][0]["on"] == "GreyboxBase/slab_col_1"
    assert scan["schema"] == D.SCAN_SCHEMA


def test_a_ladder_claims_its_shaft_at_every_floor_it_passes(tmp_path):
    # cold run 9318's deli ladder: ground floor to roof, through the first floor's slab at 3.3 m; its 7 rows there
    # are no END of the link, and a rule that asked for the ends refused them
    _hints(tmp_path, [CLIMB_LINK])
    through = _row(-43.0, 3.3, 8.25, 3.3, True, 0)       # 1.24 m from the column, the floor between its ends
    above = _row(-43.0, 9.9, 8.25, 3.3, True, 0)         # over the ladder's head: not its shaft
    beside = _row(-40.0, 3.3, 9.49, 3.3, True, 0)        # 3 m from the column
    scan = D.classify(_report([through, above, beside]), tmp_path)
    assert scan["counts"]["ladder_hole"] == 1 and scan["counts"]["undeclared"] == 2, scan["counts"]
    assert {(r["y"], r["x"]) for r in scan["undeclared"]} == {(9.9, -43.0), (3.3, -40.0)}


def test_a_declared_hole_claims_its_rim_but_not_another_storey(tmp_path):
    _hints(tmp_path, [DROP_LINK])
    near = _row(-42.0, 3.3, 1.0, 3.3, True, 0)       # 0.25 m outside the rect's edge, same storey
    other = _row(-43.0, 0.0, 1.0, 3.3, True, 5)      # under the hole, the storey below
    scan = D.classify(_report([near, other]), tmp_path)
    assert scan["counts"]["declared_drop"] == 1 and scan["counts"]["undeclared"] == 1


def test_the_verdict_refuses_only_undeclared_indoors(tmp_path):
    _hints(tmp_path, [DROP_LINK, CLIMB_LINK])
    clean = D.classify(_report([_row(-43.0, 3.3, 1.0, 3.3, True, 0), _row(10.0, 0.0, 10.0, 999.0, False, 4)]), tmp_path)
    assert D.assert_declared(tmp_path, clean) is clean
    bad = D.classify(_report([_row(-55.0, 3.3, 3.0, 3.3, True, 0)]), tmp_path)
    with pytest.raises(D.UndeclaredDropError) as err:
        D.assert_declared(tmp_path, bad)
    assert "UNDECLARED_DROP_INDOORS: 1" in str(err.value) and "slab_col_1" in str(err.value)


def test_a_package_without_links_declares_nothing(tmp_path):
    scan = D.classify(_report([_row(-43.0, 3.3, 1.0, 3.3, True, 0)]), tmp_path)
    assert scan["counts"]["undeclared"] == 1 and scan["links"]["drop"] == 0


def test_the_seed_is_the_player_start(tmp_path):
    (tmp_path / "gameplay_anchors.json").write_text(json.dumps({"anchors": [
        {"anchor_type": "extraction", "transform": {"pos": [1, 2, 3]}},
        {"anchor_type": "player_start", "transform": {"pos": [44.85, 0.0, 15.465]}}]}), encoding="utf-8")
    assert D.seed_from_anchors(tmp_path) == [44.85, 0.0, 15.465]
    (tmp_path / "gameplay_anchors.json").write_text(json.dumps({"anchors": []}), encoding="utf-8")
    with pytest.raises(D.NoSeedError):                     # a DropCensusError, but one the export does not refuse on
        D.seed_from_anchors(tmp_path)
    assert issubclass(D.NoSeedError, D.DropCensusError)


def test_a_census_not_taken_certifies_nothing_and_refuses_nothing(tmp_path):
    scan = D.not_taken("gameplay_anchors.json carries no player_start anchor")
    assert scan["counts"] is None and scan["schema"] == D.SCAN_SCHEMA
    assert "NOT TAKEN" in D.summary(scan)
    assert D.assert_declared(tmp_path, scan) is scan


def test_the_extent_is_the_nav_nodes_plus_a_margin(tmp_path):
    (tmp_path / "navigation_hints.json").write_text(json.dumps({
        "nodes": [{"id": "a", "pos": [-70.0, 0.0, -20.0]}, {"id": "b", "pos": [60.0, 3.3, 30.0]}],
        "links": [CLIMB_LINK]}), encoding="utf-8")
    assert D.extent_from_hints(tmp_path, margin=10.0) == "-80.00,-30.00,70.00,40.00"
    (tmp_path / "navigation_hints.json").write_text(json.dumps({"nodes": [], "links": []}), encoding="utf-8")
    assert D.extent_from_hints(tmp_path) == ""                 # nothing to bound by: the instrument walks it all


def test_summary_names_the_refused_class(tmp_path):
    _hints(tmp_path, [])
    scan = D.classify(_report([_row(-55.0, 3.3, 3.0, 3.3, True, 0)]), tmp_path)
    assert "1 UNDECLARED indoors" in D.summary(scan)


def test_the_scan_lands_in_the_package(tmp_path):
    _hints(tmp_path, [])
    scan = D.classify(_report([]), tmp_path)
    path = D.write_scan(tmp_path, scan)
    assert path.name == D.SCAN_NAME and json.loads(path.read_text(encoding="utf-8"))["schema"] == D.SCAN_SCHEMA


def test_the_instrument_ships_with_level_factory():
    assert D.EDGE_SCRIPT.is_file(), D.EDGE_SCRIPT
    text = D.EDGE_SCRIPT.read_text(encoding="utf-8")
    assert "extends SceneTree" in text and "lf.walkable_edge.v1" in text
