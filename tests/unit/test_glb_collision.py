"""Collision baked into a .glb is readable, and the reader says when it is not.

The defect this closes: a site whose four buildings were instanced .glb shells,
each carrying four `-colonly` floor slabs, was reported by the ground-contact
pre-flight as "12 of 15 mission point(s) have no ground beneath them
(collision inside 5 instanced resource(s) is not readable from the scene
text)". Every one of those points was standing on a slab. The pre-flight was
not wrong about what it could see; it was wrong to turn what it could not see
into a blocker.

Godot's importer decides collision from the node name, and the extent of the
resulting body is fully described by the glTF JSON chunk. So the pre-flight can
read it, and the only remaining opacity is a file it genuinely cannot open.
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from glb_fixture import gltf_doc, pack_glb, slab, write_glb  # noqa: E402

from packages.validation.glb_collision import (  # noqa: E402
    COLLISION_SUFFIXES, GlbReading, collision_solids, compose, hull,
    json_chunk, name_generates_collision, solids_in)


# ---------------------------------------------------------------------------
# the naming convention Godot actually applies
# ---------------------------------------------------------------------------
def test_every_documented_suffix_generates_collision():
    for suffix in COLLISION_SUFFIXES:
        assert name_generates_collision(f"slab{suffix}"), suffix


def test_a_plain_mesh_name_does_not():
    assert not name_generates_collision("Shell")
    assert not name_generates_collision("floor_collision")


def test_the_blender_duplicate_suffix_is_tolerated():
    """Blender appends `.001` after the marker Godot matches; a reader that
    misses it reports the second copy of a building as hollow."""
    assert name_generates_collision("slab_col_0-colonly.001")


def test_matching_is_case_insensitive_and_ignores_stray_space():
    assert name_generates_collision("  SLAB-COL  ")


# ---------------------------------------------------------------------------
# the container
# ---------------------------------------------------------------------------
def test_a_truncated_file_is_unreadable_not_empty(tmp_path):
    """"could not be parsed" and "holds no collision" are different facts and
    the caller has to be able to tell them apart."""
    path = tmp_path / "broken.glb"
    path.write_bytes(pack_glb(gltf_doc([slab("floor-colonly")]))[:9])
    reading = collision_solids(path)
    assert reading.read is False
    assert reading.solids == ()


def test_a_file_that_is_not_gltf_at_all_is_unreadable(tmp_path):
    path = tmp_path / "notreally.glb"
    path.write_bytes(b"PK\x03\x04" + b"\0" * 64)
    assert collision_solids(path).read is False


def test_a_missing_file_is_unreadable_and_names_the_reason(tmp_path):
    reading = collision_solids(tmp_path / "absent.glb")
    assert reading.read is False
    assert "not found on disk" in reading.detail


def test_the_json_chunk_is_found_past_a_leading_binary_chunk():
    """Exporters are free to order the chunks; a reader that assumes JSON comes
    first silently reports every file from that exporter as unreadable."""
    doc = gltf_doc([slab("floor-colonly")])
    import struct
    payload = b"\0" * 16
    binary = struct.pack("<II", len(payload), 0x004E4942) + payload
    packed = pack_glb(doc)
    reordered = packed[:12] + binary + packed[12:]
    assert json_chunk(reordered) is not None


# ---------------------------------------------------------------------------
# what comes out
# ---------------------------------------------------------------------------
def test_a_suffixed_slab_is_returned_as_a_box(tmp_path):
    write_glb(tmp_path / "shell.glb", [slab("slab_col_0-colonly")])
    reading = collision_solids(tmp_path / "shell.glb")
    assert reading.read is True
    assert len(reading.solids) == 1
    solid = reading.solids[0]
    assert solid.size == (44.0, 0.3, 32.0)
    assert abs(solid.centre[1] + 0.15) < 1e-9


def test_an_unsuffixed_mesh_brings_nothing_and_that_is_a_confident_answer(tmp_path):
    """The original bug, from the other side: a plain baked shell really does
    import as MeshInstance3D and nothing else. That has to read as "absent",
    not "unknown", or the check can never fire on a genuinely hollow building."""
    write_glb(tmp_path / "shell.glb", [("Shell", (0, 0, 0), (10, 10, 10))])
    reading = collision_solids(tmp_path / "shell.glb")
    assert reading.read is True
    assert reading.solids == ()
    assert "none named" in reading.detail


def test_only_the_collision_nodes_come_back(tmp_path):
    """A shell is mostly render geometry. Returning the visual meshes too would
    blanket the footprint and floor every hole in the building."""
    write_glb(tmp_path / "shell.glb", [
        ("Shell", (0, 8, 0), (44, 16, 32)),
        ("Roof", (0, 16, 0), (44, 1, 32)),
        slab("slab_col_0-colonly"),
    ])
    reading = collision_solids(tmp_path / "shell.glb")
    assert [s.name for s in reading.solids] == ["slab_col_0-colonly"]


def test_a_child_node_is_placed_by_its_parents_transform(tmp_path):
    """Exporters nest; reading a child's own transform alone stacks every
    collider at the origin."""
    doc = gltf_doc([("Level_1", (0, 0, 0), (0, 0, 0)),
                    slab("slab_col_1-colonly")],
                   children={"Level_1": ["slab_col_1-colonly"]})
    doc["nodes"][0]["translation"] = [0.0, 4.0, 0.0]
    (tmp_path / "shell.glb").write_bytes(pack_glb(doc))
    reading = collision_solids(tmp_path / "shell.glb")
    solid = next(s for s in reading.solids if s.name == "slab_col_1-colonly")
    assert abs(solid.centre[1] - 3.85) < 1e-9


def test_a_quarter_turn_on_a_node_swaps_the_footprint(tmp_path):
    """A rotated slab is still a box; describing it with its unrotated extent
    would put the floor 6 m from where it is."""
    doc = gltf_doc([slab("slab_col_0-colonly")])
    root = 2 ** 0.5 / 2.0
    doc["nodes"][0]["rotation"] = [0.0, root, 0.0, root]   # +90 about Y
    (tmp_path / "shell.glb").write_bytes(pack_glb(doc))
    solid = collision_solids(tmp_path / "shell.glb").solids[0]
    assert abs(solid.size[0] - 32.0) < 1e-6
    assert abs(solid.size[2] - 44.0) < 1e-6


def test_a_collider_with_no_declared_bounds_is_counted_not_invented(tmp_path):
    """An accessor without min/max cannot be sized without decoding the buffer.
    Skipping it silently would quietly shrink the floor."""
    doc = gltf_doc([slab("slab_col_0-colonly")])
    doc["accessors"][0].pop("min")
    (tmp_path / "shell.glb").write_bytes(pack_glb(doc))
    reading = collision_solids(tmp_path / "shell.glb")
    assert reading.solids == ()
    assert "no POSITION bounds" in reading.detail


def test_import_settings_that_request_physics_body_every_mesh(tmp_path):
    """`generate/physics=true` is the other way a .glb gets collision, and it
    ignores the naming convention entirely."""
    write_glb(tmp_path / "shell.glb", [("Shell", (0, 0, 0), (10, 4, 10))])
    (tmp_path / "shell.glb.import").write_text(
        '[params]\ngenerate/physics=true\n', encoding="utf-8")
    reading = collision_solids(tmp_path / "shell.glb")
    assert [s.name for s in reading.solids] == ["Shell"]


def test_a_file_with_no_scene_table_still_yields_its_nodes():
    """Some exporters omit `scenes`. Treating that as an empty world would
    report a fully floored shell as hollow."""
    doc = gltf_doc([slab("slab_col_0-colonly")])
    doc.pop("scenes")
    doc.pop("scene")
    reading = solids_in(doc)
    assert len(reading.solids) == 1


def test_a_cyclic_child_reference_terminates():
    """A malformed file must not turn a pre-flight into an infinite walk."""
    doc = gltf_doc([slab("a-colonly"), slab("b-colonly")])
    doc["nodes"][0]["children"] = [1]
    doc["nodes"][1]["children"] = [0]
    assert len(solids_in(doc).solids) == 2


# ---------------------------------------------------------------------------
# the matrix helpers, which the scene reader also leans on
# ---------------------------------------------------------------------------
def test_compose_applies_the_outer_transform_to_the_inner_origin():
    outer = ((0.0, 0.0, 1.0, 10.0), (0.0, 1.0, 0.0, 0.0), (-1.0, 0.0, 0.0, 0.0))
    inner = ((1.0, 0.0, 0.0, 3.0), (0.0, 1.0, 0.0, 0.0), (0.0, 0.0, 1.0, 0.0))
    combined = compose(outer, inner)
    assert (combined[0][3], combined[1][3], combined[2][3]) == (10.0, 0.0, -3.0)


def test_hull_of_an_unrotated_box_is_the_box():
    identity = ((1.0, 0.0, 0.0, 0.0), (0.0, 1.0, 0.0, 0.0), (0.0, 0.0, 1.0, 0.0))
    low, high = hull(identity, (-1.0, -2.0, -3.0), (1.0, 2.0, 3.0))
    assert low == (-1.0, -2.0, -3.0)
    assert high == (1.0, 2.0, 3.0)


# ---------------------------------------------------------------------------
# the shipped shell
# ---------------------------------------------------------------------------
FIXTURE = ROOT / "tests" / "fixtures" / "glb" / "shell_slabs.glb"


def test_the_real_deli_counter_shell_reports_its_floor_slabs():
    """A trimmed copy of the shell that produced the false blocker. Four
    `slab_col_*-colonly` floors, one per storey, 44 x 32 m."""
    if not FIXTURE.is_file():
        import pytest
        pytest.skip("shell fixture not present")
    reading = collision_solids(FIXTURE)
    assert reading.read is True
    slabs = [s for s in reading.solids if s.name.startswith("slab_col")]
    assert len(slabs) == 4
    ground = min(slabs, key=lambda s: abs(s.centre[1]))
    assert abs(ground.size[0] - 44.0) < 0.01
    assert abs(ground.size[2] - 32.0) < 0.01


def test_the_module_is_importable_without_the_rest_of_level_factory():
    """It is a pure reader; a dependency on the job graph would make it
    untestable from Lot's side of the fence, where the same question is asked."""
    import subprocess
    out = subprocess.run(
        [sys.executable, "-c",
         "import sys; sys.path.insert(0, %r);"
         "import packages.validation.glb_collision as m;"
         "print(sorted(k for k in dir(m) if not k.startswith('_')))" % str(ROOT)],
        capture_output=True, text=True, env={**os.environ, "PYTHONPATH": ""})
    assert out.returncode == 0, out.stderr
    assert "collision_solids" in out.stdout


def test_the_reading_dataclass_keeps_read_and_empty_apart():
    assert GlbReading((), True).read is True
    assert GlbReading((), False).read is False
