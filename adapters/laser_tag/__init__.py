"""Laser Tag adapter (TDD 24.3).

Bound to LaserTag v0.7.x: seeded headless firefight evaluation over a Lot
walkable scene. A passing score is a *readiness signal only* (TDD 5.5, 22.5) --
the adapter labels it as such and never marks it fun/balanced/verified.
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterable, Mapping, Sequence

from packages.adapters.sdk import BaseAdapter, PlannedCommand


class LaserTagAdapter(BaseAdapter):
    adapter_id = "laser_tag"
    adapter_version = "0.2.0"
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

    def validate_configuration(
        self, job_spec: Mapping[str, object], context: Mapping[str, object]
    ) -> Sequence[str]:
        problems: list[str] = []
        scene = job_spec.get("evaluation_scene")
        if not scene:
            problems.append("laser_tag job requires an evaluation scene (Lot walkable)")
        elif not Path(str(scene)).exists():
            problems.append(f"evaluation scene missing: {scene}")
        if not context.get("godot_executable"):
            problems.append("godot_executable is not configured (headless run)")
        return problems

    def fingerprint_inputs(
        self, job_spec: Mapping[str, object], context: Mapping[str, object]
    ) -> Mapping[str, object]:
        from packages.core.hashing import hash_file

        fp: dict[str, object] = {
            "seed": job_spec.get("seed"),
            "run_count": job_spec.get("run_count", 8),
            "scenario": job_spec.get("scenario", "default"),
        }
        scene = job_spec.get("evaluation_scene")
        if scene and Path(str(scene)).exists():
            fp["scene_hash"] = hash_file(Path(str(scene)))
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
            proj, map_res = stage_godot_project(
                Path(str(job_spec["staging_dir"])),
                addon_dirs=[Path(str(addon))] + [Path(str(a)) for a in job_spec.get("extra_addon_dirs", [])],
                scene_src=Path(str(scene_src)),
                plugins=["laser_tag_tool"])
            project = str(proj)

        scenario = str(job_spec.get(
            "scenario_res",
            "res://addons/laser_tag_tool/resources/default_laser_tag_scenario.tres"))

        # Real headless runner (SceneTree script). Everything after `--` is a
        # user arg. The harness writes <out>.json + <out>.csv (same basename)
        # and accepts an absolute --output via ProjectSettings.globalize_path.
        args = [
            "--headless", "--path", str(project),
            "-s", "res://addons/laser_tag_tool/runners/run_map_eval.gd",
            "--",
            "--map", map_res,
            "--scenario", scenario,
            "--runs", str(runs),
            "--seed", str(seed),
            "--output", str(out_json),
        ]
        return [
            PlannedCommand(
                executable=godot,
                arguments=tuple(args),
                working_directory=Path(str(project)),
                expected_outputs=("lasertag.report.json", "lasertag.report.csv"),
                resource_class="godot_headless",
                timeout_seconds=900,
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

        issues: list[dict] = []
        for p in output_paths:
            if not p.name.lower().endswith("report.json"):
                continue
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            # The grade/score is a READINESS SIGNAL ONLY (TDD 5.5) — surfaced as
            # a non-blocking finding for the human at candidate selection, never
            # a blocker and never a claim the map is fun/balanced/verified.
            grade = str(data.get("grade", "")).upper()
            score = data.get("score")
            if grade in ("BROKEN", "FAIL") or (isinstance(score, (int, float)) and score < 40):
                issues.append({
                    "code": "LT_LOW_READINESS",
                    "severity": "moderate", "category": "combat_structure",
                    "message": (f"Laser Tag readiness grade {grade or '?'} "
                                f"(score {score}); evaluation completed — "
                                f"readiness signal only, review at selection."),
                    "blocking": False, "raw_source_path": str(p),
                })
            # Overexposed / blind zones surface as informational structure notes.
            for zone in data.get("overexposed_zones", []):
                issues.append({
                    "code": "LT_OVEREXPOSED_ZONE",
                    "severity": "minor",
                    "category": "combat_structure",
                    "message": f"Overexposed zone at {zone}",
                    "blocking": False,
                    "raw_source_path": str(p),
                })
            for zone in data.get("blind_zones", []):
                issues.append({
                    "code": "LT_BLIND_ZONE",
                    "severity": "minor",
                    "category": "combat_structure",
                    "message": f"Blind zone at {zone}",
                    "blocking": False,
                    "raw_source_path": str(p),
                })
        return issues

    def read_metrics(self, report_json: Path) -> dict:
        """Extract the score/grade for candidate comparison (readiness only)."""
        import json

        try:
            data = json.loads(report_json.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return {
            "lasertag_score": data.get("score"),
            "lasertag_grade": data.get("grade"),
            "lasertag_note": "readiness signal only; not fun/balance/network",
        }
