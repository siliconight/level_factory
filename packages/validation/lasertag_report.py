"""Read a Laser Tag report honestly (TDD 5.5, 24.3).

Three separate things were wrong with how Level Factory read
``lasertag.report.json``:

* the report writes ``overall_score``; the adapter read ``score``, so every
  candidate card and every finding said "score None";
* the report's own ``findings`` array -- the list that says *why* the map could
  not be played -- was never read at all;
* and ``runs: 0`` was reported as "readiness grade BROKEN", which is a claim
  about the level. It is not. Zero runs means the evaluator never started, and
  a tool that reports a grade for a match it never played is a contract
  failure, not a low score.

That last distinction is the one that matters. TDD 5.5 forbids a *readiness
score* from blocking a build, and this module keeps that: grades and scores stay
non-blocking, always. "The evaluator could not run" is a different statement --
the same class of failure as the pipeline reporting five candidates it did not
build -- and it blocks.

There turned out to be a third state between those two, and it is the one that
wasted the most time. Laser Tag can play every run it was asked to play, write a
complete report, and still have measured nothing -- because the map came up
without navigation and the harness fell back to direct movement (TDD 29.1).
Bots then walk into walls for the whole match. The report that comes back is not
empty and not obviously wrong: it is a full set of numbers describing the
fallback rather than the level. Read at face value it produced sixteen findings
about pacing, cover, traversal and stuck enemies, every one of which was an
artifact, and none of which named the single thing to fix.

So: *evaluated* and *evaluated with navigation* are different claims. A run
without navigation blocks, exactly like a run that never happened, and the
numbers it derived from pathfinding are demoted to information with the reason
attached rather than presented as measurements of the map.

The first run that got past all three of those states produced a fourth. Every
number in the report was finally real -- navigation baked, 1025 polygons, 25
matches played -- and it said the bot completed the route in 0% of runs, on
every seed. The build passed with "none blocking", because this module treats
everything Laser Tag says as a readiness signal and TDD 5.5 forbids a readiness
signal from blocking.

That reading is too broad. A *score* is a judgement -- 50/100, grade WARN, "is
this map good" -- and it stays non-blocking forever. "The crew was given the
full clock, nobody killed them, and they still never reached the objective" is
not a judgement. It is the same statement the pre-flight already blocks on when
it reads the scene text and finds the destination sealed off, arrived at by
measurement instead of by geometry, and there is no defensible reason for the
static form of a fact to block while the measured form of it ships.

The distinction the gate turns on is whether a run had the *time* to prove the
route walkable. A match that ends in a team wipe five seconds in proves nothing
about the geometry -- that is difficulty, and difficulty is a score. A match
that runs the clock out proves the route was not walked. So 0% completion
blocks only when at least one run timed out, and otherwise says plainly that
the route was never tested.

Pure dicts in, findings out; no Godot, no filesystem.
"""
from __future__ import annotations

from typing import Mapping, Sequence

CODE_NOT_EVALUATED = "LT_NOT_EVALUATED"
CODE_DEGRADED = "LT_EVALUATED_DEGRADED"
CODE_LOW_READINESS = "LT_LOW_READINESS"
CODE_ROUTE_NEVER_COMPLETED = "LT_ROUTE_NEVER_COMPLETED"
CODE_ROUTE_UNPROVEN = "LT_ROUTE_UNPROVEN"
CODE_NO_SURVIVABLE_OPENING = "LT_NO_SURVIVABLE_OPENING"
CODE_MAP_PREFIX = "LT_MAP_"

READINESS_FLOOR = 40

#: The crew's reaction window in seconds -- the time the opening engagement is
#: built to give them before anything can shoot. Lot owns the number as
#: `site_spawns.REACTION_SECONDS` and derives its placement clearance from it
#: (`OPENING_CLEARANCE = CREW_SPEED * REACTION_SECONDS`), so an opening that
#: delivers less than this has not produced a hard map: it has broken the
#: contract the placement was built to satisfy.
#:
#: Carried here as a fallback rather than read from Lot. `normalize_validation`
#: is handed report files and nothing else -- no repository path, no context --
#: and Lot cannot be imported from Level Factory in any case. This mirrors the
#: agent contract's rule for its consumers: the fallback equals the ratified
#: value, so if the two ever drift this gate reads slightly lenient rather than
#: crashing. `advise_configuration` is where the live constant gets read.
REACTION_SECONDS = 1.0

#: Laser Tag finding types that mean the match was played without working
#: navigation. The harness says so itself and then keeps going, which is the
#: right call for a tool -- a half-run is more diagnostic than a refusal -- but
#: it makes the report look like a verdict on the level.
DEGRADED_TYPES = frozenset({"NAVIGATION_MISSING"})

#: Findings that are downstream of pathfinding, and therefore describe the
#: fallback rather than the map when the run was degraded. Sightline sampling
#: (BLIND_MAP, EXPOSURE) is not in this set on purpose: those are cast from
#: static sampled positions and stay true whether or not the bots could walk.
#:
#: An unlisted type keeps the severity Laser Tag gave it. Overstating a finding
#: is recoverable -- the degraded blocker sits above it saying how to read the
#: whole report -- whereas silently demoting a finding this list has not heard
#: of would hide a real defect behind a bug in this list.
NAV_DERIVED_TYPES = frozenset({
    "TRAVERSAL", "ROUTE_INCOMPLETE", "UNREACHABLE",
    "ENEMY_STUCK", "PLAYER_STUCK", "ENEMY_PATHING",
    "INSTANT_CONTACT", "NO_REACTION_TIME", "COMBAT_PACING",
    "COVER_BLOCKING",
})

#: Severities Laser Tag uses to report a check that *passed*. ``LT_ScoreCalculator``
#: emits these next to the failures, in one array, because its own console output
#: prints them under a "Good:" heading -- the severity is the only thing telling
#: the two lists apart.
#:
#: They were not in the severity map, so ``.get(..., "minor")`` turned every one
#: of them into a MINOR finding: "World collision blocked 40% of shots" filed as
#: a defect. Roughly a dozen entries of a 56-finding run were good news wearing a
#: problem's clothes, which is worse than noise -- it makes the count of things
#: wrong with a level untrustworthy in the direction of panic.
PASSING_SEVERITIES = frozenset({"PASS", "OK", "GOOD"})

_SEVERITY = {"FAIL": "major", "ERROR": "major", "WARN": "moderate",
             "WARNING": "moderate", "INFO": "minor"}

#: What an unrecognised severity becomes. Deliberately louder than the old
#: "minor" default: a severity string this map has not heard of is a new one
#: Laser Tag invented, and the failure mode of guessing low is a real defect
#: filed under the heading nobody reads. Guessing high is a false alarm someone
#: closes in a minute. Passes are handled above and never land here.
UNKNOWN_SEVERITY = "moderate"


def report_score(data: Mapping[str, object]):
    """The report's score under whichever key this LaserTag build wrote.

    ``overall_score`` is the 0.7 contract; ``score`` is kept as a fallback so an
    older report still reads rather than silently scoring None.
    """
    for key in ("overall_score", "score"):
        value = data.get(key)
        if isinstance(value, (int, float)):
            return value
    return None


#: The categories that measure the GEOMETRY, with agents moving through it.
#: `cover` is shots stopped by collision, `npc_pathing` is stuck events where
#: agents actually walk, `sightlines` is `LT_MapSampler` exposure sampled
#: against real collision. Sixty points, all of them about the level.
MAP_CATEGORIES = ("cover", "npc_pathing", "sightlines")

#: The categories that measure the ENCOUNTER and the bot, not the level.
#:
#: `traversal` reads `route_completion_rate`, and `LT_BotPlayerController` only
#: advances its route in the ``else`` of "can I see an enemy" -- so with six
#: guards alive on a 260 m plate it is zero whatever the map looks like.
#: `combat_pacing` reads the enemy's first shot, which `player_count`,
#: `enemy_count` and `enemy_sight_range` dominate.
#:
#: MEASURED, not asserted. `lot_demo_001` seed 5118 was evaluated four times on
#: 11 August while materials, lighting, enemy occlusion and the encounter all
#: changed. The total read 45, 45, 10, 45 -- and the one move was the harness
#: failing to run, not the map changing. Forty of the hundred points were
#: reporting on a `.tres` and an `@export`.
ENCOUNTER_CATEGORIES = ("traversal", "combat_pacing")


def category_scores(data: Mapping[str, object]) -> dict:
    """The report's per-category scores, or ``{}`` if it did not write them."""
    block = data.get("categories")
    if not isinstance(block, Mapping):
        return {}
    return {str(k): v for k, v in block.items()
            if isinstance(v, (int, float))}


def _partial(data: Mapping[str, object], names) -> object:
    """Sum ``names`` out of the report's categories, or ``None``.

    ``None`` when any of them is missing, rather than a total computed from
    whatever happened to be present. A number that silently describes four
    fifths of a table is worse than no number: it looks actionable and is not,
    which is the whole complaint this split exists to answer.
    """
    scores = category_scores(data)
    if not scores or any(name not in scores for name in names):
        return None
    return sum(scores[name] for name in names)


def map_score(data: Mapping[str, object]):
    """Of 60. What Laser Tag measured about the LEVEL."""
    return _partial(data, MAP_CATEGORIES)


def encounter_score(data: Mapping[str, object]):
    """Of 40. What Laser Tag measured about the scenario and the bot."""
    return _partial(data, ENCOUNTER_CATEGORIES)


def report_runs(data: Mapping[str, object]):
    value = data.get("runs")
    return value if isinstance(value, int) else None


def was_evaluated(data: Mapping[str, object]) -> bool:
    runs = report_runs(data)
    return runs is not None and runs > 0


def _lt_findings(data: Mapping[str, object]) -> list[Mapping[str, object]]:
    raw = data.get("findings")
    return [f for f in raw if isinstance(f, Mapping)] if isinstance(raw, list) else []


def is_passing(finding: Mapping[str, object]) -> bool:
    """True when this entry records a check that passed, not a defect."""
    return str(finding.get("severity", "")).upper() in PASSING_SEVERITIES


def passing_findings(data: Mapping[str, object]) -> list[Mapping[str, object]]:
    """The checks Laser Tag reports as passed.

    Kept reachable rather than dropped on the floor: they are evidence, and a
    caller that wants to show "what this map got right" should not have to
    re-parse the report to find it. They are simply not *issues*.
    """
    return [f for f in _lt_findings(data) if is_passing(f)]


def _number(value):
    return value if isinstance(value, (int, float)) and not isinstance(
        value, bool) else None


def report_summary(data: Mapping[str, object]) -> Mapping[str, object]:
    raw = data.get("summary")
    return raw if isinstance(raw, Mapping) else {}


def route_completion_rate(data: Mapping[str, object]):
    """Fraction of runs in which the bot completed the mission route.

    ``None`` when the report does not say. Absent is not zero: a report that
    never measured completion must not be read as one that measured failure.
    """
    return _number(report_summary(data).get("route_completion_rate"))


def timeout_count(data: Mapping[str, object]) -> int:
    """Runs that ended on the clock rather than with a dead crew.

    This is the number the route gate turns on. A timed-out run is a run in
    which nothing stopped the crew from walking except the map.
    """
    return int(_number(report_summary(data).get("timeout_count")) or 0)


def avg_time_to_first_enemy_shot(data: Mapping[str, object]):
    """Mean seconds from run start until an ENEMY first fired at the crew.

    ``None`` when the report does not say -- which, as of Laser Tag v0.7.x, is
    always: `LT_MetricsCollector` tracks `time_to_first_enemy_shot` per run but
    `summary()` does not aggregate it. The gate below therefore stands down
    until Laser Tag emits it, which is the correct behaviour and not a stub.

    Do NOT substitute `avg_time_to_first_contact`. That field is set by the
    first shot of a run from EITHER side -- `record_shot` stamps it outside the
    `shooter_is_player` branch -- so it fires on the crew's own opening shot.
    Lot places enemies specifically so the crew acquires first: the crew's bot
    sees 45 m (`LT_BotPlayerController.sight_range`) against the enemy's 35 m
    (`enemy_sight_range`), and `OPENING_RANGE` is built to that difference. On a
    map placed exactly as intended the crew therefore shoots first and
    time-to-first-contact is SHORT BY DESIGN. Reading it as danger inverts the
    contract and blocks the maps that got it right.

    Absent stays non-blocking for the same reason absent is not zero in
    `route_completion_rate`: a report that never measured the opening must not
    be read as one that measured the worst possible opening.
    """
    return _number(report_summary(data).get("avg_time_to_first_enemy_shot"))


def degrading_findings(data: Mapping[str, object]) -> list[Mapping[str, object]]:
    """The findings saying this run had no navigation under it."""
    return [f for f in _lt_findings(data)
            if str(f.get("type", "")).upper() in DEGRADED_TYPES]


def was_degraded(data: Mapping[str, object]) -> bool:
    """True when runs completed but without navigation.

    Deliberately independent of ``was_evaluated``: a report can be both (zero
    runs *and* no navmesh), and the caller decides which statement to lead with.
    """
    return bool(degrading_findings(data))


def failure_summary(data: Mapping[str, object]) -> str:
    """What Laser Tag itself said went wrong, for the human reading one line."""
    parts = [f"{f.get('type', '?')}: {f.get('message', '')}".strip()
             for f in _lt_findings(data) if not is_passing(f)]
    return "; ".join(p for p in parts if p) or "no findings reported"


def normalize_report(
    data: Mapping[str, object], *, raw_source_path: str | None = None,
) -> list[dict]:
    """Findings for one ``lasertag.report.json``."""
    issues: list[dict] = []
    src = {"raw_source_path": raw_source_path} if raw_source_path else {}
    runs = report_runs(data)
    score = report_score(data)
    grade = str(data.get("grade", "")).upper()
    evaluated = was_evaluated(data)
    # Only worth saying once. If nothing ran at all, that is the bigger and
    # earlier statement and the degraded note underneath it is noise.
    degraded = evaluated and was_degraded(data)

    if not evaluated:
        detail = ("the report does not say how many runs completed"
                  if runs is None else f"{runs} runs completed")
        issues.append({
            "code": CODE_NOT_EVALUATED,
            "severity": "blocker", "category": "tool_contract",
            "message": (
                f"Laser Tag never evaluated this map ({detail}); the reported "
                f"grade {grade or '?'} is not a readiness signal because no "
                f"firefight was played. Laser Tag said: {failure_summary(data)}"),
            "blocking": True, **src,
        })

    if degraded:
        why = "; ".join(
            f"{f.get('type', '?')}: {f.get('message', '')}".strip()
            for f in degrading_findings(data)) or "navigation was unavailable"
        issues.append({
            "code": CODE_DEGRADED,
            "severity": "blocker", "category": "tool_contract",
            "message": (
                f"Laser Tag played {runs} runs on this map without navigation "
                f"({why}). With no navmesh the harness moves bots in straight "
                f"lines, so grade {grade or '?'} (score {score}) and every "
                f"traversal, pacing, contact and cover number in this report "
                f"describes that fallback, not this level. Fix navigation and "
                f"re-run before reading the rest."),
            "blocking": True, **src,
        })

    # Whatever LaserTag found, verbatim. NO_RUNS is folded into the message
    # above; repeating it as its own finding would double-count the same fact.
    for finding in _lt_findings(data):
        kind = str(finding.get("type", "UNKNOWN")).upper()
        if kind == "NO_RUNS":
            continue
        # A pass is not a finding. It travels on `passing_findings()` and in the
        # metrics instead of being filed as a MINOR defect against the level.
        if is_passing(finding):
            continue
        severity = _SEVERITY.get(
            str(finding.get("severity", "")).upper(), UNKNOWN_SEVERITY)
        message = f"Laser Tag: {finding.get('message', kind)}"
        if degraded and kind in NAV_DERIVED_TYPES:
            # Keep it -- deleting it would be its own kind of lie, and the
            # number is real evidence about the fallback. Just stop presenting
            # it as a fact about the level, and say why on the finding itself
            # so it still reads correctly out of context.
            severity = "info"
            message = ("not a measurement of this map -- the run had no "
                       "navigation, see " + CODE_DEGRADED + " -- " + message)
        issues.append({
            "code": CODE_MAP_PREFIX + kind,
            "severity": severity,
            "category": "combat_structure",
            "message": message,
            "blocking": False, **src,
        })

    # The route gate. Not a score: a score says how good the map is, and this
    # says whether the mission can be walked at all. It only reads a run that
    # had navigation under it -- without a navmesh 0% completion is a fact about
    # the fallback, and CODE_DEGRADED already blocks on that with the cause
    # named.
    rate = route_completion_rate(data)
    if evaluated and not degraded and rate is not None and rate <= 0:
        timeouts = timeout_count(data)
        wipes = int(_number(report_summary(data).get("team_wipe_count")) or 0)
        contact = avg_time_to_first_enemy_shot(data)
        if timeouts > 0:
            issues.append({
                "code": CODE_ROUTE_NEVER_COMPLETED,
                "severity": "major", "category": "reachability",
                "message": (
                    f"The mission route was never completed in {runs} runs, and "
                    f"{timeouts} of those ran the full clock out with the crew "
                    f"still alive — nothing was stopping them walking except the "
                    f"map. This is EVIDENCE, not the gate: walktest_navqa walks "
                    f"the same spine on the baked navmesh with no combat in "
                    f"it, and says which leg failed. Read that first. This "
                    f"number is confounded by every stuck bot and every "
                    f"wipe, and while it blocked, the walktest for this "
                    f"candidate never ran at all. Formerly the measured form of the destination being "
                    f"unreachable, not a difficulty score: fix the route before "
                    f"reading the combat numbers, which describe a crew that "
                    f"never arrived."),
                "blocking": False, **src,
            })
        # `>= 0.0` is not redundant. Laser Tag's `_avg` returns **-1.0** for a
        # metric no run recorded, and "no enemy ever fired a shot" is the exact
        # opposite of an ambush -- without this guard the sentinel reads as the
        # fastest possible opening and blocks the quietest maps hardest.
        elif contact is not None and 0.0 <= contact < REACTION_SECONDS:
            # The third case, and the one the two above split between them
            # wrongly. Nothing timed out, so the branch above cannot call it
            # geometry; every run ended in a wipe, so the branch below calls it
            # difficulty and stands down. But difficulty is a property of a
            # fight the crew got to participate in. When the ENEMY's first shot
            # lands inside the reaction window the whole opening is built
            # around, the crew was shot before it could act -- without once
            # surviving long enough for the route to be testable. That is not a
            # hard map, it is an opening that never happened, and it is exactly
            # as blocking as a route the crew could not walk.
            # NON-BLOCKING, deliberately, and this was a blocker until the
            # boundary got stated plainly.
            #
            # Laser Tag is not the authority on gameplay. Its bots are not the
            # consuming game's AI, its weapons are not its weapons, its
            # time-to-kill is arbitrary. "The crew was fired on before it could
            # act" is a judgement about a combat model nobody ships, so
            # blocking a build on it enforces LT's model on Lot -- which is
            # exactly what `Scheduler._advise` and the soft-gate rule exist to
            # prevent. Read as a gap, filled in the wrong layer.
            #
            # The guardrail belongs to Lot and now is one: `LOT_ROUTE_EXPOSED`
            # asks the same question of the geometry, offline, before the scene
            # is written. What blocks here should be what our tools ARE
            # authoritative on -- navmesh, collision, reachability -- not what
            # a firefight did afterwards.
            issues.append({
                "code": CODE_NO_SURVIVABLE_OPENING,
                "severity": "major", "category": "spawn",
                "message": (
                    f"The mission route was never completed in {runs} runs and "
                    f"all {wipes} ended in a team wipe, so nothing ran the "
                    f"clock out to prove the route walkable — but the enemy's "
                    f"first shot averaged {contact:.2f} s, inside the "
                    f"{REACTION_SECONDS:g} s reaction window the opening is "
                    f"placed to guarantee (Lot's OPENING_CLEARANCE = "
                    f"CREW_SPEED * REACTION_SECONDS). A crew fired on before it "
                    f"can act has not been beaten by a difficult map; it never "
                    f"got an opening. Fix what sees the crew spawn — standoff, "
                    f"or cover in the ground between — before reading the route "
                    f"as merely untested."),
                "blocking": False, **src,
            })
        else:
            issues.append({
                "code": CODE_ROUTE_UNPROVEN,
                "severity": "moderate", "category": "reachability",
                "message": (
                    f"The mission route was never completed in {runs} runs, but "
                    f"no run lasted long enough to prove it walkable — "
                    f"{wipes} ended in a team wipe. That is difficulty, not "
                    f"geometry, so it does not block; the route itself is "
                    f"untested. Widen the enemy standoff and re-run to find out "
                    f"which one it is."),
                "blocking": False, **src,
            })

    # The readiness signal proper -- only meaningful once a match was actually
    # played, and non-blocking by contract even then. A degraded run is not a
    # low-readiness map; reporting it as one invites someone to go tune combat
    # pacing on a level whose only defect is a missing navmesh.
    if evaluated and not degraded and (
            grade in ("BROKEN", "FAIL")
            or (isinstance(score, (int, float)) and score < READINESS_FLOOR)):
        issues.append({
            "code": CODE_LOW_READINESS,
            "severity": "moderate", "category": "combat_structure",
            "message": (f"Laser Tag readiness grade {grade or '?'} "
                        f"(score {score}) over {runs} runs; evaluation "
                        f"completed — readiness signal only, review at "
                        f"selection."),
            "blocking": False, **src,
        })

    for zone in data.get("overexposed_zones", []) or []:
        issues.append({
            "code": "LT_OVEREXPOSED_ZONE", "severity": "minor",
            "category": "combat_structure",
            "message": f"Overexposed zone at {zone}", "blocking": False, **src,
        })
    for zone in data.get("blind_zones", []) or []:
        issues.append({
            "code": "LT_BLIND_ZONE", "severity": "minor",
            "category": "combat_structure",
            "message": f"Blind zone at {zone}", "blocking": False, **src,
        })
    return issues


def metrics(data: Mapping[str, object]) -> dict:
    degraded = was_evaluated(data) and was_degraded(data)
    return {
        "lasertag_score": report_score(data),
        "lasertag_grade": data.get("grade"),
        "lasertag_runs": report_runs(data),
        "lasertag_evaluated": was_evaluated(data),
        # Candidate selection compares these scores against each other. Two
        # candidates whose bots both walked into walls are not comparable, and
        # the flag is here so a ranking never quietly treats them as if they
        # were.
        "lasertag_degraded": degraded,
        # A candidate whose crew never reached the objective outranking one
        # whose crew did, on the strength of a cover percentage, is the ranking
        # this key exists to stop. None means the report did not measure it.
        "lasertag_route_completion": route_completion_rate(data),
        "lasertag_passes": len(passing_findings(data)),
        # THE SAME REPORT, READ AS THE TWO THINGS IT MEASURES. The total stays
        # exactly as it was -- it is Laser Tag's number and redefining it would
        # be a second opinion about somebody else's report. These are additions.
        #
        # `lasertag_map_score` is the one to look at when a change to the LEVEL
        # is supposed to have done something. Four evaluations of seed 5118 on
        # 11 August returned 45, 45, 10, 45 while the palette, the lighting, the
        # occlusion model and the encounter all changed; the only move was the
        # harness failing to run. Sixty of those points are geometry and forty
        # are a `.tres`, and averaging them hid every change that mattered.
        "lasertag_map_score": map_score(data),
        "lasertag_encounter_score": encounter_score(data),
        "lasertag_categories": category_scores(data) or None,
        "lasertag_note": (
            "no navigation during evaluation; score describes the "
            "direct-movement fallback, not the map"
            if degraded else
            "readiness signal only; not fun/balance/network"),
    }


def summarize(reports: Sequence[Mapping[str, object]]) -> str:
    """One line for the run output: did Laser Tag actually play anything."""
    if not reports:
        return "laser_tag: no reports"
    total = len(reports)
    evaluated = [r for r in reports if was_evaluated(r)]
    degraded = sum(1 for r in evaluated if was_degraded(r))
    if not evaluated:
        return f"laser_tag: {total} report(s), none evaluated (0 runs)"
    # "3/3 evaluated" over three navigation-less runs is the sentence this
    # module exists to stop printing.
    tail = f", {degraded} without navigation" if degraded else ""
    # The split on the run line, because a single number nobody can act on is
    # the thing this is for. Omitted rather than guessed when the reports do not
    # carry categories.
    halves = [(map_score(r), encounter_score(r)) for r in evaluated]
    scored = [(m, e) for m, e in halves if m is not None and e is not None]
    if scored:
        best_map = max(m for m, _e in scored)
        best_enc = max(e for _m, e in scored)
        tail += f", best map {best_map}/60, best encounter {best_enc}/40"
    if len(evaluated) == total:
        return f"laser_tag: {len(evaluated)}/{total} evaluated{tail}"
    return (f"laser_tag: {len(evaluated)}/{total} evaluated{tail}, "
            f"{total - len(evaluated)} never ran")
