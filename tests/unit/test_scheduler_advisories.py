"""An advisory reaches the report and never stops the build.

`validate_configuration` and `advise_configuration` differ by authority, not by
subject: the first says the tool cannot produce information from these inputs,
the second says it will run fine and mark the result down. That distinction is
only worth anything if it is enforced somewhere an adapter cannot reach, which
is why the forcing lives in the scheduler and why it is pinned here rather than
in the adapters that use it.

Two rules, both of which the pipeline got wrong before this existed:

* an adapter cannot promote an advisory into a gate by mislabelling its
  severity -- a firefight evaluator grading a map down is a design signal, and
  answering it with a refusal stops the level existing long enough to improve;
* an advisory survives every way the attempt can end, refusal included.
  Dropping them on the failure path would mean the only runs that never explain
  what is wrong with a map are the runs that went worst.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from packages.adapters.registry import AdapterRegistry  # noqa: E402
from packages.adapters.sdk import (  # noqa: E402
    BaseAdapter, PlannedCommand, ToolProbe)
from packages.artifacts.cache import ContentCache  # noqa: E402
from packages.core import states  # noqa: E402
from packages.core.models import Job  # noqa: E402
from packages.jobs.scheduler import Scheduler  # noqa: E402
from packages.pipeline.graph import JobGraph  # noqa: E402
from packages.project_store.index import Index  # noqa: E402
from packages.validation import model  # noqa: E402


# ---------------------------------------------------------------------------
# harness
# ---------------------------------------------------------------------------
class _Adapter(BaseAdapter):
    """A job that always builds. Everything under test is in the pre-flight."""

    adapter_id = "fake_advise"
    adapter_version = "0.1.0"
    capabilities = frozenset({"x"})
    output_contract_version = "fake.0.1"

    #: What `advise_configuration` hands over, verbatim. Set per test.
    advisories: list = []
    #: What `validate_configuration` refuses on. Empty means it proceeds.
    refusals: list = []
    #: Set when the advisory pass should raise instead of returning.
    advisory_raises = False

    def probe(self, installation):
        return ToolProbe(True, "0.1.0", None, {}, self.capabilities)

    def validate_configuration(self, job_spec, context):
        return list(self.refusals)

    def advise_configuration(self, job_spec, context):
        if self.advisory_raises:
            raise RuntimeError("the scene walked off")
        # Copies, so a scheduler that mutated its input would be caught by the
        # next test in the file rather than by nothing.
        return [dict(a) for a in self.advisories]

    def plan_commands(self, job_spec, context):
        work = Path(str(context["work_dir"]))
        py = context.get("python_executable") or "python3"
        script = f"open({str(work / 'shell.glb')!r}, 'w').write('x')"
        return [PlannedCommand(
            executable=Path(str(py)), arguments=("-c", script),
            working_directory=work, expected_outputs=("shell.glb",),
            resource_class="lightweight", timeout_seconds=30,
        )]

    def normalize_validation(self, output_paths):
        return []


class _SilentAdapter(_Adapter):
    """No advisory path at all: the channel is optional and stays optional."""

    adapter_id = "fake_silent"

    advise_configuration = None  # type: ignore[assignment]


def _run(tmp_path, adapter, *, spec=None):
    index = Index(tmp_path / "index.sqlite")
    cache = ContentCache(tmp_path / "cache")
    registry = AdapterRegistry({adapter.adapter_id: adapter})
    sched = Scheduler(
        index=index, cache=cache, registry=registry, jobs_dir=tmp_path / "jobs",
        installation={"repositories": {adapter.adapter_id: str(tmp_path),
                                       "lot": str(tmp_path / "lot")},
                      "python_executable": sys.executable},
    )
    graph = JobGraph()
    graph.add(Job(job_id="m.fake", mission_id="m", stage_id="s",
                  adapter_id=adapter.adapter_id))
    return sched.run(graph, job_specs={"m.fake": dict(spec or {"seed": 1})},
                     mission_id="m")


def _codes(outcome) -> list[str]:
    return [i.code for i in outcome.issues]


def _find(outcome, code):
    return [i for i in outcome.issues if i.code == code]


# ---------------------------------------------------------------------------
# the forcing rule
# ---------------------------------------------------------------------------
def test_an_advisory_labelled_a_blocker_still_does_not_block(tmp_path):
    """The rule the whole channel exists to keep.

    An adapter handing over `severity: blocker, blocking: True` on the advisory
    path is not making a decision the scheduler defers to. It is making a
    mistake, and the level gets built anyway.
    """
    adapter = _Adapter()
    adapter.advisories = [{"code": "LT_OPEN_SIGHTLINE", "severity": model.BLOCKER,
                           "category": "combat_structure", "blocking": True,
                           "message": "92 m of open street"}]
    summary = _run(tmp_path, adapter)

    assert summary.blocked_job is None
    assert summary.succeeded
    outcome = summary.outcomes[0]
    assert outcome.job.status == states.SUCCEEDED
    issue = _find(outcome, "LT_OPEN_SIGHTLINE")[0]
    assert issue.blocking is False
    assert issue.severity == model.MAJOR, (
        "demoted rather than dropped: the finding is still worth reading first, "
        "it just is not allowed to be the reason a level does not exist")


def test_an_advisory_keeps_the_severity_it_was_given_when_it_is_not_a_blocker(tmp_path):
    """Only the gate is forced. Reading order is still the adapter's call."""
    adapter = _Adapter()
    adapter.advisories = [{"code": "LT_ENGAGEMENT_DRIFT", "severity": model.MODERATE,
                           "category": "configuration", "message": "45 vs 35"}]
    outcome = _run(tmp_path, adapter).outcomes[0]

    issue = _find(outcome, "LT_ENGAGEMENT_DRIFT")[0]
    assert issue.severity == model.MODERATE
    assert issue.blocking is False


def test_the_advisory_carries_the_fix_and_not_only_the_diagnosis(tmp_path):
    """"Cover near (52.1, -12.4)" is the half somebody can act on."""
    adapter = _Adapter()
    adapter.advisories = [{"code": "LT_OPEN_SIGHTLINE", "severity": model.MODERATE,
                           "category": "combat_structure",
                           "message": "92 m of open street",
                           "suggested_fix": "cover near (0.0, 0.0)"}]
    outcome = _run(tmp_path, adapter).outcomes[0]

    assert _find(outcome, "LT_OPEN_SIGHTLINE")[0].suggested_fix == \
        "cover near (0.0, 0.0)"


def test_the_advisory_is_attributed_to_the_job_that_produced_it(tmp_path):
    """A finding with no mission on it cannot be filed against a candidate."""
    adapter = _Adapter()
    adapter.advisories = [{"code": "LT_OPEN_SIGHTLINE", "severity": model.MODERATE,
                           "category": "combat_structure", "message": "open"}]
    outcome = _run(tmp_path, adapter).outcomes[0]

    issue = _find(outcome, "LT_OPEN_SIGHTLINE")[0]
    assert issue.source_tool == adapter.adapter_id
    assert issue.mission_id == "m"
    assert issue.stage_id == "s"


# ---------------------------------------------------------------------------
# surviving the ways a job ends badly
# ---------------------------------------------------------------------------
def test_a_refused_job_still_reports_what_was_wrong_with_the_map(tmp_path):
    """The run that went worst is the one that most needs to say why.

    A pre-flight refusal and a tactical advisory are answers to different
    questions -- "can this be evaluated at all" and "will it grade badly" -- and
    the second does not stop being true because the first said no.
    """
    adapter = _Adapter()
    adapter.refusals = ["godot_executable is not configured (headless run)"]
    adapter.advisories = [{"code": "LT_OPEN_SIGHTLINE", "severity": model.MODERATE,
                           "category": "combat_structure", "message": "92 m"}]
    summary = _run(tmp_path, adapter)
    outcome = summary.outcomes[0]

    assert outcome.job.status == states.FAILED
    assert "LT_OPEN_SIGHTLINE" in _codes(outcome)
    assert len(_codes(outcome)) > 1, (
        "the refusal itself still travels: the advisory rides alongside it "
        "rather than replacing it")
    assert _find(outcome, "LT_OPEN_SIGHTLINE")[0].blocking is False


def test_the_advisories_come_first(tmp_path):
    """Ordering is not decoration here.

    A reader scanning a failed job reads the top of the list. The refusal says
    what to configure; the advisory says what to build -- and the second is the
    one nobody would have gone looking for.
    """
    adapter = _Adapter()
    adapter.refusals = ["evaluation scene missing: nowhere.tscn"]
    adapter.advisories = [{"code": "LT_ENGAGEMENT_DRIFT", "severity": model.MODERATE,
                           "category": "configuration", "message": "45 vs 35"}]
    outcome = _run(tmp_path, adapter).outcomes[0]

    assert _codes(outcome)[0] == "LT_ENGAGEMENT_DRIFT"


def test_each_advisory_is_reported_once(tmp_path):
    """Slice-assigned rather than appended, so a retry cannot double the list."""
    adapter = _Adapter()
    adapter.advisories = [{"code": "LT_OPEN_SIGHTLINE", "severity": model.MODERATE,
                           "category": "combat_structure", "message": "92 m"},
                          {"code": "LT_MARKER_OFF_FLOOR", "severity": model.MINOR,
                           "category": "spawn", "message": "3 m up"}]
    outcome = _run(tmp_path, adapter).outcomes[0]

    assert _codes(outcome).count("LT_OPEN_SIGHTLINE") == 1
    assert _codes(outcome).count("LT_MARKER_OFF_FLOOR") == 1


# ---------------------------------------------------------------------------
# the channel cannot take a build down
# ---------------------------------------------------------------------------
def test_an_advisory_pass_that_raises_says_so_and_gets_out_of_the_way(tmp_path):
    """Nothing on this path is allowed to be the reason a level is not made.

    Including a bug in the path itself. Swallowing it silently would be worse
    than either alternative: the run would look clean while the tactical
    findings quietly stopped arriving.
    """
    adapter = _Adapter()
    adapter.advisory_raises = True
    summary = _run(tmp_path, adapter)
    outcome = summary.outcomes[0]

    assert summary.succeeded
    assert outcome.job.status == states.SUCCEEDED
    failed = _find(outcome, "ADVISORY_FAILED")
    assert len(failed) == 1
    assert failed[0].severity == model.INFO
    assert failed[0].blocking is False
    assert "RuntimeError" in failed[0].message
    assert "the scene walked off" in failed[0].message


def test_an_adapter_with_nothing_to_say_is_unaffected(tmp_path):
    adapter = _Adapter()
    adapter.advisories = []
    summary = _run(tmp_path, adapter)

    assert summary.succeeded
    assert summary.outcomes[0].issues == []


def test_an_adapter_with_no_advisory_path_is_unaffected(tmp_path):
    """The channel is opt-in: every adapter written before it still runs."""
    summary = _run(tmp_path, _SilentAdapter())

    assert summary.succeeded
    assert summary.outcomes[0].issues == []
