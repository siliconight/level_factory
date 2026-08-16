"""Roadmap 49: the composed root lands where the assembly scene says it does.

`export_mission` copies the composed root into the package. Where it lands
used to be unconditional -- the package root -- which is right for a varied
lot (its composed root already holds `lot/<archetype>/` per building) and
wrong for a single-shell mission, where the composed root IS the one building
laid flat. Step 2.5 then overwrites the root `site.tscn` with the ASSEMBLY
scene, whose only `ext_resource` is `lot/<id>/site.tscn` -- a directory
nothing put in the package. Measured on unlit_probe_001, 2026-08-16: 56 files
shipped, the entry reached 2, EXPORT_CLOSURE_BROKEN in BOTH portable-godot
and art-unlit. Every single-shell themed export since 0.37.0 was unopenable.

These test `_assembly_building_dir`, which decides it. Each case is a fact it
reads off disk, so each test writes that fact and asserts the answer.

Run:  python -m pytest tests/unit/test_assembly_building_dir.py
"""
from pathlib import Path

from packages.exporting.export import _assembly_building_dir


def _assembly(tmp: Path, body: str) -> Path:
    d = tmp / "themed"
    d.mkdir(parents=True, exist_ok=True)
    (d / "site.tscn").write_text(body, encoding="utf-8")
    return d


ONE = ('[gd_scene load_steps=2 format=3]\n\n'
       '[ext_resource type="PackedScene" path="lot/shell/site.tscn" id="b1"]\n')
FIVE = '[gd_scene format=3]\n' + "".join(
    f'[ext_resource type="PackedScene" path="lot/a0{i}/site.tscn" id="b{i}"]\n'
    for i in range(1, 6))


def test_a_single_reference_names_its_directory(tmp_path):
    themed = _assembly(tmp_path, ONE)
    composed = tmp_path / "composed"
    composed.mkdir()
    assert _assembly_building_dir(themed, composed) == "lot/shell"


def test_the_id_is_read_not_assumed(tmp_path):
    """`shell` is a literal on one code branch, not a universal name."""
    themed = _assembly(tmp_path, ONE.replace("lot/shell/", "lot/depot_a01/"))
    composed = tmp_path / "composed"
    composed.mkdir()
    assert _assembly_building_dir(themed, composed) == "lot/depot_a01"


def test_a_varied_lot_is_left_alone(tmp_path):
    """Five references is a varied lot; its composed root already carries the
    buildings and moving it would break what works."""
    themed = _assembly(tmp_path, FIVE)
    composed = tmp_path / "composed"
    composed.mkdir()
    assert _assembly_building_dir(themed, composed) == ""


def test_a_composed_root_that_already_has_lot_is_left_alone(tmp_path):
    """The second guard, and it is not redundant with the first: a composed
    root holding `lot/` is the varied shape even if the scene names one."""
    themed = _assembly(tmp_path, ONE)
    composed = tmp_path / "composed"
    (composed / "lot" / "shell").mkdir(parents=True)
    assert _assembly_building_dir(themed, composed) == ""


def test_no_assembly_scene_changes_nothing(tmp_path):
    composed = tmp_path / "composed"
    composed.mkdir()
    assert _assembly_building_dir(tmp_path / "nope", composed) == ""
    assert _assembly_building_dir(None, composed) == ""


def test_a_scene_naming_no_lot_reference_changes_nothing(tmp_path):
    """A graybox assembly instances geometry directly and names no package."""
    themed = _assembly(tmp_path, '[gd_scene format=3]\n'
                       '[ext_resource type="PackedScene" '
                       'path="buildings/shell.glb" id="b1"]\n')
    composed = tmp_path / "composed"
    composed.mkdir()
    assert _assembly_building_dir(themed, composed) == ""


def test_the_same_reference_twice_is_still_one_directory(tmp_path):
    """Two placements of ONE building -- the ids are deduped, not counted."""
    themed = _assembly(tmp_path, ONE + ONE.splitlines()[-1] + "\n")
    composed = tmp_path / "composed"
    composed.mkdir()
    assert _assembly_building_dir(themed, composed) == "lot/shell"
