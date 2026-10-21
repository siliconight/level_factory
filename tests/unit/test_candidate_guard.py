"""`approve candidate_selected` refuses a candidate the mission's plan never builds (0.228.0, the factory's roadmap 278).

The factory's cold run 9362 named seed 9281 against a batch whose seed_base was 9054. The approve WARNED -- "no
bank_block_001.lot_assemble.candidate.seed_9281 yet; the selection is recorded and will resolve once that job runs" --
and recorded it, and the functional lock refused it a step later as protecting nothing. A mission's candidates are its
batch's (`planner.derive_seeds`) before any job runs, so membership is not the ordering question the warning leaves
open. These build a workspace's batch and brief in a temporary folder; nothing runs a tool.
"""
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from apps.cli import commands
from packages.project_store.workspace import Workspace

M = "bank_block_001"


@pytest.fixture()
def ws(tmp_path):
    root = tmp_path / "ws"
    batch = root / "batches" / "cold_9362"
    (batch / "missions" / M / "brief").mkdir(parents=True)
    (batch / "batch.json").write_text(json.dumps({"batch_id": "cold_9362", "seed_base": 9054,
                                                  "missions": [M]}), encoding="utf-8")
    (batch / "missions" / M / "brief" / "brief.json").write_text(
        json.dumps({"mission_id": M, "display_name": "Bank block", "candidate_count": 3}), encoding="utf-8")
    (root / "factory.project.json").write_text(json.dumps({"name": "test"}), encoding="utf-8")
    return Workspace(root=root)


def test_a_seed_the_plan_never_builds_is_refused_and_the_planned_ones_named(ws, capsys):
    """FAILS ON 0.227.0, which warned and recorded the selection."""
    assert commands._refuse_bad_candidate(ws, M, M + ".candidate.seed_9281") == commands.EXIT_BLOCKED
    err = capsys.readouterr().err
    assert "not one of bank_block_001's candidates (seed_9054, seed_9155, seed_9256)" in err, err
    assert "nothing is recorded" in err


def test_a_planned_seed_passes_and_is_warned_about_until_its_job_runs(ws, capsys):
    """The ordering question stays open: a planned candidate selected before the shell leg is recorded, with the
    warning, and once its lot_assemble job exists the warning goes."""
    assert commands._refuse_bad_candidate(ws, M, M + ".candidate.seed_9155") == commands.EXIT_OK
    assert "WARNING no bank_block_001.lot_assemble.candidate.seed_9155 yet" in capsys.readouterr().err
    (ws.jobs_dir / (M + ".lot_assemble.candidate.seed_9155")).mkdir(parents=True)
    assert commands._refuse_bad_candidate(ws, M, M + ".candidate.seed_9155") == commands.EXIT_OK
    assert "WARNING" not in capsys.readouterr().err


def test_a_malformed_id_is_still_refused(ws, capsys):
    assert commands._refuse_bad_candidate(ws, M, M + ".candidate.seed_XXXX") == commands.EXIT_BLOCKED
    assert "expected bank_block_001.candidate.seed_<number>" in capsys.readouterr().err


def test_a_mission_no_batch_holds_keeps_the_warning(tmp_path, capsys):
    """No plan to ask, so the old path: the shape passes and the warning prints."""
    empty = Workspace(root=tmp_path / "empty")
    assert commands._refuse_bad_candidate(empty, "nowhere_001", "nowhere_001.candidate.seed_1") == commands.EXIT_OK
    assert "WARNING" in capsys.readouterr().err


def test_approve_records_nothing_for_a_refused_seed(ws):
    """Through `cmd_approve`: refused before `store.record`, so no approved gate and no selection marker."""
    args = SimpleNamespace(chdir=str(ws.root), mission_id=M, gate="candidate_selected",
                           candidate=M + ".candidate.seed_9281", by="test", note="")
    assert commands.cmd_approve(args) == commands.EXIT_BLOCKED
    approvals = ws.internal_dir / "approvals"
    assert not (approvals / (M + ".selected")).exists()
    assert not any(approvals.glob("*")) if approvals.exists() else True
