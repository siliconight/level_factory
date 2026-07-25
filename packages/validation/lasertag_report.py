"""Read a Laser Tag report honestly (TDD 5.5, 24.3).

Three separate things were wrong with how Level Factory read
``lasertag.report.json``:

* the report writes ``overall_score``; the adapter read ``score``, so every
  candidate card and every finding said "score None";
* the report's own ``findings`` array -- the list that says *why* the map could
  not be played -- was never read at all;
* and ``runs: 0`` was reported as "readiness grade BROKEN", which is a claim
  about the level. It is not. Zero runs means the evaluator never started, and
  a tool that reports a grade for a match it never played is a contract
  failure, not a low score.

That last distinction is the one that matters. TDD 5.5 forbids a *readiness
score* from blocking a build, and this module keeps that: grades and scores stay
non-blocking, always. "The evaluator could not run" is a different statement --
the same class of failure as the pipeline reporting five candidates it did not
build -- and it blocks.

Pure dicts in, findings out; no Godot, no filesystem.
"""
from __future__ import annotations

from typing import Mapping, Sequence

CODE_NOT_EVALUATED = "LT_NOT_EVALUATED"
CODE_LOW_READINESS = "LT_LOW_READINESS"
CODE_MAP_PREFIX = "LT_MAP_"

READINESS_FLOOR = 40

_SEVERITY = {"FAIL": "major", "ERROR": "major", "WARN": "moderate",
             "WARNING": "moderate", "INFO": "minor"}


def report_score(data: Mapping[str, object]):
    """The report's score under whichever key this LaserTag build wrote.

    ``overall_score`` is the 0.7 contract; ``score`` is kept as a fallback so an
    older report still reads rather than silently scoring None.
    """
    for key in ("overall_score", "score"):
        value = data.get(key)
        if isinstance(value, (int, float)):
            return value
    return None


def report_runs(data: Mapping[str, object]):
    value = data.get("runs")
    return value if isinstance(value, int) else None


def was_evaluated(data: Mapping[str, object]) -> bool:
    runs = report_runs(data)
    return runs is not None and runs > 0


def _lt_findings(data: Mapping[str, object]) -> list[Mapping[str, object]]:
    raw = data.get("findings")
    return [f for f in raw if isinstance(f, Mapping)] if isinstance(raw, list) else []


def failure_summary(data: Mapping[str, object]) -> str:
    """What Laser Tag itself said went wrong, for the human reading one line."""
    parts = [f"{f.get('type', '?')}: {f.get('message', '')}".strip()
             for f in _lt_findings(data)]
    return "; ".join(p for p in parts if p) or "no findings reported"


def normalize_report(
    data: Mapping[str, object], *, raw_source_path: str | None = None,
) -> list[dict]:
    """Findings for one ``lasertag.report.json``."""
    issues: list[dict] = []
    src = {"raw_source_path": raw_source_path} if raw_source_path else {}
    runs = report_runs(data)
    score = report_score(data)
    grade = str(data.get("grade", "")).upper()

    if not was_evaluated(data):
        detail = ("the report does not say how many runs completed"
                  if runs is None else f"{runs} runs completed")
        issues.append({
            "code": CODE_NOT_EVALUATED,
            "severity": "blocker", "category": "tool_contract",
            "message": (
                f"Laser Tag never evaluated this map ({detail}); the reported "
                f"grade {grade or '?'} is not a readiness signal because no "
                f"firefight was played. Laser Tag said: {failure_summary(data)}"),
            "blocking": True, **src,
        })

    # Whatever LaserTag found, verbatim. NO_RUNS is folded into the message
    # above; repeating it as its own finding would double-count the same fact.
    for finding in _lt_findings(data):
        kind = str(finding.get("type", "UNKNOWN")).upper()
        if kind == "NO_RUNS":
            continue
        issues.append({
            "code": CODE_MAP_PREFIX + kind,
            "severity": _SEVERITY.get(str(finding.get("severity", "")).upper(), "minor"),
            "category": "combat_structure",
            "message": f"Laser Tag: {finding.get('message', kind)}",
            "blocking": False, **src,
        })

    # The readiness signal proper -- only meaningful once a match was actually
    # played, and non-blocking by contract even then.
    if was_evaluated(data) and (
            grade in ("BROKEN", "FAIL")
            or (isinstance(score, (int, float)) and score < READINESS_FLOOR)):
        issues.append({
            "code": CODE_LOW_READINESS,
            "severity": "moderate", "category": "combat_structure",
            "message": (f"Laser Tag readiness grade {grade or '?'} "
                        f"(score {score}) over {runs} runs; evaluation "
                        f"completed — readiness signal only, review at "
                        f"selection."),
            "blocking": False, **src,
        })

    for zone in data.get("overexposed_zones", []) or []:
        issues.append({
            "code": "LT_OVEREXPOSED_ZONE", "severity": "minor",
            "category": "combat_structure",
            "message": f"Overexposed zone at {zone}", "blocking": False, **src,
        })
    for zone in data.get("blind_zones", []) or []:
        issues.append({
            "code": "LT_BLIND_ZONE", "severity": "minor",
            "category": "combat_structure",
            "message": f"Blind zone at {zone}", "blocking": False, **src,
        })
    return issues


def metrics(data: Mapping[str, object]) -> dict:
    return {
        "lasertag_score": report_score(data),
        "lasertag_grade": data.get("grade"),
        "lasertag_runs": report_runs(data),
        "lasertag_evaluated": was_evaluated(data),
        "lasertag_note": "readiness signal only; not fun/balance/network",
    }


def summarize(reports: Sequence[Mapping[str, object]]) -> str:
    """One line for the run output: did Laser Tag actually play anything."""
    if not reports:
        return "laser_tag: no reports"
    evaluated = sum(1 for r in reports if was_evaluated(r))
    if evaluated == 0:
        return f"laser_tag: {len(reports)} report(s), none evaluated (0 runs)"
    if evaluated == len(reports):
        return f"laser_tag: {evaluated}/{len(reports)} evaluated"
    return (f"laser_tag: {evaluated}/{len(reports)} evaluated, "
            f"{len(reports) - evaluated} never ran")
