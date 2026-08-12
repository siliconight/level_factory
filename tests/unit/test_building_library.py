"""Selecting a lot from the library — roadmap 41, steps 2-3.

Item 37's cheap fix is a selection problem: Deli Counter already ships 41
archetypes and the site spec asks for one thing N times. These pin the two ways
that selection can quietly fail to be a fix — shipping an archetype whose
manifest is missing, and picking three authorings of the same building and
calling it variety.
"""

import pytest

from packages.pipeline import building_library as bl


def _lib(tmp_path, ids, incomplete=()):
    for aid in ids:
        for suf in bl.REQUIRED:
            (tmp_path / (aid + suf)).write_text("{}")
    for aid, missing in incomplete:
        for suf in bl.REQUIRED:
            if suf not in missing:
                (tmp_path / (aid + suf)).write_text("{}")
    return tmp_path


FULL = ["deli_a01", "deli_a02", "deli_a03", "pawn_shop_a01", "pawn_shop_a02",
        "gas_station_a01", "stadium_a01", "train_yard_a01", "museum_a01"]


# --------------------------------------------------------------------------- #
# The index
# --------------------------------------------------------------------------- #

def test_a_glb_without_its_slots_manifest_is_not_offered(tmp_path):
    """It cannot be themed. It must drop out at SELECTION, not three stages
    later at compose, where the failure names the wrong thing."""
    _lib(tmp_path, ["deli_a01"], incomplete=[("orphan_a01", (".slots.json",))])
    complete, incomplete, _non_source = bl.index(tmp_path)
    assert [e["id"] for e in complete] == ["deli_a01"]
    assert incomplete == [{"id": "orphan_a01", "missing": [".slots.json"]}]


def test_what_is_missing_is_reported_not_swallowed(tmp_path):
    """A silently shorter library is how a lot stops being varied without
    anyone noticing it stopped."""
    _lib(tmp_path, [], incomplete=[("a_a01", (".gameplay.json", ".slots.json"))])
    _complete, incomplete, _non_source = bl.index(tmp_path)
    assert set(incomplete[0]["missing"]) == {".gameplay.json", ".slots.json"}


def test_the_index_is_sorted(tmp_path):
    """Directory order is not a contract. If it leaked into selection, the
    same seed would pick different buildings on a different filesystem."""
    _lib(tmp_path, ["zebra_a01", "alpha_a01", "middle_a01"])
    complete, _i, _n = bl.index(tmp_path)
    assert [e["id"] for e in complete] == ["alpha_a01", "middle_a01", "zebra_a01"]


def test_a_missing_directory_is_empty_not_an_error(tmp_path):
    assert bl.index(tmp_path / "nope") == ([], [], [])


def test_family_strips_the_authoring_index():
    assert bl.family("deli_a01") == "deli"
    assert bl.family("parking_garage_a02") == "parking_garage"
    # hand-authored specs carry no index and are their own family
    assert bl.family("cr_deli") == "cr_deli"
    assert bl.family("fuel_stop_heist") == "fuel_stop_heist"


# --------------------------------------------------------------------------- #
# The pick
# --------------------------------------------------------------------------- #

def test_no_two_buildings_come_from_one_family(tmp_path):
    """THE POINT. deli_a01 + deli_a02 + deli_a03 is item 37 wearing a hat."""
    complete, _i, _n = bl.index(_lib(tmp_path, FULL))
    lot = bl.pick_lot(complete, seed=5421, count=5)
    fams = [e["family"] for e in lot]
    assert len(set(fams)) == len(fams), fams


def test_different_candidates_get_different_lots(tmp_path):
    """Keyed on the CANDIDATE seed, the one that already diverges placement.
    A lot that ignored it would reintroduce the defect `cmd_run`'s diversity
    check exists for, one level down."""
    complete, _i, _n = bl.index(_lib(tmp_path, FULL))
    lots = {tuple(e["id"] for e in bl.pick_lot(complete, s, 4))
            for s in (5017, 5118, 5219, 5320, 5421)}
    assert len(lots) > 1


def test_the_same_seed_picks_the_same_lot(tmp_path):
    complete, _i, _n = bl.index(_lib(tmp_path, FULL))
    assert bl.pick_lot(complete, 5421, 4) == bl.pick_lot(complete, 5421, 4)


def test_a_library_smaller_than_the_lot_degrades_visibly(tmp_path):
    """Two delis beats one deli and a hole -- but the caller must be able to
    see it happened, by comparing families to count."""
    complete, _i, _n = bl.index(_lib(tmp_path, ["deli_a01", "deli_a02"]))
    lot = bl.pick_lot(complete, 5421, 4)
    assert len(lot) == 4
    assert len({e["family"] for e in lot}) == 1      # visible degradation


def test_an_empty_library_picks_nothing_rather_than_guessing(tmp_path):
    assert bl.pick_lot([], 5421, 4) == []
    complete, _i, _n = bl.index(_lib(tmp_path, FULL))
    assert bl.pick_lot(complete, 5421, 0) == []


def test_every_pick_is_a_complete_archetype(tmp_path):
    complete, _i, _n = bl.index(_lib(tmp_path, FULL))
    for e in bl.pick_lot(complete, 5421, 5):
        assert e["glb"].endswith(".glb")
        assert e["gameplay"].endswith(".gameplay.json")
        assert e["slots"].endswith(".slots.json")


def test_footprints_ride_the_pick_in_order(tmp_path):
    """`site_variation.row_offsets` reads them positionally, so a reordering
    here would space the row for the wrong buildings."""
    complete, _i, _n = bl.index(_lib(tmp_path, FULL))
    lot = bl.pick_lot(complete, 5421, 3)
    seen = []

    def measure(glb):
        seen.append(glb)
        return (10.0, 10.0)

    fps = bl.footprints_for(lot, measure)
    assert seen == [e["glb"] for e in lot]
    assert len(fps) == len(lot)


def test_an_unmeasurable_shell_yields_none(tmp_path):
    """`shell_footprint` returns None for a GLB it cannot read, and
    `row_offsets` already treats None as DEFAULT_FOOTPRINT. One bad archetype
    must not take the site down."""
    complete, _i, _n = bl.index(_lib(tmp_path, FULL))
    lot = bl.pick_lot(complete, 5421, 2)
    assert bl.footprints_for(lot, lambda _g: None) == [None, None]


def test_the_lot_uses_the_same_stream_as_the_placement():
    """Two RNGs would make two modules disagree about what seed 5421 means,
    and the cache fingerprint depends on re-deriving what the builder did."""
    from packages.pipeline import site_variation as sv
    assert bl.stream is sv.stream
