"""The export's blocker query knows which candidate it is exporting.

COLD RUN 9074 COULD NOT PRODUCE A PACKAGE. `cmd_run` printed "1 blocker(s)
belong to eliminated candidate(s) and do not block the mission" and "blockers
open: 0"; `cmd_export` refused over that same blocker. Two queries of one
question -- `cmd_run` calls `aggregate` with `eliminated_candidates` and
`selected_candidate`, `_open_blockers` filtered by stage alone -- so a blocker
on ANY candidate refused the export whichever one a human approved, and no
selection could have passed.

These pin the rule and, as importantly, the SAFE direction: the discount fires
only when both candidates are known and differ. Cold run 9015 is why -- a
blocker this export did not read shipped a lightless package that walked black
and counted a zero.

Run:  python -m pytest tests/unit/test_export_blockers_candidate_aware.py -q
"""
from __future__ import annotations

import json

import pytest

from apps.cli.commands import _candidate_of, _open_blockers
from packages.approvals import gates

MISSION = "club_block_013"
#: verbatim from cold run 9074's validation file
BLOCKER_LOC = "club_block_013.laser_tag_evaluate.candidate.seed_9074"


class _WS:
    def __init__(self, root):
        self.internal_dir = root


def _ws(tmp_path, issues, selected=None):
    internal = tmp_path / ".level_factory"
    (internal / "validation").mkdir(parents=True)
    (internal / "validation" / f"{MISSION}.json").write_text(
        json.dumps({"mission_id": MISSION, "issues": issues}), encoding="utf-8")
    if selected is not None:
        # The REAL store writes the approval, rather than this test inventing
        # its shape -- a hand-faked one missed six required fields and the
        # failure read as a bug in the code under test.
        appr = internal / "approvals"
        gates.ApprovalStore(appr).record(
            mission_id=MISSION, gate=gates.CANDIDATE_SELECTED,
            decision=gates.DECISION_APPROVED, approved_by="test",
            protected_inputs={"candidate": selected})
        (appr / f"{MISSION}.selected").write_text(selected, encoding="utf-8")
    return _WS(internal)


def _blocker(loc=BLOCKER_LOC, stage="laser_tag_evaluate"):
    return {"code": "JOB_PREFLIGHT_REFUSED", "blocking": True,
            "location": loc, "stage_id": stage,
            "message": "LT_ObjectivePoint is inside solid geometry"}


# ---------------------------------------------------------------------------
# the token, which is the only thing the two shapes have in common
# ---------------------------------------------------------------------------
def test_the_candidate_token_is_read_from_both_location_shapes():
    """A finding's location may or may not name a stage; the selection marker
    never does. The token after `.candidate.` is what they can be compared by."""
    assert _candidate_of(BLOCKER_LOC) == "seed_9074"
    assert _candidate_of("club_block_013.candidate.seed_9276") == "seed_9276"


def test_a_location_with_no_candidate_yields_none():
    assert _candidate_of("club_block_013.lux_apply") is None
    assert _candidate_of("") is None


# ---------------------------------------------------------------------------
# the rule
# ---------------------------------------------------------------------------
def test_a_blocker_on_an_unselected_candidate_does_not_refuse_the_export(tmp_path):
    """FAILS BEFORE THIS FIX: this is cold run 9074 exactly -- seed_9074
    carried the only blocker, seed_9276 was approved, and the export refused."""
    ws = _ws(tmp_path, [_blocker()], selected="club_block_013.candidate.seed_9276")
    assert _open_blockers(ws, MISSION) == []


def test_a_blocker_on_the_selected_candidate_still_refuses(tmp_path):
    """`aggregate`: "the chosen one IS the mission". This is the first half of
    cold run 9074, where seed_9074 was both selected and blocked -- and the
    refusal there was correct."""
    ws = _ws(tmp_path, [_blocker()], selected="club_block_013.candidate.seed_9074")
    out = _open_blockers(ws, MISSION)
    assert len(out) == 1 and "JOB_PREFLIGHT_REFUSED" in out[0], out


# ---------------------------------------------------------------------------
# and the safe direction, which is what cold run 9015 bought
# ---------------------------------------------------------------------------
def test_with_no_selection_recorded_every_blocker_still_counts(tmp_path):
    ws = _ws(tmp_path, [_blocker()], selected=None)
    assert len(_open_blockers(ws, MISSION)) == 1


def test_a_blocker_naming_no_candidate_still_counts(tmp_path):
    """A stage-level blocker belongs to the mission, not to a candidate, so
    there is nothing to discount it against."""
    ws = _ws(tmp_path,
             [_blocker(loc="club_block_013.lux_apply", stage="lux_apply")],
             selected="club_block_013.candidate.seed_9276")
    assert len(_open_blockers(ws, MISSION)) == 1
