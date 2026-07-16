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
