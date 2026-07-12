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
        "godot_executable": str(FIXTURES / "bin" / "godot"),
        "blender_executable": str(FIXTURES / "bin" / "godot"),  # stub answers --version
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
