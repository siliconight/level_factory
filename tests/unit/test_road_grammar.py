"""The road grammar: a T is what it always was, and a crossroads is an X.

`site_variation` varies where the BUILDINGS go. This varies the STREET, which
until now was a constant: `_street_for` emitted one road along the plate's
south edge and one cross street ending on it -- a T -- on every site the
factory has ever generated.

TWO THINGS THESE TESTS HOLD, and they pull in opposite directions:

  * `T` must not move. It is the street a thousand existing candidates stand
    on, and the grammar exists to ADD to that rather than to replace it. The
    move from `apps.cli.commands._street_for` was checked against all 74
    building sets on disk and reproduced every one exactly; these pin the
    shape of that output so a later edit cannot drift it quietly.

  * `cross` must be a real X, not a T with a longer arm. The difference is
    whether the side street PASSES THROUGH the front road, and the test for
    it is not geometric -- it is whether LOT sees an X, because Lot is what
    draws the junction. `lot.site_streets` has carried the machinery since
    its `Road` model gained `gaps` ("where a lower-index road crosses THROUGH
    it, that road's carriageway and bands own the junction's surface") and no
    generated level has ever exercised it. So the last test here is the first
    time that code runs on a generated street.
"""
import os
import sys

import pytest

from packages.pipeline import road_grammar as rg

LOT = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                   "..", "..", "..", "lot")


def _buildings(n=3, pitch=60, footprint=(40.0, 26.0)):
    """A row of `n` shells, the shape `site_variation` lays out."""
    xs = [(i - (n - 1) / 2.0) * pitch for i in range(n)]
    return ([{"id": f"b{i}", "at": [x, 0], "rot": 0} for i, x in enumerate(xs)],
            [footprint] * n)


# ------------------------------------------------------------- vocabulary
def test_an_unknown_spelling_is_a_T_and_says_so():
    """The `site_variation` trade, repeated deliberately: refusing a build
    over a label is the wrong call, but a fallback that leaves no trace is a
    wrong-but-plausible street. So it falls back AND stays distinguishable."""
    assert rg.grammar_of("no_such_street") == "T"
    assert rg.grammar_known("no_such_street") is False
    assert rg.grammar_known("crossroads") is True
    assert rg.grammar_of("") == "T"
    assert rg.grammar_known("") is True          # unset MEANS T, and is known


def test_every_grammar_in_the_vocabulary_is_reachable_by_some_spelling():
    """A grammar nothing can ask for is dead code wearing a name."""
    reachable = {rg.grammar_of(s) for s in rg.known_spellings()}
    assert set(rg.GRAMMARS) <= reachable, (
        "unreachable: %s" % (set(rg.GRAMMARS) - reachable))


def test_no_buildings_no_street():
    assert rg.roads_for("T", [], [], 50, 50) == ([], [], 50, 50)
    assert rg.roads_for("cross", [], [], 50, 50) == ([], [], 50, 50)


# ------------------------------------------------------------------- T
def test_T_puts_the_side_street_ON_the_front_road_not_through_it():
    b, fp = _buildings()
    roads, _spurs, _sx, _sy = rg.roads_for("T", b, fp, 200, 120)
    front, side = roads
    assert front["a"][1] == front["b"][1], "the front road runs east-west"
    # a T: the side street BEGINS on the front road's centre line
    assert side["a"][1] == pytest.approx(front["a"][1])
    assert side["b"][1] > front["a"][1], "and runs away from it, northward"


def test_T_keeps_the_front_road_south_of_every_building():
    b, fp = _buildings()
    roads, _s, _sx, _sy = rg.roads_for("T", b, fp, 200, 120)
    y_road = roads[0]["a"][1]
    for bld, f in zip(b, fp):
        assert y_road < bld["at"][1] - f[1] / 2.0


# --------------------------------------------------------------- cross
def test_cross_spans_the_front_road_rather_than_ending_on_it():
    b, fp = _buildings()
    roads, _s, _sx, _sy = rg.roads_for("cross", b, fp, 200, 120)
    front, side = roads
    y = front["a"][1]
    assert side["a"][1] < y < side["b"][1], (
        "a crossroads' side street must pass THROUGH the front road; got "
        "a=%.2f road=%.2f b=%.2f" % (side["a"][1], y, side["b"][1]))


def test_cross_and_T_differ_only_in_the_side_street_s_south_end():
    """The front road, the side street's line and the spurs are the same
    decisions in both. If a later edit moves one of them for `cross` only,
    the two grammars have stopped being comparable."""
    b, fp = _buildings()
    t_roads, t_spurs, _tx, _ty = rg.roads_for("T", b, fp, 200, 120)
    x_roads, x_spurs, _xx, _xy = rg.roads_for("cross", b, fp, 200, 120)
    assert t_roads[0] == x_roads[0], "the front road is the same road"
    assert t_spurs == x_spurs, "the door paths are the same paths"
    assert t_roads[1]["a"][0] == x_roads[1]["a"][0], "the side street's line"
    assert t_roads[1]["b"] == x_roads[1]["b"], "and its north end"


def test_the_plate_grows_to_hold_the_south_arm():
    """A crossroads needs plate south of the front road for its fourth
    approach. A stub that stops at the road's own band is a T with extra
    paint."""
    b, fp = _buildings()
    _tr, _ts, _tx, t_span_y = rg.roads_for("T", b, fp, 200, 120)
    x_roads, _xs, _xx, x_span_y = rg.roads_for("cross", b, fp, 200, 120)
    assert x_span_y >= t_span_y
    south_arm = x_roads[0]["a"][1] - x_roads[1]["a"][1]
    assert south_arm > rg.ROAD_WIDTH / 2.0 + rg.SIDEWALK_WIDTH, (
        "the south arm is %.2f m, shorter than the road's own half-band -- "
        "that is a stub, not an approach" % south_arm)


# ------------------------------------------------ what LOT makes of it
def _lot_roads(roads, span_x, span_y):
    """Lot's own resolution of a road list: kerbs, crossings, slabs, gaps."""
    if LOT not in sys.path:
        sys.path.insert(0, os.path.abspath(LOT))
    import site_streets
    spec = {"buildings": [], "roads": roads,
            "ground": {"size_x": span_x, "size_y": span_y}}
    return site_streets.roads(spec)


@pytest.mark.skipif(not os.path.isdir(LOT), reason="lot repo not beside this one")
def test_lot_reads_a_T_as_a_T_and_a_crossroads_as_an_X():
    """THE ONE THAT MATTERS, because Lot draws the junction and Lot is what
    has to believe it.

    THE SIGNAL IS `terminal`, NOT `gaps`, and the first version of this test
    asserted the wrong one. `road.gaps` is filled for a crossing whose
    `crosser` index is LOWER than the road's own -- the lower-index road owns
    the junction's surface and the higher-index road yields -- so on both a T
    and an X it is road 1 that carries a gap, and asserting a gap on road 0
    fails for a crossroads that is working perfectly. Read off the real
    resolution rather than guessed a second time:

        T      road 0  crossing t=130 terminal=True   kerb cuts 1
               road 1  slab 8..81 (clipped)  gap (-8, 8) at its START
        cross  road 0  crossing t=130 terminal=False  kerb cuts 2
               road 1  slab 0..116 (full)    gap (27, 43) MID-SPAN

    A road that ENDS on another terminates there; one that PASSES THROUGH does
    not. That is the whole difference between three approaches and four, and
    it is one boolean in Lot's own output.
    """
    b, fp = _buildings()
    t_roads, _s, t_sx, t_sy = rg.roads_for("T", b, fp, 200, 120)
    x_roads, _s2, x_sx, x_sy = rg.roads_for("cross", b, fp, 200, 120)

    def front_crossing(resolved):
        road = resolved[0]
        hits = [c for c in road.crossings if c.kind == "road"]
        assert len(hits) == 1, "expected one road crossing, got %d" % len(hits)
        return hits[0]

    assert front_crossing(_lot_roads(t_roads, t_sx, t_sy)).terminal is True, (
        "a T's side street ENDS on the front road, so Lot should call that "
        "crossing terminal")
    assert front_crossing(_lot_roads(x_roads, x_sx, x_sy)).terminal is False, (
        "a crossroads' side street PASSES THROUGH the front road; if Lot "
        "still calls it terminal the fourth approach does not exist and the "
        "grammar has produced a T with a longer arm")


@pytest.mark.skipif(not os.path.isdir(LOT), reason="lot repo not beside this one")
def test_the_side_street_is_clipped_at_a_T_and_whole_at_a_crossroads():
    """The other half of the same fact, in the geometry Lot will draw. A T's
    side street begins past the front road's band -- the front road's dropped
    kerb carries its mouth -- so its slab is clipped. A crossroads' runs the
    whole way and takes a gap out of the middle instead."""
    b, fp = _buildings()
    t_roads, _s, t_sx, t_sy = rg.roads_for("T", b, fp, 200, 120)
    x_roads, _s2, x_sx, x_sy = rg.roads_for("cross", b, fp, 200, 120)

    side_T = _lot_roads(t_roads, t_sx, t_sy)[1]
    side_X = _lot_roads(x_roads, x_sx, x_sy)[1]

    assert side_T.slab[0] > 0.0, "a T's side street should start past the band"
    assert side_X.slab[0] == pytest.approx(0.0), (
        "a crossroads' side street runs the whole plate")
    assert side_X.gaps, "and takes a gap where the front road passes"
    (g0, g1), = side_X.gaps
    assert g0 > 0.0 and g1 < side_X.length, (
        "that gap must be MID-SPAN (%.1f..%.1f of %.1f); at an end it is a T"
        % (g0, g1, side_X.length))


@pytest.mark.skipif(not os.path.isdir(LOT), reason="lot repo not beside this one")
def test_a_crossroads_has_four_approaches_worth_of_kerb_cuts():
    """A T has three approaches, a crossroads four. Lot drops a kerb per
    approach, so the cut count is the cheapest reading of how many ways in
    the junction has -- and it is a count, not a picture, so it can regress
    without anybody looking at the level."""
    b, fp = _buildings()
    t_roads, _s, t_sx, t_sy = rg.roads_for("T", b, fp, 200, 120)
    x_roads, _s2, x_sx, x_sy = rg.roads_for("cross", b, fp, 200, 120)

    def cuts(resolved):
        return sum(len(k.cuts) for r in resolved for k in r.kerbs)

    t_cuts, x_cuts = cuts(_lot_roads(t_roads, t_sx, t_sy)), \
        cuts(_lot_roads(x_roads, x_sx, x_sy))
    assert x_cuts > t_cuts, (
        "a crossroads should drop more kerb than a T (%d vs %d); if they are "
        "equal the fourth approach is not reaching Lot" % (x_cuts, t_cuts))
