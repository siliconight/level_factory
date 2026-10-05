"""The Empties, merged one mesh a side per material (0.143.0, roadmap 182).

An Empty -- a sealed, non-enterable shell the terrace places across the street
as a Lot `blocker` (`packages/pipeline/empties.py`) -- reaches the package as
one kit module instance per Deli Counter slot: about 88 for a three-storey
house, 95 MeshInstance3D and 161 surfaces, in 8 materials. Hiding all 25 of
cold run 9161's Empties saved 816 draws and 1.87 ms at the median view. A
prototype merging each one's modules one mesh a side per material
(`patches/lf_empties/merge_empties_proto.gd`) saved 686 draws and 0.88 ms on
cold run 9162's level, against controls that agreed to 0.03 ms.

WHERE THIS RUNS, and each neighbour is a reason:
  * AFTER THE IMPORT PASS. Only the imported scene carries each slot's final
    transform -- Deli Counter's composer turns a module by `_fit_rotation`
    and sinks a wall 4 mm, neither of which `slots.json` records -- and the
    module materials with the worldskin's projection already on them.
  * AFTER THE OCCLUDER BAKE, which classifies module instances by their GLB's
    name and writes world-space boxes into a scene of their own. Measured on
    the modules, the boxes stay true of the merged geometry.
  * BEFORE THE LIGHT BAKE, whose users are node paths. The merged meshes are
    the users, each unwrapped for its lightmap by the Godot half.

WHAT IT KEEPS: every module's collider, copied out whole; the collision base;
the covers (already one mesh a side, roadmap 180); every material, duplicated
into its merged mesh. The unit is one side of one Empty -- the largest thing
that enters and leaves view as one (CLAUDE.md, the draw-call rules). Never
across Empties.

The Godot half (`assets/godot/merge_empties.gd`) does what only Godot can;
this half finds the scenes, runs it, and believes its report rather than its
exit code. An unrecognised report FAILS.
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

#:   packages/exporting/merge_empties.py -> exporting -> packages -> <lf>
_LF_ROOT = Path(__file__).resolve().parents[2]
MERGE_SCRIPT = _LF_ROOT / "assets" / "godot" / "merge_empties.gd"
REPORT_NAME = "merge_empties.json"
SCHEMA = "lf.merge_empties.v1"

#: The scenes that instance the site's blockers: the composed site, and the
#: presentation pass the light bake's entry scene instances (read off cold
#: run 9162's package). Either may be absent in a given export mode.
SITE_SCENES = ("site.tscn", "presentation/lux.applied.tscn")


class MergeError(RuntimeError):
    """The merge could not be trusted. Never raised for 'no Empties' -- a
    site with none is a legitimate site."""


_EXT = re.compile(r'^\[ext_resource [^\]]*\]$')
_BLOCKER = re.compile(r'^\[node name="blocker_\d+" [^\]]*instance=ExtResource\("([^"]+)"\)[^\]]*\]$')


def empty_scenes(export_dir: Path) -> list[str]:
    """`res://lot/<id>/site.tscn` of every Empty the site instances, sorted:
    the scene each `blocker_<n>` node of `SITE_SCENES` instances. A blocker
    instancing anything but a `lot/<id>/site.tscn` raises -- the terrace's
    blockers are Empties, and anything else would be merged on a guess."""
    export_dir = Path(export_dir)
    found = set()
    for rel in SITE_SCENES:
        p = export_dir / rel
        if not p.is_file():
            continue
        lines = p.read_text(encoding="utf-8").splitlines()
        res = {}
        for ln in lines:
            if _EXT.match(ln) and 'type="PackedScene"' in ln:
                path = re.search(r' path="([^"]+)"', ln)
                rid = re.search(r' id="([^"]+)"', ln)
                if path and rid:
                    res[rid.group(1)] = path.group(1)
        for ln in lines:
            m = _BLOCKER.match(ln)
            if not m:
                continue
            path = res.get(m.group(1), "")
            rel_path = path[len("res://"):] if path.startswith("res://") else path
            if not re.fullmatch(r"lot/[^/]+/site\.tscn", rel_path):
                raise MergeError(f"{rel}: a blocker instances {path!r}, not an Empty's lot scene")
            found.add("res://" + rel_path)
    return sorted(found)


def check(report, asked) -> dict:
    """The report, if it says what a finished merge must; else MergeError."""
    if not isinstance(report, dict) or report.get("schema") != SCHEMA:
        raise MergeError(f"report schema is {report.get('schema') if isinstance(report, dict) else report!r}, "
                         f"not {SCHEMA!r}")
    if not report.get("ok"):
        raise MergeError(f"merge failed: {report.get('error')}")
    rows = report.get("scenes")
    if not isinstance(rows, list):
        raise MergeError("report carries no `scenes` list")
    by = {r.get("scene"): r for r in rows if isinstance(r, dict)}
    for scene in asked:
        r = by.get(scene)
        if r is None:
            raise MergeError(f"{scene}: not in the report")
        if r.get("error") is not None:
            raise MergeError(f"{scene}: {r['error']}")
        for k in ("meshes_in", "surfaces_in", "merged", "unwrapped", "colliders"):
            if not isinstance(r.get(k), int):
                raise MergeError(f"{scene}: row has no integer {k!r}")
        if not 0 < r["merged"] < r["surfaces_in"]:
            raise MergeError(f"{scene}: {r['surfaces_in']} surfaces became {r['merged']} meshes")
        if r["unwrapped"] != r["merged"]:
            raise MergeError(f"{scene}: {r['unwrapped']} of {r['merged']} merged meshes unwrapped "
                             "for the lightmap")
        if r["colliders"] < 1:
            raise MergeError(f"{scene}: no collider kept")
    return report


def merge(export_dir: Path, godot_executable, *, script: Path = MERGE_SCRIPT,
          timeout: int = 900) -> dict:
    """Merge every Empty the site instances; return the checked report.
    `{"schema", "ok", "scenes": []}` without running anything when the site
    has no Empty."""
    from packages.exporting.occluders import OccluderError, ensure_imported
    export_dir = Path(export_dir)
    asked = empty_scenes(export_dir)
    if not asked:
        return {"schema": SCHEMA, "ok": True, "error": None, "scenes": []}
    if not godot_executable:
        raise MergeError("no Godot executable: the Empties cannot be merged")
    if not Path(script).is_file():
        raise MergeError(f"merge script missing: {script}")
    try:
        ensure_imported(export_dir, godot_executable)
    except OccluderError as exc:
        raise MergeError(str(exc)) from exc
    report_path = export_dir / REPORT_NAME
    report_path.unlink(missing_ok=True)
    bundled = export_dir / Path(script).name
    bundled.write_bytes(Path(script).read_bytes())
    try:
        subprocess.run(
            [str(godot_executable), "--headless", "--path", str(export_dir),
             "--script", f"res://{Path(script).name}", "--", str(report_path), *asked],
            capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError) as exc:
        raise MergeError(f"merge did not run: {exc}") from exc
    finally:
        bundled.unlink(missing_ok=True)
    if not report_path.is_file():
        raise MergeError("merge wrote no report")
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise MergeError(f"report unreadable: {exc}") from exc
    return check(report, asked)
