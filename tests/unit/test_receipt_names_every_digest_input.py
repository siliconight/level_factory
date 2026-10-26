"""A job's fingerprint receipt records everything its cache digest hashes, and why it ran again (0.254.0).

The receipt (`fingerprint.last.json`) claimed to record WHAT the cache decision was based on, but carried six of the
digest's twelve components. On the factory's panel trial level a job re-ran with every recorded input byte-identical
and its site spec unchanged: the digest had moved on something the receipt did not say. These tests hold the
receipt to the digest -- recomputing it from the receipt alone must give the recorded digest -- and keep the
previous receipt when the digest moves, so the difference is on disk. FAILS ON 0.253.0.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from packages.adapters.registry import AdapterRegistry  # noqa: E402
from packages.adapters.sdk import BaseAdapter, PlannedCommand, ToolProbe  # noqa: E402
from packages.artifacts.cache import ContentCache  # noqa: E402
from packages.artifacts.provenance import BuildFingerprint  # noqa: E402
from packages.core.models import Job  # noqa: E402
from packages.jobs import receipts  # noqa: E402
from packages.jobs.scheduler import Scheduler  # noqa: E402
from packages.pipeline.graph import JobGraph  # noqa: E402
from packages.project_store.index import Index  # noqa: E402


class _Adapter(BaseAdapter):
    adapter_id = "fake_receipt"
    adapter_version = "0.1.0"
    capabilities = frozenset({"x"})
    output_contract_version = "fake.0.1"
    tally: Path | None = None
    python = "3.14.0"                   # what the probe reports: the knob a re-run turns

    def probe(self, installation):
        return ToolProbe(True, "0.1.0", None, {"python": self.python}, self.capabilities)

    def validate_configuration(self, job_spec, context):
        return []

    def fingerprint_inputs(self, job_spec, context):
        return {"spec": "unchanged"}

    def plan_commands(self, job_spec, context):
        work = Path(str(context["work_dir"]))
        script = (f"open({str(work / 'out.json')!r}, 'w').write('{{}}'); "
                  f"open({str(self.tally)!r}, 'a').write('x')")
        return [PlannedCommand(executable=Path(sys.executable), arguments=("-c", script), working_directory=work,
                               expected_outputs=("out.json",), resource_class="lightweight", timeout_seconds=30)]

    def normalize_validation(self, output_paths):
        return []


def _run(tmp_path, python):
    adapter = _Adapter()
    adapter.tally, adapter.python = tmp_path / "ran.log", python
    index = Index(tmp_path / "index.sqlite")
    sched = Scheduler(index=index, cache=ContentCache(tmp_path / "cache"),
                      registry=AdapterRegistry({"fake_receipt": adapter}), jobs_dir=tmp_path / "jobs",
                      installation={"repositories": {"fake_receipt": str(tmp_path)},
                                    "python_executable": sys.executable})
    graph = JobGraph()
    graph.add(Job(job_id="m.fake", mission_id="m", stage_id="s", adapter_id="fake_receipt"))
    try:
        sched.run(graph, job_specs={"m.fake": {"seed": 1}}, mission_id="m")
    finally:
        index.close()
    return tmp_path / "jobs" / "m.fake"


def _recomputed(receipt):
    fields = {k: v for k, v in receipt["fingerprint"].items() if k != "digest"}
    return BuildFingerprint(**fields).digest()


def test_the_digest_can_be_recomputed_from_the_receipt_alone(tmp_path):
    job = _run(tmp_path, "3.14.0")
    r = receipts.read(job / receipts.LAST)
    assert r["fingerprint"]["executable_versions"] == {"python": "3.14.0"}
    assert _recomputed(r) == r["digest"] == r["fingerprint"]["digest"]


def test_a_cache_hit_keeps_one_receipt_and_says_nothing_moved(tmp_path):
    job = _run(tmp_path, "3.14.0")
    _run(tmp_path, "3.14.0")
    assert (tmp_path / "ran.log").read_text() == "x"                  # one run, one hit
    assert not (job / receipts.PREVIOUS).exists() and receipts.differences(job) is None


def test_a_re_run_keeps_the_previous_receipt_and_names_what_moved(tmp_path):
    job = _run(tmp_path, "3.14.0")
    _run(tmp_path, "3.13.9")                                           # every input the same; the interpreter not
    assert (tmp_path / "ran.log").read_text() == "xx"
    prev, last = receipts.read(job / receipts.PREVIOUS), receipts.read(job / receipts.LAST)
    assert prev["inputs"] == last["inputs"] and prev["digest"] != last["digest"]
    assert receipts.differences(job) == ["/executable_versions/python: 3.14.0 -> 3.13.9"]
    assert _recomputed(prev) == prev["digest"] and _recomputed(last) == last["digest"]


def test_receipts_written_before_they_were_whole_cannot_answer(tmp_path):
    (tmp_path / receipts.PREVIOUS).write_text('{"digest": "a", "inputs": {}}', encoding="utf-8")
    (tmp_path / receipts.LAST).write_text('{"digest": "b", "inputs": {}}', encoding="utf-8")
    assert receipts.differences(tmp_path) is None
