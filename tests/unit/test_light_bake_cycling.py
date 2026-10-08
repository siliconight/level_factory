"""The light bake keeps a cycling rig live (0.160.0, roadmap 213).

A baked stage rig stops cycling (`lux_stage_light_rig.gd`, `_cycles()`), and
`mark_steady_rigs` baked every rig resource without a `failing_kind`. The
cycle is the NODE's (`cycle_period_s`, `colors`); the bake mode is the
RESOURCE's. So the bake reads which resources a cycling node uses and leaves
them as Lux wrote them.

`_cycling_rigs` asks the rig's own question: `cycle_period_s` over 0 across
two or more `colors`. The fixture puts one of each way to fail it beside the
one that passes.

Run:  python -m pytest tests/unit/test_light_bake_cycling.py -q
"""
from __future__ import annotations

from packages.exporting import light_bake as LB

_SCENE = """[gd_scene format=3]

[ext_resource type="Script" path="res://runtime/lux/resources/lux_light_rig.gd" id="49_x"]
[ext_resource type="Script" path="res://runtime/lux/runtime/rigs/lux_stage_light_rig.gd" id="68_s"]

[sub_resource type="Resource" id="steady"]
script = ExtResource("49_x")
rig_name = &"Fluorescent (baked)"

[sub_resource type="Resource" id="tube_failing"]
script = ExtResource("49_x")
failing_kind = 1
rig_name = &"Fluorescent (baked)"

[sub_resource type="Resource" id="stage_cyc"]
script = ExtResource("49_x")
rig_name = &"Stage Light (baked)"
energy = 71.8

[sub_resource type="Resource" id="stage_still"]
script = ExtResource("49_x")
rig_name = &"Stage Light (baked)"

[sub_resource type="Resource" id="stage_one_colour"]
script = ExtResource("49_x")
rig_name = &"Stage Light (baked)"

[sub_resource type="Resource" id="stage_zero"]
script = ExtResource("49_x")
rig_name = &"Stage Light (baked)"

[sub_resource type="Resource" id="stage_shared"]
script = ExtResource("49_x")
rig_name = &"Stage Light (baked)"

[node name="Site" type="Node3D"]

[node name="cyc" type="Node3D" parent="."]
script = ExtResource("68_s")
rig = SubResource("stage_cyc")
colors = PackedColorArray(1, 0, 0, 1, 0, 1, 0, 1)
cycle_period_s = 4.0

[node name="still" type="Node3D" parent="."]
script = ExtResource("68_s")
rig = SubResource("stage_still")
colors = PackedColorArray(1, 0, 0, 1, 0, 1, 0, 1)

[node name="mono" type="Node3D" parent="."]
script = ExtResource("68_s")
rig = SubResource("stage_one_colour")
colors = PackedColorArray(1, 0, 0, 1)
cycle_period_s = 4.0

[node name="zero" type="Node3D" parent="."]
script = ExtResource("68_s")
rig = SubResource("stage_zero")
colors = PackedColorArray(1, 0, 0, 1, 0, 1, 0, 1)
cycle_period_s = 0.0

[node name="shared_still" type="Node3D" parent="."]
script = ExtResource("68_s")
rig = SubResource("stage_shared")
colors = PackedColorArray(1, 0, 0, 1, 0, 1, 0, 1)

[node name="shared_cyc" type="Node3D" parent="."]
script = ExtResource("68_s")
rig = SubResource("stage_shared")
colors = PackedColorArray(1, 0, 0, 1, 0, 1, 0, 1)
cycle_period_s = 6.0
"""


def _block(text: str, rid: str) -> str:
    return text.split(f'id="{rid}"]')[1].split("[")[0]


def test_a_cycling_rig_stays_live(tmp_path):
    """FAILS ON 0.159.0: the cycling stage rig is baked like a steady one."""
    scene = tmp_path / "lux.applied.tscn"
    scene.write_text(_SCENE, encoding="utf-8")
    got = LB.mark_steady_rigs(scene)
    assert got == {"static": 4, "live": 1, "cycling": 2}, got
    text = scene.read_text(encoding="utf-8")
    for rid in ("stage_cyc", "stage_shared"):
        assert "bake_mode" not in _block(text, rid), rid


def test_only_a_rig_that_cycles_stays_live(tmp_path):
    """A still rig, one colour, or a zero period does not cycle at runtime,
    so each is baked like any steady rig; a failing tube stays live as it
    always did."""
    scene = tmp_path / "lux.applied.tscn"
    scene.write_text(_SCENE, encoding="utf-8")
    LB.mark_steady_rigs(scene)
    text = scene.read_text(encoding="utf-8")
    for rid in ("steady", "stage_still", "stage_one_colour", "stage_zero"):
        assert "bake_mode = 1" in _block(text, rid), rid
    assert "bake_mode" not in _block(text, "tube_failing")
