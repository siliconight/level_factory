"""A lit CRT face gets a motion pass at import, and nothing else does (0.89.0).

Zoo 0.90.0 lights the club's bracket TVs with a painted ballgame, and a still
picture reads as a photograph of a television. The import pass hangs a small
shader off the screen material's `next_pass`: a sync bar drifting up the face,
a brightness flicker and a per-picture-pixel shimmer, all of them DARKENING
only, so the face is multiplied by (1 - ALPHA).

WHAT THE SHAPE IS PROTECTING, because every clause here was bought by a
measurement that came out the wrong way first:

* THE SCREEN MATERIAL STAYS A BaseMaterial3D. Lux's power cut walks the scene
  casting each material to BaseMaterial3D and zeroing `emission_energy_multi-
  plier`. Measured against the walk copy's own vendored binder over three
  materials all named to the lit-face contract, `bind` collected 2 of 3 and the
  one it silently dropped was a ShaderMaterial. Replacing the screen material
  would have left the club's TVs lit through a power cut with nothing saying
  so. Re-measured on the five materials the importer really produces: all five
  bind, and `set_fixtures_powered(false)` takes the 2 m screen region from
  90.92 to 34.25 codes with emission 1.5 -> 0.0 on every one.

* THE OVERLAY DARKENS AND NEVER ADDS. That is what makes the power cut safe
  without the shader knowing about it -- a face Lux has taken to black stays
  black when it is multiplied down. An additive pass would glow on a dead set.

* IT IS LIFTED ALONG THE SURFACE NORMAL. A next_pass rasterises the same
  triangles at the same depth the base pass wrote, and in GL Compatibility the
  depth test throws it away: `unshaded`, `blend_mix` and `depth_draw_never` all
  measured as NOT DRAWN. `depth_test_disabled` drew -- and drew through the
  set's own cabinet from behind, which on a level this size means rolling bands
  on walls with no TV behind them. The normal offset draws from the front
  (99.15 -> 1.49) and stays occluded from behind (39.55 -> 39.53).

* THE PHASE COMES FROM NODE_POSITION_WORLD, not from a per-material seed. Two
  of the five materials are worn by two sets each, and a seed on the material
  would roll both together. Measured in one frame with both of a shared-material
  pair in it, the bar sat at v=0.381 on one and v=0.714 on the other.

These read the GDScript rather than run it -- the unit suite has no Godot -- so
they hold the SHAPE those measurements depend on. See the 0.89.0 changelog.

Run:  python -m pytest tests/unit/test_worldskin_crt_motion.py
"""
import re
from pathlib import Path

from adapters.presentation import _INSTALLED_ASSETS, _installed_asset_paths

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
    m = re.search(r'const MOTION_SHADER: String = """(.*?)"""', src, re.S)
    assert m, "no MOTION_SHADER block"
    return m.group(1)


def test_the_pass_runs_for_every_glb_before_the_kit_branch():
    post = _func(_src(), "_post_import")
    call = post.find("_crt_motion(scene")
    assert call != -1, "the CRT pass is not called from _post_import"
    assert call < post.find("is_kit") < post.find("return scene"), (
        "the CRT pass must run before the kit/non-kit branch. A lit CRT arrives "
        "in a PROP glb, and that branch returns early for props")


def test_only_a_lit_crt_face_is_touched():
    body = _func(_src(), "_is_crt_face")
    # all three, because no one of them is the contract on its own: the vending
    # machine's lit panel also ends `_Face`, and Zoo's dark stand-set glass also
    # carries CRT
    assert "CRT_FACE_PREFIX" in body and "begins_with" in body
    assert "CRT_FACE_SUFFIX" in body and "ends_with" in body
    assert "CRT_FACE_MARK" in body and "contains" in body
    src = _src()
    assert 'CRT_FACE_PREFIX: String = "M_"' in src
    assert 'CRT_FACE_SUFFIX: String = "_Face"' in src
    assert 'CRT_FACE_MARK: String = "CRT_Screen"' in src
    # and the pass itself asks that question before doing anything
    crt = _func(src, "_crt_motion")
    assert "if not _is_crt_face(" in crt


def test_the_pass_only_sets_next_pass_and_keeps_emission_and_texture():
    crt = _func(_src(), "_crt_motion")
    # exactly one assignment to the screen's own material, and it is next_pass
    assigns = re.findall(r"\bbm\.(\w+)\s*=[^=]", crt)
    assert assigns == ["next_pass"], assigns
    # nothing in the CRT path touches what the picture is or how bright it is
    for forbidden in ("emission", "albedo_color", "albedo_texture",
                      "transparency", "surface_set_material"):
        assert forbidden not in crt, forbidden


def test_it_is_idempotent_on_reimport():
    crt = _func(_src(), "_crt_motion")
    assert "if bm.next_pass != null:" in crt and "continue" in crt


def test_the_overlay_darkens_and_never_adds():
    sh = _shader(_src())
    assert "blend_mix" in sh, (
        "the overlay must blend, not add: an additive pass glows on a set Lux "
        "has cut the power to")
    for mode in ("blend_add", "blend_sub", "blend_mul"):
        assert mode not in sh, mode
    assert re.search(r"ALBEDO\s*=\s*vec3\(0\.0\)", sh), (
        "ALBEDO must be black so the face is multiplied by (1 - ALPHA)")


def test_the_overlay_is_lifted_along_the_normal_and_keeps_its_depth_test():
    sh = _shader(_src())
    assert "void vertex()" in sh, (
        "without a vertex offset the pass draws at the picture's own depth and "
        "GL Compatibility's depth test discards it entirely")
    assert re.search(r"VERTEX\s*\+=\s*NORMAL\s*\*\s*proud_m", sh), (
        "the offset is along the surface NORMAL -- in vertex() VERTEX is in "
        "MODEL space, so biasing .z drew the pass from behind the set and not "
        "from in front of it")
    assert "depth_test_disabled" not in sh, (
        "a pass with no depth test draws through the cabinet and through walls")
    assert "depth_draw_never" in sh, "the overlay must not write depth"
    assert "SCREEN_PROUD_M: float = 0.002" in _src()


def test_the_roll_is_time_based_and_offset_per_instance():
    sh = _shader(_src())
    assert "TIME" in sh, "the roll must be driven by TIME, not baked"
    assert "NODE_POSITION_WORLD" in sh, (
        "the phase must come from a PER-INSTANCE built-in: two of the club's "
        "five screen materials are worn by two sets each, and a per-material "
        "seed would roll both together")
    # the phase actually reaches the bar and the flicker, rather than being
    # computed and dropped
    assert re.search(r"phase\s*=\s*hash11\(dot\(NODE_POSITION_WORLD", sh)
    assert re.search(r"bar\s*=\s*fract\(TIME\s*/\s*roll_period_s.*phase\)", sh)
    assert "+ ph" in sh, "the flicker must carry the per-instance phase too"


def test_every_knob_is_a_named_constant_pushed_into_the_material():
    src = _src()
    # the sync bar is NTSC's vertical blanking, derived rather than chosen
    assert "ROLL_BAND_FRAC: float = 21.0 / 262.5" in src
    assert "VHOLD_ERROR_HZ: float = 0.2" in src
    assert "ROLL_PERIOD_S: float = 1.0 / VHOLD_ERROR_HZ" in src
    # the roll runs UP the face, which measured as the negative sign
    assert "ROLL_UP: float = -1.0" in src
    mat = _func(src, "_motion_material")
    for uniform, const in [
            ("roll_period_s", "ROLL_PERIOD_S"),
            ("roll_band_frac", "ROLL_BAND_FRAC"),
            ("roll_depth", "ROLL_DEPTH"),
            ("roll_dir", "ROLL_UP"),
            ("flicker_depth", "FLICKER_DEPTH"),
            ("flicker_hz_a", "FLICKER_HZ_A"),
            ("flicker_hz_b", "FLICKER_HZ_B"),
            ("noise_depth", "NOISE_DEPTH"),
            ("noise_hz", "NOISE_HZ"),
            ("proud_m", "SCREEN_PROUD_M")]:
        assert f'set_shader_parameter("{uniform}", {const})' in mat, uniform
    # every uniform the shader declares is one the material sets: an unset
    # uniform is silently zero, and a zeroed depth or period is a pass that
    # does nothing while looking installed
    declared = set(re.findall(r"^uniform\s+\w+\s+(\w+);", _shader(src), re.M))
    passed = set(re.findall(r'set_shader_parameter\("(\w+)"', mat))
    assert declared == passed, (declared ^ passed)


def test_the_snow_grain_is_read_off_the_picture_not_assumed():
    mat = _func(_src(), "_motion_material")
    assert "bm.albedo_texture.get_width()" in mat
    assert "bm.albedo_texture.get_height()" in mat
    assert "PICTURE_PX_FALLBACK" in mat, (
        "a face with no texture still needs a grain at picture scale")


#: The passes allowed to REPLACE a surface's material outright, smallest set
#: that is true. `_assign_slabs` joined `_assign_stairs` for roadmap 168: the
#: greybox slab's cut edge lines every ladder shaft and stairwell, theming
#: never reached it, and the walker found it on a ladder. Both replace rather
#: than decorate for the same reason -- a greybox box carries no UVs, so the
#: material has to be swapped for a world-triplanar one.
#:
#: THE POINT OF THIS LIST IS THAT IT IS SHORT. Adding a name here is a
#: decision; arriving at this test by accident means a pass started replacing
#: materials without anyone choosing that, which is how a level quietly stops
#: looking like the packs it was dressed from.
MATERIAL_REPLACERS = {"_assign_stairs", "_assign_slabs"}


def test_nothing_elses_material_class_changes():
    src = _src()
    # the CRT pass hangs a second pass off the material that is already there
    # rather than replacing it, and must stay out of this set.
    owners = [n for n in re.findall(r"^func (\w+)\(", src, re.M)
              if "surface_set_material" in _func(src, n)]
    assert set(owners) == MATERIAL_REPLACERS, owners
    # and no pass turns anything into a ShaderMaterial in place
    assert "surface_set_material(i, sm" not in src
    assert re.search(r"ShaderMaterial", _func(src, "_crt_motion")) is None


def test_the_script_is_a_fingerprinted_installed_asset():
    assert SCRIPT.name in _INSTALLED_ASSETS
    assert SCRIPT.resolve() in [p.resolve() for p in _installed_asset_paths()]
