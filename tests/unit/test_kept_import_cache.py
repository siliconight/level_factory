"""The export keeps its import cache beside the package, for the walk copy (0.188.0).

The cold drive's walk copy imported the package from scratch -- 91 s of cold run 9252's 615 s
drive -- a minute after the export had imported the same files and deleted the cache. Kept
beside the package (`<package>.import_cache`), never in it, a walk copy started from it took
9.6 s against 85.6 and 86.2 s from scratch, every model it imports loading the same (the
factory's docs/findings/grader_speed/walk_cache_probe.py).
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from packages.exporting import occluders  # noqa: E402

EXPORT = ROOT / "packages" / "exporting" / "export.py"


def _package(tmp_path):
    pkg = tmp_path / "LF_x.portable-godot"
    (pkg / ".godot" / "imported").mkdir(parents=True)
    (pkg / ".godot" / "imported" / "wall.glb-1.scn").write_bytes(b"scn")
    (pkg / "mission.tscn").write_text("[gd_scene]\n", encoding="utf-8")
    return pkg


def test_the_cache_goes_beside_the_package_and_the_package_ships_without_it(tmp_path):
    pkg = _package(tmp_path)
    kept = occluders.keep_cache(pkg)
    assert kept == tmp_path / "LF_x.portable-godot.import_cache"
    assert not (pkg / ".godot").exists(), "the package ships cache-free, as before"
    assert (kept / "imported" / "wall.glb-1.scn").read_bytes() == b"scn"
    assert (pkg / "mission.tscn").exists()


def test_no_cache_keeps_nothing(tmp_path):
    pkg = tmp_path / "LF_x.portable-godot"
    pkg.mkdir()
    assert occluders.keep_cache(pkg) is None
    assert not occluders.kept_cache_dir(pkg).exists()


def test_a_kept_cache_is_replaced_never_merged(tmp_path):
    pkg = _package(tmp_path)
    old = occluders.kept_cache_dir(pkg)
    (old / "imported").mkdir(parents=True)
    (old / "imported" / "stale.scn").write_bytes(b"old")
    occluders.keep_cache(pkg)
    assert not (old / "imported" / "stale.scn").exists()
    assert (old / "imported" / "wall.glb-1.scn").exists()


def _export_mission_code():
    text = EXPORT.read_text(encoding="utf-8")
    start = text.index("def export_mission(")
    end = text.find("\ndef ", start + 1)
    body = text[start:end if end != -1 else len(text)]
    return "".join(line.split("#", 1)[0] + "\n" for line in body.splitlines())


def test_an_export_removes_the_last_packages_kept_cache_before_it_builds():
    """A kept cache describes the package it came from. An export that stopped before keeping
    its own would otherwise leave the last one's beside a different package for a walk copy."""
    code = _export_mission_code()
    gone = code.index("shutil.rmtree(kept_cache_dir(export_dir)")
    assert gone < code.index("export_dir.mkdir(parents=True, exist_ok=True)")


def test_the_cache_is_kept_where_it_was_dropped():
    """After the census, before the pins are read back and the verdict walks the tree."""
    code = _export_mission_code()
    census = code.index("greybox_skin.measure(")
    keep = code.index("kept = keep_cache(export_dir)")
    pins = code.index("_repin_after_imports(export_dir)")
    verdict = code.index("_closure_verdict(export_dir)")
    assert census < keep < pins < verdict
    assert "if drop_cache(export_dir):" not in code
