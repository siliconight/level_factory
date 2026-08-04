"""A row of DIFFERENT buildings — roadmap 41, step 1.

Every sizing function in `site_variation` took ONE footprint, on the stated
assumption that "every candidate instances the same Deli Counter shell, so one
measurement covers the row." That assumption IS roadmap item 37: a site is one
building N times, so the spacing only ever had to be right for one size.

Deli Counter ships 41 archetypes. A deli beside a stadium breaks it — and it
breaks LOUDLY, because `_write_site_spec` runs `uncovered` + `overlapping` on
every write and raises. These tests are the geometry that makes a mixed row
placeable rather than merely refused.

No pipeline run, no Godot, no workspace: this is the whole risk of the feature,
isolated.
"""

import pytest

from packages.pipeline import site_variation as sv

DELI = (22.0, 18.0)
STADIUM = (96.0, 74.0)
GAS = (30.0, 24.0)
MIXED = [DELI, STADIUM, GAS, DELI]


def _spec(placed, footprints):
    span_x, span_y = sv.ground_size(len(footprints), footprints=footprints)
    return {"ground": {"size_x": span_x, "size_y": span_y},
            "buildings": [{"id": f"b{i}", **p}
                          for i, p in enumerate(placed["buildings"])]}


# --------------------------------------------------------------------------- #
# The compatibility that matters
# --------------------------------------------------------------------------- #

def test_a_row_of_equal_shells_is_unchanged():
    """Every existing caller passes one footprint and must keep its layout.
    A fix that quietly re-places today's sites is a different level wearing
    the same evaluation."""
    same = [(44.0, 32.0)] * 4
    spacing = sv.row_spacing(same[0])
    uniform = sv.site_placements(5421, 4, spacing=spacing)
    mixed = sv.site_placements(5421, 4, spacing=spacing, footprints=same)
    assert [b["at"][0] for b in uniform["buildings"]] == \
           [b["at"][0] for b in mixed["buildings"]]


def test_the_old_signatures_still_answer():
    assert sv.row_spacing((44.0, 32.0)) > 0
    assert sv.ground_size(4, spacing=64, footprint=(44.0, 32.0))[0] > 0
    assert sv.overlapping({"buildings": []}) == []
    assert sv.row_offsets([]) == []
    assert sv.row_offsets(None) == []


# --------------------------------------------------------------------------- #
# The mixed row
# --------------------------------------------------------------------------- #

def test_no_two_buildings_stand_in_each_other():
    """The check `_write_site_spec` already runs before it writes. With one
    shared reach it was answering a question about a building nobody built."""
    placed = sv.site_placements(5421, len(MIXED), footprints=MIXED)
    assert sv.overlapping(_spec(placed, MIXED), footprints=MIXED) == []


def test_the_plate_carries_the_row_it_placed():
    placed = sv.site_placements(5421, len(MIXED), footprints=MIXED)
    assert sv.uncovered(_spec(placed, MIXED), footprints=MIXED) == []


def test_every_seed_places_a_legal_row():
    """The nudge and stagger tables let a candidate close the gap by 12 m.
    One seed passing proves nothing about the other four a mission builds."""
    for seed in (5017, 5118, 5219, 5320, 5421):
        placed = sv.site_placements(seed, len(MIXED), footprints=MIXED)
        spec = _spec(placed, MIXED)
        assert sv.overlapping(spec, footprints=MIXED) == [], seed
        assert sv.uncovered(spec, footprints=MIXED) == [], seed


def test_the_gap_is_sized_by_the_pair_that_shares_it():
    """A deli next to a stadium needs the stadium's clearance; two delis do
    not. One spacing for the row would either strand the delis in empty street
    or put the stadium through its neighbour."""
    offs = sv.row_offsets([DELI, DELI, STADIUM])
    small_gap = offs[1] - offs[0]
    big_gap = offs[2] - offs[1]
    assert big_gap > small_gap


def test_a_small_building_is_not_given_a_stadium_of_street():
    """The cheap alternative -- space the whole row for the largest shell --
    would be correct and look absurd. Two delis stand a deli's distance
    apart even when a stadium is on the row."""
    with_stadium = sv.row_offsets([DELI, DELI, STADIUM])
    alone = sv.row_offsets([DELI, DELI])
    assert (with_stadium[1] - with_stadium[0]) == (alone[1] - alone[0])


def test_the_row_stays_centred_on_the_origin():
    """The plate is centred on the origin, so the row has to be. A row that
    marched out along +x under a centred plate cost a whole evaluation once."""
    offs = sv.row_offsets(MIXED)
    assert abs(offs[0] + offs[-1]) <= 1        # whole metres, so allow rounding


def test_the_plate_grows_for_the_biggest_shell_not_the_last_one():
    """`ground_size` used to reach `(count - 1) * spacing / 2 + reach`, which
    on a mixed row is not where the furthest shell ends up."""
    span_x, span_y = sv.ground_size(len(MIXED), footprints=MIXED)
    offs = sv.row_offsets(MIXED)
    slack = max(abs(v) for v in sv._ALONG)
    need = max(abs(o) + slack + sv._reach(f) for o, f in zip(offs, MIXED))
    assert span_x / 2.0 >= need
    assert span_y / 2.0 >= max(abs(v) for v in sv._ACROSS) + sv._reach(STADIUM)


def test_deterministic():
    assert sv.row_offsets(MIXED) == sv.row_offsets(MIXED)
    assert (sv.site_placements(5421, 4, footprints=MIXED)
            == sv.site_placements(5421, 4, footprints=MIXED))


def test_an_unmeasurable_shell_falls_back_rather_than_crashing():
    """`shell_footprint` returns None for a GLB it cannot read. One archetype
    in a lot of five must not take the site down."""
    offs = sv.row_offsets([DELI, None, GAS])
    assert len(offs) == 3
    placed = sv.site_placements(5421, 3, footprints=[DELI, None, GAS])
    spec = _spec(placed, [DELI, None, GAS])
    assert sv.overlapping(spec, footprints=[DELI, None, GAS]) == []


def test_one_building_is_still_one_building():
    offs = sv.row_offsets([DELI])
    assert offs == [0]
