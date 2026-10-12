"""The shared textures beside a module's GLB ship with pinned import settings.

Zoo 1.2.0 writes a module's images to `_tex/` beside its GLB rather than
embedding them, because Godot builds a separate GPU texture from every
embedded copy and does not deduplicate. Measured on cold run 9066's package,
Godot 4.7, GL Compatibility, counted by distinct texture RID in the loaded
tree: 1,841 textures and 332,867,236 B of texture memory embedded, against 157
and 47,090,266 B shared.

That only holds if the export pins how those PNGs import. Two of the three
pins existed to keep the pixels exactly as Pixelcoat authored them -- the
engine defaults change them, measured against the embedded mode-3 decode of
the same 512x512 source:

    default compress/mode=2 (VRAM)          100.000% of pixels differ
    default process/fix_alpha_border=true     7.755% differ, max delta 255
    both pinned                               0.000% differ, max delta 0

The third, `mipmaps/generate=true`, keeps `zoo_worldskin.gd`'s import-time mip
pass from rebuilding each texture as its own ImageTexture and undoing the
sharing.

COMPRESSED SINCE 0.190.0, the walker's call of 2026-10-12. The lossless pin
held only in a headless import: the pins kept Godot's 3D detection, and every
editor that opened the package re-encoded the textures it saw in use as VRAM
compressed (the factory's docs/findings/grader_speed/editor_texture_probe.py).
Offered lossless everywhere or VRAM everywhere, the walker chose VRAM. The
measurement above is kept as the record of what was traded.

Every test here but those marked otherwise fails on 0.98.0.
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from packages.exporting import export  # noqa: E402
from tests.siblings import env_var, sibling_repo  # noqa: E402

#: What Godot 4.7 wrote for a PNG beside a GLB on a first `--import` pass.
#: Kept verbatim rather than trimmed, so a rewrite is exercised against the
#: real shape and not a convenient one.
REAL_SIDECAR = """[remap]

importer="texture"
type="CompressedTexture2D"
uid="uid://bfq78u53a5okl"
path.s3tc="res://.godot/imported/t.png-6e0ca6f.s3tc.ctex"
metadata={
"imported_formats": ["s3tc_bptc"],
"vram_texture": true
}

[deps]

source_file="res://_tex/t.png"
dest_files=["res://.godot/imported/t.png-6e0ca6f.s3tc.ctex"]

[params]

compress/mode=2
compress/high_quality=false
compress/lossy_quality=0.7
mipmaps/generate=true
mipmaps/limit=-1
roughness/mode=0
process/fix_alpha_border=true
process/premult_alpha=false
process/size_limit=0
detect_3d/compress_to=0
"""

#: Godot 4.7's whole first-pass sidecar for a shared texture (0.190.0), every
#: key it writes, read off cold run 9255's package with the pins taken back to
#: the engine's defaults.
FIRST_PASS = """[remap]

importer="texture"
type="CompressedTexture2D"
uid="uid://bfq78u53a5okl"
path="res://.godot/imported/t.png-6e0ca6f.ctex"

[deps]

source_file="res://_tex/t.png"
dest_files=["res://.godot/imported/t.png-6e0ca6f.ctex"]

[params]

compress/mode=0
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


def _params(text):
    return dict(ln.split("=", 1) for ln in text.splitlines() if "=" in ln
                and not ln.startswith(("path.", "path=", "source_file", "dest_files",
                                       "uid", "importer", "type")))


def _tex(tmp_path, body=REAL_SIDECAR):
    d = tmp_path / "art" / "zoo" / export.SHARED_TEX_DIR
    d.mkdir(parents=True)
    (d / "t.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"x" * 64)
    (d / "t.png.import").write_text(body, encoding="utf-8")
    return d


def test_the_pins_are_what_an_editor_leaves():
    """FAILS ON 0.189.0, which pinned the shared textures lossless and left the detection on."""
    assert export.SHARED_TEX_PINS == {
        "compress/mode": "2",
        "process/fix_alpha_border": "false",
        "mipmaps/generate": "true",
        "detect_3d/compress_to": "0",
    }
    assert export.NORMAL_TEX_PINS == {"compress/normal_map": "1", "roughness/mode": "1"}


def test_a_shared_texture_sidecar_is_pinned(tmp_path):
    d = _tex(tmp_path, FIRST_PASS)
    assert export._pin_shared_texture_imports(tmp_path) == 1
    got = _params((d / "t.png.import").read_text(encoding="utf-8"))
    for key, want in export.SHARED_TEX_PINS.items():
        assert got[key] == want, key


def test_nothing_else_in_the_sidecar_moves(tmp_path):
    d = _tex(tmp_path, FIRST_PASS)
    export._pin_shared_texture_imports(tmp_path)
    before = _params(FIRST_PASS)
    after = _params((d / "t.png.import").read_text(encoding="utf-8"))
    assert set(before) == set(after)
    moved = {k for k in before if before[k] != after[k]}
    assert moved == {"compress/mode", "process/fix_alpha_border", "mipmaps/generate",
                     "detect_3d/compress_to"}, moved


def test_a_png_outside_the_shared_folder_is_left_alone(tmp_path):
    d = tmp_path / "presentation"
    d.mkdir(parents=True)
    (d / "grain.png.import").write_text(FIRST_PASS, encoding="utf-8")
    assert export._pin_shared_texture_imports(tmp_path) == 0
    assert (d / "grain.png.import").read_text(encoding="utf-8") == FIRST_PASS


def test_running_it_twice_reports_nothing_the_second_time(tmp_path):
    _tex(tmp_path, FIRST_PASS)
    assert export._pin_shared_texture_imports(tmp_path) == 1
    assert export._pin_shared_texture_imports(tmp_path) == 0


def test_a_sidecar_missing_a_key_is_not_given_one(tmp_path):
    """An unrecognised shape is left alone rather than repaired by guess."""
    body = FIRST_PASS.replace("process/fix_alpha_border=true\n", "")
    d = _tex(tmp_path, body)
    export._pin_shared_texture_imports(tmp_path)
    text = (d / "t.png.import").read_text(encoding="utf-8")
    assert "process/fix_alpha_border" not in text
    assert "compress/mode=2" in text


def test_the_sidecar_step_deletes_no_texture():
    """No pass extracts, so nothing is cleaned up (0.189.0).

    This held the step's cleanup loop -- what extract wrote beside each GLB,
    deleted before the second pass -- to sparing `_tex/` by name, not by
    luck. Every model now imports with its images embedded from its first
    import, so there is no extract and no loop, and a texture the sidecar
    step deleted would be a texture the package lost.
    """
    import inspect
    src = inspect.getsource(export._write_import_sidecars)
    assert 'rglob("*.png")' not in src and "png.unlink" not in src


def test_the_folder_name_agrees_with_zoo():
    """One contract, two repos. Skips loudly when Zoo is not checked out."""
    marker = "zoo_keeper/core/gltf_textures.py"
    root = sibling_repo("zoo", marker=marker)
    if root is None:
        pytest.skip(
            "zoo carrying %s was not found at or above this file, and "
            "$%s is unset; the folder name agreement between the two "
            "repos is UNCHECKED, not confirmed"
            % (marker, env_var("zoo")))
    zoo = root / marker
    import ast
    tree = ast.parse(zoo.read_text(encoding="utf-8"))
    values = {t.id: n.value.value
              for n in ast.walk(tree) if isinstance(n, ast.Assign)
              and isinstance(n.value, ast.Constant)
              for t in n.targets if isinstance(t, ast.Name)}
    assert values.get("TEX_DIR") == export.SHARED_TEX_DIR


# --- 0.190.0: a normal map is pinned as the editor pins one ---------------------------------
# (0.128.0's section here pinned VRAM compression only on a texture every sampler filtered, the
# rest lossless; every shared texture is compressed since 0.190.0 and no sampler decides.)


def _glb(path, images, textures, materials):
    """A binary glTF holding only the JSON chunk this reads."""
    import json
    import struct
    body = json.dumps({"asset": {"version": "2.0"}, "images": images, "textures": textures,
                       "materials": materials}).encode("utf-8")
    body += b" " * (-len(body) % 4)
    path.write_bytes(b"glTF" + struct.pack("<II", 2, 20 + len(body))
                     + struct.pack("<I", len(body)) + b"JSON" + body)


def _two_textures(tmp_path):
    d = _tex(tmp_path, FIRST_PASS)
    (d / "n.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"y" * 64)
    (d / "n.png.import").write_text(FIRST_PASS, encoding="utf-8")
    return d


def test_a_texture_the_models_name_as_a_normal_map_is_pinned_as_the_editor_pins_one(tmp_path):
    """FAILS ON 0.189.0, which has no `_normal_map_shared_textures`. The keys are the ones the
    bake's editor wrote on all 22 of cold run 9255's normal maps: red-green compression, and the
    roughness limiter pointed at the map itself."""
    d = _two_textures(tmp_path)
    _glb(d.parent / "prop_bench.glb",
         [{"uri": "_tex/t.png"}, {"uri": "_tex/n.png"}],
         [{"source": 0}, {"source": 1}],
         [{"pbrMetallicRoughness": {"baseColorTexture": {"index": 0}},
           "normalTexture": {"index": 1}}])
    assert export._normal_map_shared_textures(tmp_path) == {(d / "n.png").resolve()}
    export._pin_shared_texture_imports(tmp_path)
    n = _params((d / "n.png.import").read_text(encoding="utf-8"))
    assert (n["compress/normal_map"], n["roughness/mode"], n["roughness/src_normal"]) == (
        "1", "1", '"res://art/zoo/_tex/n.png"'), n
    t = _params((d / "t.png.import").read_text(encoding="utf-8"))
    assert (t["compress/normal_map"], t["roughness/mode"], t["roughness/src_normal"]) == (
        "0", "0", '""'), t
    for got in (n, t):
        for key, want in export.SHARED_TEX_PINS.items():
            assert got[key] == want, key
    assert export._pin_shared_texture_imports(tmp_path) == 0
    assert export._shared_texture_pins_missing(tmp_path) == []


def test_a_texture_named_only_as_a_colour_is_not_taken_for_a_normal_map(tmp_path):
    d = _two_textures(tmp_path)
    _glb(d.parent / "a.glb", [{"uri": "_tex/n.png"}], [{"source": 0}],
         [{"pbrMetallicRoughness": {"baseColorTexture": {"index": 0}}}])
    assert export._normal_map_shared_textures(tmp_path) == set()


def test_a_file_that_is_not_a_glb_and_an_image_outside_the_shared_folder_are_ignored(tmp_path):
    d = _two_textures(tmp_path)
    zoo = d.parent
    (zoo / "broken.glb").write_bytes(b"not a gltf at all")
    _glb(zoo / "a.glb", [{"uri": "loose.png"}, {"name": "embedded"}],
         [{"source": 0}, {"source": 1}, {"source": 9}],
         [{"normalTexture": {"index": 0}}, {"normalTexture": {"index": 1}},
          {"normalTexture": {"index": 2}}, {"normalTexture": {"index": 7}}, "not a material"])
    assert export._normal_map_shared_textures(tmp_path) == set()


def test_the_filtered_split_is_gone():
    """0.190.0: every shared texture is compressed, so nothing decides by sampler any more."""
    assert not hasattr(export, "FILTERED_TEX_PINS")
    assert not hasattr(export, "_filtered_shared_textures")
