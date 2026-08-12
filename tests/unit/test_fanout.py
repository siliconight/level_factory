"""Per-building art: the planner fans out and every building keeps its own layers.

Steps 3b/3c/3d of `docs/PER_BUILDING_ART.md`. Pure: a temp directory of empty
files standing in for a Deli Counter build dir, the real planner, the real spec
builder and the real presentation adapter. No Blender, no Godot, no workspace.

THE ASSERTION THAT MATTERS is `test_five_buildings_get_five_distinct_dressings`.
Not "the planner emitted five jobs" -- a per-job count passes while the bug is
fully intact, because the count was never what was wrong. What was wrong is that
five compose invocations were handed the SAME `--dressing` path. So the test
reads the argv the adapter actually plans and asserts the paths are distinct and
that each one came from that building's own job directory.

It was run against the pre-patch tree first and observed to fail with one
distinct dressing path where five were expected. A test that has only ever been
green is decoration; this repo has already paid for that once, when the
buried-treads theory was written, tested for correctness and committed as the
cause before any experiment that could refute it.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from adapters.presentation import PresentationAdapter
from apps.cli import commands as cmds
from packages.core.models import MissionBrief
from packages.pipeline import building_library
from packages.pipeline.planner import LAYER_ART, plan_mission

MISSION = "art_fanout_demo"
SEED_BASE = 5000
LOT = 5

# The archetypes the fake library offers. Distinct families, so `pick_lot` draws
# five different buildings rather than five variants of one.
#: A FIXTURE IS A CLAIM ABOUT THE WORLD, and this one claimed the wrong thing
#: until 2026-08-09. The fifth entry was `lf_lot_demo_001_5017` -- Level
#: Factory's own composed output -- standing in as an ordinary building,
#: because that is what `deli_counter/build/` actually looked like: the
#: pipeline writes its missions into its own source library. The fixture was a
#: faithful copy of the defect, so it agreed with the code and neither said so.
#: `rail_station_a02` is a real authored archetype and keeps the eight distinct
#: families these tests need. See `test_source_library.py`.
ARCHETYPES = ("final_stand", "supermarket_a01", "pharmacy_a02", "depot_a01",
              "rail_station_a02", "cr_deli", "bank_job", "fuel_stop_heist")


def _library(root: Path, ids=ARCHETYPES, *, lights=True,
             themeable=True) -> Path:
    """A stand-in Deli Counter build dir: the suffixes `index` reads.

    THE MANIFESTS CARRY CONTENT, and they did not until 2026-08-08. Every one
    was the literal string `{}` -- no `coverage` in the slot manifest, no
    navgate manifest at all -- which is a faithful stand-in for a library of
    holed, never-judged buildings. That went unnoticed while nothing read
    them; the moment themed selection did, all eight shells were correctly
    judged unfit and thirteen fan-out tests died on a `ThemedShellsUnavailable`
    that was telling the exact truth about this fixture.

    The tests here are about FAN-OUT -- does each building get its own bake,
    its own layer, its own manifest -- so the library they need is one whose
    buildings are ordinary and themeable. `themeable=False` builds the old
    hollow one, for the tests that want a library selection must refuse.
    """
    root.mkdir(parents=True, exist_ok=True)
    for aid in ids:
        (root / f"{aid}.glb").write_text("{}", encoding="utf-8")
        (root / f"{aid}.gameplay.json").write_text("{}", encoding="utf-8")
        # `coverage` is what separates a shell the themed kit fills from one
        # it does not -- pharmacy_a02 (118 wall slots filled) against
        # final_stand ({}, and holes where its walls should be).
        (root / f"{aid}.slots.json").write_text(
            json.dumps({"coverage": {"wall": 96, "doorway": 4}}
                       if themeable else {}), encoding="utf-8")
        # The scoped shape `nav_gate.py` writes: interior counts beside the
        # legacy totals, and one extraction point deferred to site scope
        # because it stands on a street Lot has not laid yet. 99 of the real
        # library's 135 shells look exactly like this.
        (root / f"{aid}.navgate.json").write_text(json.dumps({
            "navigable": True if themeable else False,
            "navigable_reason": (
                "stairs traverse and all 1 interior marker(s) reachable from "
                "spawn; 1 deferred to site scope (extraction_STREET)"
                if themeable else
                "1 of 1 interior marker(s) unreachable from spawn"),
            "markers": {
                "checked": 2, "reachable": 1 if themeable else 0,
                "unreachable": ["extraction_STREET (snap 2.6m)"],
                "interior_checked": 1,
                "interior_reachable": 1 if themeable else 0,
                "interior_unreachable": (
                    [] if themeable else ["objective_A (snap 0.4m)"]),
                "exterior_deferred": [
                    {"name": "extraction_STREET", "type": "extraction",
                     "snap": 2.57, "reachable": False}],
            },
        }), encoding="utf-8")
        if lights:
            (root / f"{aid}.lights.json").write_text(
                json.dumps({"building_id": aid}), encoding="utf-8")
    return root


def _brief(library: Path | None, count: int = LOT) -> MissionBrief:
    return MissionBrief(
        mission_id=MISSION, display_name="art fanout",
        archetype="gas_station", building_count=count, theme="delco",
        candidate_count=1, lot_library=(str(library) if library else None))


def _plan(brief: MissionBrief):
    plan = plan_mission(brief, seed_base=SEED_BASE, layers={LAYER_ART})
    return plan_mission(brief, seed_base=SEED_BASE, layers={LAYER_ART},
                        selected_candidate=plan.candidate_ids[0])


class _Workspace(SimpleNamespace):
    """Enough Workspace for the spec builder: two directories and a tools file."""

    def load_tools_local(self) -> dict:
        return {"repositories": {"deli_counter": str(self.repos / "deli_counter"),
                                 "lot": str(self.repos / "lot"),
                                 "lux": str(self.repos / "lux"),
                                 "laser_tag": str(self.repos / "laser_tag")}}


def _specs(tmp_path: Path, plan, brief, monkeypatch, *, publish=True) -> dict:
    """Real `_job_specs_for_plan`, with the two disk-writing branches stubbed.

    `_write_site_spec` and `_write_dispatch_spec` stage real trees and measure
    GLBs; neither is under test here and both would need a workspace. Everything
    the art path touches is left alone.
    """
    ws = _Workspace(jobs_dir=tmp_path / "jobs",
                    internal_dir=tmp_path / "internal",
                    repos=tmp_path / "repos")
    monkeypatch.setattr(cmds, "_write_site_spec",
                        lambda *a, **k: tmp_path / "site.spec.json")
    monkeypatch.setattr(cmds, "_write_dispatch_spec",
                        lambda *a, **k: tmp_path / "dispatch.spec.json")
    if publish:
        # A job's layer is resolved by globbing its published out/ dir, so the
        # bug is only visible once those exist -- which is the state every run
        # after the first is in, and the state the 2026-08-06 measurement was
        # taken in.
        for job in plan.graph.jobs():
            if job.stage_id not in ("zoo_dressing_build", "zoo_fixtures_build"):
                continue
            out = ws.jobs_dir / job.job_id / "out"
            out.mkdir(parents=True, exist_ok=True)
            bid = job.archetype_id or "shell"
            kind = ("dressing" if job.stage_id == "zoo_dressing_build"
                    else "fixtures")
            (out / f"{bid}_{kind}.glb").write_bytes(b"glb")
    return cmds._job_specs_for_plan(ws, {"theme_family": "delco"}, brief, plan)


def _compose_args(spec: dict, tmp_path: Path) -> list[tuple[str, ...]]:
    return [c.arguments for c in PresentationAdapter().plan_commands(
        spec, {"work_dir": str(tmp_path / "work"), "repository": ""})]


def _flag(args: tuple[str, ...], flag: str) -> str | None:
    return args[args.index(flag) + 1] if flag in args else None


def _stages(plan, stage: str) -> list:
    return [j for j in plan.graph.jobs() if j.stage_id == stage]


# ---------------------------------------------------------------------------
# The falsifier
# ---------------------------------------------------------------------------

def test_five_buildings_get_five_distinct_dressings(tmp_path, monkeypatch):
    """The one that had to go red first. Five composes, five different props."""
    brief = _brief(_library(tmp_path / "build"))
    plan = _plan(brief)
    specs = _specs(tmp_path, plan, brief, monkeypatch)
    compose_jid = _stages(plan, "presentation_compose")[0].job_id

    dressings = [_flag(a, "--dressing")
                 for a in _compose_args(specs[compose_jid], tmp_path)]
    attached = [d for d in dressings if d]

    # Distinctness first, deliberately. A count assertion passes while the bug
    # is fully intact -- the number of composes was never what was wrong.
    assert len(set(attached)) == len(attached) == LOT, (
        f"{len(attached)} composed building(s) share "
        f"{len(set(attached))} dressing bake(s): "
        + ", ".join(sorted({Path(d).name for d in attached})))


def test_five_buildings_get_five_distinct_fixtures(tmp_path, monkeypatch):
    brief = _brief(_library(tmp_path / "build"))
    plan = _plan(brief)
    specs = _specs(tmp_path, plan, brief, monkeypatch)
    compose_jid = _stages(plan, "presentation_compose")[0].job_id

    fixtures = [f for f in (_flag(a, "--fixtures")
                            for a in _compose_args(specs[compose_jid], tmp_path))
                if f]
    assert len(set(fixtures)) == len(fixtures) == LOT, (
        f"{len(fixtures)} composed building(s) share "
        f"{len(set(fixtures))} fixture bake(s): "
        + ", ".join(sorted({Path(f).name for f in fixtures})))


def test_each_building_gets_the_bake_made_for_it(tmp_path, monkeypatch):
    """Distinctness is not enough: five shuffled paths are also five distinct."""
    brief = _brief(_library(tmp_path / "build"))
    plan = _plan(brief)
    specs = _specs(tmp_path, plan, brief, monkeypatch)
    compose_jid = _stages(plan, "presentation_compose")[0].job_id

    for args in _compose_args(specs[compose_jid], tmp_path):
        out = Path(_flag(args, "--out"))
        dressing = _flag(args, "--dressing")
        if out.name == "presentation":       # the mission's own shell
            continue
        aid = out.name
        assert dressing, f"{aid} composed with no dressing"
        assert Path(dressing).name == f"{aid}_dressing.glb", (
            f"{aid} was handed {Path(dressing).name}")
        assert Path(dressing).parent.parent.name.endswith(f".{aid}"), (
            f"{aid} was handed a layer from job "
            f"{Path(dressing).parent.parent.name}")


# ---------------------------------------------------------------------------
# 3b: the planner
# ---------------------------------------------------------------------------

def test_placement_stages_fan_out_and_libraries_do_not(tmp_path):
    plan = _plan(_brief(_library(tmp_path / "build")))
    # `zoo_kit_build` joined this list on 2026-08-09. It had been below, under
    # "a kit is a module LIBRARY resolved per slot at compose time; fanning it
    # out costs a Blender build per building and fixes nothing" -- which was
    # wrong on the last clause and therefore on all of it. Every module but
    # `wallEnd` is `fit: exact`, cut to ONE slot's dims, and one shared kit put
    # 3.300 m walls in buildings whose slots asked 3.1 to 5.2. It does cost a
    # Blender build per building. That is what it costs.
    for stage in ("patina_apply", "patina_dressing", "zoo_dressing_build",
                  "zoo_fixtures_build", "zoo_kit_build"):
        jobs = _stages(plan, stage)
        assert len(jobs) == LOT, f"{stage}: {len(jobs)} job(s)"
        assert len({j.archetype_id for j in jobs}) == LOT, stage
    # Pixelcoat's skin packs really are mission-wide: a skin is a material, not
    # a dimension, so the same pack dresses every building's walls.
    for stage in ("pixelcoat_build", "presentation_compose",
                  "themed_site_assemble", "lux_apply"):
        assert len(_stages(plan, stage)) == 1, stage
        assert _stages(plan, stage)[0].archetype_id is None, stage


def test_expected_outputs_follow_the_input_stem(tmp_path):
    """Patina names outputs from the input stem, so the contract must too."""
    plan = _plan(_brief(_library(tmp_path / "build")))
    for job in _stages(plan, "patina_dressing"):
        aid = job.archetype_id
        assert f"{aid}.patina.dressing.json" in job.expected_outputs
        assert f"{aid}.patina.glb" in job.expected_outputs
        assert not any(o.startswith("shell.") for o in job.expected_outputs)


def test_compose_waits_on_every_buildings_layers(tmp_path):
    plan = _plan(_brief(_library(tmp_path / "build")))
    compose = _stages(plan, "presentation_compose")[0]
    for stage in ("zoo_dressing_build", "zoo_fixtures_build"):
        deps = {j.job_id for j in _stages(plan, stage)}
        assert deps <= set(compose.depends_on), stage


def test_each_dressing_build_waits_on_its_own_patina(tmp_path):
    plan = _plan(_brief(_library(tmp_path / "build")))
    dress = {j.archetype_id: j.job_id for j in _stages(plan, "patina_dressing")}
    for job in _stages(plan, "zoo_dressing_build"):
        assert dress[job.archetype_id] in job.depends_on


def test_the_fixture_gate_follows_the_bake(tmp_path):
    """A gate over one of five bakes reports the mission passed on one building."""
    plan = _plan(_brief(_library(tmp_path / "build")))
    gates = _stages(plan, "lux_fixture_gate")
    bakes = {j.archetype_id: j.job_id for j in _stages(plan, "zoo_fixtures_build")}
    assert len(gates) == LOT
    for gate in gates:
        assert gate.depends_on == [bakes[gate.archetype_id]]


def test_the_single_shell_plan_did_not_move(tmp_path):
    """A mission with no lot library plans exactly what it planned before.

    Golden, not a property: re-placing a level that has already been evaluated
    would be a different level wearing the same grade, so the single-shell path
    is a regression lock rather than a rule.
    """
    plan = _plan(_brief(None))
    jobs = {j["job_id"]: j for j in plan.as_dict()["jobs"]}
    assert f"{MISSION}.patina_apply" in jobs
    assert f"{MISSION}.patina_dressing" in jobs
    assert f"{MISSION}.zoo_dressing_build" in jobs
    assert f"{MISSION}.zoo_fixtures_build" in jobs
    assert f"{MISSION}.lux_fixture_gate" in jobs
    assert jobs[f"{MISSION}.patina_dressing"]["expected_outputs"] == [
        "shell.patina.glb", "shell.patina.json", "shell.patina.gameplay.json",
        "shell.patina.dressing.json"]
    assert jobs[f"{MISSION}.presentation_compose"]["depends_on"] == [
        f"{MISSION}.deli_generate.candidate.seed_{SEED_BASE}",
        f"{MISSION}.zoo_kit_build",
        f"{MISSION}.zoo_dressing_build",
        f"{MISSION}.zoo_fixtures_build"]
    # A mission-wide job carries no archetype, and no plan that has ever been
    # written grows a null on every line.
    assert not any("archetype_id" in j for j in jobs.values())


def test_a_fanned_job_reports_its_building_in_the_plan_json(tmp_path):
    plan = _plan(_brief(_library(tmp_path / "build")))
    jobs = {j["job_id"]: j for j in plan.as_dict()["jobs"]}
    fanned = [j for j in jobs.values() if j["stage"] == "zoo_dressing_build"]
    assert len(fanned) == LOT
    assert all(j.get("archetype_id") for j in fanned)
    assert len({j["archetype_id"] for j in fanned}) == LOT


def test_a_themed_lot_refuses_a_building_that_cannot_be_dressed(tmp_path):
    """A four building site with every stage reporting success is not the brief."""
    lib = _library(tmp_path / "build")
    for p in lib.glob("*.lights.json"):
        p.unlink()
    with pytest.raises(building_library.ArtInputsMissing):
        _plan(_brief(lib))


# ---------------------------------------------------------------------------
# 3c: the spec builder
# ---------------------------------------------------------------------------

def test_each_patina_pass_treats_its_own_shell(tmp_path, monkeypatch):
    brief = _brief(_library(tmp_path / "build"))
    plan = _plan(brief)
    specs = _specs(tmp_path, plan, brief, monkeypatch)
    seen = {}
    for job in _stages(plan, "patina_apply"):
        seen[job.archetype_id] = specs[job.job_id]["input_glb"]
    assert len(set(seen.values())) == LOT, seen
    for aid, glb in seen.items():
        assert Path(glb).name == f"{aid}.glb"


def test_each_dressing_build_reads_its_own_manifest(tmp_path, monkeypatch):
    brief = _brief(_library(tmp_path / "build"))
    plan = _plan(brief)
    specs = _specs(tmp_path, plan, brief, monkeypatch)
    for job in _stages(plan, "zoo_dressing_build"):
        aid = job.archetype_id
        man = Path(specs[job.job_id]["manifest_path"])
        assert man.name == f"{aid}.patina.dressing.json"
        assert man.parent.parent.name.endswith(f".{aid}")


def test_each_fixture_bake_reads_its_own_lights_manifest(tmp_path, monkeypatch):
    brief = _brief(_library(tmp_path / "build"))
    plan = _plan(brief)
    specs = _specs(tmp_path, plan, brief, monkeypatch)
    paths = {j.archetype_id: specs[j.job_id]["lights_path"]
             for j in _stages(plan, "zoo_fixtures_build")}
    assert len(set(paths.values())) == LOT
    for aid, p in paths.items():
        assert Path(p).name == f"{aid}.lights.json"
        assert json.loads(Path(p).read_text())["building_id"] == aid


def test_the_single_shell_still_reads_its_own_job_outputs(tmp_path, monkeypatch):
    brief = _brief(None)
    plan = _plan(brief)
    specs = _specs(tmp_path, plan, brief, monkeypatch)
    fixtures = specs[f"{MISSION}.zoo_fixtures_build"]
    assert Path(fixtures["lights_path"]).name == "shell.lights.json"
    dress = specs[f"{MISSION}.zoo_dressing_build"]
    assert Path(dress["manifest_path"]).name == "shell.patina.dressing.json"
    patina = specs[f"{MISSION}.patina_apply"]
    assert Path(patina["input_glb"]).name == "shell.glb"


def test_the_single_shell_compose_still_gets_its_layers(tmp_path, monkeypatch):
    brief = _brief(None)
    plan = _plan(brief)
    specs = _specs(tmp_path, plan, brief, monkeypatch)
    spec = specs[f"{MISSION}.presentation_compose"]
    assert set(spec["dressing_glb"]) == {""}
    args = _compose_args(spec, tmp_path)
    assert len(args) == 1
    assert Path(_flag(args[0], "--dressing")).name == "shell_dressing.glb"
    assert Path(_flag(args[0], "--fixtures")).name == "shell_fixtures.glb"


def test_a_layer_is_keyed_on_the_building_it_was_built_for(tmp_path, monkeypatch):
    brief = _brief(_library(tmp_path / "build"))
    plan = _plan(brief)
    specs = _specs(tmp_path, plan, brief, monkeypatch)
    spec = specs[_stages(plan, "presentation_compose")[0].job_id]
    lot = {a["id"] for a in spec["lot_archetypes"]}
    assert set(spec["dressing_glb"]) == lot
    assert set(spec["fixtures_glb"]) == lot


def test_an_unbaked_layer_refuses_rather_than_being_dropped(tmp_path, monkeypatch):
    """A first run has published nothing -- and that must FAIL the job.

    This test previously asserted the opposite: that every layer resolved to
    `""` and no `--dressing` was passed at all. That is precisely what shipped
    on 2026-08-06, and the probe found five buildings with no props on any of
    them. "Nobody inherits anybody's props" was the right instinct. "So nobody
    gets any props, and the run succeeds" was the wrong conclusion, and it was
    sitting in this file labelled as intended behaviour.

    A compose that cannot find a bake it was told about is a failed job, not a
    bare building.
    """
    brief = _brief(_library(tmp_path / "build"))
    plan = _plan(brief)
    specs = _specs(tmp_path, plan, brief, monkeypatch, publish=False)
    spec = specs[_stages(plan, "presentation_compose")[0].job_id]
    # the spec names DIRECTORIES, which exist as constructions before the jobs
    # that fill them have run
    assert all(v and not str(v).endswith(".glb")
               for v in spec["dressing_glb"].values())
    problems = PresentationAdapter().validate_configuration(
        spec, {"repository": ""})
    assert any("dressing_glb" in p for p in problems), (
        "an unbaked layer must refuse the job, not quietly drop the flag")


def test_a_resolver_with_no_way_to_choose_refuses(tmp_path):
    job = SimpleNamespace(
        job_id="m.presentation_compose", depends_on=[
            "m.zoo_dressing_build.a01", "m.zoo_dressing_build.b02"])
    with pytest.raises(RuntimeError):
        cmds._dep(job, "zoo_dressing_build")
    assert cmds._dep(job, "zoo_dressing_build", "a01") == "m.zoo_dressing_build.a01"
    assert cmds._dep(job, "zoo_kit_build") is None


def test_an_archetype_id_that_is_a_tail_of_another_is_not_confused():
    job = SimpleNamespace(job_id="m.x", depends_on=[
        "m.zoo_dressing_build.final_stand", "m.zoo_dressing_build.stand"])
    assert cmds._dep(job, "zoo_dressing_build", "stand") == \
        "m.zoo_dressing_build.stand"
    assert cmds._dep(job, "zoo_dressing_build", "final_stand") == \
        "m.zoo_dressing_build.final_stand"


# ---------------------------------------------------------------------------
# 3d: the adapter
# ---------------------------------------------------------------------------

def test_compose_will_not_run_without_being_told_which_layers():
    """The layers are arguments now, and have no defaults on purpose.

    They were read from the closed-over job_spec while the six geometry
    arguments were overridden per archetype, which is how five different
    buildings came to be dressed out of one bake.
    """
    import inspect
    src = inspect.getsource(PresentationAdapter.plan_commands)
    sig_line = next(l for l in src.splitlines() if "def compose(" in l)
    assert "dressing" in src.split("def compose(")[1].split(")")[0]
    assert "fixtures" in src.split("def compose(")[1].split(")")[0]
    assert "job_spec[\"dressing_glb\"]" not in src
    assert sig_line  # the nested definition is still where the doc says it is


def test_the_shells_fingerprint_key_did_not_move(tmp_path):
    """A single-shell mission that has already composed must not recompose."""
    # A layer value is the DIRECTORY the bake publishes into, not the file --
    # the spec is written before the job that fills it has run.
    out = tmp_path / "shell_out"
    out.mkdir()
    (out / "shell_dressing.glb").write_bytes(b"glb")
    fp = PresentationAdapter().fingerprint_inputs(
        {"dressing_glb": {"": str(out)}}, {})
    assert "dressing_glb_hash" in fp
    legacy = PresentationAdapter().fingerprint_inputs(
        {"dressing_glb": str(out)}, {})
    assert legacy["dressing_glb_hash"] == fp["dressing_glb_hash"]


def test_every_buildings_layer_is_in_the_fingerprint(tmp_path):
    """A changed layer must invalidate the compose, for every building."""
    layers = {}
    for i, aid in enumerate(ARCHETYPES[:LOT]):
        out = tmp_path / aid
        out.mkdir()
        (out / f"{aid}_dressing.glb").write_bytes(b"glb" + bytes([i]))
        layers[aid] = str(out)
    fp = PresentationAdapter().fingerprint_inputs({"dressing_glb": layers}, {})
    hashes = {k: v for k, v in fp.items() if k.startswith("dressing_glb_hash")}
    assert len(hashes) == LOT
    assert len(set(hashes.values())) == LOT


# ---------------------------------------------------------------------------
# The art screen, which the fan-out breaks outright
# ---------------------------------------------------------------------------

def _art_pass(tmp_path: Path, job_ids) -> dict:
    from packages.service.facade import FactoryService
    jobs = tmp_path / "jobs"
    for jid in job_ids:
        out = jobs / jid / "out"
        out.mkdir(parents=True, exist_ok=True)
        (out / "thing.json").write_text("{}", encoding="utf-8")
    svc = FactoryService(SimpleNamespace(jobs_dir=jobs))
    return {s.name: s.status for s in svc.art_pass(MISSION)}


def test_a_fanned_stage_is_not_reported_as_never_started(tmp_path):
    """`<mission>.<stage>` does not exist once the stage runs per building."""
    rows = _art_pass(tmp_path, [
        f"{MISSION}.patina_apply.{a}" for a in ARCHETYPES[:LOT]])
    assert rows["Patina theme and overrides"] == "done"


def test_a_partly_finished_stage_is_not_done(tmp_path):
    """Four of five buildings dressed is not the brief either."""
    jobs = tmp_path / "jobs"
    for aid in ARCHETYPES[:LOT]:
        (jobs / f"{MISSION}.zoo_dressing_build.{aid}" / "out").mkdir(parents=True)
    for aid in ARCHETYPES[:LOT - 1]:
        (jobs / f"{MISSION}.zoo_dressing_build.{aid}" / "out" / "d.glb"
         ).write_bytes(b"g")
    from packages.service.facade import FactoryService
    rows = {s.name: s.status
            for s in FactoryService(SimpleNamespace(jobs_dir=jobs)).art_pass(MISSION)}
    assert rows["Zoo dressing"] == "not_started"


def test_the_single_shell_art_screen_did_not_move(tmp_path):
    rows = _art_pass(tmp_path, [f"{MISSION}.patina_apply", f"{MISSION}.lux_apply"])
    assert rows["Patina theme and overrides"] == "done"
    assert rows["Lux profiles"] == "done"
    assert rows["Zoo dressing"] == "not_started"


if __name__ == "__main__":  # pragma: no cover
    sys.exit(pytest.main([__file__, "-q"] + sys.argv[1:]))


# ---------------------------------------------------------------------------
# 3e: the kit is a per-building bake, not a shared library
#
# Measured 2026-08-09 with `module_extents.py --sweep`. Every kit module in
# every building of `lot_demo_001` is 3.300 m tall, against slots asking for
# 3.1, 3.9, 4.2, 4.7 and 5.2 -- and 3.300 is the MISSION SHELL's storey height,
# because `_lot_slots` hands the kit `shell.slots.json` and one kit job feeds
# every building. A clean per-building rebuild of `depot_a01` produces 5.200,
# so Zoo was never wrong.
#
# The belief that made it look correct is written down in three places: the
# planner's comment beside the dressing job ("the SHARED kit: the kit is a
# module library resolved per slot"), `_dep`'s docstring, and the assertion in
# `test_placement_stages_fan_out_and_libraries_do_not` above. An `exact`-fit
# module is built to ONE slot's dims. The only module that really is shared is
# `wallEnd`, the 1x1x1 unit box -- and it is the only species that measured
# correct in all seven buildings.
# ---------------------------------------------------------------------------

def test_each_kit_is_built_from_its_own_buildings_slots(tmp_path, monkeypatch):
    """The falsifier. A kit built from another building's slots is the defect.

    Reads the spec the builder actually writes, not the job count: one kit job
    per building would still be wrong if all five were pointed at
    `shell.slots.json`.
    """
    brief = _brief(_library(tmp_path / "build"))
    plan = _plan(brief)
    specs = _specs(tmp_path, plan, brief, monkeypatch)
    kits = _stages(plan, "zoo_kit_build")
    assert len(kits) == LOT, f"{len(kits)} kit job(s), expected {LOT}"
    paths = {j.archetype_id: specs[j.job_id]["slots_path"] for j in kits}
    assert len(set(paths.values())) == LOT, (
        f"{len(set(paths.values()))} distinct slots.json across {LOT} kits: "
        f"{sorted(set(paths.values()))}")
    for aid, p in paths.items():
        assert Path(p).name == f"{aid}.slots.json", (
            f"kit for {aid} was built from {Path(p).name}")


def test_each_building_is_composed_with_its_own_kit(tmp_path, monkeypatch):
    """Distinctness at the argv, the way the dressing falsifier does it.

    A per-building kit job that still reaches compose through one closed-over
    `modules_dir` changes nothing you could see in the level.
    """
    brief = _brief(_library(tmp_path / "build"))
    plan = _plan(brief)
    specs = _specs(tmp_path, plan, brief, monkeypatch)
    compose_jid = _stages(plan, "presentation_compose")[0].job_id

    seen = {}
    for args in _compose_args(specs[compose_jid], tmp_path):
        out = Path(_flag(args, "--out"))
        mods = _flag(args, "--modules")
        if out.name == "presentation":       # the mission's own shell
            continue
        aid = out.name
        assert mods, f"{aid} composed with no --modules"
        seen[aid] = mods
        # One level shallower than the dressing assertion: a kit layer IS the
        # job's out/ dir, where a dressing layer is a file inside one.
        assert Path(mods).parent.name.endswith(f".{aid}"), (
            f"{aid} was handed the kit from job {Path(mods).parent.name}")
    assert len(set(seen.values())) == LOT, (
        f"{len(set(seen.values()))} distinct --modules across {LOT} buildings")


def test_each_dressing_build_waits_on_its_own_kit(tmp_path):
    """A dressing bake is skinned by the kit's library; it must be ITS kit."""
    plan = _plan(_brief(_library(tmp_path / "build")))
    for job in _stages(plan, "zoo_dressing_build"):
        kits = [d for d in job.depends_on if ".zoo_kit_build" in d]
        assert len(kits) == 1, f"{job.job_id} waits on {len(kits)} kits"
        assert kits[0].endswith(f".{job.archetype_id}"), (
            f"{job.job_id} waits on {kits[0]}")


def test_compose_waits_on_every_buildings_kit(tmp_path):
    plan = _plan(_brief(_library(tmp_path / "build")))
    compose = _stages(plan, "presentation_compose")[0]
    kits = {d for d in compose.depends_on if ".zoo_kit_build" in d}
    assert len(kits) == LOT, f"compose waits on {len(kits)} kit job(s)"
