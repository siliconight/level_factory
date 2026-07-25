"""Laser Tag readiness grade is surfaced as a NON-BLOCKING finding (TDD 5.5).

A low/BROKEN grade is a readiness signal for the human at candidate selection —
never a blocker, never a claim about fun/balance/network. Paired with the
scheduler's `exit_advisory` handling, this lets a readiness evaluator that ran
and produced a report complete the job with findings instead of crashing the
build.

The counterpart rule lives here too: a report describing ZERO runs is not a
readiness signal at all. It says the evaluator never started, which is a tool
contract failure and does block — the same class as the pipeline reporting five
candidates it did not build. Every report below therefore states its `runs`,
because a report that omits the count cannot be told apart from one that ran.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from adapters.laser_tag import LaserTagAdapter  # noqa: E402


def _report(tmp_path, **fields) -> Path:
    p = tmp_path / "lasertag.report.json"
    p.write_text(json.dumps(fields))
    return p


def test_broken_grade_is_nonblocking_finding(tmp_path):
    rep = _report(tmp_path, grade="BROKEN", score=0, runs=8)
    issues = LaserTagAdapter().normalize_validation([rep])
    codes = {i["code"] for i in issues}
    assert "LT_LOW_READINESS" in codes
    low = next(i for i in issues if i["code"] == "LT_LOW_READINESS")
    assert low["blocking"] is False  # readiness signal only, never blocks


def test_low_score_is_nonblocking_finding(tmp_path):
    rep = _report(tmp_path, grade="C", score=25, runs=8)
    issues = LaserTagAdapter().normalize_validation([rep])
    assert any(i["code"] == "LT_LOW_READINESS" and not i["blocking"] for i in issues)


def test_good_grade_surfaces_no_readiness_finding(tmp_path):
    rep = _report(tmp_path, grade="A", score=88, runs=8)
    issues = LaserTagAdapter().normalize_validation([rep])
    assert all(i["code"] != "LT_LOW_READINESS" for i in issues)


def test_overall_score_is_the_field_the_report_actually_writes(tmp_path):
    """LaserTag 0.7 writes `overall_score`; the adapter read `score`, so every
    candidate card scored None and a real signal hid behind a missing key."""
    rep = _report(tmp_path, grade="C", overall_score=12, runs=8)
    issues = LaserTagAdapter().normalize_validation([rep])
    low = next(i for i in issues if i["code"] == "LT_LOW_READINESS")
    assert "12" in low["message"]
    assert LaserTagAdapter().read_metrics(rep)["lasertag_score"] == 12


def test_zero_runs_blocks_and_is_not_called_a_readiness_grade(tmp_path):
    """The bug this file exists to prevent: `runs: 0` was reported as
    "readiness grade BROKEN" — a claim about the level — when what it means is
    that the evaluator never played a single firefight."""
    rep = _report(tmp_path, grade="BROKEN", overall_score=0, runs=0, findings=[
        {"severity": "FAIL", "type": "NO_RUNS",
         "message": "No runs completed - map could not be evaluated."}])
    issues = LaserTagAdapter().normalize_validation([rep])
    not_eval = next(i for i in issues if i["code"] == "LT_NOT_EVALUATED")
    assert not_eval["blocking"] is True
    assert not_eval["category"] == "tool_contract"
    # ...and it must NOT also be dressed up as a readiness score.
    assert all(i["code"] != "LT_LOW_READINESS" for i in issues)
    # NO_RUNS is folded into the blocker's message, not double-counted.
    assert all(i["code"] != "LT_MAP_NO_RUNS" for i in issues)
    assert "No runs completed" in not_eval["message"]


def test_missing_runs_key_is_treated_as_never_evaluated(tmp_path):
    """A report that does not say how many runs it completed is
    indistinguishable from one that completed none. Silence is not a pass."""
    rep = _report(tmp_path, grade="A", overall_score=91)
    issues = LaserTagAdapter().normalize_validation([rep])
    blocker = next(i for i in issues if i["code"] == "LT_NOT_EVALUATED")
    assert blocker["blocking"] is True
    assert "does not say how many runs" in blocker["message"]
    assert LaserTagAdapter().read_metrics(rep)["lasertag_evaluated"] is False


def test_lasertags_own_findings_reach_the_operator(tmp_path):
    """The report's `findings` array — the list that says WHY the map could not
    be played — was read by nothing, so the pipeline knew the map was broken and
    could not say what was wrong with it."""
    rep = _report(tmp_path, grade="BROKEN", overall_score=0, runs=0, findings=[
        {"severity": "FAIL", "type": "MISSING_PLAYER_SPAWN",
         "message": "No LT_PlayerSpawn node found."},
        {"severity": "WARN", "type": "NAVIGATION_MISSING",
         "message": "No NavigationRegion3D in the scene."}])
    issues = LaserTagAdapter().normalize_validation([rep])
    by_code = {i["code"]: i for i in issues}
    assert by_code["LT_MAP_MISSING_PLAYER_SPAWN"]["severity"] == "major"
    assert by_code["LT_MAP_NAVIGATION_MISSING"]["severity"] == "moderate"
    assert not by_code["LT_MAP_MISSING_PLAYER_SPAWN"]["blocking"]
    assert "LT_PlayerSpawn" in by_code["LT_MAP_MISSING_PLAYER_SPAWN"]["message"]
