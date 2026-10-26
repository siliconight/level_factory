"""Walk a level's chosen layout (the factory's roadmap 315; increment 5 of `docs/AUTHORING_LOOP.md`).

The legs `make` runs after its pick, then `walk` -- each its own `level-factory` process, read through structured
sources, as `packages.service.layouts` does for generation:

  * the BRIEF and SHELL-LOCK gates, recorded by ``panel`` and noted as the panel's automatic steps: the art leg
    needs them, and the designer reviewed nothing by pressing Walk. The choice of layout is the designer's
    (`layouts.choose`) and must already be recorded.
  * the ART and GAMEPLAY leg (``run --art --gameplay``), its progress from the job index;
  * ``walk`` without ``--play``: it exports into the workspace's own ``exports/``, builds the preview project in
    the workspace's ``preview/``, imports it, and runs its traversal self-check. The worker opens no window; the
    panel launches the preview it returns.

WHAT IT SHOWS IS NAMED: the result carries the design revision and the layout, and ``builds/revision_<n>.walk.json``
beside the design records them with the preview's path and the self-check's verdict. A preview is never an accepted
export: that is a snapshot copied out of the workspace to a folder the designer chooses (roadmap 317), which a later
walk cannot touch.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from packages.service import design as design_mod
from packages.service import layouts

AUTOMATIC = "recorded by the Factory panel so the level can be built; automatic, not a review"


def _selected(ws: Path, mission: str) -> str | None:
    marker = ws / ".level_factory" / "approvals" / ("%s.selected" % mission)
    try:
        return marker.read_text(encoding="utf-8").strip() or None
    except OSError:
        return None


def walk(path: str, events, run_dir: Path, leg=layouts.run_leg) -> dict:
    """Build the walk preview of the design at ``path``'s chosen layout. Returns the preview's folder, the Godot
    executable the workspace records, the self-check's verdict, the design revision and the layout."""
    folder, doc = layouts._design_folder(path)
    mission = design_mod.mission_id(doc)
    ws = folder / "workspace"
    if not (ws / "factory.project.json").exists():
        raise layouts.LayoutError("no_layouts", "generate the level's layouts first")
    chosen = _selected(ws, mission)
    if not chosen:
        raise layouts.LayoutError("no_choice", "choose a layout first")
    log = run_dir / "legs.log"
    cancel = run_dir / "cancel"
    legs = [("brief", ["-C", str(ws), "approve", mission, "brief_approved", "--by", "panel", "--note", AUTOMATIC]),
            ("lock", ["-C", str(ws), "approve", mission, "functional_shell_locked", "--by", "panel",
                      "--note", AUTOMATIC]),
            ("art", ["-C", str(ws), "run", mission, "--art", "--gameplay"]),
            ("preview", ["-C", str(ws), "walk", mission])]
    said = {"brief": "Recording the brief", "lock": "Locking the chosen layout",
            "art": "Dressing and lighting the level. This takes several minutes.",
            "preview": "Building the walk preview and checking it"}
    done, verdict = [], None
    for name, argv in legs:
        events.emit(name, "running", said[name])
        poll = (lambda: layouts.index_progress(ws, mission, events, "art")) if name == "art" else None
        try:
            code = leg(argv, log, cancel_file=cancel, on_poll=poll)
        except layouts.LayoutError as exc:
            if exc.code == "cancelled":
                raise layouts.LayoutError("cancelled", "Stopped while %s. Finished before stopping: %s. Finished "
                                          "steps are kept." % (name, ", ".join(done) or "nothing"))
            raise
        if name == "preview":
            # `walk` exits 1 when the preview is built but its self-check found something: the preview stands
            if code not in (0, 1):
                raise layouts.LayoutError("leg_failed", "the preview exited %d; its output is in %s" % (code, log))
            verdict = "passed" if code == 0 else "findings"
        elif code not in (0, 1):
            raise layouts.LayoutError("leg_failed", "%s exited %d; its output is in %s" % (name, code, log))
        done.append(name)
    preview = ws / ".level_factory" / "preview" / ("%s_walk" % mission)
    if not (preview / "project.godot").is_file():
        raise layouts.LayoutError("no_preview", "the walk built no preview project at %s (output in %s)"
                                  % (preview, log))
    try:
        godot = json.loads((ws / "tools.local.json").read_text(encoding="utf-8")).get("godot_executable") or ""
    except (OSError, ValueError):
        godot = ""
    out = {"preview": str(preview), "godot": godot, "self_check": verdict, "mission_id": mission,
           "candidate_id": chosen, "design_revision": doc["revision"],
           "label": "%s, revision %d, layout seed %s" % (doc["name"], doc["revision"], chosen.rsplit("_", 1)[-1])}
    layouts._write_json(folder / "builds" / ("revision_%d.walk.json" % doc["revision"]),
                        dict(out, schema="gabagool.walk_record.v1", design_id=doc["design_id"],
                             recorded_at=time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime())))
    events.emit("preview", "ok", "Ready to walk: %s" % out["label"], progress=1.0)
    return out
