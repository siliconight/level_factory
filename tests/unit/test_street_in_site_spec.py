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
    roads, spurs, span_y = cmds._street_for(buildings, fps, 165, 69)
    (road,) = roads
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
    roads, spurs, span_y = cmds._street_for(buildings, [(20, 20)], 60, 30)
    # the band needs 20 m below the footprint's south face at -10
    assert span_y >= 2 * (10 + cmds.ROAD_BAND)
    y = roads[0]["a"][1]
    assert y + cmds.ROAD_WIDTH / 2 + cmds.SIDEWALK_WIDTH + cmds.ROAD_MARGIN <= -10 + 1e-9


def test_no_buildings_no_street():
    assert cmds._street_for([], [], 50, 50) == ([], [], 50)


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
    assert len(spec["roads"]) == 1 and spec["roads"][0]["sidewalk"] == 3.0
    chain = [x for x in spec["paths"] if "from" in x]
    spurs = [x for x in spec["paths"] if "a" in x]
    assert len(chain) == 2 and len(spurs) == 3
    assert all(s["b"][1] == spec["roads"][0]["a"][1] for s in spurs)
