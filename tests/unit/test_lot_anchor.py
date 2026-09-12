"""A brief's lot contains the brief's archetype (building_library.anchor_families,
pick_lot(anchor=)). Cold run 9007, 2026-09-12: `urban_bank`, three buildings,
and a lot of arena, clinic and landmark hall -- every stage green, no bank.

Run:  python -m pytest tests/unit/test_lot_anchor.py
"""
from packages.pipeline import building_library as bl


def _lib(tmp_path, ids):
    for aid in ids:
        for suf in bl.REQUIRED:
            (tmp_path / (aid + suf)).write_text("{}")
    return tmp_path


LIB = ["bank_branch_a01", "bank_branch_a02", "bank_tower_a01", "bank_job",
       "credit_union_a01", "deli_a01", "pawn_shop_a01", "arena_a03",
       "clinic_a01", "landmark_hall_a01", "gas_station_a01"]


def test_anchor_families_read_the_archetype_by_its_parts(tmp_path):
    complete, _i, _n = bl.index(_lib(tmp_path, LIB))
    assert bl.anchor_families(complete, "bank") == ["bank_branch", "bank_job", "bank_tower"]
    assert bl.anchor_families(complete, "urban_bank") == ["bank_branch", "bank_job", "bank_tower"]
    assert bl.anchor_families(complete, "pawn_shop") == ["pawn_shop"]
    assert bl.anchor_families(complete, "county_hospital") == []
    assert bl.anchor_families(complete, "") == []


def test_a_bank_brief_gets_a_bank_first(tmp_path):
    complete, _i, _n = bl.index(_lib(tmp_path, LIB))
    for seed in (9007, 9108, 9209, 5421):
        lot = bl.pick_lot(complete, seed, 3, anchor="urban_bank")
        assert lot[0]["family"] in ("bank_branch", "bank_tower", "bank_job"), (seed, lot)
        fams = [e["family"] for e in lot]
        assert len(set(fams)) == 3, fams


def test_the_anchor_keeps_candidates_distinct_and_seeds_stable(tmp_path):
    complete, _i, _n = bl.index(_lib(tmp_path, LIB))
    lots = {tuple(e["id"] for e in bl.pick_lot(complete, s, 3, anchor="bank"))
            for s in (9007, 9108, 9209, 5017, 5118)}
    assert len(lots) > 1
    assert bl.pick_lot(complete, 9007, 3, anchor="bank") == \
        bl.pick_lot(complete, 9007, 3, anchor="bank")


def test_no_anchor_is_the_draw_that_always_was(tmp_path):
    complete, _i, _n = bl.index(_lib(tmp_path, LIB))
    assert bl.pick_lot(complete, 9007, 3) == bl.pick_lot(complete, 9007, 3, anchor=None)
    # an archetype the library has no family for changes nothing either
    assert bl.pick_lot(complete, 9007, 3, anchor="county_hospital") == \
        bl.pick_lot(complete, 9007, 3)


def test_lot_for_threads_the_anchor(tmp_path):
    lib = _lib(tmp_path, LIB)
    lot, _inc = bl.lot_for(str(lib), 3, "bank_block_001.candidate.seed_9007",
                           anchor="urban_bank")
    assert lot[0]["family"].startswith("bank")
