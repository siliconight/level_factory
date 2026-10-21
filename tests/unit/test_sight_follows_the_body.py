"""The sightline advisory sights from the body the run fields (roadmap 289).

Level Factory 0.229.0 moved the advisory's eye from a stale 1.4 m to Laser
Tag's 1.6 and held it there with the check Lot's copies answer to. That made
the number right and left the rule broken: a body-derived height is read
through `agent_contract.json`, never kept as a literal beside a comment naming
it. A studio stating a 2.05 m character got a run whose crew sights from
1.85 m and an advisory still crossing at 1.3 m -- calling a 1.4 m crate cover
when both sides see over it.

The Laser Tag adapter is the seam: it writes the contract's body into the
run's scenario (`_run_scenario`), and now hands the advisory the same heights
(`_run_engagement`). The street below is 92 m long with a 1.4 m crate across
its middle. The stock body's lines cross at 1.3 m, under the crate's top; a
1.85 m eye aimed at 1.15 m crosses at 1.5 m, over it.

THE TEST THAT MATTERS IS
`test_a_studio_states_its_body_once_and_the_advisory_sights_from_it`.
"""
import dataclasses
import json
from pathlib import Path

from adapters import laser_tag
from packages.validation import lasertag_contract, sightlines
from packages.validation.ground_contact import Box

#: The codes as strings rather than through `tactical`, so a version without
#: this change fails on what the advisory said rather than on a missing name.
OPEN = "LT_OPEN_SIGHTLINE"
ONE_EYE = "LT_SIGHT_ONE_EYE"

#: A 2.05 m character: the eye at 0.9 of stature, the chest inside the capsule.
TALL = {"height_m": 2.05, "eye_height_m": 1.85, "chest_height_m": 1.15}


def _street(tmp_path: Path, crate: float | None = 1.4) -> Path:
    """92 m of street, the crew at one end and an enemy at the other, and a
    crate ``crate`` metres tall across the middle (none for ``None``). On
    disk, because the advisory reads its scene the way a run stages it."""
    lines = ["[gd_scene load_steps=3 format=3]", "",
             '[sub_resource type="BoxShape3D" id="street"]',
             "size = Vector3(240, 0.5, 60)", ""]
    if crate is not None:
        lines += ['[sub_resource type="BoxShape3D" id="crate"]',
                  f"size = Vector3(0.6, {crate:g}, 6)", ""]
    lines += ['[node name="site_walk" type="Node3D"]', ""]

    def node(name, kind, parent, x, y, z):
        lines.extend([
            f'[node name="{name}" type="{kind}" parent="{parent}"]',
            "transform = Transform3D(1, 0, 0, 0, 1, 0, 0, 0, 1, "
            f"{x:g}, {y:g}, {z:g})", ""])

    def shape(parent, sub):
        lines.extend([
            f'[node name="col" type="CollisionShape3D" parent="{parent}"]',
            f'shape = SubResource("{sub}")', ""])

    node("Street", "StaticBody3D", ".", 0, -0.25, 0)
    shape("Street", "street")
    if crate is not None:
        node("Crate", "StaticBody3D", ".", 0, crate / 2.0, 0)
        shape("Crate", "crate")
    node("LT_PlayerSpawn", "Node3D", ".", -46, 0, 0)
    node("LT_EnemySpawnPoints", "Node3D", ".", 0, 0, 0)
    node("Enemy_0", "Node3D", "LT_EnemySpawnPoints", 46, 0, 0)
    path = tmp_path / "level.tscn"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def _contract(root: Path, **player) -> Path:
    body = {"radius_m": 0.35, "height_m": 1.8, "eye_height_m": 1.6,
            "chest_height_m": 1.0, "walk_speed_mps": 4.0}
    body.update(player)
    root.mkdir(parents=True, exist_ok=True)
    (root / "agent_contract.json").write_text(
        json.dumps({"characters": {"player": body}}), encoding="utf-8")
    return root


def _advise(scene: Path, contract: Path | None = None,
            scenario=None) -> list[dict]:
    """The adapter's advisory pass as the scheduler asks it, with no Laser Tag
    checkout, so the evaluator's own numbers are `lasertag_contract.MEASURED`.
    """
    job = {"evaluation_scene": str(scene)}
    if scenario is not None:
        job["scenario"] = scenario
    context = {"repository": None,
               "repositories": ({"deli_counter": str(contract)}
                                if contract else {})}
    return list(laser_tag.LaserTagAdapter().advise_configuration(job, context))


def _codes(findings) -> list[str]:
    return [f["code"] for f in findings]


# ---- the advisory, through the adapter -------------------------------------

def test_without_the_crate_the_street_is_one_open_sightline(tmp_path):
    """The control: the advisory reports this street at all, so the crate's
    silence below is the crate's doing and not the instrument's."""
    findings = _advise(_street(tmp_path, crate=None))
    assert _codes(findings).count(OPEN) == 1, _codes(findings)


def test_the_crate_is_cover_for_the_stock_body(tmp_path):
    """The contract's own body crosses at 1.3 m, under the crate's 1.4 m top,
    and both sides sight from one height, so nothing is said about it."""
    findings = _advise(_street(tmp_path), contract=_contract(tmp_path / "dc"))
    assert OPEN not in _codes(findings), findings
    assert ONE_EYE not in _codes(findings), findings


def test_a_studio_states_its_body_once_and_the_advisory_sights_from_it(
        tmp_path):
    """THE POINT OF THE CHANGE. The same crate, the contract stating a 2.05 m
    character: its lines cross at 1.5 m, so a crate both sides see over is not
    cover. Until 0.230.0 the advisory crossed at 1.3 m whatever the contract
    said, and called it cover."""
    findings = _advise(_street(tmp_path),
                       contract=_contract(tmp_path / "dc", **TALL))
    line = [f for f in findings if f["code"] == OPEN]
    assert len(line) == 1, _codes(findings)
    assert "92.0 m of open ground" in line[0]["message"]


def test_a_brief_s_scenario_beats_the_contract_here_too(tmp_path):
    """Precedence is stock <- contract <- this job's scenario, for the advisory
    as for the run: a brief asking for a taller body is asking on purpose."""
    findings = _advise(_street(tmp_path), contract=_contract(tmp_path / "dc"),
                       scenario={"player_eye_height_m": 1.85,
                                 "enemy_eye_height_m": 1.85,
                                 "aim_height_m": 1.15})
    assert OPEN in _codes(findings), findings
    assert ONE_EYE not in _codes(findings), findings


def test_no_contract_leaves_laser_tag_s_own_heights(tmp_path):
    """No Deli Counter checkout: the stock body, which the run would field."""
    findings = _advise(_street(tmp_path))
    assert OPEN not in _codes(findings), findings
    assert ONE_EYE not in _codes(findings), findings


def test_two_eyes_are_named_rather_than_averaged(tmp_path):
    """The seam moves the crew's eye to the contract's and leaves the enemy's
    at Laser Tag's 1.6, while the advisory draws both lines from one eye. It is
    said beside the findings, with the evaluator's own crossing against the
    advisory's, rather than read as a measurement of the run."""
    findings = _advise(_street(tmp_path),
                       contract=_contract(tmp_path / "dc", **TALL))
    note = [f for f in findings if f["code"] == ONE_EYE]
    assert len(note) == 1, _codes(findings)
    assert note[0]["blocking"] is False
    real = dataclasses.replace(lasertag_contract.MEASURED, crew_eye=1.85,
                               aim_height=1.15).cover_break_height
    message = note[0]["message"]
    assert "crew sights from 1.85 m and its enemy from 1.6 m" in message
    assert "cross at 1.5 m" in message
    assert f"evaluator's at {real:g} m" in message, message


def test_a_height_that_is_not_a_number_does_not_stop_the_advisory(tmp_path):
    """A brief writing "tall" for an eye height is wrong, and the advisory is
    never the reason a level does not exist: it sights from Laser Tag's own."""
    findings = _advise(_street(tmp_path),
                       scenario={"player_eye_height_m": "tall"})
    assert OPEN not in _codes(findings), findings


# ---- the parts -------------------------------------------------------------

def test_the_geometry_takes_a_body():
    """`sightlines` itself: the crossing follows the body, and so do the lines
    drawn from it and the interval where a solid breaks them."""
    tall = sightlines.Sight(1.85, 1.15)
    assert sightlines.STOCK.cover_break == sightlines.MIN_COVER_HEIGHT == 1.3
    assert abs(tall.cover_break - 1.5) < 1e-9
    crate = Box("crate", (0.0, 0.7, 0.0), (0.6, 1.4, 6.0))
    points = {"LT_PlayerSpawn": (-46.0, 0.0, 0.0), "Enemy_0": (46.0, 0.0, 0.0)}
    assert sightlines.open_sightlines(points, [crate], limit=45.0) == []
    lines = sightlines.open_sightlines(points, [crate], limit=45.0, sight=tall)
    assert len(lines) == 1
    # a 1.4 m solid stops the stock body over part of the line, the tall one
    # nowhere: its minimum is its own crossing
    assert sightlines.break_interval(lines[0], 1.4) is not None
    assert sightlines.break_interval(lines[0], 1.4, sight=tall) is None


def test_the_run_and_the_advisory_ask_one_precedence(tmp_path):
    """`_run_scenario` is what `run` writes and what the advisory reads: the
    scenario it returns, written out, carries the heights the engagement is
    given, and the ranges stay the evaluator's."""
    job = {"scenario": {"aim_height_m": 1.2}}
    context = {"repositories": {
        "deli_counter": str(_contract(tmp_path / "dc", **TALL))}}
    merged, drift = laser_tag._run_scenario(job, context)
    assert merged["player_eye_height_m"] == 1.85
    assert merged["aim_height_m"] == 1.2
    assert drift, "a body unlike the stock one says so out loud"
    project = tmp_path / "proj"
    script = project / "addons" / "laser_tag_tool" / "resources"
    script.mkdir(parents=True)
    (script / "LT_TestScenario.gd").write_text("# stub", encoding="utf-8")
    laser_tag._write_scenario(project, merged)
    tres = (project / "mission_scenario.tres").read_text(encoding="utf-8")
    assert "player_eye_height_m = 1.85" in tres
    assert "aim_height_m = 1.2" in tres
    run = laser_tag._run_engagement(lasertag_contract.MEASURED, merged)
    assert (run.crew_eye, run.enemy_eye, run.aim_height) == (1.85, 1.6, 1.2)
    assert run.opening_range == lasertag_contract.MEASURED.opening_range
