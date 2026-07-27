"""A job that stopped says why, in the findings (TDD 14.1, 22.4).

Findings are produced by `normalize_validation`, which reads a tool's report.
A job that never ran wrote no report, so it contributed nothing: the mission
finished with an empty findings list, and the Validation Center printed
"Structural checks passed  (blockers open: 0, total findings: 0)" over a
mission that had no level in it. Those are the same bytes a clean build
produces.

The refusal was not lost -- it was recorded on the job as a `Failure`, and
printed to the job log -- but nothing downstream of the scheduler reads either.
The gates, the validation file, `batch report` and the exit code all reason
over findings, so a refusal that is not a finding is a refusal nobody can act
on.

This module is the translation, kept pure so the scheduler and the tests agree
on one definition of what a stopped job says.
"""
from __future__ import annotations

from packages.core.errors import (
    ARTIFACT_HASH_ERROR, CANCELLED, CONFIGURATION_ERROR, INPUT_VALIDATION_ERROR,
    INTERNAL_ERROR, MISSING_DEPENDENCY, OUTPUT_CONTRACT_ERROR, TIMEOUT,
    TOOL_EXIT_FAILURE, VALIDATION_BLOCKER,
)
from packages.core.models import ValidationIssue
from packages.validation.model import BLOCKER

# Failure class -> (finding code, category, what to do about it).
_TRANSLATIONS: dict[str, tuple[str, str, str]] = {
    INPUT_VALIDATION_ERROR: (
        "JOB_PREFLIGHT_REFUSED", "configuration",
        "Fix the input the pre-flight named, then re-run the stage."),
    CONFIGURATION_ERROR: (
        "JOB_CONFIGURATION_ERROR", "configuration",
        "Correct the workspace or installation configuration and re-run."),
    MISSING_DEPENDENCY: (
        "JOB_MISSING_DEPENDENCY", "runtime_requirement",
        "Install or configure the missing executable, then re-run."),
    TOOL_EXIT_FAILURE: (
        "JOB_TOOL_EXIT", "runtime_requirement",
        "Read the job log for the tool's own error before re-running."),
    TIMEOUT: (
        "JOB_TIMEOUT", "runtime_requirement",
        "Read the job log to see how far the tool got; raise the timeout only "
        "once the work is known to be finite."),
    OUTPUT_CONTRACT_ERROR: (
        "JOB_OUTPUT_MISSING", "schema",
        "The tool reported success but did not write what it promised; check "
        "the job log and the adapter's expected outputs."),
    ARTIFACT_HASH_ERROR: (
        "JOB_ARTIFACT_HASH", "provenance",
        "An artifact changed after it was hashed; re-run the stage with "
        "--force so provenance is recorded against the real bytes."),
    INTERNAL_ERROR: (
        "JOB_INTERNAL_ERROR", "configuration",
        "This is a Level Factory defect, not a mission defect; the job log "
        "carries the traceback."),
}

# Stopping because someone asked is not a defect, and a blocking validation
# issue already arrived as a finding of its own -- re-stating it here would
# double-count it in the aggregate.
SILENT_FAILURE_CLASSES = frozenset({CANCELLED, VALIDATION_BLOCKER})

_UNKNOWN = ("JOB_FAILED", "configuration",
            "Read the job log for the failure detail.")


def issues_for_failure(
    *,
    failure_class: str,
    message: str = "",
    problems: list[str] | tuple[str, ...] = (),
    source_tool: str,
    job_id: str,
    mission_id: str,
    candidate_id: str | None = None,
    stage_id: str | None = None,
    log_path: str | None = None,
) -> list[ValidationIssue]:
    """Findings that carry a stopped job's reason into the Validation Center.

    `problems` is the adapter's own list, one entry per thing it objected to.
    They are kept apart rather than joined into one sentence: the pre-flight
    that refuses a map for four separate reasons is telling the operator four
    things, and a single finding would report it as one.
    """
    if failure_class in SILENT_FAILURE_CLASSES:
        return []

    code, category, fix = _TRANSLATIONS.get(failure_class, _UNKNOWN)
    texts = [str(p).strip() for p in problems if str(p).strip()]
    if not texts:
        texts = [str(message).strip() or f"job stopped: {failure_class}"]

    return [
        ValidationIssue(
            # The job id is part of the identity because the same code from two
            # candidates is two findings, not one; an id that collided would
            # let a single acceptance silence both.
            issue_id=f"{source_tool}:{code}:{job_id}#{i}",
            source_tool=source_tool,
            mission_id=mission_id,
            candidate_id=candidate_id,
            stage_id=stage_id,
            severity=BLOCKER,
            category=category,
            code=code,
            message=text,
            suggested_fix=fix,
            location=job_id,
            blocking=True,
            raw_source_path=log_path,
        )
        for i, text in enumerate(texts)
    ]
