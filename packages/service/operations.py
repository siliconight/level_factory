"""Service operations: what a client -- the Godot panel, the CLI, the desktop app -- can ask the factory to do.

Each operation is ``fn(arguments: dict, events: EventSink) -> dict``: it validates its own arguments (unknown ones
are refused with `RequestError`), reports progress through ``events``, and returns plain JSON-able data. The worker
(`packages.service.worker`) carries one over protocol v1; another caller can call the function directly. The names
are the no-AI authoring plan's (`docs/reference/authoring/`, section 5C) as each is built, roadmap 310 onward.
"""
from __future__ import annotations

from pathlib import Path

from packages.service.worker import RequestError

#: Plain-language names for the doctor's checks, and the action that fixes each when it is not ready. The doctor's
#: own detail travels beside them as ``technical`` for whoever needs it; the panel leads with these.
CHECK_LABELS = {
    "python": "Python running the factory",
    "tools_python": "Python the tools run under",
    "git": "Git",
    "godot": "Godot",
    "blender": "Blender",
    "windows_long_paths": "Long file paths (Windows)",
    "workspace_writable": "Workspace folder",
    "themes": "Themes (looks)",
}
TOOL_LABELS = {
    "deli_counter": "Deli Counter (buildings)", "lot": "Lot (sites and streets)",
    "laser_tag": "Laser Tag (play testing)", "pixelcoat": "Pixelcoat (materials)", "zoo": "Zoo (props and modules)",
    "patina": "Patina (dressing)", "lux": "Lux (lighting)", "dispatch": "Dispatch (game handoff)",
}
FIXES = {
    "godot": "Choose Godot's executable with Find Godot.",
    "blender": "Choose blender.exe with Find Blender.",
    "tools_python": "Prepare the tools' Python environment (factory setup --venv); it downloads once.",
    "python": "Run the factory with Python 3.11 or newer; Blender's own Python qualifies.",
    "git": "Optional: install Git so builds record each tool's commit.",
    "windows_long_paths": "Keep the project in a short folder such as C:\\gabagool, or turn on Windows long paths.",
    "tool": "The factory package is incomplete: this tool's folder is missing. Unpack the factory again.",
    "themes": "The factory package is incomplete: Pixelcoat's or Zoo's themes are missing. Unpack the factory again.",
    "tool_drift": "This tool is newer than the certified set. Levels build; the combination is not certified yet.",
}
#: What a status means to a designer.
READINESS = {"PASS": "ready", "WARN": "warning", "NOT_CONFIGURED": "missing", "FAIL": "problem"}


def _no_unknown(arguments: dict, allowed: set[str]) -> None:
    unknown = sorted(set(arguments) - allowed)
    if unknown:
        raise RequestError("unknown_arguments", "unknown arguments: %s" % ", ".join(unknown))


def _text(arguments: dict, key: str) -> str:
    value = arguments.get(key, "")
    if not isinstance(value, str):
        raise RequestError("bad_argument", "%s must be a string" % key)
    return value


def _check_row(check: dict) -> dict:
    name, status, detail = check["name"], check["status"], check.get("detail", "")
    if name.startswith("tool:"):
        tool = name.split(":", 1)[1]
        label = TOOL_LABELS.get(tool, tool)
        fix = None
        if status in ("FAIL", "NOT_CONFIGURED"):
            fix = FIXES["tool"]
        elif status == "WARN" and "drift" in detail:
            fix = FIXES["tool_drift"]
    else:
        label = CHECK_LABELS.get(name, name)
        fix = FIXES.get(name) if status != "PASS" else None
    return {"name": name, "label": label, "status": status, "readiness": READINESS.get(status, "unknown"),
            "fix": fix, "technical": detail}


def _installation(root: Path, blender: str, godot: str) -> dict:
    from packages.adapters.registry import AdapterRegistry
    from packages.project_store.workspace import DEFAULT_TOOLS_LOCK
    from packages.tools import discovery
    from packages.tools.doctor import run_doctor

    try:
        found = discovery.discover(root, blender=blender, godot=godot)
    except ValueError as exc:
        raise RequestError("installation_unreadable", str(exc)) from None
    report = run_doctor(found.tools_local, DEFAULT_TOOLS_LOCK, registry=AdapterRegistry(),
                        workspace_root=root / "levels")
    rows = [_check_row(c) for c in report.as_dict()["checks"]]
    paths = {key: {"path": found.tools_local.get(key, ""), "source": found.sources.get(key),
                   "problem": found.gaps.get(key)}
             for key in ("blender_executable", "godot_executable", "python_executable")}
    blocking = [r["name"] for r in rows if r["status"] in ("FAIL", "NOT_CONFIGURED")]
    return {"factory_root": str(root), "ready": not blocking, "blocking": blocking, "worst": report.worst,
            "executables": paths, "checks": rows}


def discover_installation(arguments: dict, events) -> dict:
    """What this machine has and whether the factory can run on it. Writes nothing.

    Arguments, all optional: ``blender`` and ``godot``, executables to try in place of what discovery finds.
    Returns the factory root, each executable with where it was found or why not, every doctor check with a
    plain-language label, a readiness word and the fix for one that is not ready, and ``ready`` -- true when no
    check is a problem or missing. A warning (a tool newer than the certified set, say) is shown, not blocking."""
    _no_unknown(arguments, {"blender", "godot"})
    from packages.tools import discovery
    root = discovery.factory_root()
    if root is None:
        raise RequestError("no_factory", "no %s at or above this Level Factory" % discovery.MANIFEST)
    events.emit("discover", "running", "Looking for Blender, Godot and the factory's tools")
    out = _installation(root, _text(arguments, "blender"), _text(arguments, "godot"))
    events.emit("discover", "ok", "%d checks" % len(out["checks"]))
    return out


def configure_installation(arguments: dict, events) -> dict:
    """Record the executables the user chose, then check again.

    Arguments: ``blender`` and/or ``godot`` -- a path to the executable. Each given path must be a file; it is
    written to the factory's ``factory.local.json`` (`discovery.write_local`, the file `setup` writes and every
    `init` reads), keeping what was recorded for the other. Returns `discover_installation`'s answer afterwards."""
    _no_unknown(arguments, {"blender", "godot"})
    from packages.tools import discovery
    root = discovery.factory_root()
    if root is None:
        raise RequestError("no_factory", "no %s at or above this Level Factory" % discovery.MANIFEST)
    chosen = {}
    for arg, key in (("blender", "blender_executable"), ("godot", "godot_executable")):
        path = _text(arguments, arg)
        if path:
            if not Path(path).is_file():
                raise RequestError("not_a_file", "%s: %s is not a file" % (arg, path))
            chosen[key] = path
    if not chosen:
        raise RequestError("nothing_to_record", "give blender and/or godot")
    try:
        local = discovery.read_local(root)
    except ValueError as exc:
        raise RequestError("installation_unreadable", str(exc)) from None
    keep = {k: v for k, v in local.items() if k in ("blender_executable", "godot_executable", "python_executable")}
    keep.update(chosen)
    events.emit("configure", "running", "Recording %s" % ", ".join(sorted(chosen)))
    discovery.write_local(root, keep)
    out = _installation(root, "", "")
    events.emit("configure", "ok", "recorded")
    return out


OPERATIONS = {
    "discover_installation": discover_installation,
    "configure_installation": configure_installation,
}
