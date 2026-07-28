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


# --- an anchor on a scrap is its own defect ----------------------------------

ISOLATED = {
    "ok": False,
    "anchors": [
        {"name": "home", "raw": [36.0, 1.0, 5.0], "snap": [35.6, 0.2, 5.2],
         "snap_m": 0.92, "reaches": 18, "of": 20, "cluster_size": 5,
         "main_cluster_size": 5, "coincident_with": ""},
        {"name": "proxy_1", "raw": [-90.0, 5.9, 2.0], "snap": [-90.6, 5.2, 0.4],
         "snap_m": 1.85, "reaches": 1, "of": 20, "cluster_size": 2,
         "main_cluster_size": 5, "coincident_with": "proxy_0"},
    ],
    "stranded_anchors": 1,
    "path_proofs": [
        {"leg": "proxy_0->proxy_1", "ok": False, "isolated_endpoint": "proxy_1",
         "detail": "proxy_1 is isolated (reaches no other anchor); path stops "
                   "32.71 m short (disjoint islands)"},
        {"leg": "proxy_1->proxy_2", "ok": False, "isolated_endpoint": "proxy_1",
         "detail": "proxy_1 is isolated (reaches no other anchor); path stops "
                   "32.71 m short (disjoint islands)"},
    ],
    "walkers": [{"name": "bot_0", "status": "ok", "targets_reached": 1,
                 "targets_total": 1}],
}


def test_an_isolated_anchor_is_reported_as_the_anchor(tmp_path):
    """It passes every distance check -- it IS on the mesh -- and it reaches
    nothing. That is not a fact about the route."""
    issues = WalktestAdapter().normalize_validation([_report(tmp_path, ISOLATED)])
    assert _codes(issues) == ["WALKTEST_ANCHOR_ISOLATED"]
    assert "cluster of 2 while the main one has 5" in issues[0]["message"]
    assert "shares a position with proxy_0" in issues[0]["message"]
    assert "1.85" in issues[0]["message"]
    assert issues[0]["category"] == "anchor"


def test_legs_blamed_on_a_stranded_anchor_are_not_reported_twice(tmp_path):
    """Two legs failed, both because the same anchor is stranded. One defect,
    one finding -- otherwise the count grows with the graph and the reader
    goes looking for a routing problem."""
    issues = WalktestAdapter().normalize_validation([_report(tmp_path, ISOLATED)])
    assert "WALKTEST_LEG_UNPATHABLE" not in _codes(issues)


def test_a_genuinely_blocked_leg_is_still_reported(tmp_path):
    """The suppression is narrow: only legs the director actually blamed on a
    stranded anchor. A route blocked between two healthy anchors still fails."""
    payload = {**ISOLATED, "path_proofs": [
        {"leg": "proxy_0->proxy_1", "ok": False, "isolated_endpoint": "proxy_1",
         "detail": "isolated"},
        {"leg": "home->proxy_0", "ok": False, "detail": "no navmesh path"}]}
    codes = _codes(WalktestAdapter().normalize_validation([_report(tmp_path, payload)]))
    assert codes == ["WALKTEST_ANCHOR_ISOLATED", "WALKTEST_LEG_UNPATHABLE"]


def test_a_report_without_the_anchors_array_still_reports_legs(tmp_path):
    """Reports written by a director older than this change carry no `anchors`.
    They must keep reporting exactly as before rather than going quiet."""
    payload = {**PASSING, "ok": False,
               "path_proofs": [{"leg": "a->b", "ok": False, "detail": "d"}]}
    assert _codes(WalktestAdapter().normalize_validation(
        [_report(tmp_path, payload)])) == ["WALKTEST_LEG_UNPATHABLE"]


def test_an_anchor_that_reaches_only_its_duplicate_is_still_off_the_network(tmp_path):
    """The threshold that missed sixteen of twenty-one anchors. Lot emits four
    duplicate marker pairs per site, so `reaches == 0` never fired: each
    stranded anchor could still see its own twin."""
    payload = {**ISOLATED}
    issues = WalktestAdapter().normalize_validation([_report(tmp_path, payload)])
    assert _codes(issues) == ["WALKTEST_ANCHOR_ISOLATED"]
    # reaches is 1, not 0 -- the cluster is what makes it a finding.
    assert payload["anchors"][1]["reaches"] == 1


def test_an_older_report_falls_back_to_the_reaches_threshold(tmp_path):
    """A director from before the clusters existed still reports something."""
    payload = {"ok": False, "path_proofs": [], "walkers": [], "anchors": [
        {"name": "proxy_0", "snap": [1.0, 2.0, 3.0], "snap_m": 1.9,
         "reaches": 0, "of": 20}]}
    issues = WalktestAdapter().normalize_validation([_report(tmp_path, payload)])
    assert _codes(issues) == ["WALKTEST_ANCHOR_ISOLATED"]
    assert "reaching 0 of 20" in issues[0]["message"]


# --- an anchor whose storey never baked --------------------------------------

NO_FLOOR = {
    "ok": False,
    "anchors": [
        {"name": "home", "raw": [0.0, 0.0, 0.0], "snap": [0.0, 0.2, 0.0],
         "snap_m": 0.2, "no_standing_room": False, "reaches": 1, "of": 2,
         "cluster_size": 2, "main_cluster_size": 2},
        {"name": "proxy_0", "raw": [-88.0, 0.0, 6.0], "snap": [-88.0, 0.0, 6.0],
         "snap_m": 0.0, "no_standing_room": True, "reaches": 0, "of": 2,
         "cluster_size": 1, "main_cluster_size": 2},
    ],
    "path_proofs": [
        {"leg": "home->proxy_0", "ok": False, "isolated_endpoint": "proxy_0",
         "no_standing_room": True,
         "detail": "no standing room on the anchor's own storey within 6 m"},
    ],
    "walkers": [],
}


def test_an_anchor_with_no_floor_is_its_own_code(tmp_path):
    """Distinct from ANCHOR_ISOLATED, and the distinction is the whole point.
    Isolated means the anchor stands somewhere real that connects to nothing;
    this means the director searched the anchor's own storey and found nowhere
    to stand at all. One is a placement defect, the other is a room that did
    not bake, and they send a reader to different repos."""
    issues = WalktestAdapter().normalize_validation([_report(tmp_path, NO_FLOOR)])
    assert _codes(issues) == ["WALKTEST_ANCHOR_NO_FLOOR"]
    assert "no walkable surface anywhere on its own storey" in issues[0]["message"]
    assert "(-88.0, 0.0, 6.0)" in issues[0]["message"]


def test_legs_into_a_floorless_anchor_are_not_reported_twice(tmp_path):
    issues = WalktestAdapter().normalize_validation([_report(tmp_path, NO_FLOOR)])
    assert "WALKTEST_LEG_UNPATHABLE" not in _codes(issues)


# --- a marker a body cannot get close to -------------------------------------

BURIED = {
    "ok": True,
    "anchors": [],
    "path_proofs": [
        {"leg": "home->proxy_0", "ok": True, "length_m": 20.0,
         "stand_offset_m": 3.4, "marker_buried": True,
         "detail": "path 20.0 m, 8 points; nearest standing room is 3.4 m "
                   "from the marker"},
        {"leg": "proxy_0->proxy_1", "ok": True, "length_m": 8.0,
         "stand_offset_m": 0.2, "detail": "path 8.0 m, 4 points"},
    ],
    "walkers": [],
}


def test_a_buried_marker_is_intel_not_a_verdict(tmp_path):
    """LOOT_VAULT_CASH sits at the centre of an 8 x 6 m vault block, so the
    nearest place a body fits is 3 m away. The route is fine. The old
    proximity test failed this as `anchor off navmesh`, which blamed the
    navmesh for where a marker was put."""
    issues = WalktestAdapter().normalize_validation([_report(tmp_path, BURIED)])
    assert _codes(issues) == ["WALKTEST_MARKER_BURIED"]
    assert issues[0]["severity"] == "minor"
    assert issues[0]["blocking"] is False
    assert "proxy_0" in issues[0]["message"]


def test_a_buried_marker_does_not_block_even_once_enforced(tmp_path):
    """Enforcement is about navigability. A marker inside the furniture is a
    content note, and flipping the flag must not turn it into a gate."""
    WT.WALKTEST_ENFORCED = True
    try:
        issues = WalktestAdapter().normalize_validation([_report(tmp_path, BURIED)])
    finally:
        WT.WALKTEST_ENFORCED = False
    assert issues[0]["severity"] == "minor"
    assert issues[0]["blocking"] is False


def test_a_passing_run_with_no_buried_markers_stays_silent(tmp_path):
    payload = {**BURIED, "path_proofs": [
        {"leg": "home->proxy_0", "ok": True, "length_m": 20.0,
         "stand_offset_m": 0.3, "detail": "path 20.0 m, 8 points"}]}
    assert WalktestAdapter().normalize_validation(
        [_report(tmp_path, payload)]) == []


# --- findings have to survive the trip out of here ---------------------------

def test_every_finding_this_adapter_can_emit_is_json_serializable(tmp_path):
    """A whole four-seed run died on `Object of type WindowsPath is not JSON
    serializable` after three seeds had finished their 200 s walker sims,
    because one finding out of eight passed a Path where the others passed an
    f-string. Every test above asserted codes and messages and not one of them
    ever wrote the result out, which is the only thing the pipeline does with
    it. Exercise every payload in this file through the serializer."""
    payloads = {"PASSING": PASSING, "ISOLATED": ISOLATED,
                "NO_FLOOR": NO_FLOOR, "BURIED": BURIED,
                "BEHIND_BARRIER": BEHIND_BARRIER,
                "STUCK": STUCK_ON_GEOMETRY,
                "STUCK_NONE": STUCK_ON_NOTHING}
    for name, payload in payloads.items():
        issues = WalktestAdapter().normalize_validation(
            [_report(tmp_path, payload)])
        json.dumps(issues)  # raises TypeError on any non-primitive
        for issue in issues:
            assert isinstance(issue["location"], str), (name, issue["code"])


# --- an anchor sealed in behind a breach panel -------------------------------

BEHIND_BARRIER = {
    "ok": True,
    "anchors": [
        {"name": "home", "raw": [0.0, 0.0, 0.0], "snap": [0.0, 0.2, 0.0],
         "snap_m": 0.2, "unreachable_stand_m": 0.0, "no_standing_room": False,
         "reaches": 1, "of": 2, "cluster_size": 2, "main_cluster_size": 2},
        {"name": "proxy_3", "raw": [-94.0, -4.0, -10.0],
         "snap": [-95.0, -3.7, -13.4], "snap_m": 3.55,
         "unreachable_stand_m": 3.54, "no_standing_room": False,
         "reaches": 1, "of": 2, "cluster_size": 2, "main_cluster_size": 2},
    ],
    "path_proofs": [{"leg": "home->proxy_3", "ok": True, "length_m": 40.0,
                     "stand_offset_m": 3.55, "detail": "path 40.0 m, 12 points"}],
    "walkers": [],
}


def test_a_sealed_anchor_reports_the_substitution(tmp_path):
    """The one place the walktest passes over a substitution, so it has to say
    so. The vault's only opening is a reinforceable concrete breach panel: the
    nearest standing room is inside, unreachable, and the QA uses the nearest
    connected one instead. Both distances belong in the finding."""
    issues = WalktestAdapter().normalize_validation(
        [_report(tmp_path, BEHIND_BARRIER)])
    assert _codes(issues) == ["WALKTEST_ANCHOR_BEHIND_BARRIER"]
    assert issues[0]["severity"] == "minor"
    assert issues[0]["blocking"] is False
    assert "proxy_3 (3.5 m -> 3.5 m)" in issues[0]["message"]
    assert "proved to the barrier rather than through it" in issues[0]["message"]


def test_a_sealed_anchor_is_not_also_reported_as_isolated(tmp_path):
    """It is on the main cluster now, by construction. If both fired, the
    reader would be told the same anchor is fine and broken."""
    codes = _codes(WalktestAdapter().normalize_validation(
        [_report(tmp_path, BEHIND_BARRIER)]))
    assert "WALKTEST_ANCHOR_ISOLATED" not in codes


def test_a_zero_barrier_distance_is_silence_not_a_finding(tmp_path):
    payload = {**BEHIND_BARRIER, "anchors": [
        {**BEHIND_BARRIER["anchors"][1], "unreachable_stand_m": 0.0}]}
    assert WalktestAdapter().normalize_validation(
        [_report(tmp_path, payload)]) == []


# --- a stuck walker has to say what stopped it -------------------------------

STUCK_ON_GEOMETRY = {
    "ok": False, "anchors": [], "path_proofs": [],
    "walkers": [{
        "name": "player_0", "status": "stuck@target_8 at (20.5, 0.9, -2.7)",
        "targets_reached": 8, "targets_total": 16, "at": [20.5, 0.9, -2.7],
        "blocked_by": [{"collider": "gaming_tables_col", "path": "/root/x",
                        "normal": [1.0, 0.0, 0.0], "at": [21.0, 0.5, -2.7]}],
        "waypoint": [26.0, 0.2, -2.0], "waypoint_dist_m": 5.6,
        "path_index": 3, "path_points": 9,
    }],
}

STUCK_ON_NOTHING = {
    **STUCK_ON_GEOMETRY,
    "walkers": [{**STUCK_ON_GEOMETRY["walkers"][0], "blocked_by": []}],
}


def test_a_stuck_walker_names_what_it_is_pressing_against(tmp_path):
    issues = WalktestAdapter().normalize_validation(
        [_report(tmp_path, STUCK_ON_GEOMETRY)])
    assert _codes(issues) == ["WALKTEST_WALKER_STUCK"]
    m = issues[0]["message"]
    assert "pressing against gaming_tables_col" in m
    assert "5.6 m from waypoint 3/9" in m


def test_touching_nothing_is_reported_as_this_tools_defect(tmp_path):
    """The distinction that matters. A capsule wedged in geometry is a level
    defect; a capsule stopped in open space with nothing in contact is the
    walker's steering giving up, and blaming the level for that is how an
    afternoon goes missing."""
    issues = WalktestAdapter().normalize_validation(
        [_report(tmp_path, STUCK_ON_NOTHING)])
    m = issues[0]["message"]
    assert "touching NOTHING" in m
    assert "this tool's defect rather than the level's" in m


def test_a_report_from_a_director_that_records_neither_still_reports(tmp_path):
    payload = {**STUCK_ON_GEOMETRY, "walkers": [{
        "name": "player_0", "status": "stuck@target_8 at (20.5, 0.9, -2.7)",
        "targets_reached": 8, "targets_total": 16, "at": [20.5, 0.9, -2.7]}]}
    issues = WalktestAdapter().normalize_validation([_report(tmp_path, payload)])
    assert _codes(issues) == ["WALKTEST_WALKER_STUCK"]
    assert "pressing against" not in issues[0]["message"]
    assert "touching NOTHING" not in issues[0]["message"]
