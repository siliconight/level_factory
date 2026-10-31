"""The buildings' merge, run (0.227.0): a slot holding what the merge cannot carry stays whole.

The merge copies a StaticBody3D out whole and a MeshInstance3D's surfaces into the merged meshes, and removes each slot
it took apart. 0.223.0 to 0.226.2 so removed Deli Counter's `Ladders` -- Area3D climb volumes, group `ladder_area3d`,
which the walk's player and bot climb -- and its `Markers`, the grouped spawns and objectives a recipient game finds
with `get_nodes_in_group`: the factory's install test 11's walk read "no ladder_area3d in scene", and its
`docs/findings/merge_ladders_227/` counted the loss on two levels' packages.

THE GODOT HALF RUNS HERE FOR REAL, on a small building written as Deli Counter's composer writes one: two wall
modules of one storey's side, one with a collider and one with a bare `ATT_*` socket; a prop whose module holds a lamp;
the `Ladders` and the `Markers`. `test_merge_buildings.py` holds the same rules to the source. Skipped where no Godot
is installed (`LF_GODOT`, then `DC_GODOT`, then `LOT_GODOT`, then the usual Windows path).

FAILS ON 0.226.2: the ladder, its shape and the marker are gone from the saved scene, the lamp's prop is merged, and
the report carries no `kept_carrying`.

Run:  python -m pytest tests/unit/test_merge_buildings_godot.py -q
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from packages.exporting import merge_buildings as M  # noqa: E402

SCENE = "res://lot/b/site.tscn"

BUILDING = """[gd_scene format=3]

[sub_resource type="BoxMesh" id="BoxMesh_box"]

[sub_resource type="StandardMaterial3D" id="Mat_wall"]
resource_name = "M_wall"

[sub_resource type="BoxShape3D" id="Shape_box"]

[sub_resource type="StandardMaterial3D" id="Mat_glass"]
resource_name = "M_glass"
transparency = 1

[node name="Building" type="Node3D"]

[node name="ext_0_N_0" type="Node3D" parent="."]

[node name="Mesh" type="MeshInstance3D" parent="ext_0_N_0"]
mesh = SubResource("BoxMesh_box")
surface_material_override/0 = SubResource("Mat_wall")

[node name="Body" type="StaticBody3D" parent="ext_0_N_0"]

[node name="Shape" type="CollisionShape3D" parent="ext_0_N_0/Body"]
shape = SubResource("Shape_box")

[node name="ext_0_N_1" type="Node3D" parent="."]
transform = Transform3D(1, 0, 0, 0, 1, 0, 0, 0, 1, 2, 0, 0)

[node name="Mesh" type="MeshInstance3D" parent="ext_0_N_1"]
mesh = SubResource("BoxMesh_box")
surface_material_override/0 = SubResource("Mat_wall")

[node name="ATT_top" type="Node3D" parent="ext_0_N_1"]
transform = Transform3D(1, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0.5, 0)

[node name="ext_0_N_open1" type="Node3D" parent="."]
transform = Transform3D(1, 0, 0, 0, 1, 0, 0, 0, 1, 4, 0, 0)

[node name="Mesh" type="MeshInstance3D" parent="ext_0_N_open1"]
mesh = SubResource("BoxMesh_box")
surface_material_override/0 = SubResource("Mat_wall")

[node name="Pane" type="MeshInstance3D" parent="ext_0_N_open1"]
mesh = SubResource("BoxMesh_box")
surface_material_override/0 = SubResource("Mat_glass")

[node name="lamp_r1_0" type="Node3D" parent="."]
transform = Transform3D(1, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 3)

[node name="Mesh" type="MeshInstance3D" parent="lamp_r1_0"]
mesh = SubResource("BoxMesh_box")
surface_material_override/0 = SubResource("Mat_wall")

[node name="Body" type="StaticBody3D" parent="lamp_r1_0"]

[node name="Shape" type="CollisionShape3D" parent="lamp_r1_0/Body"]
shape = SubResource("Shape_box")

[node name="Light" type="OmniLight3D" parent="lamp_r1_0"]

[node name="Ladders" type="Node3D" parent="."]

[node name="Ladder_ladder_0" type="Area3D" parent="Ladders" groups=["ladder_area3d", "dc_ladder"]]
transform = Transform3D(1, 0, 0, 0, 1, 0, 0, 0, 1, 4, 1.5, 0)
metadata/climb_height = 3.0

[node name="CollisionShape3D" type="CollisionShape3D" parent="Ladders/Ladder_ladder_0"]
shape = SubResource("Shape_box")

[node name="Markers" type="Node3D" parent="."]

[node name="ATTACKER_SPAWN" type="Node3D" parent="Markers" groups=["attacker_spawn", "dc_marker"]]
transform = Transform3D(1, 0, 0, 0, 1, 0, 0, 0, 1, -3, 0, 2)
metadata/marker_type = "attacker_spawn"
"""

ROOMS = {"rooms": [{"id": "shop", "floor": 0.0, "bounds": [-10.0, -10.0, 10.0, 10.0]}]}

#: a saved scene's node header: name, type, parent, and the rest of the line (groups, unique_id, ...)
NODE = re.compile(r'^\[node name="([^"]+)" type="([^"]+)" parent="([^"]+)"(.*)\]$', re.M)


def _godot() -> str | None:
    for env in ("LF_GODOT", "DC_GODOT", "LOT_GODOT"):
        p = os.environ.get(env)
        if p and Path(p).is_file():
            return p
    usual = Path("C:/Godot/4.7/Godot_v4.7-stable_win64_console.exe")
    if usual.is_file():
        return str(usual)
    return shutil.which("godot")


godot_required = pytest.mark.skipif(_godot() is None, reason="no Godot binary; this test runs the merge")


@pytest.fixture(scope="module")
def merged(tmp_path_factory):
    """(report, the saved scene's text, Godot's log) of one merge of the small building."""
    proj = tmp_path_factory.mktemp("merge") / "proj"
    (proj / "lot" / "b").mkdir(parents=True)
    (proj / "project.godot").write_text('config_version=5\n\n[application]\n\nconfig/name="merge"\n',
                                        encoding="utf-8")
    (proj / M.MERGE_SCRIPT.name).write_bytes(M.MERGE_SCRIPT.read_bytes())
    (proj / "lot" / "b" / "site.tscn").write_text(BUILDING, encoding="utf-8")
    (proj / "lot" / "b" / M.ROOMS_NAME).write_text(json.dumps(ROOMS), encoding="utf-8")
    report = proj.parent / M.REPORT_NAME
    out = subprocess.run([_godot(), "--headless", "--path", str(proj), "--script", "res://" + M.MERGE_SCRIPT.name,
                          "--", str(report), SCENE], capture_output=True, text=True, timeout=180)
    log = out.stdout + out.stderr
    # an unrecognised shape FAILS: no report is a merge that never ran, not one that kept everything
    assert report.is_file(), log
    rep = json.loads(report.read_text(encoding="utf-8"))
    return rep, (proj / "lot" / "b" / "site.tscn").read_text(encoding="utf-8"), log


def _nodes(scene: str) -> dict:
    """{(parent, name): (type, the header's rest)} of every typed node the saved scene writes."""
    return {(m.group(3), m.group(1)): (m.group(2), m.group(4)) for m in NODE.finditer(scene)}


def _groups(rest: str) -> set:
    g = re.search(r'groups=\[([^\]]*)\]', rest)
    return set(re.findall(r'"([^"]+)"', g.group(1))) if g else set()


@godot_required
def test_the_merge_ran_and_its_report_is_believed(merged):
    rep, _scene, log = merged
    assert rep["ok"], log
    row = rep["scenes"][0]
    assert row["error"] is None, log
    # the two wall modules and the window's surround, one storey's side, into one mesh; the pane its own (0.258.0);
    # the lamp's prop, the ladders and the markers left whole
    assert (row["slots_merged"], row["surfaces_in"], row["merged"], row["colliders"]) == (3, 3, 1, 1), row
    assert (row["glass_surfaces"], row["glass_meshes"]) == (1, 1), row
    M.check(rep, [SCENE])


@godot_required
def test_the_ladder_and_the_marker_stay_where_deli_counter_put_them(merged):
    _rep, scene, log = merged
    nodes = _nodes(scene)
    typ, rest = nodes.get(("Ladders", "Ladder_ladder_0"), (None, ""))
    assert typ == "Area3D" and _groups(rest) == {"ladder_area3d", "dc_ladder"}, log
    assert nodes.get(("Ladders/Ladder_ladder_0", "CollisionShape3D"), (None,))[0] == "CollisionShape3D"
    assert "metadata/climb_height = 3.0" in scene
    typ, rest = nodes.get(("Markers", "ATTACKER_SPAWN"), (None, ""))
    assert typ == "Node3D" and _groups(rest) == {"attacker_spawn", "dc_marker"}
    assert 'metadata/marker_type = "attacker_spawn"' in scene


@godot_required
def test_a_module_holding_a_lamp_stays_whole_and_keeps_its_own_collider(merged):
    """Kept before any collider is copied out: its body stands once, in the module, never also under KitCollision."""
    rep, scene, _log = merged
    nodes = _nodes(scene)
    assert nodes.get(("lamp_r1_0", "Light"), (None,))[0] == "OmniLight3D"
    assert nodes.get(("lamp_r1_0", "Body"), (None,))[0] == "StaticBody3D"
    assert [k for k in nodes if k[0] == "KitCollision"] == [("KitCollision", "Body")], sorted(nodes)
    assert rep["scenes"][0]["kept_carrying"] == ["lamp_r1_0: Light (OmniLight3D)",
                                                 "Ladders: Ladder_ladder_0 (Area3D)",
                                                 "Markers: ATTACKER_SPAWN (group attacker_spawn)"]


@godot_required
def test_an_openings_surround_merges_and_its_pane_stands_alone(merged):
    """0.258.0: the window slot is gone, its wall surface in `MergedR_0`, its glass in `GlassR_0`. FAILS ON 0.257.0,
    which kept `ext_0_N_open1` whole."""
    _rep, scene, _log = merged
    nodes = _nodes(scene)
    assert not [k for k in nodes if "ext_0_N_open1" in k], sorted(nodes)
    assert nodes.get((".", "GlassR_0"), (None,))[0] == "MeshInstance3D"


@godot_required
def test_the_merged_mesh_is_given_its_draw_distance_and_the_pane_keeps_every_distance(merged):
    """0.273.0: `MergedR_0` saved with a range from its own size, `GlassR_0` with none. FAILS ON 0.272.0, which gave
    a merged mesh none."""
    rep, scene, _log = merged
    body = scene.split('[node name="MergedR_0"', 1)[1].split("[node ", 1)[0]
    end = re.search(r"^visibility_range_end = ([0-9.e+-]+)$", body, re.M)
    margin = re.search(r"^visibility_range_end_margin = ([0-9.e+-]+)$", body, re.M)
    assert end and margin, body
    assert abs(float(margin.group(1)) - 0.1 * float(end.group(1))) < 1e-3 * float(end.group(1))
    pane = scene.split('[node name="GlassR_0"', 1)[1].split("[node ", 1)[0]
    assert "visibility_range_end" not in pane
    assert (rep["scenes"][0]["draw_ranged"], rep["scenes"][0]["draw_kept_lit"]) == (1, 0)


def test_a_bare_socket_does_not_keep_its_module_whole(merged):
    """Zoo's `ATT_*` sockets are bare Node3Ds -- a transform, which the merged mesh already holds."""
    _rep, scene, _log = merged
    nodes = _nodes(scene)
    assert not [k for k in nodes if k[0] in ("ext_0_N_0", "ext_0_N_1") or k[1] in ("ext_0_N_0", "ext_0_N_1")]
    assert nodes.get((".", "MergedR_0"), (None,))[0] == "MeshInstance3D"
