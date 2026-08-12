"""Laser Tag adapter (TDD 24.3).

Bound to LaserTag v0.8.x: seeded headless firefight evaluation over a Lot
walkable scene. A passing score is a *readiness signal only* (TDD 5.5, 22.5) --
the adapter labels it as such and never marks it fun/balanced/verified.
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterable, Mapping, Sequence

from packages.adapters.sdk import BaseAdapter, PlannedCommand


#: Everything `LT_TestScenario` carries, with the stock resource's values.
#: Copied verbatim and in one place so drift between this table and
#: `default_laser_tag_scenario.tres` is a diff rather than an excavation --
#: the same reason `site_spawns` carries `OPENING_RANGE` and names where it
#: came from. Only the keys a brief names are overridden; the rest are written
#: out unchanged so the generated resource is complete and readable.
_STOCK_SCENARIO: dict = {
    "run_count": 25,
    "max_run_time_seconds": 180.0,
    "player_health": 5,
    "enemy_health": 2,
    "player_count": 1,
    "enemy_count": 6,
    "enemies_enabled": True,
    "player_laser_range": 60.0,
    "enemy_laser_range": 35.0,
    "enemy_fire_cooldown": 1.25,
    "enemy_reaction_delay_min": 0.25,
    "enemy_reaction_delay_max": 0.5,
    "enemy_sight_range": 35.0,
    "enemy_preferred_distance": 14.0,
    "first_contact_min_seconds": 3.0,
    "first_contact_max_seconds": 30.0,
    "min_reasonable_survival_seconds": 10.0,
    "use_random_spawn_permutations": True,
    "use_bot_players": True,
    "enable_debug_lasers": True,
    "record_debug_events": True,
    "enable_map_sampling": True,
    "sample_spacing": 2.0,
    "overexposed_threshold": 3,
    "fail_on_missing_player_spawn": True,
    "fail_on_missing_enemy_spawns": True,
    "fail_on_unreachable_spawns": True,
    "require_navigation": False,
}

#: Where the generated resource lands inside the staged project, and the
#: res:// path `--scenario` is given.
_SCENARIO_NAME = "mission_scenario.tres"

#: The script the resource is an instance of. It lives in Laser Tag's addon,
#: which staging has already copied into the project, so the generated
#: resource resolves against the same checkout the runner does.
_SCENARIO_SCRIPT = "res://addons/laser_tag_tool/resources/LT_TestScenario.gd"


def _tres_value(value) -> str:
    """A Godot resource literal. `bool` before `int` -- bool IS an int."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return repr(float(value))
    if isinstance(value, int):
        return str(value)
    return f'"{value}"'


def _write_scenario(project: Path, overrides: Mapping) -> str | None:
    """Write the mission's scenario into the staged project; res:// path back.

    Returns ``None`` rather than raising when the addon is not staged: without
    `LT_TestScenario.gd` at the path the resource names, Godot would load a
    resource with no script and the runner would read defaults off a bare
    `Resource` -- which is a silently different evaluation, and the stock
    resource is a better answer than that.
    """
    script = project / "addons" / "laser_tag_tool" / "resources" / \
        "LT_TestScenario.gd"
    if not script.is_file():
        return None
    values = dict(_STOCK_SCENARIO)
    for key, value in overrides.items():
        if key in values:
            values[key] = value
    lines = [
        '[gd_resource type="Resource" script_class="LT_TestScenario" '
        'load_steps=2 format=3]',
        "",
        f'[ext_resource type="Script" path="{_SCENARIO_SCRIPT}" '
        'id="1_scenario"]',
        "",
        "[resource]",
        'script = ExtResource("1_scenario")',
    ]
    lines += [f"{k} = {_tres_value(v)}" for k, v in values.items()]
    (project / _SCENARIO_NAME).write_text("\n".join(lines) + "\n",
                                          encoding="utf-8")
    return f"res://{_SCENARIO_NAME}"


class LaserTagAdapter(BaseAdapter):
    adapter_id = "laser_tag"
    adapter_version = "0.3.0"
    capabilities = frozenset(
        {
            "manual_firefight_preview",
            "headless_firefight_evaluation",
            "json_report",
            "csv_report",
            "seeded_runs",
        }
    )
    output_contract_version = "lasertag.report.0.7"

    #: Wall-clock budget for ONE evaluation run, in seconds.
    #:
    #: NOT the scenario's `max_run_time_seconds` (180.0). That is SIMULATED
    #: time and the harness runs the simulation faster than real time:
    #: measured 2026-08-09 on a level where every run went its full clock,
    #: nineteen runs cost 900 s of wall time, 47.4 s each. Multiplying the
    #: simulated figure by the run count would reserve 4,500 s for about
    #: 1,200 s of work.
    #:
    #: A run that ENDS early costs a fraction of this -- the same job took
    #: 160.85 s for 25 runs on a level whose runs wiped in 20-31 s. This has to
    #: cover the worst case, which is every run stalemating to its cap.
    run_wall_budget_seconds = 60.0

    #: Load, navmesh bake and position sampling, paid once before the first
    #: run. Roughly 20 s for a 1041-polygon bake over 34,356 source vertices;
    #: tripled, because it is paid once and a slow machine should not lose a
    #: report over it.
    bake_wall_budget_seconds = 120.0

    def validate_configuration(
        self, job_spec: Mapping[str, object], context: Mapping[str, object]
    ) -> Sequence[str]:
        from packages.staging.lt_hooks import check_scene_hooks
        from packages.validation.ground_contact import check_ground_contact
        from packages.validation.spawn_placement import check_spawn_placement

        problems: list[str] = []
        scene = job_spec.get("evaluation_scene")
        if not scene:
            problems.append("laser_tag job requires an evaluation scene (Lot walkable)")
        elif not Path(str(scene)).exists():
            problems.append(f"evaluation scene missing: {scene}")
        else:
            # Pre-flight the map contract (TDD 8). Without the LT_* hooks --
            # or the root positions staging derives them from -- the run
            # completes zero firefights and reports a grade for a match it
            # never played. Better to say so before spending 900 seconds.
            problems.extend(check_scene_hooks(
                Path(str(scene)).read_text(encoding="utf-8", errors="replace")))
            # Meeting the contract is not enough if the hooks stand over a
            # hole: validate_map() rays down from the spawn and refuses the
            # map with NO_WORLD_COLLISION, which also comes back as zero runs.
            problems.extend(check_ground_contact(Path(str(scene))))
            # And a floor is not enough either. validate_map() asks every enemy
            # to path to the crew before it plays a single run and refuses the
            # whole map with UNREACHABLE_SPAWN when one cannot -- so a spawn
            # sealed inside a building costs the same 900 seconds as a spawn
            # over a void, and reads as a level review rather than a placement
            # bug when the report finally lands.
            #
            # Only the refusals. The tactical findings this module also produces
            # -- an unfair opening, a marker hanging over its floor -- describe a
            # map Laser Tag will play and mark down, and a firefight evaluator
            # marking a map down is a design signal rather than a build failure
            # (TDD 5.5). Those come back from `advise_spawn_placement` and are
            # reported next to the score, where they can be acted on without
            # having stopped the level from existing.
            problems.extend(check_spawn_placement(Path(str(scene))))
        if not context.get("godot_executable"):
            problems.append("godot_executable is not configured (headless run)")
        return problems

    def advise_configuration(
        self, job_spec: Mapping[str, object], context: Mapping[str, object]
    ) -> Sequence[Mapping[str, object]]:
        """The tactical half of the pre-flight: never a reason to refuse.

        Laser Tag is a soft gate. It grades a map; it does not certify one, and
        the things it grades down -- an opening engagement that starts before
        the crew has moved, a street two markers can shoot the length of -- are
        design signals about a level that exists and plays. So they come back
        here, beside the score, rather than through `validate_configuration`,
        where the same sentence would stop the level being built at all.

        Read against the real Laser Tag checkout when there is one. The range
        the map has to be built against is a fact about the evaluator's own
        files -- the crew's sight range is an ``@export`` default ten metres
        past the enemy's, and the crew shoots first -- and a pre-flight that
        carried its own copy of that number would be checking its memory.
        """
        from packages.validation import lasertag_contract, tactical

        engagement = lasertag_contract.read_engagement_from(
            context.get("repository"))
        return tactical.advise_scene(
            job_spec.get("evaluation_scene"),
            engagement=engagement,
            # Lot's stated opening range, checked against the evaluator's real
            # one. Neither tool can do this alone: Lot cannot import Level
            # Factory, and Laser Tag has never heard of Lot.
            lot_repository=(context.get("repositories") or {}).get("lot"))

    def fingerprint_inputs(
        self, job_spec: Mapping[str, object], context: Mapping[str, object]
    ) -> Mapping[str, object]:
        from packages.core.hashing import hash_file

        fp: dict[str, object] = {
            "seed": job_spec.get("seed"),
            "run_count": job_spec.get("run_count", 8),
            "scenario": job_spec.get("scenario", "default"),
            # The evaluated scene is the STAGED one, not the source: the hooks
            # are baked in at staging. Without this the source scene hash alone
            # would call a run cached whose map contract had changed underneath.
            "map_contract": "lt_hooks.v1",
            "enemy_count": job_spec.get("enemy_count", 6),
        }
        scene = job_spec.get("evaluation_scene")
        if scene and Path(str(scene)).exists():
            fp["scene_hash"] = hash_file(Path(str(scene)))
        # The evaluator itself is an input, and until now it was not one.
        #
        # Everything above describes the MAP. The rest of the fingerprint comes
        # from `probe()` -- `tool_version` and `repository_commit` -- and when
        # this was written Laser Tag published neither: the factory manifest
        # pinned it "unpinned", noting "no VERSION source yet - reports UNKNOWN
        # by design". So a fingerprint meant to answer "would this job produce
        # the same output?" was blind to every line of the tool producing it.
        # Editing the addon and re-running served the previous grade back,
        # reported the job as succeeded, and left a report on disk that predated
        # the change with nothing on the filesystem to say so.
        #
        # Laser Tag now carries a VERSION file (0.8.0) and `probe()` reads it,
        # so `tool_version` contributes again. The hashing below stays, and is
        # still the load-bearing half: a version string only moves when somebody
        # remembers to move it, and the question this fingerprint asks is
        # whether the CODE changed. A tool edited without a bump is exactly the
        # case a version cannot see and a hash cannot miss.
        #
        # Hashing the addon sources answers that question directly: the
        # question is whether the code changed, and the code is the thing to
        # ask. Sources only -- `.godot/`, `.uid` sidecars and generated reports
        # are editor and run artifacts whose churn would invalidate the cache
        # for no behavioural reason. Keyed by path RELATIVE to the addon root,
        # not by bare filename: this tree has same-named files at different
        # depths, and a flat key would let one silently mask another.
        addon_hashes: dict[str, str] = {}
        addons = [job_spec.get("addon_dir"), *job_spec.get("extra_addon_dirs", [])]
        for addon in addons:
            if not addon:
                continue
            root = Path(str(addon))
            if not root.is_dir():
                continue
            for f in sorted(root.rglob("*")):
                if not f.is_file():
                    continue
                if f.suffix not in (".gd", ".tres", ".tscn", ".cfg", ".json"):
                    continue
                if any(part == ".godot" for part in f.parts):
                    continue
                addon_hashes[f"{root.name}/{f.relative_to(root).as_posix()}"] = \
                    hash_file(f)
        if addon_hashes:
            fp["addon_hashes"] = addon_hashes
        return fp

    def plan_commands(
        self, job_spec: Mapping[str, object], context: Mapping[str, object]
    ) -> Sequence[PlannedCommand]:
        work = Path(str(context["work_dir"]))
        godot = Path(str(context.get("godot_executable") or "godot"))
        seed = job_spec.get("seed", 0)
        runs = job_spec.get("run_count", 25)
        out_json = work / "lasertag.report.json"

        # Stage a throwaway project (Laser Tag addon + the walkable scene at
        # res://) so `--map res://...` resolves. Runs at execution time, after
        # Lot has produced the walkable scene.
        project = job_spec.get("godot_project") or context.get("godot_project") or str(work)
        map_res = str(job_spec.get("map_res", "res://level.tscn"))
        addon = job_spec.get("addon_dir")
        scene_src = job_spec.get("evaluation_scene")
        if addon and scene_src and job_spec.get("staging_dir"):
            from packages.staging.godot_project import stage_godot_project
            from packages.staging.lt_hooks import inject_lt_hooks

            enemies = int(job_spec.get("enemy_count", 6))

            def _bake_hooks(text: str):
                # Laser Tag discovers spawns/objective by node name; Lot's
                # walkable scene carries the positions but not the nodes, so
                # staging is where the contract gets met.
                return inject_lt_hooks(text, enemy_count=enemies)

            proj, map_res = stage_godot_project(
                Path(str(job_spec["staging_dir"])),
                addon_dirs=[Path(str(addon))] + [Path(str(a)) for a in job_spec.get("extra_addon_dirs", [])],
                scene_src=Path(str(scene_src)),
                plugins=["laser_tag_tool"],
                godot_executable=str(godot),
                scene_post_process=_bake_hooks)
            project = str(proj)

        # THE MISSION'S ENCOUNTER, when the brief expressed one.
        #
        # `scenario_res` has been readable here since this adapter was written
        # and nothing ever set it, so every mission Level Factory has evaluated
        # was graded against Laser Tag's stock 1-versus-6 -- a five-building
        # night heist and a single-shell test box against the same resource.
        # Measured on `lot_demo_001`: the crew needs twelve hits, lands six to
        # nine, wipes 25 of 25, and `route_completed` never goes true, which is
        # 25 of the 100 points unreachable by geometry.
        #
        # Written into the STAGED project rather than the checkout: the addon
        # belongs to Laser Tag and Level Factory does not edit other tools'
        # repositories. The stock resource stays the fallback, so a job spec
        # carrying no scenario behaves exactly as it did.
        scenario = str(job_spec.get(
            "scenario_res",
            "res://addons/laser_tag_tool/resources/default_laser_tag_scenario.tres"))
        wanted = job_spec.get("scenario")
        if isinstance(wanted, Mapping) and wanted and project:
            written = _write_scenario(Path(str(project)), wanted)
            if written is not None:
                scenario = written

        # Real headless runner (SceneTree script). Everything after `--` is a
        # user arg. The harness writes <out>.json + <out>.csv (same basename)
        # and accepts an absolute --output via ProjectSettings.globalize_path.
        # --bake-nav matches what Laser Tag's own CI passes. Lot ships the
        # NavigationRegion3D with parameters but no polygons, and without a
        # bake every reachability test in the harness reads as unreachable.
        args = [
            "--headless", "--path", str(project),
            "-s", "res://addons/laser_tag_tool/runners/run_map_eval.gd",
            "--",
            "--bake-nav",
            "--map", map_res,
            "--scenario", scenario,
            "--runs", str(runs),
            "--seed", str(seed),
            "--output", str(out_json),
        ]
        # Scaled by the run count, because that is the thing that varies. The
        # flat 900 s this replaces was sized for the 8-run default and became a
        # ceiling no 25-run mission could pass under: measured 2026-08-09,
        # Godot was killed nineteen runs in, the report was never written, and
        # the job reported JOB_TIMEOUT for a level `walktest_navqa` walks clean.
        #
        # A ceiling that does not follow the work is not a safety net; it is a
        # second thing to keep in sync, and it was already out of sync.
        timeout = int(self.bake_wall_budget_seconds
                      + max(1, int(runs)) * self.run_wall_budget_seconds)
        return [
            PlannedCommand(
                executable=godot,
                arguments=tuple(args),
                working_directory=Path(str(project)),
                expected_outputs=("lasertag.report.json", "lasertag.report.csv"),
                resource_class="godot_headless",
                timeout_seconds=timeout,
            )
        ]

    def collect_outputs(
        self, job_spec: Mapping[str, object], context: Mapping[str, object]
    ) -> Iterable[Path]:
        work = Path(str(context["work_dir"]))
        return sorted(p for p in work.rglob("*")
                      if p.is_file() and p.suffix in (".json", ".csv", ".png"))

    def normalize_validation(
        self, output_paths: Sequence[Path]
    ) -> Sequence[Mapping[str, object]]:
        import json

        from packages.validation.lasertag_report import normalize_report

        # The grade/score is a READINESS SIGNAL ONLY (TDD 5.5) — non-blocking,
        # never a claim the map is fun/balanced/verified. "Laser Tag never ran"
        # is a different statement and blocks; see packages/validation.
        issues: list[dict] = []
        for p in output_paths:
            if not p.name.lower().endswith("report.json"):
                continue
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            issues.extend(normalize_report(data, raw_source_path=str(p)))
        return issues

    def read_metrics(self, report_json: Path) -> dict:
        """Extract the score/grade for candidate comparison (readiness only)."""
        import json

        from packages.validation.lasertag_report import metrics

        try:
            data = json.loads(report_json.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return metrics(data)
