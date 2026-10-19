"""A seam is not a hole: the drop-edge lattice is laid off the round coordinates (0.219.0, the factory's roadmap 173).

Cold run 9333's export refused three "drops" on deli_a03's storey-1 floor. Its slab's cut and its stair's discharge
plate are authored flush on the gate's 0.5 m lattice, site x -64.0, and are not flush in float32: the cut is stored at
local x -13.000000953674316, and the plate's body, at local -11.800000190734863 under the building's -51, composes to
-62.799999237, so a 1.7 um gap straddles x -64.0 and a ray cast exactly there fell through it to the ground (the
factory's docs/findings/breadth_sweep_2026-10-19/seam_ulps.gd). This rebuilds that seam from those floats -- a trimesh
slab and a convex plate, as the GLB's -colonly and -convcolonly nodes import -- over a ground plane, and runs the real
instrument through a real Godot at the gate's own cell: nothing may drop along the seam, and the plate's far rim,
which the flood reaches only across the seam, must still be found.

Skipped where no Godot is installed (`LF_GODOT`, then `DC_GODOT`, then `LOT_GODOT`, then the usual Windows path).
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from packages.exporting import drop_edges as D  # noqa: E402

EDGE = D.EDGE_SCRIPT  # the very file the export's gate runs, at its cell
NEAR = D.CELL_M / 2 + 0.01  # an edge row sits at the midpoint of two cells, so within half a cell of its line

# deli_a03's own floats, as its GLB stores them (glTF frame, metres; site x = building x + local x)
BUILDING_X = -51.0
SLAB_Y = 3.1500000953674316
SLAB_HALF_Y = 0.15000000596046448
SLAB_CUT_X = -13.000000953674316
SLAB_FAR_X = -18.9  # deli_a03's slab runs on to -19.0; this end is kept off the lattice so only the seam is on it
PLATE_X = -11.800000190734863
PLATE_Y = 3.1968750953674316
PLATE_HALF_X = 1.2000000476837158
PLATE_HALF_Y = 0.10312499850988388
HALF_Z = 4.9  # both 9.8 m along the seam, their ends off the lattice
SEAM_X = BUILDING_X - 13.0  # -64.0, a lattice line: the grid starts at the ground's corner, x -80
PLATE_FAR_X = BUILDING_X + PLATE_X + PLATE_HALF_X  # -61.6, the plate's east rim


def _godot() -> str | None:
    for env in ("LF_GODOT", "DC_GODOT", "LOT_GODOT"):
        p = os.environ.get(env)
        if p and Path(p).is_file():
            return p
    usual = Path("C:/Godot/4.7/Godot_v4.7-stable_win64_console.exe")
    if usual.is_file():
        return str(usual)
    return shutil.which("godot")


godot_required = pytest.mark.skipif(_godot() is None, reason="no Godot binary; this runs the real instrument")

PROJECT = """config_version=5

[application]
config/name="edge_seam"
run/main_scene="res://main.tscn"
config/features=PackedStringArray("4.7")
"""


def _box_soup(x0, x1, y0, y1, z0, z1):
    """A box as a ConcavePolygonShape3D's triangles, each front-facing outward by Godot's rule: a face's normal is
    (a - c) x (a - b), and a ray meets a trimesh face only from its front."""
    def corner(i, j, k):
        return ((x0, x1)[i], (y0, y1)[j], (z0, z1)[k])
    faces = (  # each face's corners in order round it, and its outward axis
        (((0, 1, 0), (1, 1, 0), (1, 1, 1), (0, 1, 1)), (0, 1, 0)),
        (((0, 0, 0), (1, 0, 0), (1, 0, 1), (0, 0, 1)), (0, -1, 0)),
        (((0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)), (0, 0, -1)),
        (((0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1)), (0, 0, 1)),
        (((0, 0, 0), (0, 1, 0), (0, 1, 1), (0, 0, 1)), (-1, 0, 0)),
        (((1, 0, 0), (1, 1, 0), (1, 1, 1), (1, 0, 1)), (1, 0, 0)),
    )
    out = []
    for quad, outward in faces:
        pts = [corner(*q) for q in quad]
        for a, b, c in ((pts[0], pts[1], pts[2]), (pts[0], pts[2], pts[3])):
            u = [a[i] - c[i] for i in range(3)]
            v = [a[i] - b[i] for i in range(3)]
            n = (u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0])
            if sum(n[i] * outward[i] for i in range(3)) < 0:
                b, c = c, b
            out.extend(a + b + c)
    return out


def _floats(vals) -> str:
    return ", ".join(repr(float(v)) for v in vals)


def _main_scene() -> str:
    slab = _box_soup(SLAB_FAR_X, SLAB_CUT_X, -SLAB_HALF_Y, SLAB_HALF_Y, -HALF_Z, HALF_Z)
    plate = [c for x in (-PLATE_HALF_X, PLATE_HALF_X) for y in (-PLATE_HALF_Y, PLATE_HALF_Y)
             for z in (-HALF_Z, HALF_Z) for c in (x, y, z)]
    slab_w = SLAB_CUT_X - SLAB_FAR_X
    return f"""[gd_scene load_steps=7 format=3]

[sub_resource type="BoxShape3D" id="ground"]
size = Vector3(40, 0.2, 30)

[sub_resource type="BoxMesh" id="ground_mesh"]
size = Vector3(40, 0.2, 30)

[sub_resource type="ConcavePolygonShape3D" id="slab"]
data = PackedVector3Array({_floats(slab)})

[sub_resource type="BoxMesh" id="slab_mesh"]
size = Vector3({slab_w!r}, {2 * SLAB_HALF_Y!r}, {2 * HALF_Z!r})

[sub_resource type="ConvexPolygonShape3D" id="plate"]
points = PackedVector3Array({_floats(plate)})

[sub_resource type="BoxMesh" id="plate_mesh"]
size = Vector3({2 * PLATE_HALF_X!r}, {2 * PLATE_HALF_Y!r}, {2 * HALF_Z!r})

[node name="Main" type="Node3D"]

[node name="Ground" type="StaticBody3D" parent="."]
transform = Transform3D(1, 0, 0, 0, 1, 0, 0, 0, 1, -60, -0.1, 0)

[node name="col" type="CollisionShape3D" parent="Ground"]
shape = SubResource("ground")

[node name="mesh" type="MeshInstance3D" parent="Ground"]
mesh = SubResource("ground_mesh")

[node name="Building" type="Node3D" parent="."]
transform = Transform3D(1, 0, 0, 0, 1, 0, 0, 0, 1, {BUILDING_X!r}, 0, 0)

[node name="slab_col_1" type="StaticBody3D" parent="Building"]
transform = Transform3D(1, 0, 0, 0, 1, 0, 0, 0, 1, 0, {SLAB_Y!r}, 0)

[node name="col" type="CollisionShape3D" parent="Building/slab_col_1"]
shape = SubResource("slab")

[node name="mesh" type="MeshInstance3D" parent="Building/slab_col_1"]
transform = Transform3D(1, 0, 0, 0, 1, 0, 0, 0, 1, {(SLAB_FAR_X + SLAB_CUT_X) / 2!r}, 0, 0)
mesh = SubResource("slab_mesh")

[node name="stair1col_discharge_0" type="StaticBody3D" parent="Building"]
transform = Transform3D(1, 0, 0, 0, 1, 0, 0, 0, 1, {PLATE_X!r}, {PLATE_Y!r}, 0)

[node name="col" type="CollisionShape3D" parent="Building/stair1col_discharge_0"]
shape = SubResource("plate")

[node name="mesh" type="MeshInstance3D" parent="Building/stair1col_discharge_0"]
mesh = SubResource("plate_mesh")
"""


@godot_required
def test_a_seam_on_the_lattice_is_not_a_drop(tmp_path):
    proj = tmp_path / "pkg"
    proj.mkdir()
    (proj / "project.godot").write_text(PROJECT, encoding="utf-8")
    (proj / "main.tscn").write_text(_main_scene(), encoding="utf-8")
    (proj / "walkable_edge.gd").write_text(EDGE.read_text(encoding="utf-8"), encoding="utf-8")
    out = tmp_path / "edges.json"
    run = subprocess.run([_godot(), "--headless", "--path", str(proj), "--script", "res://walkable_edge.gd",
                          "--", str(out), str(D.CELL_M), "-67.0,3.3,0.1"],
                         capture_output=True, text=True, timeout=300)
    assert out.is_file(), run.stdout + run.stderr
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["ok"], report["error"]
    upper = [e for e in report["edges"] if e["y"] > 2.0]
    # along the seam's interior (its ends are the slabs' own corners): a body cannot fall through 1.7 um
    seam = [(e["x"], e["z"], e["drop_m"]) for e in upper if abs(e["x"] - SEAM_X) <= NEAR and abs(e["z"]) < 4.6]
    assert seam == [], seam[:20]
    # the plate's east rim is a real 3.3 m drop, and the flood reaches the plate only across the seam
    assert any(abs(e["x"] - PLATE_FAR_X) <= NEAR and abs(e["z"]) < 4.6 for e in upper), \
        sorted({e["x"] for e in upper})[:40]
