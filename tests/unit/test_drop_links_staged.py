"""0.216.1 -- the staging carries VERTICAL LINKS, so a declared drop's off-mesh link reaches Dispatch (factory
roadmap 173).

Found by 0.216.0's own drop-edge gate on its first export (the factory's cold run 9320): it refused the package
on 20 undeclared rows at deli_a01's floor hole. The chain, traced:

    deli_counter/build/deli_a01.gameplay.json        vertical_links: a floor_hole's and a hatch's nav_link
    lot_assemble .../out/site.site.gameplay.json     the same, the nav links in site space (Lot 0.125.0)
    dispatch_inputs/lot/lot.gameplay.json            no `vertical_links` key at all
    navigation_hints.json                            links: the two ladders' only

`stage_dispatch_inputs` projects each gameplay manifest into a whitelist of keys, and a key the whitelist does
not name is dropped exactly as if upstream never sent it -- the ladders' failure twice (roadmap 172, cold runs
9075 and 9076), one record over.

Run: python -m pytest -q tests/unit/test_drop_links_staged.py
"""
import json

from packages.staging.dispatch_inputs import stage_dispatch_inputs

#: What Dispatch 0.5.3's two importers read off a gameplay manifest (`dispatch/importers/lot.py`,
#: `dispatch/importers/deli_counter.py`). A key Dispatch learns to read and this staging does not write is the
#: next silent drop, so the list is the contract: change it when Dispatch's importers change.
DISPATCH_READS = {"up_axis", "anchors", "props", "interactives", "ladders", "vertical_links"}

#: deli_a01's three vertical links as Lot 0.125.0 wrote them into cold run 9320's site (seed 9104): a
#: descriptive stair link, and a floor hole's and a hatch's, each with its one-way nav link in site space.
VERTICAL_LINKS = [
    {"kind": "stair", "role": "main_internal_rotation", "from_story": -1, "to_story": 2, "story": None,
     "x": None, "y": None, "breachable": None, "building": "b0"},
    {"kind": "floor_hole", "role": "vertical_attack_angle", "from_story": None, "to_story": None, "story": 1,
     "x": 8.0, "y": -4.0, "breachable": None, "building": "b0",
     "nav_link": {"id": "deli_a01_floor_hole_1_8_-4_navlink", "start_position": [-43.0, -1.49, 3.3],
                  "end_position": [-43.0, -1.49, 0.0], "bidirectional": False, "cost": 4.0,
                  "agent_types": ["player", "ai_humanoid"], "required_capability": "drop",
                  "access_state": "open", "reservation_state": "free",
                  "hole": [[-44.1, -2.59], [-41.9, -0.39]]}},
    {"kind": "hatch", "role": "roof_drop_to_stair", "from_story": None, "to_story": None, "story": 1,
     "x": -12.0, "y": 8.0, "breachable": True, "building": "b0",
     "nav_link": {"id": "deli_a01_hatch_1_-12_8_navlink", "start_position": [-63.0, 10.51, 3.3],
                  "end_position": [-63.0, 10.51, 0.0], "bidirectional": False, "cost": 4.0,
                  "agent_types": ["player", "ai_humanoid"], "required_capability": "drop",
                  "access_state": "open", "reservation_state": "free",
                  "hole": [[-63.7, 9.81], [-62.3, 11.21]]}},
]
MARKERS = [{"id": "MAIN_W", "type": "door", "building": "b0", "x": -2.4, "y": -13.0, "z": 0.0}]


def _stage(tmp_path, dc, lot):
    deli = tmp_path / "shell.gameplay.json"
    deli.write_text(json.dumps(dc), encoding="utf-8")
    gp = tmp_path / "site.site.gameplay.json"
    gp.write_text(json.dumps(lot), encoding="utf-8")
    stage = tmp_path / "stage"
    stage_dispatch_inputs(stage, deli_gameplay=deli, shell_glb=tmp_path / "shell.glb",
                          lot_gameplay=gp, mission_id="m")
    read = lambda p: json.loads((stage / p).read_text(encoding="utf-8"))  # noqa: E731
    return read("deli_counter/shell.gameplay.json"), read("lot/lot.gameplay.json")


def test_the_sites_vertical_links_reach_dispatchs_lot_input(tmp_path):
    _dc, lot = _stage(tmp_path, {"up_axis": "z"},
                      {"up_axis": "z", "markers": MARKERS, "vertical_links": VERTICAL_LINKS})
    assert lot["vertical_links"] == VERTICAL_LINKS
    drops = [v["nav_link"]["id"] for v in lot["vertical_links"] if "nav_link" in v]
    assert drops == ["deli_a01_floor_hole_1_8_-4_navlink", "deli_a01_hatch_1_-12_8_navlink"]


def test_a_lone_shells_vertical_links_reach_dispatchs_deli_input(tmp_path):
    # a site with no markers to stand in for the shell: the shell side is staged, and its links with it
    dc, _lot = _stage(tmp_path, {"up_axis": "z", "vertical_links": VERTICAL_LINKS}, {"up_axis": "z"})
    assert dc["vertical_links"] == VERTICAL_LINKS


def test_a_site_that_carries_its_buildings_stages_none_from_the_generated_shell(tmp_path):
    # the anchors' rule (0.158.0): the shell's records, in the shell's own frame, would duplicate the site's
    dc, lot = _stage(tmp_path, {"up_axis": "z", "vertical_links": VERTICAL_LINKS},
                     {"up_axis": "z", "markers": MARKERS, "vertical_links": VERTICAL_LINKS})
    assert dc["vertical_links"] == [] and lot["vertical_links"] == VERTICAL_LINKS


def test_the_staged_manifests_carry_every_key_dispatch_reads(tmp_path):
    dc, lot = _stage(tmp_path, {"up_axis": "z"}, {"up_axis": "z", "markers": MARKERS})
    assert DISPATCH_READS <= set(dc), sorted(DISPATCH_READS - set(dc))
    assert DISPATCH_READS <= set(lot), sorted(DISPATCH_READS - set(lot))
