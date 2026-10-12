"""The editor's import of the lightmap is kept, not done again (0.183.0, factory roadmap 239).

Measured on cold run 9248's export: the light bake's second `--import` imported one file, the
lightmap `bake.exr`, in 49.5 s -- the same bytes the editor that baked them had just imported in
its work copy. The bake now copies the work copy's cache entries for it into the package's cache.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from packages.exporting import light_bake as L  # noqa: E402


def _cache(root, names):
    d = root / ".godot" / "imported"
    d.mkdir(parents=True)
    for n in names:
        (d / n).write_bytes(n.encode())
    return d


def test_the_lightmaps_cache_entries_are_copied_and_nothing_else(tmp_path):
    work, pkg = tmp_path / "work", tmp_path / "pkg"
    _cache(work, ["bake.exr-7a32.bptc.ctexarray", "bake.exr-7a32.md5", "brick.png-11aa.ctex"])
    dst = _cache(pkg, [])
    copied = L._copy_lightmap_import(work, pkg)
    assert copied == ["bake.exr-7a32.bptc.ctexarray", "bake.exr-7a32.md5"], copied
    assert sorted(p.name for p in dst.iterdir()) == copied
    assert (dst / "bake.exr-7a32.md5").read_bytes() == b"bake.exr-7a32.md5"


def test_without_a_cache_on_either_side_it_copies_nothing(tmp_path):
    work, pkg = tmp_path / "work", tmp_path / "pkg"
    _cache(work, ["bake.exr-7a32.md5"])
    pkg.mkdir()
    assert L._copy_lightmap_import(work, pkg) == []
    assert not (pkg / ".godot").exists(), "it does not make a cache the package did not have"


def test_the_bake_keeps_them_before_its_last_import():
    text = (ROOT / "packages" / "exporting" / "light_bake.py").read_text(encoding="utf-8")
    body = text[text.index("def bake("):]
    code = "\n".join(ln.split("#", 1)[0] for ln in body.splitlines())
    copy_back = code.find("shutil.copy(src, export_dir / f)")
    kept = code.find("_copy_lightmap_import(work, export_dir)")
    last_import = code.find("_import(export_dir, godot_executable)", copy_back)
    assert -1 < copy_back < kept < last_import, (copy_back, kept, last_import)
