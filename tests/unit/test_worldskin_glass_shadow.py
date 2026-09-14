"""Blended glass casts no shadow: the import script moves it out of the pass.

Godot 4.7 imports glTF alphaMode BLEND as TRANSPARENCY_ALPHA_DEPTH_PRE_PASS,
and a depth-prepass material is drawn into the shadow map as solid. Measured
in GL Compatibility on a delco_1997 window module under a shadowed sun: ground
under the pane at 0.463 of open ground whether the pane was opaque or blended,
1.000 with it hidden, with cast_shadow off, or at TRANSPARENCY_ALPHA. On a
scratch copy of walk 9050 the switch is what let a sunlit patch onto the bank's
carpet under its south window. See the 0.84.0 changelog entry.

These read the GDScript rather than run it -- the unit suite has no Godot --
so they hold the SHAPE the measurement depends on: the pass exists, it runs for
every GLB (props carry glass too, and the kit/non-kit branch returns early for
them), it changes exactly the importer's BLEND spelling to ALPHA, and it is
installed where the presentation fingerprint will see it change.

Run:  python -m pytest tests/unit/test_worldskin_glass_shadow.py
"""
import re
from pathlib import Path

from adapters.presentation import _INSTALLED_ASSETS, _installed_asset_paths

SCRIPT = (Path(__file__).resolve().parents[2]
          / "assets" / "godot" / "zoo_worldskin.gd")


def _func(src: str, name: str) -> str:
    m = re.search(r"^func %s\(.*?(?=^func |\Z)" % re.escape(name), src,
                  re.S | re.M)
    assert m, f"no func {name} in {SCRIPT.name}"
    return m.group(0)


def test_the_pass_exists_and_changes_only_the_blend_spelling():
    body = _func(SCRIPT.read_text(encoding="utf-8"), "_glass_casts_no_shadow")
    assert "bm.transparency == BaseMaterial3D.TRANSPARENCY_ALPHA_DEPTH_PRE_PASS" in body
    assert "bm.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA" in body
    # nothing else about the material moves
    assert len(re.findall(r"\bbm\.\w+\s*=[^=]", body)) == 1
    # recursion over the whole imported scene
    assert "_glass_casts_no_shadow(c, seen)" in body


def test_the_pass_runs_for_every_glb_before_the_kit_branch():
    post = _func(SCRIPT.read_text(encoding="utf-8"), "_post_import")
    call = post.find("_glass_casts_no_shadow(scene")
    first_return = post.find("return scene")
    kit_test = post.find("is_kit")
    assert call != -1, "the glass pass is not called from _post_import"
    assert call < kit_test < first_return, (
        "the glass pass must run before the kit/non-kit branch, which returns "
        "early for props -- the teller line, bus shelter and car carry glass")


def test_the_script_is_a_fingerprinted_installed_asset():
    assert SCRIPT.name in _INSTALLED_ASSETS
    assert SCRIPT.resolve() in [p.resolve() for p in _installed_asset_paths()]
