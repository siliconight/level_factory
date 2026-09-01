"""A blocker on the SELECTED candidate counts, whatever the scheduler did.

Roadmap item 68. `patch_lf_eliminated_not_blocking.py` (2026-08-12) taught
`aggregate` to stop counting blockers that belong to candidates the scheduler
had already discarded, and it was right to: one discarded candidate's blocker
was labelling a run that had not stopped as "Blocked". Its reasoning -- "N
candidates exist so that some can be bad" -- overshot by exactly one
candidate, because the predicate it installed never consulted the selection.

Measured 2026-08-27 on cold run `cold_7001`: the candidate a human had
approved at `candidate_selected` picked up two LUX_FIXTURE_COLOCATION
blockers, the scheduler eliminated it, and the run printed

    Structural checks passed  (blockers open: 0, total findings: 119)

The earlier bug made a good run look broken. This one made a broken run look
good. Both halves are pinned here, because the fix for either one is a way of
re-breaking the other.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from packages.core.models import ValidationIssue  # noqa: E402
from packages.validation.model import aggregate, readiness_label  # noqa: E402

SELECTED = "category5_baie_dore_001.candidate.seed_7001"
OTHER = "category5_baie_dore_001.candidate.seed_7102"


def _blocker(issue_id, candidate_id):
    return ValidationIssue(
        issue_id=issue_id, source_tool="lux", mission_id="m",
        severity="blocker", category="presentation",
        code="LUX_FIXTURE_COLOCATION", message="", candidate_id=candidate_id,
        blocking=True)


def test_cold_7001_the_selected_candidates_blockers_still_count():
    """The run this item was filed for. Two blockers, selection eliminated."""
    issues = [_blocker("a", SELECTED), _blocker("b", SELECTED)]
    agg = aggregate(issues, eliminated_candidates=frozenset({SELECTED}),
                    selected_candidate=SELECTED)
    assert agg["blocking_open"] == ["a", "b"]
    assert agg["blocking_eliminated"] == []
    assert agg["has_blockers"]
    assert readiness_label(agg) == "Blocked: unresolved blocking issues"


def test_an_eliminated_selection_is_reported_rather_than_inferred():
    """A mission whose selection was thrown away has nothing to hand over.
    Leaving that to be deduced from a blocker count is how it went unnoticed."""
    agg = aggregate([_blocker("a", SELECTED)],
                    eliminated_candidates=frozenset({SELECTED}),
                    selected_candidate=SELECTED)
    assert agg["selected_eliminated"] is True


def test_the_2026_08_12_fix_still_holds_for_a_candidate_nobody_chose():
    """The half this must not re-break: a discarded candidate's blocker does
    not block a run that carried on without it."""
    issues = [_blocker("a", SELECTED), _blocker("c", OTHER)]
    agg = aggregate(issues, eliminated_candidates=frozenset({OTHER}),
                    selected_candidate=SELECTED)
    assert agg["blocking_open"] == ["a"]
    assert agg["blocking_eliminated"] == ["c"]
    assert agg["selected_eliminated"] is False


def test_a_surviving_selection_is_not_special_cased():
    """The exemption is for the selection's OWN blockers, not a blanket one."""
    agg = aggregate([_blocker("c", OTHER)],
                    eliminated_candidates=frozenset({OTHER}),
                    selected_candidate=SELECTED)
    assert agg["blocking_open"] == []
    assert agg["blocking_eliminated"] == ["c"]
    assert agg["selected_eliminated"] is False
    assert readiness_label(agg) == "Structural checks passed"


def test_no_selection_passed_is_yesterdays_behaviour_exactly():
    """OPT-IN, the same way the eliminated set is. A caller that does not know
    the selection -- `cmd_validate` is one -- gets what it got before."""
    issues = [_blocker("a", SELECTED), _blocker("c", OTHER)]
    agg = aggregate(issues, eliminated_candidates=frozenset({SELECTED, OTHER}))
    assert agg["blocking_open"] == []
    assert agg["blocking_eliminated"] == ["a", "c"]
    assert agg["selected_eliminated"] is False
    assert agg["total"] == 2


def test_an_accepted_exception_still_wins():
    """Acceptance is checked before the partition and stays that way."""
    agg = aggregate([_blocker("a", SELECTED)],
                    accepted_issue_ids=frozenset({"a"}),
                    eliminated_candidates=frozenset({SELECTED}),
                    selected_candidate=SELECTED)
    assert agg["accepted"] == ["a"]
    assert agg["blocking_open"] == []
    assert not agg["has_blockers"]


def test_a_mission_scoped_blocker_is_never_discounted():
    """`candidate_id is None` belongs to the mission, not to any candidate."""
    agg = aggregate([_blocker("z", None)],
                    eliminated_candidates=frozenset({SELECTED}),
                    selected_candidate=SELECTED)
    assert agg["blocking_open"] == ["z"]


def test_findings_are_never_dropped_only_partitioned():
    """Whatever side they land on, the count of what was found is the truth."""
    issues = [_blocker("a", SELECTED), _blocker("c", OTHER)]
    for kwargs in ({},
                   {"eliminated_candidates": frozenset({OTHER})},
                   {"eliminated_candidates": frozenset({SELECTED, OTHER}),
                    "selected_candidate": SELECTED}):
        assert aggregate(issues, **kwargs)["total"] == 2
