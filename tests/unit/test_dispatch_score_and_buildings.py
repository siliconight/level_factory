"""0.158.0 -- the package marks the score, names each anchor's building, and
carries no anchor from a building that is not there (roadmap 204).

Found on cold run 9194's package and measured again on 9191's and 9200's:
- **The generated shell's anchors were wrong either way.** The staging
  handed Dispatch the mission's generated Deli Counter shell's anchors
  beside Lot's, in the shell's own frame.
  - On a library lot the shell is never placed, so they were the anchors of
    a building that is not in the level, listed first.
  - On deli_001 (cold run 9191), where the shell IS placed, as b0 at (6, 0),
    all 85 duplicated Lot's b0 anchors by name, 6 m off.
- **No objective was marked** as the score: every anchor carried
  `"objective": ""`.
- **No anchor named its building:** every anchor carried
  `"source_building": ""`, though Lot namespaces each marker by building.

The sites here are built so each claim can fail. Their instruments are the
tests' own: the staged anchors are read from the files the staging writes.
"""
import json

from packages.staging.dispatch_inputs import mission_flow, stage_dispatch_inputs

DC = {"up_axis": "z",
      "markers": [{"id": "OBJECTIVE_CRACK_VAULT", "type": "objective", "x": 4.5, "y": -2.25, "z": -3.1},
                  {"id": "A", "type": "crew_spawn", "x": -2.0, "y": -14.0, "z": 0.0}]}
LOT = {"up_axis": "z",
       "markers": [{"id": "A", "type": "objective", "building": "b0", "x": -54.0, "y": 12.0, "z": -3.9},
                   {"id": "A", "type": "objective", "building": "b1", "x": 18.6, "y": 10.0, "z": 4.2},
                   {"id": "MAIN_W", "type": "door", "building": "b0", "x": -2.4, "y": -13.0, "z": 0.0}],
       "site_markers": [{"type": "crew_spawn", "at": [-4.15, -14.95], "source": "getaway_van"},
                        {"type": "extraction", "at": [-4.15, -14.95], "source": "getaway_van",
                         "getaway": "step_van"}]}


def _stage(tmp_path, lot=LOT, site=None):
    deli = tmp_path / "shell.gameplay.json"
    deli.write_text(json.dumps(DC), encoding="utf-8")
    gp = tmp_path / "site.site.gameplay.json"
    gp.write_text(json.dumps(lot), encoding="utf-8")
    drawn = None
    if site is not None:
        drawn = tmp_path / "site.site.drawn.json"
        drawn.write_text(json.dumps(site), encoding="utf-8")
    stage = tmp_path / "stage"
    stage_dispatch_inputs(stage, deli_gameplay=deli, shell_glb=tmp_path / "shell.glb",
                          lot_gameplay=gp, mission_id="m", lot_site=drawn)
    read = lambda p: json.loads((stage / p).read_text(encoding="utf-8"))  # noqa: E731
    return stage, read("deli_counter/shell.gameplay.json"), read("lot/lot.gameplay.json")


def test_no_anchor_from_the_generated_shell_when_the_site_carries_its_buildings(tmp_path):
    _stage_dir, dc, _lot = _stage(tmp_path, site={"objective": "b0"})
    assert dc["anchors"] == []
    assert dc["interactives"] == [] and dc["ladders"] == []


def test_each_anchor_names_its_building(tmp_path):
    _stage_dir, _dc, lot = _stage(tmp_path, site={"objective": "b0"})
    by_id = {a["id"]: a for a in lot["anchors"]}
    assert by_id["lot:MAIN_W"]["building"] == "b0"
    assert sorted(a["building"] for a in lot["anchors"] if a["type"] == "objective") == ["b0", "b1"]


def test_the_score_is_the_objective_buildings_objective(tmp_path):
    _stage_dir, _dc, lot = _stage(tmp_path, site={"objective": "b0"})
    scored = [a for a in lot["anchors"] if "score" in (a.get("tags") or [])]
    assert len(scored) == 1 and scored[0]["building"] == "b0" and scored[0]["type"] == "objective"


def test_the_flow_goes_spawn_score_extract(tmp_path):
    stage, _dc, _lot = _stage(tmp_path, site={"objective": "b0"})
    assert mission_flow(stage) == [{"step": "spawn", "location_tag": "mission_start"},
                                   {"step": "score", "objective": "score"},
                                   {"step": "extract", "location_tag": "extraction"}]


def test_no_site_spec_no_score_and_the_old_flow(tmp_path):
    """Nothing says which building is the score: nothing is tagged, and the
    flow is the two beats it always was -- a beat that binds to no anchor is
    a Dispatch blocker."""
    stage, _dc, lot = _stage(tmp_path)
    assert not [a for a in lot["anchors"] if "score" in (a.get("tags") or [])]
    assert mission_flow(stage) == [{"step": "spawn", "location_tag": "mission_start"},
                                   {"step": "extract", "location_tag": "extraction"}]


def test_a_site_with_no_markers_still_stages_the_shell(tmp_path):
    """No Lot markers to stand in for them: the shell's anchors are staged
    as before."""
    _stage_dir, dc, _lot = _stage(tmp_path, lot={"up_axis": "z", "markers": []})
    assert {a["id"] for a in dc["anchors"]} == {"deli_counter:OBJECTIVE_CRACK_VAULT", "deli_counter:A"}
