"""Every external reference inside a shipped GLB resolves to a file in the package.

THE DEFECT THIS IS FOR. Zoo 1.2.0 stopped embedding a module's images in its
binary chunk and started writing them once beside it, named by a relative glTF
``images[].uri``. Every copy site that moved a GLB BY NAME went on moving one
file where there were now several, and four Level Factory packages -- cold
runs 9066 through 9069 -- shipped as greybox. The walker on 9068: "around 90%
graybox now with no textures/skins on much of the assets".

WHY THREE GATES PASSED IT, which is the part worth a test rather than a fix:

    closure scan    asks whether every `res://` reference resolves. A glTF
                    `uri` is a string inside a binary; no text scan reads it.
    resource manifest   accounts for files PRESENT against files on disk.
                    Both sides were right -- absent from the folder, absent
                    from the list.
    cold-run verdict    counts interventions. Nobody intervened, because
                    nothing complained.

All three are closed over what the package CONTAINS. None asked what it
REFERS TO.

FAILS ON 0.104.0's OUTPUT, and `test_it_fails_on_the_package_0_104_0_shipped`
is that claim made against the bytes rather than argued. The measurement it
reproduces, taken 2026-09-22 on cold run 9068's shipped package:

    265 GLBs, 1,264 external references, 1,264 missing, 0 resolved

and the control, the same 23 cover GLBs in the Zoo kit directory they were
copied FROM:

     23 GLBs,   128 external references,     0 missing, 128 resolved

A number that cannot move is not evidence, so both are here.

Run:  python -m pytest tests/unit/test_glb_references_resolve.py
"""
from __future__ import annotations

import json
import struct
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from packages.exporting import glb_refs  # noqa: E402
from tests.unit.glb_fixture import gltf_doc, pack_glb  # noqa: E402


def _glb_naming(path: Path, uris: list[str], *, data_uris: int = 0) -> Path:
    """A real GLB whose ``images`` name ``uris``.

    Built from the same fixture the collision tests use, so what is parsed
    here is a container Blender would produce rather than a dict shaped to
    please the reader.
    """
    doc = gltf_doc([("box", (0.0, 0.0, 0.0), (1.0, 1.0, 1.0))])
    doc["images"] = [{"name": "t%d" % i, "uri": u} for i, u in enumerate(uris)]
    doc["images"] += [{"name": "embedded%d" % i,
                       "uri": "data:image/png;base64,iVBORw0KGgo="}
                      for i in range(data_uris)]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(pack_glb(doc))
    return path


def _png(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\0" * 64)
    return path


# --- the gate ---------------------------------------------------------------

def test_a_reference_the_package_does_not_carry_is_a_refusal(tmp_path):
    _glb_naming(tmp_path / "wall.glb", ["_tex/brick_a1b2c3d4.png"])
    report = glb_refs.scan(tmp_path)
    assert report["glbs_scanned"] == 1
    assert report["references"] == 1
    assert report["resolved"] == 0
    assert [m["uri"] for m in report["missing"]] == ["_tex/brick_a1b2c3d4.png"]
    assert report["ok"] is False
    with pytest.raises(glb_refs.GlbReferenceError) as exc:
        glb_refs.assert_closed(tmp_path)
    # The message names the GLB, the reference and where it looked. A refusal
    # that does not is a re-investigation.
    assert "wall.glb" in str(exc.value)
    assert "_tex/brick_a1b2c3d4.png" in str(exc.value)


def test_the_same_package_with_the_file_present_passes(tmp_path):
    """THE CONTROL. Without it the refusal above proves only that the
    instrument can say no."""
    _glb_naming(tmp_path / "wall.glb", ["_tex/brick_a1b2c3d4.png"])
    _png(tmp_path / "_tex" / "brick_a1b2c3d4.png")
    report = glb_refs.assert_closed(tmp_path)
    assert report["ok"] is True
    assert (report["resolved"], report["dependency_files"]) == (1, 1)


def test_two_glbs_naming_one_texture_count_one_file(tmp_path):
    """The saving externalisation buys, stated as the gate sees it: two
    references, one file on disk. Godot does not deduplicate identical
    embedded images (Zoo's `gltf_textures` measured 20 identical embeds at
    27,962,000 B against 1,398,100 B for one shared external), so this
    distinction is the whole point of the format change."""
    _glb_naming(tmp_path / "a.glb", ["_tex/brick_a1b2c3d4.png"])
    _glb_naming(tmp_path / "b.glb", ["_tex/brick_a1b2c3d4.png"])
    _png(tmp_path / "_tex" / "brick_a1b2c3d4.png")
    report = glb_refs.assert_closed(tmp_path)
    assert report["references"] == 2
    assert report["dependency_files"] == 1


def test_it_does_not_look_for_a_folder_called_tex(tmp_path):
    """The next externalised asset class is carried without an edit.

    A checker keyed on `_tex` is how this defect got through: it would pass a
    package whose GLBs named `_audio/` or `_lightmaps/` and carried neither.
    """
    _glb_naming(tmp_path / "sign.glb", ["skins/delco_neon_albedo.png"])
    with pytest.raises(glb_refs.GlbReferenceError):
        glb_refs.assert_closed(tmp_path)
    _png(tmp_path / "skins" / "delco_neon_albedo.png")
    assert glb_refs.assert_closed(tmp_path)["ok"] is True
    # And no folder name is spelled in the module at all -- as a STRING, not
    # as prose. The docstring may name `_tex` to say what happened; the code
    # may not name it to decide anything.
    source = Path(glb_refs.__file__).read_text(encoding="utf-8")
    assert '"_tex"' not in source and "'_tex'" not in source


def test_a_data_uri_is_content_not_a_reference(tmp_path):
    """An embedded image is not a dependency and must not be counted as a
    resolved one either -- that would let a package of embeds report a
    reference count it does not have."""
    _glb_naming(tmp_path / "wall.glb", [], data_uris=3)
    report = glb_refs.assert_closed(tmp_path)
    assert (report["references"], report["embedded_data_uris"]) == (0, 3)


@pytest.mark.parametrize("uri, reason", [
    ("../outside/brick.png", "escapes"),
    ("/var/textures/brick.png", "absolute"),
    ("C:/textures/brick.png", "absolute"),
    ("https://example.invalid/brick.png", "remote"),
])
def test_a_reference_a_recipient_cannot_follow_is_a_refusal(tmp_path, uri, reason):
    _glb_naming(tmp_path / "wall.glb", [uri])
    report = glb_refs.scan(tmp_path)
    assert [u["reason"] for u in report["unportable"]] == [reason]
    with pytest.raises(glb_refs.GlbReferenceError):
        glb_refs.assert_closed(tmp_path, report)


def test_an_unreadable_glb_is_a_finding_not_a_skip(tmp_path):
    """CLAUDE.md's third verification rule, applied to the container: an
    unrecognised shape FAILS. A `.glb` the exporter shipped and this cannot
    parse is a GLB nothing has checked, and saying nothing about it is saying
    it is clean."""
    (tmp_path / "broken.glb").write_bytes(b"not a glb at all")
    _glb_naming(tmp_path / "fine.glb", [])
    report = glb_refs.scan(tmp_path)
    assert report["glbs_scanned"] == 1
    assert [u["glb"] for u in report["unreadable"]] == ["broken.glb"]
    with pytest.raises(glb_refs.GlbReferenceError) as exc:
        glb_refs.assert_closed(tmp_path, report)
    assert "broken.glb" in str(exc.value)


def test_a_package_with_no_glb_at_all_says_so_rather_than_passing_quietly(tmp_path):
    """RETRACTED AND KEPT, above what replaced it.

    This asserted a refusal. Measured against the suite: 18 tests across three
    files build geometry-free packages, and `pure-shell` is a real exporter
    mode that produces one. Refusing would have failed a shipping path on a
    guess about what a package must contain -- and whether the entry can reach
    any geometry is the closure scan's question, already asked. Two
    instruments answering one question is how the empty export read as clean.

    So it is not a refusal, and it is not a silence either: `nothing_to_check`
    is a field in the shipped report and the summary line says it in words.
    """
    (tmp_path / "project.godot").write_text("", encoding="utf-8")
    report = glb_refs.assert_closed(tmp_path)
    assert report["nothing_to_check"] is True
    assert report["ok"] is True
    assert "NOTHING TO CHECK" in glb_refs.summary(report)


def test_a_package_that_was_checked_does_not_claim_it_was_not(tmp_path):
    """The control for the one above: `nothing_to_check` has to be able to be
    false, or it is a constant with an opinion."""
    _glb_naming(tmp_path / "wall.glb", [])
    report = glb_refs.assert_closed(tmp_path)
    assert report["nothing_to_check"] is False
    assert "NOTHING TO CHECK" not in glb_refs.summary(report)


def test_a_report_missing_a_key_raises_rather_than_passing(tmp_path):
    """The `or []` defect, refused. A `--verify` written against a guessed
    schema once printed "closure verdict clean" three lines under
    `EXPORT_CLOSURE_BROKEN: 21 unresolved`."""
    with pytest.raises(KeyError):
        glb_refs.assert_closed(tmp_path, {"unexpected": "shape"})


# --- the copy ---------------------------------------------------------------

def test_copy_with_deps_carries_what_the_glb_names(tmp_path):
    src, dst = tmp_path / "src", tmp_path / "dst"
    _glb_naming(src / "wall.glb", ["_tex/brick_a1b2c3d4.png"])
    _png(src / "_tex" / "brick_a1b2c3d4.png")
    copied = glb_refs.copy_with_deps(src / "wall.glb", dst / "art" / "wall.glb")
    assert copied == ["_tex/brick_a1b2c3d4.png"]
    assert (dst / "art" / "_tex" / "brick_a1b2c3d4.png").is_file()
    assert glb_refs.assert_closed(dst)["ok"] is True


def test_copy_with_deps_refuses_when_the_named_file_is_absent(tmp_path):
    """A copy that silently moves half of what it was asked to move is the
    defect. It raises instead."""
    src, dst = tmp_path / "src", tmp_path / "dst"
    _glb_naming(src / "wall.glb", ["_tex/brick_a1b2c3d4.png"])
    with pytest.raises(OSError):
        glb_refs.copy_with_deps(src / "wall.glb", dst / "wall.glb")


def test_the_dressing_extract_copies_the_glbs_dependencies():
    """`dressing_layer.extract_meshes` stages clutter GLBs into a scratch
    Godot project and extracts `.res` meshes from what Godot imported. With
    `copy2` the textures were not in that project at all, so since Zoo 1.2.0
    the meshes were extracted from an image-less import. It is a source
    assertion because the alternative is a Godot run inside a unit test."""
    import inspect

    from packages.exporting import dressing_layer
    body = inspect.getsource(dressing_layer.extract_meshes)
    assert "copy_with_deps" in body
    assert "shutil.copy2(str(src)" not in body


# --- where the textures were actually lost ----------------------------------

def test_a_jobs_published_outputs_include_what_its_glbs_name(tmp_path):
    """THE ROOT CAUSE, and it is upstream of every copy in the exporter.

    Every adapter's `collect_outputs` selects by SUFFIX -- Zoo's is
    `p.suffix in (".glb", ".json")`. Zoo 1.2.0 began writing a module's images
    as `.png` beside the GLB, so they were never collected, never linked into
    the job's stable `out/`, and every downstream stage reads `out/`.

    Measured on cold run 9068's workspace:

        jobs/<m>.zoo_dressing_build.card_shop_a01/1/out/_tex/  20 .png
        jobs/<m>.zoo_dressing_build.card_shop_a01/out/         no _tex at all

    The composer and the cover staging were copying a GLB by name and would
    have dropped the textures too -- both are fixed in their own repos -- but
    on this run neither was ever handed one.
    """
    from packages.jobs.scheduler import _with_glb_dependencies

    work = tmp_path / "1" / "out"
    _glb_naming(work / "wall.glb", ["_tex/brick_a1b2c3d4.png"])
    _png(work / "_tex" / "brick_a1b2c3d4.png")
    (work / "wall.built.json").write_text("{}", encoding="utf-8")
    # what a suffix-keyed collect_outputs returns
    collected = [work / "wall.glb", work / "wall.built.json"]
    widened = _with_glb_dependencies(collected, work)
    assert (work / "_tex" / "brick_a1b2c3d4.png") in widened
    assert len(widened) == 3


def test_the_widening_does_not_reach_outside_the_work_dir(tmp_path):
    """A job publishes what it built. A GLB naming something above its own
    work directory is a finding for the export gate, not a file for the job
    to adopt and hash as its own output."""
    from packages.jobs.scheduler import _with_glb_dependencies

    work = tmp_path / "1" / "out"
    work.mkdir(parents=True)
    _png(tmp_path / "elsewhere.png")
    _glb_naming(work / "wall.glb", ["../../elsewhere.png"])
    assert _with_glb_dependencies([work / "wall.glb"], work) == [
        work / "wall.glb"]


def test_an_unreadable_glb_does_not_stop_a_job_publishing(tmp_path):
    """Widening an output set is not the place to refuse a build. The export
    gate refuses, with the whole package in front of it."""
    from packages.jobs.scheduler import _with_glb_dependencies

    work = tmp_path / "1" / "out"
    work.mkdir(parents=True)
    (work / "broken.glb").write_bytes(b"not a glb")
    assert _with_glb_dependencies([work / "broken.glb"], work) == [
        work / "broken.glb"]


# --- where the gate sits ----------------------------------------------------

def test_the_gate_runs_above_the_closure_verdict_and_is_in_the_manifest():
    """Ordering, asserted rather than commented.

    `glb_reference_scan.json` is written INSIDE the package the closure
    verdict describes and inside the manifest that lists it, so it must not
    join `_WRITTEN_AFTER_VERDICT`. 0.104.0 shipped four files unlisted for
    being four lines too low; this one is not going to be the fifth.
    """
    import inspect

    from packages.exporting import export
    src = inspect.getsource(export.export_mission)
    gate = src.index("glb_refs.assert_closed")
    verdict = src.index("_closure_verdict(export_dir)")
    manifest = src.index("build_resource_manifest(export_dir)")
    assert gate < verdict < manifest
    assert "glb_reference_scan.json" not in export._WRITTEN_AFTER_VERDICT


def test_the_report_is_exempt_from_the_marker_scan_it_would_trip():
    """It records the absolute path of the directory the build wrote, which is
    exactly what closure's `_ABS_PATH` is built to find -- the same reason
    every other LF build log is on that list."""
    from packages.exporting import closure
    assert "glb_reference_scan.json" in closure._METADATA_FILES


# --- the package that shipped -----------------------------------------------

def _factory_root() -> Path | None:
    """The workspace root, found by walking up rather than by counting parents.

    `parents[3]` is correct from `level_factory/tests/unit/` and wrong from a
    worktree one directory deeper, which is where this was written -- and the
    two shipped-package tests below SKIPPED rather than failing, which is the
    quiet pass this whole file is against.
    """
    for parent in Path(__file__).resolve().parents:
        if (parent / "workspaces").is_dir() and (parent / "CLAUDE.md").is_file():
            return parent
    return None


_ROOT = _factory_root()
_WS = (_ROOT / "workspaces" / "cold-9068-ws") if _ROOT else Path("nowhere")
_SHIPPED = (_WS / ".level_factory" / "exports"
            / "LF_club_block_007.portable-godot")
_KIT = (_WS / ".level_factory" / "jobs" / "club_block_007.zoo_kit_build.site"
        / "1" / "out")


@pytest.mark.skipif(not _SHIPPED.is_dir(),
                    reason="cold-9068-ws is not in this tree; this test says "
                           "nothing rather than passing quietly")
def test_it_fails_on_the_package_0_104_0_shipped():
    report = glb_refs.scan(_SHIPPED)
    assert report["glbs_scanned"] == 265
    assert report["references"] == 1264
    assert len(report["missing"]) == 1264
    assert report["resolved"] == 0
    with pytest.raises(glb_refs.GlbReferenceError):
        glb_refs.assert_closed(_SHIPPED, report)


@pytest.mark.skipif(not _KIT.is_dir(),
                    reason="cold-9068-ws is not in this tree; this test says "
                           "nothing rather than passing quietly")
def test_and_passes_on_the_directory_zoo_wrote_those_same_glbs_into():
    """THE CONTROL FOR THE ONE ABOVE, on the same bytes. The 23 cover modules
    in the package came from here; here all 128 of their references resolve,
    to 20 files. The copy is what lost them, not the scan."""
    report = glb_refs.assert_closed(_KIT)
    assert report["glbs_scanned"] == 23
    assert (report["references"], report["resolved"]) == (128, 128)
    assert report["dependency_files"] == 20


def test_the_gate_is_reachable_without_running_an_export(tmp_path):
    """It can be pointed at a package nobody is exporting -- including the
    four already shipped. A gate reachable only from the build that would have
    prevented the defect cannot be pointed at the defect."""
    _glb_naming(tmp_path / "wall.glb", ["_tex/brick_a1b2c3d4.png"])
    out = tmp_path / "report.json"
    assert glb_refs._cli([str(tmp_path), "--json", str(out)]) == 1
    assert json.loads(out.read_text(encoding="utf-8"))["ok"] is False
    _png(tmp_path / "_tex" / "brick_a1b2c3d4.png")
    assert glb_refs._cli([str(tmp_path)]) == 0


def test_the_container_walk_does_not_assume_json_is_the_first_chunk(tmp_path):
    """A BIN chunk before the JSON chunk is legal glTF. Assuming otherwise
    would make the reader answer "unreadable" for a file that is fine, and an
    unreadable GLB is a refusal here."""
    doc = gltf_doc([("box", (0.0, 0.0, 0.0), (1.0, 1.0, 1.0))])
    doc["images"] = [{"name": "t", "uri": "_tex/x.png"}]
    payload = json.dumps(doc).encode("utf-8")
    payload += b" " * (-len(payload) % 4)
    binc = b"\0" * 16
    body = (struct.pack("<II", len(binc), 0x004E4942) + binc
            + struct.pack("<II", len(payload), 0x4E4F534A) + payload)
    (tmp_path / "odd.glb").write_bytes(
        struct.pack("<III", 0x46546C67, 2, 12 + len(body)) + body)
    assert glb_refs.dependencies(tmp_path / "odd.glb") == ["_tex/x.png"]
