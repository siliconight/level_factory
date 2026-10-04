"""One building line a street (Level Factory 0.135.0)."""
from packages.pipeline import road_grammar, site_variation, street_line

#: `gas_station_a02`'s measured extents: canopy and forecourt 32 m in front.
STATION = (-23.0, 23.0, -32.0, 14.0)
#: `bank_tower_a02`, near-symmetric.
BANK = (-18.2, 18.2, -14.2, 14.2)
#: `freight_terminal_a01`, wider than deep.
TERMINAL = (-27.2, 27.2, -16.2, 16.2)


def test_the_reach_toward_the_street_follows_the_turn():
    """Literals: the station's front is 32 m out at yaw 0, its back 14 m at
    180, and at 90 its west side (x -23) faces the street."""
    assert street_line.south_reach(STATION, 0) == 32.0
    assert street_line.south_reach(STATION, 180) == 14.0
    assert street_line.south_reach(STATION, 90) == 23.0
    assert street_line.south_reach(STATION, 270) == 23.0
    assert street_line.south_reach(None, 0) is None


def test_every_street_edge_lands_on_one_line():
    ys = street_line.line_ys([32.0, 14.2, 27.2])
    faces = [y - r for y, r in zip(ys, [32.0, 14.2, 27.2])]
    assert max(faces) - min(faces) < 0.011
    assert abs(max(ys) + min(ys)) < 0.011          # origins straddle 0
    assert street_line.line_ys([None, 10.0])[0] is None


def _place(extents, seed=9080):
    fps = [(46.0, 64.0), (36.3, 28.3), (54.3, 32.3)]
    return site_variation.site_placements(seed, 3, footprints=fps, shape="row",
                                          fronts=[0, 0, 270], extents=extents)


def test_a_row_stands_its_street_edges_on_one_line_and_keeps_every_other_draw():
    before = _place(None)
    after = _place([STATION, BANK, TERMINAL])
    faces = [b["at"][1] - b["street_reach"] for b in after["buildings"]]
    assert max(faces) - min(faces) < 0.011
    # x, yaw and roles are what they were: the across draw is still made
    assert [b["at"][0] for b in after["buildings"]] == [b["at"][0] for b in before["buildings"]]
    assert [b["rot"] for b in after["buildings"]] == [b["rot"] for b in before["buildings"]]
    assert {k: after[k] for k in ("spawn", "objective", "extraction")} == \
        {k: before[k] for k in ("spawn", "objective", "extraction")}
    # the station's store, 11 m in front of its origin, stands back behind its
    # forecourt: 32 - 11 = 21 m behind the line
    st = after["buildings"][0]
    assert abs((st["at"][1] - 11.0) - faces[0] - 21.0) < 0.011


def test_a_shape_that_turns_keeps_its_stagger():
    fps = [(36.3, 28.3)] * 4
    a = site_variation.site_placements(9080, 4, footprints=fps, shape="L", fronts=[0] * 4)
    b = site_variation.site_placements(9080, 4, footprints=fps, shape="L", fronts=[0] * 4,
                                       extents=[BANK] * 4)
    assert a == b


def test_the_road_hangs_off_the_street_edge_not_the_symmetric_footprint():
    """The through road lies the frontage, a sidewalk and half a carriageway
    in front of the line every building now stands on."""
    placed = _place([STATION, BANK, TERMINAL])
    bs = [dict(b, id=f"b{i}") for i, b in enumerate(placed["buildings"])]
    fps = [(46.0, 64.0), (36.3, 28.3), (54.3, 32.3)]
    roads, _spurs, _sx, _sy = road_grammar.roads_for("T", bs, fps, 400, 200)
    line = bs[0]["at"][1] - bs[0]["street_reach"]
    y_road = roads[0]["a"][1]
    want = line - road_grammar.FRONTAGE - road_grammar.SIDEWALK_WIDTH - road_grammar.ROAD_WIDTH / 2.0
    assert abs(y_road - want) < 0.011


def test_the_plate_holds_the_aligned_row():
    fps = [(46.0, 64.0), (36.3, 28.3), (54.3, 32.3)]
    placed = _place([STATION, BANK, TERMINAL])
    ys = [b["at"][1] for b in placed["buildings"]]
    sx, sy = site_variation.ground_size(3, footprints=fps, shape="row", ys=ys)
    spec = {"ground": {"size_x": sx, "size_y": sy},
            "buildings": [dict(b, id=f"b{i}") for i, b in enumerate(placed["buildings"])]}
    assert site_variation.uncovered(spec, footprints=fps) == []
