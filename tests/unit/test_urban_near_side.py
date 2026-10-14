"""The urban street's near side: mid-rise Empties filling the frontage between the mission's own buildings
(Level Factory 0.201.0, factory roadmap 241).

The comps (`docs/reference/URBAN_MIDRISE_COMPS.md` in the factory root): buildings at the sidewalk line,
touching, a gap an event. 0.200.0 stood the far side as that wall; this stands the near side's frontage the
same way, between the mission's buildings, each of which keeps `NEAR_PASSAGE` clear on both sides. No road but
the through road is built over, and the plate's ends keep `CLEARANCE`.
"""
from packages.pipeline import empties, site_variation

#: Two mid-rises as `street_line.shell_extents` reads them (x0, x1, y0, y1): 15 and 24 m wide, 15 m deep.
EXT = {"gs_midrise_a": (-7.5, 7.5, -7.5, 7.5), "gs_midrise_b": (-12.0, 12.0, -7.5, 7.5)}
ROWS = [{"id": "gs_midrise_a"}, {"id": "gs_midrise_b"}]
#: The through road at y -27.65, 10 m wide with 3 m sidewalks: the near walk's back edge is y -19.65, and the
#: near building line, `FRONTAGE` behind it, y -17.65.
THROUGH = {"a": [-90.0, -27.65], "b": [90.0, -27.65], "width": 10.0, "sidewalk": 3.0}
LINE = -17.65
#: Two of the mission's buildings standing on the near line, 30 m wide and 40 m deep.
BUILDINGS = [(-40.0, -10.0, LINE, LINE + 40.0), (20.0, 50.0, LINE, LINE + 40.0)]


def _rect(p):
    x0, x1, y0, y1 = EXT[p["archetype"]]
    return (p["at"][0] + x0, p["at"][0] + x1, p["at"][1] + y0, p["at"][1] + y1)


def _infill(roads=(THROUGH,), buildings=BUILDINGS, seed=9104):
    return empties.infill(ROWS, EXT, site_variation.stream(seed), list(roads), 180.0, list(buildings))


def test_every_front_stands_on_the_near_line_facing_the_road():
    placed, need = _infill()
    assert placed
    assert {p["front"] for p in placed} == {LINE}
    assert all(p["rot"] == 0 for p in placed)
    # `need` is how far NORTH of the origin the plate must reach: these backs stand at y -2.65, south of it
    assert need == 0.0
    north = {"a": [-90.0, 10.0], "b": [90.0, 10.0], "width": 10.0, "sidewalk": 3.0}   # the line at y 20
    placed, need = empties.infill(ROWS, EXT, site_variation.stream(9104), [north], 180.0, [])
    assert placed and abs(need - (20.0 + 15.0)) < 1e-6


def test_each_mission_building_keeps_its_passage_and_the_plate_its_ends():
    placed, _ = _infill()
    for p in placed:
        x0, x1, _y0, _y1 = _rect(p)
        assert x0 >= -90.0 + empties.CLEARANCE - 1e-9 and x1 <= 90.0 - empties.CLEARANCE + 1e-9, p
        for bx0, bx1, _by0, _by1 in BUILDINGS:
            assert x1 <= bx0 - empties.NEAR_PASSAGE + 1e-9 or x0 >= bx1 + empties.NEAR_PASSAGE - 1e-9, (p, bx0, bx1)


def test_the_frontage_between_is_filled_and_no_two_neighbours_are_the_same():
    placed, _ = _infill()
    rects = sorted(_rect(p) + (p["archetype"],) for p in placed)
    # the run between the two buildings, x -6 to 16: 22 m holds one 15 m block and not a 24 m one
    between = [r for r in rects if r[0] >= -10.0 and r[1] <= 20.0]
    assert len(between) == 1 and between[0][4] == "gs_midrise_a", between
    for a, b in zip(rects, rects[1:]):
        if abs(b[0] - a[1]) < 1e-6:
            assert a[4] != b[4], (a, b)


def test_a_side_street_and_a_service_lane_are_never_built_over():
    side = {"a": [70.0, -22.65], "b": [70.0, 60.0], "width": 8.0, "sidewalk": 2.0}
    placed, _ = _infill(roads=(THROUGH, side))
    band = (70.0 - (4.0 + 2.0 + empties.FRONTAGE), 70.0 + (4.0 + 2.0 + empties.FRONTAGE))
    assert all(_rect(p)[1] <= band[0] + 1e-9 or _rect(p)[0] >= band[1] - 1e-9 for p in placed)
    lane = {"a": [-90.0, LINE + 12.0], "b": [90.0, LINE + 12.0], "width": 5.0, "sidewalk": 0.0}
    placed, need = _infill(roads=(THROUGH, lane))
    assert placed == [] and need == 0.0, "a 15 m block on a line 12 m from the lane would stand in it"


def test_no_rows_or_no_roads_place_nothing():
    assert empties.infill([], EXT, site_variation.stream(1), [THROUGH], 180.0, BUILDINGS) == ([], 0.0)
    assert empties.infill(ROWS, EXT, site_variation.stream(1), [], 180.0, BUILDINGS) == ([], 0.0)


def test_building_rect_turns_a_quarter_at_a_time():
    assert empties.building_rect([10.0, 5.0], 0, (30.0, 40.0)) == (-5.0, 25.0, -15.0, 25.0)
    assert empties.building_rect([10.0, 5.0], 90, (30.0, 40.0)) == (-10.0, 30.0, -10.0, 20.0)
