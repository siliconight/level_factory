"""A draw distance from each part's own size (0.272.0).

No mesh in a package had a draw distance. `_draw_distance` gives each part of an object's GLB the distance at which
its bounding sphere spans `DRAW_PX` pixels of a `DRAW_SCREEN_H` screen through a `DRAW_FOV_DEG` camera, keeps any part
that lights to every distance, keeps a range already set, and runs on no kit tile, dressing or building base. Read
as source, as the other worldskin tests are; the derivation is checked in numbers here.
"""
import math
import re
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "assets" / "godot" / "zoo_worldskin.gd"


def _src() -> str:
    return SCRIPT.read_text(encoding="utf-8")


def _func(src: str, name: str) -> str:
    m = re.search(r"^func %s\(.*?(?=^func |^## |\Z)" % re.escape(name), src, re.S | re.M)
    assert m, f"no func {name} in {SCRIPT.name}"
    return m.group(0)


def _const(src: str, name: str) -> float:
    m = re.search(r"^const %s: float = ([0-9.]+)$" % name, src, re.M)
    assert m, name
    return float(m.group(1))


def test_the_distance_is_derived_from_the_games_camera_and_a_pixel_threshold():
    """FAILS ON 0.271.0: no draw distance."""
    src = _src()
    px, h, fov = _const(src, "DRAW_PX"), _const(src, "DRAW_SCREEN_H"), _const(src, "DRAW_FOV_DEG")
    assert (px, h, fov) == (3.0, 1080.0, 75.0)
    body = _func(src, "_draw_distance")
    assert "var k: float = (DRAW_SCREEN_H / 2.0) / tan(deg_to_rad(DRAW_FOV_DEG) / 2.0)" in body
    assert "var end: float = radius * k / DRAW_PX" in body
    # about 235 x the radius: a meter's 0.15 m window at about 35 m, its 0.6 m body at about 140 m
    k = (h / 2.0) / math.tan(math.radians(fov) / 2.0)
    assert 234.0 < k / px < 235.0
    assert 30.0 < 0.15 * k / px < 40.0 and 130.0 < 0.6 * k / px < 150.0


def test_the_walk_camera_is_the_one_derived_from():
    """`DRAW_FOV_DEG` is Godot's default because the walk player's Camera3D sets none; one that set a FOV would make
    this constant wrong."""
    player = (SCRIPT.parent / "player_walk.tscn").read_text(encoding="utf-8")
    assert "fov" not in player


def test_a_lit_part_and_a_range_already_set_are_kept():
    body = _func(_src(), "_draw_distance")
    assert "if mi.visibility_range_end > 0.0:" in body
    assert "m is ShaderMaterial or (bm != null and bm.emission_enabled)" in body
    assert "mi.visibility_range_end_margin = end * DRAW_HYSTERESIS" in body
    # the part's own size, in the GLB's space
    assert "var box: AABB = _stain_to_root(mi, scene) * mi.mesh.get_aabb()" in body


def test_only_an_objects_glb_never_a_kit_tile_dressing_or_base():
    post = _func(_src(), "_post_import")
    call = post.index("_draw_distance(scene)")
    branch = post.rfind("if not is_kit and not _is_tiled(base):", 0, call)
    assert branch != -1 and post.rfind("\n\tif ", branch + 1, call) == -1
    assert "if not base.begins_with(BASE_PREFIX):" in post[branch:call]
