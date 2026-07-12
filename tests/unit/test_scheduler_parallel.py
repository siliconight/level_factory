"""Parallel scheduler behavior (TDD 19.2, Phase 4)."""
import sys
import threading
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from packages.core import states  # noqa: E402
from packages.core.models import Job  # noqa: E402
from packages.jobs.scheduler import Scheduler  # noqa: E402
from packages.pipeline.graph import JobGraph  # noqa: E402


class _RecordingScheduler(Scheduler):
    """Overrides _execute_job to record concurrency without touching real tools."""

    def __init__(self, concurrency, delay=0.05):
        self.concurrency = dict(concurrency)
        self.jobs_dir = Path("/tmp")
        self._delay = delay
        self._lock = threading.Lock()
        self.peak_by_class = {}
        self.running_by_class = {}
        # minimal attrs used by run()
        class _Idx:
            def get_job(self, jid):
                return None
        self.index = _Idx()

    def _execute_job(self, job, job_spec, cancel):
        from packages.jobs.scheduler import JobOutcome
        cls = job.resource_class
        with self._lock:
            self.running_by_class[cls] = self.running_by_class.get(cls, 0) + 1
            self.peak_by_class[cls] = max(self.peak_by_class.get(cls, 0),
                                          self.running_by_class[cls])
        time.sleep(self._delay)
        with self._lock:
            self.running_by_class[cls] -= 1
        job.status = states.SUCCEEDED
        return JobOutcome(job=job)


def _independent_graph(n, resource_class):
    g = JobGraph()
    for i in range(n):
        g.add(Job(job_id=f"j{i}", mission_id="m", stage_id="s",
                  adapter_id="a", resource_class=resource_class))
    return g


def test_independent_jobs_run_in_parallel():
    sched = _RecordingScheduler({"python_cpu": 4})
    g = _independent_graph(8, "python_cpu")
    summary = sched.run(g, job_specs={}, mission_id="m")
    assert summary.succeeded
    assert len(summary.outcomes) == 8
    # Peak concurrency should reach the cap (4), proving real parallelism.
    assert sched.peak_by_class["python_cpu"] >= 2
    assert sched.peak_by_class["python_cpu"] <= 4


def test_resource_cap_is_respected():
    sched = _RecordingScheduler({"blender": 1})
    g = _independent_graph(4, "blender")
    sched.run(g, job_specs={}, mission_id="m")
    # blender cap is 1 → never more than one at a time.
    assert sched.peak_by_class["blender"] == 1


def test_dependencies_are_ordered():
    sched = _RecordingScheduler({"python_cpu": 4})
    g = JobGraph()
    g.add(Job(job_id="a", mission_id="m", stage_id="s", adapter_id="a",
              resource_class="python_cpu"))
    g.add(Job(job_id="b", mission_id="m", stage_id="s", adapter_id="a",
              resource_class="python_cpu", depends_on=["a"]))
    summary = sched.run(g, job_specs={}, mission_id="m")
    order = [o.job.job_id for o in summary.outcomes]
    assert order.index("a") < order.index("b")


def test_failure_fails_fast_but_drains():
    class _Failing(_RecordingScheduler):
        def _execute_job(self, job, job_spec, cancel):
            from packages.jobs.scheduler import JobOutcome
            if job.job_id == "bad":
                job.status = states.FAILED
                return JobOutcome(job=job)
            return super()._execute_job(job, job_spec, cancel)

    sched = _Failing({"python_cpu": 4})
    g = JobGraph()
    g.add(Job(job_id="bad", mission_id="m", stage_id="s", adapter_id="a",
              resource_class="python_cpu"))
    g.add(Job(job_id="downstream", mission_id="m", stage_id="s", adapter_id="a",
              resource_class="python_cpu", depends_on=["bad"]))
    summary = sched.run(g, job_specs={}, mission_id="m")
    assert summary.blocked_job == "bad"
    # downstream never runs because its dependency failed.
    assert "downstream" not in [o.job.job_id for o in summary.outcomes]
