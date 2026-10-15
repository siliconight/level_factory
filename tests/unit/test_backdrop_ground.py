"""The ground under the backdrop (0.211.0, the walker's walk of 2026-10-14, finding 2).

The walker at urban_row_001's east fence: "looks like the bottom of the level just disappears". The backdrop's
scene held its rowhomes and its water tower and no ground, so past the plate's edge they stood on nothing -- the sky
and the fog below and between them, hidden from the street by the fence and seen from beside it. `with_ground` lays
one dark plane under the backdrop, a little below the plate so the plate covers it wherever both stand.

FAILS ON 0.210.0: there is no `with_ground`.
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from packages.exporting import backdrop_layer as B  # noqa: E402

SCENE = ('[gd_scene load_steps=3 format=3]\n\n'
         '[ext_resource type="Mesh" path="res://backdrop/a.res" id="Mesh_a__N"]\n\n'
         '[sub_resource type="MultiMesh" id="MM_a__N"]\ninstance_count = 1\n\n'
         '[node name="site_backdrop" type="Node3D"]\n\n'
         '[node name="dress_a__N" type="MultiMeshInstance3D" parent="."]\nmultimesh = SubResource("MM_a__N")\n')
ORDERS = [{"pos": [-120.0, 70.0, 5.0], "side": "N"}, {"pos": [110.0, -60.0, 5.0], "side": "S"},
          {"pos": [150.0, 10.0, 20.0], "side": "E"}]


def test_one_plane_spans_the_backdrop_and_its_margin_below_the_plate():
    text, ground = B.with_ground(SCENE, ORDERS)
    m = B.GROUND_MARGIN
    want_w, want_d = (150.0 - -120.0) + 2 * m, (70.0 - -60.0) + 2 * m
    assert ground == {"size": [round(want_w, 3), round(want_d, 3)], "y": B.GROUND_Y,
                      "centre": [15.0, 5.0], "draw_calls": 1, "shaded": False}
    size = re.search(r'\[sub_resource type="PlaneMesh" id="BackdropGround_mesh"\]\nsize = Vector2\(([^)]*)\)', text)
    assert size and [float(v) for v in size.group(1).split(",")] == [want_w, want_d]
    # the spec's (x, y) is Godot's (x, -z), as `dressing_scene` maps it; the plane sits under the plate
    node = re.search(r'\[node name="BackdropGround" type="MeshInstance3D" parent="\."\]\n'
                     r'transform = Transform3D\(([^)]*)\)', text)
    assert node and [float(v) for v in node.group(1).split(",")][9:] == [15.0, B.GROUND_Y, -5.0]
    assert B.GROUND_Y < 0 and text.count("BackdropGround") >= 3


def test_the_ground_is_after_the_root_and_the_load_steps_count_it():
    text, _ground = B.with_ground(SCENE, ORDERS)
    assert text.startswith("[gd_scene load_steps=5 format=3]")
    assert text.index('[node name="site_backdrop"') < text.index('[node name="BackdropGround"')
    assert text.index('id="BackdropGround_mesh"]') < text.index('[node name="site_backdrop"')
    assert 'cast_shadow = 0' in text[text.index('[node name="BackdropGround"'):]
    assert text.count("MultiMeshInstance3D") == SCENE.count("MultiMeshInstance3D")


def test_the_ground_takes_no_light():
    """0.215.0 (the factory's roadmap 252): shaded, the plane cost up to +7 draws and +7.20 ms a heading on
    cold run 9308's package; unshaded, +1 draw. The line stands where the priced arm put it, ahead of the
    roughness, so the scene is the priced one byte for byte. Fails on 0.214.0."""
    text, ground = B.with_ground(SCENE, ORDERS)
    mat = re.search(r'\[sub_resource type="StandardMaterial3D" id="BackdropGround_mat"\]\n(.*?)\n\n',
                    text, re.S)
    assert mat and mat.group(1).split("\n") == [
        "albedo_color = Color(%s, %s, %s, 1)" % B.GROUND_RGB, "shading_mode = 0", "roughness = 1.0"]
    assert ground["shaded"] is False


def test_no_orders_no_ground():
    assert B.with_ground(SCENE, []) == (SCENE, None)
