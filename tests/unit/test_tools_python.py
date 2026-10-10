"""The tools' interpreter is named in one place and the doctor asks it (0.167.0, roadmap 202).

Until 0.167.0 a blank `python_executable` ran jobs under `python3` and the Deli Counter and
Dispatch probes under `python`, and `doctor`'s "python" check read the interpreter running
Level Factory instead of either. These hold the three to one answer and the doctor to the
interpreter the tools actually run under.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from packages.adapters.registry import AdapterRegistry
from packages.adapters.sdk import BaseAdapter, PlannedCommand, ToolProbe
from packages.artifacts.cache import ContentCache
from packages.core.models import Job
from packages.jobs.scheduler import Scheduler
from packages.pipeline.graph import JobGraph
from packages.project_store.index import Index
from packages.tools import doctor, interpreter

NOWHERE = str(Path(__file__).resolve().parent / "no_such_interpreter_here.exe")


def _check(report, name):
    found = [c for c in report.checks if c.name == name]
    assert len(found) == 1, [c.name for c in report.checks]
    return found[0]


def test_a_blank_python_executable_is_the_interpreter_running_level_factory():
    assert interpreter.tools_python({}) == sys.executable
    assert interpreter.tools_python({"python_executable": ""}) == sys.executable
    assert interpreter.tools_python({"python_executable": "  "}) == sys.executable
    assert interpreter.tools_python(None) == sys.executable


def test_a_configured_python_executable_is_used_as_given():
    assert interpreter.tools_python({"python_executable": " /x/python3.13 "}) == "/x/python3.13"


def test_the_interpreter_answers_its_version_and_what_it_cannot_import(monkeypatch):
    monkeypatch.setattr(interpreter, "TOOL_IMPORTS", interpreter.TOOL_IMPORTS + (
        ("no_such_module_for_this_test", "no-such-dist", "nobody"),))
    ans = interpreter.ask_tools_python({})
    assert ans["error"] == ""
    assert ans["executable"] == sys.executable and ans["configured"] is False
    assert ans["version"] == tuple(sys.version_info[:3])
    names = [m for m, _d, _r in ans["missing"]]
    assert "no_such_module_for_this_test" in names
    dist = {m: d for m, d, _r in ans["missing"]}
    assert dist["no_such_module_for_this_test"] == "no-such-dist"


def test_an_interpreter_that_does_not_run_is_an_error_not_a_pass():
    ans = interpreter.ask_tools_python({"python_executable": NOWHERE})
    assert ans["error"].startswith("did not run"), ans
    assert ans["version"] is None and ans["missing"] == []


def test_an_answer_in_another_shape_is_an_error_not_a_pass(monkeypatch):
    monkeypatch.setattr(interpreter, "_ASK", "print('hello')\n")
    ans = interpreter.ask_tools_python({})
    assert ans["error"].startswith("did not answer"), ans
    assert ans["version"] is None


def test_the_doctor_asks_the_tools_interpreter_not_its_own():
    report = doctor.run_doctor({"python_executable": NOWHERE}, {},
                               registry=AdapterRegistry({}))
    # Level Factory's own interpreter is fine; the tools' does not exist.
    assert _check(report, "python").status == doctor.PASS
    tools = _check(report, "tools_python")
    assert tools.status == doctor.FAIL
    assert NOWHERE in tools.detail and "did not run" in tools.detail
    assert report.worst == doctor.FAIL


def test_the_doctor_names_what_the_tools_interpreter_cannot_import(monkeypatch):
    monkeypatch.setattr(interpreter, "TOOL_IMPORTS", interpreter.TOOL_IMPORTS + (
        ("no_such_module_for_this_test", "no-such-dist", "nobody"),))
    report = doctor.run_doctor({}, {}, registry=AdapterRegistry({}))
    tools = _check(report, "tools_python")
    assert tools.status == doctor.FAIL
    assert "no_such_module_for_this_test" in tools.detail
    assert "-m pip install" in tools.detail and "no-such-dist" in tools.detail
    assert "python_executable blank" in tools.detail


class _Recorder(BaseAdapter):
    adapter_id = "fake_record"
    adapter_version = "0.1.0"
    capabilities = frozenset({"x"})
    output_contract_version = "fake.0.1"
    seen: list = []

    def probe(self, installation):
        return ToolProbe(True, "0.1.0", None, {}, self.capabilities)

    def validate_configuration(self, job_spec, context):
        return []

    def plan_commands(self, job_spec, context):
        self.seen.append(context["python_executable"])
        work = Path(str(context["work_dir"]))
        script = f"open({str(work / 'out.txt')!r}, 'w').write('x')"
        return [PlannedCommand(
            executable=Path(str(context["python_executable"])), arguments=("-c", script),
            working_directory=work, expected_outputs=("out.txt",),
            resource_class="lightweight", timeout_seconds=30,
        )]

    def normalize_validation(self, output_paths):
        return []


def test_a_job_with_a_blank_python_executable_runs_under_this_interpreter(tmp_path):
    rec = _Recorder()
    rec.seen = []
    sched = Scheduler(
        index=Index(tmp_path / "index.sqlite"), cache=ContentCache(tmp_path / "cache"),
        registry=AdapterRegistry({"fake_record": rec}), jobs_dir=tmp_path / "jobs",
        installation={"repositories": {"fake_record": str(tmp_path)},
                      "python_executable": ""},
    )
    graph = JobGraph()
    graph.add(Job(job_id="m.rec", mission_id="m", stage_id="s", adapter_id="fake_record"))
    summary = sched.run(graph, job_specs={"m.rec": {"seed": 1}}, mission_id="m")
    assert rec.seen == [sys.executable]
    assert summary.succeeded, [o.job.status for o in summary.outcomes]


def _probe_argv(adapter_id, monkeypatch, tmp_path):
    from packages.adapters import sdk
    seen = []
    monkeypatch.setattr(sdk.BaseAdapter, "run_contract_probe",
                        staticmethod(lambda argv, cwd=None: seen.append(list(argv)) or None))
    monkeypatch.setattr(sdk.BaseAdapter, "probe",
                        lambda self, inst: ToolProbe(True, "0.1.0", None, {}, frozenset()))
    adapter = AdapterRegistry().get(adapter_id)
    adapter.probe({"repository": str(tmp_path), "python_executable": ""})
    return seen


def test_the_deli_counter_and_dispatch_probes_use_the_same_interpreter(monkeypatch, tmp_path):
    for adapter_id in ("deli_counter", "dispatch"):
        seen = _probe_argv(adapter_id, monkeypatch, tmp_path)
        assert seen and seen[0][0] == sys.executable, (adapter_id, seen)
