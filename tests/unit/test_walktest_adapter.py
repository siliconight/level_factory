"""Unit tests: the walktest adapter reads a nav QA report honestly.

Two properties matter more than the rest and both are about silence. A walktest
that ran and found nothing must produce no findings; a walktest that could not
run must not be able to look like one. The second is the scheduler's
output-contract check, so the tests here pin the adapter's half: it declares the
report as its expected output, it passes --require so a missing Godot fails
loudly instead of skipping quietly, and it says something when a report claims
failure without naming one.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import adapters.walktest as WT
from adapters.walktest import REPORT_NAME, WalktestAdapter


def _report(tmp_path, payload) -> Path:
    p = tmp_path / REPORT_NAME
    p.write_text(json.dumps(payload), encoding="utf-8")
    return p


def _codes(issues):
    return [i["code"] for i in issues]


PASSING = {
    "ok": True,
    "path_proofs": [{"leg": "spawn->objective", "ok": True, "length_m": 41.2}],
    "walkers": [{"name": "bot_0", "status": "ok", "targets_reached": 1,
                 "targets_total": 1, "travelled_m": 44.0}],
    "proxies": 1, "bot_spawns": 1, "sim_seconds": 18.4,
}


# --- silence, earned and unearned -------------------------------------------

def test_a_passing_walktest_reports_nothing(tmp_path):
    assert WalktestAdapter().normalize_validation([_report(tmp_path, PASSING)]) == []


def test_a_missing_report_is_not_this_methods_lie_to_tell(tmp_path):
    """The scheduler's output contract fails a job whose declared output is
    absent, before validation is consulted. Inventing a finding here would put
    the same complaint in two places and let one drift from the other."""
    assert WalktestAdapter().normalize_validation([]) == []


def test_failure_without_a_named_cause_still_says_something(tmp_path):
    """The worst report shape: ok=false, nothing itemised. Anything counting
    findings would read it as a pass."""
    payload = {**PASSING, "ok": False, "path_proofs": [], "walkers": []}
    issues = WalktestAdapter().normalize_validation([_report(tmp_path, payload)])
    assert _codes(issues) == ["WALKTEST_FAILED_WITHOUT_DETAIL"]


def test_unreadable_report(tmp_path):
    p = tmp_path / REPORT_NAME
    p.write_text("{ not json", encoding="utf-8")
    assert _codes(WalktestAdapter().normalize_validation([p])) == \
        ["WALKTEST_REPORT_UNREADABLE"]


# --- what the director actually reports -------------------------------------

def test_unpathable_leg_names_the_leg_and_the_detail(tmp_path):
    payload = {**PASSING, "ok": False, "path_proofs": [
        {"leg": "spawn->objective", "ok": True, "length_m": 12.0},
        {"leg": "objective->extraction", "ok": False,
         "detail": "no navmesh path"}]}
    issues = WalktestAdapter().normalize_validation([_report(tmp_path, payload)])
    assert _codes(issues) == ["WALKTEST_LEG_UNPATHABLE"]
    assert "objective->extraction" in issues[0]["message"]
    assert "no navmesh path" in issues[0]["message"]
    assert issues[0]["category"] == "reachability"


def test_stuck_walker_carries_the_coordinates(tmp_path):
    payload = {**PASSING, "ok": False, "walkers": [
        {"name": "bot_0", "status": "stuck", "targets_reached": 0,
         "targets_total": 2, "travelled_m": 3.1, "at": [12.5, 0.0, -8.25]}]}
    issues = WalktestAdapter().normalize_validation([_report(tmp_path, payload)])
    assert _codes(issues) == ["WALKTEST_WALKER_STUCK"]
    assert "(12.5, 0.0, -8.25)" in issues[0]["message"]
    assert "0/2" in issues[0]["message"]


def test_every_ok_flavoured_status_passes(tmp_path):
    """The director's own comment warns about this: an exact match on "ok"
    rejects the vertical-access statuses, which are passes."""
    payload = {**PASSING, "walkers": [
        {"name": "a", "status": "ok", "targets_reached": 1, "targets_total": 1},
        {"name": "b", "status": "ok(1 vertical leg(s) via ladder)",
         "targets_reached": 1, "targets_total": 1},
        {"name": "c", "status": "ok_vertical_targets_only",
         "targets_reached": 0, "targets_total": 0}]}
    assert WalktestAdapter().normalize_validation([_report(tmp_path, payload)]) == []


def test_an_empty_navmesh_is_its_own_code(tmp_path):
    """"There was nothing to walk on" and "the route is blocked" are different
    failures with different fixes, and the director distinguishes them."""
    payload = {"ok": False, "regions": 0,
               "error": "navigation map is EMPTY at QA time (bake produced no "
                        "polygons or region never registered)"}
    issues = WalktestAdapter().normalize_validation([_report(tmp_path, payload)])
    assert "WALKTEST_NAVMESH_EMPTY" in _codes(issues)


def test_missing_spawns_is_its_own_code(tmp_path):
    payload = {"ok": False, "path_proofs": [], "walkers": [],
               "error": "no player proxies in group 'lt_player_spawn'"}
    issues = WalktestAdapter().normalize_validation([_report(tmp_path, payload)])
    assert "WALKTEST_NO_SPAWNS" in _codes(issues)


def test_several_failures_are_several_findings(tmp_path):
    payload = {**PASSING, "ok": False,
               "path_proofs": [{"leg": "a->b", "ok": False, "detail": "d"},
                               {"leg": "b->c", "ok": False, "detail": "d"}],
               "walkers": [{"name": "bot_0", "status": "stuck",
                            "targets_reached": 0, "targets_total": 1}]}
    issues = WalktestAdapter().normalize_validation([_report(tmp_path, payload)])
    assert _codes(issues) == ["WALKTEST_LEG_UNPATHABLE",
                              "WALKTEST_LEG_UNPATHABLE",
                              "WALKTEST_WALKER_STUCK"]


# --- the rollout flag --------------------------------------------------------

def test_findings_warn_while_the_library_is_remediated(tmp_path):
    assert WT.WALKTEST_ENFORCED is False
    payload = {**PASSING, "ok": False,
               "path_proofs": [{"leg": "a->b", "ok": False, "detail": "d"}]}
    issue = WalktestAdapter().normalize_validation([_report(tmp_path, payload)])[0]
    assert issue["blocking"] is False and issue["severity"] == "major"


def test_the_same_finding_blocks_once_enforced(tmp_path):
    payload = {**PASSING, "ok": False,
               "path_proofs": [{"leg": "a->b", "ok": False, "detail": "d"}]}
    WT.WALKTEST_ENFORCED = True
    try:
        issue = WalktestAdapter().normalize_validation(
            [_report(tmp_path, payload)])[0]
        assert issue["blocking"] is True and issue["severity"] == "blocker"
        # The finding itself does not change -- only what happens to it.
        assert issue["code"] == "WALKTEST_LEG_UNPATHABLE"
    finally:
        WT.WALKTEST_ENFORCED = False


# --- pre-flight and the planned command --------------------------------------

def test_preflight_refuses_without_a_godot_binary(tmp_path):
    scene = tmp_path / "site_navqa.tscn"
    scene.write_text("[gd_scene]", encoding="utf-8")
    problems = WalktestAdapter().validate_configuration(
        {"navqa_scene": str(scene), "lot_repository": str(tmp_path),
         "staging_dir": str(tmp_path / "stage")},
        {"work_dir": str(tmp_path)})
    assert any("godot_executable" in p for p in problems)


def test_preflight_refuses_when_lot_never_emitted_the_scene(tmp_path):
    problems = WalktestAdapter().validate_configuration(
        {"lot_repository": str(tmp_path), "staging_dir": str(tmp_path)},
        {"work_dir": str(tmp_path), "godot_executable": "/usr/bin/godot"})
    assert any("navqa=True" in p for p in problems)


def test_command_requires_godot_and_redirects_the_report(tmp_path, monkeypatch):
    """--require and --report-dir are the two flags this stage cannot work
    without: one stops a skipped check from passing, the other puts the report
    where the scheduler looks."""
    import packages.staging.godot_project as gp
    project = tmp_path / "stage" / "proj"
    project.mkdir(parents=True)
    monkeypatch.setattr(gp, "stage_godot_project",
                        lambda *a, **k: (project, "res://site_navqa.tscn"))

    scene = tmp_path / "site_navqa.tscn"
    scene.write_text("[gd_scene]", encoding="utf-8")
    work = tmp_path / "work"
    work.mkdir()

    cmd = WalktestAdapter().plan_commands(
        {"navqa_scene": str(scene), "lot_repository": str(tmp_path),
         "staging_dir": str(tmp_path / "stage")},
        {"work_dir": str(work), "godot_executable": "/opt/godot4",
         "python_executable": sys.executable})[0]

    assert "--require" in cmd.arguments
    assert "--report-dir" in cmd.arguments
    assert cmd.arguments[cmd.arguments.index("--report-dir") + 1] == str(work)
    # walktest.py finds Godot through the environment; run_command copies
    # os.environ and updates it with this mapping, so the child sees it.
    assert cmd.environment["LOT_GODOT"] == "/opt/godot4"
    assert cmd.expected_outputs == (REPORT_NAME,)
    assert cmd.resource_class == "godot_headless"


def test_the_director_is_part_of_the_fingerprint(tmp_path):
    """Lot's VERSION moves for reasons unrelated to the nav QA scripts, and the
    scripts change without it moving. Hash what runs."""
    repo = tmp_path / "lot"
    addon = repo / "godot" / "addons" / "heist_nav_qa"
    addon.mkdir(parents=True)
    (repo / "walktest.py").write_text("# runner", encoding="utf-8")
    (addon / "nav_qa_director.gd").write_text("extends Node3D", encoding="utf-8")
    scene = tmp_path / "site_navqa.tscn"
    scene.write_text("[gd_scene]", encoding="utf-8")

    fp = WalktestAdapter().fingerprint_inputs(
        {"navqa_scene": str(scene), "lot_repository": str(repo)},
        {"work_dir": str(tmp_path)})
    assert "scene_hash" in fp
    hashes = fp["director_hashes"]
    assert "walktest.py" in hashes
    assert "godot/addons/heist_nav_qa/nav_qa_director.gd" in hashes

    before = dict(hashes)
    (addon / "nav_qa_director.gd").write_text("extends Node3D # edited",
                                              encoding="utf-8")
    after = WalktestAdapter().fingerprint_inputs(
        {"navqa_scene": str(scene), "lot_repository": str(repo)},
        {"work_dir": str(tmp_path)})["director_hashes"]
    assert after != before


def test_probe_reads_the_lot_checkout(tmp_path):
    """There is no walktest repository. The tool behind this adapter is Lot,
    and a fingerprint that forgets which Lot ran the QA is a fingerprint that
    cannot answer the only question it exists to answer."""
    repo = tmp_path / "lot"
    repo.mkdir()
    (repo / "VERSION").write_text("Lot 0.25.0\n", encoding="utf-8")
    probe = WalktestAdapter().probe({"repositories": {"lot": str(repo)}})
    assert probe.available
    assert "0.25.0" in str(probe.tool_version)
