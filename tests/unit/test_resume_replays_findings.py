"""A second run must still report what the first run found.

`Scheduler.run` used to pre-skip any job the index recorded as succeeded,
appending a fabricated `JobOutcome` whose `issues` defaulted to `[]`. Such a job
never reached `_attempt_job`, so `_normalize` never ran over its outputs and its
findings were lost -- and `cmd_run` then wrote the empty `summary.all_issues`
over the persisted validation file, so the previous run's record was destroyed
by the run that failed to notice it.

These tests pin the two properties that failure violated: a re-run reports the
same findings, and it says out loud that it came from cache rather than
labelling itself `succeeded` as though a tool had run.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from packages.adapters.registry import AdapterRegistry
from packages.adapters.sdk import BaseAdapter, PlannedCommand, ToolProbe
from packages.artifacts.cache import ContentCache
from packages.core import states
from packages.core.models import Job
from packages.jobs.scheduler import Scheduler
from packages.pipeline.graph import JobGraph
from packages.project_store.index import Index

CODE = "TRAVERSAL"


class _FindingAdapter(BaseAdapter):
    """Succeeds, writes one output, and always reports one non-blocking finding.

    Non-blocking on purpose: a blocking issue fails the job, and a failed job
    was never the case in question. The defect was a job that SUCCEEDED while
    carrying findings.
    """

    adapter_id = "fake_findings"
    adapter_version = "0.1.0"
    capabilities = frozenset({"x"})
    output_contract_version = "fake.0.1"
    tally: Path | None = None          # every tool invocation appends one byte

    def probe(self, installation):
        return ToolProbe(True, "0.1.0", None, {}, self.capabilities)

    def validate_configuration(self, job_spec, context):
        return []

    def plan_commands(self, job_spec, context):
        work = Path(str(context["work_dir"]))
        py = context.get("python_executable") or "python3"
        script = (f"open({str(work / 'report.json')!r}, 'w').write('{{}}'); "
                  f"open({str(self.tally)!r}, 'a').write('x')")
        return [PlannedCommand(
            executable=Path(str(py)), arguments=("-c", script),
            working_directory=work, expected_outputs=("report.json",),
            resource_class="lightweight", timeout_seconds=30,
        )]

    def normalize_validation(self, output_paths):
        return [{"code": CODE, "severity": "major", "category": "traversal",
                 "message": "the crew could not reach the objective",
                 "blocking": False}]


def _run(tmp_path, **kwargs):
    """One full `run` against a workspace that persists across calls."""
    adapter = _FindingAdapter()
    adapter.tally = tmp_path / "invocations.log"
    index = Index(tmp_path / "index.sqlite")
    sched = Scheduler(
        index=index,
        cache=ContentCache(tmp_path / "cache"),
        registry=AdapterRegistry({"fake_findings": adapter}),
        jobs_dir=tmp_path / "jobs",
        installation={"repositories": {"fake_findings": str(tmp_path)},
                      "python_executable": sys.executable},
    )
    graph = JobGraph()
    graph.add(Job(job_id="m.fake", mission_id="m", stage_id="s",
                  adapter_id="fake_findings"))
    try:
        return sched.run(graph, job_specs={"m.fake": {"seed": 1}},
                         mission_id="m", **kwargs)
    finally:
        index.close()


def _invocations(tmp_path) -> int:
    log = tmp_path / "invocations.log"
    return len(log.read_text()) if log.exists() else 0


def test_first_run_reports_the_finding(tmp_path):
    summary = _run(tmp_path)
    assert [i.code for i in summary.all_issues] == [CODE]
    assert summary.outcomes[0].job.status == states.SUCCEEDED
    assert _invocations(tmp_path) == 1


def test_second_run_reports_the_same_finding(tmp_path):
    _run(tmp_path)
    again = _run(tmp_path)
    # The regression: this was [] and the CLI printed "total findings: 0".
    assert [i.code for i in again.all_issues] == [CODE]


def test_second_run_does_not_re_run_the_tool(tmp_path):
    _run(tmp_path)
    _run(tmp_path)
    # Replaying findings must not cost a rebuild -- that is what the cache is
    # for. If this ever reads 2, resume got correct by getting expensive.
    assert _invocations(tmp_path) == 1


def test_second_run_says_it_came_from_cache(tmp_path):
    _run(tmp_path)
    outcome = _run(tmp_path).outcomes[0]
    # `cmd_run` prints `"cache" if o.cache_hit else o.job.status.lower()`. The
    # pre-skip left cache_hit False on a job recorded SUCCEEDED, so the stage
    # line read "succeeded" for work that never happened.
    assert outcome.cache_hit is True
    assert outcome.job.status == states.SKIPPED_CACHE_HIT


def test_force_changes_nothing(tmp_path):
    _run(tmp_path)
    forced = _run(tmp_path, force=True)
    # `--force` used to be the only way to get an honest re-run. It is now
    # indistinguishable from the default, which is the point.
    assert [i.code for i in forced.all_issues] == [CODE]
    assert _invocations(tmp_path) == 1


def test_every_job_appears_exactly_once_in_the_outcomes(tmp_path):
    _run(tmp_path)
    again = _run(tmp_path)
    # The pre-skip appended its fabricated outcome before the dispatch loop
    # could append a real one, so any path that both pre-skipped and dispatched
    # would double-count a job in the summary the CLI prints and aggregates.
    assert [o.job.job_id for o in again.outcomes] == ["m.fake"]
