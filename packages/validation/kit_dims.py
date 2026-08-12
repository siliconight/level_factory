"""Does a built Zoo kit have the dimensions its own index says it has?

The producer checking its own output. Zoo writes
``<building_id>_kit.built.json`` beside the modules, and every entry carries the
``dims`` the planner asked for and the ``fit`` that says how to read them. The
``.glb`` beside it is what was actually built. Nothing compared the two.

## Why this exists

Measured 2026-08-09. Every kit module in every building of ``lot_demo_001``
was 3.300 m tall against slots asking 3.1, 3.9, 4.2, 4.7 and 5.2 -- because one
kit job was planned per mission, built from the mission shell's slots, and its
output handed to every building. Seven of eight buildings shipped with walls
that did not reach their own ceilings; ``depot_a01`` had a 0.95 m gap under
every wall in the building. Every gate passed it.

The gate that would have caught it needs no new information. The index states
the intent, the file next to it is the fact, and both are inside one job's
outputs -- so this needs no slots path, no Zoo import, and no knowledge of the
naming law. A check that can be made from what a job already produces is a
check that cannot drift from what it is checking.

## The axis, which is the part to get right

A ``.glb`` IS Y-UP. Zoo authors in Blender's Z-up and the glTF exporter
converts on the way out, so a standing slab's height is its **y** extent on
disk and its thickness is z. Deli Counter's ``fit.dims`` are
``[width, depth, height]``. The mapping is therefore ``(x, z, y)``.

Read z as the height and a correct kit reports
``wall wanted 5.2, built 0.3`` -- a wall's height compared against its own
thickness. That is not hypothetical either; it is what the first version of
`module_extents.py --kit` did, and its fixture was authored Z-up too, so the
pair agreed with each other and passed.

## What is NOT flagged

``fit: "unit"`` modules are checked against 1x1x1 rather than against their
slot. A ``wallEnd`` is one unit box that Deli Counter SCALES per slot at
placement time -- measuring one against its slot's 5.2 m would report the one
correct module in the kit as the broken one, which is exactly the mistake that
opened this whole thread from the other end.

Modules whose ``status`` is ``fail`` are skipped. Zoo already reports those as
``ZOO_PARTIAL_BUILD`` and a module that failed to build has no dimensions to
disagree about; flagging it twice would make one fault look like two.
"""
from __future__ import annotations

import json
from pathlib import Path

from packages.validation.glb_collision import json_chunk, solids_in

#: A millimetre. Exported floats are not exact, and bevels move an edge by
#: less than this; a real mismatch in this library is centimetres at minimum
#: and was metres in the case that prompted the check.
TOLERANCE_M = 0.001

#: ``fit.dims`` order, for the message. Named because the transposition
#: between this and the file's own axes is the one thing here worth checking
#: twice.
DIMS_ORDER = ("width", "depth", "height")


def module_extent(path: Path) -> tuple[float, float, float] | None:
    """``(w, d, h)`` of everything in the ``.glb``, or ``None`` if unreadable.

    ``every_mesh=True``: this wants the module's whole visible extent, not the
    subset Godot would build bodies for. A wall's collider and its relief are
    different objects by construction (``recipes/_arch.py``) and the thing that
    has to reach the ceiling is the geometry.
    """
    doc = _doc(Path(path))
    if doc is None:
        return None
    reading = solids_in(doc, every_mesh=True)
    if not reading.read or not reading.solids:
        return None
    lo = [float("inf")] * 3
    hi = [float("-inf")] * 3
    for solid in reading.solids:
        for axis in range(3):
            half = abs(solid.size[axis]) / 2.0
            lo[axis] = min(lo[axis], solid.centre[axis] - half)
            hi[axis] = max(hi[axis], solid.centre[axis] + half)
    if any(v == float("inf") for v in lo):
        return None
    # (x, z, y) -> (w, d, h). See the module docstring; a .glb is Y-up.
    return (round(hi[0] - lo[0], 4),
            round(hi[2] - lo[2], 4),
            round(hi[1] - lo[1], 4))


def _doc(path: Path):
    """The glTF document, via the reader `glb_collision` already owns.

    `collision_solids` is not reused wholesale because it decides `every_mesh`
    from the `.import` sidecar, and this measurement wants every mesh whatever
    Godot was told to body.
    """
    try:
        if path.suffix.lower() == ".gltf":
            doc = json.loads(path.read_text(encoding="utf-8", errors="replace"))
        else:
            doc = json_chunk(path.read_bytes())
    except (OSError, ValueError):
        return None
    return doc if isinstance(doc, dict) else None


def _glb_for(entry: dict, root: Path) -> Path | None:
    """The module's own ``.glb``: named by the index, else ``<stem>.glb``."""
    for value in (entry.get("files") or {}).values():
        p = Path(str(value))
        if p.suffix.lower() == ".glb":
            return p if p.is_file() else root / p.name
    stem = entry.get("stem")
    if not stem:
        return None
    candidate = root / f"{stem}.glb"
    return candidate if candidate.is_file() else None


def kit_dimension_findings(index_path) -> list[dict]:
    """Findings for every module in a kit index that is not the size it claims.

    Returns the adapter issue shape, so a caller appends and is done.
    """
    index_path = Path(index_path)
    try:
        index = json.loads(index_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    if not isinstance(index, dict):
        return []
    root = index_path.parent
    building = index.get("building_id") or index_path.stem
    issues: list[dict] = []
    unreadable: list[str] = []

    for entry in index.get("modules") or []:
        if not isinstance(entry, dict) or entry.get("status") == "fail":
            continue
        fit = entry.get("fit")
        if fit == "unit":
            want = (1.0, 1.0, 1.0)
        else:
            dims = entry.get("dims")
            if not (isinstance(dims, list) and len(dims) >= 3):
                continue
            want = tuple(float(v) for v in dims[:3])
        glb = _glb_for(entry, root)
        if glb is None or not glb.is_file():
            continue          # a missing file is the build's finding, not ours
        got = module_extent(glb)
        if got is None:
            unreadable.append(str(entry.get("stem") or glb.name))
            continue
        off = [(DIMS_ORDER[i], want[i], got[i]) for i in range(3)
               if abs(want[i] - got[i]) > TOLERANCE_M]
        if not off:
            continue
        detail = ", ".join(f"{axis} {w:.3f} -> {g:.3f}" for axis, w, g in off)
        issues.append({
            "code": "ZOO_KIT_DIMS_MISMATCH",
            "severity": "blocker", "category": "art_geometry",
            "message": (
                f"{building}: module '{entry.get('stem')}' was built to a "
                f"different size than the slot it was planned for ({detail}). "
                f"A module that does not fill its slot leaves a gap you can "
                f"walk through, and the composed scene will look finished."),
            "blocking": True, "raw_source_path": str(glb),
        })

    if unreadable:
        # Not silence. An unreadable module is an unknown, and an unknown that
        # prints nothing is indistinguishable from a pass -- which is the
        # failure this whole file exists downstream of.
        issues.append({
            "code": "ZOO_KIT_DIMS_UNREADABLE",
            "severity": "moderate", "category": "art_geometry",
            "message": (f"{building}: {len(unreadable)} module(s) could not be "
                        f"measured, so their dimensions are unverified: "
                        + ", ".join(sorted(unreadable)[:6])),
            "blocking": False, "raw_source_path": str(index_path),
        })
    return issues
