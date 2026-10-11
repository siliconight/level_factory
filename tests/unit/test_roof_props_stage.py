"""Roof props reach a level (Level Factory 0.179.0, roadmap 181).

Zoo 0.25's rooftop scatter was planned by nothing: the Zoo adapter's kit branch
read `roof_props_slots`, which no planner wrote, and the one command it would
have built could not have run both (zoo_cli answers --roof-props before
--build-kit and returns). Pure: the fan-out fixtures, the real planner, the
real spec builder, the real adapters. Run against 0.178.6 first: the planner
tests fail with no roof job, the adapter test with an unknown mode.
"""
from __future__ import annotations

import dataclasses
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from adapters.presentation import _circulation_arms
from adapters.zoo import ZooAdapter
from apps.cli.commands import _brief_model
from test_fanout import (LOT, _brief, _compose_args, _flag, _library, _plan,
                         _specs, _stages)

STAGE = "zoo_roof_props_build"


def _ctx(tmp_path: Path) -> dict:
    return {"work_dir": str(tmp_path / "work"), "repository": str(tmp_path / "zoo"),
            "blender_executable": "blender"}


def test_every_enterable_building_gets_its_own_roof_job(tmp_path):
    plan = _plan(_brief(_library(tmp_path / "build")))
    jobs = _stages(plan, STAGE)
    assert len(jobs) == LOT and len({j.archetype_id for j in jobs}) == LOT
    kits = {j.archetype_id for j in _stages(plan, "zoo_kit_build")}
    for job in jobs:
        assert job.adapter_id == "zoo" and job.resource_class == "blender"
        assert job.archetype_id in kits
        assert any(".lot_assemble" in d for d in job.depends_on)
        assert any(".pixelcoat_build" in d for d in job.depends_on)
    compose = _stages(plan, "presentation_compose")[0]
    assert {j.job_id for j in jobs} <= set(compose.depends_on)


def test_a_building_without_a_roof_slot_gets_none(tmp_path):
    lib = _library(tmp_path / "build")
    drawn = _stages(_plan(_brief(lib)), STAGE)[0].archetype_id
    (lib / f"{drawn}.slots.json").write_text(
        json.dumps({"coverage": {"wall": 96, "doorway": 4}, "slots": []}),
        encoding="utf-8")
    plan = _plan(_brief(lib))
    roofs = {j.archetype_id for j in _stages(plan, STAGE)}
    kits = {j.archetype_id for j in _stages(plan, "zoo_kit_build")}
    assert drawn in kits and drawn not in roofs
    assert len(roofs) == LOT - 1


def test_an_empty_gets_a_kit_and_no_roof_job(tmp_path):
    lib = _library(tmp_path / "build")
    aid = "gs_empty_rowhome_t"
    roof = [{"slot_id": "roof_footprint", "role": "roof", "fit": {"dims": [6.0, 12.0, 0.3]}}]
    for suffix, body in ((".glb", "{}"), (".gameplay.json", "{}"),
                         (".slots.json", json.dumps({"coverage": {"wall": 12}, "slots": roof})),
                         (".validation.json", json.dumps({"facade": True}))):
        (lib / f"{aid}{suffix}").write_text(body, encoding="utf-8")
    plan = _plan(_brief(lib))
    assert aid in {j.archetype_id for j in _stages(plan, "zoo_kit_build")}
    assert aid not in {j.archetype_id for j in _stages(plan, STAGE)}


def test_the_brief_can_plan_none(tmp_path):
    brief = dataclasses.replace(_brief(_library(tmp_path / "build")), roof_props=False)
    plan = _plan(brief)
    assert not _stages(plan, STAGE)
    assert len([j for j in _stages(plan, "zoo_kit_build")
                if j.archetype_id != "site"]) == LOT


def test_the_brief_reads_the_key_and_defaults_it_on():
    assert _brief_model({"mission_id": "m", "display_name": "m"}).roof_props is True
    assert _brief_model({"mission_id": "m", "display_name": "m",
                         "roof_props": False}).roof_props is False


def test_each_roof_job_reads_its_own_slots_and_the_skin_library(tmp_path, monkeypatch):
    brief = _brief(_library(tmp_path / "build"))
    plan = _plan(brief)
    specs = _specs(tmp_path, plan, brief, monkeypatch)
    for job in _stages(plan, STAGE):
        spec = specs[job.job_id]
        assert spec["mode"] == "roof_props"
        assert Path(spec["slots_path"]).name == f"{job.archetype_id}.slots.json"
        assert spec["skins_dir"] and spec["theme"] == "delco"


def test_the_adapter_plans_one_blender_command_with_its_own_outputs(tmp_path):
    slots = tmp_path / "deli_a01.slots.json"
    slots.write_text(json.dumps({"building_id": "deli_a01", "slots": []}), encoding="utf-8")
    skins = tmp_path / "skins"
    skins.mkdir()
    spec = {"mode": "roof_props", "slots_path": str(slots), "theme": "delco",
            "seed": 7, "skins_dir": str(skins), "wet": True, "density": 0.8}
    assert ZooAdapter().validate_configuration(spec, _ctx(tmp_path)) == []
    (cmd,) = ZooAdapter().plan_commands(spec, _ctx(tmp_path))
    args = cmd.arguments
    assert _flag(args, "--roof-props") == str(slots)
    assert _flag(args, "--skins") == str(skins) and _flag(args, "--theme") == "delco"
    assert _flag(args, "--seed") == "7" and _flag(args, "--density") == "0.8"
    assert "--wet" in args and "--no-blend" in args and "--build-kit" not in args
    assert cmd.expected_outputs == ("deli_a01_roofprops.built.json",
                                    "deli_a01_roofprops.glb")
    assert cmd.resource_class == "blender"
    bad = dict(spec, slots_path=str(tmp_path / "missing.json"))
    assert ZooAdapter().validate_configuration(bad, _ctx(tmp_path))
    # the density is an input of this job and of no other
    fp = ZooAdapter().fingerprint_inputs(spec, _ctx(tmp_path))
    assert fp["density"] == "0.8"
    assert "density" not in ZooAdapter().fingerprint_inputs(
        dict(spec, mode="kit"), _ctx(tmp_path))


def test_the_kit_command_no_longer_carries_roof_props(tmp_path):
    """The dead branch: `roof_props_slots` on a kit job added --roof-props to
    a command zoo_cli would have answered as a roof props build alone."""
    slots = tmp_path / "deli_a01.slots.json"
    slots.write_text(json.dumps({"building_id": "deli_a01", "slots": []}), encoding="utf-8")
    spec = {"mode": "kit", "slots_path": str(slots), "roof_props_slots": str(slots)}
    cmd = ZooAdapter().plan_commands(spec, _ctx(tmp_path))[0]
    assert "--roof-props" not in cmd.arguments
    assert _flag(cmd.arguments, "--build-kit") == str(slots)


def test_each_building_s_compose_bundles_its_own_roof_props(tmp_path, monkeypatch):
    brief = _brief(_library(tmp_path / "build"))
    plan = _plan(brief)
    specs = _specs(tmp_path, plan, brief, monkeypatch)
    compose = _stages(plan, "presentation_compose")[0]
    paths = [_flag(a, "--roofprops")
             for a in _compose_args(specs[compose.job_id], tmp_path)]
    flagged = [p for p in paths if p]
    # the lot's buildings, each its own; the mission's own shell composes
    # without one in a lot mission, as it has no roof job of its own there
    assert len(flagged) == LOT and len(set(flagged)) == LOT
    for p in flagged:
        assert p.endswith("_roofprops.glb") and f".{STAGE}." in p


def test_the_gate_reads_the_roof_props_arm():
    circ = {"ok": False, "shell": {"ok": True}, "dressing": {"ok": True},
            "roofprops": {"ok": False, "conflicts": [{"prop": "Hvac0"}]}}
    assert [k for k, _ in _circulation_arms(circ)] == ["shell", "dressing", "roofprops"]
