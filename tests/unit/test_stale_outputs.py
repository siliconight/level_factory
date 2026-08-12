"""A job's outputs are exactly what this run produced.

`work_dir` is `<job>/<attempt>/out`, and attempt 1 is attempt 1 on every run,
so the directory was reused indefinitely. Anything a previous run wrote and the
next one did not survived -- and `collect_outputs` rglobs the tree, so the
leftover was ADOPTED as an output of this run: published to `out/`, hashed into
the artifact record, cached, and read by everything downstream.

Measured 2026-08-09 on `bank_branch_a04`: `prop_rockay_01_w160.glb` dated
08-04, sitting in a compose output whose every other module came from that
day's build, re-skinned and re-imported by the packaging step as though it were
current. `module_extents.py --sweep` reported it as a dimension mismatch and
the investigation started at Zoo, which had no bug.

The repo had already paid for this once from the other end: `_without_provenance`
exists because the same rglob swept up the previous run's provenance sidecars
and wrote a sidecar for each, adding a level of nesting per run until a path
passed Windows' MAX_PATH and killed a run before any stage did work. That fix
filtered the symptom. This one removes the cause.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from packages.jobs.scheduler import Scheduler


def _sched(tmp_path: Path) -> Scheduler:
    return Scheduler(index=None, cache=None, registry=None,
                     jobs_dir=tmp_path / "jobs", installation={})


def test_publish_prunes_what_this_run_no_longer_produces(tmp_path):
    """The falsifier. `out/` is what downstream jobs read."""
    s = _sched(tmp_path)
    work = tmp_path / "work"
    (work / "art" / "zoo").mkdir(parents=True)
    fresh = work / "art" / "zoo" / "wall_rockay_01_w200.glb"
    fresh.write_bytes(b"new")

    stable = s._stable_out("j1")
    (stable / "art" / "zoo").mkdir(parents=True)
    orphan = stable / "art" / "zoo" / "prop_rockay_01_w160.glb"
    orphan.write_bytes(b"five days old")

    s._publish_stable("j1", work, [fresh])

    assert (stable / "art" / "zoo" / "wall_rockay_01_w200.glb").is_file()
    assert not orphan.exists(), "a module this run did not build is still published"


def test_publish_keeps_everything_this_run_did_produce(tmp_path):
    """The clean case. A pruner that removes too much is worse than none."""
    s = _sched(tmp_path)
    work = tmp_path / "work"
    (work / "sub").mkdir(parents=True)
    files = [work / "a.glb", work / "sub" / "b.glb", work / "sub" / "c.json"]
    for f in files:
        f.write_bytes(b"x")

    s._publish_stable("j2", work, files)
    stable = s._stable_out("j2")
    assert sorted(p.relative_to(stable).as_posix()
                  for p in stable.rglob("*") if p.is_file()) == [
        "a.glb", "sub/b.glb", "sub/c.json"]

    # Re-publishing the same set changes nothing.
    s._publish_stable("j2", work, files)
    assert len([p for p in stable.rglob("*") if p.is_file()]) == 3


def test_a_republished_file_is_the_new_content(tmp_path):
    """Pruning must not be confused with replacing."""
    s = _sched(tmp_path)
    work = tmp_path / "work"
    work.mkdir()
    f = work / "site.tscn"

    f.write_text("first")
    s._publish_stable("j3", work, [f])
    f.write_text("second")
    s._publish_stable("j3", work, [f])

    assert (s._stable_out("j3") / "site.tscn").read_text() == "second"
