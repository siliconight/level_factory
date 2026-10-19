"""Can a body walk off an edge the level did not declare? The gate over UNDECLARED DROPS (factory roadmap 173).

WHAT THIS EXISTS FOR. Every other gate in this exporter measures traversal correctness or resource closure --
can a body get from A to B, does every `res://` reference resolve. None asked whether a body can FALL somewhere
nobody meant. On cold run 9072's package the instrument found, from physics, a stairwell the walker had found
first, and its first run on a current package found the office's stair pit: a landing open 6.67 m over the well,
a flight's inner side open over the flight beside it, 12 edges no gate had ever seen (the factory's
`docs/findings/drop_edges_173/`; Deli Counter 0.225.0 fixed them at the source). THE RULE this gate enforces is
the item's: every drop a body can reach is either GUARDED, or DECLARED, or a defect.

THE MEASUREMENT is `assets/godot/walkable_edge.gd`, which owns it (this module owns the verdict): over a grid of
cells it finds every surface a body stands on with the body's own capsule, floods what the body can REACH from
the package's `player_start` across steps, falls and the package's off-mesh links (its ladders), and reports
every edge where a reached cell's neighbour is further down than a body steps with nothing above step-over
height between them and nothing in the body's way -- an UNGUARDED drop. Nine repairs on cold run 9317's package
went into that instrument before its residue was the level's and not its own; they are written beside it.

THE DECLARED SET is read off the PACKAGE, so the gate's list and the AI's list are one list:
  * a drop link: `navigation_hints.json` `links[]` with `required_capability` "drop" (Deli Counter 0.226.0 files
    one on every `floor_hole` / `hatch` vertical link, Lot 0.125.0 moves it into site space, Dispatch 0.5.3
    carries it) -- an edge at its storey within HOLE_MARGIN of its `hole` rect is declared;
  * a ladder's shaft: a link with `required_capability` "climb" -- an edge within LADDER_R of the ladder's
    column, at any height from its foot to its head, is the hatch or hole the ladder passes through: its head's,
    and every floor's between (`_in_shaft`);
  * a flight's own open side: an edge whose cell stands on a stair collider (`GreyboxBase/stair<n>...`), which
    the agent contract calls ordinary architecture and Deli Counter guards at its own thresholds;
  * a thing's top: an edge whose cell stands on anything that is not a floor, a roof, a tread or the ground (a
    desk, a car, a parapet, the perimeter fence) is not a floor a body walks, and is reported, not refused;
  * outdoors: an edge with nothing overhead (the plate's rim, a roof, a dock) is somebody's decision -- reported,
    not refused. In the instrument's own comment, a body that walks off an edge INSIDE a building has found a
    defect.

WHAT IT REFUSES: an unguarded drop, indoors, from a reached cell on a floor-like surface, that nothing above
declares. Measured through this module, in the engine, on cold run 9318's package (Deli Counter 0.225.0, which
predates the drop links; the factory's `docs/findings/drop_edges_173/gate_probe_9318.out.txt` and
`gate_reclass_9318.out.txt`): 54 unguarded edges, 46 indoors -- 10 a flight's own side, 3 a rail's top, 13 a
ladder's shaft, and 20 at deli_a01's floor hole, which that package does not declare, so the gate refuses it.
The same report with the link Deli Counter 0.226.0 records and Lot 0.125.0 places for that hole passes: its
rect lies within 0.16 m of all 20 rows. A package that trips it is fixed by DECLARING the drop in its spec (a
`floor_hole` link) or GUARDING it (a rail), never by editing the package -- the fix lands in Deli Counter, which
is where roadmap 173's first two findings landed.

THE RECORDS: `drop_edges.json` is the instrument's report (every row, with what each stands on and drops to, and
the owner table), `drop_edges_scan.json` is this module's verdict. Both land ABOVE the closure verdict, inside
the package the verdict describes and the manifest that lists it, like `greybox_skin_scan.json`.

THE COST: the instrument walks the rectangle the package's nav nodes and links span plus `EXTENT_MARGIN_M`
(`extent_from_hints`), not the backdrop, with the rectangle's corner snapped to the cell lattice by the
instrument. On cold run 9318's package: 1,521 x 1,521 cells and 150 s over everything; bounded by its `Site`
node's subtree STILL 1,521 a side (the site's ground carries the backdrop's); bounded by its nav nodes 341 x 126
cells and 7 s, with the same rows as the unbounded run. An unsnapped corner put every cell a centimetre off the
unbounded lattice and the flood lost a stair's one-cell turn landing -- the fragility the nav gate's grid sweep
exists for, measured and recorded beside the instrument. In an export the import cache is warm; on a bare
package `measure` imports first, and that is most of its 104 s on the same package.
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

from packages.exporting.greybox_skin import _engine_tail

_LF_ROOT = Path(__file__).resolve().parents[2]
EDGE_SCRIPT = _LF_ROOT / "assets" / "godot" / "walkable_edge.gd"
#: The instrument's report, as it writes it.
REPORT_NAME = "drop_edges.json"
#: This module's verdict, beside it.
SCAN_NAME = "drop_edges_scan.json"
SCHEMA = "lf.walkable_edge.v1"
SCAN_SCHEMA = "drop_edges_scan/1"
#: The grid's margin beyond the rectangle the package's nav nodes and links span, metres: a body wanders past
#: the last nav node to a wall, a fence, a kerb. Measured on cold run 9318's package: the site node's own subtree
#: reached as far as the backdrop (its ground carries the backdrop's), so a node name bounded nothing; the nav
#: nodes do, and every package has them (Dispatch's `navigation_hints.json`).
EXTENT_MARGIN_M = 12.0
#: The instrument's grid, metres. Half a body's width: an edge is found within one cell of where it is.
CELL_M = 0.5
#: An edge this close to a storey's level is at that storey (a ramp head, a plate, a slab's own thickness).
LEVEL_TOL = 0.35
#: An edge this far outside a declared hole's rect is the hole's own rim (one cell plus a tread).
HOLE_MARGIN = 0.6
#: A ladder's hole is 1.5 m square: its rim plus a cell.
LADDER_R = 1.6


class DropCensusError(RuntimeError):
    """The census could not be taken. Not the same as a package with no undeclared drop."""


class UndeclaredDropError(RuntimeError):
    """A body can walk off an edge, indoors, that nothing guards and nothing declares."""


class NoSeedError(DropCensusError):
    """The package says nowhere a body starts, so the flood has no seed and the census is NOT TAKEN -- which
    the export says out loud and records, rather than refusing a package it could not measure. A
    single-building shell exported on its own (the exporter's own tests) has no `player_start`; a site
    mission always has one (Lot's getaway van)."""


def _floor_like(tail: str) -> bool:
    """A surface a body WALKS on, by what owns its collider in this toolchain's packages: Deli Counter's floor
    and basement slabs (`GreyboxBase/slab_col_<n>`), a roof (`roof_footprint/Roof`, an Empty's
    `KitCollision/Roof`), a stair's ramps, landings and discharges (`GreyboxBase/stair<n>...`, never a
    `stair_guard`), a ladder's plane, and Lot's own surfaces, which are the site node's direct children
    (`Site/Ground`, `Site/road_1`, `Site/sidewalk_1L_2`, `Site/frontage_0L_1`, `Site/kerbcut_0L_1`, `Site/path_1`,
    `Site/yard_1`) -- except `Site/perim_*`, the fence. Everything else is a thing's top."""
    if tail.startswith("Site/perim_"):
        return False
    return (tail.startswith("Site/") or re.match(r"GreyboxBase/slab_col_-?\d+$", tail) is not None
            or tail.endswith("/Roof") or re.match(r"GreyboxBase/stair\d", tail) is not None
            or re.match(r"GreyboxBase/ladder\d+_plane$", tail) is not None)


def _tail(owners: list, i) -> str:
    return "none" if i is None or int(i) < 0 else "/".join(str(owners[int(i)]).split("/")[-2:])


def seed_from_anchors(export_dir) -> list:
    """Where the body starts: the package's `player_start` anchor, `transform.pos`, Godot metres."""
    path = Path(export_dir) / "gameplay_anchors.json"
    if not path.is_file():
        raise DropCensusError("no gameplay_anchors.json in the package: nothing says where a body starts")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise DropCensusError(f"gameplay_anchors.json unreadable: {exc}") from exc
    starts = [a for a in (data.get("anchors") or []) if a.get("anchor_type") == "player_start"]
    if not starts:
        raise NoSeedError("gameplay_anchors.json carries no player_start anchor: nothing says where a body starts")
    pos = ((starts[0].get("transform") or {}).get("pos"))
    if not (isinstance(pos, list) and len(pos) == 3):
        raise DropCensusError("the player_start anchor carries no transform.pos: %r" % (starts[0],))
    return [float(v) for v in pos]


def extent_from_hints(export_dir, margin: float = EXTENT_MARGIN_M):
    """The rectangle the package's nav nodes and off-mesh links span, plus `margin`, as "x0,z0,x1,z1" in Godot
    metres (x and z: the ground plane) -- or "" when the package carries no nav hints, which leaves the
    instrument to walk everything it draws and says so in its report."""
    path = Path(export_dir) / "navigation_hints.json"
    if not path.is_file():
        return ""
    hints = json.loads(path.read_text(encoding="utf-8"))
    pts = []
    for n in hints.get("nodes") or []:
        p = n.get("pos")
        if isinstance(p, list) and len(p) == 3:
            pts.append((float(p[0]), float(p[2])))
    for link in hints.get("links") or []:
        for key in ("start_position", "end_position"):
            p = link.get(key)
            if isinstance(p, list) and len(p) == 3:
                pts.append((float(p[0]), float(p[2])))
    if not pts:
        return ""
    xs = [p[0] for p in pts]
    zs = [p[1] for p in pts]
    return "%.2f,%.2f,%.2f,%.2f" % (min(xs) - margin, min(zs) - margin, max(xs) + margin, max(zs) + margin)


def not_taken(reason: str) -> dict:
    """The scan a package carries when the census could not be seeded: it says so, and certifies nothing."""
    return {"schema": SCAN_SCHEMA, "not_taken": reason, "counts": None, "undeclared": [], "outdoors": []}


def measure(export_dir, godot_executable, *, script: Path = EDGE_SCRIPT, cell: float = CELL_M,
            timeout: int = 900) -> dict:
    """Run the instrument in the engine and return its report.

    The report is the evidence, not the exit code: one that does not parse, or whose schema and keys are not
    the instrument's, RAISES rather than reading as a package with no edges (the factory's CLAUDE.md, a checker
    written against a guessed schema). Leaves the package as it found it: the exporter keeps the bake's import
    cache until the censuses have run, so in an export this imports nothing; on a bare package it imports and
    then removes what it made, because the closure verdict scans every file.
    """
    from packages.exporting import occluders

    export_dir = Path(export_dir)
    report_path = export_dir / REPORT_NAME
    if not godot_executable:
        raise DropCensusError("no Godot executable: the drop-edge census cannot be taken")
    if not Path(script).is_file():
        raise DropCensusError(f"instrument missing: {script}")
    seed = seed_from_anchors(export_dir)
    links = export_dir / "navigation_hints.json"
    had_cache = (export_dir / ".godot").exists()
    occluders.ensure_imported(export_dir, godot_executable)
    bundled = export_dir / Path(script).name
    bundled.write_bytes(Path(script).read_bytes())
    proc = None
    try:
        args = [str(godot_executable), "--headless", "--path", str(export_dir),
                "--script", f"res://{Path(script).name}", "--",
                f"res://{REPORT_NAME}", str(cell), "%s,%s,%s" % tuple(seed),
                f"res://{links.name}" if links.is_file() else "", extent_from_hints(export_dir)]
        proc = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError) as exc:
        raise DropCensusError(f"the instrument did not run: {exc}") from exc
    finally:
        bundled.unlink(missing_ok=True)
        if not had_cache:
            occluders.drop_cache(export_dir)
    if not report_path.is_file():
        raise DropCensusError("the instrument wrote no report (godot exit %s)%s"
                              % (getattr(proc, "returncode", "?"), _engine_tail(proc)))
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise DropCensusError(f"report unreadable: {exc}") from exc
    if not isinstance(report, dict) or report.get("schema") != SCHEMA:
        raise DropCensusError(f"report schema is {report.get('schema')!r}, not {SCHEMA!r}")
    for key in ("edges", "owners", "reachable_cells", "seed", "standable_cells", "unguarded"):
        if key not in report:
            raise DropCensusError(f"report carries no {key!r}")
    if report.get("error") or not report.get("ok", False):
        raise DropCensusError(f"the instrument failed: {report.get('error') or 'ok is false'}")
    return report


def _declared_from_links(export_dir) -> tuple:
    """(drop rects, ladders) from the package's links: rects as (x0, z0, x1, z1, level) in Godot metres
    (a `hole` rides verbatim in the site's Blender frame: Godot x = x, z = -y), ladders as their two ends,
    ((x, y, z), (x, y, z)), Godot metres."""
    path = Path(export_dir) / "navigation_hints.json"
    rects, ladders = [], []
    if not path.is_file():
        return rects, ladders
    hints = json.loads(path.read_text(encoding="utf-8"))
    for link in hints.get("links") or []:
        cap = link.get("required_capability")
        if cap == "drop" and link.get("hole") and link.get("start_position"):
            (hx0, hy0), (hx1, hy1) = link["hole"]
            rects.append((min(hx0, hx1), -max(hy0, hy1), max(hx0, hx1), -min(hy0, hy1),
                          float(link["start_position"][1])))
        elif cap == "climb":
            a, b = link.get("start_position"), link.get("end_position")
            if all(isinstance(p, list) and len(p) == 3 for p in (a, b)):
                ladders.append((tuple(float(v) for v in a), tuple(float(v) for v in b)))
    return rects, ladders


def _in_shaft(x, y, z, ladder) -> bool:
    """Whether (x, y, z) is at a ladder's shaft: at a height from its foot to its head (LEVEL_TOL either way),
    within LADDER_R of where the ladder is at that height -- a vertical ladder's column, a raked one's line.

    NOT ITS ENDS ONLY. The first draft of this rule claimed an edge within LADDER_R of either END at that end's
    height, and refused cold run 9318's package on 7 rows: the deli's ladder runs from the ground floor to the
    roof THROUGH the first floor, whose slab is cut for it, and the cut is no end of the link."""
    (x0, y0, z0), (x1, y1, z1) = ladder
    lo, hi = min(y0, y1), max(y0, y1)
    if y < lo - LEVEL_TOL or y > hi + LEVEL_TOL:
        return False
    t = 0.0 if hi - lo < 1e-6 else min(1.0, max(0.0, (y - y0) / (y1 - y0)))
    px, pz = x0 + t * (x1 - x0), z0 + t * (z1 - z0)
    return ((x - px) ** 2 + (z - pz) ** 2) ** 0.5 <= LADDER_R


def _dist_outside_rect(x, z, rect) -> float:
    """How far (x, z) lies outside the rect (0 inside)."""
    x0, z0, x1, z1 = rect[:4]
    dx = max(x0 - x, 0.0, x - x1)
    dz = max(z0 - z, 0.0, z - z1)
    return (dx * dx + dz * dz) ** 0.5


def classify(report: dict, export_dir) -> dict:
    """Every row put in the first class that claims it; the verdict is the `undeclared` count."""
    owners = report.get("owners") or []
    rects, ladders = _declared_from_links(export_dir)
    counts = {k: 0 for k in ("top", "outdoors", "stair_side", "declared_drop", "ladder_hole", "undeclared")}
    undeclared, outdoors = [], []
    for e in report.get("edges") or []:
        x, y, z = float(e["x"]), float(e["y"]), float(e["z"])
        on = _tail(owners, e.get("on"))
        if not _floor_like(on):
            cls = "top"
        elif not e.get("indoors", False):
            cls = "outdoors"
        elif re.match(r"GreyboxBase/stair\d", on):
            cls = "stair_side"
        elif any(abs(y - r[4]) <= LEVEL_TOL and _dist_outside_rect(x, z, r) <= HOLE_MARGIN for r in rects):
            cls = "declared_drop"
        elif any(_in_shaft(x, y, z, lad) for lad in ladders):
            cls = "ladder_hole"
        else:
            cls = "undeclared"
        counts[cls] += 1
        row = {"x": x, "y": y, "z": z, "drop_m": float(e.get("drop_m", 0)), "on": on,
               "to": _tail(owners, e.get("to"))}
        if cls == "undeclared":
            undeclared.append(row)
        elif cls == "outdoors":
            outdoors.append(row)
    undeclared.sort(key=lambda r: -r["drop_m"])
    outdoors.sort(key=lambda r: -r["drop_m"])
    return {
        "schema": SCAN_SCHEMA,
        "seed": report.get("seed"),
        "standable_cells": report.get("standable_cells"),
        "reachable_cells": report.get("reachable_cells"),
        "links": {"drop": len(rects), "climb": len(ladders),
                  "used": report.get("links_used"), "unresolved": report.get("links_unresolved")},
        "drop_edges": report.get("drop_edges"), "guarded": report.get("guarded"),
        "unguarded": report.get("unguarded"), "counts": counts,
        "undeclared": undeclared[:200], "outdoors": outdoors[:50],
        "cell_m": report.get("cell_m"), "extent": report.get("extent"),
    }


def write_scan(export_dir, scan: dict) -> Path:
    path = Path(export_dir) / SCAN_NAME
    path.write_text(json.dumps(scan, indent=2, sort_keys=True), encoding="utf-8")
    return path


def summary(scan: dict) -> str:
    """One line for the export log. Says which question it answered."""
    if scan.get("counts") is None:
        return "NOT TAKEN -- %s; nothing is certified about this package's drops" % scan.get("not_taken", "?")
    c = scan["counts"]
    return ("%s reached of %s standable cells, %s unguarded drop edge(s): %d a flight's own side, %d at a "
            "declared drop, %d at a ladder's shaft, %d a thing's top, %d outdoors (reported), %d UNDECLARED "
            "indoors -- the class this gate refuses on"
            % (scan.get("reachable_cells"), scan.get("standable_cells"), scan.get("unguarded"),
               c["stair_side"], c["declared_drop"], c["ladder_hole"], c["top"], c["outdoors"], c["undeclared"]))


def assert_declared(export_dir, scan: dict) -> dict:
    """Raise `UndeclaredDropError` when a body can walk off an undeclared edge indoors. A scan not taken
    refuses nothing: it certified nothing, and said so."""
    if scan.get("counts") is None:
        return scan
    bad = int(scan["counts"].get("undeclared", 0))
    if not bad:
        return scan
    lines = [
        "UNDECLARED_DROP_INDOORS: %d unguarded edge(s) a body reaches, indoors, on a floor, that nothing "
        "declares" % bad,
        "  a body walks off each into a fall deeper than it steps; a rail guards it, a floor_hole / hatch "
        "vertical link in the building's spec declares it, and either fix lands in Deli Counter, not here",
    ]
    for r in scan["undeclared"][:8]:
        lines.append("    (%.2f, %.2f, %.2f) drop %.2f m  on %s  to %s"
                     % (r["x"], r["y"], r["z"], r["drop_m"], r["on"], r["to"]))
    lines.append("  full report: %s and %s" % (Path(export_dir) / SCAN_NAME, Path(export_dir) / REPORT_NAME))
    raise UndeclaredDropError("\n".join(lines))
