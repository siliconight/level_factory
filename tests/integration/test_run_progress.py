"""The panel's progress counts against the whole plan, from the start, and only moves forward (0.256.0).

The walker, on the first windowed run of the authoring loop: the bar's total kept growing, so its percentage went up
and then down. It counted finished jobs over the jobs the index had met so far. Now `run` writes its plan before it
dispatches anything (`runs/<mission>.json`) and `layouts.index_progress` counts the jobs finished since that run
started against that fixed total. FAILS ON 0.255.0.
"""
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from packages.service import layouts  # noqa: E402
from tests.integration.test_end_to_end import _run_cli, workspace  # noqa: E402,F401


class _Events:
    def __init__(self):
        self.said = []

    def emit(self, stage, status, message="", progress=None):
        self.said.append((message, progress))


def test_run_records_its_plan_and_progress_counts_against_it(workspace):  # noqa: F811
    ws, src = workspace
    root = ws.root
    assert _run_cli(root, "batch", "create", str(src / "batch.json")).returncode == 0
    planned = json.loads(_run_cli(root, "plan", "bank_block_001", "--target", "functional-lock", "--json").stdout)
    before = time.time()
    r = _run_cli(root, "run", "bank_block_001", "--target", "functional-lock")
    assert r.returncode in (0, 1), r.stderr + r.stdout
    record = json.loads((root / ".level_factory" / "runs" / "bank_block_001.json").read_text(encoding="utf-8"))
    assert record["schema"] == "level_factory.run_plan.v1"
    assert sorted(record["jobs"]) == sorted(j["job_id"] for j in planned["jobs"])

    events = _Events()
    layouts.index_progress(root, "bank_block_001", events, "layouts", since=before)
    total = len(record["jobs"])
    assert events.said == [("%d of %d build steps done" % (total, total), 1.0)]

    # a record older than this leg is the last run's: nothing is said
    events = _Events()
    layouts.index_progress(root, "bank_block_001", events, "layouts", since=time.time() + 60)
    assert events.said == []

    # a job the index holds from before this run started does not count as done in it
    later = dict(record, started_at="9999-01-01T00:00:00+00:00")
    path = root / ".level_factory" / "runs" / "bank_block_001.json"
    path.write_text(json.dumps(later), encoding="utf-8")
    os.utime(path, None)
    events = _Events()
    layouts.index_progress(root, "bank_block_001", events, "layouts", since=before)
    assert events.said == [("0 of %d build steps done" % total, 0.0)]
