"""Approval gates and functional lock (TDD 23).

Human gates are first-class (TDD 5.5). Metrics compare candidates; they never
select one. Selection, functional lock, exception acceptance, and final handoff
are explicit, recorded approvals tied to an exact artifact fingerprint. If a
protected input changes, the approval goes stale.
"""
from __future__ import annotations

import datetime as _dt
from pathlib import Path

from packages.core.canonical import pretty_dumps
from packages.core.errors import ApprovalBlockedError
from packages.core.hashing import hash_json
from packages.core.models import Approval

# Required gates in lifecycle order (TDD 23.1).
BRIEF_APPROVED = "brief_approved"
CANDIDATE_SELECTED = "candidate_selected"
FUNCTIONAL_SHELL_LOCKED = "functional_shell_locked"
PRESENTATION_APPROVED = "presentation_approved"
REGRESSION_APPROVED = "regression_approved"
HANDOFF_APPROVED = "handoff_approved"

REQUIRED_GATES = (
    BRIEF_APPROVED,
    CANDIDATE_SELECTED,
    FUNCTIONAL_SHELL_LOCKED,
    PRESENTATION_APPROVED,
    REGRESSION_APPROVED,
    HANDOFF_APPROVED,
)

DECISION_APPROVED = "approved"
DECISION_REJECTED = "rejected"


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat()


def gate_fingerprint(protected_inputs: dict) -> str:
    """The fingerprint an approval is bound to (TDD 23.2)."""
    return hash_json(protected_inputs)


class ApprovalStore:
    """Approvals live under each mission's ``approvals/`` folder as JSON."""

    def __init__(self, approvals_dir: Path) -> None:
        self.dir = approvals_dir
        self.dir.mkdir(parents=True, exist_ok=True)

    def _path(self, mission_id: str, gate: str) -> Path:
        return self.dir / f"{mission_id}.{gate}.json"

    def record(
        self,
        *,
        mission_id: str,
        gate: str,
        decision: str,
        approved_by: str,
        protected_inputs: dict,
        notes: str = "",
        accepted_issue_ids: list[str] | None = None,
    ) -> Approval:
        if gate not in REQUIRED_GATES:
            raise ApprovalBlockedError(f"unknown gate '{gate}'")
        fp = gate_fingerprint(protected_inputs)
        approval = Approval(
            approval_id=f"{mission_id}.{gate}",
            mission_id=mission_id,
            gate=gate,
            decision=decision,
            approved_by=approved_by,
            timestamp=_now(),
            artifact_fingerprint=fp,
            notes=notes,
            accepted_issue_ids=list(accepted_issue_ids or []),
        )
        self._path(mission_id, gate).write_text(
            pretty_dumps(approval.as_dict()), encoding="utf-8"
        )
        return approval

    def get(self, mission_id: str, gate: str) -> Approval | None:
        p = self._path(mission_id, gate)
        if not p.exists():
            return None
        import json

        return Approval(**json.loads(p.read_text(encoding="utf-8")))

    def is_approved(self, mission_id: str, gate: str, protected_inputs: dict) -> bool:
        """True only when an approval exists AND is not stale (TDD 23.2)."""
        approval = self.get(mission_id, gate)
        if approval is None or approval.decision != DECISION_APPROVED:
            return False
        return approval.artifact_fingerprint == gate_fingerprint(protected_inputs)

    def require(self, mission_id: str, gate: str, protected_inputs: dict) -> Approval:
        approval = self.get(mission_id, gate)
        if approval is None:
            raise ApprovalBlockedError(
                f"gate '{gate}' for '{mission_id}' has no approval yet"
            )
        if approval.decision != DECISION_APPROVED:
            raise ApprovalBlockedError(
                f"gate '{gate}' for '{mission_id}' was rejected"
            )
        if approval.artifact_fingerprint != gate_fingerprint(protected_inputs):
            raise ApprovalBlockedError(
                f"approval for gate '{gate}' is stale: protected inputs changed"
            )
        return approval
