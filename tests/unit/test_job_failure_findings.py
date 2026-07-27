"""A job that stopped must say why in the findings, not only on the job row.

Guards the defect where a pre-flight refusal, a nonzero tool exit or a missing
output produced ZERO findings: the tool wrote no report, `normalize_validation`
had nothing to read, and the mission finished with `total findings: 0`. The
Validation Center then printed "Structural checks passed" over a mission whose
level had never been built -- byte-identical to a clean run.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from packages.adapters.registry import AdapterRegistry
from packages.adapters.sdk import BaseAdapter, PlannedCommand, ToolProbe
from packages.artifacts.cache import ContentCache
from packages.core import states
from packages.core.errors import (
    CANCELLED, INPUT_VALIDATION_ERROR, OUTPUT_CONTRACT_ERROR, TIMEOUT,
    TOOL_EXIT_FAILURE, VALIDATION_BLOCKER,
)
from packages.core.models import Job
from packages.jobs.scheduler import Scheduler
from packages.pipeline.graph import JobGraph
from packages.project_store.index import Index
from packages.validation.job_failure import issues_for_failure
from packages.validation.model import CATEGORIES, aggregate, readiness_label


# --------------------------------------------------------------------------
# The translation itself
# --------------------------------------------------------------------------
def _mk(**kw):
    base = dict(failure_class=TOOL_EXIT_FAILURE, message="tool exited 1",
                source_tool="laser_tag", job_id="m.lt", mission_id="m")
    base.update(kw)
    return issues_for_failure(**base)


def test_a_failed_job_produces_a_blocking_finding():
    issues = _mk()
    assert len(issues) == 1
    assert issues[0].blocking and issues[0].severity == "blocker"


def test_each_preflight_objection_is_its_own_finding():
    issues = _mk(failure_class=INPUT_VALIDATION_ERROR, message="a; b; c",
                 problems=["a", "b", "c"])
    assert [i.message for i in issues] == ["a", "b", "c"]


def test_the_preflight_message_survives_intact():
    text = ("17 of 18 mission point(s) have no ground beneath them: "
            "LT_PlayerSpawn, LT_Objective; Laser Tag would refuse the map "
            "with NO_WORLD_COLLISION and complete zero runs")
    assert _mk(failure_class=INPUT_VALIDATION_ERROR, problems=[text])[0].message == text


def test_blank_objections_do_not_become_empty_findings():
    issues = _mk(failure_class=INPUT_VALIDATION_ERROR, message="real",
                 problems=["", "   ", "real"])
    assert [i.message for i in issues] == ["real"]


def test_a_failure_with_nothing_to_say_still_names_its_class():
    issues = _mk(failure_class=TIMEOUT, message="")
    assert TIMEOUT in issues[0].message


def test_two_candidates_failing_the_same_way_are_two_findings():
    a = _mk(job_id="m.lt.seed_1", candidate_id="seed_1")[0]
    b = _mk(job_id="m.lt.seed_2", candidate_id="seed_2")[0]
    assert a.issue_id != b.issue_id
    assert len(aggregate([a, b])["blocking_open"]) == 2


def test_a_cancelled_job_is_not_a_defect():
    assert _mk(failure_class=CANCELLED) == []


def test_a_validation_blocker_is_not_restated():
    # It already arrived as a normalized finding of its own; a second copy
    # would double-count it in the aggregate.
    assert _mk(failure_class=VALIDATION_BLOCKER) == []


def test_every_failure_class_lands_in_a_known_category():
    for fc in (INPUT_VALIDATION_ERROR, TOOL_EXIT_FAILURE, TIMEOUT,
               OUTPUT_CONTRACT_ERROR, "some_class_added_later"):
        assert _mk(failure_class=fc)[0].category in CATEGORIES


def test_a_finding_says_where_to_look():
    issue = _mk(job_id="m.lt.seed_5017", log_path="/jobs/m.lt.seed_5017/1/job.log")[0]
    assert issue.location == "m.lt.seed_5017"
    assert issue.raw_source_path.endswith("job.log")
    assert issue.suggested_fix


def test_the_finding_survives_the_round_trip_through_validate():
    from packages.validation.model import issue_from_normalized

    original = _mk(failure_class=INPUT_VALIDATION_ERROR, problems=["no ground"])[0]
    revived = issue_from_normalized(
        original.as_dict(), source_tool="laser_tag", mission_id="m",
        candidate_id=None, stage_id=None)
    assert revived.issue_id == original.issue_id
    assert revived.message == "no ground" and revived.blocking


# --------------------------------------------------------------------------
# The label that was making the claim
# --------------------------------------------------------------------------
def test_an_unfinished_run_never_reports_structural_checks_passed():
    assert readiness_label(aggregate([]), run_completed=False).startswith("Blocked")


def test_a_finished_clean_run_still_passes():
    assert readiness_label(aggregate([])) == "Structural checks passed"


# --------------------------------------------------------------------------
# ...and the scheduler actually wires it
# --------------------------------------------------------------------------
class _Adapter(BaseAdapter):
    adapter_id = "fake_fail"
    adapter_version = "0.1.0"
    capabilities = frozenset({"x"})
    output_contract_version = "fake.0.1"
    problems: list[str] = []
    script = "open('out.txt', 'w').write('x')"

    def probe(self, installation):
        return ToolProbe(True, "0.1.0", None, {}, self.capabilities)

    def validate_configuration(self, job_spec, context):
        return list(self.problems)

    def plan_commands(self, job_spec, context):
        work = Path(str(context["work_dir"]))
        py = context.get("python_executable") or "python3"
        return [PlannedCommand(
            executable=Path(str(py)), arguments=("-c", self.script),
            working_directory=work, expected_outputs=("out.txt",),
            resource_class="lightweight", timeout_seconds=30,
        )]

    def normalize_validation(self, output_paths):
        return []


def _run(tmp_path, adapter):
    sched = Scheduler(
        index=Index(tmp_path / "index.sqlite"),
        cache=ContentCache(tmp_path / "cache"),
        registry=AdapterRegistry({"fake_fail": adapter}),
        jobs_dir=tmp_path / "jobs",
        installation={"repositories": {"fake_fail": str(tmp_path)},
                      "python_executable": sys.executable},
    )
    graph = JobGraph()
    graph.add(Job(job_id="m.fake", mission_id="m", stage_id="s",
                  adapter_id="fake_fail"))
    return sched.run(graph, job_specs={"m.fake": {"seed": 1}}, mission_id="m")


def test_a_preflight_refusal_reaches_the_mission_findings(tmp_path):
    adapter = _Adapter()
    adapter.problems = ["mission points have no ground beneath them",
                        "godot_executable is not configured"]
    summary = _run(tmp_path, adapter)

    assert summary.blocked_job == "m.fake"
    assert summary.outcomes[0].job.status == states.FAILED
    messages = [i.message for i in summary.all_issues]
    assert messages == adapter.problems
    assert aggregate(summary.all_issues)["has_blockers"]


def test_a_tool_that_exits_nonzero_is_not_a_silent_pass(tmp_path):
    adapter = _Adapter()
    adapter.script = "raise SystemExit(3)"
    summary = _run(tmp_path, adapter)

    assert summary.all_issues, "a crashed tool reported nothing at all"
    assert all(i.blocking for i in summary.all_issues)
    assert summary.all_issues[0].code == "JOB_TOOL_EXIT"


def test_a_tool_that_writes_nothing_is_not_a_silent_pass(tmp_path):
    adapter = _Adapter()
    adapter.script = "pass"  # exits 0, promises out.txt, delivers nothing
    summary = _run(tmp_path, adapter)

    assert summary.all_issues[0].code == "JOB_OUTPUT_MISSING"
    assert "out.txt" in summary.all_issues[0].message


def test_a_clean_job_adds_no_failure_findings(tmp_path):
    summary = _run(tmp_path, _Adapter())
    assert summary.succeeded
    assert summary.all_issues == []
