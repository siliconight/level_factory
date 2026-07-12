"""A blocking normalized issue must stop the job (no false completion)."""
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


class _BlockingAdapter(BaseAdapter):
    adapter_id = "fake_block"
    adapter_version = "0.1.0"
    capabilities = frozenset({"x"})
    output_contract_version = "fake.0.1"

    def probe(self, installation):
        return ToolProbe(True, "0.1.0", None, {}, self.capabilities)

    def validate_configuration(self, job_spec, context):
        return []

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
        return [{"code": "LADDER_NO_ROLE", "severity": "blocker",
                 "category": "traversal", "message": "hard error", "blocking": True}]


def test_blocking_issue_blocks_job(tmp_path):
    index = Index(tmp_path / "index.sqlite")
    cache = ContentCache(tmp_path / "cache")
    registry = AdapterRegistry({"fake_block": _BlockingAdapter()})
    sched = Scheduler(
        index=index, cache=cache, registry=registry, jobs_dir=tmp_path / "jobs",
        installation={"repositories": {"fake_block": str(tmp_path)},
                      "python_executable": sys.executable},
    )
    graph = JobGraph()
    job = Job(job_id="m.fake", mission_id="m", stage_id="s", adapter_id="fake_block")
    graph.add(job)

    summary = sched.run(graph, job_specs={"m.fake": {"seed": 1}}, mission_id="m")
    assert summary.blocked_job == "m.fake"
    assert not summary.succeeded
    outcome = summary.outcomes[0]
    assert outcome.job.status == states.BLOCKED
    assert any(i.blocking for i in outcome.issues)
