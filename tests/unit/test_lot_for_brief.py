"""One rule for the lot: `lot_for_brief` reads library, count and archetype
off the brief, and the compose spec's `_lot_for_compose` goes through it.
Cold run 9008 (2026-09-12) fired the planner's guard because only one of
three call sites was anchored.

Run:  python -m pytest tests/unit/test_lot_for_brief.py
"""
from types import SimpleNamespace

from packages.pipeline import building_library as bl


LIB = ["bank_branch_a01", "bank_branch_a02", "bank_tower_a01", "bank_job",
       "credit_union_a01", "deli_a01", "pawn_shop_a01", "arena_a03",
       "clinic_a01", "landmark_hall_a01", "gas_station_a01", "marina_a02",
       "strip_club_a02"]


def _lib(tmp_path):
    for aid in LIB:
        for suf in bl.REQUIRED:
            (tmp_path / (aid + suf)).write_text("{}")
    return str(tmp_path)


def test_lot_for_brief_anchors_on_the_brief_archetype(tmp_path):
    model = SimpleNamespace(lot_library=_lib(tmp_path), building_count=3,
                            archetype="urban_bank")
    for cid in ("bank_block_001.candidate.seed_9008",
                "bank_block_001.candidate.seed_9109",
                "bank_block_001.candidate.seed_9210"):
        lot, _inc = bl.lot_for_brief(model, cid)
        assert lot[0]["family"] in ("bank_branch", "bank_tower", "bank_job"), (cid, lot)
        assert len(lot) == 3


def test_the_three_callers_are_one_draw(tmp_path):
    """planner, compose spec, site spec: same brief, same candidate, same lot."""
    model = SimpleNamespace(lot_library=_lib(tmp_path), building_count=3,
                            archetype="urban_bank")
    cid = "bank_block_001.candidate.seed_9008"
    via_brief, _ = bl.lot_for_brief(model, cid)
    complete, _i, _n = bl.index(model.lot_library)
    seed = int(cid.rsplit("_", 1)[-1])
    via_site = bl.pick_lot(complete, seed, 3, anchor=model.archetype)
    assert [e["id"] for e in via_brief] == [e["id"] for e in via_site]


def test_compose_spec_uses_the_one_rule(tmp_path):
    """The compose spec draws THEMED, so its library must be shells the kit
    fills and the nav bake crosses -- `test_fanout._library` builds those."""
    import sys
    sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))
    from test_fanout import _library
    from apps.cli.commands import _lot_for_compose
    root = _library(tmp_path / "lib", ids=("bank_branch_a02", "bank_job",
                                          "pharmacy_a02", "depot_a01",
                                          "rail_station_a02", "cr_deli"))
    model = SimpleNamespace(lot_library=str(root), building_count=3,
                            archetype="urban_bank")
    lot = _lot_for_compose(model, "bank_block_001.candidate.seed_9008")
    assert lot and lot[0]["family"] in ("bank_branch", "bank_job"), lot
    assert len({e["family"] for e in lot}) == 3


def test_a_brief_without_a_library_is_the_single_shell(tmp_path):
    model = SimpleNamespace(lot_library="", building_count=3, archetype="urban_bank")
    assert bl.lot_for_brief(model, "m.candidate.seed_1") == ([], [])
