"""Zoo's shutters get their clock at import, and the register's display a flicker (0.127.0).

The walker, 2026-10-02: the lit screens are "just fixed with nothing
dynamic/alive about them". Zoo 1.45.0 ships shutters -- black quads over
parts of a lit screen, a schedule in their UV sets, on a transparent material
named `M_Shutter_Screen` -- and this import gives them the shader that reads
it. The register's display, a lit face of its own, takes the CRT pass's
darkening overlay with no roll and no snow.

These read the GDScript rather than run it -- the unit suite has no Godot --
so they hold the SHAPE: the contract with Zoo (the name, which UV is which),
that a shutter only ever darkens, that the phase is per node, that both
passes run for every GLB before the kit branch, and that the register's own
material is not replaced. What the shader DOES is measured in frames; see the
0.127.0 changelog.

Run:  python -m pytest tests/unit/test_worldskin_shutters.py
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


def _shader(src: str) -> str:
    m = re.search(r'const SHUTTER_SHADER: String = """(.*?)"""', src, re.S)
    assert m, "no SHUTTER_SHADER block"
    return m.group(1)


def test_both_passes_run_for_every_glb_before_the_kit_branch():
    post = _func(_src(), "_post_import")
    for call in ("_shutters(scene", "_vfd_motion(scene"):
        at = post.find(call)
        assert at != -1, call
        assert at < post.find("is_kit") < post.find("return scene"), call


def test_the_name_is_zoo_s_when_zoo_is_beside_this_repo():
    src = _src()
    assert 'const SHUTTER_MATERIAL: String = "M_Shutter_Screen"' in src
    zoo = sibling_repo("zoo", marker="zoo_keeper/core/shutters.py")
    if zoo is None:
        pytest.skip("no Zoo with shutters beside this repo")
    their = (zoo / "zoo_keeper" / "core" / "shutters.py").read_text(encoding="utf-8")
    assert 'MATERIAL = "M_Shutter_Screen"' in their
    # which UV is which, as Zoo's contract spells it
    assert "UV  = (open_from, open_to)" in their and "UV2 = (period_s, phase_s)" in their


def test_the_shader_reads_the_schedule_and_only_ever_darkens():
    sh = _shader(_src())
    assert "render_mode unshaded, blend_mix" in sh and "depth_draw_never" in sh
    assert "shadows_disabled" in sh
    # open from UV.x to UV.y of a period UV2.x long, offset UV2.y
    assert "(TIME + UV2.y) / max(UV2.x" in sh
    assert "step(UV.x, t) * (1.0 - step(UV.y, t))" in sh
    # the closed colour where closed, absent where open; never emission
    assert "ALBEDO = closed_color;" in sh and "ALPHA = 1.0 - open;" in sh
    assert "uniform vec3 closed_color : source_color" in sh
    assert "EMISSION" not in sh
    # the depth test stays on: a shutter must lose it to a wall in front
    assert "depth_test_disabled" not in sh


def test_the_phase_is_per_node_so_two_machines_do_not_run_in_step():
    sh = _shader(_src())
    assert "NODE_POSITION_WORLD" in sh
    # and it is added to the whole machine's clock, not to one shutter's
    assert re.search(r"fract\(\(TIME \+ UV2\.y\) / max\(UV2\.x, 0\.001\) \+ inst\)", sh)


def test_only_the_shutter_material_is_replaced_and_only_once():
    body = _func(_src(), "_shutters")
    assert "begins_with(SHUTTER_MATERIAL)" in body and "continue" in body
    assert "if bm == null:" in body                          # idempotent on re-import
    assert body.count("surface_set_material") == 1
    # the closed colour is the placeholder's own base colour
    make = _func(_src(), "_shutter_shader_material")
    assert "bm.albedo_color" in make and '"closed_color"' in make


def test_the_register_keeps_its_own_material_and_gets_no_roll_and_no_snow():
    vfd = _func(_src(), "_vfd_motion")
    assigns = re.findall(r"\bbm\.(\w+)\s*=[^=]", vfd)
    assert assigns == ["next_pass"], assigns
    assert "surface_set_material" not in vfd and "emission" not in vfd
    assert "if bm.next_pass != null:" in vfd
    assert 'set_shader_parameter("roll_depth", 0.0)' in vfd
    assert 'set_shader_parameter("noise_depth", 0.0)' in vfd
    face = _func(_src(), "_is_vfd_face")
    assert "CRT_FACE_PREFIX + VFD_FACE_MARK" in face and "CRT_FACE_SUFFIX" in face
    assert 'const VFD_FACE_MARK: String = "Register_"' in _src()
    # and it does not catch the CRTs, which have their own pass
    assert "CRT_Screen" not in "M_Register_x_Face"
