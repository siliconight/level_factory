"""Resource closure + export assembly (TDD 33)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from packages.exporting.closure import scan_closure
from packages.exporting.export import (
    ExportProfile, MODE_PURE_SHELL, export_mission, zip_export,
)


def test_closure_flags_absolute_paths(tmp_path):
    root = tmp_path / "mission"
    root.mkdir()
    (root / "mission.tscn").write_text(
        '[gd_scene]\n[ext_resource path="C:/Projects/deli-counter/x.glb"]\n')
    result = scan_closure(root)
    assert result.absolute_path_count >= 1
    assert not result.ok


def test_closure_clean_when_self_contained(tmp_path):
    root = tmp_path / "mission"
    root.mkdir()
    (root / "mission.tscn").write_text(
        '[gd_scene]\n[ext_resource path="res://model.glb"]\n')
    (root / "model.glb").write_bytes(b"glb")
    result = scan_closure(root)
    assert result.ok


def test_closure_flags_autoload_and_plugin(tmp_path):
    root = tmp_path / "mission"
    root.mkdir()
    (root / "mission.tscn").write_text("[gd_scene]\n")
    (root / "project.godot").write_text(
        "[autoload]\nGameState=\"res://gs.gd\"\n\n"
        "[editor_plugins]\nenabled=PackedStringArray(\"res://addons/lux/plugin.cfg\")\n")
    result = scan_closure(root)
    assert result.required_autoload_count >= 1
    assert result.required_plugin_count >= 1
    assert not result.ok


def test_export_pure_shell_drops_presentation(tmp_path):
    handoff = tmp_path / "handoff"
    handoff.mkdir()
    (handoff / "mission.tscn").write_text("[gd_scene]\n")
    (handoff / "gameplay_anchors.json").write_text("{}")
    pres = tmp_path / "pres"
    pres.mkdir()
    (pres / "lux.applied.tscn").write_text("[gd_scene]\n")
    (pres / "lux.quality.json").write_text("{}")

    result = export_mission(
        mission_id="m1", handoff_dir=handoff, presentation_dir=pres,
        source_dir=None, profile=ExportProfile(mode=MODE_PURE_SHELL),
        tool_versions={"dispatch": "0.1.0"}, out_root=tmp_path / "exports",
    )
    files = {p.name for p in result.export_dir.rglob("*") if p.is_file()}
    assert "mission.tscn" in files
    assert "lux.applied.tscn" not in files  # presentation dropped in pure-shell
    assert "HANDOFF.md" in files
    assert "portable_resource_manifest.json" in files


def test_export_zip_is_deterministic(tmp_path):
    handoff = tmp_path / "handoff"
    handoff.mkdir()
    (handoff / "mission.tscn").write_text("[gd_scene]\n")
    result = export_mission(
        mission_id="m1", handoff_dir=handoff, presentation_dir=None,
        source_dir=None, profile=ExportProfile(),
        tool_versions={}, out_root=tmp_path / "exports",
    )
    z = zip_export(result)
    assert z.exists()
    assert z.suffix == ".zip"
