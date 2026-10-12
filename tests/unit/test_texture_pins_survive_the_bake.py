"""The shared textures' import pins survive the export's imports (0.182.0).

Measured in the factory (`docs/findings/texture_pins/`): the light bake's first `--import` turned
62 to 86 of 415 pinned sidecars under `_tex/` back into Godot's defaults, which ones varying from
run to run, and cold run 9248 shipped 65 of them so. The export now applies the pins again after
its last import and refuses a package whose shared sidecars still do not carry them.
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from packages.exporting import export as E  # noqa: E402

#: A sidecar as Godot 4.7 writes it fresh: the engine's defaults, the keys the pins name among them.
FRESH = """[remap]

importer="texture"
type="CompressedTexture2D"
uid="uid://b0000000000000"

[params]

compress/mode=0
compress/high_quality=false
mipmaps/generate=false
mipmaps/limit=-1
process/fix_alpha_border=true
process/premult_alpha=false
detect_3d/compress_to=1
"""


def _package(tmp_path, names, text=FRESH):
    tex = tmp_path / "lot" / "deli_a01" / "art" / "zoo" / E.SHARED_TEX_DIR
    tex.mkdir(parents=True)
    for n in names:
        (tex / n).write_bytes(b"")
        (tex / (n + ".import")).write_text(text, encoding="utf-8")
    return tex


def _values(sidecar):
    return dict(ln.partition("=")[::2] for ln in sidecar.read_text(encoding="utf-8").splitlines() if "=" in ln)


def test_a_sidecar_the_import_reset_is_pinned_again(tmp_path):
    tex = _package(tmp_path, ["a.png", "b.png"])
    E._pin_shared_texture_imports(tmp_path)          # as the sidecar step leaves them
    (tex / "b.png.import").write_text(FRESH, encoding="utf-8")   # as the bake's import leaves one
    report = E._repin_after_imports(tmp_path)
    assert report["shared_repinned"] == 1 and report["shared_sidecars"] == 2, report
    for n in ("a.png", "b.png"):
        v = _values(tex / (n + ".import"))
        for key, want in E.SHARED_TEX_PINS.items():
            assert v[key] == want, (n, key, v[key])
    assert E._shared_texture_pins_missing(tmp_path) == []


def test_a_sidecar_without_a_pinned_key_refuses_the_package(tmp_path):
    """A key the sidecar does not carry is not one the pins write, so it cannot ship on the
    engine's default unseen: the read-back names it."""
    _package(tmp_path, ["c.png"], text=FRESH.replace("mipmaps/generate=false\n", ""))
    with pytest.raises(E.ExportImportError) as exc:
        E._repin_after_imports(tmp_path)
    assert "c.png.import" in str(exc.value) and "mipmaps/generate" in str(exc.value)


def test_the_cache_is_not_the_package(tmp_path):
    _package(tmp_path, ["d.png"])
    E._pin_shared_texture_imports(tmp_path)
    cached = tmp_path / ".godot" / "imported" / E.SHARED_TEX_DIR
    cached.mkdir(parents=True)
    (cached / "e.png.import").write_text(FRESH, encoding="utf-8")
    assert E._shared_texture_pins_missing(tmp_path) == []


def test_the_export_reads_them_back_after_its_last_import():
    text = (ROOT / "packages" / "exporting" / "export.py").read_text(encoding="utf-8")
    body = text[text.index("def export_mission("):]
    body = body[:body.find("\ndef ", 1)]
    code = "\n".join(ln.split("#", 1)[0] for ln in body.splitlines())
    repin = code.find("_repin_after_imports(export_dir)")
    assert repin != -1, "the export does not read the pins back"
    for earlier in ("_bake_lights(", "greybox_skin.measure(", "if drop_cache(export_dir):"):
        assert -1 < code.find(earlier) < repin, earlier
    assert repin < code.find("_closure_verdict(export_dir)")
