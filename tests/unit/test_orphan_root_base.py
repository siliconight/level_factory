"""A varied lot shipped a `site_base.glb` no scene in the package named.

Cold run 9061, `LF_card_block_001.portable-godot`: 371,260 bytes at the
package root -- 525 nodes, 279 meshes, 18 `stair0_*` flight meshes -- while
`grep -rn site_base --include=*.tscn` over the package hit only the three
`lot/<id>/site.tscn`, each naming its own `res://lot/<id>/site_base.glb`. It
was in `portable_resource_manifest.json`, so it shipped and imported rather
than merely sitting on disk, and with no `art/` beside it 0.93.0's worldskin
guard push_errors on every import about a file nobody loads. Cold run 9057's
`LF_club_block_001` carries the same orphan at 400,444 bytes.

IT IS NOT THE FIRST BUILDING'S BASE, which is what the sizes say and what
makes the producer worth naming: `adapters/presentation.plan_commands`
composes the mission's OWN shell to `presentation/site.tscn` for every
mission, varied or not. The export already refused that scene -- Lux names
`res://lot/<id>/site.tscn` and never `res://site.tscn` -- and kept the base
the scene alone named.

So these ask the one question that decides it: does the composer's root base
leave with the composer's root scene, on each of the three paths through the
copy.

Run:  python -m pytest tests/unit/test_orphan_root_base.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tests.unit.glb_fixture import stub_glb  # noqa: E402

from packages.exporting.export import (  # noqa: E402
    MODE_ART_UNLIT, MODE_PORTABLE, ExportProfile, export_mission,
)

#: What Deli Counter's composer writes at the root of a composed package: the
#: scene, and the greybox base it alone names.
_ROOT_SCENE = ('[gd_scene load_steps=2 format=3]\n\n'
               '[ext_resource type="PackedScene" path="res://site_base.glb" '
               'id="0_greybox_base"]\n')


def _building(composed: Path, bid: str) -> None:
    """One `lot/<id>/` package, naming ITS OWN base and no other."""
    d = composed / "lot" / bid
    d.mkdir(parents=True)
    (d / "site.tscn").write_text(
        '[gd_scene load_steps=2 format=3]\n\n'
        '[ext_resource type="PackedScene" '
        f'path="res://lot/{bid}/site_base.glb" id="0_greybox_base"]\n',
        encoding="utf-8")
    stub_glb(d / "site_base.glb", bid)
    # The composer drops a copy of the import script beside every package.
    # Only the ROOT one is ever named -- see `_COMPOSED_ROOT_PAIR`.
    (d / "zoo_worldskin.gd").write_text("@tool\n", encoding="utf-8")


def _mission(root: Path, *, buildings, with_lux: bool):
    """Job directories shaped like a themed mission with `buildings` shells.

    The composed root always carries the mission's own shell flat -- scene,
    base and import script -- because the compose adapter always writes it.
    """
    handoff = root / "handoff"
    handoff.mkdir(parents=True)
    (handoff / "mission_manifest.json").write_text("{}", encoding="utf-8")

    lux = root / "lux_out"
    lux.mkdir(parents=True)
    if with_lux:
        # Lux is run over the ASSEMBLY, so it names the buildings and never
        # `res://site.tscn`. This is the fact `_root_site_wanted` reads.
        (lux / "lux.applied.tscn").write_text(
            '[gd_scene format=3]\n' + "".join(
                f'[ext_resource type="PackedScene" '
                f'path="res://lot/{b}/site.tscn" id="{b}"]\n'
                for b in buildings), encoding="utf-8")
        (lux / "lux.quality.json").write_text("{}", encoding="utf-8")

    composed = root / "composed"
    composed.mkdir(parents=True)
    (composed / "site.tscn").write_text(_ROOT_SCENE, encoding="utf-8")
    stub_glb(composed / "site_base.glb", "shell")
    (composed / "zoo_worldskin.gd").write_text("@tool\n", encoding="utf-8")
    for b in buildings:
        _building(composed, b)

    themed = root / "themed"
    themed.mkdir(parents=True)
    (themed / "site.tscn").write_text(
        '[gd_scene format=3]\n' + "".join(
            f'[ext_resource type="PackedScene" path="lot/{b}/site.tscn" '
            f'id="{b}"]\n' for b in buildings), encoding="utf-8")
    return handoff, lux, composed, themed


def _export(root: Path, *, buildings, mode=MODE_PORTABLE, themed=True,
            with_lux=True) -> Path:
    handoff, lux, composed, themed_dir = _mission(
        root, buildings=buildings, with_lux=with_lux)
    result = export_mission(
        mission_id="m1", out_root=root / "exports",
        profile=ExportProfile(mode=mode),
        handoff_dir=handoff, presentation_dir=lux, composed_root=composed,
        themed_site_dir=themed_dir if themed else None,
        source_dir=None, tool_versions={}, layers=frozenset({"art"}),
    )
    return result.export_dir


# ------------------------------------------------------------- a varied lot

def test_a_varied_lot_ships_no_root_base(tmp_path):
    """THE DEFECT. The scene is refused; the base it named goes with it."""
    out = _export(tmp_path, buildings=("b1", "b2", "b3"))
    assert not (out / "site_base.glb").exists(), (
        "the composer's root base shipped with nothing to name it")


def test_a_varied_lot_still_ships_every_building_base(tmp_path):
    """The guard on the fix: `skip` matches basenames anywhere in the tree,
    and `site_base.glb` is the name of four different files here. Skipping by
    name would take all four and leave three buildings unresolved -- the
    failure the `skip_rel` note above the call records for `site.tscn`."""
    out = _export(tmp_path, buildings=("b1", "b2", "b3"))
    for b in ("b1", "b2", "b3"):
        assert (out / "lot" / b / "site_base.glb").is_file(), b


def test_the_root_import_script_stays(tmp_path):
    """`project.godot` names `res://zoo_worldskin.gd` as the scene importer
    default, so every `.import` in the package points at the ROOT copy. It
    sits beside the base and is not part of the pair."""
    out = _export(tmp_path, buildings=("b1", "b2"))
    assert (out / "zoo_worldskin.gd").is_file()


def test_the_root_scene_is_still_the_assembly(tmp_path):
    """Unchanged behaviour, asserted so the fix cannot be read as dropping
    the root scene: step 2.5 writes the assembly there."""
    out = _export(tmp_path, buildings=("b1", "b2"))
    body = (out / "site.tscn").read_text(encoding="utf-8")
    assert "lot/b1/site.tscn" in body
    assert "res://site_base.glb" not in body


# -------------------------------------------- the two paths that keep it

def test_a_single_shell_keeps_its_base_under_the_building(tmp_path):
    """One building and no `lot/` in the composed root is roadmap 49's
    single-shell shape: the whole composed root moves under `lot/<id>/`,
    where the assembly names the scene and the scene names the base."""
    handoff = tmp_path / "handoff"
    handoff.mkdir(parents=True)
    (handoff / "mission_manifest.json").write_text("{}", encoding="utf-8")
    lux = tmp_path / "lux_out"
    lux.mkdir(parents=True)
    (lux / "lux.applied.tscn").write_text(
        '[gd_scene format=3]\n[ext_resource type="PackedScene" '
        'path="res://lot/shell/site.tscn" id="b"]\n', encoding="utf-8")
    composed = tmp_path / "composed"
    composed.mkdir(parents=True)
    (composed / "site.tscn").write_text(_ROOT_SCENE, encoding="utf-8")
    stub_glb(composed / "site_base.glb", "shell")
    themed = tmp_path / "themed"
    themed.mkdir(parents=True)
    (themed / "site.tscn").write_text(
        '[gd_scene format=3]\n[ext_resource type="PackedScene" '
        'path="lot/shell/site.tscn" id="b"]\n', encoding="utf-8")
    out = export_mission(
        mission_id="m1", out_root=tmp_path / "exports",
        profile=ExportProfile(mode=MODE_PORTABLE),
        handoff_dir=handoff, presentation_dir=lux, composed_root=composed,
        themed_site_dir=themed, source_dir=None, tool_versions={},
        layers=frozenset({"art"}),
    ).export_dir
    assert (out / "lot" / "shell" / "site_base.glb").is_file()
    assert (out / "lot" / "shell" / "site.tscn").is_file()
    assert not (out / "site_base.glb").exists()


def test_no_lux_scene_keeps_the_root_pair(tmp_path):
    """`_root_site_wanted` answers True when there is no presentation scene
    to ask: the composer's root scene IS the entry then, and an entry with no
    base is the empty package the guard above it was written for."""
    out = _export(tmp_path, buildings=("b1",), mode=MODE_ART_UNLIT,
                  themed=False, with_lux=False)
    assert (out / "site.tscn").is_file()
    assert (out / "site_base.glb").is_file()
