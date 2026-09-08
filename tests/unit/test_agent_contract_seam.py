"""The size contract reaches the body that tests it (roadmap 123).

`deli_counter/agent_contract.json` calls itself "THE single source of truth for
character/agent dimensions and every clearance derived from them". Deli Counter
reads it. Laser Tag did not: its evaluation pill was hardcoded in a `.tscn` at
0.40 m wide and 4.5 m/s against the contract's 0.35 and 4.0, so every
door-width test ran against a proxy 14% fatter than the character it stood for
-- the 0.40 being `nav_bake.agent_radius_m`, a BAKE parameter with "fattest
navigating character + 0.05 safety" already folded in.

Laser Tag 0.11.0 made the body settable from the scenario. Level Factory is the
seam that sets it: it already writes `mission_scenario.tres` into the staged
evaluation project, so the numbers cross there without either tool importing or
reading the other at run time.

THE TEST THAT MATTERS IS `test_a_studio_states_its_body_once`. Everything else
here guards the degradation paths.
"""
import json

import pytest

from adapters import laser_tag
from packages.validation import agent_contract


def _contract(tmp_path, **player):
    body = {"radius_m": 0.35, "height_m": 1.8, "eye_height_m": 1.6,
            "walk_speed_mps": 4.0}
    body.update(player)
    (tmp_path / "agent_contract.json").write_text(
        json.dumps({"characters": {"player": body},
                    "nav_bake": {"agent_radius_m": 0.4}}), encoding="utf-8")
    return tmp_path


def _staged(tmp_path):
    """A project with the addon script present, which `_write_scenario` requires."""
    script = tmp_path / "addons" / "laser_tag_tool" / "resources"
    script.mkdir(parents=True)
    (script / "LT_TestScenario.gd").write_text("# stub", encoding="utf-8")
    return tmp_path


# ---- reading ---------------------------------------------------------------

def test_reads_the_players_body_not_the_bakes_radius(tmp_path):
    repo = _contract(tmp_path)
    body = agent_contract.read_player_body(repo)
    assert body["player_radius_m"] == 0.35      # characters.player
    assert body["player_radius_m"] != 0.4       # NOT nav_bake.agent_radius_m
    assert body["player_height_m"] == 1.8
    assert body["player_eye_height_m"] == 1.6
    assert body["player_walk_speed_mps"] == 4.0


@pytest.mark.parametrize("repo", [None, "", "/definitely/not/here"])
def test_a_missing_contract_is_not_an_error(repo):
    """A pre-flight that refuses because a tool moved a file is worse than one
    that degrades -- the same rule `lasertag_contract.read_engagement_from`
    follows."""
    assert agent_contract.read_player_body(repo) is None


def test_malformed_json_degrades(tmp_path):
    (tmp_path / "agent_contract.json").write_text("{not json", encoding="utf-8")
    assert agent_contract.read_player_body(tmp_path) is None


def test_a_contract_without_a_player_degrades(tmp_path):
    (tmp_path / "agent_contract.json").write_text(
        json.dumps({"nav_bake": {"agent_radius_m": 0.4}}), encoding="utf-8")
    assert agent_contract.read_player_body(tmp_path) is None


def test_nonsense_values_are_dropped_rather_than_written(tmp_path):
    repo = _contract(tmp_path, radius_m=0, height_m="tall", walk_speed_mps=-2)
    body = agent_contract.read_player_body(repo)
    assert "player_radius_m" not in body      # 0 is not a body
    assert "player_height_m" not in body      # a string is not metres
    assert "player_walk_speed_mps" not in body
    assert body["player_eye_height_m"] == 1.6  # the sane one still lands


def test_drift_is_reported_rather_than_silently_resolved(tmp_path):
    body = agent_contract.read_player_body(_contract(tmp_path))
    lines = agent_contract.body_drift(
        body, {"player_radius_m": 0.4, "player_walk_speed_mps": 4.5})
    assert len(lines) == 2
    assert all("using the contract" in line for line in lines)
    assert agent_contract.body_drift(body, dict(body)) == []


# ---- the seam --------------------------------------------------------------

def test_the_stock_scenario_carries_a_body_at_all():
    """So a run with no Deli Counter checkout still states a body instead of
    inheriting whatever `LT_PlayerPill.tscn` happens to carry."""
    for key in ("player_radius_m", "player_height_m", "player_eye_height_m",
                "player_walk_speed_mps"):
        assert key in laser_tag._STOCK_SCENARIO


def test_a_studio_states_its_body_once(tmp_path):
    """THE POINT OF THE ITEM. A studio whose characters are 2.05 m tall and
    0.45 m wide says so in `agent_contract.json`, and the pill that proves
    their doors fit is built at 2.05 x 0.45 without touching Laser Tag."""
    (tmp_path / "dc").mkdir()
    repo = _contract(tmp_path / "dc", radius_m=0.45, height_m=2.05,
                     eye_height_m=1.85, walk_speed_mps=3.2)
    body, drift = laser_tag._body_overrides({"repositories": {"deli_counter": repo}})
    assert body["player_radius_m"] == 0.45
    assert body["player_height_m"] == 2.05
    assert drift, "a body unlike the stock one should say so out loud"

    project = _staged(tmp_path / "proj")
    written = laser_tag._write_scenario(project, body)
    assert written == "res://mission_scenario.tres"
    tres = (project / "mission_scenario.tres").read_text(encoding="utf-8")
    assert "player_radius_m = 0.45" in tres
    assert "player_height_m = 2.05" in tres
    assert "player_eye_height_m = 1.85" in tres
    assert "player_walk_speed_mps = 3.2" in tres


def test_an_explicit_scenario_key_still_beats_the_contract(tmp_path):
    """Precedence is stock <- contract <- this job's scenario: a brief asking
    for a different body is asking on purpose."""
    (tmp_path / "dc").mkdir()
    repo = _contract(tmp_path / "dc", radius_m=0.45)
    body, _ = laser_tag._body_overrides({"repositories": {"deli_counter": repo}})
    merged = dict(body)
    merged.update({"player_radius_m": 0.6})
    project = _staged(tmp_path / "proj")
    laser_tag._write_scenario(project, merged)
    tres = (project / "mission_scenario.tres").read_text(encoding="utf-8")
    assert "player_radius_m = 0.6" in tres


def test_no_repository_leaves_the_stock_body(tmp_path):
    body, drift = laser_tag._body_overrides({"repositories": {}})
    assert body == {} and drift == []
    project = _staged(tmp_path)
    laser_tag._write_scenario(project, {})
    tres = (project / "mission_scenario.tres").read_text(encoding="utf-8")
    assert "player_radius_m = 0.35" in tres
