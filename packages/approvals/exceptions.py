"""Accepted exceptions (TDD 23.3, AC11).

A non-blocking issue may be accepted with an approver, timestamp, written reason,
the exact issue id, and the exact artifact fingerprint (optional expiration and
follow-up ticket). An acceptance goes STALE when the related artifact's
fingerprint changes or the expiration passes (TDD 23.4 staleness). Blocking
issues can never be accepted this way.
"""
from __future__ import annotations

import datetime as _dt
import json
from dataclasses import dataclass, field
from pathlib import Path

from packages.core.canonical import pretty_dumps


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat()


class ExceptionError(Exception):
    pass


@dataclass
class AcceptedException:
    issue_id: str
    approver: str
    reason: str
    artifact_fingerprint: str
    timestamp: str = field(default_factory=_now)
    expires_at: str | None = None
    follow_up_ticket: str | None = None

    def as_dict(self) -> dict:
        return self.__dict__.copy()

    def is_stale(self, current_fingerprint: str, *, now: str | None = None) -> bool:
        if self.artifact_fingerprint != current_fingerprint:
            return True
        if self.expires_at:
            return (now or _now()) >= self.expires_at
        return False


class ExceptionStore:
    def __init__(self, root: Path) -> None:
        self.dir = root
        self.dir.mkdir(parents=True, exist_ok=True)

    def _path(self, mission_id: str) -> Path:
        return self.dir / f"{mission_id}.accepted_exceptions.json"

    def load(self, mission_id: str) -> list[AcceptedException]:
        p = self._path(mission_id)
        if not p.exists():
            return []
        return [AcceptedException(**d) for d in json.loads(p.read_text(encoding="utf-8"))]

    def accept(self, *, mission_id: str, issue: dict, approver: str, reason: str,
               artifact_fingerprint: str, expires_at: str | None = None,
               follow_up_ticket: str | None = None) -> AcceptedException:
        if issue.get("blocking"):
            raise ExceptionError(
                f"issue '{issue.get('code')}' is blocking and cannot be accepted")
        if not reason.strip():
            raise ExceptionError("an accepted exception requires a written reason")
        exc = AcceptedException(
            issue_id=issue.get("issue_id") or issue.get("code", ""),
            approver=approver, reason=reason,
            artifact_fingerprint=artifact_fingerprint,
            expires_at=expires_at, follow_up_ticket=follow_up_ticket)
        existing = [e for e in self.load(mission_id) if e.issue_id != exc.issue_id]
        existing.append(exc)
        self._path(mission_id).write_text(
            pretty_dumps([e.as_dict() for e in existing]), encoding="utf-8")
        return exc

    def active(self, mission_id: str, fingerprints_by_issue: dict[str, str]) -> list[AcceptedException]:
        """Exceptions that are still valid against current artifact fingerprints."""
        out = []
        for e in self.load(mission_id):
            current = fingerprints_by_issue.get(e.issue_id, e.artifact_fingerprint)
            if not e.is_stale(current):
                out.append(e)
        return out

    def stale(self, mission_id: str, fingerprints_by_issue: dict[str, str]) -> list[AcceptedException]:
        out = []
        for e in self.load(mission_id):
            current = fingerprints_by_issue.get(e.issue_id, e.artifact_fingerprint)
            if e.is_stale(current):
                out.append(e)
        return out
