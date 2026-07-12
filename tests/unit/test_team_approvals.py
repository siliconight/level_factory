"""Team approvals + accepted exceptions (TDD 23.3, Phase 5)."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from packages.approvals.team import TeamApprovalStore
from packages.approvals.exceptions import ExceptionStore, ExceptionError


def test_quorum_requires_multiple_distinct_approvers(tmp_path):
    store = TeamApprovalStore(tmp_path / "team", quorum={"handoff_approved": 2})
    inputs = {"functional_signature": "abc"}
    store.sign(mission_id="m1", gate="handoff_approved", approver="alice",
               protected_inputs=inputs)
    st = store.status("m1", "handoff_approved", inputs)
    assert not st.satisfied and st.remaining == 1
    # Same approver signing again does not add to the quorum.
    store.sign(mission_id="m1", gate="handoff_approved", approver="alice",
               protected_inputs=inputs)
    assert not store.is_satisfied("m1", "handoff_approved", inputs)
    # A second distinct approver satisfies it.
    store.sign(mission_id="m1", gate="handoff_approved", approver="bob",
               protected_inputs=inputs)
    assert store.is_satisfied("m1", "handoff_approved", inputs)


def test_signoffs_go_stale_when_protected_inputs_change(tmp_path):
    store = TeamApprovalStore(tmp_path / "team", quorum={"g": 1})
    store.sign(mission_id="m1", gate="g", approver="alice",
               protected_inputs={"sig": "v1"})
    assert store.is_satisfied("m1", "g", {"sig": "v1"})
    # Protected inputs changed → the sign-off is now stale, not current.
    st = store.status("m1", "g", {"sig": "v2"})
    assert not st.satisfied
    assert len(st.stale_signoffs) == 1


def test_blocking_issue_cannot_be_accepted(tmp_path):
    store = ExceptionStore(tmp_path / "exc")
    with pytest.raises(ExceptionError):
        store.accept(mission_id="m1",
                     issue={"code": "HARD", "blocking": True},
                     approver="alice", reason="x", artifact_fingerprint="fp")


def test_exception_requires_reason(tmp_path):
    store = ExceptionStore(tmp_path / "exc")
    with pytest.raises(ExceptionError):
        store.accept(mission_id="m1", issue={"code": "SOFT", "blocking": False},
                     approver="alice", reason="   ", artifact_fingerprint="fp")


def test_exception_goes_stale_on_fingerprint_change(tmp_path):
    store = ExceptionStore(tmp_path / "exc")
    store.accept(mission_id="m1",
                 issue={"issue_id": "i1", "code": "SOFT", "blocking": False},
                 approver="alice", reason="ok", artifact_fingerprint="fp_v1")
    assert store.active("m1", {"i1": "fp_v1"})
    assert not store.active("m1", {"i1": "fp_v2"})  # artifact changed
    assert store.stale("m1", {"i1": "fp_v2"})
