"""Dispatch adapter (TDD 24.8).

Bound to Dispatch v0.3.0, contract ``dispatch.mission.v0.2``. Uses the machine-
readable ``dispatch contract`` probe (D12 -- the pattern LF adapters read
instead of scraping prose) and drives ``dispatch build <spec> --mode
shell-handoff`` (the LF default). Dispatch exit codes: 0 clean, 1 blockers,
2 build failure.

Required adapter checks (24.8): contract is v0.2-compatible, default output has
no production mission controller, preview code is isolated, shell IDs are not
network IDs, runtime ownership is a requirement not an implementation claim.
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterable, Mapping, Sequence

from packages.adapters.sdk import BaseAdapter, PlannedCommand, ToolProbe
from packages.core.hashing import hash_file

REQUIRED_CONTRACT = "dispatch.mission.v0.2"

# Node names Dispatch must never place in a default shell-handoff (contract D).
_FORBIDDEN_NODE_NAMES = {
    "Runtime", "MissionController", "AuthorityController",
    "NetworkController", "ReplicationController",
}
# Strings that would signal a leaked network id in a shell-only handoff.
_FORBIDDEN_ID_STRINGS = ("net_id", "network_authority")


class DispatchAdapter(BaseAdapter):
    adapter_id = "dispatch"
    adapter_version = "0.1.0"
    capabilities = frozenset(
        {
            "assemble_shell",
            "validate_shell",
            "export_godot",
            "shell_handoff",
            "preview_playtest_optional",
            "portable_resource_closure",
            "dependency_manifest",
        }
    )
    output_contract_version = REQUIRED_CONTRACT

    def probe(self, installation: Mapping[str, str]) -> ToolProbe:
        base = super().probe(installation)
        if not base.available:
            return base
        repo = Path(str(installation["repository"]))
        py = installation.get("python_executable") or "python"
        contract = self.run_contract_probe([py, "-m", "dispatch", "contract"], cwd=repo)
        problems: list[str] = []
        if contract is None:
            problems.append("dispatch 'contract' probe unavailable; assuming v0.2")
        else:
            supported = contract.get("mission_contract") or contract.get("contract")
            if supported and REQUIRED_CONTRACT not in str(supported):
                problems.append(
                    f"dispatch contract '{supported}' not compatible with {REQUIRED_CONTRACT}"
                )
        return ToolProbe(
            available=not problems or all("assuming" in p for p in problems),
            tool_version=(contract or {}).get("version",
                          (contract or {}).get("tool_version", base.tool_version)),
            repository_commit=base.repository_commit,
            executable_versions=base.executable_versions,
            capabilities=base.capabilities,
            problems=tuple(problems),
        )

    def validate_configuration(
        self, job_spec: Mapping[str, object], context: Mapping[str, object]
    ) -> Sequence[str]:
        problems: list[str] = []
        spec = job_spec.get("mission_spec_path")
        if not spec:
            problems.append("dispatch job requires a dispatch.mission.json spec")
        elif not Path(str(spec)).exists():
            problems.append(f"dispatch mission spec missing: {spec}")
        mode = job_spec.get("mode", "shell-handoff")
        if mode not in ("shell-handoff", "preview-playtest"):
            problems.append(f"unsupported dispatch mode for LF default: {mode}")
        return problems

    def fingerprint_inputs(
        self, job_spec: Mapping[str, object], context: Mapping[str, object]
    ) -> Mapping[str, object]:
        fp: dict[str, object] = {
            "mode": job_spec.get("mode", "shell-handoff"),
            "include_preview": bool(job_spec.get("include_preview", False)),
        }
        spec = job_spec.get("mission_spec_path")
        if spec and Path(str(spec)).exists():
            fp["mission_spec_hash"] = hash_file(Path(str(spec)))
        for role, path in sorted(job_spec.get("inputs", {}).items()):
            p = Path(str(path))
            if p.exists():
                fp[f"input:{role}"] = hash_file(p)
        return fp

    def plan_commands(
        self, job_spec: Mapping[str, object], context: Mapping[str, object]
    ) -> Sequence[PlannedCommand]:
        repo = Path(str(context["repository"]))
        work = Path(str(context["work_dir"]))
        py = context.get("python_executable") or "python"
        spec = job_spec.get("mission_spec_path", "")
        mode = job_spec.get("mode", "shell-handoff")

        args = ["-m", "dispatch", "build", str(spec), "--mode", mode, "--out", str(work)]
        if job_spec.get("include_preview"):
            args.append("--include-preview")
        # --strict-licenses is the documented Level Factory default (unknown
        # bundled licenses become blockers), unless explicitly disabled.
        if job_spec.get("strict_licenses", True):
            args.append("--strict-licenses")

        return [
            PlannedCommand(
                executable=Path(str(py)),
                arguments=tuple(args),
                working_directory=repo,
                expected_outputs=(
                    "mission.tscn", "mission_manifest.json", "gameplay_anchors.json",
                    "runtime_ownership_requirements.json", "proposed_beat_graph.json",
                    "navigation_hints.json", "resource_manifest.json",
                    "build.lock.json", "HANDOFF.md",
                ),
                resource_class="python_cpu",
                timeout_seconds=600,
            )
        ]

    def collect_outputs(
        self, job_spec: Mapping[str, object], context: Mapping[str, object]
    ) -> Iterable[Path]:
        work = Path(str(context["work_dir"]))
        return sorted(p for p in work.rglob("*") if p.is_file())

    def normalize_validation(
        self, output_paths: Sequence[Path]
    ) -> Sequence[Mapping[str, object]]:
        import json

        issues: list[dict] = []
        tscn = next((p for p in output_paths if p.name == "mission.tscn"), None)
        if tscn is not None:
            text = tscn.read_text(encoding="utf-8", errors="replace")
            for bad in _FORBIDDEN_NODE_NAMES:
                if f'name="{bad}"' in text:
                    issues.append({
                        "code": "DISPATCH_PRODUCTION_CONTROLLER_IN_SHELL",
                        "severity": "blocker",
                        "category": "handoff",
                        "message": f"shell-handoff scene contains forbidden node '{bad}'",
                        "blocking": True,
                        "raw_source_path": str(tscn),
                    })
        for p in output_paths:
            if p.name in ("gameplay_anchors.json", "runtime_ownership_requirements.json"):
                raw = p.read_text(encoding="utf-8", errors="replace")
                for token in _FORBIDDEN_ID_STRINGS:
                    if token in raw:
                        issues.append({
                            "code": "DISPATCH_LEAKED_NETWORK_ID",
                            "severity": "blocker",
                            "category": "handoff",
                            "message": f"'{token}' present in shell handoff ({p.name})",
                            "blocking": True,
                            "raw_source_path": str(p),
                        })
        # Dispatch's own validation report (if present).
        report = next((p for p in output_paths
                       if p.name.endswith("validation.json") or p.name == "report.json"), None)
        if report is not None:
            try:
                data = json.loads(report.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                data = {}
            for raw in data.get("issues", []):
                sev = raw.get("severity", "moderate")
                issues.append({
                    "code": raw.get("code", "DISPATCH_FINDING"),
                    "severity": sev,
                    "category": raw.get("category", "handoff"),
                    "message": raw.get("message", ""),
                    "suggested_fix": raw.get("suggested_fix", ""),
                    "blocking": sev == "blocker",
                    "raw_source_path": str(report),
                })
        return issues
