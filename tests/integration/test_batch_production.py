"""Phase-4 batch production (TDD 42).

Proves the Phase-4 exit criteria:
  * N missions move through stage-based production as one batch (`batch run`)
  * shared work is reused, not rebuilt per mission (one shared Pixelcoat pack;
    cross-mission cache reuse)
  * a batch report is produced with the mission-status matrix + shared packs.
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests" / "fixtures"
sys.path.insert(0, str(ROOT))

from packages.project_store.workspace import init_workspace  # noqa: E402

_REPOS = ("deli_counter", "lot", "laser_tag", "pixelcoat", "zoo", "patina", "lux", "dispatch")
_MISSIONS = ["m1", "m2", "m3"]


@pytest.fixture()
def batch_ws(tmp_path):
    ws = init_workspace(tmp_path / "ws", project_id="t", name="Batch")
    ws.write_json(ws.tools_local, {
        "python_executable": sys.executable,
        "godot_executable": str(FIXTURES / "bin" / ("godot.cmd" if sys.platform.startswith("win") else "godot")),
        "blender_executable": str(FIXTURES / "bin" / ("godot.cmd" if sys.platform.startswith("win") else "godot")),
        "repositories": {r: str(FIXTURES / "repos" / r) for r in _REPOS},
    })
    (ws.shared_dir / "pixelcoat" / "recipes").mkdir(parents=True)
    (ws.shared_dir / "pixelcoat" / "recipes" / "b.json").write_text('{"recipe":"b"}')
    src = tmp_path / "src"
    (src / "briefs").mkdir(parents=True)
    (src / "batch.json").write_text(json.dumps({
        "schema": "level_factory.batch.v0.1", "batch_id": "b1", "name": "B",
        "seed_base": 1997, "theme_family": "delco_1997", "missions": _MISSIONS}))
    for m in _MISSIONS:
        (src / "briefs" / f"{m}.json").write_text(json.dumps({
            "schema": "level_factory.mission_brief.v0.1", "mission_id": m,
            "display_name": m, "archetype": "urban_bank", "building_count": 1,
            "site_shape": "street_block", "route_shape": "push_then_backtrack",
            "candidate_count": 3, "target_minutes": [25, 35],
            "theme": "delco_1997", "time_of_day": "afternoon"}))
    return ws, src


def _cli(root, *args):
    return subprocess.run(
        [sys.executable, str(ROOT / "apps" / "cli" / "main.py"), "-C", str(root), *args],
        capture_output=True, text=True)


def test_batch_run_and_report(batch_ws):
    ws, src = batch_ws
    root = ws.root
    assert _cli(root, "batch", "create", str(src / "batch.json")).returncode == 0

    # Lock each mission (functional-lock + approvals).
    for m in _MISSIONS:
        assert _cli(root, "run", m, "--target", "functional-lock").returncode in (0, 1)
        _cli(root, "approve", m, "brief_approved")
        _cli(root, "approve", m, "candidate_selected", "--candidate", f"{m}.candidate.seed_1997")
        _cli(root, "approve", m, "functional_shell_locked")

    # Run the whole batch as one DAG.
    r = _cli(root, "batch", "run", "b1", "--target", "presentation")
    assert r.returncode == 0, r.stderr + r.stdout
    assert "3 mission(s), 1 shared job(s)" in r.stdout

    # Shared Pixelcoat pack built exactly once.
    shared = root / ".level_factory" / "jobs" / "batch.b1.pixelcoat_shared" / "out"
    assert (shared / "theme" / "theme.pack.json").exists()

    # Every mission produced a handoff + presentation.
    for m in _MISSIONS:
        assert (root / ".level_factory" / "jobs" / f"{m}.dispatch_handoff" / "out" / "mission.tscn").exists()
        assert (root / ".level_factory" / "jobs" / f"{m}.lux_apply" / "out" / "lux.applied.tscn").exists()

    # Batch report: matrix + shared packs + all handoff-ready.
    r = _cli(root, "batch", "report", "b1", "--json")
    assert r.returncode == 0, r.stderr
    report = json.loads(r.stdout)
    assert report["batch_id"] == "b1"
    assert len(report["mission_status_matrix"]) == 3
    assert "theme.pack.json" in report["shared_asset_packs"]
    assert set(report["handoff_ready_missions"]) == set(_MISSIONS)
    assert (root / "batches" / "b1" / "reports" / "batch_summary.md").exists()


def test_batch_skips_missions_without_selection(batch_ws):
    ws, src = batch_ws
    root = ws.root
    _cli(root, "batch", "create", str(src / "batch.json"))
    # Lock only m1.
    _cli(root, "run", "m1", "--target", "functional-lock")
    _cli(root, "approve", "m1", "brief_approved")
    _cli(root, "approve", "m1", "candidate_selected", "--candidate", "m1.candidate.seed_1997")
    _cli(root, "approve", "m1", "functional_shell_locked")

    r = _cli(root, "batch", "run", "b1", "--target", "presentation")
    assert r.returncode == 0, r.stderr + r.stdout
    assert "1 mission(s)" in r.stdout
    assert "skipped" in r.stdout
