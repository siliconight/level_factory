"""Export localization: the fixer must satisfy the judge (scan_closure)."""
import json
from pathlib import Path

from packages.exporting.closure import scan_closure
from packages.exporting.localize import localize_export, write_entry_scene


def _fake_repo(tmp_path: Path) -> Path:
    """A lux-shaped tool repo with a two-deep script chain."""
    repo = tmp_path / "repos" / "lux"
    runtime = repo / "addons" / "lux" / "runtime"
    runtime.mkdir(parents=True)
    (runtime / "lux_root.gd").write_text(
        'extends Node3D\n'
        'const HELPER := preload("res://addons/lux/runtime/lux_helper.gd")\n',
        encoding="utf-8")
    (runtime / "lux_helper.gd").write_text("extends RefCounted\n", encoding="utf-8")
    return repo


def _fake_export(tmp_path: Path) -> Path:
    export = tmp_path / "export"
    export.mkdir(parents=True)
    shell = tmp_path / "jobs" / "seed_2199" / "out" / "shell.glb"
    shell.parent.mkdir(parents=True)
    shell.write_bytes(b"glTF-fake-shell")
    win_path = str(shell).replace("/", "/")
    (export / "site.tscn").write_text(
        '[gd_scene format=3]\n'
        f'[ext_resource type="PackedScene" path="res://{shell.as_posix()}" id="1"]\n',
        encoding="utf-8")
    (export / "site_walk.tscn").write_text(
        '[gd_scene format=3]\n'
        '[ext_resource type="Script" path="res://addons/lot/lot_player.gd" id="1"]\n',
        encoding="utf-8")
    pres = export / "presentation"
    pres.mkdir()
    (pres / "lux.applied.tscn").write_text(
        '[gd_scene format=3]\n'
        '[ext_resource type="Script" path="res://addons/lux/runtime/lux_root.gd" id="1"]\n',
        encoding="utf-8")
    return export


def test_absolute_refs_bundled_and_rewritten(tmp_path):
    export = _fake_export(tmp_path)
    repo = _fake_repo(tmp_path)
    report = localize_export(export, addon_sources={"lux": repo}, strip_walk=True)
    text = (export / "site.tscn").read_text(encoding="utf-8")
    assert 'path="res://assets/shell.glb"' in text
    assert (export / "assets" / "shell.glb").read_bytes() == b"glTF-fake-shell"
    assert any("shell.glb" in r for r in report.rewritten_absolute)


def test_addon_scripts_localized_recursively(tmp_path):
    export = _fake_export(tmp_path)
    repo = _fake_repo(tmp_path)
    localize_export(export, addon_sources={"lux": repo}, strip_walk=True)
    tscn = (export / "presentation" / "lux.applied.tscn").read_text(encoding="utf-8")
    assert "res://runtime/lux/runtime/lux_root.gd" in tscn
    root_gd = export / "runtime" / "lux" / "runtime" / "lux_root.gd"
    helper_gd = export / "runtime" / "lux" / "runtime" / "lux_helper.gd"
    assert root_gd.exists() and helper_gd.exists()
    # the copied script's own preload was rewritten too (recursive closure)
    assert "res://runtime/lux/runtime/lux_helper.gd" in root_gd.read_text(encoding="utf-8")
    assert "res://addons/" not in root_gd.read_text(encoding="utf-8")


def test_walk_scene_stripped_by_default_localized_on_flag(tmp_path):
    export = _fake_export(tmp_path)
    repo = _fake_repo(tmp_path)
    report = localize_export(export, addon_sources={"lux": repo}, strip_walk=True)
    assert not (export / "site_walk.tscn").exists()
    assert "site_walk.tscn" in report.stripped_scenes

    export2 = _fake_export(tmp_path / "two")
    lot_repo = tmp_path / "two" / "repos" / "lot"
    (lot_repo / "addons" / "lot").mkdir(parents=True)
    (lot_repo / "addons" / "lot" / "lot_player.gd").write_text(
        "extends CharacterBody3D\n", encoding="utf-8")
    report2 = localize_export(
        export2, addon_sources={"lux": _fake_repo(tmp_path / "two"), "lot": lot_repo},
        strip_walk=False)
    assert (export2 / "site_walk.tscn").exists()
    assert "res://runtime/lot/lot_player.gd" in (export2 / "site_walk.tscn").read_text(encoding="utf-8")
    assert report2.stripped_scenes == []


def test_entry_scene_and_closure_judge_green(tmp_path):
    export = _fake_export(tmp_path)
    repo = _fake_repo(tmp_path)
    report = localize_export(export, addon_sources={"lux": repo}, strip_walk=True)
    entry = write_entry_scene(export, report)
    assert entry == "mission.tscn"
    text = (export / "mission.tscn").read_text(encoding="utf-8")
    assert "load('res://site.tscn')" in text
    assert "load('res://presentation/lux.applied.tscn')" in text
    assert "--lf-portability-check" in text

    result = scan_closure(export)
    assert result.absolute_path_count == 0
    assert result.missing_resource_count == 0, result.issues
    assert result.ok, result.issues


def test_asset_name_collision_deduped_by_hash(tmp_path):
    export = tmp_path / "export"
    export.mkdir()
    a = tmp_path / "a" / "shell.glb"
    b = tmp_path / "b" / "shell.glb"
    a.parent.mkdir(); b.parent.mkdir()
    a.write_bytes(b"AAA"); b.write_bytes(b"BBB")
    (export / "site.tscn").write_text(
        '[gd_scene format=3]\n'
        f'[ext_resource type="PackedScene" path="res://{a.as_posix()}" id="1"]\n'
        f'[ext_resource type="PackedScene" path="res://{b.as_posix()}" id="2"]\n',
        encoding="utf-8")
    localize_export(export, addon_sources={}, strip_walk=True)
    assets = sorted(p.name for p in (export / "assets").iterdir())
    assert len(assets) == 2 and "shell.glb" in assets
    text = (export / "site.tscn").read_text(encoding="utf-8")
    assert text.count("res://assets/") == 2


def test_directory_addon_ref_copytreed_not_crashed(tmp_path):
    """lux_root.gd scans res://addons/lux/presets (a DIRECTORY) — v0.10.0
    crashed the whole export on this (Errno 13 on Windows)."""
    export = tmp_path / "export"
    export.mkdir(parents=True)
    repo = tmp_path / "repos" / "lux"
    (repo / "addons" / "lux" / "runtime").mkdir(parents=True)
    (repo / "addons" / "lux" / "presets").mkdir()
    (repo / "addons" / "lux" / "presets" / "blue_hour.tres").write_text(
        "[gd_resource]\n", encoding="utf-8")
    (repo / "addons" / "lux" / "runtime" / "lux_root.gd").write_text(
        "extends Node3D\n"
        "const PRESET_DIR := 'res://addons/lux/presets'\n", encoding="utf-8")
    (export / "presentation").mkdir()
    (export / "presentation" / "lux.applied.tscn").write_text(
        '[gd_scene format=3]\n'
        '[ext_resource type="Script" path="res://addons/lux/runtime/lux_root.gd" id="1"]\n',
        encoding="utf-8")
    report = localize_export(export, addon_sources={"lux": repo}, strip_walk=True)
    gd = (export / "runtime" / "lux" / "runtime" / "lux_root.gd").read_text(encoding="utf-8")
    assert "res://runtime/lux/presets" in gd
    assert (export / "runtime" / "lux" / "presets" / "blue_hour.tres").exists()
    assert any("(dir)" in x for x in report.localized_scripts)
    assert report.unresolved == []


def test_copy_failure_recorded_never_raised(tmp_path):
    export = tmp_path / "export"
    export.mkdir(parents=True)
    (export / "scene.tscn").write_text(
        '[gd_scene format=3]\n'
        '[ext_resource type="Script" path="res://addons/ghost/missing.gd" id="1"]\n',
        encoding="utf-8")
    report = localize_export(export, addon_sources={}, strip_walk=True)
    assert any("ghost" in u for u in report.unresolved)


def test_class_name_references_pull_scripts(tmp_path):
    """v0.10.1 hardware: lux_root.gd names LuxLighting/LuxEmissiveBinder etc.
    by GLOBAL CLASS NAME (no res:// path) -> 30 clean-project parse errors.
    The class map must pull those scripts by name, recursively."""
    export = tmp_path / "export"
    export.mkdir(parents=True)
    repo = tmp_path / "repos" / "lux"
    rt = repo / "addons" / "lux" / "runtime"
    rt.mkdir(parents=True)
    (rt / "lux_root.gd").write_text(
        "extends Node3D\n"
        "func _build() -> void:\n"
        "\tvar l := LuxLighting.new()\n", encoding="utf-8")
    (rt / "lux_lighting.gd").write_text(
        "class_name LuxLighting\nextends RefCounted\n"
        "func bind() -> void:\n"
        "\tLuxEmissiveBinder.bind_all()\n", encoding="utf-8")
    (rt / "lux_emissive_binder.gd").write_text(
        "class_name LuxEmissiveBinder\nextends RefCounted\n", encoding="utf-8")
    (export / "presentation").mkdir()
    (export / "presentation" / "lux.applied.tscn").write_text(
        '[gd_scene format=3]\n'
        '[ext_resource type="Script" path="res://addons/lux/runtime/lux_root.gd" id="1"]\n',
        encoding="utf-8")
    localize_export(export, addon_sources={"lux": repo}, strip_walk=True)
    rtdir = export / "runtime" / "lux" / "runtime"
    assert (rtdir / "lux_root.gd").exists()
    assert (rtdir / "lux_lighting.gd").exists()       # named by lux_root
    assert (rtdir / "lux_emissive_binder.gd").exists()  # named by lux_lighting (recursive)
    result = scan_closure(export)
    assert result.ok, result.issues


def test_directory_ref_counts_as_present_in_judge(tmp_path):
    export = tmp_path / "export"
    (export / "runtime" / "lux" / "presets").mkdir(parents=True)
    (export / "runtime" / "lux" / "presets" / "a.tres").write_text("[gd_resource]\n")
    (export / "boot.gd").write_text(
        "extends Node\nconst P := 'res://runtime/lux/presets'\n", encoding="utf-8")
    result = scan_closure(export)
    assert result.missing_resource_count == 0, result.issues


def test_export_metadata_exempt_from_marker_scan(tmp_path):
    """v0.10.2 hardware: the closure audit report incriminated itself — its
    rewritten_absolute entries contain the original absolute paths."""
    export = tmp_path / "export"
    export.mkdir(parents=True)
    (export / "export_closure.json").write_text(
        '{"rewritten_absolute": ["C:/Projects/level_factory/x.glb -> res://assets/x.glb"]}',
        encoding="utf-8")
    result = scan_closure(export)
    assert result.absolute_path_count == 0, result.issues
    assert result.external_reference_count == 0, result.issues
