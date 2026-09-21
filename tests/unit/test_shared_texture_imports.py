"""The shared textures beside a module's GLB ship with pinned import settings.

Zoo 1.2.0 writes a module's images to `_tex/` beside its GLB rather than
embedding them, because Godot builds a separate GPU texture from every
embedded copy and does not deduplicate. Measured on cold run 9066's package,
Godot 4.7, GL Compatibility, counted by distinct texture RID in the loaded
tree: 1,841 textures and 332,867,236 B of texture memory embedded, against 157
and 47,090,266 B shared.

That only holds if the export pins how those PNGs import. Two of the three
pins exist to keep the pixels exactly as Pixelcoat authored them -- the engine
defaults change them, measured against the embedded mode-3 decode of the same
512x512 source:

    default compress/mode=2 (VRAM)          100.000% of pixels differ
    default process/fix_alpha_border=true     7.755% differ, max delta 255
    both pinned                               0.000% differ, max delta 0

The third, `mipmaps/generate=true`, keeps `zoo_worldskin.gd`'s import-time mip
pass from rebuilding each texture as its own ImageTexture and undoing the
sharing.

Every test here fails on 0.98.0.
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


def _params(text):
    return dict(ln.split("=", 1) for ln in text.splitlines() if "=" in ln
                and not ln.startswith(("path.", "source_file", "dest_files",
                                       "uid", "importer", "type")))


def _tex(tmp_path, body=REAL_SIDECAR):
    d = tmp_path / "art" / "zoo" / export.SHARED_TEX_DIR
    d.mkdir(parents=True)
    (d / "t.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"x" * 64)
    (d / "t.png.import").write_text(body, encoding="utf-8")
    return d


def test_the_three_pins_are_the_measured_ones():
    assert export.SHARED_TEX_PINS == {
        "compress/mode": "0",
        "process/fix_alpha_border": "false",
        "mipmaps/generate": "true",
    }


def test_a_shared_texture_sidecar_is_pinned(tmp_path):
    d = _tex(tmp_path)
    assert export._pin_shared_texture_imports(tmp_path) == 1
    got = _params((d / "t.png.import").read_text(encoding="utf-8"))
    for key, want in export.SHARED_TEX_PINS.items():
        assert got[key] == want, key


def test_nothing_else_in_the_sidecar_moves(tmp_path):
    d = _tex(tmp_path)
    export._pin_shared_texture_imports(tmp_path)
    before = _params(REAL_SIDECAR)
    after = _params((d / "t.png.import").read_text(encoding="utf-8"))
    assert set(before) == set(after)
    moved = {k for k in before if before[k] != after[k]}
    assert moved == {"compress/mode", "process/fix_alpha_border"}, moved


def test_a_png_outside_the_shared_folder_is_left_alone(tmp_path):
    d = tmp_path / "presentation"
    d.mkdir(parents=True)
    (d / "grain.png.import").write_text(REAL_SIDECAR, encoding="utf-8")
    assert export._pin_shared_texture_imports(tmp_path) == 0
    assert (d / "grain.png.import").read_text(encoding="utf-8") == REAL_SIDECAR


def test_running_it_twice_reports_nothing_the_second_time(tmp_path):
    _tex(tmp_path)
    assert export._pin_shared_texture_imports(tmp_path) == 1
    assert export._pin_shared_texture_imports(tmp_path) == 0


def test_a_sidecar_missing_a_key_is_not_given_one(tmp_path):
    """An unrecognised shape is left alone rather than repaired by guess."""
    body = REAL_SIDECAR.replace("process/fix_alpha_border=true\n", "")
    d = _tex(tmp_path, body)
    export._pin_shared_texture_imports(tmp_path)
    text = (d / "t.png.import").read_text(encoding="utf-8")
    assert "process/fix_alpha_border" not in text
    assert "compress/mode=0" in text


def test_the_extract_cleanup_spares_the_shared_textures():
    """The cleanup loop must skip `_tex/` by name, not by luck.

    Those PNGs already survived because their folder holds no `.glb` to match
    the loop's test. A later change that moved the textures next to the GLB,
    or widened the glob, would have deleted a module's textures with no test
    to notice.
    """
    import inspect
    src = inspect.getsource(export._write_import_sidecars)
    cleanup = src.split("Drop what EXTRACT wrote", 1)[1].split("_import_pass")[0]
    assert "SHARED_TEX_DIR" in cleanup


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
