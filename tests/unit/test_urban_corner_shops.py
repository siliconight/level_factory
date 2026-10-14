"""Corner shops: an urban wall's runs open and close on a corner block (Level Factory 0.206.0, factory roadmap 241).

The comps (the factory root's `docs/reference/URBAN_MIDRISE_COMPS.md`): "Corners carry the life. The corner
building has the shop at grade (lit, awning), homes above. The middle of the block is residential." Deli Counter
0.218.0 builds four corner blocks, `gs_cornershop_a` to `_d`, mid-rises whose ground-floor front is a shop. A run of
the urban wall -- between two roads crossing the far side, or a road and the plate's end -- is one block face, and
its two ends are the block's corners. The near side never stands one: its corners are the mission's.

FAILS ON 0.205.0: the library hands an urban brief no `gs_cornershop_*`, and a row of the corner family is dealt
along the wall like any other.
"""
import hashlib
import json

from packages.core.models import MissionBrief
from packages.pipeline import building_library, empties, site_variation

#: The six wide mid-rises as `street_line.shell_extents` reads them (x0, x1, y0, y1), and each one's top.
EXT = {"a": (-7.5, 7.5, -7.5, 7.5), "b": (-9.0, 9.0, -7.5, 7.5), "c": (-10.5, 10.5, -7.5, 7.5),
       "d": (-8.25, 8.25, -7.5, 7.5), "e": (-12.0, 12.0, -7.5, 7.5), "f": (-9.75, 9.75, -7.5, 7.5)}
TOP = {"a": 16.5, "b": 19.8, "c": 22.7, "d": 26.2, "e": 32.5, "f": 38.7}
#: The four corner blocks at Deli Counter 0.218.0's widths, 15 m deep.
CORNER_EXT = {"ka": (-7.5, 7.5, -7.5, 7.5), "kb": (-9.0, 9.0, -7.5, 7.5), "kc": (-6.0, 6.0, -7.5, 7.5),
              "kd": (-8.25, 8.25, -7.5, 7.5)}
ALL_EXT = dict(EXT, **CORNER_EXT)
TOPS = dict(TOP, ka=19.6, kb=26.0, kc=16.5, kd=22.8)
ROWS = [{"id": k, "family": "empty"} for k in EXT]
CORNERS = [{"id": k, "family": "corner"} for k in CORNER_EXT]
THROUGH = {"a": [-90.0, -27.65], "b": [90.0, -27.65], "width": 10.0, "sidewalk": 3.0}
#: A road leaving the through road southward, across the far side: it splits the wall into two runs.
CROSS = {"a": [10.0, -27.65], "b": [10.0, -80.0], "width": 8.0, "sidewalk": 2.0}
WALLS = [(seed, action) for seed in range(1, 41) for action in (None, 0.0, -40.0, 55.0)]


def _wall(seed, action, roads=(THROUGH,), rows=ROWS + CORNERS, continuous=True):
    placed, _ = empties.terrace(list(rows), ALL_EXT, site_variation.stream(seed), list(roads), 180.0,
                                continuous=continuous, action=action,
                                heights=TOPS if action is not None else None)
    return placed


def _touch(a, b):
    return abs((a["at"][0] + a["size_x"] / 2.0) - (b["at"][0] - b["size_x"] / 2.0)) < 1e-6


def test_a_run_opens_and_closes_on_a_corner_and_none_stands_between():
    for seed, action in WALLS:
        placed = _wall(seed, action)
        kinds = [p["archetype"] in CORNER_EXT for p in placed]
        assert kinds[0] and kinds[-1], (seed, action, [p["archetype"] for p in placed])
        assert not any(kinds[1:-1]), (seed, action, [p["archetype"] for p in placed])


def test_the_wall_between_its_corners_is_continuous():
    for seed, action in WALLS:
        placed = _wall(seed, action)
        for a, b in zip(placed, placed[1:]):
            assert _touch(a, b), (seed, action, a, b)


def test_a_crossing_splits_the_wall_and_each_run_has_its_corners():
    edge = empties._far_side(THROUGH)[0]
    (b0, b1), = empties._blocked([THROUGH, CROSS], edge)
    for seed, action in WALLS:
        placed = _wall(seed, action, roads=(THROUGH, CROSS))
        west = [p for p in placed if p["at"][0] < b0]
        east = [p for p in placed if p["at"][0] > b1]
        assert len(west) + len(east) == len(placed), (seed, action)
        for run in (west, east):
            assert run[0]["archetype"] in CORNER_EXT and run[-1]["archetype"] in CORNER_EXT, (seed, action, run)
            assert not any(p["archetype"] in CORNER_EXT for p in run[1:-1]), (seed, action, run)
        assert all(p["at"][0] + p["size_x"] / 2.0 <= b0 + 1e-6 for p in west), (seed, action)
        assert all(p["at"][0] - p["size_x"] / 2.0 >= b1 - 1e-6 for p in east), (seed, action)


def test_a_run_s_two_corners_are_two_shops():
    for seed, action in WALLS:
        placed = _wall(seed, action)
        assert placed[0]["archetype"] != placed[-1]["archetype"], (seed, action)


def test_the_wall_s_own_rule_still_holds_between_the_corners():
    """Every mid-rise design stands, and no two neighbours are alike, as 0.204.0's wall."""
    for seed, action in WALLS:
        placed = _wall(seed, action)
        assert {p["archetype"] for p in placed[1:-1]} == set(EXT), (seed, action)
        for a, b in zip(placed, placed[1:]):
            assert a["archetype"] != b["archetype"], (seed, action, a, b)


def _digest(rows):
    h = hashlib.sha256()
    for roads in ([THROUGH], [THROUGH, CROSS]):
        for seed in range(1, 41):
            for action in (None, 0.0, -40.0, 55.0):
                for continuous in (True, False):
                    placed, need = empties.terrace(list(rows), EXT, site_variation.stream(seed), roads, 180.0,
                                                   continuous=continuous, action=action,
                                                   heights=TOP if action is not None else None)
                    h.update(json.dumps([placed, need], sort_keys=True).encode("utf-8"))
    return h.hexdigest()[:16]


def test_without_a_corner_row_every_wall_is_0_205_0_s():
    """The control: 320 walls -- with and without a crossing, four actions, strip and urban -- read on 0.205.0
    before this change was written, digest 0e0dee4a52faa9e4."""
    assert _digest([{"id": k} for k in EXT]) == "0e0dee4a52faa9e4"


def test_a_strip_terrace_stands_no_corner():
    for seed, action in WALLS:
        placed = _wall(seed, action, continuous=False)
        assert placed == _wall(seed, action, rows=ROWS, continuous=False), (seed, action)
        assert not any(p["archetype"] in CORNER_EXT for p in placed), (seed, action)


def test_the_near_side_stands_no_corner():
    rooms = [(-40.0, -20.0, -25.0, 5.0), (20.0, 40.0, -25.0, 5.0)]
    for seed in range(1, 41):
        placed, _ = empties.infill(ROWS + CORNERS, ALL_EXT, site_variation.stream(seed), [THROUGH], 180.0, rooms)
        plain, _ = empties.infill(ROWS, ALL_EXT, site_variation.stream(seed), [THROUGH], 180.0, rooms)
        assert placed and placed == plain, seed


def _brief(**kw):
    base = dict(mission_id="m", display_name="m", archetype="corner_deli", building_count=3, lot_library="lib")
    base.update(kw)
    return MissionBrief(**{k: v for k, v in base.items() if k in MissionBrief.__dataclass_fields__})


def test_an_urban_brief_draws_the_corners_as_their_own_family(tmp_path):
    for aid in ("gs_empty_rowhome_a", "gs_midrise_a", "gs_midrise_b", "gs_cornershop_a", "gs_cornershop_b",
                "gs_corner_station"):
        (tmp_path / (aid + ".glb")).write_bytes(b"glb")
        (tmp_path / (aid + ".gameplay.json")).write_text("{}")
        (tmp_path / (aid + ".slots.json")).write_text("{}")
        facade = "false" if aid == "gs_corner_station" else "true"
        (tmp_path / (aid + ".validation.json")).write_text('{"facade": %s}' % facade)
    strip = building_library.empties_for_brief(_brief(lot_library=str(tmp_path)))
    urban = building_library.empties_for_brief(_brief(lot_library=str(tmp_path), streetscape="urban"))
    assert [(r["id"], r["family"]) for r in strip] == [("gs_empty_rowhome_a", "empty")]
    assert [(r["id"], r["family"]) for r in urban] == [("gs_midrise_a", "empty"), ("gs_midrise_b", "empty"),
                                                      ("gs_cornershop_a", "corner"), ("gs_cornershop_b", "corner")]
