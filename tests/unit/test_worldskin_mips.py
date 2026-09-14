"""Every imported texture gets a mip chain (0.85.0).

The export embeds kit textures uncompressed, which keeps no mipmaps: 138 of
138 metal-skin surfaces on cold run 9051's walk copy read back with none, and
a far corrugated wall beat against the pixel grid into moire arcs. An A/B on
two copies of that walk copy, differing only in this pass, took the wall's
high-frequency energy from 22.32 to 12.58 with the arcs gone. See the 0.85.0
changelog entry.

These read the GDScript rather than run it -- the unit suite has no Godot --
so they hold the shape the measurement depends on.

Run:  python -m pytest tests/unit/test_worldskin_mips.py
"""
import re
from pathlib import Path

SCRIPT = (Path(__file__).resolve().parents[2]
          / "assets" / "godot" / "zoo_worldskin.gd")


def _func(src, name):
    m = re.search(r"^func %s\(.*?(?=^func |\Z)" % re.escape(name), src,
                  re.S | re.M)
    assert m, f"no func {name}"
    return m.group(0)


def test_the_pass_runs_for_every_glb_before_the_kit_branch():
    post = _func(SCRIPT.read_text(encoding="utf-8"), "_post_import")
    call = post.find("_mip_chains(scene")
    assert call != -1
    assert call < post.find("is_kit") < post.find("return scene")


def test_it_covers_albedo_normal_and_roughness_and_renormalises_normals():
    body = _func(SCRIPT.read_text(encoding="utf-8"), "_mip_chains")
    for slot in ("albedo_texture", "normal_texture", "roughness_texture"):
        assert f"bm.{slot} = " in body, slot
    assert "_with_mips(bm.normal_texture, true)" in body
    assert "_with_mips(bm.albedo_texture, false)" in body


def test_it_only_adds_mips_and_keeps_the_filter():
    body = _func(SCRIPT.read_text(encoding="utf-8"), "_with_mips")
    assert "img.has_mipmaps()" in body and "generate_mipmaps(" in body
    src = SCRIPT.read_text(encoding="utf-8")
    assert "texture_filter" not in _func(src, "_mip_chains")
