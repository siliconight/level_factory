"""A job spec can be finished at dispatch, and Lot's site spec is (0.144.2).

COLD RUN 9171 (county_hospital_001, the breadth sweep) could not export. Its
site spec was written at plan time, before the Deli Counter job generated the
building it places, so `shell_footprint` had nothing to read and the plate and
spacing fell back to `DEFAULT_FOOTPRINT`: the candidates were judged on a
100 x 108 m plate. `run --art` re-planned after the shell existed, measured it
and wrote a 93 x 71 m site, the selected candidate re-assembled after the
functional lock, and the export refused the drift.

These pin both halves: the scheduler runs a spec's `prepare` at dispatch,
after the job's dependencies have succeeded, and Lot's spec builder hands it
one that writes the site spec again.

Run:  python -m pytest tests/unit/test_site_spec_at_dispatch.py -q
"""
import inspect
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from packages.adapters.registry import AdapterRegistry  # noqa: E402
from packages.adapters.sdk import BaseAdapter, PlannedCommand, ToolProbe  # noqa: E402
from packages.artifacts.cache import ContentCache  # noqa: E402
from packages.core import states  # noqa: E402
from packages.core.models import Job  # noqa: E402
from packages.jobs.scheduler import Scheduler  # noqa: E402
from packages.pipeline.graph import JobGraph  # noqa: E402
from packages.project_store.index import Index  # noqa: E402


class _Adapter(BaseAdapter):
    """Writes `shell.glb`, and records the spec each job was planned with."""

    adapter_id = "fake_prepare"
    adapter_version = "0.1.0"
    capabilities = frozenset({"x"})
    output_contract_version = "fake.0.1"

    def probe(self, installation):
        return ToolProbe(True, "0.1.0", None, {}, self.capabilities)

    def validate_configuration(self, job_spec, context):
        return []

    def plan_commands(self, job_spec, context):
        self.seen[job_spec.get("name")] = dict(job_spec)
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


def _run(tmp_path, b_spec):
    """Job b depends on job a, which builds `shell.glb`."""
    adapter = _Adapter()
    adapter.seen = {}
    sched = Scheduler(
        index=Index(tmp_path / "index.sqlite"), cache=ContentCache(tmp_path / "cache"),
        registry=AdapterRegistry({adapter.adapter_id: adapter}),
        jobs_dir=tmp_path / "jobs",
        installation={"repositories": {adapter.adapter_id: str(tmp_path)},
                      "python_executable": sys.executable},
    )
    graph = JobGraph()
    graph.add(Job(job_id="m.a", mission_id="m", stage_id="a",
                  adapter_id=adapter.adapter_id))
    graph.add(Job(job_id="m.b", mission_id="m", stage_id="b",
                  adapter_id=adapter.adapter_id, depends_on=["m.a"]))
    summary = sched.run(graph, job_specs={"m.a": {"name": "a"}, "m.b": b_spec},
                        mission_id="m")
    return summary, adapter


# ---------------------------------------------------------------------------
# the scheduler half
# ---------------------------------------------------------------------------
def test_prepare_runs_at_dispatch_after_its_dependency_and_its_spec_is_the_one_used(tmp_path):
    """FAILS BEFORE 0.144.2: nothing ran `prepare`, so job b ran on the spec
    as planned -- which for Lot was a site sized before its building existed."""
    built = tmp_path / "jobs" / "m.a" / "1" / "out" / "shell.glb"
    calls = []

    def prepare(spec):
        calls.append(built.exists())
        return {**{k: v for k, v in spec.items() if k != "prepare"}, "measured": True}

    summary, adapter = _run(tmp_path, {"name": "b", "prepare": prepare})
    assert summary.succeeded, [(o.job.job_id, o.job.status) for o in summary.outcomes]
    assert calls == [True], "once, and only after the job it depends on had built"
    assert adapter.seen["b"].get("measured") is True
    assert "prepare" not in adapter.seen["b"]


def test_a_prepare_that_raises_fails_its_job_and_not_the_run(tmp_path):
    def prepare(spec):
        raise RuntimeError("the shell was never built")

    summary, adapter = _run(tmp_path, {"name": "b", "prepare": prepare})
    by_id = {o.job.job_id: o for o in summary.outcomes}
    assert by_id["m.a"].job.status == states.SUCCEEDED
    assert by_id["m.b"].job.status == states.FAILED
    assert "b" not in adapter.seen, "the tool never ran on an unfinished spec"


# ---------------------------------------------------------------------------
# the Lot half
# ---------------------------------------------------------------------------
def test_the_site_spec_is_written_again_from_the_same_arguments(tmp_path, monkeypatch):
    from apps.cli import commands
    calls = []

    def fake_write(ws, model, deli_out, **kw):
        calls.append((ws, model, deli_out, kw))
        return tmp_path / "site.json"

    monkeypatch.setattr(commands, "_write_site_spec", fake_write)
    spec = {"site_spec_path": str(tmp_path / "site.json"), "walkable": True,
            "skins_dir": "batch-merged", "prepare": object()}
    out = commands._site_spec_at_dispatch("ws", "model", "deli", spec,
                                          seed=9208, themed_scene=None)
    # everything the scheduler handed in, a batch's merged keys included,
    # and no prepare
    assert out == {"site_spec_path": str(tmp_path / "site.json"),
                   "walkable": True, "skins_dir": "batch-merged"}
    assert calls == [("ws", "model", "deli", {"seed": 9208, "themed_scene": None})]


def test_a_site_spec_that_would_land_somewhere_else_refuses(tmp_path, monkeypatch):
    from apps.cli import commands
    monkeypatch.setattr(commands, "_write_site_spec",
                        lambda *a, **k: tmp_path / "elsewhere.json")
    with pytest.raises(RuntimeError, match="moved between plan and dispatch"):
        commands._site_spec_at_dispatch(
            "ws", "model", "deli", {"site_spec_path": str(tmp_path / "site.json")},
            seed=1)


def test_the_plan_attaches_it_to_every_lot_job_that_writes_a_site_spec():
    from apps.cli import commands
    src = inspect.getsource(commands._job_specs_for_plan)
    lot = src[src.index('elif job.adapter_id == "lot":'):
              src.index('elif job.adapter_id == "walktest":')]
    assert "_write_site_spec(" in lot
    assert '"prepare"' in lot and "_site_spec_at_dispatch" in lot
