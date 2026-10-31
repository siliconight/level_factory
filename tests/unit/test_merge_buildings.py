"""The enterable buildings' static modules, merged per room cell and material (0.223.0, the factory's roadmap 266).

The Godot half runs only inside Godot; a cold run and the factory's `docs/findings/interior_merge_266/` (the same
merge priced on copies of cold run 9347's package) exercise it. This is the Python half -- which scenes it asks for,
the rooms it hands them in each building's own frame, what it refuses to believe, where in the export it runs -- and
the Godot half's rules held to its source, as `test_merge_empties.py` holds the Empties'. A stub Godot writes the
report, so `merge` goes through its own reading of one.

FAIL ON 0.222.0: there is no `merge_buildings`, and the export merges no building. The lit-face tests (0.224.0) fail
on 0.223.0, which left every module with a lit face whole. The kept-whole tests (0.227.0) fail on 0.226.2, which took
apart a slot holding what the merge cannot carry -- Deli Counter's `Ladders` and `Markers` -- and removed it; where a
Godot is installed `test_merge_buildings_godot.py` runs the Godot half on a small building to the same end.
"""
import json
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from packages.exporting import merge_buildings as M  # noqa: E402

_REPO = Path(__file__).resolve().parents[2]

SITE = '''[gd_scene load_steps=4 format=3]

[ext_resource type="PackedScene" path="lot/deli_a03/site.tscn" id="b1"]
[ext_resource type="PackedScene" path="lot/office/site.tscn" id="b3"]
[ext_resource type="PackedScene" path="lot/gs_empty_rowhome_h/site.tscn" id="b4"]

[node name="Site" type="Node3D"]

[node name="b0" parent="." instance=ExtResource("b1")]
transform = Transform3D(1, 0, 0, 0, 1, 0, -0, 0, 1, -51, 0, -2.51)

[node name="b2" parent="." instance=ExtResource("b3")]
transform = Transform3D(0, 0, 1, 0, 1, 0, -1, 0, 0, 40, 0, 10)

[node name="blocker_0" parent="." instance=ExtResource("b4")]
transform = Transform3D(1, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 30)
'''
ASKED = ["res://lot/deli_a03/site.tscn", "res://lot/office/site.tscn"]

#: Lot's record of the site: a room's bounds in the SITE's plan, its centre in the building's frame. b0 is unturned
#: at (-51, 2.51) on the plan -- Godot's (x, -z) -- so its room's site bounds are its local ones moved by that.
LOT = {"rooms": [
    {"id": "b0/customer_floor", "building": "b0", "story": 0, "bounds": [-70.0, -11.49, -59.0, -0.49],
     "center": [-13.5, -8.5, 0.0]},
    {"id": "b0/manager_office", "building": "b0", "story": 1, "bounds": [-70.0, -11.49, -59.0, -0.49],
     "center": [-10.5, -6.0, 3.3]},
    {"id": "b2/lobby", "building": "b2", "story": 0, "bounds": [38.0, -14.0, 44.0, -6.0],
     "center": [0.0, 0.0, 0.0]},
]}


def _pkg(tmp_path, site=SITE, lot=LOT):
    p = tmp_path / "pkg"
    p.mkdir()
    (p / "site.tscn").write_text(site, encoding="utf-8")
    (p / ".godot").mkdir()
    for s in ASKED:
        (p / s[len("res://"):]).parent.mkdir(parents=True, exist_ok=True)
    g = tmp_path / "site.site.gameplay.json"
    g.write_text(json.dumps(lot), encoding="utf-8")
    return p, g


def _row(scene, **kw):
    r = {"scene": scene, "slots_merged": 519, "meshes_in": 838, "surfaces_in": 1047, "merged": 470,
         "unwrapped": 590, "colliders": 485, "units": {"ext": 24, "int": 7, "roof": 5, "room": 434},
         "lit_surfaces": 132, "lit_meshes": 90, "glass_surfaces": 41, "glass_meshes": 30,
         "draw_ranged": 468, "draw_kept_lit": 2,
         "kept_carrying": ["Ladders: Ladder_ladder_0 (Area3D)", "Markers: LADDER_0 (group dc_marker)"], "error": None}
    r.update(kw)
    return r


def _report(rows, **kw):
    r = {"schema": M.SCHEMA, "ok": True, "error": None, "scenes": rows}
    r.update(kw)
    return r


def _stub_godot(tmp_path, pkg, doc):
    """A stand-in for Godot that writes `doc` as the merge's report."""
    src = tmp_path / "report_src.json"
    src.write_text(json.dumps(doc), encoding="utf-8")
    dst = pkg / M.REPORT_NAME
    if sys.platform == "win32":
        s = tmp_path / "godot.cmd"
        body = '@echo off\r\ncopy /y "{0}" "{1}" >nul\r\nexit /b 0\r\n'.format(src, dst)
    else:
        s = tmp_path / "godot.sh"
        body = "#!/bin/sh\ncp '{0}' '{1}'\nexit 0\n".format(src, dst)
    s.write_text(body, encoding="utf-8")
    if sys.platform != "win32":
        s.chmod(0o755)
    return s


def test_the_buildings_are_the_b_nodes_and_never_a_blocker(tmp_path):
    pkg, _g = _pkg(tmp_path)
    placed = M.placed_buildings(pkg)
    assert list(placed) == ASKED
    assert [n for n, _m in placed["res://lot/deli_a03/site.tscn"]] == ["b0"]
    # rows, as Godot writes them: the quarter turn's basis row by row, then the origin
    assert placed["res://lot/office/site.tscn"][0][1] == ((0.0, 0.0, 1.0, 40.0), (0.0, 1.0, 0.0, 0.0),
                                                          (-1.0, 0.0, 0.0, 10.0))


def test_a_building_node_that_is_not_a_lot_scene_refuses(tmp_path):
    pkg, _g = _pkg(tmp_path, SITE.replace('path="lot/office/site.tscn"', 'path="props/crate.tscn"'))
    with pytest.raises(M.MergeError):
        M.placed_buildings(pkg)


def test_an_unturned_buildings_rooms_come_back_to_its_own_frame():
    """b0 stands at (-51, 2.51) on the site's plan: Deli Counter's customer_floor, [-19, -14, -8, -3], is Lot's
    [-70, -11.49, -59, -0.49]. Back in the building's frame, with its floor off the centre's third number."""
    m = ((1.0, 0.0, 0.0, -51.0), (0.0, 1.0, 0.0, 0.0), (0.0, 0.0, 1.0, -2.51))
    got = M.local_rooms(LOT["rooms"], "b0", m)
    assert got == [{"id": "customer_floor", "floor": 0.0, "bounds": [-19.0, -14.0, -8.0, -3.0]},
                   {"id": "manager_office", "floor": 3.3, "bounds": [-19.0, -14.0, -8.0, -3.0]}]


def test_a_turned_buildings_rooms_turn_back():
    """A quarter turn: the node sends its local +x to the site's -z. A room 6 m along the site's x and 8 m along
    its plan y, at (41, -10) on the plan, is 8 m along the building's own x and 6 m along its y."""
    m = ((0.0, 0.0, 1.0, 40.0), (0.0, 1.0, 0.0, 0.0), (-1.0, 0.0, 0.0, 10.0))
    got = M.local_rooms(LOT["rooms"], "b2", m)
    assert len(got) == 1 and got[0]["id"] == "lobby"
    x0, y0, x1, y1 = got[0]["bounds"]
    assert (round(x1 - x0, 4), round(y1 - y0, 4)) == (8.0, 6.0)
    # and the box is where the inverse puts the site's corners: site Godot (38, 0, 14) -> local (-4, 0, -2), the
    # plan's (-4, 2); (44, 0, 6) -> (4, 0, 4), the plan's (4, -4)
    assert (x0, y0, x1, y1) == (-4.0, -4.0, 4.0, 2.0)


def test_rooms_are_written_beside_each_scene(tmp_path):
    pkg, g = _pkg(tmp_path)
    out = M.write_rooms(pkg, M.placed_buildings(pkg), g)
    assert out == {"res://lot/deli_a03/site.tscn": 2, "res://lot/office/site.tscn": 1}
    doc = json.loads((pkg / "lot" / "deli_a03" / M.ROOMS_NAME).read_text(encoding="utf-8"))
    assert [r["id"] for r in doc["rooms"]] == ["customer_floor", "manager_office"]


def test_a_building_lot_records_no_room_for_refuses(tmp_path):
    lot = {"rooms": [r for r in LOT["rooms"] if r["building"] != "b2"]}
    pkg, g = _pkg(tmp_path, lot=lot)
    with pytest.raises(M.MergeError):
        M.write_rooms(pkg, M.placed_buildings(pkg), g)


def test_a_site_without_buildings_asks_for_nothing_and_runs_nothing(tmp_path):
    site = "\n".join(ln for ln in SITE.splitlines() if not re.match(r'\[node name="b\d', ln))
    pkg, g = _pkg(tmp_path, site)
    rep = M.merge(pkg, None, g)
    assert rep["ok"] and rep["scenes"] == []


def test_no_godot_or_no_lot_record_refuses(tmp_path):
    pkg, g = _pkg(tmp_path)
    with pytest.raises(M.MergeError):
        M.merge(pkg, None, g)
    with pytest.raises(M.MergeError):
        M.merge(pkg, _stub_godot(tmp_path, pkg, _report([_row(s) for s in ASKED])), tmp_path / "missing.json")


def test_a_finished_merge_is_believed_and_leaves_no_rooms_behind(tmp_path):
    pkg, g = _pkg(tmp_path)
    rep = M.merge(pkg, _stub_godot(tmp_path, pkg, _report([_row(s) for s in ASKED])), g)
    assert [r["scene"] for r in rep["scenes"]] == ASKED
    assert not (pkg / M.MERGE_SCRIPT.name).exists()
    assert not list(pkg.rglob(M.ROOMS_NAME))


@pytest.mark.parametrize("doc", [
    _report([_row(ASKED[0])]),                                   # a scene missing
    _report([_row(s) for s in ASKED], schema="something.else"),  # not this report
    _report([_row(s) for s in ASKED], ok=False, error="boom"),   # said it failed
    _report([_row(ASKED[0]), _row(ASKED[1], unwrapped=12)]),     # a mesh with no lightmap UV
    _report([_row(ASKED[0]), _row(ASKED[1], unwrapped=470)]),    # the lit meshes not unwrapped
    _report([_row(ASKED[0]), _row(ASKED[1], unwrapped=560)]),    # the glass meshes not unwrapped (0.258.0)
    _report([_row(ASKED[0]), _row(ASKED[1], glass_meshes=0)]),   # glass surfaces in no mesh
    # a merge before 0.258.0, which kept every opening whole and counted no glass
    _report([_row(ASKED[0]), {k: v for k, v in _row(ASKED[1]).items() if k != "glass_surfaces"}]),
    _report([_row(ASKED[0]), _row(ASKED[1], lit_meshes=0)]),     # lit surfaces in no mesh
    _report([_row(ASKED[0]), {k: v for k, v in _row(ASKED[1]).items() if k != "lit_surfaces"}]),
    _report([_row(ASKED[0]), _row(ASKED[1], merged=0)]),         # merged nothing
    _report([_row(ASKED[0]), _row(ASKED[1], merged=2000)]),      # more meshes than surfaces
    _report([_row(ASKED[0]), _row(ASKED[1], colliders=0)]),      # lost the collision
    _report([_row(ASKED[0]), _row(ASKED[1], units={})]),         # says nothing of its units
    _report([_row(ASKED[0]), _row(ASKED[1], error="cannot load")]),
    _report([_row(ASKED[0]), {"scene": ASKED[1]}]),              # a row of nothing
    # an older merge's report (0.226.2 and before), which removed what it could not carry, and a count for the list
    _report([_row(ASKED[0]), {k: v for k, v in _row(ASKED[1]).items() if k != "kept_carrying"}]),
    _report([_row(ASKED[0]), _row(ASKED[1], kept_carrying=2)]),
])
def test_an_unfinished_or_unrecognised_merge_refuses(tmp_path, doc):
    pkg, g = _pkg(tmp_path)
    with pytest.raises(M.MergeError):
        M.merge(pkg, _stub_godot(tmp_path, pkg, doc), g)


def test_it_runs_after_the_empties_merge_and_before_the_light_bake():
    src = (_REPO / "packages" / "exporting" / "export.py").read_text(encoding="utf-8")
    occ = src.index("occ = emit(export_dir, godot_executable)")
    empties = src.index("_merge_empties(export_dir, godot_executable)")
    buildings = src.index("_merge_buildings(export_dir, godot_executable, lot_gameplay)")
    bake = src.index("_bake_lights(export_dir, godot_executable")
    assert occ < empties < buildings < bake


def test_the_profile_merges_by_default():
    from packages.exporting.export import ExportProfile
    assert ExportProfile().merge_buildings is True


def test_the_godot_half_ships_with_the_python_half():
    assert M.MERGE_SCRIPT.is_file()
    text = M.MERGE_SCRIPT.read_text(encoding="utf-8")
    assert re.search(r'^const SCHEMA := "' + re.escape(M.SCHEMA) + '"$', text, re.M)


def _func(text, name):
    a = text.index("func %s(" % name)
    b = text.find("\nfunc ", a + 1)
    return text[a:b if b > 0 else len(text)]


def test_what_a_merge_leaves_alone():
    """Held to the Godot half's source: an interactive slot, anything animated, scripted or shader-driven, the
    collision base and the covers are never taken apart. An OPENING is, since 0.258.0 (`test_an_openings_glass_...`)."""
    text = M.MERGE_SCRIPT.read_text(encoding="utf-8")
    keep = _func(text, "_mergeable")
    for needle in ('"GreyboxBase"', '"Dressing"', 'has_meta("interactive_id")',
                   "AnimationPlayer", "get_script() != null", "is ShaderMaterial", "_fixture(m)"):
        assert needle in keep, needle
    assert "_open" not in keep
    # a lit face that is not a fixture's no longer keeps its whole module out (0.224.0); a fixture's still does
    assert "_lit(" not in keep
    assert re.search(r'^const FIXTURE_SUFFIXES: Array\[String\] = \["_Lens", "_Diffuser"\]$', text, re.M)


def test_a_slot_holding_what_a_merge_cannot_carry_stays_whole():
    """0.227.0, held to the Godot half's source: outside a static body, a node that is neither a mesh nor a bare Node3D,
    or any node in a group of its own or with metadata, keeps its slot whole -- decided before any collider is copied
    out, so a kept slot's colliders are never doubled -- and the report names the slot. FAILS ON 0.226.2, which took
    Deli Counter's `Ladders` and `Markers` apart and removed them (the factory's install test 11's walk)."""
    text = M.MERGE_SCRIPT.read_text(encoding="utf-8")
    carry = _func(text, "_cannot_carry")
    for needle in ("if p is StaticBody3D:", "n.get_groups()", 'begins_with("_")', "n.get_meta_list()",
                   'not (n is MeshInstance3D) and n.get_class() != "Node3D"'):
        assert needle in carry, needle
    merge = _func(text, "_merge_scene")
    held = merge.index("var held: String = _held(child, nodes)")
    assert merge.index("if not _mergeable(child, nodes):") < held
    assert held < merge.index("var unit := _unit(") < merge.index("body.duplicate()")
    assert '(row["kept_carrying"] as Array).append(' in merge


def test_a_lit_face_stays_its_own_instances_mesh():
    """0.224.0: Lux finds a lit face by material and by place -- the failing fixture dims the one nearest its lamp --
    so each instance's lit surfaces go into one mesh of their own where it stood (`LitR_<n>`), never into a room
    cell's merged mesh."""
    text = M.MERGE_SCRIPT.read_text(encoding="utf-8")
    merge = _func(text, "_merge_scene")
    lit_at = merge.index("if _lit(mat):")
    # the lit branch ends the surface's turn before the key a merged group is filed under
    assert merge.index("continue", lit_at) < merge.index("var key: String = _key(unit, mat, fmt)")
    assert 'lout.name = "LitR_%d" % li' in merge
    assert "LuxFailing.find_lens" in text
    assert re.search(r'^const LIT_SUFFIXES: Array\[String\] = \["_Lens", "_Diffuser", "_Face"\]$', text, re.M)


def test_an_openings_glass_stays_its_own_instances_mesh():
    """0.258.0: an opening's surround merges with its wall -- the walker's seams round doors, breach panels and
    windows (the factory's docs/findings/walk_2026-10-26_panel/, L5-L7) -- and a transparent surface goes into one
    mesh of its own where its instance stood (`GlassR_<n>`), sorted as it always was."""
    text = M.MERGE_SCRIPT.read_text(encoding="utf-8")
    glass = _func(text, "_glass")
    assert "transparency != BaseMaterial3D.TRANSPARENCY_DISABLED" in glass
    merge = _func(text, "_merge_scene")
    pane_at = merge.index("if _glass(mat):")
    assert merge.index("continue", pane_at) < merge.index("var key: String = _key(unit, mat, fmt)")
    assert 'gout.name = "GlassR_%d" % gi' in merge


def test_a_room_unit_is_cut_into_cells():
    """The light cap's rule (the header's price): every room unit carries a cell of the plan, and the cell is the
    one measured."""
    text = M.MERGE_SCRIPT.read_text(encoding="utf-8")
    assert re.search(r"^const CELL_M := 6\.0$", text, re.M)
    room = _func(text, "_room_unit")
    assert 'return "room %s %s" % [best, _cell(px, py)]' in room
    unit = _func(text, "_unit")
    assert 'return "room %s %s" % [rid, _cell(origin.x, -origin.z)]' in unit


def test_a_civic_buildings_pilasters_merge_with_their_side():
    """FAILS ON 0.269.0: a pilaster (Deli Counter >= 0.294.0, `pilaster_<side>_<n>`) stands outside the wall and in no
    room, so it fell to a cell of its own -- a mesh and a draw a pier; the vertical slice's bank priced +34 draws at
    one heading. It joins the ground storey's side, before the room fallback."""
    text = M.MERGE_SCRIPT.read_text(encoding="utf-8")
    unit = _func(text, "_unit")
    rule = 'if name.begins_with("pilaster_") and parts.size() > 1:\n\t\treturn "ext 0 %s" % parts[1]'
    assert rule in unit
    assert unit.index(rule) < unit.index("return _room_unit(origin, rooms)")
