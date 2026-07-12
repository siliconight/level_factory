"""Phase-5 advanced review & CI end-to-end (TDD 42).

Drives the CLI through: team quorum sign-off on final handoff, accepting a
non-blocking exception, a visual review, writing CI templates, and tagging a
release in a real git repo.
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


@pytest.fixture()
def ws(tmp_path):
    w = init_workspace(tmp_path / "ws", project_id="t", name="P5")
    w.write_json(w.tools_local, {
        "python_executable": sys.executable,
        "godot_executable": str(FIXTURES / "bin" / "godot"),
        "blender_executable": str(FIXTURES / "bin" / "godot"),
        "repositories": {r: str(FIXTURES / "repos" / r) for r in _REPOS},
    })
    (w.shared_dir / "pixelcoat" / "recipes").mkdir(parents=True)
    (w.shared_dir / "pixelcoat" / "recipes" / "b.json").write_text('{"recipe":"b"}')
    src = tmp_path / "src"
    (src / "briefs").mkdir(parents=True)
    (src / "batch.json").write_text(json.dumps({
        "schema": "level_factory.batch.v0.1", "batch_id": "b1", "name": "B",
        "seed_base": 1997, "theme_family": "delco_1997", "missions": ["m1"]}))
    (src / "briefs" / "m1.json").write_text(json.dumps({
        "schema": "level_factory.mission_brief.v0.1", "mission_id": "m1",
        "display_name": "M1", "archetype": "urban_bank", "building_count": 1,
        "site_shape": "street_block", "route_shape": "push_then_backtrack",
        "candidate_count": 3, "target_minutes": [25, 35], "theme": "delco_1997",
        "time_of_day": "afternoon"}))
    return w, src


def _cli(root, *args):
    return subprocess.run(
        [sys.executable, str(ROOT / "apps" / "cli" / "main.py"), "-C", str(root), *args],
        capture_output=True, text=True)


def _advance_to_presentation(root, src):
    assert _cli(root, "batch", "create", str(src / "batch.json")).returncode == 0
    _cli(root, "run", "m1", "--target", "functional-lock")
    _cli(root, "approve", "m1", "brief_approved")
    _cli(root, "approve", "m1", "candidate_selected", "--candidate", "m1.candidate.seed_1997")
    _cli(root, "approve", "m1", "functional_shell_locked")
    _cli(root, "run", "m1", "--target", "presentation")


def test_team_quorum_on_handoff(ws):
    w, src = ws
    _advance_to_presentation(w.root, src)
    # Default handoff quorum is 2.
    r = _cli(w.root, "team-sign", "m1", "handoff_approved", "--by", "alice")
    assert "1 more needed" in r.stdout
    r = _cli(w.root, "team-sign", "m1", "handoff_approved", "--by", "bob")
    assert "satisfied" in r.stdout
    r = _cli(w.root, "team-status", "m1", "handoff_approved")
    assert r.returncode == 0
    assert json.loads(r.stdout)["satisfied"] is True


def test_accept_exception_and_review_and_ci(ws):
    w, src = ws
    _advance_to_presentation(w.root, src)

    # Inject a non-blocking issue and accept it.
    vfile = w.internal_dir / "validation" / "m1.json"
    data = json.loads(vfile.read_text())
    data["issues"].append({"code": "PACING_LOW", "issue_id": "m1#pace",
                           "severity": "minor", "blocking": False,
                           "category": "pacing", "message": "low", "source_tool": "lot"})
    vfile.write_text(json.dumps(data))
    r = _cli(w.root, "accept-exception", "m1", "--issue", "PACING_LOW",
             "--by", "alice", "--reason", "backtrack padding covers it")
    assert r.returncode == 0, r.stderr
    accepted = json.loads((w.internal_dir / "exceptions" / "m1.accepted_exceptions.json").read_text())
    assert accepted[0]["issue_id"] == "m1#pace"

    # Visual review writes an HTML + JSON artifact.
    r = _cli(w.root, "review", "m1")
    assert r.returncode == 0, r.stderr
    assert (w.internal_dir / "review" / "m1" / "visual_review.html").exists()

    # CI templates land in the workspace.
    r = _cli(w.root, "ci-init")
    assert r.returncode == 0
    assert (w.root / ".github" / "workflows" / "level-factory.yml").exists()
    assert (w.root / "ci" / "run.sh").exists()


def test_release_tags_git_repo(ws):
    w, src = ws
    _advance_to_presentation(w.root, src)
    root = w.root
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    subprocess.run(["git", "-C", str(root), "config", "user.email", "t@t.co"], check=True)
    subprocess.run(["git", "-C", str(root), "config", "user.name", "t"], check=True)
    subprocess.run(["git", "-C", str(root), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(root), "commit", "-qm", "init"], check=True)

    r = _cli(root, "release", "b1", "--tag", "v0.1.0-b1")
    assert r.returncode == 0, r.stderr
    assert (root / "batches" / "b1" / "reports" / "release.json").exists()
    tags = subprocess.run(["git", "-C", str(root), "tag", "--list"],
                          capture_output=True, text=True).stdout
    assert "v0.1.0-b1" in tags
