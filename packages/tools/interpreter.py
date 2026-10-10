"""The interpreter the tools' Python runs under, named in one place (0.167.0, roadmap 202).

Every Python tool -- Deli Counter's driver and gates, Lot, Pixelcoat, Patina, Dispatch, the
presentation composer and the walk test -- runs as a subprocess of `tools.local.json`'s
`python_executable`. Until 0.167.0 a blank one meant two different interpreters: jobs ran under
`python3`, the scheduler's fallback, and the Deli Counter and Dispatch probes under `python`,
their own. On a fresh Windows machine both names are the Microsoft Store's app-execution
alias, which runs no Python. `doctor` could not notice, because its "python" check read a third
interpreter: the one running Level Factory.

A blank one now means the interpreter running Level Factory, everywhere. On the machine this
was written on, `python3`, `python` and that interpreter are one 3.14.4 (measured 2026-10-10),
so no cold run there changes.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Mapping

#: The oldest Python the tools' interpreter may be. Level Factory's own `pyproject.toml` asks
#: the same; Pixelcoat and Patina ask >= 3.10.
MIN_VERSION = (3, 11)

#: What the tools' interpreter must import: (module, distribution, who imports it at the top of
#: a module on the level-making path). Measured 2026-10-10 by a search of every tracked `.py` in
#: the ten tool repos (`docs/findings/stranger_install/` in the factory). Blender 5.1.1's own
#: Python carries numpy and lacks the other three. `PIL.Image` rather than `PIL`, because the
#: package imports without its compiled half and the module does not.
TOOL_IMPORTS = (
    ("numpy", "numpy", "Pixelcoat, Patina"),
    ("PIL.Image", "pillow", "Pixelcoat, Patina"),
    ("pygltflib", "pygltflib", "Patina; Deli Counter's gates and composer"),
    ("jsonschema", "jsonschema", "Patina"),
)

# Run BY the interpreter being asked: its version, and each module it could not import with
# why. One line of JSON, read from the last line of its output.
_ASK = (
    "import importlib, json, sys\n"
    "missing = []\n"
    "for name in sys.argv[1:]:\n"
    "    try:\n"
    "        importlib.import_module(name)\n"
    "    except Exception as exc:\n"
    "        missing.append([name, type(exc).__name__ + ': ' + str(exc)[:200]])\n"
    "print(json.dumps({'version': list(sys.version_info[:3]), 'missing': missing}))\n"
)


#: What `setup --venv` installs (0.168.0): the versions every suite and cold run on the
#: machine this was written on used, 2026-10-10. A different Pillow is a different PNG encoder
#: and resampler, so an unpinned one would make texture packs nobody here has looked at.
PINNED = {"pillow": "12.3.0", "pygltflib": "1.16.5", "jsonschema": "4.26.0"}
VENV = ".venv"


def venv_python(venv: Path) -> Path | None:
    """The interpreter inside a virtual environment, on either platform's layout."""
    for rel in (("Scripts", "python.exe"), ("bin", "python")):
        p = Path(venv, *rel)
        if p.is_file():
            return p
    return None


def make_venv(root: Path, base: str, *, run=subprocess.run, timeout: int = 1800) -> tuple[str, str]:
    """Make `<root>/.venv` from `base` and install `PINNED` into it. ``(its python, "")``, or
    ``("", what failed)``.

    `--system-site-packages`, so the environment keeps what `base` already carries -- numpy,
    for Blender's own Python -- and installs only what it lacks. It writes nothing outside
    `<root>/.venv`, so it needs no rights over wherever Blender is installed. pip fetches from
    its index, so this is the one step that needs the network; its output goes to the terminal
    as it runs, because a download that only reports at the end reads as a hang.
    """
    venv = Path(root) / VENV
    made = run([base, "-m", "venv", "--system-site-packages", str(venv)],
               capture_output=True, text=True, timeout=timeout, stdin=subprocess.DEVNULL)
    if made.returncode != 0:
        said = (made.stderr or made.stdout or "").strip().splitlines() or ["no output"]
        return "", f"{base} -m venv exited {made.returncode}: {said[-1][:200]}"
    py = venv_python(venv)
    if py is None:
        return "", f"{venv} has no interpreter after `-m venv`"
    pins = [f"{dist}=={ver}" for dist, ver in PINNED.items()]
    got = run([str(py), "-m", "pip", "install", "--disable-pip-version-check", *pins],
              timeout=timeout, stdin=subprocess.DEVNULL)
    if got.returncode != 0:
        return "", f"pip install {' '.join(pins)} exited {got.returncode} (its output is above)"
    return str(py), ""


def tools_python(installation: Mapping | None) -> str:
    """The interpreter the tools run under: `python_executable`, or this one when it is blank."""
    configured = str((installation or {}).get("python_executable") or "").strip()
    return configured or sys.executable


def ask_tools_python(installation: Mapping | None, *, timeout: int = 60) -> dict:
    """Ask the tools' interpreter its version and which of `TOOL_IMPORTS` it cannot import.

    Returns ``{"executable", "configured", "version", "missing", "error"}``. `version` is a
    tuple; `missing` is a list of ``(module, distribution, reason)``. When the interpreter did
    not run, or answered in any other shape, `error` says so and `version` is None -- an
    answer this cannot read is never a pass.
    """
    exe = tools_python(installation)
    configured = bool(str((installation or {}).get("python_executable") or "").strip())
    out = {"executable": exe, "configured": configured, "version": None,
           "missing": [], "error": ""}
    try:
        run = subprocess.run([exe, "-c", _ASK, *(m for m, _d, _w in TOOL_IMPORTS)],
                             capture_output=True, text=True, timeout=timeout,
                             stdin=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError) as exc:
        out["error"] = f"did not run: {exc}"
        return out
    lines = [ln for ln in (run.stdout or "").splitlines() if ln.strip()]
    try:
        answer = json.loads(lines[-1]) if lines else None
    except json.JSONDecodeError:
        answer = None
    if (not isinstance(answer, dict) or not isinstance(answer.get("version"), list)
            or not isinstance(answer.get("missing"), list)):
        said = (run.stderr or run.stdout or "").strip().splitlines() or ["no output"]
        out["error"] = f"did not answer (exit {run.returncode}): {said[-1][:200]}"
        return out
    out["version"] = tuple(int(x) for x in answer["version"])
    dist = {m: d for m, d, _w in TOOL_IMPORTS}
    out["missing"] = [(str(m), dist.get(str(m), "?"), str(why)) for m, why in answer["missing"]]
    return out
