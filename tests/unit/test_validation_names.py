"""Two rules that asked for a name the files do not carry (0.260.0, the factory's roadmap 297).

1. `building_library.source_exclusion` read a shell's validation manifest as `<id>.validation.json`, but Deli Counter
   writes it under the spec's `level` (`<id>.gameplay.json`'s `level`): three library shells' stems are not their
   level's name, so a facade or demo flag in theirs was never read. `validation_manifest` falls back to the level's.
2. The export added `"validation"` to `_copy_tree`'s `skip`, which matches FILE names, so it could never leave the
   handoff's `validation/` directory out and `ExportProfile.include_validation` had no effect. `base_skips` makes it a
   directory rule.

FAILS ON 0.259.0: `validation_manifest` and `base_skips` do not exist, and a facade flag under the level's name is not
read.

Run:  python -m pytest tests/unit/test_validation_names.py -q
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from packages.exporting import export as E  # noqa: E402
from packages.pipeline import building_library as BL  # noqa: E402


def _build(tmp_path, stem, level, manifest):
    (tmp_path / (stem + ".gameplay.json")).write_text(json.dumps({"level": level}), encoding="utf-8")
    (tmp_path / (level + ".validation.json")).write_text(json.dumps(manifest), encoding="utf-8")
    return tmp_path


def test_a_shell_whose_stem_is_not_its_level_is_judged_by_its_levels_manifest(tmp_path):
    b = _build(tmp_path, "street_wall_schemafixed", "street_wall", {"facade": True})
    assert BL.validation_manifest(b, "street_wall_schemafixed") == {"facade": True}
    assert "facade=true" in BL.source_exclusion(b, "street_wall_schemafixed")


def test_its_own_manifest_wins_and_absence_still_fails_open(tmp_path):
    b = _build(tmp_path, "shop_b", "shop", {"demo": True})
    (tmp_path / "shop_b.validation.json").write_text(json.dumps({}), encoding="utf-8")
    assert BL.validation_manifest(b, "shop_b") == {}
    assert BL.source_exclusion(b, "shop_b") == ""
    assert BL.validation_manifest(tmp_path, "nothing_here") is None
    assert BL.source_exclusion(tmp_path, "nothing_here") == ""


def test_the_validation_rule_is_a_directory_rule(tmp_path):
    on = E.ExportProfile()
    assert on.include_validation is True
    names, dirs = E.base_skips(on)
    assert "validation" not in names and "validation" not in dirs
    off = E.ExportProfile(include_validation=False)
    names, dirs = E.base_skips(off)
    assert dirs == {"validation"} and "validation" not in names
    src, dst = tmp_path / "src", tmp_path / "dst"
    (src / "validation" / "overlays").mkdir(parents=True)
    (src / "validation" / "report.json").write_text("{}", encoding="utf-8")
    (src / "validation" / "overlays" / "a.png").write_bytes(b"x")
    (src / "mission.tscn").write_text("", encoding="utf-8")
    E._copy_tree(src, dst, skip=names, skip_dirs=dirs)
    assert (dst / "mission.tscn").exists() and not (dst / "validation").exists()
