"""Mission and job state machines (TDD 13 and 14).

State is kept as plain strings on the domain objects; this module owns the
legal transitions and the linear order of the mission lifecycle so the planner
and scheduler can reason about "how far has this mission progressed".
"""
from __future__ import annotations

# ---------------------------------------------------------------------------
# Mission states (TDD 13)
# ---------------------------------------------------------------------------
DRAFT = "DRAFT"
BRIEF_APPROVED = "BRIEF_APPROVED"
BUILDING_CANDIDATES_GENERATED = "BUILDING_CANDIDATES_GENERATED"
SITE_CANDIDATES_GENERATED = "SITE_CANDIDATES_GENERATED"
FUNCTIONALLY_EVALUATED = "FUNCTIONALLY_EVALUATED"
CANDIDATE_SELECTED = "CANDIDATE_SELECTED"
FUNCTIONAL_SHELL_LOCKED = "FUNCTIONAL_SHELL_LOCKED"
PRESENTATION_INPUTS_READY = "PRESENTATION_INPUTS_READY"
PRESENTATION_COMPLETE = "PRESENTATION_COMPLETE"
REGRESSION_PASSED = "REGRESSION_PASSED"
DISPATCH_PACKAGED = "DISPATCH_PACKAGED"
HANDOFF_READY = "HANDOFF_READY"
INVALIDATED = "INVALIDATED"

# Linear progression of the happy path. Index = "distance travelled".
MISSION_ORDER = (
    DRAFT,
    BRIEF_APPROVED,
    BUILDING_CANDIDATES_GENERATED,
    SITE_CANDIDATES_GENERATED,
    FUNCTIONALLY_EVALUATED,
    CANDIDATE_SELECTED,
    FUNCTIONAL_SHELL_LOCKED,
    PRESENTATION_INPUTS_READY,
    PRESENTATION_COMPLETE,
    REGRESSION_PASSED,
    DISPATCH_PACKAGED,
    HANDOFF_READY,
)

_ORDER_INDEX = {state: i for i, state in enumerate(MISSION_ORDER)}


def mission_rank(state: str) -> int:
    """Ordinal position in the happy path. INVALIDATED ranks below DRAFT."""
    if state == INVALIDATED:
        return -1
    return _ORDER_INDEX[state]


def is_at_least(state: str, target: str) -> bool:
    return mission_rank(state) >= mission_rank(target)


def next_mission_state(state: str) -> str:
    idx = _ORDER_INDEX[state]
    if idx + 1 >= len(MISSION_ORDER):
        return state
    return MISSION_ORDER[idx + 1]


# ---------------------------------------------------------------------------
# Job states (TDD 14)
# ---------------------------------------------------------------------------
PLANNED = "PLANNED"
QUEUED = "QUEUED"
RUNNING = "RUNNING"
CANCELLING = "CANCELLING"
CANCELLED = "CANCELLED"
SUCCEEDED = "SUCCEEDED"
FAILED = "FAILED"
BLOCKED = "BLOCKED"
SKIPPED_CACHE_HIT = "SKIPPED_CACHE_HIT"

JOB_TERMINAL = frozenset({CANCELLED, SUCCEEDED, FAILED, BLOCKED, SKIPPED_CACHE_HIT})
JOB_RESUMABLE = frozenset({PLANNED, QUEUED, RUNNING, CANCELLING})

_JOB_TRANSITIONS = {
    PLANNED: {QUEUED, BLOCKED, SKIPPED_CACHE_HIT, CANCELLED},
    QUEUED: {RUNNING, CANCELLED, BLOCKED, SKIPPED_CACHE_HIT},
    RUNNING: {SUCCEEDED, FAILED, CANCELLING, BLOCKED},
    CANCELLING: {CANCELLED, FAILED},
}


def job_can_transition(src: str, dst: str) -> bool:
    if src in JOB_TERMINAL:
        return False
    return dst in _JOB_TRANSITIONS.get(src, set())


def job_succeeded(state: str) -> bool:
    return state in (SUCCEEDED, SKIPPED_CACHE_HIT)
