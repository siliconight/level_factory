"""The enemy sights from the contract's body too (the factory's roadmap 292).

`adapters/laser_tag` writes the contract's body into every run's scenario
(roadmap 123), and until 0.231.0 it wrote only the player's: the scenario's
`enemy_eye_height_m` went out at `_STOCK_SCENARIO`'s 1.6 whatever the contract
said. The contract says its NPCs share the player's metrics until a distinct
class ships, and Laser Tag has built every enemy's capsule, mesh and agent from
the crew's body since its 0.26.0 -- so a studio stating a 2.05 m character
fielded 2.05 m enemies sighting from 1.6 m, and the evaluator's lines crossed
at 1.42 m where the body's own cross at 1.5.

The enemy's eye is `characters.npc_standard`'s now, and the player's where that
block states none.

THE TEST THAT MATTERS IS `test_a_studio_states_its_body_once_and_both_sides_take_it`.
"""
import json
from pathlib import Path

import pytest

from adapters import laser_tag
from packages.validation import agent_contract, lasertag_contract
from tests.siblings import not_found, sibling_repo

#: A 2.05 m character: the eye at 0.9 of stature, the chest inside the capsule.
TALL = {"radius_m": 0.45, "height_m": 2.05, "eye_height_m": 1.85,
        "chest_height_m": 1.15, "walk_speed_mps": 3.2}


def _contract(root: Path, npc: dict | None = None, **player) -> Path:
    body = {"radius_m": 0.35, "height_m": 1.8, "eye_height_m": 1.6,
            "chest_height_m": 1.0, "walk_speed_mps": 4.0}
    body.update(player)
    characters = {"player": body}
    if npc is not None:
        characters["npc_standard"] = npc
    root.mkdir(parents=True, exist_ok=True)
    (root / "agent_contract.json").write_text(
        json.dumps({"characters": characters}), encoding="utf-8")
    return root


def _staged(root: Path) -> Path:
    """A project with the addon script present, which `_write_scenario` requires."""
    script = root / "addons" / "laser_tag_tool" / "resources"
    script.mkdir(parents=True)
    (script / "LT_TestScenario.gd").write_text("# stub", encoding="utf-8")
    return root


def test_a_studio_states_its_body_once_and_both_sides_take_it(tmp_path):
    """THE POINT OF THE ITEM. One stated body and an NPC stating nothing of its
    own: the crew and the enemy both sight from 1.85 m, in the scenario the run
    writes and in the engagement the advisory is handed, and the evaluator's
    lines cross where the body's own do."""
    dc = _contract(tmp_path / "dc", npc={"note": "shares the player's"}, **TALL)
    merged, drift = laser_tag._run_scenario(
        {}, {"repositories": {"deli_counter": str(dc)}})
    assert merged["player_eye_height_m"] == 1.85
    assert merged["enemy_eye_height_m"] == 1.85
    assert any(line.startswith("enemy_eye_height_m:") for line in drift), drift
    project = _staged(tmp_path / "proj")
    laser_tag._write_scenario(project, merged)
    tres = (project / "mission_scenario.tres").read_text(encoding="utf-8")
    assert "player_eye_height_m = 1.85" in tres
    assert "enemy_eye_height_m = 1.85" in tres
    run = laser_tag._run_engagement(lasertag_contract.MEASURED, merged)
    assert (run.crew_eye, run.enemy_eye) == (1.85, 1.85)
    assert abs(run.cover_break_height - (1.85 + 1.15) / 2.0) < 1e-9


def test_a_contract_with_no_npc_block_shares_the_player_s_eye(tmp_path):
    body = agent_contract.read_player_body(_contract(tmp_path, **TALL))
    assert body["enemy_eye_height_m"] == body["player_eye_height_m"] == 1.85


def test_a_distinct_class_states_its_own_eye(tmp_path):
    """An NPC block stating an eye is a distinct class, and the eye is its own.
    The run then has two, which the advisory says (`LT_SIGHT_ONE_EYE`)."""
    body = agent_contract.read_player_body(
        _contract(tmp_path, npc={"eye_height_m": 1.7}, **TALL))
    assert body["player_eye_height_m"] == 1.85
    assert body["enemy_eye_height_m"] == 1.7


def test_a_nonsense_npc_eye_is_dropped_rather_than_replaced(tmp_path):
    """What the NPC states is its own, so a nonsense eye is dropped -- the run
    keeps Laser Tag's -- rather than quietly swapped for the player's."""
    body = agent_contract.read_player_body(
        _contract(tmp_path, npc={"eye_height_m": "tall"}, **TALL))
    assert "enemy_eye_height_m" not in body
    assert body["player_eye_height_m"] == 1.85


def test_a_brief_s_scenario_still_beats_the_contract(tmp_path):
    """Precedence is stock <- contract <- this job's scenario, for the enemy's
    eye as for the player's."""
    dc = _contract(tmp_path / "dc", **TALL)
    merged, _ = laser_tag._run_scenario(
        {"scenario": {"enemy_eye_height_m": 1.6}},
        {"repositories": {"deli_counter": str(dc)}})
    assert merged["enemy_eye_height_m"] == 1.6
    assert merged["player_eye_height_m"] == 1.85


def test_the_shipped_contract_fields_one_eye_on_both_sides():
    """The Deli Counter beside this checkout, not a fixture: its NPC states no
    eye of its own, so a run fields one eye on both sides. Skipped when the
    sibling checkout is absent."""
    dc = sibling_repo("deli_counter", marker="agent_contract.json")
    if dc is None:
        pytest.skip(not_found("deli_counter", marker="agent_contract.json"))
    body = agent_contract.read_player_body(dc)
    assert body["enemy_eye_height_m"] == body["player_eye_height_m"]
