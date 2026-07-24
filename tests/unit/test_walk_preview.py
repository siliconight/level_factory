"""Unit tests: dev-only walk-preview builder.

Proves the separation the architecture requires: the drop-in content package is
never modified and never becomes a project; the preview is a SEPARATE throwaway
project that wraps the content and adds the player at a spawn marker.
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from packages.preview.walk_preview import build_walk_preview  # noqa: E402

_PLAYER_SRC = ROOT / "assets" / "godot"

_SITE_TSCN = '''[gd_scene load_steps=2 format=3]

[ext_resource type="PackedScene" path="res://site_base.glb" id="1_base"]

[node name="site" type="Node3D"]

[node name="GreyboxBase" parent="." instance=ExtResource("1_base")]

[node name="Markers" type="Node3D" parent="."]

[node name="AUTO_FRONT_DOOR" type="Node3D" parent="Markers" groups=["door", "dc_marker"]]
transform = Transform3D(1, 0, 0, 0, 1, 0, 0, 0, 1, 1.0, 0.0, 2.0)
metadata/marker_type = "door"

[node name="SPAWN_1" type="Node3D" parent="Markers" groups=["spawn", "dc_marker"]]
transform = Transform3D(1, 0, 0, 0, 1, 0, 0, 0, 1, 5.0, 0.0, -3.0)
metadata/marker_type = "spawn"
'''


@pytest.fixture()
def content_dir(tmp_path):
    """A minimal drop-in content package as presentation_compose emits it."""
    c = tmp_path / "presentation"
    (c / "art" / "zoo").mkdir(parents=True)
    (c / "site.tscn").write_text(_SITE_TSCN, encoding="utf-8")
    (c / "site_base.glb").write_bytes(b"glb-base")
    (c / "art" / "zoo" / "wall_rockay_01_w200.glb").write_bytes(b"glb-wall")
    # Package harness/meta that must NOT leak into the preview project.
    (c / "project.godot").write_text('config/name="site (portable building)"\n')
    (c / "site_main.tscn").write_text("[gd_scene format=3]\n")
    (c / "HANDOFF.md").write_text("# handoff\n")
    (c / "portable_resource_manifest.json").write_text("{}")
    return c


def test_preview_is_a_separate_project_wrapping_the_content(content_dir, tmp_path):
    dest = tmp_path / "preview"
    report = build_walk_preview(content_dir, _PLAYER_SRC, dest, name="cat5")

    # It's a runnable project whose main scene is the walk wrapper.
    proj = (dest / "project.godot").read_text(encoding="utf-8")
    assert 'run/main_scene="res://walk.tscn"' in proj
    assert 'config/features=PackedStringArray("4.7")' in proj

    # The walk scene instances the SAME content scene + the player.
    walk = (dest / "walk.tscn").read_text(encoding="utf-8")
    assert 'path="res://site.tscn"' in walk
    assert 'path="res://player_walk.tscn"' in walk
    assert '[node name="Player"' in walk

    # Player controller + content came along so res:// refs resolve.
    assert (dest / "player_walk.tscn").exists()
    assert (dest / "player_walk.gd").exists()
    assert (dest / "site.tscn").exists()
    assert (dest / "site_base.glb").exists()
    assert (dest / "art" / "zoo" / "wall_rockay_01_w200.glb").exists()


def test_preview_does_not_leak_package_harness(content_dir, tmp_path):
    dest = tmp_path / "preview"
    build_walk_preview(content_dir, _PLAYER_SRC, dest, name="cat5")
    # The preview writes its OWN project.godot; the package's harness/meta files
    # are not copied in.
    assert not (dest / "site_main.tscn").exists()
    assert not (dest / "HANDOFF.md").exists()
    assert not (dest / "portable_resource_manifest.json").exists()
    # project.godot exists but is the preview's (main scene = walk), not the
    # package's standalone one.
    assert 'main_scene="res://walk.tscn"' in (dest / "project.godot").read_text()


def test_content_package_is_left_untouched(content_dir, tmp_path):
    """Building the preview must not mutate the drop-in package."""
    before = {p.name for p in content_dir.iterdir()}
    build_walk_preview(content_dir, _PLAYER_SRC, tmp_path / "preview", name="cat5")
    after = {p.name for p in content_dir.iterdir()}
    assert before == after
    assert "player_walk.tscn" not in after  # no player leaked into the package
    assert "walk.tscn" not in after


def test_spawn_prefers_higher_priority_marker(content_dir, tmp_path):
    dest = tmp_path / "preview"
    report = build_walk_preview(content_dir, _PLAYER_SRC, dest, name="cat5")
    # 'spawn' outranks 'door'; origin is the spawn marker lifted +0.6 on Y.
    assert report["spawn_source"] == "marker:spawn"
    assert report["spawn_transform"][9:] == [5.0, 0.6, -3.0]


def test_missing_content_scene_raises(tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(FileNotFoundError):
        build_walk_preview(empty, _PLAYER_SRC, tmp_path / "preview")
