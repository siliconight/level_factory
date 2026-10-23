"""The ground under the backdrop (0.211.0, the walker's walk of 2026-10-14, finding 2), a frame round the plate
(0.237.0, the walker's walk of cold run 9383, finding 1).

The walker at urban_row_001's east fence: "looks like the bottom of the level just disappears". The backdrop's
scene held its rowhomes and its water tower and no ground, so past the plate's edge they stood on nothing -- the sky
and the fog below and between them, hidden from the street by the fence and seen from beside it. `with_ground` lays
dark ground under the backdrop, a little below the plate.

0.237.0: across the plate, that ground was a black lid on every opening into a basement -- inside a building's ground
slab, under its stair, its ladder hole, its broken floor. The walker, of deli_a03's basement stair: "this shouldn't
look pitch black". The ground is now laid round `plate_bound`, never across it.

THE TEST THAT MATTERS IS `test_no_ground_stands_under_the_plate_or_a_building`. FAILS ON 0.236.1: there is no
`plate_bound` and the ground is one plane across the plate.
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
#: restaurant_row_001 at seed 9003 as cold run 9384 drew it: its plate and the building whose ladder hole the ground
#: lidded, deli_a03 (`b0`), 38 x 28 m at (-51, 2.51)
DRAWN = {"ground": {"size_x": 181, "size_y": 96},
         "buildings": [{"id": "b0", "at": [-51, 2.51], "rot": 0, "_footprint": [38.0, 28.0]},
                       {"id": "b1", "at": [60, -20], "rot": 90, "_footprint": [10.0, 30.0]}]}
#: their footprints, b1 quarter-turned
BUILDINGS = [(-70.0, -11.49, -32.0, 16.51), (45.0, -25.0, 75.0, -15.0)]
#: deli_a03's ground-floor ladder hole in the site's metres: Godot world x -58.55..-57.45, z 9.39..10.69
LADDER_HOLE = (-58.55, -10.69, -57.45, -9.39)


def _strips(text):
    """The scene's ground strips back out of its MultiMesh buffer, as (x0, y0, x1, y1) in the spec's metres."""
    mm = re.search(r'\[sub_resource type="MultiMesh" id="BackdropGround_mm"\]\ntransform_format = 1\n'
                   r'instance_count = (\d+)\nmesh = SubResource\("BackdropGround_mesh"\)\n'
                   r'buffer = PackedFloat32Array\(([^)]*)\)', text)
    assert mm, "no ground MultiMesh"
    v = [float(x) for x in mm.group(2).split(",")]
    assert len(v) == 12 * int(mm.group(1))
    out = []
    for i in range(0, len(v), 12):
        sx, cx, y, sz, cz = v[i], v[i + 3], v[i + 7], v[i + 10], v[i + 11]
        assert y == B.GROUND_Y and v[i + 5] == 1 and v[i + 1] == v[i + 2] == v[i + 4] == v[i + 6] == 0
        out.append((cx - sx / 2, -cz - sz / 2, cx + sx / 2, -cz + sz / 2))
    return out


def _overlap(a, b):
    return max(0.0, min(a[2], b[2]) - max(a[0], b[0])) * max(0.0, min(a[3], b[3]) - max(a[1], b[1]))


def test_without_a_plate_the_ground_is_one_quad_spanning_the_backdrop_and_its_margin():
    text, ground = B.with_ground(SCENE, ORDERS)
    m = B.GROUND_MARGIN
    want_w, want_d = (150.0 - -120.0) + 2 * m, (70.0 - -60.0) + 2 * m
    assert ground["size"] == [round(want_w, 3), round(want_d, 3)] and ground["centre"] == [15.0, 5.0]
    assert ground["draw_calls"] == 1 and ground["shaded"] is False and ground["keep_out"] is None
    (s,) = _strips(text)
    assert [round(c, 3) for c in s] == [-120.0 - m, -60.0 - m, 150.0 + m, 70.0 + m]
    assert B.GROUND_Y < 0


def test_plate_bound_is_the_plate_and_every_building_turned_as_lot_turns_it():
    # the plate +-90.5 x +-48, both buildings on it; a quarter-turned one past a small plate widens the bound
    assert B.plate_bound(DRAWN) == (-90.5, -48.0, 90.5, 48.0)
    far = {"ground": {"size_x": 20, "size_y": 20, "at": [5, 5]},
           "buildings": [{"at": [40, 0], "rot": 90, "_footprint": [10.0, 30.0]}]}
    assert B.plate_bound(far) == (-5.0, -5.0, 55.0, 15.0)
    assert B.plate_bound({}) is None


def test_no_ground_stands_under_the_plate_or_a_building():
    keep = B.plate_bound(DRAWN)
    text, ground = B.with_ground(SCENE, ORDERS, keep_out=keep)
    strips = _strips(text)
    assert len(strips) == 4 and ground["strips"] == [[round(c, 3) for c in s] for s in strips]
    for s in strips:
        assert _overlap(s, keep) < 1e-6, s
        assert _overlap(s, LADDER_HOLE) == 0.0, s
        for b in BUILDINGS:
            assert _overlap(s, b) == 0.0, (s, b)
    # and together they are all the ground there was, less the plate: nothing past the plate went missing
    w, d = ground["size"]
    total = sum((s[2] - s[0]) * (s[3] - s[1]) for s in strips)
    assert abs(total - (w * d - (keep[2] - keep[0]) * (keep[3] - keep[1]))) < 1e-3


def test_the_ground_reaches_past_a_plate_wider_than_its_pieces():
    keep = (-200.0, -10.0, 200.0, 10.0)
    _text, ground = B.with_ground(SCENE, ORDERS, keep_out=keep)
    x0 = ground["centre"][0] - ground["size"][0] / 2
    x1 = ground["centre"][0] + ground["size"][0] / 2
    assert x0 <= -200.0 - B.GROUND_MARGIN + 1e-6 and x1 >= 200.0 + B.GROUND_MARGIN - 1e-6


def test_the_ground_is_after_the_root_and_the_load_steps_count_it():
    text, _ground = B.with_ground(SCENE, ORDERS, keep_out=B.plate_bound(DRAWN))
    assert text.startswith("[gd_scene load_steps=6 format=3]")
    assert text.index('[node name="site_backdrop"') < text.index('[node name="BackdropGround"')
    for rid in ("BackdropGround_mesh", "BackdropGround_mat", "BackdropGround_mm"):
        assert text.index('id="%s"]' % rid) < text.index('[node name="site_backdrop"')
    node = text[text.index('[node name="BackdropGround"'):]
    assert node.startswith('[node name="BackdropGround" type="MultiMeshInstance3D" parent="."]')
    assert 'cast_shadow = 0' in node and 'material_override = SubResource("BackdropGround_mat")' in node
    assert text.count("MultiMeshInstance3D") == SCENE.count("MultiMeshInstance3D") + 1


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


def test_the_package_lays_it_round_the_drawn_plate():
    # the call site, read off the source: ship_backdrop hands with_ground the drawn spec's plate_bound
    src = Path(B.__file__).read_text(encoding="utf-8")
    assert 'with_ground(text, manifest["orders"], keep_out=plate_bound(drawn))' in src
