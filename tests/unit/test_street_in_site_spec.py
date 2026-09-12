"""The generated site has a street (roadmap 153).

Measured 2026-09-13: every cold package's spec carried `paths` and no
`roads`, so Lot's road, sidewalk, kerb and crossing machinery had never run
on one. `_street_for` puts one road along the plate's south edge with
sidewalks, a spur from every building to it, and deepens the plate when the
row leaves no room for the band.
"""
import json
from pathlib import Path
from types import SimpleNamespace

import apps.cli.commands as cmds
from packages.core.models import MissionBrief


def test_the_road_runs_south_of_every_building_and_spurs_reach_it():
    buildings = [{"id": "b0", "at": [-49, 5], "rot": 90},
                 {"id": "b1", "at": [3, 10], "rot": 270},
                 {"id": "b2", "at": [46, 5], "rot": 270}]
    fps = [(40, 26), (22, 16), (40, 28)]          # cold run 9021's row
    roads, spurs, span_x, span_y = cmds._street_for(buildings, fps, 165, 69)
    road, cross = roads
    assert road["width"] == 10.0 and road["sidewalk"] == 3.0
    assert road["a"][0] == -82.5 and road["b"][0] == 82.5
    y = road["a"][1]
    assert y == road["b"][1]
    # the row's south faces: b0 -15, b1 -1, b2 -15 (rot swaps the axes)
    south = -15.0
    assert y + cmds.ROAD_WIDTH / 2 + cmds.SIDEWALK_WIDTH + cmds.ROAD_MARGIN <= south + 1e-9
    assert y - cmds.ROAD_WIDTH / 2 - cmds.SIDEWALK_WIDTH >= -span_y / 2 + cmds.ROAD_MARGIN - 1e-9
    assert len(spurs) == 3
    for s, b in zip(spurs, buildings):
        assert s["a"][0] == s["b"][0] == b["at"][0]
        assert s["b"][1] == y and s["a"][1] < b["at"][1]
        assert s["width"] == cmds.SPUR_WIDTH


def test_a_shallow_plate_is_deepened_for_the_band_not_the_road_squeezed():
    buildings = [{"id": "b0", "at": [0, 0], "rot": 0}]
    roads, spurs, span_x, span_y = cmds._street_for(buildings, [(20, 20)], 60, 30)
    # the band needs 20 m below the footprint's south face at -10
    assert span_y >= 2 * (10 + cmds.ROAD_BAND)
    y = roads[0]["a"][1]
    assert y + cmds.ROAD_WIDTH / 2 + cmds.SIDEWALK_WIDTH + cmds.ROAD_MARGIN <= -10 + 1e-9


def test_no_buildings_no_street():
    assert cmds._street_for([], [], 50, 50) == ([], [], 50, 50)


def test_the_cross_street_runs_through_the_widest_gap_that_holds_a_band():
    """Cold run 9021's row: b0 spans x -62..-36, b1 -5..11, b2 32..60 (rot
    swaps the footprint axes): the gaps are 31 m and 21 m, both hold a
    20 m band, and the street takes the wider one, centred at -20.5."""
    buildings = [{"id": "b0", "at": [-49, 5], "rot": 90},
                 {"id": "b1", "at": [3, 10], "rot": 270},
                 {"id": "b2", "at": [46, 5], "rot": 270}]
    fps = [(40, 26), (22, 16), (40, 28)]
    roads, spurs, span_x, span_y = cmds._street_for(buildings, fps, 165, 69)
    road, cross = roads
    assert cross["a"][1] == road["a"][1] and cross["b"][1] == span_y / 2 - cmds.ROAD_MARGIN
    assert cross["a"][0] == cross["b"][0] == -20.5 and span_x == 165
    assert cross["width"] == cmds.ROAD_WIDTH and cross["sidewalk"] == cmds.SIDEWALK_WIDTH
    # a row with no gap that holds a band puts the street past the west
    # end and widens the plate to hold it
    tight = [{"id": "b0", "at": [-15, 0], "rot": 0}, {"id": "b1", "at": [15, 0], "rot": 0}]
    roads, _s, span_x, _y = cmds._street_for(tight, [(20, 20), (20, 20)], 70, 60)
    assert roads[1]["a"][0] == -25 - cmds.ROAD_BAND / 2
    assert span_x >= 2 * (25 + cmds.ROAD_BAND)
    assert roads[0]["a"][0] == -span_x / 2 and roads[0]["b"][0] == span_x / 2


class _Workspace(SimpleNamespace):
    def load_tools_local(self) -> dict:
        return {"repositories": {}}


def test_the_written_spec_carries_the_road_and_the_spurs(tmp_path):
    out = tmp_path / "deli" / "out"
    out.mkdir(parents=True)
    (out / "shell.glb").write_bytes(b"glb")
    (out / "shell.gameplay.json").write_text("{}", encoding="utf-8")
    brief = MissionBrief(mission_id="m", display_name="m", archetype="bank",
                         building_count=3, theme="delco", candidate_count=1,
                         lot_library=None)
    ws = _Workspace(jobs_dir=tmp_path / "jobs", internal_dir=tmp_path / "internal")
    p = cmds._write_site_spec(ws, brief, tmp_path / "deli", seed=9021)
    spec = json.loads(Path(p).read_text(encoding="utf-8"))
    assert len(spec["roads"]) == 2 and spec["roads"][0]["sidewalk"] == 3.0
    assert spec["roads"][1]["a"][1] == spec["roads"][0]["a"][1]      # a T on the road
    assert spec["ground"]["size_x"] >= 2 * abs(spec["roads"][1]["a"][0]) + cmds.ROAD_BAND
    chain = [x for x in spec["paths"] if "from" in x]
    spurs = [x for x in spec["paths"] if "a" in x]
    assert len(chain) == 2 and len(spurs) == 3
    assert all(s["b"][1] == spec["roads"][0]["a"][1] for s in spurs)
