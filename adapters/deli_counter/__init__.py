"""Deli Counter adapter (TDD 24.1) — bound to the REAL Deli Counter 0.74.2 CLI.

Real invocation is TWO steps (verified against the uploaded repo):

    python new_level.py --preset <preset> --name <level> --mode <mode> [--floors N]
                        [--basement|--no-basement] [--vertex-nuance]
                        [--rarity <tier>] --force        # -> specs/<level>.json (headless)

    python build.py specs/<level>.json --out <work>/shell.glb --blender <exe>
        # -> <work>/shell.glb + shell.{gameplay,slots,lights,manifest}.json (BLENDER)

``new_level`` writes its spec into the repo's ``specs/`` dir (path is relative to
the script, not cwd), so each job uses a unique level name to avoid collisions.
``new_level`` has NO seed flag — DC is deterministic per preset; candidate
variation comes from Lot's site assembly downstream, not from DC. The archetype
maps to one of DC's named presets.
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

# Real DC presets (new_level.py --list).
_VALID_PRESETS = {
    "auto_shop", "bank", "casino_tower", "compound", "corner_deli",
    "facade_industrial", "facade_rowhome", "facade_storefront", "gas_station",
    "hospital", "office", "parking_garage", "pawn_shop", "police_station",
    "rowhome", "suburban_safehouse", "warehouse",
}
# LF archetype -> DC preset aliases (extend as briefs introduce new archetypes).
_ARCHETYPE_ALIASES = {
    "urban_bank": "bank", "bank_branch": "bank",
    "corporate_office": "office", "office_tower": "office",
    "industrial_warehouse": "warehouse", "storage_warehouse": "warehouse",
    "convenience_store": "gas_station", "highway_stop": "gas_station",
    "precinct": "police_station", "fortified_compound": "compound",
    "rowhouse": "rowhome", "safehouse": "suburban_safehouse",
}


def _preset_for(archetype: str) -> str:
    a = (archetype or "").strip().lower()
    if a in _VALID_PRESETS:
        return a
    if a in _ARCHETYPE_ALIASES:
        return _ARCHETYPE_ALIASES[a]
    # Strip a leading qualifier (urban_/downtown_/...), then re-check.
    if "_" in a and a.split("_", 1)[1] in _VALID_PRESETS:
        return a.split("_", 1)[1]
    # Keyword fallback.
    for key in _VALID_PRESETS:
        if key in a:
            return key
    return "bank"


class DeliCounterAdapter(BaseAdapter):
    adapter_id = "deli_counter"
    adapter_version = "0.2.0"
    capabilities = frozenset(
        {"generate_spec", "generate_building", "validate_building",
         "combat_audit", "slot_contract", "deterministic_build"}
    )
    output_contract_version = "deli.gameplay.1.21.0"

    def _level_name(self, job_spec) -> str:
        # Unique per job so parallel builds don't clash in the repo's specs/.
        base = str(job_spec.get("level_name") or "lf_shell")
        seed = job_spec.get("seed")
        return f"{base}_{seed}" if seed is not None else base

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
            tool_version=(contract or {}).get("version",
                          (contract or {}).get("tool_version", base.tool_version)),
            repository_commit=base.repository_commit,
            executable_versions=base.executable_versions,
            capabilities=caps,
        )

    def validate_configuration(self, job_spec, context) -> Sequence[str]:
        problems: list[str] = []
        if not context.get("blender_executable"):
            problems.append("blender_executable is not configured (Deli build needs Blender)")
        return problems

    def fingerprint_inputs(self, job_spec, context) -> Mapping[str, object]:
        # DC is deterministic per preset+flags; the seed does NOT affect the
        # building (it drives Lot's site variation), so it is intentionally not
        # part of the build fingerprint — identical configs dedupe in the cache.
        return {
            "preset": _preset_for(str(job_spec.get("archetype", ""))),
            "mode": job_spec.get("mode", "heist"),
            "floors": job_spec.get("floors"),
            "basement": job_spec.get("basement"),
            "vertex_nuance": bool(job_spec.get("vertex_nuance")),
            "rarity": job_spec.get("rarity"),
        }

    def plan_commands(self, job_spec, context) -> Sequence[PlannedCommand]:
        repo = Path(str(context["repository"]))
        work = Path(str(context["work_dir"]))
        py = context.get("python_executable") or "python"
        blender = str(context.get("blender_executable") or "blender")
        preset = _preset_for(str(job_spec.get("archetype", "")))
        mode = str(job_spec.get("mode", "heist"))
        level = self._level_name(job_spec)
        spec_path = repo / "specs" / f"{level}.json"
        out_glb = work / "shell.glb"

        # Step 1: generate the spec (headless).
        new_args = [str(repo / "new_level.py"), "--preset", preset,
                    "--name", level, "--mode", mode, "--force"]
        if job_spec.get("floors") is not None:
            new_args += ["--floors", str(job_spec["floors"])]
        if job_spec.get("basement") is True:
            new_args.append("--basement")
        elif job_spec.get("basement") is False:
            new_args.append("--no-basement")
        if job_spec.get("vertex_nuance"):
            new_args.append("--vertex-nuance")
        if job_spec.get("rarity"):
            new_args += ["--rarity", str(job_spec["rarity"])]

        # Step 2: build the shell into the job's work dir (Blender).
        build_args = [str(repo / "build.py"), str(spec_path),
                      "--out", str(out_glb), "--blender", blender]

        # The output-contract check runs after BOTH commands, against work_dir,
        # so the final build outputs live on the first command's declared set.
        return [
            PlannedCommand(
                executable=Path(str(py)), arguments=tuple(new_args),
                working_directory=repo,
                expected_outputs=("shell.glb", "shell.gameplay.json",
                                  "shell.slots.json", "shell.lights.json"),
                resource_class="python_cpu", timeout_seconds=300,
            ),
            PlannedCommand(
                executable=Path(str(py)), arguments=tuple(build_args),
                working_directory=repo,
                expected_outputs=(),
                resource_class="blender", timeout_seconds=900,
            ),
        ]

    def collect_outputs(self, job_spec, context) -> Iterable[Path]:
        work = Path(str(context["work_dir"]))
        wanted = (".glb", ".json", ".svg", ".png")
        return sorted(p for p in work.rglob("*") if p.is_file() and p.suffix in wanted)

    def normalize_validation(self, output_paths) -> Sequence[Mapping[str, object]]:
        import json
        issues: list[dict] = []
        for p in output_paths:
            name = p.name.lower()
            if not (name.endswith("gameplay.json") or name.endswith("audit.json")):
                continue
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            intel = data.get("intel", []) if isinstance(data, dict) else []
            for raw in intel:
                code = raw.get("code", "UNSPECIFIED")
                sev = raw.get("severity") or ("blocker" if code in _DC_HARD_CODES else "moderate")
                issues.append({
                    "code": code, "severity": sev,
                    "category": raw.get("category", "geometry"),
                    "message": raw.get("message", ""),
                    "blocking": code in _DC_HARD_CODES or sev == "blocker",
                    "raw_source_path": str(p),
                })
        return issues
