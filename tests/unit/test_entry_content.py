"""A package must have something for its entry to instance.

Written after the first real art-unlit export -- lot_demo_001, 180 files,
28.6 MB of themed geometry -- opened to an empty scene, with
`export_closure_scan.json` reporting `ok: true` and `resource_count: 6`.
Closure walks from the entry, so an entry that references nothing is
trivially closed.

0.36.0's fixtures could not reproduce it: their handoff directory contains a
`site.tscn`, so the base copy always left something at the export root. These
build a mission WITHOUT that file, which is the shape a real one has.
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from packages.exporting.export import (  # noqa: E402
    MODE_ART_UNLIT, MODE_PORTABLE, ExportProfile, export_mission,
)
from packages.exporting.localize import (  # noqa: E402
    ExportContentError, write_entry_scene, LocalizeReport,
)


def _mission(root, *, with_lux=True):
    """Job directories shaped like a REAL art-passed mission.

    Note what the handoff does NOT contain: a root `site.tscn`. On
    lot_demo_001 the handoff carries mission JSON and the per-building
    packages, and the only scene that assembles them is Lux's output.
    """
    handoff = root / "handoff"
    handoff.mkdir(parents=True)
    (handoff / "mission_manifest.json").write_text("{}")

    lux = root / "lux_out"
    lux.mkdir(parents=True)
    if with_lux:
        (lux / "lux.applied.tscn").write_text("[gd_scene]\n")
        (lux / "lux.quality.json").write_text("{}")

    composed = root / "composed"
    (composed / "lot" / "b1").mkdir(parents=True)
    (composed / "lot" / "b1" / "site.tscn").write_text("[gd_scene]\n")
    (composed / "wall.glb").write_bytes(b"glTF")

    themed = root / "themed"
    themed.mkdir(parents=True)
    (themed / "site.tscn").write_text(
        '[gd_scene]\n[ext_resource path="res://lot/b1/site.tscn"]\n')
    return handoff, lux, composed, themed


def _export(root, mode, *, themed=True, with_lux=True):
    handoff, lux, composed, themed_dir = _mission(root / mode,
                                                  with_lux=with_lux)
    return export_mission(
        mission_id="m1", out_root=root / mode / "exports",
        profile=ExportProfile(mode=mode),
        handoff_dir=handoff, presentation_dir=lux, composed_root=composed,
        themed_site_dir=themed_dir if themed else None,
        source_dir=None, tool_versions={}, layers=frozenset({"art"}),
    )


# -------------------------------------------------------------- the guard

def test_an_entry_with_nothing_to_instance_raises(tmp_path):
    """THE BUG, as an exception instead of a silent empty package."""
    report = LocalizeReport()
    (tmp_path / "empty").mkdir()
    with pytest.raises(ExportContentError) as exc:
        write_entry_scene(tmp_path / "empty", report)
    assert "empty level" in str(exc.value)


def test_the_guard_does_not_fire_when_there_is_a_site(tmp_path):
    d = tmp_path / "ok"
    d.mkdir()
    (d / "site.tscn").write_text("[gd_scene]\n")
    report = LocalizeReport()
    assert write_entry_scene(d, report) == "mission.tscn"
    assert report.entry_instances == ["site.tscn"]


def test_the_report_records_what_the_entry_instances(tmp_path):
    """`entry_scene` says `mission.tscn` for a hollow package too."""
    d = tmp_path / "lit"
    (d / "presentation").mkdir(parents=True)
    (d / "presentation" / "lux.applied.tscn").write_text("[gd_scene]\n")
    report = LocalizeReport()
    write_entry_scene(d, report)
    assert report.entry_instances == ["presentation/lux.applied.tscn"]
    assert report.as_dict()["entry_instances"] == [
        "presentation/lux.applied.tscn"]


# ------------------------------------------------------- the assembly scene

def test_the_themed_site_reaches_the_package(tmp_path):
    result = _export(tmp_path, MODE_ART_UNLIT)
    assert (result.export_dir / "site.tscn").is_file()


def test_the_unlit_entry_instances_it(tmp_path):
    result = _export(tmp_path, MODE_ART_UNLIT)
    body = (result.export_dir / "mission.tscn").read_text()
    assert "res://site.tscn" in body
    assert "add_child" in body


def test_the_lit_entry_still_prefers_the_presentation_scene(tmp_path):
    result = _export(tmp_path, MODE_PORTABLE)
    body = (result.export_dir / "mission.tscn").read_text()
    assert "res://presentation/lux.applied.tscn" in body


def test_the_lit_package_also_carries_the_assembly(tmp_path):
    """It is what lux.applied.tscn was lit against; a single-shell mission's
    presentation scene names res://site.tscn directly."""
    result = _export(tmp_path, MODE_PORTABLE)
    assert (result.export_dir / "site.tscn").is_file()


def test_without_a_themed_site_an_unlit_export_refuses(tmp_path):
    """The old behaviour, now loud.

    No Lux output and no assembly is exactly what shipped 180 files and an
    empty scene. It raises rather than producing that package.
    """
    with pytest.raises(ExportContentError):
        _export(tmp_path, MODE_ART_UNLIT, themed=False, with_lux=False)


def test_the_closure_report_names_the_instance(tmp_path):
    result = _export(tmp_path, MODE_ART_UNLIT)
    report = json.loads(
        (result.export_dir / "export_closure.json").read_text())
    assert report["entry_instances"] == ["site.tscn"]
