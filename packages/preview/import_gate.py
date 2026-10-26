"""A walk preview is playable only once Godot has imported it, and the walk says so or fails.

Godot loads a project's models, textures and their collision through its import cache, and only an editor or an
``--import`` pass fills it: a Godot launched to PLAY a fresh project loads none of what is missing -- in the walker's
words on the first windowed run of the authoring loop, 2026-10-26, "fell through the floor of the first building i
walked in". That walk's headless import was killed at its 600 s timeout with 96 of 758 imports unwritten, every
building's shell among them, and the walk printed a warning and finished ``ok`` (the factory's
`docs/findings/walk_2026-10-26_panel/`, L1).

So the import is judged by what it left, not by the process: `missing_imports` reads every ``.import`` sidecar and
asks whether the cache file it names exists, which is the measurement that found the 96. `import_preview` runs the
pass, with the light bake's bound for importing the same package (`light_bake.IMPORT_TIMEOUT_S`), and answers
``(ok, said)``; a timeout, a non-zero exit or any import left unwritten is not ok.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

_DEST = re.compile(r'^(?:path|path\.[A-Za-z0-9_]+)="(res://\.godot/imported/[^"]+)"', re.M)


def missing_imports(project: Path) -> list[str]:
    """Every ``.import`` sidecar under ``project`` (outside ``.godot``) whose imported file is missing, as paths
    relative to the project. A sidecar that names no imported file (``valid=false``, a skipped type) is not one."""
    project = Path(project)
    out = []
    for sidecar in sorted(project.rglob("*.import")):
        rel = sidecar.relative_to(project)
        if rel.parts and rel.parts[0] == ".godot":
            continue
        dests = _DEST.findall(sidecar.read_text(encoding="utf-8", errors="replace"))
        if dests and not all((project / d[len("res://"):]).exists() for d in dests):
            out.append(rel.as_posix())
    return out


def import_preview(godot_exe: str, project: Path, *, run=subprocess.run, timeout: float | None = None) -> tuple[bool, str]:
    """Run Godot's headless ``--import`` on ``project`` and judge it by what it left. ``(ok, said)``."""
    from packages.exporting.light_bake import IMPORT_TIMEOUT_S
    timeout = IMPORT_TIMEOUT_S if timeout is None else timeout
    try:
        done = run([godot_exe, "--headless", "--path", str(project), "--import"], capture_output=True,
                   timeout=timeout)
    except subprocess.TimeoutExpired:
        why = "the headless import did not finish in %d s" % timeout
    except (OSError, subprocess.SubprocessError) as exc:
        why = "the headless import could not run: %s" % exc
    else:
        why = "" if done.returncode == 0 else "the headless import exited %d" % done.returncode
    missing = missing_imports(project)
    if missing:
        why = "%s%s of the preview's imports were not written (e.g. %s)" % (
            (why + "; ") if why else "", len(missing), ", ".join(missing[:3]))
    if why:
        return False, why
    return True, "imported: resources ready (headless --import pass, every import written)"
