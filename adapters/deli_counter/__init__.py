"""Deli Counter adapter (TDD 24.1).

Bound to the Deli Counter contract as of v0.74.0 / gameplay SCHEMA 1.21.0:
building generation from a LevelSpec with a deterministic seed, emitting the
GLB, the gameplay sidecar (stair_systems / ladders / platforms / fire_escapes),
the slot contract, a manifest, and the ``.lights.json`` for the Lux pipeline.

The adapter never encodes DC business logic; it constructs a command and reads
DC's machine-readable outputs. If DC exposes a ``contract`` probe, we prefer it
over assumptions (the Dispatch D12 pattern).
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterable, Mapping, Sequence

from packages.adapters.sdk import BaseAdapter, PlannedCommand, ToolProbe
from packages.core.hashing import hash_file

# DC intel codes that must block (HARD errors in the stair/ladder specs).
_DC_HARD_CODES = {
    "LADDER_NO_ROLE", "ROOF_HATCH_BLOCKED", "LOCKED_EGRESS_DOOR",
    "EXTERIOR_TOWER_NO_DOOR", "VEHICLE_CONFLICT",
    "DROP_LADDER_NO_DEPLOYMENT_CLEARANCE", "LADDER_TO_NOWHERE",
    "STAIR_VOLUME_INVADED",
}


class DeliCounterAdapter(BaseAdapter):
    adapter_id = "deli_counter"
    adapter_version = "0.1.0"
    capabilities = frozenset(
        {
            "generate_building",
            "validate_building",
            "combat_audit",
            "floorplan_preview",
            "slot_contract",
            "deterministic_build",
        }
    )
    output_contract_version = "deli.gameplay.1.21.0"

    def probe(self, installation: Mapping[str, str]) -> ToolProbe:
        base = super().probe(installation)
        if not base.available:
            return base
        repo = Path(str(installation["repository"]))
        py = installation.get("python_executable") or "python"
        contract = self.run_contract_probe([py, "-m", "deli_counter", "contract"], cwd=repo)
        caps = base.capabilities
        if contract and isinstance(contract.get("capabilities"), list):
            caps = frozenset(contract["capabilities"])
        return ToolProbe(
            available=True,
            tool_version=(contract or {}).get("tool_version", base.tool_version),
            repository_commit=base.repository_commit,
            executable_versions=base.executable_versions,
            capabilities=caps,
        )

    def validate_configuration(
        self, job_spec: Mapping[str, object], context: Mapping[str, object]
    ) -> Sequence[str]:
        problems: list[str] = []
        if "seed" not in job_spec:
            problems.append("deli_counter job requires a seed")
        spec = job_spec.get("spec_path")
        if spec and not Path(str(spec)).exists():
            problems.append(f"level spec not found: {spec}")
        if not context.get("blender_executable"):
            problems.append("blender_executable is not configured")
        return problems

    def fingerprint_inputs(
        self, job_spec: Mapping[str, object], context: Mapping[str, object]
    ) -> Mapping[str, object]:
        fp: dict[str, object] = {
            "seed": job_spec.get("seed"),
            "archetype": job_spec.get("archetype"),
            "theme": job_spec.get("theme"),
            "mode": job_spec.get("mode", "greybox"),
            "output_formats": sorted(job_spec.get("output_formats", ["glb"])),
        }
        spec = job_spec.get("spec_path")
        if spec and Path(str(spec)).exists():
            fp["spec_hash"] = hash_file(Path(str(spec)))
        return fp

    def plan_commands(
        self, job_spec: Mapping[str, object], context: Mapping[str, object]
    ) -> Sequence[PlannedCommand]:
        repo = Path(str(context["repository"]))
        work = Path(str(context["work_dir"]))
        blender = Path(str(context.get("blender_executable") or "blender"))
        py = context.get("python_executable") or "python"
        seed = job_spec.get("seed")
        theme = job_spec.get("theme", "")
        archetype = job_spec.get("archetype", "")
        spec = job_spec.get("spec_path", "")

        args = [
            "-m", "deli_counter", "build",
            "--seed", str(seed),
            "--out", str(work),
            "--formats", ",".join(job_spec.get("output_formats", ["glb"])),
            "--emit-gameplay", "--emit-slots", "--emit-lights",
            "--combat-audit", "json",
            "--blender", str(blender),
        ]
        if spec:
            args += ["--spec", str(spec)]
        if theme:
            args += ["--theme", str(theme)]
        if archetype:
            args += ["--archetype", str(archetype)]

        return [
            PlannedCommand(
                executable=Path(str(py)),
                arguments=tuple(args),
                working_directory=repo,
                environment={"DELI_OUT": str(work)},
                expected_outputs=(
                    "shell.glb", "shell.gameplay.json", "shell.slots.json",
                    "shell.manifest.json", "shell.lights.json",
                ),
                resource_class="blender",
                timeout_seconds=900,
            )
        ]

    def collect_outputs(
        self, job_spec: Mapping[str, object], context: Mapping[str, object]
    ) -> Iterable[Path]:
        work = Path(str(context["work_dir"]))
        wanted = (".glb", ".json", ".svg", ".png")
        return sorted(p for p in work.rglob("*") if p.is_file() and p.suffix in wanted)

    def normalize_validation(
        self, output_paths: Sequence[Path]
    ) -> Sequence[Mapping[str, object]]:
        import json

        issues: list[dict] = []
        for p in output_paths:
            name = p.name.lower()
            if not (name.endswith("validation.json") or name.endswith("gameplay.json")
                    or name.endswith("audit.json")):
                continue
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            intel = data.get("intel", []) if isinstance(data, dict) else []
            for raw in intel:
                code = raw.get("code", "UNSPECIFIED")
                sev = raw.get("severity")
                if not sev:
                    sev = "blocker" if code in _DC_HARD_CODES else "moderate"
                issues.append(
                    {
                        "code": code,
                        "severity": sev,
                        "category": raw.get("category", "geometry"),
                        "message": raw.get("message", ""),
                        "suggested_fix": raw.get("suggested_fix", ""),
                        "blocking": code in _DC_HARD_CODES or sev == "blocker",
                        "raw_source_path": str(p),
                    }
                )
        return issues
