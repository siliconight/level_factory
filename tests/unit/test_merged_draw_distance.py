"""A draw distance on the meshes the export merges, and a solid object's silhouette kept (0.273.0).

0.272.0 gave each part of an object's GLB a draw distance at import. The meshes `merge_buildings.gd` and
`merge_empties.gd` make at export were not imports and had none; each now gets the same rule from its own size, a lit
one keeps every distance, and the Python halves refuse a report that does not account for every merged mesh. At
import, an object carrying a collider keeps its largest part at every distance: cover stays visible wherever it can
stop a shot (the factory's draw-distance handoff, REQ-001 and VAL-004). Read as source, as the worldskin tests are.
"""
import importlib
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

GODOT = Path(__file__).resolve().parents[2] / "assets" / "godot"
SCRIPTS = ("zoo_worldskin.gd", "merge_buildings.gd", "merge_empties.gd")
CONSTS = ("DRAW_PX", "DRAW_SCREEN_H", "DRAW_FOV_DEG", "DRAW_ZOOM", "DRAW_HYSTERESIS")


def _src(name: str) -> str:
    return (GODOT / name).read_text(encoding="utf-8")


def _func(src: str, name: str) -> str:
    m = re.search(r"^func %s\(.*?(?=^func |^## |^const |\Z)" % re.escape(name), src, re.S | re.M)
    assert m, f"no func {name}"
    return m.group(0)


def _const(src: str, name: str) -> float:
    m = re.search(r"^const %s: float = ([0-9.]+)$" % name, src, re.M)
    assert m, name
    return float(m.group(1))


def test_the_three_scripts_share_one_rule():
    """FAILS ON 0.272.0: the merges carry no DRAW_* constants."""
    values = {s: tuple(_const(_src(s), c) for c in CONSTS) for s in SCRIPTS}
    assert len(set(values.values())) == 1, values
    assert values["zoo_worldskin.gd"] == (3.0, 1080.0, 75.0, 1.0, 0.1)


@pytest.mark.parametrize("script,name", [("merge_buildings.gd", '"MergedR_%d" % k'),
                                         ("merge_empties.gd", '"Merged%s_%d" % [side_tag, k]')])
def test_every_merged_mesh_is_given_a_range_or_kept_for_its_light(script, name):
    src = _src(script)
    body = _func(src, "_draw_range")
    assert "var k: float = (DRAW_SCREEN_H / 2.0) / tan(deg_to_rad(DRAW_FOV_DEG) / 2.0) * DRAW_ZOOM" in body
    assert "var end: float = radius * k / DRAW_PX" in body
    assert "mi.visibility_range_end_margin = end * DRAW_HYSTERESIS" in body
    assert "m is ShaderMaterial or (bm != null and bm.emission_enabled)" in body
    merge = _func(src, "_merge_scene")
    made = merge.index("out.name = %s" % name)
    ranged = merge.index('var ranged: String = "draw_ranged" if _draw_range(out) else "draw_kept_lit"', made)
    assert merge.find("add_child(out)", made) > ranged
    assert '"draw_ranged": 0, "draw_kept_lit": 0' in merge


def test_a_lit_face_and_a_pane_keep_every_distance():
    """A distant storefront keeps its windows and its lit sign: only the merged groups get a range."""
    merge = _func(_src("merge_buildings.gd"), "_merge_scene")
    assert merge.count("_draw_range(") == 1
    assert merge.index("_draw_range(") < merge.index('lout.name = "LitR_%d" % li')


# one real row of each merge's report, as the merge tests write them
ROWS = {
    "merge_buildings": {"slots_merged": 519, "meshes_in": 838, "surfaces_in": 1047, "merged": 470, "unwrapped": 590,
                        "colliders": 485, "units": {"ext": 24, "room": 446}, "lit_surfaces": 132, "lit_meshes": 90,
                        "glass_surfaces": 41, "glass_meshes": 30, "draw_ranged": 468, "draw_kept_lit": 2,
                        "kept_carrying": [], "error": None},
    "merge_empties": {"meshes_in": 95, "surfaces_in": 161, "merged": 13, "unwrapped": 13, "colliders": 86,
                      "doors_dropped": 2, "draw_ranged": 13, "draw_kept_lit": 0, "error": None},
}


@pytest.mark.parametrize("module", sorted(ROWS))
def test_the_python_half_refuses_a_merged_mesh_unaccounted_for(module):
    M = importlib.import_module(f"packages.exporting.{module}")
    scene = "res://lot/x/site.tscn"

    def report(**kw):
        row = dict(ROWS[module], scene=scene, **kw)
        return {"schema": M.SCHEMA, "ok": True, "error": None, "scenes": [{k: v for k, v in row.items() if v != "-"}]}

    M.check(report(), [scene])
    with pytest.raises(M.MergeError, match="ranged"):
        M.check(report(draw_ranged=ROWS[module]["draw_ranged"] - 1), [scene])
    # a report from before 0.273.0 says nothing of it: refused, not passed
    with pytest.raises(M.MergeError, match="draw_ranged"):
        M.check(report(draw_ranged="-"), [scene])


def test_a_solid_objects_largest_part_keeps_every_distance():
    """FAILS ON 0.272.0: every part of a car went by its own size, its body included."""
    src = _src("zoo_worldskin.gd")
    body = _func(src, "_draw_distance")
    assert "var hull: MeshInstance3D = _largest_part(scene, found) if _has_body(scene) else null" in body
    assert body.index("if mi == hull:") < body.index("var end: float = radius * k / DRAW_PX")
    assert "return [set_n, lit_n, hull_n]" in body
    assert "if n is PhysicsBody3D:" in _func(src, "_has_body")
    assert "(_stain_to_root(mi, scene) * mi.mesh.get_aabb()).size.length() / 2.0" in _func(src, "_largest_part")
