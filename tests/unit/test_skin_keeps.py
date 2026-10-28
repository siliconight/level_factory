"""A merged building keeps the modules its runtime skin reads (0.264.0).

`drop_merged_modules` removed every kit module no file named, and a merged building names none, so the stair pass in
`zoo_worldskin.gd` found no `floor_` module and every stair shipped in Deli Counter's fallback yellow (the walker: "the
stairs are only yellow as the default if they haven't been given a texture/skin"). FAILS ON 0.263.0.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from packages.exporting import merge_empties as M  # noqa: E402


def _package(tmp_path, names):
    art = tmp_path / "lot" / "b0" / "art" / "zoo"
    art.mkdir(parents=True)
    for n in names:
        (art / n).write_bytes(b"glb")
    (tmp_path / "lot" / "b0" / "site.tscn").write_text("[gd_scene]\n", encoding="utf-8")
    return {"scenes": [{"scene": "res://lot/b0/site.tscn", "merged": 4, "error": None}]}


def test_the_first_module_of_each_family_the_skin_reads_is_kept(tmp_path):
    names = ["floor_delco_1997_07_w200.glb", "floor_delco_1997_01_w200.glb", "roof_delco_1997_01_w200.glb",
             "wall_delco_1997_02_w200_mdrywall.glb", "wall_delco_1997_01_w200.glb", "prop_desk_delco_01.glb",
             "doorway_delco_1997_01_w100.glb", "window_delco_1997_01_w120.glb"]
    out = M.drop_merged_modules(tmp_path, _package(tmp_path, names))
    left = sorted(p.name for p in (tmp_path / "lot" / "b0" / "art" / "zoo").glob("*.glb"))
    assert left == ["floor_delco_1997_01_w200.glb", "prop_desk_delco_01.glb", "roof_delco_1997_01_w200.glb",
                    "wall_delco_1997_01_w200.glb", "wall_delco_1997_02_w200_mdrywall.glb"], left
    assert len(out["dropped"]) == 3                       # the second floor, the doorway, the window


def test_the_rows_are_the_skins_own_families():
    """`SKIN_READS` says what `zoo_worldskin.gd` asks `_family_material` for; a row the skin reads and this keeps
    nothing for is the yellow stair again."""
    src = (ROOT / "assets" / "godot" / "zoo_worldskin.gd").read_text(encoding="utf-8")
    for prefix in ("floor_", "roof_", "wall_", "prop_"):
        assert '"%s"' % prefix in src, prefix
    assert {p for p, _s in M.SKIN_READS} == {"floor_", "roof_", "wall_", "prop_"}
