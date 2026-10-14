"""A package carries the buildings its scene stands, and no others (Level Factory 0.207.0).

The compose stage themes every Empty the brief was given, and an urban brief is given every corner block and
mid-rise; a candidate stands some. Cold run 9297's package carried sixteen `lot/` packages while its assembly scene
named thirteen: `gs_cornershop_a`, `gs_cornershop_b` and `gs_midrise_g` -- 12.2 MB, and 95 of the 711 model imports
the light bake sets to Static Lightmaps -- shipped and imported for scenes nothing instanced.

FAILS ON 0.206.1: every composed `lot/<id>/` ships. The controls hold the cases where nothing may be left out: no
assembly scene to ask, an assembly that names no package, and a single-shell mission.

Run:  python -m pytest tests/unit/test_export_standing_lot.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tests.unit.glb_fixture import stub_glb  # noqa: E402

from packages.exporting.export import MODE_PORTABLE, ExportProfile, export_mission  # noqa: E402


def _building(composed: Path, bid: str) -> None:
    d = composed / "lot" / bid
    (d / "art" / "zoo").mkdir(parents=True)
    (d / "site.tscn").write_text(
        '[gd_scene load_steps=2 format=3]\n\n'
        f'[ext_resource type="PackedScene" path="res://lot/{bid}/art/zoo/wall.glb" id="1"]\n', encoding="utf-8")
    stub_glb(d / "art" / "zoo" / "wall.glb", bid)


def _export(root: Path, *, composed_ids, stood_ids, assembly=True) -> Path:
    handoff = root / "handoff"
    handoff.mkdir(parents=True)
    (handoff / "mission_manifest.json").write_text("{}", encoding="utf-8")
    lux = root / "lux_out"
    lux.mkdir(parents=True)
    (lux / "lux.applied.tscn").write_text(
        '[gd_scene format=3]\n' + "".join(
            f'[ext_resource type="PackedScene" path="res://lot/{b}/site.tscn" id="{b}"]\n' for b in stood_ids),
        encoding="utf-8")
    (lux / "lux.quality.json").write_text("{}", encoding="utf-8")
    composed = root / "composed"
    composed.mkdir(parents=True)
    (composed / "site.tscn").write_text('[gd_scene format=3]\n', encoding="utf-8")
    for b in composed_ids:
        _building(composed, b)
    themed = root / "themed"
    themed.mkdir(parents=True)
    (themed / "site.tscn").write_text(
        '[gd_scene format=3]\n' + "".join(
            f'[ext_resource type="PackedScene" path="lot/{b}/site.tscn" id="{b}"]\n' for b in stood_ids),
        encoding="utf-8")
    result = export_mission(
        mission_id="m1", out_root=root / "exports", profile=ExportProfile(mode=MODE_PORTABLE),
        handoff_dir=handoff, presentation_dir=lux, composed_root=composed,
        themed_site_dir=themed if assembly else None, source_dir=None, tool_versions={},
        layers=frozenset({"art"}))
    return result.export_dir


def test_a_composed_building_no_scene_stands_is_left_out(tmp_path, capsys):
    """THE DEFECT: three stood, two composed beside them for nothing."""
    out = _export(tmp_path, composed_ids=("b1", "b2", "b3", "idle_a", "idle_b"), stood_ids=("b1", "b2", "b3"))
    shipped = sorted(p.name for p in (out / "lot").iterdir() if p.is_dir())
    assert shipped == ["b1", "b2", "b3"], shipped
    for b in ("b1", "b2", "b3"):
        assert (out / "lot" / b / "art" / "zoo" / "wall.glb").is_file(), b
    assert "2 composed building(s) no scene stands, left out: idle_a, idle_b" in capsys.readouterr().out


def test_a_name_shared_with_a_stood_building_is_not_matched_loosely(tmp_path):
    """By the path's first two parts, never by a name: `b1` stood keeps `b1`, and `b10` idle goes."""
    out = _export(tmp_path, composed_ids=("b1", "b10"), stood_ids=("b1",))
    assert sorted(p.name for p in (out / "lot").iterdir() if p.is_dir()) == ["b1"]


def test_with_no_assembly_scene_everything_composed_ships(tmp_path):
    """The control: no scene to ask, so nothing is left out -- absence decides toward including."""
    out = _export(tmp_path, composed_ids=("b1", "idle_a"), stood_ids=("b1",), assembly=False)
    assert sorted(p.name for p in (out / "lot").iterdir() if p.is_dir()) == ["b1", "idle_a"]


def test_an_assembly_naming_no_package_leaves_nothing_out(tmp_path):
    """The control: an assembly with no `lot/<id>/site.tscn` cannot say what stands."""
    out = _export(tmp_path, composed_ids=("b1", "b2"), stood_ids=())
    assert sorted(p.name for p in (out / "lot").iterdir() if p.is_dir()) == ["b1", "b2"]


def test_when_every_composed_building_stands_nothing_is_left_out(tmp_path, capsys):
    out = _export(tmp_path, composed_ids=("b1", "b2"), stood_ids=("b1", "b2"))
    assert sorted(p.name for p in (out / "lot").iterdir() if p.is_dir()) == ["b1", "b2"]
    assert "left out" not in capsys.readouterr().out
