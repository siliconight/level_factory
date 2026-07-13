"""Laser Tag readiness grade is surfaced as a NON-BLOCKING finding (TDD 5.5).

A low/BROKEN grade is a readiness signal for the human at candidate selection —
never a blocker, never a claim about fun/balance/network. Paired with the
scheduler's `exit_advisory` handling, this lets a readiness evaluator that ran
and produced a report complete the job with findings instead of crashing the
build.
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
    rep = _report(tmp_path, grade="BROKEN", score=0)
    issues = LaserTagAdapter().normalize_validation([rep])
    codes = {i["code"] for i in issues}
    assert "LT_LOW_READINESS" in codes
    low = next(i for i in issues if i["code"] == "LT_LOW_READINESS")
    assert low["blocking"] is False  # readiness signal only, never blocks


def test_low_score_is_nonblocking_finding(tmp_path):
    rep = _report(tmp_path, grade="C", score=25)
    issues = LaserTagAdapter().normalize_validation([rep])
    assert any(i["code"] == "LT_LOW_READINESS" and not i["blocking"] for i in issues)


def test_good_grade_surfaces_no_readiness_finding(tmp_path):
    rep = _report(tmp_path, grade="A", score=88)
    issues = LaserTagAdapter().normalize_validation([rep])
    assert all(i["code"] != "LT_LOW_READINESS" for i in issues)
