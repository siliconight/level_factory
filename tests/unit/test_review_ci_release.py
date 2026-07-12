"""Visual review, CI templates, release helper, worker abstraction (Phase 5)."""
import struct
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from packages.review.visual import compare_presentation
from packages.ci.templates import render_templates
from packages.release.scm import is_clean, tag_release, ReleaseError
from packages.jobs.workers import JobEnvelope, JobResult, FakeRemoteWorker
from packages.core.models import Job


def _png(path: Path, w: int, h: int, tag: bytes = b""):
    header = b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\x0dIHDR" + struct.pack(">II", w, h)
    path.write_bytes(header + tag)


def test_visual_review_detects_added_and_changed(tmp_path):
    after = tmp_path / "after"; after.mkdir()
    _png(after / "preview_calm.png", 320, 240, b"A")
    _png(after / "preview_alarm.png", 320, 240, b"B")
    # No before dir → both states are new.
    review = compare_presentation("m1", before_dir=None, after_dir=after)
    statuses = {c.state: c.status for c in review.comparisons}
    assert statuses["calm"] == "added"
    assert set(review.as_dict()["changed_states"]) == {"calm", "alarm"}

    before = tmp_path / "before"; before.mkdir()
    _png(before / "preview_calm.png", 320, 240, b"A")   # identical
    _png(before / "preview_alarm.png", 320, 240, b"OLD")  # different
    review2 = compare_presentation("m1", before_dir=before, after_dir=after)
    st2 = {c.state: c.status for c in review2.comparisons}
    assert st2["calm"] == "unchanged"
    assert st2["alarm"] == "changed"


def test_visual_review_reads_png_dimensions(tmp_path):
    after = tmp_path / "after"; after.mkdir()
    _png(after / "preview_calm.png", 640, 360)
    review = compare_presentation("m1", before_dir=None, after_dir=after)
    calm = next(c for c in review.comparisons if c.state == "calm")
    assert calm.after["dimensions"] == [640, 360]


def test_ci_templates_render_valid_shape():
    templates = render_templates()
    assert ".github/workflows/level-factory.yml" in templates
    assert "ci/run.sh" in templates
    wf = templates[".github/workflows/level-factory.yml"]
    assert "batch run" in wf and "portability-test" in wf
    assert templates["ci/run.sh"].startswith("#!/usr/bin/env bash")


def test_release_tags_clean_repo_and_rejects_dirty(tmp_path):
    repo = tmp_path / "repo"; repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "t@t.co"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "t"], check=True)
    (repo / "f.txt").write_text("hi")
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-qm", "init"], check=True)

    assert is_clean(repo)
    rec = tag_release(repo, batch_id="b1", tag="v1", message="m")
    assert rec.tag == "v1" and rec.commit
    # Second identical tag fails.
    try:
        tag_release(repo, batch_id="b1", tag="v1", message="m")
        assert False, "expected duplicate tag to fail"
    except ReleaseError:
        pass
    # Dirty tree is rejected.
    (repo / "dirty.txt").write_text("x")
    try:
        tag_release(repo, batch_id="b1", tag="v2", message="m")
        assert False, "expected dirty tree to fail"
    except ReleaseError:
        pass


def test_worker_envelope_round_trips():
    job = Job(job_id="j1", mission_id="m", stage_id="s", adapter_id="pixelcoat")
    env = JobEnvelope(job=job, job_spec={"theme": "d"}, repository="/r", work_dir="/w")
    seen = {}

    def execute(e):
        seen["job_id"] = e.job.job_id
        return JobResult(job_id=e.job.job_id, status="SUCCEEDED", exit_code=0)

    result = FakeRemoteWorker(execute=execute).run(env)
    assert result.status == "SUCCEEDED"
    assert seen["job_id"] == "j1"
    # Envelope survives serialization.
    back = JobEnvelope.from_dict(env.as_dict())
    assert back.job.adapter_id == "pixelcoat" and back.job_spec == {"theme": "d"}
