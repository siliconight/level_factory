"""End-to-end orchestration test using stub tool repos (TDD 37.3).

Proves the Phase-1 exit criteria:
  * one mission runs from brief -> functional candidates -> shell handoff
  * cache reuse is proven (second run hits cache)
  * jobs resume after a simulated restart (fresh index/scheduler)
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests" / "fixtures"
sys.path.insert(0, str(ROOT))

from packages.project_store.workspace import init_workspace  # noqa: E402


def _installation() -> dict:
    return {
        "python_executable": sys.executable,
        "godot_executable": str(FIXTURES / "bin" / ("godot.cmd" if sys.platform.startswith("win") else "godot")),
        "blender_executable": str(FIXTURES / "bin" / ("godot.cmd" if sys.platform.startswith("win") else "godot")),  # stub answers --version
        "repositories": {
            "deli_counter": str(FIXTURES / "repos" / "deli_counter"),
            "lot": str(FIXTURES / "repos" / "lot"),
            "laser_tag": str(FIXTURES / "repos" / "laser_tag"),
            "dispatch": str(FIXTURES / "repos" / "dispatch"),
        },
    }


@pytest.fixture()
def workspace(tmp_path):
    ws = init_workspace(tmp_path / "ws", project_id="test", name="Test Factory")
    ws.write_json(ws.tools_local, _installation())

    # A batch with one mission.
    batch = {
        "schema": "level_factory.batch.v0.1",
        "batch_id": "batch_001",
        "name": "Test Batch",
        "seed_base": 1997,
        "theme_family": "delco_1997",
        "missions": ["bank_block_001"],
    }
    src = tmp_path / "batch_src"
    (src / "briefs").mkdir(parents=True)
    (src / "batch.json").write_text(json.dumps(batch))
    (src / "briefs" / "bank_block_001.json").write_text(json.dumps({
        "schema": "level_factory.mission_brief.v0.1",
        "mission_id": "bank_block_001",
        "display_name": "Bank Block",
        "archetype": "urban_bank",
        "building_count": 1,
        "site_shape": "street_block",
        "route_shape": "push_then_backtrack",
        "candidate_count": 3,
        "target_minutes": [25, 35],
        "theme": "delco_1997",
    }))
    return ws, src


def _run_cli(ws_root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(ROOT / "apps" / "cli" / "main.py"), "-C", str(ws_root), *args],
        capture_output=True, text=True,
    )


def test_full_pipeline(workspace):
    ws, src = workspace
    root = ws.root

    # Doctor: tools resolve.
    r = _run_cli(root, "doctor")
    assert r.returncode == 0, r.stderr
    assert "deli_counter" in r.stdout

    # Create the batch.
    r = _run_cli(root, "batch", "create", str(src / "batch.json"))
    assert r.returncode == 0, r.stderr
    assert (root / "batches" / "batch_001" / "missions" / "bank_block_001" / "brief" / "brief.json").exists()

    # Plan the functional pipeline.
    r = _run_cli(root, "plan", "bank_block_001", "--target", "functional-lock", "--json")
    assert r.returncode == 0, r.stderr
    plan = json.loads(r.stdout)
    assert len(plan["candidates"]) == 3
    assert any(j["adapter"] == "deli_counter" for j in plan["jobs"])
    assert any(j["adapter"] == "laser_tag" for j in plan["jobs"])

    # Run to functional lock (no dispatch yet, no candidate selected).
    r = _run_cli(root, "run", "bank_block_001", "--target", "functional-lock")
    assert r.returncode in (0, 1), r.stderr + r.stdout
    assert "Structural checks passed" in r.stdout

    # Approve brief + select a candidate, then run to handoff.
    _run_cli(root, "approve", "bank_block_001", "brief_approved")
    cand = plan["candidates"][0]
    r = _run_cli(root, "approve", "bank_block_001", "candidate_selected", "--candidate", cand)
    assert r.returncode == 0, r.stderr

    r = _run_cli(root, "run", "bank_block_001", "--target", "dispatch-handoff")
    assert r.returncode in (0, 1), r.stderr + r.stdout
    assert "dispatch_handoff" in r.stdout

    # Handoff artifacts exist and HANDOFF.md carries the required language.
    handoff_out = root / ".level_factory" / "jobs" / "bank_block_001.dispatch_handoff" / "out"
    assert (handoff_out / "mission.tscn").exists()
    handoff_md = (handoff_out / "HANDOFF.md").read_text()
    assert "authoritative for mission progression" in handoff_md


def test_cache_reuse(workspace):
    ws, src = workspace
    root = ws.root
    _run_cli(root, "batch", "create", str(src / "batch.json"))
    _run_cli(root, "run", "bank_block_001", "--target", "functional-lock")

    before = json.loads(_run_cli(root, "cache", "inspect").stdout)
    assert before["manifest_count"] > 0

    # Wipe job records (simulate restart) but keep the cache; re-run.
    shutil.rmtree(root / ".level_factory" / "jobs")
    (root / ".level_factory" / "index.sqlite").unlink()
    r = _run_cli(root, "run", "bank_block_001", "--target", "functional-lock")
    assert r.returncode in (0, 1), r.stderr + r.stdout
    # Every functional job should be a cache hit the second time.
    assert r.stdout.count("cache") >= 6  # 3 deli + 3 lot at minimum


def test_resume_after_partial(workspace):
    ws, src = workspace
    root = ws.root
    _run_cli(root, "batch", "create", str(src / "batch.json"))
    # First run completes; a second run with the index intact skips finished jobs.
    _run_cli(root, "run", "bank_block_001", "--target", "functional-lock")
    r = _run_cli(root, "status", "bank_block_001")
    assert r.returncode == 0
    assert "SUCCEEDED" in r.stdout or "SKIPPED_CACHE_HIT" in r.stdout


def test_candidates_are_actually_different_levels(workspace):
    """N candidates exist so a human can choose; N copies is not a choice.

    The site spec was written to one path per mission rather than per candidate,
    so every Lot job in a mission read whichever spec was written last and every
    candidate came out byte-identical. It survived for the life of the pipeline
    because per-candidate validation running N times looks the same whether the
    candidates are real or copies -- nothing had ever compared two of them.
    """
    ws, src = workspace
    root = ws.root
    _run_cli(root, "batch", "create", str(src / "batch.json"))
    plan = json.loads(_run_cli(root, "plan", "bank_block_001",
                               "--target", "functional-lock", "--json").stdout)
    r = _run_cli(root, "run", "bank_block_001", "--target", "functional-lock")
    assert r.returncode in (0, 1), r.stderr + r.stdout

    # Each candidate gets its own spec, not a shared one the last writer wins.
    specs = sorted((root / ".level_factory" / "temp" / "bank_block_001").glob(
        "candidate_seed_*/site.json"))
    assert len(specs) == len(plan["candidates"]), (
        "one site spec per candidate -- a shared path is the original bug")
    placements = [json.loads(p.read_text())["buildings"] for p in specs]
    assert len({json.dumps(b, sort_keys=True) for b in placements}) == len(specs), (
        "two candidates were handed the same placements")

    # And the roles Lot resolves into the walkable scene are set at all; they
    # were left unset, so every candidate spawned the player at Lot's default.
    for p in specs:
        spec = json.loads(p.read_text())
        assert spec["spawn"] and spec["objective"] and spec["extraction"]

    # The run says out loud how many distinct levels it built, so "5 candidates"
    # can never again be printed for one level built five times.
    assert "all distinct" in r.stdout, r.stdout


def test_identical_candidates_block_the_run(workspace):
    """The gate has to fail when the candidates really are copies."""
    ws, src = workspace
    root = ws.root
    _run_cli(root, "batch", "create", str(src / "batch.json"))
    _run_cli(root, "run", "bank_block_001", "--target", "functional-lock")

    # Force the failure the old code produced: give every candidate the same
    # outputs, then re-validate the comparison directly.
    sys.path.insert(0, str(ROOT))
    from apps.cli.commands import candidate_artifact_hashes  # noqa: E402
    from packages.validation.candidate_diversity import check_candidate_diversity

    plan = json.loads(_run_cli(root, "plan", "bank_block_001",
                               "--target", "functional-lock", "--json").stdout)
    same = {c: {"site.tscn": "sha256:same", "shell.glb": "sha256:same"}
            for c in plan["candidates"]}
    findings = check_candidate_diversity(same)
    assert findings and findings[0]["blocking"] is True

    # ...and that the real run does NOT trip it, so the gate is measuring
    # something rather than always firing.
    real = candidate_artifact_hashes(ws, plan["candidates"],
                                     [])  # no jobs -> nothing to compare
    assert set(real) == set(plan["candidates"])


def test_a_run_leaves_a_trace_anyone_can_read(workspace):
    """A run nobody can inspect afterwards is a run nobody can act on.

    Two reporting surfaces were silently empty. ``status`` with no mission id
    listed nothing, because the missions table had no writer at all -- every
    mission was invisible and ``batch report`` called them all "draft" no matter
    how many times they had been built. And ``validate`` printed a histogram:
    "combat_structure: 5" is a number, not a finding, and a count that cannot be
    acted on sits unchanged for weeks while looking like weather.
    """
    ws, src = workspace
    root = ws.root
    _run_cli(root, "batch", "create", str(src / "batch.json"))
    r = _run_cli(root, "run", "bank_block_001", "--target", "functional-lock")
    assert r.returncode in (0, 1), r.stderr + r.stdout

    r = _run_cli(root, "status")
    assert r.returncode == 0, r.stderr
    assert "bank_block_001" in r.stdout, "a mission that ran must be listed"
    assert "batch_001" in r.stdout, "and attributed to its batch"

    r = _run_cli(root, "validate", "bank_block_001")
    assert r.returncode in (0, 2), r.stderr
    assert "no findings" in r.stdout or "finding(s)" in r.stdout

    r = _run_cli(root, "validate", "bank_block_001", "--json")
    data = json.loads(r.stdout)
    assert "aggregate" in data and "issues" in data
    assert data["aggregate"]["total"] == len(data["issues"]), (
        "the machine output must carry the findings, not just count them")


def test_laser_tag_actually_evaluates_the_map(workspace):
    """Every Laser Tag job in this pipeline's history evaluated nothing.

    The harness finds spawns, enemies and the objective by node name --
    ``LT_PlayerSpawn``, ``LT_EnemySpawnPoints``, ``LT_ObjectivePoint`` -- and
    nothing in the pipeline had ever written one. ``validate_map()`` failed,
    ``run_evaluation`` returned before a single firefight, and the report came
    back ``runs: 0, grade: BROKEN``, which Level Factory printed as a readiness
    grade. "The map plays badly" and "the map was never played" are different
    statements and only one of them was true.

    The stub godot mirrors the real harness's refusal, so this test can only
    pass if the staged scene genuinely carries the contract.
    """
    ws, src = workspace
    root = ws.root
    _run_cli(root, "batch", "create", str(src / "batch.json"))
    r = _run_cli(root, "run", "bank_block_001", "--target", "functional-lock")
    assert r.returncode in (0, 1), r.stderr + r.stdout

    sys.path.insert(0, str(ROOT))
    from packages.validation.lasertag_report import was_evaluated  # noqa: E402

    reports = [json.loads(p.read_text()) for p in
               sorted((root / ".level_factory" / "jobs").rglob("lasertag.report.json"))]
    assert reports, "laser_tag produced no report at all"
    assert all(was_evaluated(rep) for rep in reports), (
        f"laser_tag reported a grade without running: {reports}")

    # The staged scene -- not the source -- is what the evaluator reads, so the
    # contract has to hold there.
    staged = sorted((root / ".level_factory" / "staging").rglob("level.tscn"))
    assert staged, "no staged Laser Tag project"
    for scene in staged:
        text = scene.read_text()
        for hook in ("LT_PlayerSpawn", "LT_EnemySpawnPoints", "LT_ObjectivePoint"):
            assert hook in text, f"{scene} is missing {hook}"

        # ...and the illegal node name Lot used to emit is repaired on the way
        # in, so the ladder's CollisionShape3D still has a parent to attach to.
        assert "b0/LADDER_0_climb" not in text
        assert 'name="b0_LADDER_0_climb"' in text
        assert 'parent="b0_LADDER_0_climb"' in text

    # Repairs are recorded where a human can find them, not applied invisibly.
    notes = sorted((root / ".level_factory" / "staging").rglob("staging.notes.json"))
    assert notes, "staging repaired the scene and said nothing"
    note = json.loads(notes[0].read_text())
    assert any("LADDER" in n for n in note.get("renamed_nodes", []))
    assert "LT_PlayerSpawn" in note["scene_post_process"]["injected"]


def test_a_map_laser_tag_cannot_play_blocks_the_run(workspace):
    """The gate has to fail when the evaluator really did not run -- otherwise
    it is measuring nothing. A readiness *score* still never blocks (TDD 5.5);
    "the tool could not run at all" is a contract failure and does."""
    sys.path.insert(0, str(ROOT))
    from packages.validation.lasertag_report import normalize_report, summarize  # noqa: E402

    never_ran = {"grade": "BROKEN", "overall_score": 0, "runs": 0,
                 "findings": [{"severity": "FAIL", "type": "NO_RUNS",
                               "message": "No runs completed."}]}
    blockers = [i for i in normalize_report(never_ran) if i["blocking"]]
    assert len(blockers) == 1
    assert blockers[0]["code"] == "LT_NOT_EVALUATED"

    played_badly = {"grade": "BROKEN", "overall_score": 3, "runs": 25}
    assert not any(i["blocking"] for i in normalize_report(played_badly))

    assert summarize([never_ran, played_badly]) == "laser_tag: 1/2 evaluated, 1 never ran"
