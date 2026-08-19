"""A dressing manifest becoming a Godot scene.

Two kinds of thing are checked here and they carry different weight.

VERIFIED BY CONSTRUCTION: the coordinate conversion. Lot already solved
Z-up -> Y-up and shipped it on hardware, so these tests pin the transcription
against cases whose answer is known by inspection -- a yaw of zero, a yaw of
ninety degrees. If the transcription drifts from Lot's, that is caught here
rather than by a level whose dressing is rotated.

SETTLED BY GODOT, HAVING BEEN WRONG: the MultiMesh buffer layout. It was
pinned here rather than proved, on the honest ground that Python cannot ask an
engine what it stores -- and it was transposed. `tools/dressing_ab.ps1` read
the transforms back out of a running window and 4372 of 4374 disagreed with
the node scene. The tests below now assert the layout at a yaw whose sine is
not zero, which is the property the old ones lacked: at zero yaw a transposed
basis is the SAME basis, and three of the four buffer tests used zero yaw.

NOT VERIFIABLE WITHOUT GODOT: how a mesh resource is addressed. That one is
still pinned rather than proved.

WHY A ZERO YAW PROVES ALMOST NOTHING HERE, since it is the trap this file fell
into: the identity basis is symmetric, so it survives a transpose unchanged,
as does any pure scale. A test at yaw 0 checks that the twelve floats are laid
out in some consistent order and nothing about WHICH order. Any test of the
basis ordering in this file must use a yaw whose sine is not zero.
"""
from __future__ import annotations

import math

import pytest

from packages.exporting import dressing_scene as DS

STEP_MAX = 0.11716


def order(asset="pebble", pos=(1.0, 2.0, 0.0), yaw=0.0, scale=1.0, **kw):
    o = {"surface_zone_id": "z", "asset_set": "ground_clutter",
         "asset_id": asset, "placement_mode": "cluster", "pos": list(pos),
         "yaw": yaw, "scale": scale, "height_m": 0.06, "height_band": "micro",
         "collision_policy": "none", "in_traversed_space": True,
         "seed_offset": 0, "transparency": "opaque"}
    o.update(kw)
    return o


def manifest(orders=None, **kw):
    m = {"schema": DS.SCHEMA, "site_id": "site",
         "space": "spec/Blender Z-up raw coords",
         "capsule": {"unassisted_step_max_m": STEP_MAX},
         "orders": orders if orders is not None else [order()]}
    m.update(kw)
    return m


PATHS = {"pebble": "res://dress/pebble.tres",
         "weed_tuft": "res://dress/weed_tuft.tres"}


# --- the conversion, which is Lot's ----------------------------------------

def test_origin_maps_site_xyz_to_godot_x_z_negy():
    """`lot.py`: origin: site (x, y, z) -> Godot (x, z_height, -y)."""
    _, _, _, origin = DS.godot_transform((3.0, 7.0, 0.5), 0.0)
    assert origin == (3.0, 0.5, -7.0)


def test_zero_yaw_is_the_identity_basis():
    r0, r1, r2, _ = DS.godot_transform((0, 0, 0), 0.0)
    assert r0 == (1.0, 0.0, 0.0)
    assert r1 == (0.0, 1.0, 0.0)
    assert r2 == (0.0, 0.0, 1.0)


def test_quarter_turn_matches_lots_handedness_flip():
    """The negation is the whole game: yaw about site Z becomes yaw about
    Godot Y with the sign flipped, because the axis swap flips handedness.
    At 90 degrees that is unmistakable -- x goes to +z, z goes to -x."""
    r0, r1, r2, _ = DS.godot_transform((0, 0, 0), math.pi / 2)
    assert r0[0] == pytest.approx(0.0, abs=1e-9)
    assert r0[2] == pytest.approx(1.0)
    assert r2[0] == pytest.approx(-1.0)
    assert r2[2] == pytest.approx(0.0, abs=1e-9)
    assert r1 == (0.0, 1.0, 0.0)


def test_site_plus_x_lands_where_the_axis_map_says():
    """The unlossy form of "the yaw is negated", and the test this file was
    missing. Site +X under yaw r is site (cos r, sin r, 0); the axis map
    (x, y, z) -> (x, z, -y) sends it to Godot (cos r, 0, -sin r). That is
    basis COLUMN 0, which is read DOWN the rows -- (row0[0], row1[0], row2[0]).
    Asserted at a yaw whose sine is not zero, because a transposed basis
    satisfies this at yaw 0 and the whole defect hid there."""
    r = 0.7
    r0, r1, r2, _ = DS.godot_transform((0, 0, 0), r)
    assert (r0[0], r1[0], r2[0]) == \
        pytest.approx((math.cos(r), 0.0, -math.sin(r)))


def test_scale_folds_into_the_basis():
    """A MultiMesh instance transform has no separate scale channel."""
    r0, r1, r2, _ = DS.godot_transform((0, 0, 0), 0.0, scale=2.5)
    assert r0 == (2.5, 0.0, 0.0)
    assert r1 == (0.0, 2.5, 0.0)
    assert r2 == (0.0, 0.0, 2.5)


def test_scale_does_not_move_the_origin():
    _, _, _, origin = DS.godot_transform((4.0, 5.0, 1.0), 0.0, scale=3.0)
    assert origin == (4.0, 1.0, -5.0)


def test_transform3d_string_is_lots_argument_order():
    r0, r1, r2, o = DS.godot_transform((1.0, 2.0, 0.0), 0.0)
    assert DS.transform3d_string(r0, r1, r2, o) == \
        "Transform3D(1, 0, 0, 0, 1, 0, 0, 0, 1, 1, 0, -2)"


# --- the one assumption ----------------------------------------------------

def test_negative_zero_never_reaches_the_scene():
    """A sign on a zero is not information, and it makes two scenes that place
    things identically differ as text -- which is how a rebuild is checked."""
    text = DS.scene_text(manifest([order(yaw=0.0)]), PATHS)
    assert "-0," not in text and "-0)" not in text


def test_multimesh_floats_is_row_major_with_the_origin_interleaved():
    """The shape of the buffer: basis row, that row's origin component, four
    floats at a time. Kept at yaw 0 because it pins the ORIGIN positions, and
    the origin is what this case can actually see -- the identity basis is
    symmetric, so it says nothing about the basis ordering. The tests that
    check that are below, at a yaw whose sine is not zero."""
    r0, r1, r2, o = DS.godot_transform((1.0, 2.0, 0.5), 0.0)
    assert DS.multimesh_floats(r0, r1, r2, o) == [
        1.0, 0.0, 0.0, 1.0,
        0.0, 1.0, 0.0, 0.5,
        0.0, 0.0, 1.0, -2.0,
    ]


def test_the_buffer_is_not_the_transpose_of_itself():
    """The defect, named. `multimesh_floats` used to interleave its three
    tuples as if they were basis columns, which transposes the basis; for a
    pure yaw that is the inverse rotation, so it renders and looks fine. These
    two off-diagonals have opposite signs, so they swap under a transpose and
    this fails the moment the old interleave comes back."""
    yaw = 0.6
    r0, r1, r2, o = DS.godot_transform((0.0, 0.0, 0.0), yaw)
    f = DS.multimesh_floats(r0, r1, r2, o)
    rows = [f[0:3], f[4:7], f[8:11]]
    assert rows[0][2] == pytest.approx(math.sin(yaw))
    assert rows[2][0] == pytest.approx(-math.sin(yaw))


def test_the_buffer_and_the_literal_describe_the_same_transform():
    """The test that should have caught the transpose and could not.

    Its ancestor compared `sorted(floats)` against `sorted(from_literal)`,
    believing the two forms used genuinely different orderings so that only
    the multiset of values could be compared. They do not differ: both are
    row-major, and the only difference is where the origin sits. Sorting threw
    away the single property under test -- and a transpose is a permutation,
    which no multiset comparison can ever see. This compares position by
    position, at a yaw whose sine is not zero.
    """
    r0, r1, r2, o = DS.godot_transform((3.0, -4.0, 0.25), 0.9, scale=1.7)
    floats = DS.multimesh_floats(r0, r1, r2, o)
    literal = DS.transform3d_string(r0, r1, r2, o)
    n = [float(x) for x in literal[len("Transform3D("):-1].split(", ")]
    # %g carries six significant digits, so compare to the precision the text
    # actually has -- not to the precision of the float it came from.
    basis_from_buffer = floats[0:3] + floats[4:7] + floats[8:11]
    assert basis_from_buffer == pytest.approx(n[0:9], rel=1e-5)
    assert [floats[3], floats[7], floats[11]] == \
        pytest.approx(n[9:12], rel=1e-5)


# --- refusals --------------------------------------------------------------

def test_a_collider_in_the_manifest_stops_the_scene():
    m = manifest([order(collision_policy="convex")])
    with pytest.raises(DS.DressingSceneError) as e:
        DS.scene_text(m, PATHS)
    assert "collisionless" in str(e.value)


def test_a_y_up_manifest_is_refused_not_reinterpreted():
    m = manifest()
    m["space"] = "glTF Y-up"
    with pytest.raises(DS.DressingSceneError) as e:
        DS.scene_text(m, PATHS)
    assert "on its side" in str(e.value)


def test_the_honesty_rule_is_rechecked_at_the_last_stage():
    """A manifest is data and data travels. The gate that matters is the one
    standing where the geometry is about to become real."""
    m = manifest([order(height_m=0.30)])
    with pytest.raises(DS.DressingSceneError) as e:
        DS.scene_text(m, PATHS)
    assert "traversed space" in str(e.value)


def test_a_missing_mesh_path_is_an_error_not_a_smaller_layer():
    m = manifest([order(asset="pebble"), order(asset="litter_scrap")])
    with pytest.raises(DS.DressingSceneError) as e:
        DS.scene_text(m, PATHS)
    assert "litter_scrap" in str(e.value)


def test_a_manifest_of_the_wrong_schema_is_refused():
    m = manifest()
    m["schema"] = "patina-dressing/1"
    with pytest.raises(DS.DressingSceneError):
        DS.scene_text(m, PATHS)


# --- the scene -------------------------------------------------------------

def test_one_multimesh_per_asset_not_per_instance():
    """The entire point. Four meshes and four thousand objects is four
    MultiMeshes, not four thousand nodes."""
    orders = [order(asset="pebble") for _ in range(30)] + \
             [order(asset="weed_tuft") for _ in range(20)]
    text = DS.scene_text(manifest(orders), PATHS)
    assert text.count('type="MultiMeshInstance3D"') == 2
    assert text.count("[sub_resource type=\"MultiMesh\"") == 2
    assert "instance_count = 30" in text
    assert "instance_count = 20" in text


def test_the_buffer_is_twelve_floats_per_instance():
    orders = [order() for _ in range(7)]
    text = DS.scene_text(manifest(orders), PATHS)
    buf = text.split("PackedFloat32Array(")[1].split(")")[0]
    assert len(buf.split(",")) == 7 * 12


def test_every_asset_gets_an_ext_resource():
    orders = [order(asset="pebble"), order(asset="weed_tuft")]
    text = DS.scene_text(manifest(orders), PATHS)
    for a, p in PATHS.items():
        assert f'path="{p}"' in text
        assert f'id="Mesh_{a}"' in text


def test_load_steps_counts_the_resources():
    text = DS.scene_text(manifest([order(), order(asset="weed_tuft")]), PATHS)
    head = text.splitlines()[0]
    # 1 (scene) + 2 ext + 2 sub
    assert "load_steps=5" in head


def test_nodes_mode_is_one_node_per_placement():
    orders = [order() for _ in range(5)]
    text = DS.scene_text(manifest(orders), PATHS, mode="nodes")
    assert text.count('type="MeshInstance3D"') == 5
    assert "MultiMesh" not in text
    assert text.count("transform = Transform3D(") == 5


def test_both_modes_place_things_in_the_same_spot():
    """The reference only works if it references the same thing."""
    o = order(pos=(2.0, 3.0, 0.1), yaw=0.7, scale=1.3)
    mm = DS.scene_text(manifest([o]), PATHS)
    nd = DS.scene_text(manifest([o]), PATHS, mode="nodes")
    r0, r1, r2, org = DS.godot_transform(o["pos"], o["yaw"], o["scale"])
    assert DS.transform3d_string(r0, r1, r2, org) in nd
    # As ONE substring, in order. Asserting each float appears somewhere is
    # order-blind, and order was the whole defect -- a transposed buffer holds
    # exactly the same twelve values.
    assert ", ".join(DS._g(v) for v in DS.multimesh_floats(r0, r1, r2, org)) \
        in mm


def test_the_scene_root_is_named_for_the_site():
    text = DS.scene_text(manifest(site_id="coldrun_pawn_job"), PATHS)
    assert '[node name="coldrun_pawn_job_dressing" type="Node3D"]' in text


def test_summarise_counts_draw_calls_honestly():
    orders = [order(asset="pebble") for _ in range(100)] + \
             [order(asset="weed_tuft") for _ in range(100)]
    m = manifest(orders)
    assert DS.summarise(m, "multimesh") == {
        "instances": 200, "meshes": 2, "draw_calls": 2, "mode": "multimesh"}
    assert DS.summarise(m, "nodes")["draw_calls"] == 200


def test_the_same_manifest_writes_the_same_scene():
    m = manifest([order(pos=(i, i * 2, 0)) for i in range(20)])
    assert DS.scene_text(m, PATHS) == DS.scene_text(m, PATHS)
