"""The enterable buildings' static modules, merged per room cell and material (0.223.0, the factory's roadmap 266).

An enterable building reaches the package as one kit module instance per Deli Counter slot -- deli_a03 on cold run
9347's package: 1,047 surfaces in its static modules alone, every wall panel, partition run, prop and floor its own
submission. The Empties have merged one mesh a side per material since 0.143.0 (`merge_empties`); the covers merge
per side per material (Zoo 1.68.0); the buildings were the rest of the draw pool -- 2,576 of the 3,798 surfaces of
cold run 9339's level (the factory's `docs/findings/multimesh_audit/`).

WHAT IT MERGES, AND IN WHAT UNIT: the Godot half's header (`assets/godot/merge_buildings.gd`). In short: a static
slot -- not interactive, not an opening, nothing animated or shader-driven, not the collision base, not the covers --
joins one mesh per (unit, material); a unit is a wall side of a storey, a partition run, the parapet's side, the
roof, or a 6 m cell of the room the piece stands in. Colliders are copied out whole, as `merge_empties` copies them.
A LIT FACE stays its own instance's mesh where it stood (0.224.0), because Lux's failing fixture dims the lit face
nearest its lamp; the module round it merges. 0.223.0 left every module with a lit face whole. A SLOT HOLDING WHAT THE
MERGE CANNOT CARRY stays whole (0.227.0): the merge keeps meshes and static bodies and removed the rest with its slot --
Deli Counter's `Ladders`, the Area3D climb volumes, and its `Markers`, the grouped spawns and objectives a game finds by
group, until the factory's install test 11's walk found no ladder to climb. The report names each slot it kept so
(`kept_carrying`), and a report without that list is an older merge's and is not believed.

PRICED BEFORE IT SHIPPED (the factory's `docs/findings/interior_merge_266/`): on cold run 9347's package, both arms
re-baked by this repo's own bake and the control priced twice, the cells cut the draws by 79.6 a heading (11 %, 420 at
the most), took the level's worst heading from 10.05 to 9.14 ms p95, kept the meshes over the 8-light cap at the
control's nine, and cost a 2048 x 1024 lightmap where the control's was 1024 x 1024.

THE ROOMS come from Lot's own record of the site (`site.site.gameplay.json`, which the export already reads for the
responders): each room names its building's node (`b<n>`) and carries its plan bounds in the SITE's frame and its
floor height in the building's. `write_rooms` takes each room's bounds through the inverse of that node's transform
in `site.tscn` (rows, `ground_contact._transform`) into the building's own frame -- Deli Counter's plan, where a local
Godot point (x, y, z) is (x, -z) -- and writes them beside the building's scene as `rooms.json`, which the merge
reads and which goes again after it.

WHERE THIS RUNS: after the Empties' merge, for the same reasons -- after the occluder bake, whose boxes were measured
on the modules and are world-space; before the light bake, whose users are node paths. Its report is believed only
when it says what a finished merge must (`check`), and an unrecognised one FAILS.
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

from packages.exporting.merge_empties import SITE_SCENES, MergeError

#:   packages/exporting/merge_buildings.py -> exporting -> packages -> <lf>
_LF_ROOT = Path(__file__).resolve().parents[2]
MERGE_SCRIPT = _LF_ROOT / "assets" / "godot" / "merge_buildings.gd"
REPORT_NAME = "merge_buildings.json"
ROOMS_NAME = "rooms.json"
SCHEMA = "lf.merge_buildings.v1"

_EXT = re.compile(r'^\[ext_resource [^\]]*\]$')
_BUILDING = re.compile(r'^\[node name="(b\d+)" parent="\." instance=ExtResource\("([^"]+)"\)[^\]]*\]$')


def placed_buildings(export_dir: Path) -> dict:
    """``{res://lot/<id>/site.tscn: [(node name, 3x4 row matrix)]}`` for every enterable building the site places:
    each `b<n>` node of `SITE_SCENES` instancing a `lot/<id>/site.tscn`, with its transform (the identity when it
    writes none). The terrace's Empties are `blocker_<n>` and are `merge_empties`'. A `b<n>` instancing anything else
    raises -- a building merged on a guess is the failure this refuses."""
    from packages.validation.ground_contact import _transform
    export_dir = Path(export_dir)
    out: dict = {}
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
        for i, ln in enumerate(lines):
            m = _BUILDING.match(ln)
            if not m:
                continue
            path = res.get(m.group(2), "")
            rel_path = path[len("res://"):] if path.startswith("res://") else path
            if not re.fullmatch(r"lot/[^/]+/site\.tscn", rel_path):
                raise MergeError(f"{rel}: building {m.group(1)} instances {path!r}, not a lot scene")
            body = []
            for nxt in lines[i + 1:]:
                if nxt.startswith("["):
                    break
                body.append(nxt)
            entry = (m.group(1), _transform("\n".join(body)))
            scene = "res://" + rel_path
            if entry[0] not in [n for n, _m in out.get(scene, [])]:
                out.setdefault(scene, []).append(entry)
    return dict(sorted(out.items()))


def _invert(m):
    """The inverse of a 3x4 rigid row matrix (a rotation and a translation, as Lot places a building)."""
    r = [[m[c][r] for c in range(3)] for r in range(3)]          # the transpose of the rotation
    t = [m[0][3], m[1][3], m[2][3]]
    return [r[i] + [-(r[i][0] * t[0] + r[i][1] * t[1] + r[i][2] * t[2])] for i in range(3)]


def _apply(m, p):
    return [m[i][0] * p[0] + m[i][1] * p[1] + m[i][2] * p[2] + m[i][3] for i in range(3)]


def local_rooms(rooms: list, node: str, matrix) -> list:
    """The rooms Lot records for building `node`, in that building's own plan frame: ``[{id, floor, bounds}]``.

    Lot writes a room's `bounds` in the site's plan (x, y) -- Godot's (x, -z) -- and its `center` in the building's
    own frame, the third number its floor height. Each bound's four corners go through the inverse of the node's
    transform; their box is the local bounds (a building turns in quarter turns). The id loses Lot's `b<n>/`."""
    inv = _invert(matrix)
    out = []
    for r in rooms:
        if str(r.get("building", "")) != node:
            continue
        b = r.get("bounds") or []
        c = r.get("center") or []
        if len(b) != 4 or len(c) != 3:
            raise MergeError(f"{node}: room {r.get('id')!r} has no four bounds and three-number centre")
        xs, ys = [], []
        for (x, y) in ((b[0], b[1]), (b[2], b[1]), (b[2], b[3]), (b[0], b[3])):
            g = _apply(inv, [float(x), 0.0, -float(y)])
            xs.append(g[0])
            ys.append(-g[2])
        rid = str(r.get("id", ""))
        out.append({"id": rid.split("/", 1)[1] if rid.startswith(node + "/") else rid,
                    "floor": float(c[2]),
                    "bounds": [round(min(xs), 4), round(min(ys), 4), round(max(xs), 4), round(max(ys), 4)]})
    return out


def write_rooms(export_dir: Path, placed: dict, lot_gameplay: Path) -> dict:
    """`rooms.json` beside each placed building's scene, from Lot's record: ``{scene: rooms written}``. A scene two
    nodes instance gets its first node's rooms -- the same in its own frame. A building with no room in Lot's record
    raises: the merge would cut it into bare cells and say nothing."""
    export_dir = Path(export_dir)
    try:
        doc = json.loads(Path(lot_gameplay).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise MergeError(f"Lot's site record unreadable: {exc}") from exc
    rooms = doc.get("rooms")
    if not isinstance(rooms, list):
        raise MergeError(f"{lot_gameplay}: no `rooms` list")
    out = {}
    for scene, nodes in placed.items():
        node, matrix = nodes[0]
        mine = local_rooms(rooms, node, matrix)
        if not mine:
            raise MergeError(f"{scene}: Lot records no room for {node}")
        dst = export_dir / scene[len("res://"):]
        (dst.parent / ROOMS_NAME).write_text(json.dumps({"rooms": mine}, indent=1), encoding="utf-8")
        out[scene] = len(mine)
    return out


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
        for k in ("slots_merged", "meshes_in", "surfaces_in", "merged", "unwrapped", "colliders",
                  "lit_surfaces", "lit_meshes"):
            if not isinstance(r.get(k), int):
                raise MergeError(f"{scene}: row has no integer {k!r}")
        # what the merge cannot carry keeps its slot whole and is named (0.227.0); an older merge removed it
        if not isinstance(r.get("kept_carrying"), list):
            raise MergeError(f"{scene}: row names no `kept_carrying` list")
        if not 0 < r["merged"] < r["surfaces_in"]:
            raise MergeError(f"{scene}: {r['surfaces_in']} surfaces became {r['merged']} meshes")
        # every mesh it made is unwrapped: the merged groups and the lit instances both (0.224.0)
        if r["unwrapped"] != r["merged"] + r["lit_meshes"]:
            raise MergeError(f"{scene}: {r['unwrapped']} of {r['merged'] + r['lit_meshes']} meshes unwrapped "
                             "for the lightmap")
        if (r["lit_meshes"] > 0) != (r["lit_surfaces"] > 0) or r["lit_meshes"] > r["lit_surfaces"]:
            raise MergeError(f"{scene}: {r['lit_surfaces']} lit surfaces in {r['lit_meshes']} meshes")
        if r["colliders"] < 1:
            raise MergeError(f"{scene}: no collider kept")
        if not isinstance(r.get("units"), dict) or not r["units"]:
            raise MergeError(f"{scene}: row says nothing of its units")
    return report


def merge(export_dir: Path, godot_executable, lot_gameplay, *, script: Path = MERGE_SCRIPT,
          timeout: int = 1800) -> dict:
    """Merge every enterable building the site places; return the checked report. `{"schema", "ok", "scenes": []}`
    without running anything when the site places none."""
    from packages.exporting.occluders import OccluderError, ensure_imported
    export_dir = Path(export_dir)
    placed = placed_buildings(export_dir)
    asked = list(placed)
    if not asked:
        return {"schema": SCHEMA, "ok": True, "error": None, "scenes": []}
    if not godot_executable:
        raise MergeError("no Godot executable: the buildings cannot be merged")
    if not lot_gameplay or not Path(lot_gameplay).is_file():
        raise MergeError("no Lot site record to read the buildings' rooms from")
    if not Path(script).is_file():
        raise MergeError(f"merge script missing: {script}")
    try:
        ensure_imported(export_dir, godot_executable)
    except OccluderError as exc:
        raise MergeError(str(exc)) from exc
    write_rooms(export_dir, placed, lot_gameplay)
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
        for scene in asked:
            (export_dir / scene[len("res://"):]).parent.joinpath(ROOMS_NAME).unlink(missing_ok=True)
    if not report_path.is_file():
        raise MergeError("merge wrote no report")
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise MergeError(f"report unreadable: {exc}") from exc
    return check(report, asked)
