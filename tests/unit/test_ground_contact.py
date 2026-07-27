"""Mission points must stand on something (TDD 24.3).

Laser Tag's `validate_map()` fires a ray down from the player spawn and refuses
the map outright when it hits nothing (`NO_WORLD_COLLISION`); the navmesh bake
parses static colliders, so the same hole yields zero polygons. The result is
`runs: 0, grade: "BROKEN"` after the full 900-second timeout — a verdict that
reads like a level review and is actually a missing floor.

The defect that produced this module: a site whose ground slabs formed a ring of
streets around an unfloored block interior, with the spawn, the objective, the
extraction and every enemy inside the void. Seventeen of eighteen mission points
had no slab beneath them and the pipeline ran the evaluation anyway.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from glb_fixture import slab, write_glb  # noqa: E402

from packages.validation.ground_contact import (  # noqa: E402
    MAX_DROP, STAND_TOLERANCE, Box, Reading, axis_aligned,
    check_ground_contact, check_ground_contact_text, mission_points,
    read_scene, read_scene_text, resolver, support_under)


def _slab(name: str, x: float, z: float, sx: float, sz: float,
          top: float = 0.0) -> Box:
    """A 0.5 m ground slab centred so that its top sits at ``top``."""
    return Box(name, (x, top - 0.25, z), (sx, 0.5, sz))


SITE = '''[gd_scene load_steps=5 format=3]

[sub_resource type="BoxShape3D" id="BoxShape_Ground"]
size = Vector3(40, 0.5, 10)

[sub_resource type="BoxShape3D" id="BoxShape_Ground_1"]
size = Vector3(40, 0.5, 10)

[node name="Site" type="Node3D"]

[node name="Ground" type="StaticBody3D" parent="."]
transform = Transform3D(1, 0, 0, 0, 1, 0, 0, 0, 1, 0, -0.25, 20)

[node name="col" type="CollisionShape3D" parent="./Ground"]
shape = SubResource("BoxShape_Ground")

[node name="Ground_1" type="StaticBody3D" parent="."]
transform = Transform3D(1, 0, 0, 0, 1, 0, 0, 0, 1, 0, -0.25, -20)

[node name="col" type="CollisionShape3D" parent="./Ground_1"]
shape = SubResource("BoxShape_Ground_1")
'''

WALK = '''[gd_scene load_steps=3 format=3]

[ext_resource type="PackedScene" path="res://site.tscn" id="site"]

[node name="site_walk" type="Node3D"]
spawn_pos = Vector3(0, 1, 20)
objective_pos = Vector3(0, 0, -20)
extraction_pos = Vector3(0, 0, 20)

[node name="Nav" type="NavigationRegion3D" parent="."]

[node name="Site" parent="./Nav" instance=ExtResource("site")]
'''


# ---------------------------------------------------------------------------
# support_under: the arithmetic that decides "hole" vs "floor"
# ---------------------------------------------------------------------------
def test_a_point_on_a_slab_is_supported():
    boxes = [_slab("Ground", 0.0, 0.0, 40.0, 10.0)]
    assert support_under((5.0, 1.0, 2.0), boxes) is not None


def test_a_point_over_the_gap_between_slabs_is_not():
    """Two streets with a block between them. The block interior is a hole."""
    boxes = [_slab("Street_N", 0.0, 20.0, 40.0, 5.0),
             _slab("Street_S", 0.0, -20.0, 40.0, 5.0)]
    assert support_under((0.0, 1.0, 0.0, ), boxes) is None
    assert support_under((0.0, 1.0, 20.0), boxes) is not None


def test_the_ring_of_streets_around_an_unfloored_block_is_caught():
    """The shipped defect, reduced: four streets, an empty middle, the whole
    mission placed in the middle."""
    boxes = [_slab("N", 0.0, 30.0, 80.0, 6.0), _slab("S", 0.0, -30.0, 80.0, 6.0),
             _slab("E", 40.0, 0.0, 6.0, 60.0), _slab("W", -40.0, 0.0, 6.0, 60.0)]
    reading = Reading(tuple(boxes), ())
    text = ('[gd_scene format=3]\n\n[node name="site_walk" type="Node3D"]\n'
            "spawn_pos = Vector3(0, 1, 0)\n"
            "objective_pos = Vector3(10, 0, 5)\n"
            "extraction_pos = Vector3(0, 0, 30)\n")
    problems = check_ground_contact_text(text, reading)
    assert len(problems) == 1
    assert "2 of 3" in problems[0]
    assert "NO_WORLD_COLLISION" in problems[0]


def test_support_must_be_below_the_point_not_above():
    """A slab overhead is a ceiling. Accepting it would call a basement floored
    by the roof two storeys up."""
    boxes = [_slab("Roof", 0.0, 0.0, 40.0, 40.0, top=12.0)]
    assert support_under((0.0, 0.0, 0.0), boxes) is None


def test_a_point_slightly_inside_its_slab_still_stands_on_it():
    """Spawns are authored at the surface, not floating above it; a hair of
    penetration is normal and must not read as a hole."""
    boxes = [_slab("Ground", 0.0, 0.0, 40.0, 40.0)]
    assert support_under((0.0, -STAND_TOLERANCE / 2.0, 0.0), boxes) is not None


def test_a_point_too_far_above_its_slab_is_a_fall_not_a_stand():
    boxes = [_slab("Ground", 0.0, 0.0, 40.0, 40.0)]
    assert support_under((0.0, MAX_DROP - 0.5, 0.0), boxes) is not None
    assert support_under((0.0, MAX_DROP + 0.5, 0.0), boxes) is None


def test_the_highest_covering_slab_wins():
    """Standing on a mezzanine is standing on the mezzanine, not the floor
    below it."""
    boxes = [_slab("Floor", 0.0, 0.0, 40.0, 40.0),
             _slab("Mezzanine", 0.0, 0.0, 10.0, 10.0, top=3.0)]
    assert support_under((0.0, 3.1, 0.0), boxes).name == "Mezzanine"


# ---------------------------------------------------------------------------
# reading scene text
# ---------------------------------------------------------------------------
def test_nested_and_dot_slash_parents_are_both_read():
    """Godot writes `parent="."` and `parent="./Ground"` for the same tree;
    a reader that handles one and not the other loses half the colliders."""
    reading = read_scene_text(SITE)
    assert len(reading.boxes) == 2
    assert {b.name for b in reading.boxes} == {"Ground/col", "Ground_1/col"}


def test_a_collision_shapes_ancestor_transform_moves_the_box():
    """The shape sits on a child of the body; the body carries the position.
    Reading the shape's own transform alone puts every slab at the origin."""
    reading = read_scene_text(SITE)
    zs = sorted(round(b.centre[2], 3) for b in reading.boxes)
    assert zs == [-20.0, 20.0]


def test_boxes_in_an_instanced_subscene_are_offset_by_the_instance(tmp_path):
    """Lot's mission scene instances the greybox, and the greybox is where the
    ground lives. An unfollowed instance reads as a world with no floor."""
    (tmp_path / "site.tscn").write_text(SITE, encoding="utf-8")
    walk = WALK.replace("[node name=\"Site\" parent=\"./Nav\" instance=ExtResource(\"site\")]",
                        "[node name=\"Site\" parent=\"./Nav\" instance=ExtResource(\"site\")]\n"
                        "transform = Transform3D(1, 0, 0, 0, 1, 0, 0, 0, 1, 100, 0, 0)")
    (tmp_path / "level.tscn").write_text(walk, encoding="utf-8")
    reading = read_scene(tmp_path / "level.tscn")
    assert len(reading.boxes) == 2
    assert all(abs(b.centre[0] - 100.0) < 1e-6 for b in reading.boxes)


def test_a_glb_that_is_not_on_disk_is_opaque_and_says_why(tmp_path):
    """Guessing either way here is how four buildings became invisible to the
    ray. A .glb that cannot be opened is unknown, and the message has to carry
    the reason: "no collision in this shell" and "I never found this shell"
    send an operator to two different places."""
    (tmp_path / "site.tscn").write_text(SITE, encoding="utf-8")
    walk = WALK.replace(
        '[node name="Site" parent="./Nav" instance=ExtResource("site")]',
        '[ext_resource type="PackedScene" path="res://shell.glb" id="b1"]\n'
        '[node name="Site" parent="./Nav" instance=ExtResource("site")]\n\n'
        '[node name="b0" parent="." instance=ExtResource("b1")]')
    (tmp_path / "level.tscn").write_text(walk, encoding="utf-8")
    reading = read_scene(tmp_path / "level.tscn")
    assert any(o.startswith("shell.glb") for o in reading.opaque)
    assert any("not found on disk" in o for o in reading.opaque)


def test_a_rotated_ancestor_is_reported_opaque_not_guessed():
    """A rotated box is no longer axis-aligned; describing its footprint as if
    it were would invent a floor that is not there."""
    text = SITE.replace(
        "transform = Transform3D(1, 0, 0, 0, 1, 0, 0, 0, 1, 0, -0.25, 20)",
        "transform = Transform3D(0.707, 0, -0.707, 0, 1, 0, 0.707, 0, 0.707, 0, -0.25, 20)")
    reading = read_scene_text(text)
    assert [b.name for b in reading.boxes] == ["Ground_1/col"]
    assert "Ground/col" in reading.opaque


def test_a_ladder_trigger_volume_is_not_counted_as_floor():
    """Lot writes each ladder as an Area3D with a tall BoxShape3D climb volume.
    An Area3D stops no ray and bakes into no navmesh: counting its box as ground
    would report a point hanging in mid-air beside the wall as floored, which is
    the false negative that lets a broken map through to a 900-second timeout."""
    text = SITE + (
        '\n[sub_resource type="BoxShape3D" id="BoxShape_Climb"]\n'
        "size = Vector3(2, 8, 2)\n"
        '\n[node name="b0_LADDER_0_climb" type="Area3D" parent="."]\n'
        "transform = Transform3D(1, 0, 0, 0, 1, 0, 0, 0, 1, 30, 4, 0)\n"
        '\n[node name="col" type="CollisionShape3D" parent="./b0_LADDER_0_climb"]\n'
        'shape = SubResource("BoxShape_Climb")\n')
    reading = read_scene_text(text)
    assert [b.name for b in reading.boxes] == ["Ground/col", "Ground_1/col"]
    # And it is not opaque either: the reader knows exactly what it is.
    assert not any("LADDER" in o for o in reading.opaque)
    assert support_under((30.0, 8.0, 0.0), reading.boxes) is None


def test_a_shape_the_reader_cannot_size_is_named_by_its_type():
    """"Player/col" in a blocker message sends an operator looking for a missing
    floor. "Player/col (CapsuleShape3D)" says it is a character capsule that was
    never ground, and that the verdict is not really less certain for it."""
    text = SITE + (
        '\n[sub_resource type="CapsuleShape3D" id="Capsule_P"]\n'
        "radius = 0.4\n"
        '\n[node name="Player" type="CharacterBody3D" parent="."]\n'
        '\n[node name="col" type="CollisionShape3D" parent="./Player"]\n'
        'shape = SubResource("Capsule_P")\n')
    reading = read_scene_text(text)
    assert "Player/col (CapsuleShape3D)" in reading.opaque


def test_a_missing_subscene_is_opaque_rather_than_an_empty_world(tmp_path):
    (tmp_path / "level.tscn").write_text(WALK, encoding="utf-8")
    reading = read_scene(tmp_path / "level.tscn")
    assert reading.boxes == ()
    assert reading.opaque


# ---------------------------------------------------------------------------
# which points get checked
# ---------------------------------------------------------------------------
def test_declared_hooks_are_preferred_over_the_root_properties():
    text = WALK + ('\n[node name="LT_PlayerSpawn" type="Marker3D" parent="."]\n'
                   "transform = Transform3D(1, 0, 0, 0, 1, 0, 0, 0, 1, 7, 1, 8)\n")
    points = mission_points(text)
    assert points == {"LT_PlayerSpawn": (7.0, 1.0, 8.0)}


def test_a_hook_group_container_is_not_itself_a_point():
    """LT_EnemySpawnPoints sits at the origin and holds the real spawns. Testing
    the container would report a phantom hole at (0, 0, 0)."""
    text = WALK + ('\n[node name="LT_EnemySpawnPoints" type="Node3D" parent="."]\n'
                   '\n[node name="Enemy_0" type="Marker3D" parent="./LT_EnemySpawnPoints"]\n'
                   "transform = Transform3D(1, 0, 0, 0, 1, 0, 0, 0, 1, 3, 0, 4)\n")
    points = mission_points(text)
    assert "LT_EnemySpawnPoints" not in points
    assert points["LT_EnemySpawnPoints/Enemy_0"] == (3.0, 0.0, 4.0)


def test_an_unstaged_scene_falls_back_to_the_root_positions():
    points = mission_points(WALK)
    assert set(points) == {"root.spawn_pos", "root.objective_pos",
                           "root.extraction_pos"}


# ---------------------------------------------------------------------------
# the finding itself
# ---------------------------------------------------------------------------
def test_a_fully_floored_scene_reports_nothing(tmp_path):
    (tmp_path / "site.tscn").write_text(SITE, encoding="utf-8")
    (tmp_path / "level.tscn").write_text(WALK, encoding="utf-8")
    assert check_ground_contact(tmp_path / "level.tscn") == []


def test_a_scene_with_no_readable_collision_says_so_rather_than_passing():
    """Silence here would be indistinguishable from "checked, and it is fine" —
    the exact confusion this whole module exists to end."""
    reading = Reading((), ("shell.glb",))
    problems = check_ground_contact_text(WALK, reading)
    assert len(problems) == 1
    assert "no readable box collision" in problems[0]
    assert "shell.glb" in problems[0]


def test_the_message_names_the_points_not_just_the_count():
    """"3 points are floating" sends a human back to the scene to find out
    which. Naming them makes the finding actionable on its own."""
    reading = Reading((_slab("Street", 0.0, 20.0, 40.0, 5.0),), ())
    problems = check_ground_contact_text(WALK, reading)
    assert "root.objective_pos" in problems[0]


def test_a_scene_with_no_mission_points_is_left_to_the_hook_check():
    """One defect, one message. check_scene_hooks already refuses this scene."""
    bare = '[gd_scene format=3]\n\n[node name="x" type="Node3D"]\n'
    assert check_ground_contact_text(bare, Reading((), ())) == []


def test_a_scene_that_is_not_on_disk_is_not_an_assertion(tmp_path):
    assert check_ground_contact(tmp_path / "absent.tscn") == []


# ---------------------------------------------------------------------------
# collision baked into an instanced .glb
# ---------------------------------------------------------------------------
#: A street-and-block site: ground slabs everywhere except a hole cut under
#: each building, and the buildings instanced as .glb shells. This is the exact
#: shape of `site.tscn` as Lot writes it once a building is known to floor
#: itself -- the ground stops at the footprint because the shell takes over.
BLOCK = '''[gd_scene load_steps=4 format=3]

[ext_resource type="PackedScene" path="res://shell.glb" id="b1"]

[sub_resource type="BoxShape3D" id="BoxShape_Ground"]
size = Vector3(200, 0.5, 20)

[node name="Site" type="Node3D"]

[node name="Ground" type="StaticBody3D" parent="."]
transform = Transform3D(1, 0, 0, 0, 1, 0, 0, 0, 1, 0, -0.25, 40)

[node name="col" type="CollisionShape3D" parent="./Ground"]
shape = SubResource("BoxShape_Ground")

[node name="b0" parent="." instance=ExtResource("b1")]
transform = Transform3D(6.12323e-17, 0, 1, 0, 1, 0, -1, 0, 6.12323e-17, 6, 0, 0)

[node name="b1" parent="." instance=ExtResource("b1")]
transform = Transform3D(1, 0, 0, 0, 1, 0, -0, 0, 1, 48, 0, 0)
'''

BLOCK_WALK = '''[gd_scene load_steps=2 format=3]

[ext_resource type="PackedScene" path="res://site.tscn" id="site"]

[node name="site_walk" type="Node3D"]

[node name="LT_PlayerSpawn" type="Node3D" parent="."]
transform = Transform3D(1, 0, 0, 0, 1, 0, 0, 0, 1, 48, 1, 0)

[node name="LT_ObjectivePoint" type="Node3D" parent="."]
transform = Transform3D(1, 0, 0, 0, 1, 0, 0, 0, 1, -6, 0.9, -16)

[node name="Nav" type="NavigationRegion3D" parent="."]

[node name="Site" parent="./Nav" instance=ExtResource("site")]
'''


def _block_site(tmp_path, *, collision=True):
    """The site above, with a shell that does or does not bring collision."""
    names = [slab("slab_col_0-colonly")] if collision else [
        ("Shell", (0.0, 8.0, 0.0), (44.0, 16.0, 32.0))]
    write_glb(tmp_path / "shell.glb", names)
    (tmp_path / "site.tscn").write_text(BLOCK, encoding="utf-8")
    (tmp_path / "level.tscn").write_text(BLOCK_WALK, encoding="utf-8")
    return tmp_path / "level.tscn"


def test_a_point_on_a_floor_inside_an_instanced_glb_is_supported(tmp_path):
    """The false blocker, end to end. Both mission points stand on a slab baked
    into the shell; the pre-flight used to call both of them holes because the
    slab was on the far side of a binary it declined to open."""
    assert check_ground_contact(_block_site(tmp_path)) == []


def test_a_shell_with_no_collision_still_reports_the_hole(tmp_path):
    """The other half of the same fix: reading into the .glb must not turn the
    check off. A shell that really is hollow still leaves the mission over a
    void, and this is the case Laser Tag refuses with NO_WORLD_COLLISION."""
    problems = check_ground_contact(_block_site(tmp_path, collision=False))
    assert len(problems) == 1
    assert "2 of 2" in problems[0]
    assert "could not be read" not in problems[0]


def test_the_quarter_turned_building_floors_its_own_rotated_footprint(tmp_path):
    """b0 is placed at 90 degrees, so its 44 x 32 slab covers 32 x 44 of the
    site. The objective at (-6, -16) is inside the turned footprint and outside
    the unturned one -- read the rotation wrong and the fix reports a hole."""
    reading = read_scene(_block_site(tmp_path))
    b0 = next(b for b in reading.boxes if "shell.glb" in b.name
              and abs(b.centre[0] - 6.0) < 1e-6)
    assert abs(b0.size[0] - 32.0) < 1e-6
    assert abs(b0.size[2] - 44.0) < 1e-6
    assert support_under((-6.0, 0.9, -16.0), reading.boxes) is not None


def test_a_shell_beside_the_scene_is_found_by_name(tmp_path):
    """Lot writes the shell's absolute path into a local-preview scene, and the
    shell lives in a different job directory. Resolving only the literal path
    would report every building opaque on any other machine."""
    write_glb(tmp_path / "shell.glb", [slab("slab_col_0-colonly")])
    absolute = BLOCK.replace(
        'path="res://shell.glb"',
        'path="res://D:/nowhere/that/exists/shell.glb"')
    (tmp_path / "site.tscn").write_text(absolute, encoding="utf-8")
    (tmp_path / "level.tscn").write_text(BLOCK_WALK, encoding="utf-8")
    assert check_ground_contact(tmp_path / "level.tscn") == []


def test_a_shell_placed_at_an_odd_angle_is_opaque_not_guessed(tmp_path):
    """A 37-degree building is not a box in site space. Over-stating its
    footprint would invent floor where the corner is not."""
    write_glb(tmp_path / "shell.glb", [slab("slab_col_0-colonly")])
    turned = BLOCK.replace(
        "Transform3D(6.12323e-17, 0, 1, 0, 1, 0, -1, 0, 6.12323e-17, 6, 0, 0)",
        "Transform3D(0.8, 0, 0.6, 0, 1, 0, -0.6, 0, 0.8, 6, 0, 0)")
    (tmp_path / "site.tscn").write_text(turned, encoding="utf-8")
    (tmp_path / "level.tscn").write_text(BLOCK_WALK, encoding="utf-8")
    reading = read_scene(tmp_path / "level.tscn")
    assert any("non-axis rotation" in o for o in reading.opaque)


def test_an_unreadable_shell_is_still_named_in_the_message(tmp_path):
    """Reading the .glb is the fix; hiding the cases where it cannot be read
    would just move the silence one layer down."""
    (tmp_path / "shell.glb").write_bytes(b"not a gltf at all")
    (tmp_path / "site.tscn").write_text(BLOCK, encoding="utf-8")
    (tmp_path / "level.tscn").write_text(BLOCK_WALK, encoding="utf-8")
    problems = check_ground_contact(tmp_path / "level.tscn")
    assert len(problems) == 1
    assert "shell.glb" in problems[0]
    assert "could not be read" in problems[0]


# ---------------------------------------------------------------------------
# the transform reader
# ---------------------------------------------------------------------------
def test_a_quarter_turn_is_axis_aligned_and_a_diagonal_is_not():
    quarter = ((6.12323e-17, 0.0, -1.0, 0.0), (0.0, 1.0, 0.0, 0.0),
               (1.0, 0.0, 6.12323e-17, 0.0))
    diagonal = ((0.707, 0.0, -0.707, 0.0), (0.0, 1.0, 0.0, 0.0),
                (0.707, 0.0, 0.707, 0.0))
    assert axis_aligned(quarter)
    assert not axis_aligned(diagonal)


def test_the_resolver_prefers_the_literal_path_over_the_basename(tmp_path):
    """Two shells with the same name in different directories is the normal
    case across candidates; picking the wrong one audits the wrong bytes."""
    real = tmp_path / "real"
    beside = tmp_path / "beside"
    real.mkdir()
    beside.mkdir()
    write_glb(real / "shell.glb", [slab("a-colonly")])
    write_glb(beside / "shell.glb", [slab("b-colonly")])
    resolve = resolver(beside)
    assert resolve(f"res://{real / 'shell.glb'}") == real / "shell.glb"
    assert resolve("res://shell.glb") == beside / "shell.glb"


# ---------------------------------------------------------------------------
# headers the reader could not see at all
# ---------------------------------------------------------------------------
LADDER = '''[gd_scene load_steps=2 format=3]

[sub_resource type="BoxShape3D" id="LadderBox_0"]
size = Vector3(1.3, 5.0, 1.3)

[node name="site_walk" type="Node3D"]

[node name="b0_LADDER_0_climb" type="Area3D" parent="." groups=["ladder"]]
transform = Transform3D(1, 0, 0, 0, 1, 0, 0, 0, 1, 27.0, 0.0, 19.0)
monitoring = true

[node name="shape" type="CollisionShape3D" parent="b0_LADDER_0_climb"]
shape = SubResource("LadderBox_0")
transform = Transform3D(1, 0, 0, 0, 1, 0, 0, 0, 1, 0, 2.0, 0)
'''


def test_a_node_with_a_group_is_still_a_node():
    """`groups=["ladder"]` puts a bracket inside a section header, and the
    header pattern used to stop at the first one -- so the header did not match
    and the node did not exist as far as this reader was concerned.

    A node the reader never saw is worse than an attribute it never read. The
    ladder volume never entered `frames`, so its CollisionShape3D child composed
    against the identity instead of against (27, 0, 19); and it never entered
    `types`, so the child was not recognised as belonging to an Area3D and the
    trigger exclusion never fired. Lot writes one of these per ladder, which is
    how a walkable site acquired four phantom 1.3 x 5 x 1.3 floor slabs stacked
    at the world origin -- ground that is not ground, in a place nothing is."""
    reading = read_scene_text(LADDER)
    assert reading.boxes == (), (
        "a ladder climb volume is an Area3D trigger, not a floor: "
        f"{[b.name for b in reading.boxes]}")
    assert reading.opaque == (), "and it is known not to be ground, not unknown"


def test_a_grouped_trigger_does_not_floor_a_point_standing_in_mid_air():
    """The consequence, stated as the thing that goes wrong. A point hanging in
    space over the origin used to find 'support' on a ladder volume that the
    scene actually placed 27 m away."""
    reading = read_scene_text(LADDER)
    assert support_under((0.0, 4.0, 0.0), reading.boxes) is None
