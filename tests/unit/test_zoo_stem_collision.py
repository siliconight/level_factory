"""Two geometries under one module name block the run (0.139.0).

Zoo exits 2 for a failed module and for a stem collision (Zoo 1.62.0), and
this adapter has always read exit 2 as a usable kit: a failed module falls
back to its base and is a non-blocking `ZOO_PARTIAL_BUILD`. A collision has
no fallback. Whichever module built last stands in every slot of both --
cold run 9148's Empties stood 2.8 m walls in 3.1 m slots, and the warning
sat in six kit logs. So it is read off the index and BLOCKS.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from adapters.zoo import ZooAdapter  # noqa: E402


def _index(tmp_path, **fields) -> Path:
    p = tmp_path / "gs_empty_rowhome_f_kit.built.json"
    p.write_text(json.dumps(dict({"building_id": "gs_empty_rowhome_f",
                                  "modules": [{"status": "pass"}], "n_fail": 0}, **fields)),
                 encoding="utf-8")
    return p


def _coll(issues):
    return [i for i in issues if i["code"] == "ZOO_STEM_COLLISION"]


def test_a_stem_collision_blocks_and_names_the_module(tmp_path):
    """FAILS ON 0.138.1: nothing read the field."""
    idx = _index(tmp_path, stem_collisions=[
        {"stem": "wall_delco_1997_01_w200_mbrick_idrywall", "count": 2},
        {"stem": "window_delco_1997_01_w95_mbrick_o173e47", "count": 2}])
    found = _coll(ZooAdapter().normalize_validation([idx]))
    assert len(found) == 1 and found[0]["blocking"] is True
    assert "wall_delco_1997_01_w200_mbrick_idrywall" in found[0]["message"]
    assert found[0]["message"].startswith("2 module name(s)")


def test_a_clean_index_and_an_old_one_say_nothing(tmp_path):
    """The controls: an empty list, and an index from before Zoo 1.62.0 that
    has no such key, are both silent -- absence is not a collision."""
    assert _coll(ZooAdapter().normalize_validation([_index(tmp_path, stem_collisions=[])])) == []
    assert _coll(ZooAdapter().normalize_validation([_index(tmp_path)])) == []
