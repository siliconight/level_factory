"""The closure verdict must describe the package that ships.

Measured 2026-09-22 on cold 9066's and 9067's shipped packages
(`LF_club_block_00{5,6}.portable-godot`), which are what went out:

    export_closure_scan.json, the gate's own verdict : ok=true,  0 issues, 46
    scan_closure(package), run on the same folder    : ok=false, 1 issue,  48

`scan_closure` was called at step 3.6 and 22 files landed after it -- among
them `occluders.tscn` and `warmup.gd`, which are the two the resource count
was short by, and `handoff_bindings.json`, which is the issue. `project.godot`
did not exist at all when the judge looked, so the autoload and plugin
counters could not have been anything but zero on this path.

EVERY TEST HERE FAILS ON 0.102.0. That is the entry requirement: a test that
would pass on the code that shipped the defect has not caught it. The proof
is recorded in level_factory/CHANGELOG.md for 0.103.0 -- five failures, and
which line each died on.
"""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from packages.exporting import export  # noqa: E402
from packages.exporting.closure import (fingerprint_package,  # noqa: E402
                                        scan_closure)

#: The suffixes `ClosureResult.resource_count` counts. Spelled here rather
#: than imported, so the test is asking the question independently instead of
#: agreeing with the code by construction.
_RESOURCE_SUFFIXES = (".tscn", ".tres", ".gdshader", ".gd")


def _export(tmp_path):
    """A package with the three things the defect needs to show itself.

    `warmup.gd` needs no Godot and always ships, so `resource_count` is wrong
    by at least one on any export. `gameplay_anchors.json` carries a node
    path whose leaf exists in no scene, so `strip_dead_node_paths` writes
    `handoff_bindings.json`, which is the file the post-verdict scan refuses.
    The occluder bake needs a Godot and is simply absent here; the unit
    fixture therefore reproduces the SMALLER of the two resource-count gaps,
    which is enough to fail and honest about being a floor.
    """
    handoff = tmp_path / "handoff"
    handoff.mkdir()
    handoff.joinpath("mission.tscn").write_text(
        '[gd_scene format=3]\n[node name="MissionRoot" type="Node3D"]\n',
        encoding="utf-8")
    handoff.joinpath("site.tscn").write_text(
        '[gd_scene format=3]\n[node name="Ground" type="StaticBody3D"]\n',
        encoding="utf-8")
    handoff.joinpath("gameplay_anchors.json").write_text(json.dumps({
        "schema": "dispatch.gameplay_anchors.v0.2",
        "anchors": [{
            "id": "deli_counter:LOBBY", "pos": [1, 2, 3],
            "node": "Functional/GameplayAnchors/Objectives/deli_counter:LOBBY",
        }]}), encoding="utf-8")
    return export.export_mission(
        mission_id="m1", handoff_dir=handoff, presentation_dir=None,
        source_dir=None, profile=export.ExportProfile(),
        tool_versions={}, out_root=tmp_path / "exports",
    ).export_dir


def _verdict(export_dir):
    return json.loads(
        (export_dir / "export_closure_scan.json").read_text("utf-8"))


def test_the_verdict_counts_the_resources_that_ship(tmp_path):
    """THE POINT, in one number.

    46 against 48 on the shipped packages. Counted off the folder, not off
    the scan, because a recount that reuses the scan's own walk can only
    agree with it.
    """
    export_dir = _export(tmp_path)
    on_disk = sum(1 for p in export_dir.rglob("*")
                  if p.is_file() and p.suffix in _RESOURCE_SUFFIXES)
    assert _verdict(export_dir)["resource_count"] == on_disk


def test_the_shipped_verdict_survives_being_checked(tmp_path):
    """Re-run the same judge on the same folder and get the same answer.

    This is the whole defect stated as an invariant: `ok` and the issue list
    in the package must be what the package produces when somebody asks it
    again. `run_portability_test` asks exactly this, off a separate command,
    and on 9066/9067 it would have answered FAIL about a package whose own
    verdict said clean.
    """
    export_dir = _export(tmp_path)
    shipped = _verdict(export_dir)
    again = scan_closure(export_dir)
    assert (shipped["ok"], shipped["issues"]) == (again.ok, again.issues)


def test_the_verdict_says_which_package_it_is_about(tmp_path):
    """An unrecognised shape FAILS rather than passes.

    On 0.102.0 the verdict carries no fingerprint at all, so this raises
    KeyError -- which is the correct outcome, not an accident: a verdict that
    cannot say which package it judged is the defect, and a test that shrugged
    at the missing key (`.get(...) or ...`) would be the one this repo already
    wrote once and warned about.
    """
    export_dir = _export(tmp_path)
    shipped = _verdict(export_dir)
    assert shipped["package_fingerprint"] == fingerprint_package(
        export_dir, exclude=frozenset(shipped["written_after_verdict"]))
    # And the excluded list is short and honest: every file in the package
    # except the manifests that describe it is covered.
    on_disk = sum(1 for p in export_dir.rglob("*") if p.is_file())
    assert shipped["package_file_count"] == \
        on_disk - len(shipped["written_after_verdict"])


def test_the_judge_read_the_project_godot_that_ships(tmp_path):
    """`required_autoload_count` was a check that could not fail.

    `_write_project_godot` ran AFTER the scan, so the file the autoload and
    plugin half reads did not exist when it looked -- for five versions, on
    every export. Both counters were structurally zero and `ok` read both.
    """
    export_dir = _export(tmp_path)
    assert (export_dir / "project.godot").is_file()
    assert "project.godot" in scan_closure(export_dir).input_digest


def test_the_backstop_catches_the_next_writer(tmp_path):
    """The guard must be able to fail, or it says nothing.

    Plants exactly the defect that shipped -- a Godot resource written after
    the verdict -- and requires the build to refuse it.
    """
    export_dir = _export(tmp_path)
    scan = scan_closure(export_dir)
    export._guard_verdict_is_about_the_package(export_dir, scan)  # clean now
    (export_dir / "written_too_late.tscn").write_text(
        '[gd_scene format=3]\n', encoding="utf-8")
    with pytest.raises(export.ExportClosureError) as exc:
        export._guard_verdict_is_about_the_package(export_dir, scan)
    assert "written_too_late.tscn" in str(exc.value)


def test_the_backstop_sees_a_rewrite_not_only_an_arrival(tmp_path):
    """`occluders.emit` and `warmup.emit` both REWRITE `mission.tscn`, so a
    check that only counted new filenames would have missed the entry scene
    changing under the verdict -- which it did, twice per export."""
    export_dir = _export(tmp_path)
    scan = scan_closure(export_dir)
    entry = export_dir / "mission.tscn"
    entry.write_text(entry.read_text("utf-8") + '\n[node name="Late"]\n',
                     encoding="utf-8")
    with pytest.raises(export.ExportClosureError) as exc:
        export._guard_verdict_is_about_the_package(export_dir, scan)
    assert "mission.tscn" in str(exc.value)


def test_every_late_file_is_one_the_judge_declines_to_scan(tmp_path):
    """The two lists cannot drift apart.

    A file allowed to land after the verdict must also be metadata, or the
    next scan of the shipped folder judges it and the two judges disagree
    about one package -- which is how `handoff_bindings.json` became a
    failure that only the separate command could see.
    """
    from packages.exporting.closure import _METADATA_FILES
    assert export._WRITTEN_AFTER_VERDICT <= _METADATA_FILES


def test_excluding_the_bindings_did_not_blind_the_marker_test(tmp_path):
    """The narrow risk, checked rather than argued.

    `handoff_bindings.json` is excluded because its `deli_counter` is a Godot
    NODE path in LF's own log of addresses the package does NOT carry. A real
    authoring-repo path, in a real resource, must still be a failure -- and
    the same string in a scene must still be a failure, or the exclusion has
    bought the clean verdict by making the gate blind.
    """
    root = tmp_path / "pkg"
    root.mkdir()
    (root / "mission.tscn").write_text('[gd_scene format=3]\n',
                                       encoding="utf-8")
    (root / "handoff_bindings.json").write_text(json.dumps({
        "schema": "level_factory.handoff_bindings.v1", "moved_total": 1,
        "files": {"gameplay_anchors.json": {"moved": 1, "paths": [
            "Functional/GameplayAnchors/Triggers/deli_counter:01"]}}}),
        encoding="utf-8")
    assert scan_closure(root).ok

    (root / "site.tscn").write_text(
        '[gd_scene format=3]\n'
        '[ext_resource path="res://deli_counter/art/x.glb" id="1"]\n',
        encoding="utf-8")
    bad = scan_closure(root)
    assert not bad.ok
    assert any("deli_counter" in i for i in bad.issues)
