"""What a pick counts (0.202.0): a tie goes to the higher grade; Laser Tag's verdicts on the fight, and a
doubt the walk test answered, are shown on a candidate's line and not counted.

The factory's census (`docs/findings/pick_majors/` in the factory root) read 62 cold workspace missions:
LOT_DESTINATION_ABOVE_FLOOR on 96 of 186 candidates, walked to on 95, steering 28 picks; the five fight
verdicts taken together steering none, and cold run 9283's three candidates carrying one each, two of them
the opposite of the third.
"""
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from apps.cli import commands
from packages.pipeline import pick

M = "row_001"
DOUBT = "LOT_DESTINATION_ABOVE_FLOOR"


def _candidate(lf, seed, *, completion=1.0, score=None, grade="PASS", walkers=("ok", "ok")):
    """One candidate as the shell leg leaves it: a walk test whose crew walkers read `walkers`
    (None writes the walk test's verdict and nothing else), and a Laser Tag report."""
    jobs = lf / "jobs"
    (jobs / f"{M}.lot_assemble.candidate.seed_{seed}" / "1" / "out").mkdir(parents=True)
    w = jobs / f"{M}.walktest_navqa.candidate.seed_{seed}" / "1" / "out"
    w.mkdir(parents=True)
    walk = {"ok": True}
    if walkers is not None:
        # a bot credited without walking is the director's ordinary case and says nothing about the crew
        walk["walkers"] = [{"name": f"player_{i}", "status": s, "targets_reached": 4, "targets_total": 4}
                           for i, s in enumerate(walkers)] + [
            {"name": "bot_0", "status": "ok_vertical_targets_only", "targets_reached": 0, "targets_total": 0}]
    (w / "site_navqa.walktest.json").write_text(json.dumps(walk), encoding="utf-8")
    r = jobs / f"{M}.laser_tag_evaluate.candidate.seed_{seed}" / "1" / "out"
    r.mkdir(parents=True)
    report = {"summary": {"route_completion_rate": completion}}
    if score is not None:
        report.update(overall_score=score, grade=grade)
    (r / "lasertag.report.json").write_text(json.dumps(report), encoding="utf-8")


def _issues(lf, issues):
    v = lf / "validation"
    v.mkdir(parents=True, exist_ok=True)
    (v / f"{M}.json").write_text(json.dumps({"mission_id": M, "issues": issues}), encoding="utf-8")


def _major(seed, code="LOT_SOMETHING"):
    return {"candidate_id": f"{M}.candidate.seed_{seed}", "severity": "major", "code": code}


@pytest.fixture()
def lf(tmp_path):
    return tmp_path / "ws" / ".level_factory"


def test_a_tie_goes_to_the_higher_grade_and_a_missing_score_sorts_last(lf):
    # cold run 9283: one major each, completion 1.00 each, and the lower seed won at 77 over 89
    _candidate(lf, 1, score=77, grade="PASS_WITH_TUNING")
    _candidate(lf, 2, score=89, grade="PASS_WITH_TUNING")
    _candidate(lf, 3)                                       # a report with no score
    _issues(lf, [])
    rows = pick.candidates(lf, M)
    assert pick.pick(rows)[0].seed == 2
    assert "grade PASS_WITH_TUNING 89" in rows[1].line() and "grade ? ?" in rows[2].line()
    assert pick.pick([rows[0], rows[2]])[0].seed == 1      # any score beats none


def test_an_upstairs_objective_the_walk_test_walked_to_is_not_counted(lf):
    # cold runs 9263-9265: 0.72 completion at 78 picked over 1.00 at 90, whose objective was a storey up
    _candidate(lf, 1, completion=0.72, score=78)
    _candidate(lf, 2, completion=1.0, score=90)
    _issues(lf, [_major(2, DOUBT)])
    rows = {r.seed: r for r in pick.candidates(lf, M)}
    assert rows[2].walked and rows[2].major == 0 and rows[2].not_counted == [DOUBT]
    assert f"0 major (not counted: {DOUBT})" in rows[2].line()
    assert pick.pick(list(rows.values()))[0].seed == 2


def test_the_doubt_counts_where_a_leg_was_credited_rather_than_walked(lf):
    # the walk test's own `ok` passes a leg it credits as a ladder without walking it
    _candidate(lf, 1, score=78)
    _candidate(lf, 2, score=90, walkers=("ok(1 vertical leg(s) via ladder)", "ok"))
    _candidate(lf, 3, score=90, walkers=None)               # no walkers read: nothing answered the doubt
    _issues(lf, [_major(2, DOUBT), _major(3, DOUBT)])
    rows = {r.seed: r for r in pick.candidates(lf, M)}
    assert not rows[2].walked and rows[2].major == 1 and rows[2].not_counted == []
    assert not rows[3].walked and rows[3].major == 1
    assert pick.pick(list(rows.values()))[0].seed == 1


def test_laser_tags_verdicts_on_the_fight_are_shown_and_not_counted(lf):
    # cold run 9283's three candidates: two crews dead in seconds, one that lost nobody
    _candidate(lf, 9061, completion=1.0, score=77)
    _candidate(lf, 9162, completion=0.96, score=84)
    _candidate(lf, 9263, completion=1.0, score=89)
    _candidate(lf, 9364, completion=1.0, score=95)
    _issues(lf, [_major(9061, "LT_MAP_NO_REACTION_TIME"), _major(9162, "LT_MAP_NO_REACTION_TIME"),
                 _major(9263, "LT_MAP_TRIVIAL_ENCOUNTER"), _major(9364)])
    rows = {r.seed: r for r in pick.candidates(lf, M)}
    assert [rows[s].major for s in (9061, 9162, 9263, 9364)] == [0, 0, 0, 1]
    assert rows[9263].not_counted == ["LT_MAP_TRIVIAL_ENCOUNTER"]
    assert pick.pick(list(rows.values()))[0].seed == 9263   # 9364's major still counts
    for code in pick.ADVISORY:
        assert code.startswith("LT_") and code not in pick.OUT_CODES


def test_an_out_code_still_puts_a_candidate_out(lf):
    _candidate(lf, 1, score=95)
    _candidate(lf, 2, score=60)
    _issues(lf, [_major(1, "LT_MAP_ENEMY_PATHING_BROKEN")])
    best, every_out = pick.pick(pick.candidates(lf, M))
    assert (best.seed, every_out) == (2, False)


def test_pick_json_carries_the_grade_and_what_was_not_counted(lf, capsys):
    _candidate(lf, 7, score=90)
    _issues(lf, [_major(7, DOUBT)])
    (lf.parent / "factory.project.json").write_text("{}", encoding="utf-8")
    rc = commands.cmd_pick(SimpleNamespace(chdir=str(lf.parent), mission_id=M, json=True))
    assert rc == commands.EXIT_OK
    row = json.loads(capsys.readouterr().out)["candidates"][0]
    assert (row["score"], row["grade"], row["not_counted"], row["major"]) == (90, "PASS", [DOUBT], 0)
