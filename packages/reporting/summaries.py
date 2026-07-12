"""Mission and batch reports (TDD 32).

Deterministic Markdown + JSON summaries. Mission summary (32.1) covers a single
mission's brief, selection, validation, lock status, and handoff contents. Batch
summary (32.2) is the batch mission-status matrix, shared asset packs,
tool-version consistency, failed/stale/handoff-ready buckets, and the batch
build lock.
"""
from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass, field


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat()


@dataclass
class MissionSummary:
    mission_id: str
    selected_candidate: str | None
    seeds: list[int]
    tool_versions: dict
    validation: str
    functional_lock: str
    handoff_ready: bool
    presentation_ready: bool
    remaining_runtime: list[str] = field(default_factory=lambda: [
        "Gameplay runtime", "Networking", "Enemy AI"])

    def as_dict(self) -> dict:
        return {
            "schema": "level_factory.mission_summary.v0.1",
            "created_at": _now(),
            "mission_id": self.mission_id,
            "selected_candidate": self.selected_candidate,
            "seeds": self.seeds,
            "tool_versions": self.tool_versions,
            "validation": self.validation,
            "functional_lock": self.functional_lock,
            "handoff_ready": self.handoff_ready,
            "presentation_ready": self.presentation_ready,
            "remaining_runtime_responsibilities": self.remaining_runtime,
        }

    def to_markdown(self) -> str:
        lines = [
            f"# Mission Summary — {self.mission_id}", "",
            f"- Selected candidate: {self.selected_candidate or '(none)'}",
            f"- Seeds: {', '.join(map(str, self.seeds))}",
            f"- Functional lock: {self.functional_lock}",
            f"- Validation: {self.validation}",
            f"- Presentation: {'ready' if self.presentation_ready else 'pending'}",
            f"- Handoff: {'ready' if self.handoff_ready else 'pending'}", "",
            "## Tool versions",
        ]
        for tool, ver in sorted(self.tool_versions.items()):
            lines.append(f"- {tool}: {ver}")
        lines += ["", "## Remaining runtime responsibilities (by design)"]
        lines += [f"- {r}" for r in self.remaining_runtime]
        return "\n".join(lines) + "\n"


@dataclass
class BatchSummary:
    batch_id: str
    mission_rows: list[dict]  # {mission_id, state, validation, handoff, presentation, selected}
    shared_packs: list[str]
    tool_versions: dict
    tool_version_consistent: bool
    build_lock: str

    @property
    def handoff_ready(self) -> list[str]:
        return [r["mission_id"] for r in self.mission_rows if r.get("handoff") == "ready"]

    @property
    def failed_or_stale(self) -> list[str]:
        return [r["mission_id"] for r in self.mission_rows
                if r.get("state") in ("FAILED", "BLOCKED", "stale")]

    def as_dict(self) -> dict:
        return {
            "schema": "level_factory.batch_summary.v0.1",
            "created_at": _now(),
            "batch_id": self.batch_id,
            "mission_status_matrix": self.mission_rows,
            "shared_asset_packs": self.shared_packs,
            "tool_versions": self.tool_versions,
            "tool_version_consistent": self.tool_version_consistent,
            "handoff_ready_missions": self.handoff_ready,
            "failed_or_stale_missions": self.failed_or_stale,
            "batch_build_lock": self.build_lock,
        }

    def to_markdown(self) -> str:
        lines = [f"# Batch Summary — {self.batch_id}", "",
                 f"- Build lock: {self.build_lock}",
                 f"- Shared asset packs: {', '.join(self.shared_packs) or '(none)'}",
                 f"- Tool versions consistent: {self.tool_version_consistent}",
                 f"- Handoff-ready: {', '.join(self.handoff_ready) or '(none)'}",
                 f"- Failed/stale: {', '.join(self.failed_or_stale) or '(none)'}",
                 "", "## Mission status matrix", "",
                 "| Mission | State | Presentation | Handoff | Selected | Validation |",
                 "|---|---|---|---|---|---|"]
        for r in self.mission_rows:
            lines.append(
                f"| {r['mission_id']} | {r.get('state','?')} | "
                f"{r.get('presentation','?')} | {r.get('handoff','?')} | "
                f"{r.get('selected') or '-'} | {r.get('validation','')} |")
        return "\n".join(lines) + "\n"
