"""Where this machine's tools are, found rather than typed (0.167.0, roadmap 202).

`init` wrote `tools.local.json` with every path blank and asked for them to be filled in by
hand: the first question a stranger with a fresh unpack would have to ask. The cold driver
never filled them either. It copied the previous run's file, and cold run 9194 stopped when
that run's workspace had been retired.

Found, each value with where it came from:

* **The tool repositories:** the directories `factory.manifest.json` names (an entry's `path`,
  else its key), beside Level Factory's own checkout, each holding a `VERSION`. They are the
  checkouts the manifest certifies, so nothing else is searched.
* **Blender, Godot and the tools' Python:** a value given on the command line; then this
  machine's `factory.local.json` beside the manifest, which `setup` writes; then the
  environment; then PATH; then, for Blender only, where its installers and archives put it.
  Godot has no installer, so after PATH it is not searched for.

What is not found stays blank and is named. Nothing is guessed. A blank `python_executable`
is not a gap: it means the interpreter running Level Factory (`interpreter.tools_python`).
"""
from __future__ import annotations

import json
import os
import re
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Mapping

from packages.project_store.workspace import DEFAULT_TOOLS_LOCAL

LOCAL_FILE = "factory.local.json"
LOCAL_SCHEMA = "level_factory.factory_local.v0.1"
MANIFEST = "factory.manifest.json"
EXECUTABLES = ("blender_executable", "godot_executable", "python_executable")

#: Environment variables each executable is read from, in order. `BLENDER` is Deli Counter's
#: (`build.find_blender`); `LOT_GODOT` and `DC_GODOT` are Lot's walk test's (`walktest.find_godot`).
ENV = {
    "blender_executable": ("BLENDER",),
    "godot_executable": ("GODOT", "LOT_GODOT", "DC_GODOT"),
    "python_executable": (),
}
#: The names each executable is looked up by on PATH.
ON_PATH = {
    "blender_executable": ("blender",),
    "godot_executable": ("godot4", "godot"),
    "python_executable": (),
}
#: What to tell somebody when one is not found.
FLAG = {"blender_executable": "--blender", "godot_executable": "--godot",
        "python_executable": "--python"}


#: Set by the factory's launchers to what was typed to run them (`.\factory`, `sh factory.sh`).
COMMAND_ENV = "LEVEL_FACTORY_COMMAND"


def command_name() -> str:
    """What the person running Level Factory types to run it, for the commands a hint names.

    `level-factory` is the console script an installed copy has. Somebody who unpacked the
    factory has no such command: they type the launcher, which says so in `COMMAND_ENV`
    (0.170.0). A hint naming a command they cannot run is a question they will have to ask.
    """
    return str(os.environ.get(COMMAND_ENV) or "").strip() or "level-factory"


def factory_root(start: Path | None = None) -> Path | None:
    """The nearest directory at or above `start` (this file) holding `factory.manifest.json`.

    Searched for, not counted: `parents[3]` is the factory from a checkout beside its siblings
    and something else from a git worktree (`tests/siblings.py`, 0.91.0 and 0.94.0). None when
    there is no manifest above, which is a Level Factory standing outside any factory.
    """
    for parent in Path(start or __file__).resolve().parents:
        if (parent / MANIFEST).is_file():
            return parent
    return None


def _version_key(path: Path) -> tuple:
    return tuple(int(n) for n in re.findall(r"\d+", path.parent.name)) or (0,)


def blender_installs() -> list[Path]:
    """Where Blender's installers and archives put it on this platform, newest first."""
    found: list[Path] = []
    if sys.platform.startswith("win"):
        for var in ("ProgramFiles", "ProgramW6432"):
            base = os.environ.get(var)
            if base:
                found += sorted(Path(base, "Blender Foundation").glob("Blender*/blender.exe"),
                                key=_version_key, reverse=True)
        x86 = os.environ.get("ProgramFiles(x86)")
        if x86:
            found.append(Path(x86, "Steam", "steamapps", "common", "Blender", "blender.exe"))
    elif sys.platform == "darwin":
        found.append(Path("/Applications/Blender.app/Contents/MacOS/Blender"))
    else:
        for base in (Path.home(), Path("/opt")):
            found += sorted(base.glob("blender*/blender"), key=_version_key, reverse=True)
        found.append(Path("/snap/bin/blender"))
    out: list[Path] = []
    for p in found:
        if p not in out and p.is_file():
            out.append(p)
    return out


def read_local(root: Path) -> dict:
    """This machine's `factory.local.json`, or {} when there is none.

    A file in any other shape raises ValueError rather than reading as empty: an unreadable
    record of where the tools are is not the same thing as no record.
    """
    p = Path(root) / LOCAL_FILE
    if not p.is_file():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{p} is not JSON: {exc}") from exc
    if not isinstance(data, dict) or data.get("schema") != LOCAL_SCHEMA:
        raise ValueError(f"{p} is not a {LOCAL_SCHEMA} file")
    return data


def write_local(root: Path, values: Mapping) -> Path:
    """Record the three executables in `factory.local.json`, blanks included."""
    p = Path(root) / LOCAL_FILE
    data = {"schema": LOCAL_SCHEMA, **{k: str(values.get(k) or "") for k in EXECUTABLES}}
    p.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return p


def find_executable(key: str, given: str = "", local: Mapping | None = None,
                    env: Mapping | None = None, which: Callable = shutil.which,
                    installs: list | None = None) -> tuple[str, str]:
    """``(path, where it came from)`` for one of `EXECUTABLES`, or ``("", "")``."""
    if str(given or "").strip():
        return str(given).strip(), "given"
    recorded = str((local or {}).get(key) or "").strip()
    if recorded:
        return recorded, LOCAL_FILE
    env = os.environ if env is None else env
    for var in ENV[key]:
        if str(env.get(var) or "").strip():
            return str(env[var]).strip(), "$" + var
    for name in ON_PATH[key]:
        hit = which(name)
        if hit:
            return str(hit), f"PATH ({name})"
    if key == "blender_executable":
        for p in (blender_installs() if installs is None else installs):
            return str(p), "installed"
    return "", ""


def repositories(root: Path) -> tuple[dict, dict, dict]:
    """``(paths, sources, gaps)`` for the repositories `tools.local.json` names.

    `gaps` maps a key to why it was not found. A manifest in another shape raises ValueError.
    """
    keys = list(DEFAULT_TOOLS_LOCAL["repositories"])
    paths = {k: "" for k in keys}
    sources: dict = {}
    gaps: dict = {}
    manifest = Path(root) / MANIFEST
    if not manifest.is_file():
        return paths, sources, {k: f"no {MANIFEST} at {Path(root)}" for k in keys}
    try:
        tools = json.loads(manifest.read_text(encoding="utf-8")).get("tools")
    except (json.JSONDecodeError, AttributeError) as exc:
        raise ValueError(f"{manifest} is not a manifest: {exc}") from exc
    if not isinstance(tools, dict):
        raise ValueError(f"{manifest} has no `tools` table")
    for key in keys:
        entry = tools.get(key)
        if not isinstance(entry, dict):
            gaps[key] = f"{MANIFEST} names no {key!r}"
            continue
        repo = Path(root) / str(entry.get("path") or key)
        if (repo / "VERSION").is_file():
            paths[key] = repo.as_posix()
            sources[key] = MANIFEST
        else:
            gaps[key] = f"no checkout with a VERSION at {repo.as_posix()}"
    return paths, sources, gaps


@dataclass
class Found:
    """What `discover` found: a `tools.local.json`, where each value came from, and what not."""
    tools_local: dict
    sources: dict = field(default_factory=dict)
    gaps: dict = field(default_factory=dict)

    @property
    def missing(self) -> list[str]:
        return sorted(self.gaps)

    def lines(self) -> list[str]:
        out = []
        for key in EXECUTABLES:
            val = self.tools_local.get(key) or ""
            if val and key in self.gaps:
                out.append(f"{key:<20} {val}  ({self.gaps[key]})")
            elif val:
                out.append(f"{key:<20} {val}  ({self.sources.get(key, '?')})")
            elif key == "python_executable":
                out.append(f"{key:<20} (blank: the interpreter running Level Factory, "
                           f"{sys.executable})")
            else:
                out.append(f"{key:<20} NOT FOUND ({self.gaps.get(key, '')})")
        for key, val in (self.tools_local.get("repositories") or {}).items():
            if val:
                out.append(f"{key:<20} {val}")
            else:
                out.append(f"{key:<20} NOT FOUND ({self.gaps.get(key, '')})")
        return out


def discover(root: Path | None = None, *, blender: str = "", godot: str = "", python: str = "",
             env: Mapping | None = None, which: Callable = shutil.which,
             installs: list | None = None) -> Found:
    """Fill a `tools.local.json` from what this machine has. Raises ValueError on a file in the
    wrong shape (`factory.local.json`, `factory.manifest.json`), never on a missing one."""
    root = Path(root) if root else factory_root()
    local = read_local(root) if root is not None else {}
    given = {"blender_executable": blender, "godot_executable": godot,
             "python_executable": python}
    tools_local: dict = {}
    sources: dict = {}
    gaps: dict = {}
    for key in EXECUTABLES:
        path, where = find_executable(key, given[key], local, env, which, installs)
        tools_local[key] = path
        if where:
            sources[key] = where
            if not Path(path).is_file():
                gaps[key] = f"{where} names {path}, which is not a file"
        elif key != "python_executable":
            looked = [LOCAL_FILE] + ["$" + v for v in ENV[key]] + [
                f"PATH ({n})" for n in ON_PATH[key]]
            if key == "blender_executable":
                looked.append("the usual installs")
            gaps[key] = f"looked in {', '.join(looked)}; pass {FLAG[key]} <path>"
    if root is None:
        # a Level Factory standing outside any factory: no manifest names the repositories
        keys = list(DEFAULT_TOOLS_LOCAL["repositories"])
        here = Path(__file__).resolve().parent
        paths, rsources = {k: "" for k in keys}, {}
        rgaps = {k: f"no {MANIFEST} at or above {here}" for k in keys}
    else:
        paths, rsources, rgaps = repositories(root)
    tools_local["repositories"] = paths
    sources.update(rsources)
    gaps.update(rgaps)
    return Found(tools_local=tools_local, sources=sources, gaps=gaps)
