"""Empties across the street (Level Factory 0.137.0, roadmap 106)."""
import json
from pathlib import Path

from packages.core.models import MissionBrief
from packages.pipeline import building_library, empties, site_variation

#: Deli Counter 0.174.0's rowhome Empties as `street_line.shell_extents`
#: reads them (x0, x1, y0, y1): widths 5.5-6.5 m, 12 m deep. Literals.
EXT = {"gs_empty_rowhome_a": (-3.0, 3.0, -6.15, 6.15),
       "gs_empty_rowhome_b": (-2.75, 2.75, -6.15, 6.15),
       "gs_empty_rowhome_c": (-3.25, 3.25, -6.15, 6.15)}
ROWS = [{"id": k} for k in sorted(EXT)]
#: A through road along x at y -27.65, 10 m wide, 3 m sidewalks: the far
#: sidewalk's back edge is y -35.65, so the Empties' fronts stand at -37.65.
THROUGH = {"a": [-90.0, -27.65], "b": [90.0, -27.65], "width": 10.0, "sidewalk": 3.0}


def _terrace(roads=(THROUGH,), span_x=180.0, seed=9080):
    return empties.terrace(ROWS, EXT, site_variation.stream(seed), list(roads), span_x)


def test_every_front_stands_on_one_line_two_metres_behind_the_far_walk():
    placed, need = _terrace()
    assert placed
    assert {p["front"] for p in placed} == {-37.65}
    assert all(p["rot"] == 180 for p in placed)
    # the plate must reach past the deepest back: 37.65 + 12.3
    assert abs(need - (37.65 + 12.3)) < 1e-6


def test_no_two_neighbours_are_the_same_house_and_alleys_break_the_row():
    placed, _ = _terrace()
    kinds = [p["archetype"] for p in placed]
    assert all(a != b for a, b in zip(kinds, kinds[1:]))
    # touching within a run, an alley of 3 m between runs, runs of 5 to 8
    gaps, run = [], 1
    runs = []
    for a, b in zip(placed, placed[1:]):
        gap = (b["at"][0] - b["size_x"] / 2) - (a["at"][0] + a["size_x"] / 2)
        if gap > 1e-6:
            gaps.append(round(gap, 3))
            runs.append(run)
            run = 1
        else:
            assert abs(gap) < 1e-6
            run += 1
    assert gaps and set(gaps) == {3.0}
    assert all(5 <= r <= 8 for r in runs)


def test_the_row_stays_on_the_plate_and_off_a_road_that_runs_south():
    span = 180.0
    placed, _ = _terrace(span_x=span)
    assert min(p["at"][0] - p["size_x"] / 2 for p in placed) >= -span / 2 + 4.0 - 1e-6
    assert max(p["at"][0] + p["size_x"] / 2 for p in placed) <= span / 2 - 4.0 + 1e-6
    south = {"a": [10.0, -27.65], "b": [10.0, -80.0], "width": 8.0, "sidewalk": 2.0}
    placed2, _ = _terrace(roads=(THROUGH, south))
    band = (10.0 - (4.0 + 2.0 + 2.0), 10.0 + (4.0 + 2.0 + 2.0))
    assert not [p for p in placed2 if not (p["at"][0] + p["size_x"] / 2 <= band[0]
                                           or p["at"][0] - p["size_x"] / 2 >= band[1])]
    assert len(placed2) < len(placed)


def test_the_same_seed_builds_the_same_row():
    assert _terrace(seed=5) == _terrace(seed=5)
    assert _terrace(seed=5) != _terrace(seed=6)


def test_a_brief_asks_for_empties_and_its_signature_says_so_only_then(tmp_path):
    lib = tmp_path / "build"
    lib.mkdir()
    for aid, facade in (("gs_empty_rowhome_a", True), ("gs_facade_rowhome", True),
                        ("gs_empty_rowhome_x", False)):
        for suf in (".glb", ".gameplay.json", ".slots.json"):
            (lib / f"{aid}{suf}").write_text("{}", encoding="utf-8")
        (lib / f"{aid}.validation.json").write_text(json.dumps({"facade": facade}), encoding="utf-8")
    plain = MissionBrief(mission_id="m", display_name="m", lot_library=str(lib), building_count=3)
    asked = MissionBrief(mission_id="m", display_name="m", lot_library=str(lib), building_count=3, empties="across")
    assert building_library.empties_for_brief(plain) == []
    # only the prefixed shell Deli Counter calls a facade
    assert [r["id"] for r in building_library.empties_for_brief(asked)] == ["gs_empty_rowhome_a"]
    assert "empties" not in plain.functional_signature()
    assert asked.functional_signature()["empties"] == "across"


def test_the_planner_themes_an_empty_without_fixtures():
    src = Path(__file__).resolve().parents[2] / "packages" / "pipeline" / "planner.py"
    text = src.read_text(encoding="utf-8")
    block = text[text.index("THE EMPTIES (0.137.0)"):text.index("# Named before the fixtures jobs")]
    for stage in ("_STAGE_ZOO_KIT", "_STAGE_PATINA_BASE", "_STAGE_PATINA_DRESS", "_STAGE_ZOO_DRESS"):
        assert stage in block
    assert "_STAGE_ZOO_FIXTURES" not in block and "require_art_inputs" not in block.split("#")[-1]
