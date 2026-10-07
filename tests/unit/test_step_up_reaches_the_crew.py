"""The contract's step-up reaches Laser Tag's crew (0.154.0, roadmap 203).

`deli_counter/agent_contract.json` gives the player `max_step_up_m` 0.5 and
says a transition above `clearances.unassisted_step_max_m` (0.1025) requires
the consumer's step-up. Laser Tag 0.24.0's crew steps up to its scenario's
`player_max_step_up_m`; this is the seam that fills it from the contract, the
road the radius, height, eye and walk speed already travel (roadmap 123).
Cold run 9194's bank_branch_a04 crew wedged against a 0.118 m stair edge with
no step-up at all.
"""
import json

import pytest

from adapters import laser_tag
from packages.validation import agent_contract
from tests.siblings import not_found, sibling_repo

_CONTRACT = "agent_contract.json"


def _staged(tmp_path):
    """A project with the addon script present, which `_write_scenario` requires."""
    script = tmp_path / "addons" / "laser_tag_tool" / "resources"
    script.mkdir(parents=True)
    (script / "LT_TestScenario.gd").write_text("# stub", encoding="utf-8")
    return tmp_path


def test_the_contracts_step_up_is_read_as_a_body_field(tmp_path):
    (tmp_path / _CONTRACT).write_text(json.dumps(
        {"characters": {"player": {"radius_m": 0.35, "max_step_up_m": 0.5}}}),
        encoding="utf-8")
    assert agent_contract.read_player_body(tmp_path)["player_max_step_up_m"] == 0.5


def test_the_real_contract_gives_half_a_metre():
    dc = sibling_repo("deli_counter", marker=_CONTRACT)
    if dc is None:
        pytest.skip(not_found("deli_counter", marker=_CONTRACT))
    assert agent_contract.read_player_body(dc)["player_max_step_up_m"] == 0.5


def test_the_stock_scenario_carries_it():
    assert laser_tag._STOCK_SCENARIO["player_max_step_up_m"] == 0.5


def test_it_reaches_the_mission_scenario(tmp_path):
    project = _staged(tmp_path)
    assert laser_tag._write_scenario(project, {"player_max_step_up_m": 0.3}) \
        == "res://mission_scenario.tres"
    tres = (project / "mission_scenario.tres").read_text(encoding="utf-8")
    assert "player_max_step_up_m = 0.3" in tres
