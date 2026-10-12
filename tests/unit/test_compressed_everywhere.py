"""Compressed everywhere: a package's textures import as an editor leaves them (0.190.0).

The walker's call of 2026-10-12. The export pinned its shared textures lossless and left Godot's
3D detection on, and pinned no skin and only some signs, so every editor that opened the package
-- the light bake's, the walk copy opened to be walked, a recipient's -- re-encoded each texture it
saw in use: 426 sidecars on cold run 9255's package (the factory's
docs/findings/grader_speed/editor_texture_probe.py). A headless import and an editor disagreed
about every one. Offered lossless everywhere or VRAM everywhere, the walker chose VRAM.

Each test here pins Godot's first-pass sidecar the way the export does and compares the result,
key by key, with what the bake's editor wrote for the same kind of texture in that probe: a shared
albedo, a normal map, a site skin, a sign. All four fail on 0.189.0.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from packages.exporting import export  # noqa: E402

#: Godot 4.7's first-pass `[params]` for a PNG, every key, the engine's defaults (cold run 9255).
FIRST_PASS = """compress/mode=0
compress/high_quality=false
compress/lossy_quality=0.7
compress/uastc_level=0
compress/rdo_quality_loss=0.0
compress/hdr_compression=1
compress/normal_map=0
compress/channel_pack=0
mipmaps/generate=false
mipmaps/limit=-1
roughness/mode=0
roughness/src_normal=""
process/channel_remap/red=0
process/channel_remap/green=1
process/channel_remap/blue=2
process/channel_remap/alpha=3
process/fix_alpha_border=true
process/premult_alpha=false
process/normal_map_invert_y=false
process/hdr_as_srgb=false
process/hdr_clamp_exposure=false
process/size_limit=0
detect_3d/compress_to=1
"""

#: What the bake's editor wrote, read off its work copy of cold run 9255's package, verbatim.
EDITOR = {
    "albedo": """compress/mode=2
compress/high_quality=false
compress/lossy_quality=0.7
compress/uastc_level=0
compress/rdo_quality_loss=0.0
compress/hdr_compression=1
compress/normal_map=0
compress/channel_pack=0
mipmaps/generate=true
mipmaps/limit=-1
roughness/mode=0
roughness/src_normal=""
process/channel_remap/red=0
process/channel_remap/green=1
process/channel_remap/blue=2
process/channel_remap/alpha=3
process/fix_alpha_border=false
process/premult_alpha=false
process/normal_map_invert_y=false
process/hdr_as_srgb=false
process/hdr_clamp_exposure=false
process/size_limit=0
detect_3d/compress_to=0
""",
    "normal": """compress/mode=2
compress/high_quality=false
compress/lossy_quality=0.7
compress/uastc_level=0
compress/rdo_quality_loss=0.0
compress/hdr_compression=1
compress/normal_map=1
compress/channel_pack=0
mipmaps/generate=true
mipmaps/limit=-1
roughness/mode=1
roughness/src_normal="res://cover/_tex/metal_rusted_street_normal_1f5687b5.png"
process/channel_remap/red=0
process/channel_remap/green=1
process/channel_remap/blue=2
process/channel_remap/alpha=3
process/fix_alpha_border=false
process/premult_alpha=false
process/normal_map_invert_y=false
process/hdr_as_srgb=false
process/hdr_clamp_exposure=false
process/size_limit=0
detect_3d/compress_to=0
""",
    "skin": """compress/mode=2
compress/high_quality=false
compress/lossy_quality=0.7
compress/uastc_level=0
compress/rdo_quality_loss=0.0
compress/hdr_compression=1
compress/normal_map=0
compress/channel_pack=0
mipmaps/generate=true
mipmaps/limit=-1
roughness/mode=0
roughness/src_normal=""
process/channel_remap/red=0
process/channel_remap/green=1
process/channel_remap/blue=2
process/channel_remap/alpha=3
process/fix_alpha_border=true
process/premult_alpha=false
process/normal_map_invert_y=false
process/hdr_as_srgb=false
process/hdr_clamp_exposure=false
process/size_limit=0
detect_3d/compress_to=0
""",
    "sign": """compress/mode=2
compress/high_quality=false
compress/lossy_quality=0.7
compress/uastc_level=0
compress/rdo_quality_loss=0.0
compress/hdr_compression=1
compress/normal_map=0
compress/channel_pack=0
mipmaps/generate=true
mipmaps/limit=-1
roughness/mode=0
roughness/src_normal=""
process/channel_remap/red=0
process/channel_remap/green=1
process/channel_remap/blue=2
process/channel_remap/alpha=3
process/fix_alpha_border=true
process/premult_alpha=false
process/normal_map_invert_y=false
process/hdr_as_srgb=false
process/hdr_clamp_exposure=false
process/size_limit=0
detect_3d/compress_to=0
""",
}


def _sidecar(params):
    return ('[remap]\n\nimporter="texture"\ntype="CompressedTexture2D"\n\n[params]\n\n' + params)


def _params(path):
    text = path.read_text(encoding="utf-8")
    return text[text.index("[params]") + len("[params]"):].strip().splitlines()


def _png(folder, name):
    folder.mkdir(parents=True, exist_ok=True)
    (folder / name).write_bytes(b"\x89PNG\r\n\x1a\n")
    (folder / (name + ".import")).write_text(_sidecar(FIRST_PASS), encoding="utf-8")
    return folder / (name + ".import")


def _glb_naming_a_normal_map(path, uri):
    import struct
    body = json.dumps({"asset": {"version": "2.0"}, "images": [{"uri": uri}],
                       "textures": [{"source": 0}],
                       "materials": [{"normalTexture": {"index": 0}}]}).encode("utf-8")
    body += b" " * (-len(body) % 4)
    path.write_bytes(b"glTF" + struct.pack("<II", 2, 20 + len(body))
                     + struct.pack("<I", len(body)) + b"JSON" + body)


def test_a_shared_albedo_is_pinned_as_the_editor_leaves_it(tmp_path):
    side = _png(tmp_path / "cover" / export.SHARED_TEX_DIR, "canvas_neutral_albedo_2f7f6a2f.png")
    export._pin_shared_texture_imports(tmp_path)
    assert _params(side) == EDITOR["albedo"].strip().splitlines()


def test_a_normal_map_is_pinned_as_the_editor_leaves_it(tmp_path):
    side = _png(tmp_path / "cover" / export.SHARED_TEX_DIR, "metal_rusted_street_normal_1f5687b5.png")
    _glb_naming_a_normal_map(tmp_path / "cover" / "prop_bench.glb",
                             "_tex/metal_rusted_street_normal_1f5687b5.png")
    export._pin_shared_texture_imports(tmp_path)
    assert _params(side) == EDITOR["normal"].strip().splitlines()


def test_a_skin_is_pinned_as_the_editor_leaves_it(tmp_path):
    side = _png(tmp_path / "skins", "asphalt_delco_albedo.png")
    assert export._pin_skin_texture_imports(tmp_path) == 1
    assert _params(side) == EDITOR["skin"].strip().splitlines()
    assert export._pin_skin_texture_imports(tmp_path) == 0


def test_a_sign_is_pinned_as_the_editor_leaves_it_whatever_its_pack_asks(tmp_path):
    """A pixel pack -- `nearest`, no mips -- was left as it was (0.166.0); an editor compressed and
    mipped it anyway."""
    d = tmp_path / "signs"
    side = _png(d, "sign_scrapple_sons_deli_albedo.png")
    (d / "sign_scrapple_sons_deli.pack.json").write_text(json.dumps(
        {"maps": {"albedo": "sign_scrapple_sons_deli_albedo.png"},
         "import_hints": {"interpolation": "nearest", "extension": "extend"}}), encoding="utf-8")
    assert export._pin_sign_texture_imports(tmp_path) == 1
    assert _params(side) == EDITOR["sign"].strip().splitlines()


def test_a_png_outside_the_skins_is_not_taken_for_one(tmp_path):
    side = _png(tmp_path / "runtime" / "lux", "grain_balanced.png")
    assert export._pin_skin_texture_imports(tmp_path) == 0
    assert _params(side) == FIRST_PASS.strip().splitlines()


def test_the_export_pins_the_skins_where_it_pins_the_signs():
    """In the sidecar step, between its first and second passes, and in the read-back after the
    last import."""
    src = (ROOT / "packages" / "exporting" / "export.py").read_text(encoding="utf-8")
    step = src.index("        _pin_sign_texture_imports(export_dir)\n        _pin_skin_texture_imports(export_dir)\n")
    assert step > 0
    back = src[src.index("def _repin_after_imports("):]
    back = back[:back.index("\ndef ", 1)]
    assert "_pin_skin_texture_imports(export_dir)" in back
