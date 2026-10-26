"""Export a level as a snapshot (the factory's roadmap 317; increment 7 of `docs/AUTHORING_LOOP.md`).

THE PACKAGE IS THE ONE THE DESIGNER WALKED. `walk_level` exports the chosen layout of the current revision into the
workspace's own ``exports/`` -- baked, its closure scanned -- and records the walk beside the design. Export takes that
package, refusing when the last walk is not of the current revision (a later change was never walked), runs the
existing `portability-test` on it, and COPIES it into a new folder the designer chooses: an accepted snapshot, outside
the workspace, which no later walk or build can touch. The copy goes into a hidden sibling first and is renamed into
place, so a folder that exists is a whole snapshot; a folder that already holds anything is refused, never merged.

THE CHECKLIST says what the snapshot is, each line read from the file that knows it: the package complete (the export's
closure scan), portable (the portability report, PASS or FAIL), its lights baked or not (``light_bake.json``), the
renderer (the package's ``project.godot``), and the major findings the chosen layout carries. ``GABAGOOL_SNAPSHOT.json``
in the snapshot names the design, its revision and the layout, with the checklist and the package's fingerprint.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import time
from pathlib import Path

from packages.service import design as design_mod
from packages.service import layouts

SNAPSHOT_FILE = "GABAGOOL_SNAPSHOT.json"


def _json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def checklist(export_dir: Path, portability: dict | None, chosen: dict | None) -> list[dict]:
    """``[{"item", "state", "detail"}]``: ``state`` is ok, problem or unknown -- unknown when the file that would say
    is missing, never a pass."""
    rows = []
    closure = _json(export_dir / "export_closure_scan.json")
    if isinstance(closure, dict) and "ok" in closure:
        rows.append({"item": "Package complete", "state": "ok" if closure["ok"] else "problem",
                     "detail": "%s files, %s missing, %s outside the package" % (
                         closure.get("package_file_count"), closure.get("missing_resource_count"),
                         closure.get("external_reference_count"))})
    else:
        rows.append({"item": "Package complete", "state": "unknown", "detail": "no closure scan in the export"})
    if isinstance(portability, dict) and portability.get("status") in ("PASS", "FAIL"):
        rows.append({"item": "Opens without the factory", "state": "ok" if portability["status"] == "PASS" else "problem",
                     "detail": "portability %s, engine check %s" % (portability["status"],
                                                                   portability.get("engine_check", "?"))})
    else:
        rows.append({"item": "Opens without the factory", "state": "unknown", "detail": "no portability report"})
    bake = _json(export_dir / "light_bake.json")
    if isinstance(bake, dict) and "ok" in bake:
        users = None
        for a in bake.get("attempts") or []:
            users = (a.get("result") or {}).get("users", users)
        rows.append({"item": "Lights baked", "state": "ok" if bake["ok"] else "problem",
                     "detail": ("baked, %s lightmapped" % users) if bake["ok"] else "the bake did not run or failed: "
                               "the level ships with live lights"})
    else:
        rows.append({"item": "Lights baked", "state": "unknown", "detail": "no light_bake.json: not baked"})
    try:
        text = (export_dir / "project.godot").read_text(encoding="utf-8")
        m = re.search(r'renderer/rendering_method="([^"]+)"', text)
        renderer = m.group(1) if m else None
    except OSError:
        renderer = None
    rows.append({"item": "Renderer", "state": "ok" if renderer == "gl_compatibility" else "unknown",
                 "detail": renderer or "not stated in project.godot"})
    if chosen is not None:
        majors = int(chosen.get("major_findings") or 0)
        rows.append({"item": "Findings left", "state": "ok" if majors == 0 else "problem",
                     "detail": "%d major on the chosen layout%s" % (majors, (" (%s)" % ", ".join(chosen["out_for"]))
                                                                    if chosen.get("out_for") else "")})
    return rows


def export(path: str, destination: str, events, run_dir: Path, leg=layouts.run_leg) -> dict:
    """Snapshot the design at ``path``'s walked package into the new folder ``destination``. Returns the snapshot's
    folder, the checklist and the snapshot manifest."""
    from packages.core.ids import export_build_dir_name
    folder, doc = layouts._design_folder(path)
    mission = design_mod.mission_id(doc)
    ws = folder / "workspace"
    walked = _json(folder / "builds" / ("revision_%d.walk.json" % doc["revision"]))
    if not isinstance(walked, dict):
        raise layouts.LayoutError("walk_first", "revision %d has not been walked: walk the level, then export what "
                                  "you walked" % doc["revision"])
    export_dir = ws / ".level_factory" / "exports" / export_build_dir_name(mission, "portable-godot")
    if not (export_dir / "mission.tscn").is_file():
        raise layouts.LayoutError("walk_first", "no walked package at %s: walk the level again" % export_dir)
    dest = Path(destination)
    if not str(destination).strip() or not dest.is_absolute():
        raise layouts.LayoutError("bad_destination", "choose a folder for the snapshot")
    if dest.exists() and (not dest.is_dir() or any(dest.iterdir())):
        raise layouts.LayoutError("destination_not_empty", "%s already holds something: choose a new or empty folder; "
                                  "a snapshot is never merged into another" % dest)
    if not dest.parent.is_dir():
        raise layouts.LayoutError("bad_destination", "%s does not exist" % dest.parent)
    events.emit("portability", "running", "Checking the package opens without the factory")
    code = leg(["-C", str(ws), "portability-test", mission, "--mode", "portable-godot"], run_dir / "legs.log",
               cancel_file=run_dir / "cancel")
    portability = _json(export_dir.parent / (export_dir.name + ".portability.json"))
    if code not in (0, 2) or not isinstance(portability, dict):
        raise layouts.LayoutError("leg_failed", "the portability test exited %d and left no report; its output is in "
                                  "%s" % (code, run_dir / "legs.log"))
    rows = layouts.candidate_rows(ws / ".level_factory", mission)
    chosen = next((c for c in rows["candidates"] if c["candidate_id"] == walked.get("candidate_id")), None)
    items = checklist(export_dir, portability, chosen)
    closure = _json(export_dir / "export_closure_scan.json") or {}
    manifest = {"schema": "gabagool.snapshot.v1", "design_id": doc["design_id"], "design_name": doc["name"],
                "design_revision": doc["revision"], "mission_id": mission, "layout": walked.get("candidate_id"),
                "package_fingerprint": closure.get("package_fingerprint"), "checklist": items,
                "exported_at": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime())}
    staging = dest.with_name(".%s.partial" % dest.name)
    if staging.exists():
        shutil.rmtree(staging)
    events.emit("copy", "running", "Copying the package to %s" % dest)
    shutil.copytree(export_dir, staging)
    layouts._write_json(staging / SNAPSHOT_FILE, manifest)
    if dest.exists():
        dest.rmdir()                     # empty, checked above
    os.replace(staging, dest)
    layouts._write_json(folder / "builds" / ("revision_%d.export.json" % doc["revision"]),
                        dict(manifest, snapshot=str(dest)))
    events.emit("copy", "ok", "Exported to %s" % dest, progress=1.0)
    return {"snapshot": str(dest), "checklist": items, "manifest": manifest}
