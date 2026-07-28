"""A candidate that fails is eliminated; the run carries on.

Five candidates are generated so the weak ones can be dropped. Mission-wide
fail-fast defeated that: one blocked job halted the whole DAG, so a candidate
was never eliminated -- it took its siblings down with it, their jobs never
dispatched, and their `out/` directories kept the previous run's artifacts where
the next reader mistook them for current answers. That is exactly how a Laser
Tag finding on seed 5320 caused seed 5320's own walktest to be skipped for an
evening and read as a passing geometry check.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from packages.core import states  # noqa: E402
from packages.core.models import Job  # noqa: E402
from packages.jobs.scheduler import JobOutcome, Scheduler  # noqa: E402
from packages.pipeline.graph import JobGraph  # noqa: E402


class _Sched(Scheduler):
    def __init__(self, fail=()):
        self.concurrency = {"python_cpu": 4}
        self.jobs_dir = Path("/tmp")
        self._fail = set(fail)

        class _Idx:
            def get_job(self, jid):
                return None
        self.index = _Idx()

    def _execute_job(self, job, job_spec, cancel):
        job.status = states.FAILED if job.job_id in self._fail else states.SUCCEEDED
        return JobOutcome(job=job)


def _five_candidates():
    """Two stages per candidate, plus one mission-level job at the end."""
    g = JobGraph()
    for seed in (5017, 5118, 5219, 5320, 5421):
        cid = f"candidate.seed_{seed}"
        g.add(Job(job_id=f"eval.{cid}", mission_id="m", stage_id="eval",
                  adapter_id="lt", candidate_id=cid, resource_class="python_cpu"))
        g.add(Job(job_id=f"walk.{cid}", mission_id="m", stage_id="walk",
                  adapter_id="wt", candidate_id=cid, resource_class="python_cpu",
                  depends_on=[f"eval.{cid}"]))
    return g


def _ran(summary):
    return {o.job.job_id for o in summary.outcomes}


def test_one_bad_candidate_does_not_stop_the_other_four():
    sched = _Sched(fail={"eval.candidate.seed_5320"})
    summary = sched.run(_five_candidates(), job_specs={}, mission_id="m")
    ran = _ran(summary)
    for seed in (5017, 5118, 5219, 5421):
        assert f"walk.candidate.seed_{seed}" in ran, seed
    assert summary.blocked_job is None


def test_the_eliminated_candidate_is_named_with_the_job_that_did_it():
    sched = _Sched(fail={"eval.candidate.seed_5320"})
    summary = sched.run(_five_candidates(), job_specs={}, mission_id="m")
    assert summary.eliminated_candidates == {
        "candidate.seed_5320": "eval.candidate.seed_5320"}


def test_the_eliminated_candidates_own_downstream_does_not_run():
    sched = _Sched(fail={"eval.candidate.seed_5320"})
    summary = sched.run(_five_candidates(), job_specs={}, mission_id="m")
    assert "walk.candidate.seed_5320" not in _ran(summary)
    assert "walk.candidate.seed_5320" in summary.never_dispatched


def test_a_job_that_did_not_run_says_why():
    """The list alone is not enough. "Never ran" reads as a defect until you
    know whether it was the point."""
    sched = _Sched(fail={"eval.candidate.seed_5320"})
    summary = sched.run(_five_candidates(), job_specs={}, mission_id="m")
    why = summary.not_run_reason["walk.candidate.seed_5320"]
    assert "candidate.seed_5320 was eliminated" in why
    assert "eval.candidate.seed_5320" in why


def test_a_mission_level_failure_still_stops_the_run():
    """The concession is narrow. A job with no candidate_id is not a candidate
    to drop -- nothing downstream of it can be salvaged by carrying on."""
    g = JobGraph()
    g.add(Job(job_id="site", mission_id="m", stage_id="site", adapter_id="a",
              resource_class="python_cpu"))
    g.add(Job(job_id="after", mission_id="m", stage_id="after", adapter_id="a",
              resource_class="python_cpu", depends_on=["site"]))
    sched = _Sched(fail={"site"})
    summary = sched.run(g, job_specs={}, mission_id="m")
    assert summary.blocked_job == "site"
    assert "after" in summary.never_dispatched
    assert "the run stopped at site" in summary.not_run_reason["after"]


def test_every_candidate_failing_is_not_a_blocked_run_either():
    """Five eliminations is a mission with nothing to select from, and that is
    a decision for candidate selection to make out loud rather than something
    the scheduler should disguise as a crash."""
    sched = _Sched(fail={f"eval.candidate.seed_{s}"
                         for s in (5017, 5118, 5219, 5320, 5421)})
    summary = sched.run(_five_candidates(), job_specs={}, mission_id="m")
    assert summary.blocked_job is None
    assert len(summary.eliminated_candidates) == 5
    assert len(summary.never_dispatched) == 5


def test_nothing_is_eliminated_when_nothing_fails():
    sched = _Sched()
    summary = sched.run(_five_candidates(), job_specs={}, mission_id="m")
    assert summary.eliminated_candidates == {}
    assert summary.never_dispatched == []
    assert summary.not_run_reason == {}
    assert summary.succeeded
