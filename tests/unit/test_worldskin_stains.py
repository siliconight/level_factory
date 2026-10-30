"""A stain where water runs down a wall, drawn as black at `1 - shade` over it (0.271.0, Zoo >= 1.153.0).

Zoo lays a `stain_streak` 2 mm off a wall in a material named `<skin>_stain`, its darkening in its vertex colour --
1.0 at its foot and both sides. `_stains` draws it black, alpha-blended at `1 - shade`, so the blend leaves the wall
times the shade at whatever light the wall has; black because Compatibility tonemaps each material's output and every
curve takes 0 to 0. Its instance leaves the bake and casts no shadow, or the wall behind would bake into its shadow.
Slice 17b drew it opaque and lit apart from the wall (an outline); slice 17c multiplied a tonemapped white onto it
(near black at evening) -- the factory's `docs/findings/slice_look/`. Read as source, as the other worldskin tests are.
"""
import re
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "assets" / "godot" / "zoo_worldskin.gd"


def _src() -> str:
    return SCRIPT.read_text(encoding="utf-8")


def _func(src: str, name: str) -> str:
    m = re.search(r"^func %s\(.*?(?=^func |^## |\Z)" % re.escape(name), src, re.S | re.M)
    assert m, f"no func {name} in {SCRIPT.name}"
    return m.group(0)


def test_the_stain_pass_runs_for_every_glb_before_the_kit_branch():
    """FAILS ON 0.270.0: no stain pass."""
    post = _func(_src(), "_post_import")
    call = post.find("_stains(scene")
    assert call != -1
    assert call < post.find("is_kit")


def test_a_stain_draws_black_at_one_minus_its_shade_and_nothing_of_its_own():
    """FAILS ON slice 17b's version (opaque, lit apart from the wall) and slice 17c's (a tonemapped white multiplied)."""
    src = _src()
    assert re.search(r'^const STAIN_SUFFIX: String = "_stain"$', src, re.M)
    shader = re.search(r'^const STAIN_SHADER: String = """(.*?)"""$', src, re.S | re.M)
    assert shader, "no STAIN_SHADER"
    code = shader.group(1)
    for token in ("unshaded", "blend_mix", "depth_draw_never", "fog_disabled",
                  "ALBEDO = vec3(0.0);", "ALPHA = 1.0 - pow(clamp(COLOR.r, 0.0, 1.0), 1.0 / 2.2);"):
        assert token in code, token
    assert "blend_mul" not in code
    body = _func(src, "_stains")
    assert "sh.code = STAIN_SHADER" in body and "am.surface_set_material(0, sm)" in body
    assert "ends_with(STAIN_SUFFIX)" in _func(src, "_find_stains")
    # nothing of the earlier versions is left
    for gone in ("uv1_triplanar", "_uv_density", "BLEND_MODE_MUL", "vertex_color_use_as_albedo"):
        assert gone not in body, gone


def test_a_glbs_stains_are_one_mesh_out_of_the_bake_and_casting_no_shadow():
    """FAILS ON slice 17c's version: a stain mesh a side, and slice 17c priced it at draws median +6, largest +50."""
    src = _src()
    body = _func(src, "_stains")
    assert "_find_stains(scene, found)" in body
    assert "st.append_from(mi.mesh, i, xf)" in body and "var xf: Transform3D = _stain_to_root(mi, scene)" in body
    assert "mi.get_parent().remove_child(mi)" in body
    assert "out.gi_mode = GeometryInstance3D.GI_MODE_DISABLED" in body
    assert "out.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF" in body
    # only a mesh that draws nothing but stain is taken
    find = _func(src, "_find_stains")
    assert "all_stain = false" in find and "if all_stain:" in find
    # a post-import scene is in no tree: its transform is walked up to the root, never read as global
    to_root = _func(src, "_stain_to_root")
    assert "xf = p3.transform * xf" in to_root and "global_transform" not in to_root
