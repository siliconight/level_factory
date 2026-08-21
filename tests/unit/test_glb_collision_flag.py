"""Flipping the collision a ``.glb`` generates, which is a rename.

Every test that claims a file collides checks it through
``packages.validation.glb_collision`` -- the READER, a separate implementation
that walks the container and the node tree on its own. A writer that graded its
own homework would pass while the engine disagreed, which is the mistake this
repo made once already with a MultiMesh buffer and a dummy renderer.
"""
from __future__ import annotations

import json
import struct
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from glb_fixture import gltf_doc, pack_glb, slab, write_glb  # noqa: E402

from packages.validation.glb_collision import (  # noqa: E402
    collision_solids, json_chunk, name_generates_collision)
from packages.exporting import glb_collision_flag as F  # noqa: E402


def read(path):
    return collision_solids(path)


# --- the name arithmetic ---------------------------------------------------

def test_every_policy_round_trips_through_the_readers_own_test():
    """Applying a policy makes the reader say yes; `none` makes it say no."""
    for policy in F.POLICIES:
        if policy == F.NONE:
            continue
        tagged = F.with_collision("floor", F.suffix_for(policy))
        assert name_generates_collision(tagged), policy
        assert not name_generates_collision(F.strip_collision(tagged)), policy


def test_the_suffix_goes_before_blenders_duplicate_tail():
    """Blender's `.NNN` is terminal, so the marker goes in front of it.

    NOT because the other order stops colliding. `floor.001-colonly` matches
    Godot's rule perfectly well -- there is no trailing `.NNN` left to ignore,
    so the suffix is at the end. The patch selftest was originally built to
    falsify this by writing the suffix after the tail, and it could not,
    because the file still collided. The reason to keep the order is that a
    name with anything after `.NNN` is one no exporter would ever write.
    """
    assert F.with_collision("floor.001", "-colonly") == "floor-colonly.001"
    assert name_generates_collision("floor-colonly.001")
    # the honest half: the wrong order collides too, and that is why this
    # test asserts the STRING and not the collision.
    assert name_generates_collision("floor.001-colonly")


def test_stripping_keeps_the_duplicate_tail():
    assert F.strip_collision("floor-colonly.001") == "floor.001"


def test_a_name_with_no_marker_is_returned_untouched():
    """A no-op has to be a true no-op, or the rename list overstates the work."""
    for name in ("Shell", "floor_collision", "wall.001", ""):
        assert F.strip_collision(name) == name


def test_switching_policy_does_not_stack_suffixes():
    once = F.with_collision("floor", "-col")
    twice = F.with_collision(once, "-convcolonly")
    assert twice == "floor-convcolonly"


def test_no_suffix_is_a_suffix_of_another():
    """WHY `strip_collision` SORTS LONGEST-FIRST, stated honestly.

    Today that sort is inert: the leading hyphen keeps every marker distinct,
    so `floor-convcolonly` does NOT end with `-colonly` and the order cannot
    matter. This test is what makes the sort worth keeping anyway -- if Godot
    ever adds a marker that IS a tail of another, this fails and the sort stops
    being decoration and starts being the reason it works.

    An earlier version of this file asserted the sort mattered and gave
    `-convcolonly` / `-colonly` as the example. That was simply false, and the
    test passed regardless of the sort order -- which is how a mutation run
    found it rather than a reader.
    """
    from packages.validation.glb_collision import COLLISION_SUFFIXES
    overlapping = [(a, b) for a in COLLISION_SUFFIXES
                   for b in COLLISION_SUFFIXES if a != b and a.endswith(b)]
    assert not overlapping


def test_every_suffix_strips_back_to_the_bare_name():
    from packages.validation.glb_collision import COLLISION_SUFFIXES
    for suffix in COLLISION_SUFFIXES:
        assert F.strip_collision(f"floor{suffix}") == "floor", suffix
        assert F.strip_collision(f"floor{suffix}.001") == "floor.001", suffix


def test_matching_is_case_insensitive_like_the_importer():
    assert F.strip_collision("floor-COLONLY") == "floor"


def test_an_unknown_policy_is_refused_by_name():
    with pytest.raises(F.GlbCollisionError) as exc:
        F.suffix_for("solid")
    assert "solid" in str(exc.value)


def test_the_policy_list_is_derived_from_the_readers_vocabulary():
    """If Godot gains a suffix, it is added in one file and both directions
    follow. A hand-written list here is how the two drift apart."""
    from packages.validation.glb_collision import COLLISION_SUFFIXES
    assert F.POLICIES == (F.NONE,) + tuple(s[1:] for s in COLLISION_SUFFIXES)


# --- the document ----------------------------------------------------------

def test_clearing_removes_collision_the_reader_could_see(tmp_path):
    src = write_glb(tmp_path / "shell.glb", [slab("floor-colonly")])
    assert len(read(src).solids) == 1
    out = tmp_path / "clean.glb"
    report = F.apply_to_file(src, "none", out=out)
    assert read(out).solids == ()
    assert report.colliders_before == 1 and report.colliders_after == 0


def test_applying_gives_collision_the_reader_can_see(tmp_path):
    src = write_glb(tmp_path / "prop.glb", [slab("floor")])
    assert read(src).solids == ()
    out = tmp_path / "solid.glb"
    report = F.apply_to_file(src, "colonly", out=out)
    assert len(read(out).solids) == 1
    # The report is asserted in the ADDING direction too. Only ever checking
    # `colliders_after == 0` lets a counter that is stuck at zero pass forever.
    assert (report.colliders_before, report.colliders_after) == (0, 1)
    assert report.renamed == [("floor", "floor-colonly")]


def test_a_node_without_a_mesh_is_not_given_a_suffix(tmp_path):
    """A marker on an empty generates nothing in Godot; writing one there
    leaves a name that lies about the file."""
    doc = gltf_doc([slab("floor")])
    doc["nodes"].append({"name": "Empty"})
    doc["scenes"][0]["nodes"].append(len(doc["nodes"]) - 1)
    out, report = F.retag(doc, "col")
    names = [n["name"] for n in out["nodes"]]
    assert "floor-col" in names and "Empty" in names
    assert report.mesh_nodes == 1


def test_clearing_does_reach_a_node_without_a_mesh():
    """`none` means none, including a stale marker sitting on an empty.

    The COUNT is asserted too, not just the names. Clearing happens
    unconditionally, so a report that only counted meshed nodes would rename
    correctly and still understate what it found -- a mutation run caught
    exactly that, because the first version of this test checked names alone.
    """
    doc = gltf_doc([slab("floor-col")])
    doc["nodes"].append({"name": "rig-colonly"})
    out, report = F.retag(doc, "none")
    assert [n["name"] for n in out["nodes"]] == ["floor", "rig"]
    assert report.colliders_before == 2
    assert report.colliders_after == 0
    assert len(report.renamed) == 2


def test_retag_does_not_mutate_the_document_it_was_given():
    doc = gltf_doc([slab("floor-colonly")])
    F.retag(doc, "none")
    assert doc["nodes"][0]["name"] == "floor-colonly"


def test_geometry_is_untouched_by_the_rewrite(tmp_path):
    """The bounds the reader returns come from the accessors. If a rewrite
    moved a byte of geometry, the box would move with it."""
    src = write_glb(tmp_path / "a.glb", [slab("floor-colonly")])
    before = read(src).solids[0]
    out = tmp_path / "b.glb"
    F.apply_to_file(src, "convcolonly", out=out)
    after = read(out).solids[0]
    assert (after.centre, after.size) == (before.centre, before.size)


# --- the container ---------------------------------------------------------

def _with_bin(doc: dict, blob: bytes) -> bytes:
    """A GLB whose BIN chunk sits after the JSON chunk, as Blender writes it."""
    payload = json.dumps(doc).encode("utf-8")
    payload += b" " * (-len(payload) % 4)
    padded = blob + b"\x00" * (-len(blob) % 4)
    body = (struct.pack("<II", len(payload), 0x4E4F534A) + payload
            + struct.pack("<II", len(padded), 0x004E4942) + padded)
    return struct.pack("<III", 0x46546C67, 2, 12 + len(body)) + body


def test_a_trailing_bin_chunk_survives_byte_for_byte(tmp_path):
    """The vertex data lives in that chunk. Copying it through unchanged is
    what makes this safe on a real export rather than only on a fixture."""
    blob = bytes(range(256)) * 3
    src = tmp_path / "real.glb"
    src.write_bytes(_with_bin(gltf_doc([slab("floor-colonly")]), blob))
    out = tmp_path / "out.glb"
    F.apply_to_file(src, "none", out=out)
    data = out.read_bytes()
    assert blob in data
    assert read(out).solids == ()


def test_the_container_length_header_is_rewritten(tmp_path):
    """A stale total length is a file that opens in some readers and not in
    others -- the worst kind of broken."""
    src = write_glb(tmp_path / "a.glb", [slab("floor-colonly")])
    out = tmp_path / "b.glb"
    F.apply_to_file(src, "convcol", out=out)
    data = out.read_bytes()
    assert struct.unpack_from("<I", data, 8)[0] == len(data)


def test_the_json_chunk_is_space_padded_not_zero_padded(tmp_path):
    """The spec says SPACES for a JSON chunk and zeroes for a BIN chunk.

    Sweeping four name lengths is the point: only three residues in four need
    any padding at all, so a single fixture tests this one time in four and
    passes by luck the rest. The first version of this test did exactly that
    -- a zero-padding mutant survived it.
    """
    padded_cases = 0
    for extra in range(4):
        src = write_glb(tmp_path / f"a{extra}.glb", [slab("f" + "x" * extra)])
        out = tmp_path / f"b{extra}.glb"
        F.apply_to_file(src, "col", out=out)
        data = out.read_bytes()
        size = struct.unpack_from("<I", data, 12)[0]
        chunk = data[20:20 + size]
        text = chunk.rstrip(b" ")
        pad = chunk[len(text):]
        padded_cases += 1 if pad else 0
        assert set(pad) <= {0x20}, (extra, pad)
        assert b"\x00" not in chunk, extra
        assert json.loads(text.decode("utf-8"))
    assert padded_cases >= 2, "the sweep never exercised a padded chunk"


def test_a_file_that_is_not_a_glb_is_refused(tmp_path):
    bad = tmp_path / "x.glb"
    bad.write_bytes(b"not a gltf at all, not even close")
    with pytest.raises(F.GlbCollisionError):
        F.apply_to_file(bad, "none", out=tmp_path / "y.glb")


def test_a_missing_file_is_refused_by_name(tmp_path):
    with pytest.raises(F.GlbCollisionError) as exc:
        F.apply_to_file(tmp_path / "nope.glb", "none", out=tmp_path / "y.glb")
    assert "no such file" in str(exc.value)


# --- the refusals that matter ----------------------------------------------

def test_generate_physics_in_the_import_file_blocks_clearing(tmp_path):
    """THE ONE THAT MATTERS. `generate/physics=true` bodies every mesh whatever
    the nodes are called, so clearing the names would report a collisionless
    file that imports with collision on everything."""
    src = write_glb(tmp_path / "shell.glb", [slab("floor-colonly")])
    (tmp_path / "shell.glb.import").write_text(
        '[params]\ngenerate/physics=true\n', encoding="utf-8")
    with pytest.raises(F.GlbCollisionError) as exc:
        F.apply_to_file(src, "none", out=tmp_path / "out.glb")
    assert "generate/physics" in str(exc.value)


def test_that_block_does_not_stop_you_ADDING_collision(tmp_path):
    """It is only the false-negative direction that is dangerous."""
    src = write_glb(tmp_path / "shell.glb", [slab("floor")])
    (tmp_path / "shell.glb.import").write_text(
        '[params]\ngenerate/physics=true\n', encoding="utf-8")
    F.apply_to_file(src, "colonly", out=tmp_path / "out.glb")
    assert len(read(tmp_path / "out.glb").solids) == 1


def test_writing_over_the_input_needs_saying_so(tmp_path):
    src = write_glb(tmp_path / "a.glb", [slab("floor-col")])
    with pytest.raises(F.GlbCollisionError) as exc:
        F.apply_to_file(src, "none")
    assert "refusing to guess" in str(exc.value)


def test_out_and_in_place_together_are_refused(tmp_path):
    src = write_glb(tmp_path / "a.glb", [slab("floor-col")])
    with pytest.raises(F.GlbCollisionError):
        F.apply_to_file(src, "none", out=tmp_path / "b.glb", in_place=True)


def test_in_place_rewrites_the_original(tmp_path):
    src = write_glb(tmp_path / "a.glb", [slab("floor-colonly")])
    F.apply_to_file(src, "none", in_place=True)
    assert read(src).solids == ()


# --- the CLI ---------------------------------------------------------------

def test_the_cli_clears_a_file(tmp_path, capsys):
    src = write_glb(tmp_path / "a.glb", [slab("floor-colonly")])
    out = tmp_path / "b.glb"
    assert F.main([str(src), "--collision", "none", "--out", str(out)]) == 0
    assert read(out).solids == ()


def test_the_cli_reports_a_refusal_rather_than_a_traceback(tmp_path, capsys):
    src = write_glb(tmp_path / "a.glb", [slab("floor-colonly")])
    (tmp_path / "a.glb.import").write_text('generate/physics=true',
                                           encoding="utf-8")
    rc = F.main([str(src), "--collision", "none", "--out",
                 str(tmp_path / "b.glb")])
    assert rc == 2
    assert "refused" in capsys.readouterr().err


def test_out_with_several_inputs_is_refused(tmp_path, capsys):
    a = write_glb(tmp_path / "a.glb", [slab("f")])
    b = write_glb(tmp_path / "b.glb", [slab("g")])
    assert F.main([str(a), str(b), "--collision", "none",
                   "--out", str(tmp_path / "c.glb")]) == 2
