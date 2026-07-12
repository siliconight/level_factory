"""Patina adapter (TDD 24.6).

Bound to Patina v0.18.0: PS1-era art pass. Two LF stages:
  * ``patina_apply`` -> base cohesion (palette/wear/decals, trim atlas)
  * ``patina_dressing`` -> dressing_manifest.json (panel/frame/gutter/pilaster
    orders) that Zoo turns into collision-free geometry.
Dressing is spec-space only (Patina refuses --anchor-patina-space), so an art
pass never moves collision (24.6 required check).
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterable, Mapping, Sequence

from packages.adapters.sdk import BaseAdapter, PlannedCommand
from packages.core.hashing import hash_file


class PatinaAdapter(BaseAdapter):
    adapter_id = "patina"
    adapter_version = "0.1.0"
    capabilities = frozenset(
        {"base_cohesion", "dressing_manifest", "trim_atlas", "photo_projection",
         "templates", "overrides", "deterministic_build"}
    )
    output_contract_version = "patina.pass.0.18"

    def validate_configuration(self, job_spec, context) -> Sequence[str]:
        problems: list[str] = []
        mode = job_spec.get("mode", "apply")
        if mode == "dress":
            slots = job_spec.get("slots_path")
            if not slots:
                problems.append("patina dressing requires a slots.json")
            elif not Path(str(slots)).exists():
                problems.append(f"slots.json missing: {slots}")
        elif mode != "apply":
            problems.append(f"unknown patina mode: {mode}")
        if not job_spec.get("theme"):
            problems.append("patina job requires a theme")
        return problems

    def fingerprint_inputs(self, job_spec, context) -> Mapping[str, object]:
        fp: dict[str, object] = {
            "mode": job_spec.get("mode", "apply"),
            "theme": job_spec.get("theme"),
            "panel_size": job_spec.get("panel_size"),
            "panel_gap": job_spec.get("panel_gap"),
        }
        slots = job_spec.get("slots_path")
        if slots and Path(str(slots)).exists():
            fp["slots_hash"] = hash_file(Path(str(slots)))
        for key in ("overrides_path", "family_path"):
            p = job_spec.get(key)
            if p and Path(str(p)).exists():
                fp[key + "_hash"] = hash_file(Path(str(p)))
        return fp

    def plan_commands(self, job_spec, context) -> Sequence[PlannedCommand]:
        repo = Path(str(context["repository"]))
        work = Path(str(context["work_dir"]))
        py = context.get("python_executable") or "python"
        mode = job_spec.get("mode", "apply")

        if mode == "dress":
            args = ["-m", "patina", "dress",
                    "--slots", str(job_spec.get("slots_path", "")),
                    "--out", str(work), "--dressing",
                    "--panel-fields", "--frames", "--gutters", "--pilasters"]
            if job_spec.get("panel_size"):
                args += ["--panel-size", str(job_spec["panel_size"])]
            if job_spec.get("panel_gap"):
                args += ["--panel-gap", str(job_spec["panel_gap"])]
        else:
            args = ["-m", "patina", "apply",
                    "--theme", str(job_spec.get("theme", "")),
                    "--out", str(work)]
            if job_spec.get("templates"):
                args.append("--templates")
            if job_spec.get("overrides_path"):
                args += ["--overrides", str(job_spec["overrides_path"])]
            if job_spec.get("family_path"):
                args += ["--family", str(job_spec["family_path"])]

        return [PlannedCommand(
            executable=Path(str(py)), arguments=tuple(args),
            working_directory=repo,
            expected_outputs=tuple(job_spec.get("expected_outputs", [])),
            resource_class="python_cpu", timeout_seconds=600,
        )]

    def collect_outputs(self, job_spec, context) -> Iterable[Path]:
        work = Path(str(context["work_dir"]))
        return sorted(p for p in work.rglob("*")
                      if p.is_file() and p.suffix in (".png", ".json"))

    def normalize_validation(self, output_paths) -> Sequence[Mapping[str, object]]:
        import json
        issues: list[dict] = []
        man = next((p for p in output_paths if p.name == "dressing_manifest.json"), None)
        if man is not None:
            try:
                data = json.loads(man.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                data = {}
            # Dressing must be spec-space (24.6). If Patina emitted patina-space
            # orders, that is an ambiguous change that must be treated functional.
            if data.get("space") == "patina":
                issues.append({
                    "code": "PATINA_DRESSING_NOT_SPEC_SPACE",
                    "severity": "blocker", "category": "geometry",
                    "message": "dressing manifest is patina-space, not spec-space",
                    "blocking": True, "raw_source_path": str(man),
                })
        return issues
