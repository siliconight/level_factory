"""`pick` names a candidate by the cold runs' rule, and `make` runs a level start to finish
(0.169.0, roadmap 202).

`pick` reads the files the shell leg writes, so these build them in a temporary workspace.
`make` runs each leg as its own `level-factory` process; here a stand-in runner records the
command lines and answers as the real commands print, so the sequence and its stops can be held
without Blender or Godot. The real `make` is proven by a level made with it, not here.
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


def _candidate(lf, seed, *, walk_ok=True, completion=1.0):
    jobs = lf / "jobs"
    (jobs / f"{M}.lot_assemble.candidate.seed_{seed}" / "1" / "out").mkdir(parents=True)
    if walk_ok is not None:
        w = jobs / f"{M}.walktest_navqa.candidate.seed_{seed}" / "1" / "out"
        w.mkdir(parents=True)
        (w / "site_navqa.walktest.json").write_text(json.dumps({"ok": walk_ok}), encoding="utf-8")
    if completion is not None:
        r = jobs / f"{M}.laser_tag_evaluate.candidate.seed_{seed}" / "1" / "out"
        r.mkdir(parents=True)
        (r / "lasertag.report.json").write_text(
            json.dumps({"summary": {"route_completion_rate": completion}}), encoding="utf-8")


def _issues(lf, issues):
    v = lf / "validation"
    v.mkdir(parents=True, exist_ok=True)
    (v / f"{M}.json").write_text(json.dumps({"mission_id": M, "issues": issues}), encoding="utf-8")


def _major(seed, code="LOT_SOMETHING"):
    return {"candidate_id": f"{M}.candidate.seed_{seed}", "severity": "major", "code": code}


@pytest.fixture()
def lf(tmp_path):
    return tmp_path / "ws" / ".level_factory"


def test_the_fewest_major_findings_win_then_route_completion_then_the_lowest_seed(lf):
    _candidate(lf, 1, completion=1.0)
    _candidate(lf, 2, completion=0.08)
    _candidate(lf, 3, completion=1.0)
    _candidate(lf, 4, completion=1.0)
    _issues(lf, [_major(1), _major(1)])
    best, every_out = pick.pick(pick.candidates(lf, M))
    assert (best.seed, every_out) == (3, False)    # 0 major and 1.00; 4 ties and loses on seed
    _issues(lf, [_major(1), _major(3), _major(4)])
    best, _ = pick.pick(pick.candidates(lf, M))
    assert best.seed == 2                          # 0 major beats 1, even at 0.08 completion


def test_a_candidate_is_out_on_its_walk_test_or_a_major_route_finding(lf):
    _candidate(lf, 1, walk_ok=False)
    _candidate(lf, 2, walk_ok=None)                # no walk test at all
    _candidate(lf, 3)
    _candidate(lf, 4)
    _issues(lf, [_major(3, "LT_ROUTE_NEVER_COMPLETED"), _major(4)])
    rows = {r.seed: r for r in pick.candidates(lf, M)}
    assert rows[1].out == ["walktest not ok"] and rows[2].out == ["no walktest"]
    assert rows[3].out == ["LT_ROUTE_NEVER_COMPLETED"] and rows[4].out == []
    best, every_out = pick.pick(list(rows.values()))
    assert (best.seed, every_out) == (4, False)


def test_when_every_candidate_is_out_the_fewest_major_findings_is_still_picked(lf):
    _candidate(lf, 1, walk_ok=False)
    _candidate(lf, 2, walk_ok=False)
    _issues(lf, [_major(1)])
    best, every_out = pick.pick(pick.candidates(lf, M))
    assert (best.seed, every_out) == (2, True)


def test_a_missing_report_sorts_last_and_reads_as_unknown(lf):
    _candidate(lf, 1, completion=None)
    _candidate(lf, 2, completion=0.5)
    _issues(lf, [])
    rows = pick.candidates(lf, M)
    assert rows[0].completion is None and "route completion ?" in rows[0].line()
    assert pick.pick(rows)[0].seed == 2


def test_no_candidates_or_no_validation_file_refuses_rather_than_guessing(lf):
    with pytest.raises(ValueError, match="no candidates"):
        pick.candidates(lf, M)
    _candidate(lf, 1)
    with pytest.raises(ValueError, match="validation"):
        pick.candidates(lf, M)


def test_pick_prints_the_candidate_id_last(lf, capsys):
    _candidate(lf, 7)
    _issues(lf, [])
    (lf.parent / "factory.project.json").write_text("{}", encoding="utf-8")
    rc = commands.cmd_pick(SimpleNamespace(chdir=str(lf.parent), mission_id=M, json=False))
    assert rc == commands.EXIT_OK
    assert capsys.readouterr().out.strip().splitlines()[-1] == f"{M}.candidate.seed_7"


# ------------------------------------------------------------------- make

class _Legs:
    """Answers each command as the real one prints; records every command line."""

    def __init__(self, shell="blockers open: 0", art="blockers open: 0", export_rc=0):
        self.calls, self.shell, self.art, self.export_rc = [], shell, art, export_rc

    def __call__(self, argv):
        self.calls.append(list(argv))
        cmd = argv[2] if argv[:1] == ["-C"] else argv[0]
        if cmd == "run":
            text = self.art if "--art" in argv else self.shell
            return 0, f"Structural checks passed  ({text}, total findings: 3)\n"
        if cmd == "export":
            return self.export_rc, f"exported {M} [portable-godot] -> /x/LF_{M}.portable-godot\n"
        return 0, ""


def _batch(tmp_path, missions=(M,)):
    b = tmp_path / "batch.json"
    b.write_text(json.dumps({"batch_id": "b", "missions": list(missions)}), encoding="utf-8")
    return b


def _ws(tmp_path):
    root = tmp_path / "ws"
    lf = root / ".level_factory"
    _candidate(lf, 11, completion=0.5)
    _candidate(lf, 12, completion=1.0)
    _issues(lf, [])
    (root / "factory.project.json").write_text("{}", encoding="utf-8")
    return root


def _args(root, batch, **kw):
    return SimpleNamespace(chdir=str(root), batch_json=str(batch), mission=kw.get("mission", ""),
                           seed=kw.get("seed"), no_bake_lights=kw.get("no_bake_lights", False))


def _verbs(calls):
    return [" ".join(c[2:5]) for c in calls]


def test_make_runs_the_legs_in_the_cold_drivers_order(tmp_path, capsys):
    root, legs = _ws(tmp_path), _Legs()
    rc = commands.cmd_make(_args(root, _batch(tmp_path)), run_leg=legs)
    assert rc == commands.EXIT_OK
    assert all(c[:2] == ["-C", str(root)] for c in legs.calls)
    assert _verbs(legs.calls) == [
        f"batch create {tmp_path / 'batch.json'}", f"plan {M}", f"run {M}",
        f"approve {M} brief_approved", f"approve {M} candidate_selected",
        f"approve {M} functional_shell_locked", f"run {M} --art", f"export {M} --mode"]
    assert legs.calls[4][-1] == f"{M}.candidate.seed_12"     # the pick: 1.00 beats 0.50
    assert legs.calls[-1][-1] == "portable-godot"
    out = capsys.readouterr().out
    assert f"the level: /x/LF_{M}.portable-godot" in out and f"walk {M} --play" in out


def test_make_initialises_a_new_workspace_first(tmp_path):
    legs = _Legs()
    root = tmp_path / "fresh"
    commands.cmd_make(_args(root, _batch(tmp_path)), run_leg=legs)
    assert legs.calls[0] == ["init", str(root)]


def test_make_stops_at_the_shell_leg_on_an_open_blocker(tmp_path, capsys):
    legs = _Legs(shell="blockers open: 2")
    rc = commands.cmd_make(_args(_ws(tmp_path), _batch(tmp_path)), run_leg=legs)
    assert rc == commands.EXIT_BLOCKED
    assert not [c for c in legs.calls if "approve" in c]
    assert "STOPPED at shell: 2 blocker(s) open" in capsys.readouterr().err


def test_make_stops_when_a_leg_prints_no_blocker_count(tmp_path, capsys):
    legs = _Legs(art="something else entirely")
    rc = commands.cmd_make(_args(_ws(tmp_path), _batch(tmp_path)), run_leg=legs)
    assert rc != commands.EXIT_OK
    assert not [c for c in legs.calls if "export" in c]
    assert "STOPPED at art" in capsys.readouterr().err


def test_make_stops_on_a_failed_export(tmp_path):
    rc = commands.cmd_make(_args(_ws(tmp_path), _batch(tmp_path)), run_leg=_Legs(export_rc=4))
    assert rc == 4


def test_seed_selects_instead_of_the_pick_and_no_bake_lights_reaches_the_export(tmp_path):
    legs = _Legs()
    commands.cmd_make(_args(_ws(tmp_path), _batch(tmp_path), seed=11, no_bake_lights=True),
                      run_leg=legs)
    assert legs.calls[4][-1] == f"{M}.candidate.seed_11"
    assert legs.calls[-1][-1] == "--no-bake-lights"


def test_make_refuses_a_folder_that_is_not_a_workspace_and_not_empty(tmp_path, capsys):
    root = tmp_path / "busy"
    root.mkdir()
    (root / "notes.txt").write_text("mine", encoding="utf-8")
    legs = _Legs()
    assert commands.cmd_make(_args(root, _batch(tmp_path)), run_leg=legs) == commands.EXIT_CONFIG
    assert legs.calls == [] and "not a workspace" in capsys.readouterr().err


def test_make_asks_which_mission_when_the_batch_names_several(tmp_path, capsys):
    batch = _batch(tmp_path, missions=(M, "other_002"))
    legs = _Legs()
    assert commands.cmd_make(_args(_ws(tmp_path), batch), run_leg=legs) == commands.EXIT_CONFIG
    assert legs.calls == [] and "--mission" in capsys.readouterr().err
