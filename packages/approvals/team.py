"""Team approvals — multi-party gate sign-off (TDD 42 Phase 5).

A gate can require more than one approver (a quorum). Each approver's sign-off is
recorded individually and bound to the gate's protected-input fingerprint, so a
protected-input change invalidates every sign-off (staleness is inherited from
the single-approver model, TDD 23.2). A gate is satisfied only when the number
of current (non-stale) approvals from distinct approvers meets the quorum.

Decision 8 (TDD 45): final handoff may require a second approver — model this as
a per-gate quorum policy rather than special-casing handoff.
"""
from __future__ import annotations

import datetime as _dt
import json
from dataclasses import dataclass, field
from pathlib import Path

from packages.core.canonical import pretty_dumps
from packages.core.hashing import hash_json

DEFAULT_QUORUM = {
    "brief_approved": 1,
    "candidate_selected": 1,
    "functional_shell_locked": 1,
    "presentation_approved": 1,
    "regression_approved": 1,
    "handoff_approved": 2,  # final handoff needs a second approver by default
}


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat()


@dataclass
class Signoff:
    approver: str
    timestamp: str
    fingerprint: str
    note: str = ""

    def as_dict(self) -> dict:
        return self.__dict__.copy()


@dataclass
class GateStatus:
    gate: str
    quorum: int
    current_signoffs: list[Signoff]
    stale_signoffs: list[Signoff] = field(default_factory=list)

    @property
    def satisfied(self) -> bool:
        distinct = {s.approver for s in self.current_signoffs}
        return len(distinct) >= self.quorum

    @property
    def remaining(self) -> int:
        return max(0, self.quorum - len({s.approver for s in self.current_signoffs}))

    def as_dict(self) -> dict:
        return {
            "gate": self.gate, "quorum": self.quorum,
            "satisfied": self.satisfied, "remaining": self.remaining,
            "current_signoffs": [s.as_dict() for s in self.current_signoffs],
            "stale_signoffs": [s.as_dict() for s in self.stale_signoffs],
        }


class TeamApprovalStore:
    """Per-gate list of individual sign-offs under ``team_approvals/``."""

    def __init__(self, root: Path, quorum: dict[str, int] | None = None) -> None:
        self.dir = root
        self.dir.mkdir(parents=True, exist_ok=True)
        self.quorum = dict(quorum or DEFAULT_QUORUM)

    def _path(self, mission_id: str, gate: str) -> Path:
        return self.dir / f"{mission_id}.{gate}.signoffs.json"

    def _load(self, mission_id: str, gate: str) -> list[Signoff]:
        p = self._path(mission_id, gate)
        if not p.exists():
            return []
        return [Signoff(**d) for d in json.loads(p.read_text(encoding="utf-8"))]

    def sign(self, *, mission_id: str, gate: str, approver: str,
             protected_inputs: dict, note: str = "") -> Signoff:
        fp = hash_json(protected_inputs)
        signoffs = self._load(mission_id, gate)
        # One current sign-off per approver: replace theirs if it exists.
        signoffs = [s for s in signoffs if s.approver != approver]
        so = Signoff(approver=approver, timestamp=_now(), fingerprint=fp, note=note)
        signoffs.append(so)
        self._path(mission_id, gate).write_text(
            pretty_dumps([s.as_dict() for s in signoffs]), encoding="utf-8")
        return so

    def revoke(self, *, mission_id: str, gate: str, approver: str) -> None:
        signoffs = [s for s in self._load(mission_id, gate) if s.approver != approver]
        self._path(mission_id, gate).write_text(
            pretty_dumps([s.as_dict() for s in signoffs]), encoding="utf-8")

    def status(self, mission_id: str, gate: str, protected_inputs: dict) -> GateStatus:
        fp = hash_json(protected_inputs)
        current, stale = [], []
        for s in self._load(mission_id, gate):
            (current if s.fingerprint == fp else stale).append(s)
        return GateStatus(gate=gate, quorum=self.quorum.get(gate, 1),
                          current_signoffs=current, stale_signoffs=stale)

    def is_satisfied(self, mission_id: str, gate: str, protected_inputs: dict) -> bool:
        return self.status(mission_id, gate, protected_inputs).satisfied
