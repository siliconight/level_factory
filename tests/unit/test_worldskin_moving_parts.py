"""Zoo's turning parts turn and its slush churns at import (0.129.0).

The walker, 2026-10-02: "start with the roller grill, and i want some motion
on the slurpee stuff too". Zoo 1.55.0 builds the grill's rollers and dogs as
surfaces of their own, every vertex carrying its axle in its second UV set
and the material named for its axis and rate (`_turn_x36`, `_turn_xn36`),
and paints the slush tile without its bands, each churn facet carrying its
place round the barrel in ITS second UV set. This import gives the first a
vertex stage that turns it and the second a darkening pass that walks the
bands round.

These read the GDScript rather than run it -- the unit suite has no Godot --
so they hold the SHAPE: the contract with Zoo (the name pattern, which UV
set, the sentinel), that a turning surface's material is replaced with the
flat material's own numbers and a churn's is kept with a pass on it, that the
churn only ever darkens, that both phases are per node, that both run for
every GLB before the kit branch, and that neither touches a surface twice.
What the shaders DO is measured in frames; see the 0.129.0 changelog.

Run:  python -m pytest tests/unit/test_worldskin_moving_parts.py
"""
import re
from pathlib import Path

import pytest

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


def _block(src: str, const: str) -> str:
    m = re.search(r'const %s: String = """(.*?)"""' % const, src, re.S)
    assert m, f"no {const} block"
    return m.group(1)


# --- the contract with Zoo ----------------------------------------------------------------


def test_the_turn_name_pattern_reads_axis_sense_and_rate():
    src = _src()
    m = re.search(r'const TURN_PATTERN: String = "(.*?)"', src)
    assert m
    pat = m.group(1).replace("\\\\", "\\")
    for name, want in (("M_Roller_metal_bare_turn_x36", ("x", "", "36")),
                       ("M_Roller_metal_painted_turn_xn36", ("x", "n", "36")),
                       ("M_Fan_blade_turn_y120", ("y", "", "120"))):
        got = re.search(pat, name)
        assert got and got.groups() == want, (name, got and got.groups())
    assert re.search(pat, "M_Roller_metal_bare") is None
    assert re.search(pat, "M_Roller_glass_turn_") is None
    spec = _func(src, "_turn_spec")
    assert '"n"' in spec and "deg = -deg" in spec


def test_the_names_are_zoo_s_when_zoo_is_beside_this_repo():
    zoo = sibling_repo("zoo")
    if zoo is None:
        pytest.skip("zoo is not beside this repo")
    forms = (zoo / "zoo_keeper" / "core" / "roller_grill_forms.py").read_text(encoding="utf-8")
    assert 'name += "_x" + ("n%d" % -r if r < 0 else "%d" % r)' in forms
    assert '"metal_bare_turn"' in forms and '"metal_painted_turn"' in forms
    slush = (zoo / "zoo_keeper" / "recipes" / "slush_machine.py").read_text(encoding="utf-8")
    assert 'bm.loops.layers.uv.new("Churn")' in slush
    assert "loop[uv2].uv = (0.0, -1.0)" in slush          # arrives as v = 2
    assert 'f"M_Slush_{A[\'name\']}_Face"' in slush
    pm = (zoo / "zoo_keeper" / "bpylayer" / "prim_mesh.py").read_text(encoding="utf-8")
    assert 'bm.loops.layers.uv.new(geometry.PIVOT_LAYER)' in pm
    ex = (zoo / "zoo_keeper" / "bpylayer" / "export.py").read_text(encoding="utf-8")
    assert "lambda yz: (yz[1], 1.0 + yz[0])" in ex           # Blender (y, z) -> engine (z, -y), v flipped


# --- the turning surface ------------------------------------------------------------------


def test_the_turn_shader_rotates_vertex_and_normal_about_the_uv2_axle():
    sh = _block(_src(), "TURN_SHADER")
    assert "vec2 pivot = UV2;" in sh
    assert "VERTEX.yz = turn_about(VERTEX.yz, pivot, c, s);" in sh
    assert "NORMAL.yz = turn_about(NORMAL.yz, vec2(0.0), c, s);" in sh
    assert "rate_rad_s * TIME" in sh
    assert "ALBEDO = albedo.rgb * COLOR.rgb;" in sh
    assert "ROUGHNESS = roughness;" in sh and "METALLIC = metallic;" in sh
    assert "unshaded" not in sh                            # it is lit like the flat material it replaces


def test_the_turn_phase_is_per_node_so_two_grills_do_not_turn_in_step():
    sh = _block(_src(), "TURN_SHADER")
    assert "NODE_POSITION_WORLD" in sh
    assert re.search(r"float inst = turn_hash\(dot\(NODE_POSITION_WORLD", sh)
    assert "inst * 6.2831853" in sh


def test_a_turning_surface_is_replaced_once_with_the_flat_material_s_numbers():
    src = _src()
    fn = _func(src, "_turning_parts")
    assert "surface_set_material(i, _turn_material(" in fn
    assert "if bm == null:" in fn and "already the shader" in fn
    assert "contains(TURN_MARK)" in fn
    mat = _func(src, "_turn_material")
    for p in ("albedo", "roughness", "metallic", "rate_rad_s", "axis"):
        assert 'set_shader_parameter("%s"' % p in mat, p
    assert "deg_to_rad(deg_s)" in mat
    assert "_turn_materials[key] = sm" in mat


# --- the churn ----------------------------------------------------------------------------


def test_the_churn_pass_is_a_next_pass_and_the_face_is_kept_for_lux():
    src = _src()
    fn = _func(src, "_churn_passes")
    assert "bm.next_pass = _churn_material(bm)" in fn
    assert "surface_set_material" not in fn
    assert "begins_with(CHURN_PREFIX) and nm.ends_with(CHURN_SUFFIX)" in fn
    assert "if bm.next_pass != null:" in fn
    assert 'const CHURN_PREFIX: String = "M_Slush_"' in src
    assert 'const CHURN_SUFFIX: String = "_Face"' in src


def test_the_churn_only_ever_darkens_and_skips_what_is_not_slush():
    sh = _block(_src(), "CHURN_SHADER")
    assert "ALBEDO = vec3(0.0);" in sh
    assert "blend_mix" in sh and "unshaded" in sh and "depth_draw_never" in sh
    assert "if (UV2.y > 1.5) {" in sh and "discard;" in sh
    assert "fract(3.0 * UV2.x + 1.5 * UV2.y - 3.0 * TIME / period_s + inst)" in sh
    assert "ALPHA = band * band_dark;" in sh
    assert "EMISSION" not in sh
    assert "NODE_POSITION_WORLD" in sh


def test_the_churn_walks_the_painted_diagonal_at_zoo_s_period():
    src = _src()
    assert "const CHURN_PERIOD_S: float = 6.0" in src
    zoo = sibling_repo("zoo")
    if zoo is None:
        pytest.skip("zoo is not beside this repo")
    forms = (zoo / "zoo_keeper" / "core" / "slush_machine_forms.py").read_text(encoding="utf-8")
    assert "CHURN_PERIOD_S = 6.0" in forms
    # the tile no longer paints a band: base and ice only
    churn = re.search(r"^def _churn\(.*?(?=^def |\Z)", forms, re.S | re.M).group(0)
    assert "a[t < 3] = light" not in churn and "= dark" not in churn
    assert "= ice" in churn


# --- both run for every GLB, before the kit branch ----------------------------------------


def test_both_run_for_every_glb_before_the_kit_branch():
    post = _func(_src(), "_post_import")
    i_turn = post.index("_turning_parts(scene)")
    i_churn = post.index("_churn_passes(scene, {})")
    i_kit = post.index("var is_kit: bool = false")
    assert i_turn < i_kit and i_churn < i_kit
    assert post.index("_shutters(scene)") < i_turn
