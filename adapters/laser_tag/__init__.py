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
    adapter_version = "0.1.0"
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
        repo = Path(str(context["repository"]))
        work = Path(str(context["work_dir"]))
        godot = Path(str(context.get("godot_executable") or "godot"))
        scene = job_spec.get("evaluation_scene", "")
        seed = job_spec.get("seed", 0)
        runs = job_spec.get("run_count", 8)

        args = [
            "--headless", "--path", str(context["godot_project"]),
            "--", "--lasertag-eval",
            "--scene", str(scene),
            "--seed", str(seed),
            "--runs", str(runs),
            "--json", str(work / "lasertag.report.json"),
            "--csv", str(work / "lasertag.report.csv"),
        ]
        return [
            PlannedCommand(
                executable=godot,
                arguments=tuple(args),
                working_directory=repo,
                expected_outputs=("lasertag.report.json", "lasertag.report.csv"),
                resource_class="godot_headless",
                timeout_seconds=600,
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
