"""Clean-project portability test and PortabilityReport (TDD 33.8, 12.12).

The strongest portability guarantee: copy the exported mission folder into a
freshly generated clean Godot 4.7 project (nothing but the mission), then open
and instantiate the mission scene headlessly. If it imports without parser or
shader errors, with no missing resources and no required plugin/autoload, the
export is portable by construction.

The resource-closure half is pure Python (always run). The instantiate half
needs Godot; when a godot executable is configured we run it headless, otherwise
the report records that the engine check was skipped.
"""
from __future__ import annotations

import datetime as _dt
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from packages.exporting.closure import scan_closure


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat()


@dataclass
class PortabilityReport:
    mission_id: str
    export_mode: str
    godot_version: str
    schema: str = "level_factory.portability_report.v0.1"
    resource_count: int = 0
    external_reference_count: int = 0
    absolute_path_count: int = 0
    missing_resource_count: int = 0
    parser_error_count: int = 0
    shader_error_count: int = 0
    required_plugin_count: int = 0
    required_autoload_count: int = 0
    scene_instantiated: bool = False
    engine_check: str = "skipped"  # skipped | passed | failed
    status: str = "unknown"        # PASS | FAIL
    issues: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=_now)

    def as_dict(self) -> dict:
        d = self.__dict__.copy()
        d["root"] = None
        d.pop("root", None)
        return d


def run_portability_test(
    *,
    mission_id: str,
    export_dir: Path,
    export_mode: str,
    godot_executable: str | None,
    godot_version: str = "4.7",
    work_root: Path,
) -> PortabilityReport:
    report = PortabilityReport(
        mission_id=mission_id, export_mode=export_mode, godot_version=godot_version)

    # 1. Resource closure (pure Python, always).
    closure = scan_closure(export_dir)
    report.resource_count = closure.resource_count
    report.external_reference_count = closure.external_reference_count
    report.absolute_path_count = closure.absolute_path_count
    report.missing_resource_count = closure.missing_resource_count
    report.required_plugin_count = closure.required_plugin_count
    report.required_autoload_count = closure.required_autoload_count
    report.issues.extend(closure.issues)

    # 2. Clean-project instantiate (needs Godot).
    clean = work_root / f"clean_{mission_id}"
    if clean.exists():
        shutil.rmtree(clean)
    clean.mkdir(parents=True, exist_ok=True)
    # Copy the mission folder under the clean project root (res://).
    shutil.copytree(export_dir, clean, dirs_exist_ok=True)

    if godot_executable:
        entry = "mission.tscn"
        try:
            proc = subprocess.run(
                [godot_executable, "--headless", "--path", str(clean),
                 "--", "--lf-portability-check", "--scene", f"res://{entry}"],
                capture_output=True, text=True, timeout=300,
            )
            out = (proc.stdout or "") + (proc.stderr or "")
            report.parser_error_count = out.count("Parse Error") + out.count("SCRIPT ERROR")
            report.shader_error_count = out.count("Shader Error") + out.count("shader error")
            report.scene_instantiated = proc.returncode == 0 and "instantiated" in out.lower()
            report.engine_check = "passed" if (
                proc.returncode == 0 and report.parser_error_count == 0
                and report.shader_error_count == 0) else "failed"
            if report.engine_check == "failed":
                report.issues.append("clean-project instantiate failed")
        except (OSError, subprocess.SubprocessError) as exc:
            report.engine_check = "failed"
            report.issues.append(f"godot invocation failed: {exc}")
    else:
        report.engine_check = "skipped"
        report.issues.append("godot not configured: engine instantiate skipped")

    # 3. Overall status: closure MUST be clean; engine check must not have failed.
    closure_ok = closure.ok
    engine_ok = report.engine_check in ("passed", "skipped")
    report.status = "PASS" if (closure_ok and engine_ok) else "FAIL"
    return report
