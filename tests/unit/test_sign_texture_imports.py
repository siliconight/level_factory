"""A dealt business's sign maps import as their pack asks (0.166.0, roadmap 223).

Pixelcoat 0.62.0 letters a business's sign smooth, in Blue Highway, and its pack asks for `linear`
sampling and a mip chain; a pixel pack asks for `nearest` and neither. Lot copies the maps to
`signs/` beside its scene and, since Lot 0.105.0, the pack's manifest with them. Before this, the
export left every sign map at Godot's first-pass defaults -- measured on `LF_gas_block_001`'s
package: `compress/mode=0`, `mipmaps/generate=false` -- so a smooth sign would ship uncompressed,
6.3 MB of maps where 1.6 MB would do, and shimmer across a street for want of its mips.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from packages.exporting import export  # noqa: E402

#: What Godot 4.7 wrote for a sign map on a first `--import` pass, read off `LF_gas_block_001`'s
#: package (`signs/sign_delco_storage_albedo.png.import`), its paths shortened.
SIGN_SIDECAR = """[remap]

importer="texture"
type="CompressedTexture2D"
uid="uid://cstpgp2xodb0m"
path="res://.godot/imported/sign_flappahs_albedo.png-3b37154f.ctex"
metadata={
"vram_texture": false
}

[deps]

source_file="res://signs/sign_flappahs_albedo.png"
dest_files=["res://.godot/imported/sign_flappahs_albedo.png-3b37154f.ctex"]

[params]

compress/mode=0
compress/high_quality=false
compress/lossy_quality=0.7
mipmaps/generate=false
mipmaps/limit=-1
process/fix_alpha_border=true
process/size_limit=0
detect_3d/compress_to=1
"""


def _params(text):
    return dict(ln.split("=", 1) for ln in text.splitlines() if "=" in ln
                and not ln.startswith(("path", "source_file", "dest_files", "uid", "importer",
                                       "type")))


def _signs(tmp_path, hints, body=SIGN_SIDECAR, folder="signs"):
    d = tmp_path / folder
    d.mkdir(parents=True)
    maps = {"albedo": "sign_flappahs_albedo.png", "emissive": "sign_flappahs_emissive.png",
            "roughness": "sign_flappahs_roughness.png"}
    (d / "sign_flappahs.pack.json").write_text(json.dumps(
        {"schema": "pixelcoat-pack/2", "maps": maps, "import_hints": hints}), encoding="utf-8")
    for m in ("albedo", "emissive"):                  # Lot copies these two, not the roughness
        (d / maps[m]).write_bytes(b"PNG")
        (d / (maps[m] + ".import")).write_text(body, encoding="utf-8")
    return d


SMOOTH = {"interpolation": "linear", "generate_mipmaps": True, "extension": "extend"}
PIXEL = {"interpolation": "nearest", "extension": "extend"}


def test_a_smooth_sign_is_compressed_and_mipped(tmp_path):
    """FAILS on 0.165.0: there is no `_pin_sign_texture_imports`."""
    d = _signs(tmp_path, SMOOTH)
    assert export._pin_sign_texture_imports(tmp_path) == 2
    for m in ("albedo", "emissive"):
        got = _params((d / f"sign_flappahs_{m}.png.import").read_text(encoding="utf-8"))
        assert got["compress/mode"] == "2" and got["mipmaps/generate"] == "true", (m, got)


def test_nothing_else_in_the_sidecar_moves(tmp_path):
    d = _signs(tmp_path, SMOOTH)
    export._pin_sign_texture_imports(tmp_path)
    before = _params(SIGN_SIDECAR)
    after = _params((d / "sign_flappahs_albedo.png.import").read_text(encoding="utf-8"))
    assert set(before) == set(after)
    assert {k for k in before if before[k] != after[k]} == {"compress/mode", "mipmaps/generate"}


def test_a_pixel_sign_is_left_as_it_was(tmp_path):
    d = _signs(tmp_path, PIXEL)
    assert export._pin_sign_texture_imports(tmp_path) == 0
    assert (d / "sign_flappahs_albedo.png.import").read_text(encoding="utf-8") == SIGN_SIDECAR


def test_running_it_twice_reports_nothing_the_second_time(tmp_path):
    _signs(tmp_path, SMOOTH)
    assert export._pin_sign_texture_imports(tmp_path) == 2
    assert export._pin_sign_texture_imports(tmp_path) == 0


def test_a_sidecar_missing_a_key_is_not_given_one(tmp_path):
    body = SIGN_SIDECAR.replace("mipmaps/generate=false\n", "")
    d = _signs(tmp_path, SMOOTH, body)
    export._pin_sign_texture_imports(tmp_path)
    text = (d / "sign_flappahs_albedo.png.import").read_text(encoding="utf-8")
    assert "mipmaps/generate" not in text and "compress/mode=2" in text


def test_a_manifest_outside_signs_is_not_read(tmp_path):
    d = _signs(tmp_path, SMOOTH, folder="skins")
    assert export._pin_sign_texture_imports(tmp_path) == 0
    assert (d / "sign_flappahs_albedo.png.import").read_text(encoding="utf-8") == SIGN_SIDECAR


def test_a_manifest_that_cannot_be_read_pins_nothing(tmp_path):
    d = _signs(tmp_path, SMOOTH)
    (d / "sign_flappahs.pack.json").write_text("{ not json", encoding="utf-8")
    assert export._pin_sign_texture_imports(tmp_path) == 0


def test_the_export_pins_signs_where_it_pins_the_shared_textures():
    src = (ROOT / "packages" / "exporting" / "export.py").read_text(encoding="utf-8")
    shared = src.index("    rewrote += _pin_shared_texture_imports(export_dir)\n")
    signs = src.index("    rewrote += _pin_sign_texture_imports(export_dir)\n")
    assert 0 < signs - shared < 80
