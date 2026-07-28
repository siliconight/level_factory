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


# ---------------------------------------------------------------------------
# pre-flight: what the adapter refuses before Godot is launched at all
# ---------------------------------------------------------------------------
_SITE_RING = '''[gd_scene load_steps=2 format=3]

[sub_resource type="BoxShape3D" id="BoxShape_Street"]
size = Vector3(120, 0.5, 6)

[node name="Site" type="Node3D"]

[node name="Street_N" type="StaticBody3D" parent="."]
transform = Transform3D(1, 0, 0, 0, 1, 0, 0, 0, 1, 0, -0.25, 40)

[node name="col" type="CollisionShape3D" parent="./Street_N"]
shape = SubResource("BoxShape_Street")
'''

_WALK = '''[gd_scene load_steps=2 format=3]

[ext_resource type="PackedScene" path="res://site.tscn" id="site"]

[node name="SiteWalk" type="Node3D"]
spawn_pos = Vector3(0, 1, 0)
objective_pos = Vector3(10, 0, 5)
extraction_pos = Vector3(0, 0, 40)

[node name="Site" parent="." instance=ExtResource("site")]
'''


def _scene(tmp_path, site=_SITE_RING, walk=_WALK) -> Path:
    (tmp_path / "site.tscn").write_text(site, encoding="utf-8")
    level = tmp_path / "level.tscn"
    level.write_text(walk, encoding="utf-8")
    return level


def _preflight(scene: Path):
    return LaserTagAdapter().validate_configuration(
        {"evaluation_scene": str(scene)}, {"godot_executable": "godot"})


def test_a_mission_standing_over_a_hole_is_refused_before_the_run(tmp_path):
    """The shipped defect: streets around an unfloored block, the whole mission
    inside the void. Laser Tag rays down from the spawn, hits nothing, refuses
    the map with NO_WORLD_COLLISION, and reports zero runs 900 seconds later.
    The scene text already said so."""
    problems = _preflight(_scene(tmp_path))
    assert any("no ground beneath them" in p for p in problems)
    assert any("NO_WORLD_COLLISION" in p for p in problems)


def test_a_floored_mission_passes_pre_flight(tmp_path):
    """The gate has to let a good scene through, or it is just an outage."""
    floored = _SITE_RING.replace("size = Vector3(120, 0.5, 6)",
                                 "size = Vector3(120, 0.5, 120)").replace(
        "0, -0.25, 40)", "0, -0.25, 0)")
    assert _preflight(_scene(tmp_path, site=floored)) == []


def test_the_navmesh_is_baked_the_way_lasertags_own_ci_bakes_it(tmp_path):
    """Lot ships the NavigationRegion3D with parameters and no polygons. Without
    --bake-nav every reachability test in the harness reads as unreachable — and
    Laser Tag's own CI passes the flag, so the pipeline was running the tool in a
    configuration its authors never test."""
    planned = LaserTagAdapter().plan_commands(
        {"evaluation_scene": str(_scene(tmp_path)), "seed": 1},
        {"work_dir": str(tmp_path), "godot_executable": "godot"})
    assert "--bake-nav" in planned[0].arguments


# ---------------------------------------------------------------------------
# the third state: it ran, it reported, and it measured nothing
# ---------------------------------------------------------------------------
def _degraded_report(tmp_path, **over):
    """A real seed-5017 report in miniature: 25 runs, a full set of numbers,
    and NAVIGATION_MISSING underneath every one of them."""
    fields = dict(
        grade="FAIL", overall_score=40, runs=25,
        findings=[
            {"severity": "WARN", "type": "NAVIGATION_MISSING",
             "message": ("No usable NavigationRegion3D/NavigationMesh found. "
                         "Falling back to direct movement (TDD 29.1).")},
            {"severity": "FAIL", "type": "TRAVERSAL",
             "message": "0% route completion across 25 runs."},
            {"severity": "WARN", "type": "ENEMY_STUCK",
             "message": "Enemies stuck 57 times."},
            {"severity": "WARN", "type": "BLIND_MAP",
             "message": "74% of sampled positions see no other position."},
        ])
    fields.update(over)
    return _report(tmp_path, **fields)


def test_a_run_without_navigation_blocks_even_though_every_run_completed(tmp_path):
    """The defect this section exists to prevent. Laser Tag played all 25 runs
    and wrote a complete report, so `was_evaluated` said yes and the pipeline
    presented sixteen findings about pacing, cover and traversal as facts about
    the level. The bots had no navmesh: they walked into walls for 25 straight
    matches. Every one of those numbers described the fallback."""
    issues = LaserTagAdapter().normalize_validation([_degraded_report(tmp_path)])
    blocker = next(i for i in issues if i["code"] == "LT_EVALUATED_DEGRADED")
    assert blocker["blocking"] is True
    assert blocker["severity"] == "blocker"
    assert blocker["category"] == "tool_contract"
    # It has to name the cause, not just the symptom.
    assert "NAVIGATION_MISSING" in blocker["message"]
    assert "25 runs" in blocker["message"]


def test_pathfinding_derived_findings_are_not_presented_as_measurements(tmp_path):
    """0% route completion is true of the run and says nothing about the map.
    Keep it -- deleting evidence is its own lie -- but stop ranking it MAJOR
    above the one finding that actually needs fixing."""
    issues = LaserTagAdapter().normalize_validation([_degraded_report(tmp_path)])
    by_code = {i["code"]: i for i in issues}
    assert by_code["LT_MAP_TRAVERSAL"]["severity"] == "info"
    assert by_code["LT_MAP_ENEMY_STUCK"]["severity"] == "info"
    # ...and it still reads correctly when quoted on its own.
    assert "not a measurement of this map" in by_code["LT_MAP_TRAVERSAL"]["message"]
    assert "0% route completion" in by_code["LT_MAP_TRAVERSAL"]["message"]


def test_sightline_findings_survive_a_degraded_run_intact(tmp_path):
    """Blind/exposure sampling rays between static sampled positions. It never
    asked the navmesh anything, so it is still a fact about the map -- demoting
    it would throw away the one real finding in a degraded report."""
    issues = LaserTagAdapter().normalize_validation([_degraded_report(tmp_path)])
    blind = next(i for i in issues if i["code"] == "LT_MAP_BLIND_MAP")
    assert blind["severity"] == "moderate"
    assert "not a measurement" not in blind["message"]


def test_a_degraded_run_is_not_reported_as_a_low_readiness_map(tmp_path):
    """grade FAIL / score 40 over a match played without pathfinding is not a
    readiness signal. Printed as one it sends someone off to tune combat pacing
    on a level whose only defect is a missing navmesh."""
    issues = LaserTagAdapter().normalize_validation([_degraded_report(tmp_path)])
    assert all(i["code"] != "LT_LOW_READINESS" for i in issues)


def test_a_healthy_run_is_untouched_by_the_degraded_path(tmp_path):
    """The gate has to let a real evaluation through with its severities intact,
    or it is just an outage that hides findings."""
    rep = _degraded_report(tmp_path, findings=[
        {"severity": "FAIL", "type": "TRAVERSAL",
         "message": "0% route completion across 25 runs."}])
    issues = LaserTagAdapter().normalize_validation([rep])
    by_code = {i["code"]: i for i in issues}
    assert "LT_EVALUATED_DEGRADED" not in by_code
    assert by_code["LT_MAP_TRAVERSAL"]["severity"] == "major"
    assert "LT_LOW_READINESS" in by_code   # grade FAIL, and this time it means it


def test_zero_runs_still_leads_with_never_ran_not_degraded(tmp_path):
    """Both statements are true of a report with 0 runs and no navmesh. Only the
    earlier one is useful, and two blockers for one fault is noise."""
    rep = _degraded_report(tmp_path, runs=0)
    issues = LaserTagAdapter().normalize_validation([rep])
    codes = {i["code"] for i in issues}
    assert "LT_NOT_EVALUATED" in codes
    assert "LT_EVALUATED_DEGRADED" not in codes


def test_candidate_metrics_flag_a_score_that_ranks_nothing(tmp_path):
    """Selection compares these scores across candidates. Two candidates whose
    bots both walked into walls are not comparable at all."""
    m = LaserTagAdapter().read_metrics(_degraded_report(tmp_path))
    assert m["lasertag_evaluated"] is True      # it did run
    assert m["lasertag_degraded"] is True       # and it measured nothing
    assert "not the map" in m["lasertag_note"]


def test_the_run_summary_line_does_not_call_a_blind_run_evaluated():
    """`laser_tag: 3/3 evaluated` over three navigation-less runs is the exact
    sentence that let this ship."""
    from packages.validation.lasertag_report import summarize

    nav = [{"severity": "WARN", "type": "NAVIGATION_MISSING", "message": "x"}]
    line = summarize([{"runs": 25, "findings": nav},
                      {"runs": 25, "findings": nav},
                      {"runs": 25, "findings": []}])
    assert "3/3 evaluated" in line
    assert "2 without navigation" in line


# ---------------------------------------------------------------------------
# the fourth state: navigation worked, the numbers are real, and the crew
# never arrived
# ---------------------------------------------------------------------------
def _real_report(tmp_path, **over):
    """Seed 5320 in miniature, from the first run where the navmesh baked.

    25 matches, 1025 navmesh polygons, every number a measurement -- and route
    completion 0.0 on all five seeds, reported as "none blocking".
    """
    fields = dict(
        grade="WARN", overall_score=50, runs=25,
        summary={"route_completion_rate": 0.0, "timeout_count": 4,
                 "team_wipe_count": 21, "player_stuck_events": 174},
        findings=[
            {"severity": "FAIL", "type": "TRAVERSAL",
             "message": "Bot rarely completed the route (0% of runs)."},
            {"severity": "WARN", "type": "PLAYER_STUCK",
             "message": "Player got stuck 174 time(s)."},
            {"severity": "PASS", "type": "EXPOSURE",
             "message": "Only 5% of positions are overexposed."},
            {"severity": "PASS", "type": "COVER_BLOCKING",
             "message": "World collision blocked 40% of shots."},
        ])
    fields.update(over)
    return _report(tmp_path, **fields)


def test_a_pass_is_not_filed_as_a_defect(tmp_path):
    """`LT_ScoreCalculator` prints its passes under a "Good:" heading and ships
    them in the same `findings` array as the failures, told apart only by
    severity PASS. `_SEVERITY` had no PASS key, so `.get(..., "minor")` filed
    "World collision blocked 40% of shots" as a MINOR problem with the level."""
    issues = LaserTagAdapter().normalize_validation([_real_report(tmp_path)])
    codes = {i["code"] for i in issues}
    assert "LT_MAP_EXPOSURE" not in codes
    assert "LT_MAP_COVER_BLOCKING" not in codes
    # ...and the real findings in the same array are untouched.
    assert "LT_MAP_TRAVERSAL" in codes
    assert "LT_MAP_PLAYER_STUCK" in codes


def test_passes_are_kept_as_evidence_not_deleted(tmp_path):
    """Dropping them from the findings list must not mean losing them: they are
    what the map got right, and something has to be able to say so."""
    from packages.validation.lasertag_report import passing_findings

    data = json.loads(_real_report(tmp_path).read_text())
    assert [f["type"] for f in passing_findings(data)] == [
        "EXPOSURE", "COVER_BLOCKING"]
    assert LaserTagAdapter().read_metrics(_real_report(tmp_path))[
        "lasertag_passes"] == 2


def test_a_pass_is_not_quoted_as_a_reason_the_map_failed(tmp_path):
    """`failure_summary` is pasted into the LT_NOT_EVALUATED blocker as "Laser
    Tag said:". Listing a pass there says the map could not be played because
    something about it was fine."""
    from packages.validation.lasertag_report import failure_summary

    data = json.loads(_real_report(tmp_path).read_text())
    assert "overexposed" not in failure_summary(data)
    assert "Bot rarely completed" in failure_summary(data)


def test_an_unrecognised_severity_is_not_quietly_minor(tmp_path):
    """A severity this module has not heard of is one Laser Tag added. Guessing
    low files a real defect under the heading nobody reads; guessing high costs
    someone a minute. This is the same asymmetry NAV_DERIVED_TYPES follows."""
    rep = _real_report(tmp_path, findings=[
        {"severity": "CRITICAL", "type": "GEOMETRY_HOLE",
         "message": "The floor has a hole in it."}])
    issues = LaserTagAdapter().normalize_validation([rep])
    hole = next(i for i in issues if i["code"] == "LT_MAP_GEOMETRY_HOLE")
    assert hole["severity"] == "moderate"


def test_a_route_never_walked_on_a_full_clock_reports_but_does_not_block(tmp_path):
    """This blocked until Level Factory 0.20.0, and the reasoning was sound when
    it was written: five seeds, 125 matches, route completion 0.0 in every one,
    and the build printing "56 finding(s) -- none blocking". Four of seed 5320's
    runs went the full 180 s with the crew alive and still never reached the
    objective, and that is a measurement rather than a score.

    What changed is that walktest_navqa now measures the same claim directly, on
    every candidate, with no combat in it -- while this number is confounded by
    everything combat does. That same seed 5320 report carries 835 player-stuck
    events and six team wipes alongside the timeouts.

    And the ordering settled it. The scheduler fail-fasts on the first blocked
    job, so while this blocked, seed 5320's own walktest never dispatched: the
    firefight silenced the instrument built to replace it, and the stale report
    left in its place read as a passing geometry check for an evening.

    So it reports, it points at the walktest, and it leaves the verdict there.
    """
    issues = LaserTagAdapter().normalize_validation([_real_report(tmp_path)])
    found = next(i for i in issues if i["code"] == "LT_ROUTE_NEVER_COMPLETED")
    assert found["blocking"] is False
    assert found["severity"] == "major"
    # The category does NOT change: it is still a statement about reachability,
    # and filing it under readiness would lose that.
    assert found["category"] == "reachability"
    assert "4 of those ran the full clock" in found["message"]
    # It has to name the instrument that does own the verdict, or the reader is
    # left with a demoted finding and nowhere to go.
    assert "walktest_navqa" in found["message"]
    # And it still must not be mistakable for the score it sits beside.
    assert "not a difficulty score" in found["message"]
def test_a_route_never_walked_but_never_given_time_does_not_block(tmp_path):
    """The line the gate has to hold. A crew wiped five seconds in proves
    nothing about the geometry -- that is difficulty, and TDD 5.5 says
    difficulty never blocks a build. Blocking here would make the pipeline
    refuse to ship hard maps."""
    rep = _real_report(tmp_path, summary={
        "route_completion_rate": 0.0, "timeout_count": 0, "team_wipe_count": 25})
    issues = LaserTagAdapter().normalize_validation([rep])
    codes = {i["code"] for i in issues}
    assert "LT_ROUTE_NEVER_COMPLETED" not in codes
    unproven = next(i for i in issues if i["code"] == "LT_ROUTE_UNPROVEN")
    assert unproven["blocking"] is False
    assert unproven["severity"] == "moderate"
    # And it has to say which of the two it is, or the operator re-derives it.
    assert "difficulty, not" in unproven["message"]
    assert "untested" in unproven["message"]


def test_a_route_that_was_walked_raises_nothing(tmp_path):
    """The gate has to let a working map through, or it is just an outage."""
    rep = _real_report(tmp_path, summary={
        "route_completion_rate": 0.6, "timeout_count": 3, "team_wipe_count": 7})
    codes = {i["code"] for i in LaserTagAdapter().normalize_validation([rep])}
    assert "LT_ROUTE_NEVER_COMPLETED" not in codes
    assert "LT_ROUTE_UNPROVEN" not in codes


def test_an_opening_that_never_happened_is_reported_but_does_not_block(tmp_path):
    """The gap the two branches above left between them.

    Seed 5320 as it actually shipped: 25 runs, 25 team wipes, zero timeouts, so
    the geometry branch stands down and the difficulty branch takes it. But
    first contact averaged 0.21 s against Lot's 1.0 s REACTION_SECONDS -- the
    crew was fired on before it could act, 25 times out of 25, and never once
    survived long enough for the route to be testable. Difficulty is a property
    of a fight you got to have. This one never started, and it shipped."""
    rep = _real_report(tmp_path, summary={
        "route_completion_rate": 0.0, "timeout_count": 0, "team_wipe_count": 25,
        "avg_time_to_first_enemy_shot": 0.21})
    issues = LaserTagAdapter().normalize_validation([rep])
    finding = next(i for i in issues if i["code"] == "LT_NO_SURVIVABLE_OPENING")
    # Surfaced, never blocking. Laser Tag is not the authority on the combat
    # model this measures, so it informs Lot rather than refusing Lot's output;
    # `LOT_ROUTE_EXPOSED` is the owned guardrail that asks it of the geometry.
    assert finding["blocking"] is False
    assert finding["severity"] == "major"
    assert finding["category"] == "spawn"
    # It must name the window it measured against, or the number reads arbitrary.
    assert "0.21 s" in finding["message"]
    assert "1 s reaction window" in finding["message"]
    # And it must not be mistaken for the difficulty finding it displaces.
    assert "LT_ROUTE_UNPROVEN" not in {i["code"] for i in issues}


def test_a_hard_map_that_gave_the_crew_its_opening_still_does_not_block(tmp_path):
    """The line the new branch must not cross. Same wipe-only shape, but the
    crew had three seconds before anyone shot at them -- three times the window
    the placement promises. They were beaten, not denied. TDD 5.5 says
    difficulty never blocks a build, and this is difficulty."""
    rep = _real_report(tmp_path, summary={
        "route_completion_rate": 0.0, "timeout_count": 0, "team_wipe_count": 25,
        "avg_time_to_first_enemy_shot": 3.0})
    issues = LaserTagAdapter().normalize_validation([rep])
    codes = {i["code"] for i in issues}
    assert "LT_NO_SURVIVABLE_OPENING" not in codes
    unproven = next(i for i in issues if i["code"] == "LT_ROUTE_UNPROVEN")
    assert unproven["blocking"] is False


def test_an_unmeasured_opening_is_not_read_as_an_instant_one(tmp_path):
    """Absent is not zero, applied to the opening. A report that never measured
    the enemy's first shot must fall back to the non-blocking difficulty
    reading -- inferring the worst possible opening from a missing key would
    block a build on any Laser Tag whose summary lacks the field, which as of
    v0.7.x is all of them."""
    rep = _real_report(tmp_path, summary={
        "route_completion_rate": 0.0, "timeout_count": 0, "team_wipe_count": 25})
    codes = {i["code"] for i in LaserTagAdapter().normalize_validation([rep])}
    assert "LT_NO_SURVIVABLE_OPENING" not in codes
    assert "LT_ROUTE_UNPROVEN" in codes


def test_the_crews_own_opening_shot_is_never_read_as_being_shot_at(tmp_path):
    """The defect this branch shipped with, and the reason it now reads a
    different field.

    `avg_time_to_first_contact` is stamped by the first shot of a run from
    EITHER side — `LT_MetricsCollector.record_shot` sets it outside the
    `shooter_is_player` branch. Lot places enemies precisely so the crew
    acquires first: the crew's bot sees 45 m against the enemy's 35 m, and
    OPENING_RANGE is built to exactly that gap. So on a map placed as intended,
    the crew shoots first and time-to-first-contact is small BY DESIGN.

    Gating on it inverted the contract: it blocked hardest on the maps whose
    opening worked. Seed 5320 reported 0.21 s, which was read as an ambush and
    was at least partly the crew opening fire on schedule.

    A report carrying only the both-sides field must therefore not block."""
    rep = _real_report(tmp_path, summary={
        "route_completion_rate": 0.0, "timeout_count": 0, "team_wipe_count": 25,
        "avg_time_to_first_contact": 0.21})
    issues = LaserTagAdapter().normalize_validation([rep])
    codes = {i["code"] for i in issues}
    assert "LT_NO_SURVIVABLE_OPENING" not in codes
    assert "LT_ROUTE_UNPROVEN" in codes


def test_the_no_enemy_ever_fired_sentinel_does_not_block(tmp_path):
    """Laser Tag's `_avg` returns -1.0 for a metric no run recorded. A run where
    no enemy ever fired is the quietest possible opening, not the fastest, and a
    naive `< REACTION_SECONDS` reads the sentinel as an instant ambush and
    blocks the map hardest for having no enemies shoot at all."""
    rep = _real_report(tmp_path, summary={
        "route_completion_rate": 0.0, "timeout_count": 0, "team_wipe_count": 25,
        "avg_time_to_first_enemy_shot": -1.0})
    codes = {i["code"] for i in LaserTagAdapter().normalize_validation([rep])}
    assert "LT_NO_SURVIVABLE_OPENING" not in codes
    assert "LT_ROUTE_UNPROVEN" in codes


def test_the_reaction_window_boundary_is_the_contract_being_met(tmp_path):
    """Exactly REACTION_SECONDS is the promise kept, not broken. The comparison
    has to be strict, or a map that delivers precisely what Lot placed it to
    deliver gets blocked for it."""
    from packages.validation.lasertag_report import REACTION_SECONDS

    def codes_at(contact):
        rep = _real_report(tmp_path, summary={
            "route_completion_rate": 0.0, "timeout_count": 0,
            "team_wipe_count": 25, "avg_time_to_first_enemy_shot": contact})
        return {i["code"] for i in LaserTagAdapter().normalize_validation([rep])}

    assert "LT_NO_SURVIVABLE_OPENING" not in codes_at(REACTION_SECONDS)
    assert "LT_NO_SURVIVABLE_OPENING" in codes_at(REACTION_SECONDS - 0.001)


def test_a_timed_out_route_still_reads_as_geometry_not_opening(tmp_path):
    """Precedence. A run that ran the full clock with the crew alive is the
    stronger statement -- nothing stopped them walking except the map -- and it
    must keep reporting as reachability even when the opening was also brutal,
    or the operator gets sent to fix spawns on a level whose route is broken."""
    rep = _real_report(tmp_path, summary={
        "route_completion_rate": 0.0, "timeout_count": 4, "team_wipe_count": 21,
        "avg_time_to_first_enemy_shot": 0.21})
    codes = {i["code"] for i in LaserTagAdapter().normalize_validation([rep])}
    assert "LT_ROUTE_NEVER_COMPLETED" in codes
    assert "LT_NO_SURVIVABLE_OPENING" not in codes


def test_a_report_that_never_measured_completion_is_not_read_as_zero(tmp_path):
    """Absent is not zero. A report with no summary block did not measure the
    route; calling that 0% would block a build on a missing key."""
    rep = _real_report(tmp_path, summary={"timeout_count": 4})
    codes = {i["code"] for i in LaserTagAdapter().normalize_validation([rep])}
    assert "LT_ROUTE_NEVER_COMPLETED" not in codes
    assert "LT_ROUTE_UNPROVEN" not in codes
    assert LaserTagAdapter().read_metrics(rep)["lasertag_route_completion"] is None


def test_a_degraded_run_does_not_raise_the_route_blocker(tmp_path):
    """Without a navmesh the bots walk into walls, so 0% completion is a fact
    about the fallback. LT_EVALUATED_DEGRADED already blocks and already names
    the cause; a second blocker here would send someone to fix a route that was
    never tested."""
    rep = _degraded_report(tmp_path, summary={
        "route_completion_rate": 0.0, "timeout_count": 25, "team_wipe_count": 0})
    codes = {i["code"] for i in LaserTagAdapter().normalize_validation([rep])}
    assert "LT_EVALUATED_DEGRADED" in codes
    assert "LT_ROUTE_NEVER_COMPLETED" not in codes


def test_enemy_pathing_is_demoted_with_the_rest_of_the_pathfinding_numbers(tmp_path):
    """ENEMY_PATHING is emitted by the same calculator as ENEMY_STUCK off the
    same navigation agents, and was missing from NAV_DERIVED_TYPES -- so a
    navigation-less run reported "no enemy stuck events recorded" as a fact
    about the level, when it means the enemies never pathed at all."""
    rep = _degraded_report(tmp_path, findings=[
        {"severity": "WARN", "type": "NAVIGATION_MISSING",
         "message": "No usable NavigationRegion3D found."},
        {"severity": "WARN", "type": "ENEMY_PATHING",
         "message": "No enemy stuck events recorded."}])
    issues = LaserTagAdapter().normalize_validation([rep])
    pathing = next(i for i in issues if i["code"] == "LT_MAP_ENEMY_PATHING")
    assert pathing["severity"] == "info"
    assert "not a measurement of this map" in pathing["message"]
