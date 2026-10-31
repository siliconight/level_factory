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


# ------------------------------------------------------------- block (0.177.0)

def _cycles(roads):
    """The road graph's cycles, as Lot's `site_targets.road_graph` counts them:
    nodes are road ends and junctions, edges the pieces between, cycles =
    edges - nodes + components. Axis-aligned roads only."""
    import math as _m

    def hit(r, s):
        (ax, ay), (bx, by) = r["a"], r["b"]
        (cx, cy), (dx, dy) = s["a"], s["b"]
        rw, sw = r["width"] / 2.0, s["width"] / 2.0
        r_h, s_h = abs(by - ay) < 1e-6, abs(dy - cy) < 1e-6
        if r_h == s_h:
            return None
        px, py = (cx, ay) if r_h else (ax, cy)
        if r_h and not (min(ax, bx) - rw <= px <= max(ax, bx) + rw and min(cy, dy) - sw <= py <= max(cy, dy) + sw):
            return None
        if not r_h and not (min(ay, by) - rw <= py <= max(ay, by) + rw and min(cx, dx) - sw <= px <= max(cx, dx) + sw):
            return None
        return (px, py)

    def on(r, p):
        (ax, ay), (bx, by) = r["a"], r["b"]
        w = r["width"] / 2.0
        return (min(ax, bx) - w <= p[0] <= max(ax, bx) + w and min(ay, by) - w <= p[1] <= max(ay, by) + w
                and (abs(by - ay) < 1e-6 and abs(p[1] - ay) <= w or abs(bx - ax) < 1e-6 and abs(p[0] - ax) <= w))

    junctions = [hit(r, s) for i, r in enumerate(roads) for j, s in enumerate(roads) if j > i and hit(r, s)]
    nodes, pieces = {}, []
    for r in roads:
        pts = [tuple(r["a"]), tuple(r["b"])] + [p for p in junctions if on(r, p)]
        along = sorted(set((round(p[0], 2), round(p[1], 2)) for p in pts))
        for p in along:
            nodes.setdefault(p, len(nodes))
        pieces += list(zip(along, along[1:]))
    parent = list(range(len(nodes)))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for p, q in pieces:
        a, b = find(nodes[p]), find(nodes[q])
        if a != b:
            parent[a] = b
    comps = len({find(i) for i in range(len(nodes))})
    return len(pieces) - len(nodes) + comps


def test_block_is_a_T_with_a_second_side_street_and_a_lane_behind_the_row():
    b, fp = _buildings()
    t_roads, t_doors, t_sx, t_sy = rg.roads_for("T", b, fp, 200, 120)
    roads, doors, sx, sy = rg.roads_for("block", b, fp, 200, 120)
    assert len(t_roads) == 2 and len(roads) == 4
    # the T is untouched when the plate already holds the rest
    assert roads[0] == t_roads[0] and roads[1] == t_roads[1] and (sx, sy) == (t_sx, t_sy)
    cross1, cross2, lane = roads[1], roads[2], roads[3]
    # the lane: the guide's service lane, no sidewalk, behind the deepest rear face by the yard
    # with its dumpster and a margin, between the two side streets' centre lines
    rear = max(float(x["at"][1]) + fp[0][1] / 2.0 for x in b)
    assert lane["kind"] == "service_lane" and lane["sidewalk"] == 0.0 and lane["width"] == rg.LANE_WIDTH
    assert lane["a"][1] == lane["b"][1] == rear + rg.LANE_SETBACK + rg.LANE_WIDTH / 2.0
    assert sorted((lane["a"][0], lane["b"][0])) == sorted((cross1["a"][0], cross2["a"][0]))
    assert lane["serves"] == ["b0", "b1", "b2"]
    # the second side street: past the row's end farther from the first, half a band off the
    # last building, ending on the front road and running to the plate's far margin like the first
    west = min(float(x["at"][0]) for x in b) - fp[0][0] / 2.0
    east = max(float(x["at"][0]) for x in b) + fp[0][0] / 2.0
    far = west - rg.ROAD_BAND / 2.0 if cross1["a"][0] > (west + east) / 2.0 else east + rg.ROAD_BAND / 2.0
    assert cross2["a"] == [far, roads[0]["a"][1]] and cross2["b"] == [far, sy / 2.0 - rg.ROAD_MARGIN]
    assert cross2["width"] == rg.ROAD_WIDTH and cross2["sidewalk"] == rg.SIDEWALK_WIDTH
    # one loop where the T had none
    assert _cycles(t_roads) == 0 and _cycles(roads) == 1


def test_block_gives_every_building_a_rear_door_path_to_the_lane():
    b, fp = _buildings()
    _t, t_doors, _sx, _sy = rg.roads_for("T", b, fp, 200, 120)
    roads, doors, _sx2, _sy2 = rg.roads_for("block", b, fp, 200, 120)
    lane = roads[3]
    new = [d for d in doors if d not in t_doors]
    rear = [d for d in new if d["a"][1] > 0 and d["a"][0] == d["b"][0]]
    assert [d["building"] for d in rear] == ["b0", "b1", "b2"]
    for d in rear:
        assert d["a"][1] == fp[0][1] / 2.0 + 1.0                       # a metre out from the rear face
        assert d["b"][1] == lane["a"][1] - rg.LANE_WIDTH / 2.0 - 0.5    # half a metre short of the lane
        assert d["width"] == rg.SPUR_WIDTH
    # and the far building gets a side door onto the second street, as the first street's flank does
    assert any(d.get("building") == "b0" and d["a"][1] == d["b"][1] and d not in t_doors for d in new)


def test_the_plate_grows_to_hold_the_lane_and_the_second_street():
    b, fp = _buildings()
    roads, _d, sx, sy = rg.roads_for("block", b, fp, 100, 50)
    lane, cross2 = roads[3], roads[2]
    assert sx / 2.0 >= abs(cross2["a"][0]) + rg.ROAD_BAND / 2.0
    assert sy / 2.0 - rg.ROAD_MARGIN >= lane["a"][1] + rg.LANE_WIDTH / 2.0 + rg.ROAD_MARGIN
    assert roads[0]["a"][0] == -sx / 2.0 and roads[0]["b"][0] == sx / 2.0
    assert roads[1]["b"][1] == cross2["b"][1] == sy / 2.0 - rg.ROAD_MARGIN


def test_block_spellings_and_the_rest_unchanged():
    for word in ("block", "loop", "service_lane", "rear_lane", "alley", "back_lane"):
        assert rg.grammar_of(word) == "block", word
    assert rg.grammar_of("") == "T" and rg.grammar_of("cross") == "cross"
    assert "block" in rg.GRAMMARS


@pytest.mark.skipif(not os.path.isdir(LOT), reason="lot repo not beside this one")
def test_lot_reads_the_lane_as_two_stems_that_stop_at_the_streets():
    """Lot draws the junctions, so Lot has to believe them: the lane ENDS on both
    side streets -- `terminal` is recorded on the road that is crossed, as the
    T test above reads it off the front road, and the stem's slab is clipped at
    its mouths -- and a lane without a sidewalk STOPS at a street and never
    gets a signal (Lot 0.113.0's rule; against an older Lot every leg of an
    arterial's junction was signalised)."""
    b, fp = _buildings()
    roads, _d, sx, sy = rg.roads_for("block", b, fp, 200, 120)
    resolved = _lot_roads(roads, sx, sy)
    lane = resolved[3]
    for street in (resolved[1], resolved[2]):
        hits = [c for c in street.crossings if c.kind == "road" and c.crosser == 3]
        assert len(hits) == 1 and hits[0].terminal, "the lane should end on this street"
    assert len([c for c in lane.crossings if c.kind == "road"]) == 2
    assert 0.0 < lane.slab[0] < lane.slab[1] < lane.length, "the lane's slab is clipped at both mouths"
    sys.path.insert(0, LOT)
    import site_streets
    legs = [a for a in site_streets.approaches(resolved) if a.road == 3]
    assert legs and all(a.control == "stop" and a.minor for a in legs), legs
    assert not any(a.control == "signal" for a in site_streets.approaches(resolved) if 3 in (a.road, a.crosser))


def test_an_avenue_is_the_front_road_alone():
    """0.263.0: the T's front road and its doors' spurs, no cross street, the plate not widened for one."""
    b, fp = _buildings(n=4)
    t_roads, t_doors, t_x, t_y = rg.roads_for("T", b, fp, 200, 120)
    a_roads, a_doors, a_x, a_y = rg.roads_for("avenue", b, fp, 200, 120)
    assert len(a_roads) == 1 and len(t_roads) >= 2
    assert a_roads[0]["a"][1] == t_roads[0]["a"][1] and a_roads[0]["width"] == rg.ROAD_WIDTH
    assert a_y == t_y and a_x <= t_x
    assert a_doors and all(d in t_doors for d in a_doors)
    for spelling in ("avenue", "ave", "one_road", "single_road"):
        assert rg.grammar_of(spelling) == "avenue"
    for spelling in ("main_street", "strip", "street"):        # what briefs on disk wrote stays a T
        assert rg.grammar_of(spelling) == "T"


# ------------------------------------------------------------- side_streets (0.275.0)

def _slice_row():
    """The vertical slice's row (seed 9104 of slice 24, `site.site.drawn.json`): its four buildings and the
    footprints `site_variation.shell_footprint` measures off their Deli Counter shells. Gaps between them, edge to
    edge: 32.8, 14.6 and 30.7 m."""
    b = [{"id": "b0", "at": [-86, 11.44], "rot": 0, "street_reach": 32.0},
         {"id": "b1", "at": [-15, -9.41], "rot": 0, "street_reach": 11.15},
         {"id": "b2", "at": [25, -11.44], "rot": 0, "street_reach": 9.125},
         {"id": "b3", "at": [92, -7.41], "rot": 0, "street_reach": 13.15}]
    fp = [(46.0, 64.0), (30.46, 22.46), (20.25, 18.25), (52.3, 26.9)]
    return b, fp


def test_side_streets_cross_the_avenue_in_every_gap_a_block_apart():
    """The slice's row has two gaps that hold a street, 97 m apart, and one that does not: two side streets, each
    in its gap, each running the plate's full depth across the avenue."""
    b, fp = _slice_row()
    roads, doors, sx, sy = rg.roads_for("side_streets", b, fp, 256, 114)
    av = rg.roads_for("avenue", b, fp, 256, 114)[0][0]
    assert roads[0]["a"][1] == av["a"][1] and len(roads) == 3
    xs = [r["a"][0] for r in roads[1:]]
    assert xs == sorted(xs) and xs[1] - xs[0] >= rg.BLOCK_MIN
    assert xs[0] == pytest.approx((-63.0 + -30.23) / 2.0, abs=0.01)     # between the gas station and the bank
    assert xs[1] == pytest.approx((35.125 + 65.85) / 2.0, abs=0.01)     # between the card shop and the train yard
    for r in roads[1:]:
        assert r["a"][1] < roads[0]["a"][1] < r["b"][1], "a side street crosses the avenue, it does not end on it"
        assert r["a"][1] == -sy / 2.0 + rg.ROAD_MARGIN and r["b"][1] == sy / 2.0 - rg.ROAD_MARGIN
    # each building flanking a street gets a door on it, as a T's corner buildings do
    lateral = [d for d in doors if d["a"][1] == d["b"][1]]
    assert sorted(d["building"] for d in lateral) == ["b0", "b1", "b2", "b3"]
    for spelling in ("side_streets", "side_street", "main_drag"):
        assert rg.grammar_of(spelling) == "side_streets"


def test_side_streets_keep_a_block_between_them():
    """Two gaps nearer than `BLOCK_MIN` get one street, in the wider; a row with no gap that holds a band gets one
    street past its west end, as a T does."""
    b = [{"id": "b%d" % i, "at": [x, 0], "rot": 0} for i, x in enumerate((-60, 0, 50))]
    fp = [(30.0, 20.0)] * 3                     # gaps 30 m and 20 m, centres 55 m apart
    roads, _d, _sx, _sy = rg.roads_for("side_streets", b, fp, 200, 120)
    assert [r["a"][0] for r in roads[1:]] == [-30.0]
    tight, tfp = _buildings(n=3, pitch=40, footprint=(30.0, 20.0))   # 10 m gaps
    roads, _d, sx, _sy = rg.roads_for("side_streets", tight, tfp, 140, 120)
    t_roads = rg.roads_for("T", tight, tfp, 140, 120)[0]
    assert len(roads) == 2 and roads[1]["a"][0] == t_roads[1]["a"][0] < -55.0


@pytest.mark.skipif(not os.path.isdir(LOT), reason="lot repo not beside this one")
def test_lot_reads_each_side_street_as_an_X():
    """Lot draws the junctions: each side street passes THROUGH the avenue -- its slab whole, a gap mid-span where
    the avenue owns the surface -- and the avenue records each crossing as not terminal."""
    b, fp = _slice_row()
    roads, _d, sx, sy = rg.roads_for("side_streets", b, fp, 256, 114)
    resolved = _lot_roads(roads, sx, sy)
    hits = [c for c in resolved[0].crossings if c.kind == "road"]
    assert sorted(c.crosser for c in hits) == [1, 2] and not any(c.terminal for c in hits)
    for side in resolved[1:]:
        assert side.slab[0] == pytest.approx(0.0)
        (g0, g1), = side.gaps
        assert 0.0 < g0 < g1 < side.length
