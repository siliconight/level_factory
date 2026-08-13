"""Normalized validation model (TDD 22).

Every tool speaks its own dialect of findings. Adapters translate into this
normalized shape so the Validation Center and gates reason about one model.
"""
from __future__ import annotations

from packages.core.models import ValidationIssue

# Severities (TDD 22.1), most-severe first.
BLOCKER = "blocker"
MAJOR = "major"
MODERATE = "moderate"
MINOR = "minor"
INFO = "info"
SEVERITY_ORDER = (BLOCKER, MAJOR, MODERATE, MINOR, INFO)
_SEV_RANK = {s: i for i, s in enumerate(SEVERITY_ORDER)}

# Categories (TDD 22.2).
CATEGORIES = frozenset(
    {
        "configuration",
        "schema",
        "geometry",
        "collision",
        "traversal",
        "reachability",
        "combat_structure",
        "spawn",
        "navigation",
        "anchor",
        "pacing",
        "presentation",
        "performance",
        "provenance",
        "runtime_requirement",
        "handoff",
    }
)

# Labels we ARE allowed to attach to a passing run (TDD 22.5).
ALLOWED_COMPLETION_LABELS = (
    "Structural checks passed",
    "Shell integration requirements complete",
    "Presentation regression passed",
    "Handoff package complete",
)

# Labels a passing score must NEVER be given (TDD 22.5, 5.7).
FORBIDDEN_COMPLETION_LABELS = frozenset(
    {"Fun", "Balanced", "Multiplayer verified", "Network ready", "Shipping ready"}
)


def severity_rank(severity: str) -> int:
    return _SEV_RANK.get(severity, len(SEVERITY_ORDER))


def issue_from_normalized(
    raw: dict, *, source_tool: str, mission_id: str,
    candidate_id: str | None, stage_id: str | None,
) -> ValidationIssue:
    """Build a ValidationIssue from an adapter's normalized dict."""
    severity = raw.get("severity", INFO)
    code = raw.get("code", "UNSPECIFIED")
    blocking = bool(raw.get("blocking", severity == BLOCKER))
    return ValidationIssue(
        issue_id=raw.get("issue_id") or f"{source_tool}:{code}:{mission_id}",
        source_tool=source_tool,
        mission_id=mission_id,
        candidate_id=candidate_id,
        stage_id=stage_id,
        severity=severity,
        category=raw.get("category", "configuration"),
        code=code,
        message=raw.get("message", ""),
        suggested_fix=raw.get("suggested_fix", ""),
        location=raw.get("location", ""),
        related_shell_ids=list(raw.get("related_shell_ids", [])),
        blocking=blocking,
        raw_source_path=raw.get("raw_source_path"),
    )


def aggregate(issues: list[ValidationIssue],
              accepted_issue_ids: frozenset[str] = frozenset(),
              eliminated_candidates: frozenset[str] = frozenset()) -> dict:
    """Aggregate findings for reporting and gating (TDD 22.4, 22.5).

    `eliminated_candidates` are candidates the scheduler already discarded --
    `SchedulerSummary.eliminated_candidates`. A blocker belonging to one of
    them is reported separately and does NOT count against the mission,
    because the mission is not blocked by a candidate it stopped building.
    N candidates exist so that some can be bad.

    Measured 2026-08-12 on lot_demo_001: one candidate's `dispatch_handoff`
    exited 1, the scheduler eliminated that candidate and carried on, all
    three candidates built, and the summary line still read "Blocked:
    unresolved blocking issues". `blocked_job` was never set. The run that
    continued reported as the run that halted.

    OPT-IN. The default is empty, and with it every blocking issue lands in
    `blocking_open` exactly as before -- a caller that does not know which
    candidates were eliminated gets today's behaviour unchanged, which is the
    safe direction for a gate.
    """
    by_severity: dict[str, int] = {s: 0 for s in SEVERITY_ORDER}
    by_category: dict[str, int] = {}
    by_tool: dict[str, int] = {}
    blocking_open: list[str] = []
    blocking_eliminated: list[str] = []
    accepted: list[str] = []

    for issue in issues:
        by_severity[issue.severity] = by_severity.get(issue.severity, 0) + 1
        by_category[issue.category] = by_category.get(issue.category, 0) + 1
        by_tool[issue.source_tool] = by_tool.get(issue.source_tool, 0) + 1
        if issue.issue_id in accepted_issue_ids:
            accepted.append(issue.issue_id)
        elif issue.blocking:
            if issue.candidate_id in eliminated_candidates:
                blocking_eliminated.append(issue.issue_id)
            else:
                blocking_open.append(issue.issue_id)

    return {
        "by_severity": by_severity,
        "by_category": dict(sorted(by_category.items())),
        "by_tool": dict(sorted(by_tool.items())),
        "blocking_open": sorted(blocking_open),
        # Kept apart, not dropped. A blocker on a discarded candidate is still
        # a real finding about a real defect -- it just is not the mission's
        # to answer for. Folding it into `blocking_open` blocks a run that
        # carried on; deleting it loses the only record of why the candidate
        # went.
        "blocking_eliminated": sorted(blocking_eliminated),
        "accepted": sorted(accepted),
        "has_blockers": len(blocking_open) > 0,
        "total": len(issues),
    }


def readiness_label(aggregation: dict, *, run_completed: bool = True) -> str:
    """A structural-only label. Never claims fun/balance/network (TDD 5.7).

    `run_completed` is the second thing the label depends on and it is not
    visible in the aggregate: a run that stopped at a failed stage has no
    findings from the stages it never reached, so an empty aggregate means
    "nothing was checked" just as readily as "everything checked out". Saying
    "Structural checks passed" over a mission that has no level in it is the
    one sentence this label must never produce.
    """
    if not run_completed:
        return "Blocked: the run did not complete"
    if aggregation["has_blockers"]:
        return "Blocked: unresolved blocking issues"
    return "Structural checks passed"
