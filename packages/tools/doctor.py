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
from packages.tools.discovery import command_name

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


#: Windows refuses a path longer than this unless `LongPathsEnabled` is 1 (0.173.0, roadmap 227).
WINDOWS_MAX_PATH = 260
#: How far below its workspace a level's files reach, in characters. MEASURED, not derived
#: (`docs/findings/long_paths/` at the factory root): restaurant_row_001 in cold runs 9222 and
#: 9223, Level Factory 0.172.0. The deepest was a Godot editor-state file in the lux_apply
#: staging copy, 217; the pipeline's own deepest output, a texture's provenance file, 193. The
#: names come from the library and from Godot's cache scheme, so a longer prop name or mission
#: id moves it.
LEVEL_DEPTH = 217
_LONG_PATHS_KEY = "SYSTEM\\CurrentControlSet\\Control\\FileSystem"


def long_paths_enabled() -> int | None:
    """`LongPathsEnabled` from the registry: 1, 0, or None where it cannot be read (no winreg
    off Windows, no key, no value)."""
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, _LONG_PATHS_KEY) as key:
            value, _kind = winreg.QueryValueEx(key, "LongPathsEnabled")
    except (ImportError, OSError):
        return None
    return 1 if value == 1 else 0


def long_paths_check(flag: int | None, workspace_root=None) -> tuple[str, str]:
    """The `windows_long_paths` row, (status, detail), from the flag and the workspace's path.

    Until 0.173.0 the row WARNed on every Windows machine without reading the flag, so it could
    not pass where long paths were on, and where they were off it could not say whether a
    workspace sat deep enough to matter. It WARNs, and does not FAIL, past the budget: what
    fails with the flag off has not been measured (this repo's machine has it on).
    """
    budget = WINDOWS_MAX_PATH - 1 - LEVEL_DEPTH
    if flag == 1:
        return PASS, f"LongPathsEnabled is 1: a path may run past {WINDOWS_MAX_PATH} characters"
    said = "LongPathsEnabled is 0" if flag == 0 else "LongPathsEnabled could not be read"
    if not workspace_root:
        return WARN, (f"{said}; a level writes files up to {LEVEL_DEPTH} characters below its "
                      f"workspace, so keep a workspace's path to {budget} characters or fewer")
    reach = len(str(workspace_root)) + 1 + LEVEL_DEPTH
    if reach <= WINDOWS_MAX_PATH:
        return PASS, (f"{said}, and a level's deepest file under {workspace_root} reaches "
                      f"{reach} of {WINDOWS_MAX_PATH} characters")
    return WARN, (f"{said}, and a level's deepest file under {workspace_root} would reach "
                  f"{reach} characters, past Windows' {WINDOWS_MAX_PATH}: unzip the factory into "
                  f"a shorter folder, for a workspace of at most {budget} characters such as "
                  f"C:\\gabagool\\levels, or have an administrator turn long paths on")


def run_doctor(
    tools_local: dict,
    tools_lock: dict,
    *,
    registry: AdapterRegistry | None = None,
    workspace_writable: bool = True,
    workspace_root=None,
) -> DoctorReport:
    registry = registry or AdapterRegistry()
    report = DoctorReport()

    # Python: the interpreter running Level Factory, which needs nothing third-party.
    py = sys.version_info
    report.add(
        "python",
        PASS if py >= (3, 11) else FAIL,
        f"{py.major}.{py.minor}.{py.micro}",
    )

    # THE TOOLS' PYTHON (0.167.0, roadmap 202). Not the interpreter above: the
    # tools run under `python_executable`, and this check never asked it
    # anything, so a machine whose tools could not start read PASS. Asked
    # here for its version and for what `interpreter.TOOL_IMPORTS` lists.
    from packages.tools import interpreter as _interp
    _ans = _interp.ask_tools_python(tools_local)
    _where = _ans["executable"] + ("" if _ans["configured"] else
                                   " (python_executable blank: the interpreter above)")
    _floor = ".".join(str(n) for n in _interp.MIN_VERSION)
    if _ans["error"]:
        report.add("tools_python", FAIL, f"{_where}: {_ans['error']}")
    elif _ans["version"] < _interp.MIN_VERSION:
        report.add("tools_python", FAIL,
                   f"{'.'.join(map(str, _ans['version']))} at {_where}; "
                   f"the tools need >= {_floor}")
    elif _ans["missing"]:
        _mods = ", ".join(m for m, _d, _r in _ans["missing"])
        _dists = " ".join(d for _m, d, _r in _ans["missing"])
        report.add("tools_python", FAIL,
                   f"{'.'.join(map(str, _ans['version']))} at {_where} cannot import "
                   f"{_mods}; make the factory its own with `{command_name()} setup --venv`, "
                   f"or install into this one: \"{_ans['executable']}\" -m pip install {_dists}")
    else:
        report.add("tools_python", PASS,
                   f"{'.'.join(map(str, _ans['version']))} at {_where}")

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

    # WHAT THEMES ARE ACTUALLY INSTALLED (roadmap 72). Not a verdict on any
    # particular brief -- doctor does not know which mission you mean -- but
    # the list a reader needs to spot `delco_1997` against `delco` before a
    # run spends the whole graybox leg finding out. NOT_CONFIGURED rather
    # than a failure when a repo is unset: this is information, not a gate.
    from packages.tools import themes as _themes
    _pc = repos.get("pixelcoat", "")
    _zoo = repos.get("zoo", "")
    if not _pc and not _zoo:
        report.add("themes", NOT_CONFIGURED, "pixelcoat/zoo repositories not set")
    else:
        _avail = _themes.pixelcoat_themes(_pc)
        _styles, _species = _themes.zoo_styles(_zoo)
        _detail = ("pixelcoat: " + (", ".join(_avail) if _avail else "(none)"))
        if _species:
            _full = sorted(s for s, n in _styles.items() if n == _species)
            _part = sorted(s for s, n in _styles.items() if 0 < n < _species)
            _detail += f" | zoo ({_species} species): " + (
                ", ".join(_full) if _full else "(none on all)")
            if _part:
                _detail += " | zoo partial: " + ", ".join(
                    f"{s} ({_styles[s]}/{_species})" for s in _part)
        report.add("themes", PASS if _avail else WARN, _detail)

    # Workspace writability
    report.add("workspace_writable", PASS if workspace_writable else FAIL,
               "writable" if workspace_writable else "cannot write workspace/cache")

    # Windows long paths (0.173.0, roadmap 227): the flag, weighed against how deep the
    # workspace sits; `long_paths_check` says why the row used to be a constant WARN.
    if sys.platform.startswith("win"):
        report.add("windows_long_paths", *long_paths_check(long_paths_enabled(), workspace_root))

    return report
