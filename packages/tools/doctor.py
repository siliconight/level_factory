"""Tool registry resolution and the doctor command (TDD 18).

The doctor answers "can this machine run the pipeline, and if not, exactly what
is missing". A missing required tool blocks only the stages that need it
(TDD 18.3), so results are per-tool.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

from packages.adapters.registry import AdapterRegistry

PASS = "PASS"
WARN = "WARN"
FAIL = "FAIL"
NOT_CONFIGURED = "NOT_CONFIGURED"

# adapter_id -> repository key in tools.local.json.
ADAPTER_REPO_KEYS = {
    "deli_counter": "deli_counter",
    "lot": "lot",
    "laser_tag": "laser_tag",
    "pixelcoat": "pixelcoat",
    "zoo": "zoo",
    "patina": "patina",
    "lux": "lux",
    "dispatch": "dispatch",
}


@dataclass
class CheckResult:
    name: str
    status: str
    detail: str = ""

    def as_dict(self) -> dict:
        return {"name": self.name, "status": self.status, "detail": self.detail}


@dataclass
class DoctorReport:
    checks: list[CheckResult] = field(default_factory=list)

    def add(self, name: str, status: str, detail: str = "") -> None:
        self.checks.append(CheckResult(name, status, detail))

    @property
    def worst(self) -> str:
        order = {PASS: 0, NOT_CONFIGURED: 1, WARN: 2, FAIL: 3}
        return max((c.status for c in self.checks), key=lambda s: order.get(s, 0), default=PASS)

    def as_dict(self) -> dict:
        return {"worst": self.worst, "checks": [c.as_dict() for c in self.checks]}


def _exe_version(path: str, args: list[str]) -> str | None:
    if not path:
        return None
    try:
        out = subprocess.run([path, *args], capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.SubprocessError):
        return None
    text = (out.stdout or out.stderr or "").strip()
    return text.splitlines()[0] if text else None


def run_doctor(
    tools_local: dict,
    tools_lock: dict,
    *,
    registry: AdapterRegistry | None = None,
    workspace_writable: bool = True,
) -> DoctorReport:
    registry = registry or AdapterRegistry()
    report = DoctorReport()

    # Python
    py = sys.version_info
    report.add(
        "python",
        PASS if py >= (3, 11) else FAIL,
        f"{py.major}.{py.minor}.{py.micro}",
    )

    # Git
    report.add("git", PASS if shutil.which("git") else WARN,
               "found" if shutil.which("git") else "git not on PATH (commits unknown)")

    # Godot / Blender executables
    godot = tools_local.get("godot_executable", "")
    if not godot:
        report.add("godot", NOT_CONFIGURED, "godot_executable not set")
    else:
        v = _exe_version(godot, ["--version"])
        expected = tools_lock.get("godot", "4.7")
        ok = bool(v) and (expected.split(".")[0:2] == v.split(".")[0:2] or expected in (v or ""))
        report.add("godot", PASS if v else FAIL,
                   (v or "not runnable") + (f" (expected {expected})" if v and not ok else ""))

    blender = tools_local.get("blender_executable", "")
    if not blender:
        report.add("blender", NOT_CONFIGURED, "blender_executable not set")
    else:
        v = _exe_version(blender, ["--version"])
        report.add("blender", PASS if v else FAIL, v or "not runnable")

    # Per-tool repositories + adapter probe
    repos = tools_local.get("repositories", {})
    for adapter_id, repo_key in ADAPTER_REPO_KEYS.items():
        repo = repos.get(repo_key, "")
        if not repo:
            report.add(f"tool:{adapter_id}", NOT_CONFIGURED, "repository path not set")
            continue
        if not Path(repo).exists():
            report.add(f"tool:{adapter_id}", FAIL, f"repository missing: {repo}")
            continue
        adapter = registry.get(adapter_id)
        probe = adapter.probe({"repository": repo, **tools_local})
        if not probe.available:
            report.add(f"tool:{adapter_id}", FAIL, "; ".join(probe.problems) or "unavailable")
        else:
            from packages.tools import contracts
            detail = f"v{probe.tool_version or '?'}"
            if probe.repository_commit:
                detail += f" @ {probe.repository_commit[:8]}"
            certified, src = contracts.certified_version(
                adapter_id, tools_lock.get("tools", {}))
            status = contracts.compare(certified, probe.tool_version)
            if status == contracts.OK:
                report.add(f"tool:{adapter_id}", PASS, detail)
            elif status == contracts.INCOMPATIBLE:
                report.add(f"tool:{adapter_id}", FAIL,
                           f"{detail} — {contracts.INCOMPATIBLE} vs certified {certified} ({src})")
            elif status == contracts.DRIFT:
                report.add(f"tool:{adapter_id}", WARN,
                           f"{detail} — drift vs certified {certified} ({src}); re-certify")
            else:  # UNKNOWN — no comparable version
                report.add(f"tool:{adapter_id}", PASS, f"{detail} (version unpinned)")

    # Workspace writability
    report.add("workspace_writable", PASS if workspace_writable else FAIL,
               "writable" if workspace_writable else "cannot write workspace/cache")

    # Windows long-path awareness (informational off-Windows).
    if sys.platform.startswith("win"):  # pragma: no cover - platform specific
        report.add("windows_long_paths", WARN,
                   "verify LongPathsEnabled registry flag for deep asset paths")

    return report
