"""Lux adapter (TDD 24.7).

Lux (v0.13.0) is an IN-ENGINE Godot 4.7 addon, not a headless CLI like the other
tools. So this adapter stages the Lux addon into the generated Godot project and
drives a headless Godot "lux apply" entry that:
  * applies the LEVEL/PROP/CHARACTER/GUN roles + the selected preset
  * applies mission-level overrides
  * validates scene budgets and that Lux roots are presentation-only
  * captures configured preview states (calm/alarm etc.)
  * preserves gameplay-critical nodes OUTSIDE presentation roots (24.7 check)

Lux owns runtime light/shadow-colour/fog/palette/banding; it multiplies its lit
result by the Patina/Zoo vertex bakes (form). The apply run never touches
collision or anchors.
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterable, Mapping, Sequence

from packages.adapters.sdk import BaseAdapter, PlannedCommand
from packages.core.hashing import hash_file

# Node names Lux must never own -- these are gameplay authority, not presentation.
_GAMEPLAY_NODES = {"Collision", "GameplayAnchors", "NavRegion", "Interactives"}


class LuxAdapter(BaseAdapter):
    adapter_id = "lux"
    adapter_version = "0.2.0"
    capabilities = frozenset(
        {"apply_preset", "apply_roles", "level_override", "validate_scene",
         "preview_states", "quality_tiers"}
    )
    output_contract_version = "lux.look.0.13"

    def validate_configuration(self, job_spec, context) -> Sequence[str]:
        problems: list[str] = []
        scene = job_spec.get("composed_scene")
        if not scene:
            problems.append("lux apply requires a composed presentation scene")
        elif not Path(str(scene)).exists():
            problems.append(f"composed scene missing: {scene}")
        if not job_spec.get("preset"):
            problems.append("lux apply requires a preset name")
        if not context.get("godot_executable"):
            problems.append("godot_executable is not configured (headless apply)")
        # Godot version must be 4.7 (24.7). The doctor enforces this; note here.
        return problems

    def fingerprint_inputs(self, job_spec, context) -> Mapping[str, object]:
        fp: dict[str, object] = {
            "preset": job_spec.get("preset"),
            "quality_tier": job_spec.get("quality_tier", "standard"),
            "overrides": job_spec.get("overrides", {}),
            "preview_states": sorted(job_spec.get("preview_states", [])),
        }
        for key in ("composed_scene", "lights_json"):
            p = job_spec.get(key)
            if p and Path(str(p)).exists():
                fp[key + "_hash"] = hash_file(Path(str(p)))
        return fp

    def plan_commands(self, job_spec, context) -> Sequence[PlannedCommand]:
        work = Path(str(context["work_dir"]))
        godot = Path(str(context.get("godot_executable") or "godot"))

        # Stage a throwaway project: Lux addon + LF's headless driver at the
        # project root + the composed presentation scene at res://.
        project = job_spec.get("godot_project") or context.get("godot_project") or str(work)
        scene_res = str(job_spec.get("scene_res", "res://level.tscn"))
        addon = job_spec.get("addon_dir")
        driver_src = job_spec.get("driver_src")
        scene_src = job_spec.get("composed_scene")
        if addon and scene_src and job_spec.get("staging_dir"):
            import shutil
            from packages.staging.godot_project import stage_godot_project
            proj, scene_res = stage_godot_project(
                Path(str(job_spec["staging_dir"])),
                addon_dirs=[Path(str(addon))], scene_src=Path(str(scene_src)),
                plugins=["lux"])
            if driver_src and Path(str(driver_src)).exists():
                shutil.copy2(str(driver_src), proj / "run_lux_apply.gd")
            project = str(proj)

        # Lux is in-engine only (no --lux-apply flag). LF ships a headless
        # driver, run_lux_apply.gd, staged at the project root; it uses the real
        # LuxRoot API to apply a preset by name and save the applied scene + JSON.
        args = ["--headless", "--path", str(project),
                "-s", "res://run_lux_apply.gd", "--",
                "--scene", scene_res,
                "--preset", str(job_spec.get("preset", "")),
                "--out", str(work)]

        return [PlannedCommand(
            executable=godot, arguments=tuple(args),
            working_directory=Path(str(project)),
            expected_outputs=("lux.applied.tscn", "lux.quality.json",
                              "lux.validation.json"),
            resource_class="godot_headless", timeout_seconds=900,
        )]

    def collect_outputs(self, job_spec, context) -> Iterable[Path]:
        work = Path(str(context["work_dir"]))
        return sorted(p for p in work.rglob("*")
                      if p.is_file() and p.suffix in (".tscn", ".tres", ".json", ".png"))

    def normalize_validation(self, output_paths) -> Sequence[Mapping[str, object]]:
        import json
        issues: list[dict] = []
        applied = next((p for p in output_paths if p.name == "lux.applied.tscn"), None)
        if applied is not None:
            text = applied.read_text(encoding="utf-8", errors="replace")
            # Gameplay nodes must NOT live under a Lux presentation root (24.7).
            for gp in _GAMEPLAY_NODES:
                if f'parent="Lux' in text and f'name="{gp}"' in text:
                    issues.append({
                        "code": "LUX_GAMEPLAY_NODE_UNDER_PRESENTATION",
                        "severity": "blocker", "category": "presentation",
                        "message": f"gameplay node '{gp}' placed under a Lux root",
                        "blocking": True, "raw_source_path": str(applied),
                    })
        report = next((p for p in output_paths if p.name == "lux.validation.json"), None)
        if report is not None:
            try:
                data = json.loads(report.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                data = {}
            for raw in data.get("issues", []):
                sev = raw.get("severity", "moderate")
                issues.append({
                    "code": raw.get("code", "LUX_FINDING"),
                    "severity": sev, "category": raw.get("category", "presentation"),
                    "message": raw.get("message", ""),
                    "blocking": sev == "blocker", "raw_source_path": str(report),
                })
        return issues
