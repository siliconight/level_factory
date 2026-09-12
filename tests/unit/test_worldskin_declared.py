"""The export declares the worldskin import script WHERE THE PACKAGE CARRIES IT.

Roadmap 141 (2026-09-11). `run_presentation_compose` installs
`zoo_worldskin.gd` at the root of the composed package; the export copies
that package in as `lot/shell/`, so the script ships at
`lot/shell/zoo_worldskin.gd`. `_importer_defaults_block` looked only at the
export root, found nothing, wrote no `[importer_defaults]`, and the sidecar
pass baked an empty `import_script/path` into every kit GLB -- measured on
cold run 9005's hospital package: 0 of 48 bound, a 66.0x world-density
mismatch on the concrete skin; 1.0x once declared where it sits.

Run:  python -m pytest tests/unit/test_worldskin_declared.py
"""
from pathlib import Path

from packages.exporting.export import (_WORLDSKIN, _importer_defaults_block,
                                       _worldskin_in_package,
                                       _write_project_godot)


def _settings_block(text: str) -> str:
    """The `[importer_defaults]` section's text, or ''."""
    if "[importer_defaults]" not in text:
        return ""
    return text.split("[importer_defaults]", 1)[1].split("\n[", 1)[0]


def test_a_package_without_the_script_declares_nothing(tmp_path):
    (tmp_path / "presentation").mkdir()
    assert _worldskin_in_package(tmp_path) is None
    assert _importer_defaults_block(tmp_path) == ""


def test_the_script_at_the_root_is_declared_at_the_root(tmp_path):
    (tmp_path / _WORLDSKIN).write_text("# script", encoding="utf-8")
    assert _worldskin_in_package(tmp_path) == Path(_WORLDSKIN)
    assert f'"import_script/path": "res://{_WORLDSKIN}"' in _importer_defaults_block(tmp_path)


def test_the_script_under_lot_shell_is_declared_where_it_sits(tmp_path):
    """The shipped shape: compose put it at its root, export nested that."""
    shell = tmp_path / "lot" / "shell"
    shell.mkdir(parents=True)
    (shell / _WORLDSKIN).write_text("# script", encoding="utf-8")
    assert _worldskin_in_package(tmp_path) == Path("lot") / "shell" / _WORLDSKIN
    block = _importer_defaults_block(tmp_path)
    assert '"import_script/path": "res://lot/shell/zoo_worldskin.gd"' in block


def test_a_stale_copy_under_dot_godot_does_not_count(tmp_path):
    cache = tmp_path / ".godot" / "imported"
    cache.mkdir(parents=True)
    (cache / _WORLDSKIN).write_text("# cache", encoding="utf-8")
    assert _worldskin_in_package(tmp_path) is None


def test_project_godot_carries_the_declaration_for_the_shipped_shape(tmp_path):
    (tmp_path / "presentation").mkdir()
    shell = tmp_path / "lot" / "shell"
    shell.mkdir(parents=True)
    (shell / _WORLDSKIN).write_text("# script", encoding="utf-8")
    _write_project_godot(tmp_path, "mission.tscn", "m", "4.7")
    text = (tmp_path / "project.godot").read_text(encoding="utf-8")
    assert text.count("[importer_defaults]") == 1
    assert 'res://lot/shell/zoo_worldskin.gd' in _settings_block(text)
