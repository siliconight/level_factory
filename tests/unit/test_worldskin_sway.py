"""The wind: a street tree's crown sways at import (0.130.0).

The walker, 2026-10-03: "start with the crowns" (`docs/proposals/WIND_DESIGN.md`
at the factory root). Zoo 1.56.0 writes every corner of a crown with its
sway weight (height over the crown's, squared) and a phase of its own leaf
cluster in its second UV set; this import replaces the crown's skin with a
shader that reproduces the skin and moves the vertices with `lf_wind`, the
one global the shipped project.godot declares from the brief's weather.

These read the GDScript rather than run it -- the unit suite has no Godot --
so they hold the SHAPE: the crown is found by its node name and its second UV
set, the shader's support set and the refusal outside it, the lee lean and
the gust front, the per-node phase, that only crown surfaces are touched and
only once, that it runs before the kit branch, and that the wind global is
declared by both project writers from the same table. What the shader DOES is
measured in frames; see the 0.130.0 changelog.

Run:  python -m pytest tests/unit/test_worldskin_sway.py
"""
import re
from pathlib import Path

import pytest

from packages.core.godot_project import (WIND_BY_WEATHER, WIND_DEFAULT_M_S,
                                         shader_globals_block, wind_for_weather)
from tests.siblings import sibling_repo

SCRIPT = (Path(__file__).resolve().parents[2]
          / "assets" / "godot" / "zoo_worldskin.gd")


def _src() -> str:
    return SCRIPT.read_text(encoding="utf-8")


def _func(src: str, name: str) -> str:
    m = re.search(r"^func %s\(.*?(?=^func |\Z)" % re.escape(name), src,
                  re.S | re.M)
    assert m, f"no func {name} in {SCRIPT.name}"
    return m.group(0)


def _shader(src: str) -> str:
    m = re.search(r'const SWAY_SHADER: String = """(.*?)"""', src, re.S)
    assert m, "no SWAY_SHADER block"
    return m.group(1)


# --- the contract with Zoo ----------------------------------------------------------------


def test_the_crown_is_found_by_its_node_name_and_its_second_uv_set():
    src = _src()
    assert 'const CROWN_NODE_PREFIX: String = "StreetTree_Crown"' in src
    fn = _func(src, "_sway_crowns")
    assert "String(mi.name).begins_with(CROWN_NODE_PREFIX)" in fn
    assert "arrays[Mesh.ARRAY_TEX_UV2]" in fn
    assert "no sway layer: an older Zoo's crown" in fn


def test_the_names_are_zoo_s_when_zoo_is_beside_this_repo():
    zoo = sibling_repo("zoo")
    if zoo is None:
        pytest.skip("zoo is not beside this repo")
    tree = (zoo / "zoo_keeper" / "recipes" / "street_tree.py").read_text(encoding="utf-8")
    assert 'leaves.loops.layers.uv.new("Sway")' in tree
    assert 'part(leaves, "StreetTree_Crown"' in tree
    forms = (zoo / "zoo_keeper" / "core" / "tree_forms.py").read_text(encoding="utf-8")
    assert "SWAY_WEIGHT_POWER = 2.0" in forms


# --- the shader ---------------------------------------------------------------------------


def test_the_shader_reads_the_one_global_and_leans_with_the_wind():
    sh = _shader(_src())
    assert "global uniform vec3 lf_wind;" in sh
    assert "world_vertex_coords" in sh
    assert "float weight = UV2.x;" in sh and "float phase = UV2.y;" in sh
    # the lee lean: weight squared, capped, never past upright
    assert "float lean = weight * weight * min(speed * m_per_ms, cap_m) * gust;" in sh
    assert "VERTEX += dir * lean + across * flutter;" in sh
    # the gust front walks downwind
    assert "float down = dot(VERTEX, dir) / front_ms;" in sh
    assert "if (speed > 0.0001) {" in sh                  # the calm is exactly still


def test_the_phase_is_per_node_so_two_trees_do_not_sway_in_step():
    sh = _shader(_src())
    assert "NODE_POSITION_WORLD" in sh
    assert re.search(r"float inst = sway_hash\(dot\(NODE_POSITION_WORLD", sh)


def test_the_shader_reproduces_the_skin_s_own_numbers_and_nothing_else():
    sh = _shader(_src())
    for p in ("albedo_tex", "has_albedo_tex", "rm_tex", "rough_channel", "metal_channel",
              "uv1_scale", "uv1_offset", "use_vertex_colour", "alpha_scissor"):
        assert "uniform" in sh and p in sh, p
    assert "filter_nearest_mipmap" in sh                 # pixel art stays pixel art
    assert "NORMAL_MAP" not in sh and "EMISSION" not in sh


def test_a_skin_outside_the_support_set_is_refused_by_name():
    src = _src()
    fn = _func(src, "_sway_unsupported")
    for feature in ("normal_enabled", "emission_enabled", "TRANSPARENCY_ALPHA_SCISSOR",
                    "uv1_triplanar", "ao_enabled", "refraction_enabled"):
        assert feature in fn, feature
    crowns = _func(src, "_sway_crowns")
    assert "push_warning" in crowns and "left still" in crowns
    assert "refused += 1" in crowns


def test_a_crown_surface_is_replaced_once_with_the_skin_s_numbers():
    src = _src()
    fn = _func(src, "_sway_crowns")
    assert "surface_set_material(i, _sway_material(" in fn
    assert "if bm == null:" in fn and "already the shader" in fn
    assert "_has_tint(cols)" in fn
    mat = _func(src, "_sway_material")
    for p in ("albedo", "albedo_tex", "rm_tex", "rough_channel", "metal_channel", "roughness",
              "metallic", "uv1_scale", "uv1_offset", "use_vertex_colour", "alpha_scissor"):
        assert 'set_shader_parameter("%s"' % p in mat, p
    assert "_sway_materials[key] = sm" in mat


def test_it_runs_for_every_glb_before_the_kit_branch():
    post = _func(_src(), "_post_import")
    i_sway = post.index("_sway_crowns(scene)")
    i_kit = post.index("var is_kit: bool = false")
    assert i_sway < i_kit
    assert post.index("_churn_passes(scene, {})") < i_sway


# --- the wind in the project --------------------------------------------------------------


def test_the_wind_is_written_from_the_weather_word():
    assert wind_for_weather("clear") == (1.5, 0.0, 0.0)
    assert wind_for_weather("storm")[0] == WIND_BY_WEATHER["storm"]
    assert wind_for_weather("Hurricane")[0] == 15.0
    assert wind_for_weather(None)[0] == WIND_DEFAULT_M_S
    assert wind_for_weather("a word nobody knows")[0] == WIND_DEFAULT_M_S
    block = shader_globals_block("rain")
    assert block.startswith("[shader_globals]\n")
    assert 'lf_wind={"type": "vec3", "value": Vector3(4, 0, 0)}' in block
    assert block.endswith("\n\n")
    assert block.count("\n") == 3                        # one line a global


def test_the_preview_declares_the_calm_the_export_declares():
    from packages.preview.walk_preview import _PROJECT
    assert "[shader_globals]" in _PROJECT
    calm = shader_globals_block("clear").splitlines()[1]
    assert calm.replace("{", "{{").replace("}", "}}") in _PROJECT or calm in _PROJECT
