"""The drip that ships must be the drip that was priced.

+1.85 ms at the worst of six stations (LF 0.116.0) is a measurement of one
shader text attached to one set of 19 wall families. Either of those drifting
makes the number a statement about something that no longer exists -- and the
last unmeasured drip figure in this repo had to be withdrawn, so a quiet drift
here is expensive.

Each test below fails if the arrangement that keeps them identical comes apart:
one shader file with two readers, and one family list with two readers.
"""
from __future__ import annotations

import re
from pathlib import Path

_LF = Path(__file__).resolve().parents[1]
_SHADER = _LF / "assets" / "godot" / "rain_drip.gdshader"
_NODE = _LF / "assets" / "godot" / "rain_drip.gd"
_PROBE = _LF / "tools" / "wet_ab.gd"


def _families(text: str, block: str) -> list[str]:
    """The quoted strings in the first `[...]` literal after `block`."""
    i = text.index(block)
    lit = text[i:].split("[", 1)[1].split("]", 1)[0]
    return re.findall(r'"([^"]+)"', lit)


def test_shader_is_a_real_shader_with_the_measured_offset() -> None:
    src = _SHADER.read_text(encoding="utf-8")
    assert src.startswith("shader_type spatial;")
    # The 2 mm offset is why the pass draws at all on GL Compatibility. Without
    # it the depth test rejects the second rasterisation of the same triangles
    # and every figure measured through it is a figure for nothing drawn.
    assert "PROUD_M = 0.002" in src
    assert "VERTEX += NORMAL * PROUD_M" in src
    # the per-drop clock, which is the whole reason this cannot be a baked map
    assert "fract(drop.b - TIME * drip_speed)" in src
    # no screen read: that is Reference B and it is unpriced on this renderer
    assert "hint_screen_texture" not in src
    assert "hint_depth_texture" not in src


def test_nothing_carries_a_second_copy_of_the_shader() -> None:
    """One text, two readers. A second copy is a copy to drift from.

    Keyed on the DROP CLOCK rather than on `shader_type`, because `wet_ab.gd`
    legitimately carries a second, different shader: the wet pass it also
    prices. Naming the drip's own line is the difference between "this file has
    a shader in it" and "this file has THE drip in it".
    """
    CLOCK = "fract(drop.b - TIME * drip_speed)"
    assert CLOCK in _SHADER.read_text(encoding="utf-8")
    for p in (_NODE, _PROBE):
        src = p.read_text(encoding="utf-8")
        assert CLOCK not in src, (
            "%s embeds its own copy of the drip fragment; the one in "
            "rain_drip.gdshader is the text that was measured" % p.name)
        assert "rain_drip.gdshader" in src, (
            "%s does not name the shader file, so it is reading a drip from "
            "somewhere else" % p.name)


def test_the_shipped_family_set_is_the_set_that_was_priced() -> None:
    """`rain_drip.gd` and the probe's narrow arm must name the same families.

    The probe measured 19 materials matching `_is_wall_few`. If the runtime
    node's list grows past it, the level costs more than the recorded figure
    and nothing says so.
    """
    shipped = _families(_NODE.read_text(encoding="utf-8"),
                        "const WALL_FAMILIES")
    priced = _families(_PROBE.read_text(encoding="utf-8"),
                       "func _is_wall_few")
    assert shipped, "no WALL_FAMILIES literal found in rain_drip.gd"
    assert shipped == priced, (
        "rain_drip.gd attaches to %s but +1.85 ms was measured on %s. "
        "Re-measure with `wet_ab_run.py --arms dry drip_few` before widening "
        "the set." % (shipped, priced))


def test_stager_writes_the_shader_the_atlas_and_the_node(tmp_path) -> None:
    import sys
    sys.path.insert(0, str(_LF / "tools"))
    import drip_assets

    assert drip_assets.stage(tmp_path, node=True) == [
        "rain_drip.gdshader", "drop_atlas.png", "rain_drip.gd"]
    # the atlas is generated, so the only thing worth asserting about it is
    # that it exists and carries four channels -- the drip reads all four.
    from PIL import Image
    with Image.open(tmp_path / "drop_atlas.png") as im:
        assert im.mode == "RGBA"
        assert im.size == (drip_assets.ATLAS_PX, drip_assets.ATLAS_PX)
    assert (tmp_path / "rain_drip.gdshader").read_bytes() == _SHADER.read_bytes()
