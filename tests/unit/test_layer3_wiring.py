"""Layer 3 surface dressing is PLANNED, not merely built (roadmap 110).

Every stage of the chain existed and was tested by 2026-08-19 -- Lot's
`site_surfaces`, Zoo's clutter species and `measure_shapes`, Patina's
`surface_dressing`, the export's `dressing_scene` -- and the planner
referenced none of it. These tests are about the wiring, which is the part
that was missing: that the three jobs are planned in the art layer with the
right edges, that each adapter turns its job spec into the command the tool
takes, that the spec builder reads the species off the one file that decides
them, and that the export ships the scene -- or says exactly why it did not.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from adapters.lot import LotAdapter  # noqa: E402
from adapters.zoo import ZooAdapter  # noqa: E402
from packages.core.models import MissionBrief  # noqa: E402
from packages.exporting import dressing_layer  # noqa: E402
from packages.exporting.localize import LocalizeReport, write_entry_scene  # noqa: E402
from packages.pipeline.planner import LAYER_ART, plan_mission  # noqa: E402

_SEL = "m1.candidate.seed_1997"


def _brief():
    return MissionBrief(mission_id="m1", display_name="M1",
                        archetype="urban_bank", candidate_count=3)


def _ctx(tmp_path):
    return {"work_dir": str(tmp_path / "work"),
            "repository": str(tmp_path / "repo"),
            "python_executable": "python", "blender_executable": "blender"}


# --- the planner ------------------------------------------------------------

def test_the_art_layer_plans_the_three_layer3_jobs():
    plan = plan_mission(_brief(), seed_base=1997, layers=frozenset({LAYER_ART}),
                        selected_candidate=_SEL)
    jobs = {j.stage_id: j for j in plan.graph.jobs()}
    for stage, adapter in (("zoo_clutter_build", "zoo"),
                           ("lot_site_surfaces", "lot"),
                           ("patina_surface_dressing", "patina")):
        assert stage in jobs, stage
        assert jobs[stage].adapter_id == adapter
        assert jobs[stage].candidate_id == _SEL


def test_the_dressing_joins_clutter_surfaces_and_the_themed_assembly():
    plan = plan_mission(_brief(), seed_base=1997, layers=frozenset({LAYER_ART}),
                        selected_candidate=_SEL)
    jobs = {j.stage_id: j for j in plan.graph.jobs()}
    dress = jobs["patina_surface_dressing"]
    assert set(dress.depends_on) == {jobs["zoo_clutter_build"].job_id,
                                     jobs["lot_site_surfaces"].job_id,
                                     jobs["themed_site_assemble"].job_id}
    # Clutter and surfaces need only the locked candidate's assembly.
    lot_jid = f"{_SEL.split('.candidate')[0]}.lot_assemble.candidate.seed_1997"
    assert jobs["zoo_clutter_build"].depends_on == [lot_jid]
    assert jobs["lot_site_surfaces"].depends_on == [lot_jid]
    assert dress.expected_outputs == ["m1.surface_dressing.json"]
    assert jobs["zoo_clutter_build"].expected_outputs == ["shapes.metrics.json"]
    assert jobs["lot_site_surfaces"].expected_outputs == ["surfaces.json"]


def test_no_layer3_without_the_art_layer():
    plan = plan_mission(_brief(), seed_base=1997, selected_candidate=_SEL)
    stages = {j.stage_id for j in plan.graph.jobs()}
    assert not stages & {"zoo_clutter_build", "lot_site_surfaces",
                         "patina_surface_dressing"}


# --- the adapters -----------------------------------------------------------

def test_zoo_habitat_mode_builds_the_named_species_without_collision(tmp_path):
    spec = {"mode": "habitat", "habitat": "pebble,weed_tuft", "theme": "delco",
            "seed": 7, "measure_shapes": True,
            "metrics_name": "shapes.metrics.json"}
    cmds = ZooAdapter().plan_commands(spec, _ctx(tmp_path))
    assert len(cmds) == 2, "the build, then the measurement"
    build = cmds[0].arguments
    assert "--habitat" in build and build[build.index("--habitat") + 1] == "pebble,weed_tuft"
    assert "--no-collision" in build, "dressing carries collision_policy none"
    assert "--prompt" in build and build[build.index("--prompt") + 1] == "delco"
    assert "--seed" in build and build[build.index("--seed") + 1] == "7"
    assert cmds[0].resource_class == "blender"
    assert cmds[1].expected_outputs == ("shapes.metrics.json",)


def test_zoo_habitat_mode_refuses_an_empty_species_list(tmp_path):
    problems = ZooAdapter().validate_configuration(
        {"mode": "habitat", "habitat": ""}, _ctx(tmp_path))
    assert problems and "habitat" in problems[0]


def test_the_species_list_is_in_the_zoo_fingerprint(tmp_path):
    a = ZooAdapter().fingerprint_inputs({"mode": "habitat", "habitat": "pebble"},
                                        _ctx(tmp_path))
    b = ZooAdapter().fingerprint_inputs({"mode": "habitat", "habitat": "pebble,weed_tuft"},
                                        _ctx(tmp_path))
    assert a != b


def test_a_failed_clutter_species_is_a_finding(tmp_path):
    idx = tmp_path / "abc123.habitat.json"
    idx.write_text(json.dumps({"members": [
        {"species": "pebble", "status": "pass", "files": {"glb": "pebble_1.glb"}},
        {"species": "weed_tuft", "status": "fail", "files": {}}]}),
        encoding="utf-8")
    issues = ZooAdapter().normalize_validation([idx])
    codes = [i["code"] for i in issues]
    assert codes == ["ZOO_PARTIAL_BUILD"]
    assert "weed_tuft" in issues[0]["message"]
    assert issues[0]["blocking"] is False


def test_lot_surfaces_mode_runs_site_surfaces_strictly(tmp_path):
    spec_path = tmp_path / "site.json"
    spec_path.write_text("{}", encoding="utf-8")
    base = tmp_path / "lot_out"
    base.mkdir()
    spec = {"mode": "surfaces", "site_spec_path": str(spec_path),
            "base_dir": str(base)}
    assert LotAdapter().validate_configuration(spec, _ctx(tmp_path)) == []
    cmds = LotAdapter().plan_commands(spec, _ctx(tmp_path))
    assert len(cmds) == 1
    args = cmds[0].arguments
    assert args[0].endswith("site_surfaces.py")
    assert args[1] == str(spec_path)
    assert "--base-dir" in args and args[args.index("--base-dir") + 1] == str(base)
    assert "--strict" in args
    assert cmds[0].expected_outputs == ("surfaces.json",)


def test_lot_surfaces_mode_requires_a_base_dir(tmp_path):
    spec_path = tmp_path / "site.json"
    spec_path.write_text("{}", encoding="utf-8")
    problems = LotAdapter().validate_configuration(
        {"mode": "surfaces", "site_spec_path": str(spec_path)}, _ctx(tmp_path))
    assert any("base_dir" in p for p in problems)


def test_lot_modes_fingerprint_differently(tmp_path):
    spec_path = tmp_path / "site.json"
    spec_path.write_text("{}", encoding="utf-8")
    a = LotAdapter().fingerprint_inputs({"site_spec_path": str(spec_path)}, _ctx(tmp_path))
    b = LotAdapter().fingerprint_inputs({"site_spec_path": str(spec_path),
                                         "mode": "surfaces"}, _ctx(tmp_path))
    assert a != b


# --- the spec builder reads the one file that decides the species ----------

def test_clutter_species_come_from_patinas_asset_set_file(tmp_path):
    from apps.cli.commands import _clutter_asset_sets, _clutter_species
    repo = tmp_path / "patina"
    sets = repo / "patina" / "asset_sets"
    sets.mkdir(parents=True)
    (sets / "ground_clutter.json").write_text(json.dumps({
        "asset_sets": {"weed_tuft": "ground_cover", "pebble": "ground_clutter"}}),
        encoding="utf-8")
    path = _clutter_asset_sets({"patina": str(repo)})
    assert path == sets / "ground_clutter.json"
    assert _clutter_species(path) == ["pebble", "weed_tuft"]


def test_a_missing_asset_set_file_plans_a_refusal_not_a_crash(tmp_path, capsys):
    from apps.cli.commands import _clutter_species
    assert _clutter_species(tmp_path / "nope.json") == []
    assert "not readable" in capsys.readouterr().err


def test_the_tracked_asset_set_file_names_the_four_clutter_species():
    """The real file, in the real Patina checkout beside this repo."""
    path = ROOT.parent / "patina" / "patina" / "asset_sets" / "ground_clutter.json"
    doc = json.loads(path.read_text(encoding="utf-8"))
    assert sorted(doc["asset_sets"]) == ["litter_scrap", "pebble", "rubble_frag",
                                         "weed_tuft"]


# --- the export -------------------------------------------------------------

def _manifest(site_id="m1"):
    # The smallest surface-dressing/1 manifest dressing_scene accepts.
    return {"schema": "surface-dressing/1", "site_id": site_id,
            "source": "site.tscn", "space": "spec/Blender Z-up raw coords",
            "orders": [{"asset_id": "pebble", "collision_policy": "none",
                        "pos": [1.0, 2.0, 0.0], "yaw_deg": 30.0, "scale": 1.0,
                        "height_m": 0.02, "in_traversed_space": False}]}


def test_find_clutter_glbs_reads_the_habitat_index(tmp_path):
    (tmp_path / "pebble_a1b2.glb").write_bytes(b"glb")
    (tmp_path / "weed_tuft_c3d4.glb").write_bytes(b"glb")
    (tmp_path / "h.habitat.json").write_text(json.dumps({"members": [
        {"species": "pebble", "status": "pass", "files": {"glb": "pebble_a1b2.glb"}},
        {"species": "weed_tuft", "status": "fail", "files": {"glb": "weed_tuft_c3d4.glb"}},
    ]}), encoding="utf-8")
    found, missing = dressing_layer.find_clutter_glbs(tmp_path, ["pebble", "weed_tuft", "litter_scrap"])
    assert found == {"pebble": tmp_path / "pebble_a1b2.glb",
                     # a failed member is not listed, the glob finds the file anyway
                     "weed_tuft": tmp_path / "weed_tuft_c3d4.glb"}
    assert missing and missing[0].startswith("litter_scrap:")


def test_without_godot_the_layer_is_reported_not_shipped(tmp_path):
    export_dir = tmp_path / "pkg"
    export_dir.mkdir()
    man = tmp_path / "m1.surface_dressing.json"
    man.write_text(json.dumps(_manifest()), encoding="utf-8")
    clutter = tmp_path / "clutter"
    clutter.mkdir()
    (clutter / "pebble_a1b2.glb").write_bytes(b"glb")
    report = dressing_layer.ship_dressing(export_dir, man, clutter, None,
                                          scratch_root=tmp_path)
    assert report["shipped"] is False
    assert any("godot" in r for r in report["reasons"]), report
    assert not list(export_dir.glob("*_dressing.tscn"))
    written = json.loads((export_dir / "dressing_layer.json").read_text(encoding="utf-8"))
    assert written["shipped"] is False


def test_a_missing_manifest_is_said_in_the_package(tmp_path):
    export_dir = tmp_path / "pkg"
    export_dir.mkdir()
    report = dressing_layer.ship_dressing(export_dir, None, None, None)
    assert report["shipped"] is False
    assert (export_dir / "dressing_layer.json").is_file()


def test_the_entry_scene_instances_the_dressing_beside_the_level(tmp_path):
    (tmp_path / "site.tscn").write_text("[gd_scene]\n", encoding="utf-8")
    (tmp_path / "m1_dressing.tscn").write_text("[gd_scene]\n", encoding="utf-8")
    report = LocalizeReport()
    write_entry_scene(tmp_path, report)
    assert report.entry_instances == ["site.tscn", "m1_dressing.tscn"]
    text = (tmp_path / "mission.tscn").read_text(encoding="utf-8")
    assert "res://m1_dressing.tscn" in text
