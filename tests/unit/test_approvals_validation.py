"""Unit tests: approvals/gates + validation model (TDD 22, 23)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from packages.approvals import gates
from packages.core.models import ValidationIssue
from packages.validation.model import (
    FORBIDDEN_COMPLETION_LABELS, aggregate, issue_from_normalized, readiness_label,
)


def test_approval_records_and_detects_staleness(tmp_path):
    store = gates.ApprovalStore(tmp_path / "approvals")
    protected = {"functional_signature": {"archetype": "bank"}}
    store.record(mission_id="m1", gate=gates.CANDIDATE_SELECTED,
                 decision=gates.DECISION_APPROVED, approved_by="b$",
                 protected_inputs=protected)
    assert store.is_approved("m1", gates.CANDIDATE_SELECTED, protected)
    # Changing a protected input makes the approval stale.
    changed = {"functional_signature": {"archetype": "warehouse"}}
    assert not store.is_approved("m1", gates.CANDIDATE_SELECTED, changed)


def test_require_raises_when_missing(tmp_path):
    store = gates.ApprovalStore(tmp_path / "approvals")
    from packages.core.errors import ApprovalBlockedError
    import pytest
    with pytest.raises(ApprovalBlockedError):
        store.require("m1", gates.HANDOFF_APPROVED, {"x": 1})


def test_rejected_gate_is_not_approved(tmp_path):
    store = gates.ApprovalStore(tmp_path / "approvals")
    store.record(mission_id="m1", gate=gates.BRIEF_APPROVED,
                 decision=gates.DECISION_REJECTED, approved_by="b$",
                 protected_inputs={"x": 1})
    assert not store.is_approved("m1", gates.BRIEF_APPROVED, {"x": 1})


def test_aggregate_and_no_false_completion():
    issues = [
        ValidationIssue(issue_id="a", source_tool="lot", mission_id="m1",
                        severity="blocker", category="collision", code="C1",
                        message="", blocking=True),
        ValidationIssue(issue_id="b", source_tool="deli_counter", mission_id="m1",
                        severity="minor", category="geometry", code="G1", message=""),
    ]
    agg = aggregate(issues)
    assert agg["has_blockers"]
    assert agg["total"] == 2
    assert readiness_label(agg).startswith("Blocked")
    # The label must never claim fun/balance/network.
    assert readiness_label(aggregate([])) not in FORBIDDEN_COMPLETION_LABELS


def test_accepted_exception_clears_blocker():
    issues = [ValidationIssue(issue_id="a", source_tool="lot", mission_id="m1",
                              severity="blocker", category="collision", code="C1",
                              message="", blocking=True)]
    agg = aggregate(issues, accepted_issue_ids=frozenset({"a"}))
    assert not agg["has_blockers"]
    assert "a" in agg["accepted"]


def test_issue_from_normalized_defaults_blocking_from_severity():
    issue = issue_from_normalized(
        {"code": "X", "severity": "blocker", "category": "handoff", "message": "m"},
        source_tool="dispatch", mission_id="m1", candidate_id=None, stage_id=None,
    )
    assert issue.blocking is True
