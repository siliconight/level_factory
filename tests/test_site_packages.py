"""Staging is pure file work, so it is checked without Blender or Godot.

The fixtures are CAPTURED, not invented: the ext_resource blocks below are the
real headers emitted by presentation_compose for lot_demo_001 (final_stand and
pharmacy_a02, 2026-08-06). A rule tested only against scenes written by the
test is a rule tested against the test's idea of the format.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from packages.staging.site_packages import (  # noqa: E402
    SKIP_NAMES, StagingError, absolute_refs, portable_refs, stage_all,
    stage_glb, stage_package,
)

# --- captured: final_stand/site.tscn, header verbatim ----------------------
FINAL_STAND = '''[gd_scene load_steps=4 format=3]

[ext_resource type="PackedScene" path="res://site_base.glb" id="0_greybox_base"]

[ext_resource type="PackedScene" path="res://art/dressing/lf_lot_demo_001_5118_dressing.glb" id="L_Dressing"]

[ext_resource type="PackedScene" path="res://art/fixtures/lf_lot_demo_001_5118_fixtures.glb" id="L_Fixtures"]

[node name="site" type="Node3D"]

[node name="GreyboxBase" parent="." instance=ExtResource("0_greybox_base")]

[node name="Markers" type="Node3D" parent="."]

[node name="ATTACKER_SPAWN_A" type="Node3D" parent="Markers" groups=["attacker_spawn", "dc_marker"]]
transform = Transform3D(1, 0, 0, 0, 1, 0, 0, 0, 1, 0.0, 0.0, 19.0)
metadata/marker_type = "attacker_spawn"
'''

# --- captured: pharmacy_a02/site.tscn, ext_resource block verbatim ---------
PHARMACY = '''[gd_scene load_steps=14 format=3]

[ext_resource type="PackedScene" path="res://site_base.glb" id="0_greybox_base"]
[ext_resource type="PackedScene" path="res://art/zoo/wall_rockay_01_w200.glb" id="1_wall_rockay_01_w200"]
[ext_resource type="PackedScene" path="res://art/zoo/wallEnd_rockay_01.glb" id="3_wallEnd_rockay_01"]
[ext_resource type="PackedScene" path="res://art/dressing/lf_lot_demo_001_5118_dressing.glb" id="L_Dressing"]

[node name="site" type="Node3D"]
'''

# --- captured: the shape the defect actually ships -------------------------
BROKEN_SITE = '''[gd_scene load_steps=3 format=3]

[ext_resource type="PackedScene" path="res://C:/Projects/gabagool_studios/gabagool_factory/lot-demo-ws/.level_factory/jobs/lot_demo_001.presentation_compose/out/presentation/lot/final_stand/site.tscn" id="b1"]

[node name="Site" type="Node3D"]
'''


def _package(root: Path, scene_text: str) -> Path:
    """A composed package on disk: the scene, plus every file it names."""
    import re
    root.mkdir(parents=True, exist_ok=True)
    (root / "site.tscn").write_text(scene_text, encoding="utf-8")
    for ref in re.findall(r'path="res://([^"]+)"', scene_text):
        target = root / ref
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"glTF stand-in")
    # the harness files a real package carries and staging must drop
    (root / "project.godot").write_text("config_version=5\n", encoding="utf-8")
    (root / "site_main.tscn").write_text(
        '[gd_scene load_steps=2 format=3]\n\n'
        '[ext_resource type="PackedScene" path="res://site.tscn" id="1"]\n',
        encoding="utf-8")
    (root / "HANDOFF.md").write_text("# handoff\n", encoding="utf-8")
    (root / "compose.summary.json").write_text("{}", encoding="utf-8")
    (root / "portable_resource_manifest.json").write_text("{}", encoding="utf-8")
    return root


# ---------------------------------------------------------------------------
# the rewrite itself
# ---------------------------------------------------------------------------
def test_root_scene_refs_lose_the_res_prefix_and_nothing_else():
    out = portable_refs(FINAL_STAND)
    assert 'path="site_base.glb"' in out
    assert 'path="art/dressing/lf_lot_demo_001_5118_dressing.glb"' in out
    assert "res://" not in out
    # ids, node lines and transforms are untouched
    assert 'id="0_greybox_base"' in out
    assert "transform = Transform3D(1, 0, 0, 0, 1, 0, 0, 0, 1, 0.0, 0.0, 19.0)" in out
    assert out.count("[ext_resource") == FINAL_STAND.count("[ext_resource")


def test_a_nested_scene_is_rewritten_against_its_own_directory():
    """``res://X`` is package-root-relative; a bare path is scene-relative.

    They coincide only at the root, so a scene one level down must climb back
    out. This is the term `portable_refs` would silently drop if it ignored
    the directory it was handed.
    """
    out = portable_refs(PHARMACY, scene_rel_dir="art/zoo")
    assert 'path="../../site_base.glb"' in out
    assert 'path="wall_rockay_01_w200.glb"' in out


def test_embedded_preload_is_not_a_rewrite_target():
    text = ('[gd_scene format=3]\n\n'
            '[ext_resource type="PackedScene" path="res://site_base.glb" id="1"]\n\n'
            '[sub_resource type="GDScript" id="s"]\n'
            'script/source = "extends Node3D\n'
            "\tadd_child(preload('res://site.tscn').instantiate())\n\"\n")
    out = portable_refs(text)
    assert 'path="site_base.glb"' in out
    assert "preload('res://site.tscn')" in out  # code, not data


# ---------------------------------------------------------------------------
# the defect, stated as a check
# ---------------------------------------------------------------------------
def test_absolute_refs_finds_the_shipped_defect():
    found = absolute_refs(BROKEN_SITE)
    assert len(found) == 1
    assert found[0].startswith("res://C:/Projects/")


@pytest.mark.parametrize("path", [
    "res://C:/Projects/x/site.tscn",
    "res://D:\\work\\site.tscn",
    "res:///absolute/site.tscn",
])
def test_absolute_refs_reads_every_punctuation_of_the_same_mistake(path):
    scene = f'[ext_resource type="PackedScene" path="{path}" id="b1"]\n'
    assert absolute_refs(scene) == [path]


def test_a_correctly_staged_site_scene_has_no_absolute_refs():
    good = '[ext_resource type="PackedScene" path="lot/final_stand/site.tscn" id="b1"]\n'
    assert absolute_refs(good) == []


# ---------------------------------------------------------------------------
# staging a package
# ---------------------------------------------------------------------------
def test_stage_package_copies_content_drops_harness_rewrites_scene(tmp_path):
    src = _package(tmp_path / "src" / "final_stand", FINAL_STAND)
    dest = tmp_path / "out"

    ref = stage_package(src, dest, "final_stand")
    assert ref == "lot/final_stand/site.tscn"

    staged = dest / "lot" / "final_stand"
    assert (staged / "site_base.glb").is_file()
    assert (staged / "art" / "dressing" /
            "lf_lot_demo_001_5118_dressing.glb").is_file()
    for name in SKIP_NAMES:
        assert not (staged / name).exists(), f"{name} should not be staged"
    assert not (staged / "site_main.tscn").exists()

    text = (staged / "site.tscn").read_text(encoding="utf-8")
    assert "res://" not in text
    # every rewritten ref resolves as a sibling path, which is what Godot
    # resolves a bare ext_resource path against
    import re
    for rel in re.findall(r'path="([^"]+)"', text):
        assert (staged / rel).is_file(), rel


def test_two_packages_that_would_collide_do_not(tmp_path):
    _package(tmp_path / "src" / "final_stand", FINAL_STAND)
    _package(tmp_path / "src" / "pharmacy_a02", PHARMACY)
    dest = tmp_path / "out"

    a = stage_package(tmp_path / "src" / "final_stand", dest, "final_stand")
    b = stage_package(tmp_path / "src" / "pharmacy_a02", dest, "pharmacy_a02")

    assert a != b
    # both packages ship a file called site_base.glb; the whole point is that
    # they are now two files rather than one overwriting the other
    fs = dest / "lot" / "final_stand" / "site_base.glb"
    ph = dest / "lot" / "pharmacy_a02" / "site_base.glb"
    assert fs.is_file() and ph.is_file()
    assert fs != ph


def test_restaging_replaces_rather_than_merges(tmp_path):
    src = _package(tmp_path / "src" / "depot_a01", PHARMACY)
    dest = tmp_path / "out"
    stage_package(src, dest, "depot_a01")
    stale = dest / "lot" / "depot_a01" / "art" / "zoo" / "gone.glb"
    stale.write_bytes(b"from a previous run")

    stage_package(src, dest, "depot_a01")
    assert not stale.exists()


# ---------------------------------------------------------------------------
# refusing, loudly
# ---------------------------------------------------------------------------
def test_a_missing_package_raises_rather_than_shrinking_the_lot(tmp_path):
    with pytest.raises(StagingError, match="not a directory"):
        stage_package(tmp_path / "never_composed", tmp_path / "out", "ghost")


def test_a_package_without_a_scene_raises(tmp_path):
    empty = tmp_path / "src" / "half_composed"
    empty.mkdir(parents=True)
    with pytest.raises(StagingError, match="no site.tscn"):
        stage_package(empty, tmp_path / "out", "half_composed")


def test_a_runtime_preload_in_a_kept_scene_raises(tmp_path):
    src = tmp_path / "src" / "odd"
    _package(src, FINAL_STAND)
    (src / "extra.tscn").write_text(
        '[gd_scene format=3]\n\n'
        '[sub_resource type="GDScript" id="s"]\n'
        "script/source = \"extends Node\n"
        "\tvar x = preload('res://art/zoo/thing.glb')\n\"\n",
        encoding="utf-8")
    with pytest.raises(StagingError, match="at runtime"):
        stage_package(src, tmp_path / "out", "odd")


def test_a_missing_greybox_glb_raises(tmp_path):
    with pytest.raises(StagingError, match="no geometry"):
        stage_glb(tmp_path / "nope.glb", tmp_path / "out", "b0")


# ---------------------------------------------------------------------------
# the whole manifest
# ---------------------------------------------------------------------------
def test_stage_all_returns_the_refs_the_site_spec_should_name(tmp_path):
    _package(tmp_path / "src" / "final_stand", FINAL_STAND)
    _package(tmp_path / "src" / "pharmacy_a02", PHARMACY)
    shell = tmp_path / "src" / "shell.glb"
    shell.write_bytes(b"glTF stand-in")
    addons = tmp_path / "addons"
    addons.mkdir()
    (addons / "lot_player.gd").write_text("extends CharacterBody3D\n",
                                          encoding="utf-8")
    (addons / "lot_site_walk.gd").write_text("extends Node3D\n",
                                             encoding="utf-8")

    dest = tmp_path / "out"
    report = stage_all({
        "packages": {"final_stand": str(tmp_path / "src" / "final_stand"),
                     "pharmacy_a02": str(tmp_path / "src" / "pharmacy_a02")},
        "glbs": {"b4": str(shell)},
        "addon_dir": str(addons),
    }, dest)

    assert report["packages"] == {
        "final_stand": "lot/final_stand/site.tscn",
        "pharmacy_a02": "lot/pharmacy_a02/site.tscn",
    }
    assert report["glbs"] == {"b4": "buildings/b4.glb"}
    assert sorted(report["addons"]) == ["lot_player.gd", "lot_site_walk.gd"]
    # the walk scene written by write_walk_scene(portable=True) names these
    # bare at the site root, so that is where they have to be
    assert (dest / "lot_player.gd").is_file()
    assert (dest / "buildings" / "b4.glb").is_file()


def test_stage_all_is_empty_and_harmless_with_nothing_to_do(tmp_path):
    report = stage_all({}, tmp_path / "out")
    assert report == {"packages": {}, "glbs": {}, "addons": []}
