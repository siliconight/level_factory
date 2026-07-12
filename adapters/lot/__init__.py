"""Lot adapter (TDD 24.2).

Bound to Lot v0.17.x: composes Deli Counter buildings into a site, runs the
site audit + pacing in JSON mode, and produces a walkable Godot scene. In the
light-anchor pipeline, Lot merges DC ``.lights.json`` before Lux bakes; the
adapter passes the DC lights sidecar through as a Lot input.
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterable, Mapping, Sequence

from packages.adapters.sdk import BaseAdapter, PlannedCommand
from packages.core.hashing import hash_file


class LotAdapter(BaseAdapter):
    adapter_id = "lot"
    adapter_version = "0.1.0"
    capabilities = frozenset(
        {
            "assemble_site",
            "preview_without_blender",
            "walkable_scene",
            "site_audit",
            "pacing_estimate",
            "encounter_intel",
        }
    )
    output_contract_version = "lot.site.0.17"

    def validate_configuration(
        self, job_spec: Mapping[str, object], context: Mapping[str, object]
    ) -> Sequence[str]:
        problems: list[str] = []
        buildings = job_spec.get("building_glbs", [])
        if not buildings:
            problems.append("lot job requires at least one building GLB")
        for b in buildings:
            if not Path(str(b)).exists():
                problems.append(f"building artifact missing: {b}")
        return problems

    def fingerprint_inputs(
        self, job_spec: Mapping[str, object], context: Mapping[str, object]
    ) -> Mapping[str, object]:
        building_hashes = {}
        for b in job_spec.get("building_glbs", []):
            p = Path(str(b))
            if p.exists():
                building_hashes[p.name] = hash_file(p)
        fp: dict[str, object] = {
            "site_shape": job_spec.get("site_shape"),
            "route_shape": job_spec.get("route_shape"),
            "target_minutes": job_spec.get("target_minutes"),
            "building_hashes": building_hashes,
        }
        site_spec = job_spec.get("site_spec_path")
        if site_spec and Path(str(site_spec)).exists():
            fp["site_spec_hash"] = hash_file(Path(str(site_spec)))
        return fp

    def plan_commands(
        self, job_spec: Mapping[str, object], context: Mapping[str, object]
    ) -> Sequence[PlannedCommand]:
        repo = Path(str(context["repository"]))
        work = Path(str(context["work_dir"]))
        py = context.get("python_executable") or "python"

        args = [
            "-m", "lot", "assemble",
            "--out", str(work),
            "--audit", "json",
            "--walkable",
            "--nav-qa",
        ]
        for b in job_spec.get("building_glbs", []):
            args += ["--building", str(b)]
        for lights in job_spec.get("lights_jsons", []):
            args += ["--lights", str(lights)]
        site_spec = job_spec.get("site_spec_path")
        if site_spec:
            args += ["--spec", str(site_spec)]
        tm = job_spec.get("target_minutes")
        if tm:
            args += ["--target-minutes", f"{tm[0]}-{tm[1]}"]

        return [
            PlannedCommand(
                executable=Path(str(py)),
                arguments=tuple(args),
                working_directory=repo,
                expected_outputs=(
                    "site.tscn", "site.gameplay.json", "site.nav_hints.json",
                    "site.audit.json", "pacing.json",
                ),
                resource_class="python_cpu",
                timeout_seconds=600,
            )
        ]

    def collect_outputs(
        self, job_spec: Mapping[str, object], context: Mapping[str, object]
    ) -> Iterable[Path]:
        work = Path(str(context["work_dir"]))
        wanted = (".tscn", ".json", ".csv")
        return sorted(p for p in work.rglob("*") if p.is_file() and p.suffix in wanted)

    def normalize_validation(
        self, output_paths: Sequence[Path]
    ) -> Sequence[Mapping[str, object]]:
        import json

        issues: list[dict] = []
        for p in output_paths:
            if not p.name.lower().endswith("audit.json"):
                continue
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            findings = data.get("findings", []) if isinstance(data, dict) else []
            for raw in findings:
                sev = raw.get("severity", "moderate")
                issues.append(
                    {
                        "code": raw.get("code", "LOT_FINDING"),
                        "severity": sev,
                        "category": raw.get("category", "combat_structure"),
                        "message": raw.get("message", ""),
                        "suggested_fix": raw.get("suggested_fix", ""),
                        # Pacing results are estimates, never blocking (24.2).
                        "blocking": sev == "blocker" and raw.get("category") != "pacing",
                        "raw_source_path": str(p),
                    }
                )
        return issues
