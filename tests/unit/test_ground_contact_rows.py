"""The ground-contact pre-flight reads a `.tscn` Transform3D as Godot does: the basis's rows, then the origin
(0.218.2).

Until 0.218.1 `_transform` built the transpose, on the belief that Godot writes the basis's columns. Godot 4.7 writes
and parses rows (Lot measured `str_to_var` on 2026-09-13: at 30 degrees local +X lands on (0.866, 0, -0.5)). A pure
quarter turn read transposed turns the other way, so a floor box off a turned building's origin landed mirrored
about it; a box centred on the origin, as `test_ground_contact`'s quarter-turn test uses, lands the same either way
and could not tell.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from glb_fixture import write_glb  # noqa: E402

from packages.validation.ground_contact import _transform, read_scene, support_under  # noqa: E402

# Lot's measured case: `lot._godot_transform` at 30 degrees, `Transform3D(c, 0, s, 0, 1, 0, -s, 0, c, ...)`
THIRTY = "transform = Transform3D(0.866025, 0, 0.5, 0, 1, 0, -0.5, 0, 0.866025, 0, 0, 0)\n"

SITE = """[gd_scene load_steps=2 format=3]

[ext_resource type="PackedScene" path="res://shell.glb" id="b1"]

[node name="Site" type="Node3D"]

[node name="b0" parent="." instance=ExtResource("b1")]
transform = Transform3D(6.12323e-17, 0, 1, 0, 1, 0, -1, 0, 6.12323e-17, 6, 0, 0)
"""


def test_lots_measured_turn_reads_as_godot_reads_it():
    m = _transform(THIRTY)
    local_x = (m[0][0], m[1][0], m[2][0])   # where the basis sends local +X
    assert abs(local_x[0] - 0.866025) < 1e-6
    assert abs(local_x[1]) < 1e-9
    assert abs(local_x[2] + 0.5) < 1e-6


def test_an_offset_floor_in_a_quarter_turned_building_lands_where_godot_puts_it(tmp_path):
    # a 4 x 4 m floor 10 m along the shell's own +X, its top at y = 0
    write_glb(tmp_path / "shell.glb", [("floor_off-colonly", (10.0, -0.15, 0.0), (4.0, 0.3, 4.0))])
    (tmp_path / "site.tscn").write_text(SITE, encoding="utf-8")
    reading = read_scene(tmp_path / "site.tscn")
    # b0 turns local +X to world -Z (basis.x = (0, 0, -1)), so the floor stands at (6, -10)
    assert support_under((6.0, 0.9, -10.0), reading.boxes) is not None
    assert support_under((6.0, 0.9, 10.0), reading.boxes) is None
