"""Ship the backdrop beyond the plate's edge: the drawn site's `backdrop` list and the kit's
modules become a MultiMesh scene (0.174.0, roadmap 228 step E).

The walker picked E from the edge menu (`docs/findings/edge_menu/` at the factory root): a
chain-link fence at the plate's edge, rows of rowhomes with lit windows and a water tower behind
it, under a sky-glow. Lux 0.73.0 drew the glow, Lot 0.107.0 the fence, Zoo 1.95.0 the rowhome
and the tower, and Lot 0.108.0 planned the bands into the drawn site's `backdrop` list, where
each piece names a species, dims, a plan position and a yaw, and the side of the plate it
stands beyond. Nothing in a level showed any of it until this: the drawn scene writes no node
for a backdrop piece on purpose, because three hundred scene instances would be three hundred
draws.

THE DRESSING LAYER'S ROAD, TAKEN WHOLE. `dressing_layer` already answers the two hard questions:
how a built GLB becomes a Mesh resource a MultiMesh can draw (`extract_meshes`, Godot's own
import in a scratch project, a self-contained `.res` an asset), and how placements become a
`.tscn` of MultiMeshes with the buffer laid out the way Godot reads it (`dressing_scene`).
This module builds the manifest those two take from the drawn spec and ships
`<site>_backdrop.tscn` with `backdrop/<module>.res` beside it, which the entry scene instances
beside the level as it instances the dressing.

ONE MULTIMESH A MODULE A SIDE. A MultiMesh is one object to the culler, so one for the whole
level would keep every band alive from everywhere; one a side keeps the north's bands out of a
frame that looks south. The asset ids carry the side (`<module>__N`) and the four of a module
share one extracted mesh, so the draws are modules times sides (24 for Lot's six modules) plus
the tower, and never the houses (about 300).

WHAT IS NOT HERE. No collision (every order says so, and `dressing_scene.check_manifest`
refuses otherwise), no navmesh, no lightmap: a backdrop is seen and never reached. The kit
build that made the modules is the site kit Lot's `cover_modules` names, so a package whose
kit lacks a module says which and ships without the backdrop rather than with a hole in it.
"""
from __future__ import annotations

import json
import math
import shutil
from pathlib import Path

from packages.core.canonical import pretty_dumps
from packages.exporting.dressing_layer import extract_meshes
from packages.exporting.dressing_scene import (SCHEMA, DressingSceneError,
                                               orders_by_asset, scene_text,
                                               summarise)

#: Where the meshes live inside the package, and the report beside the scene.
BACKDROP_DIR = "backdrop"
REPORT_NAME = "backdrop_layer.json"
SPACE = "spec/Blender Z-up raw coords"
SIDES = ("N", "S", "E", "W")


def module_stem(species: str, dims, theme: str, style: int = 1) -> str:
    """The kit module's file stem for a species at dims, as Lot's `cover_module_stem`
    and Zoo's `kit.module_stem` spell it: centimetres, the style two digits."""
    w, d, h = (int(round(float(v) * 100)) for v in dims)
    return f"prop_{species}_{theme}_{int(style):02d}_w{w}_d{d}_h{h}"


def manifest_from_drawn(drawn: dict) -> dict:
    """The dressing-shaped manifest for a drawn site's `backdrop` list: one order a piece,
    its asset the module's stem and the side it stands beyond, its position the module's
    centre (a Zoo module stands on -h/2), its yaw in radians, no collision. Empty when the
    spec lays no backdrop or names no kit."""
    cm = drawn.get("cover_modules") or {}
    theme, style = str(cm.get("theme") or ""), int(cm.get("style") or 1)
    orders = []
    for p in drawn.get("backdrop") or []:
        sp, dims = p.get("species"), p.get("dims")
        if not sp or not dims or len(dims) < 3 or not theme:
            continue
        side = str(p.get("side") or "N")
        x, y = p["at"][:2]
        orders.append({
            "asset_id": f"{module_stem(sp, dims, theme, style)}__{side}",
            "module": module_stem(sp, dims, theme, style),
            "species": sp, "side": side,
            "pos": [float(x), float(y), float(dims[2]) / 2.0],
            "yaw": math.radians(float(p.get("yaw") or 0.0)),
            "scale": 1.0, "collision_policy": "none",
            "height_m": float(dims[2]), "in_traversed_space": False,
        })
    return {"schema": SCHEMA, "space": SPACE, "site_id": str(drawn.get("name") or "site"),
            "kit_dir": str(cm.get("dir") or ""), "orders": orders}


def find_kit_glbs(kit_dir: Path, modules) -> tuple[dict, list]:
    """``{module: glb_path}`` for the modules the manifest orders, and what is missing: the
    site kit build writes `<stem>.glb` at its top."""
    kit_dir = Path(kit_dir)
    found, missing = {}, []
    for stem in sorted(modules):
        p = kit_dir / f"{stem}.glb"
        if p.is_file():
            found[stem] = p
        else:
            missing.append(stem)
    return found, missing


def ship_backdrop(export_dir: Path, drawn_path, godot_executable, *,
                  scratch_root: Path | None = None) -> dict:
    """Put `<site>_backdrop.tscn` and its meshes into the package.

    Returns the report that is also written to `backdrop_layer.json` in the package:
    ``shipped``, ``scene``, ``instances``, ``meshes`` (the asset ids, a module a side),
    ``modules``, ``draw_calls``, the count by side and the tower, and the reasons it did not
    ship. Refuses to write a scene that names a mesh it could not extract.
    """
    export_dir = Path(export_dir)
    # the spec's name only: this report ships, and the closure scan reads paths in a shipped JSON
    report: dict = {"shipped": False, "drawn": Path(drawn_path).name if drawn_path else "",
                    "reasons": []}

    def _done() -> dict:
        shipped = {k: v for k, v in report.items() if k != "extraction"}
        ext = report.get("extraction") or {}
        if ext:
            shipped["extracted"] = {a: {k: v for k, v in e.items() if k != "path"}
                                    for a, e in (ext.get("extracted") or {}).items()}
            shipped["extraction_failed"] = sorted(ext.get("failed") or {})
        (export_dir / REPORT_NAME).write_text(pretty_dumps(shipped), encoding="utf-8")
        if ext:
            (export_dir.parent / (export_dir.name + ".backdrop_extract.log.json")
             ).write_text(pretty_dumps(ext), encoding="utf-8")
        return report

    if not drawn_path or not Path(drawn_path).is_file():
        report["reasons"].append("no drawn site spec to read a backdrop from")
        return _done()
    try:
        drawn = json.loads(Path(drawn_path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        report["reasons"].append(f"drawn spec unreadable: {exc}")
        return _done()
    manifest = manifest_from_drawn(drawn)
    if not manifest["orders"]:
        why = ("the drawn spec lays no backdrop" if not drawn.get("backdrop")
               else "the drawn spec names no kit (cover_modules) to take the modules from")
        report["reasons"].append(why)
        return _done()
    kit_dir = Path(manifest["kit_dir"])
    if not kit_dir.is_dir():
        report["reasons"].append("the site kit directory the spec names is not there")
        return _done()
    modules = sorted({o["module"] for o in manifest["orders"]})
    glbs, missing = find_kit_glbs(kit_dir, modules)
    report["missing_modules"] = missing
    if missing:
        report["reasons"].append(f"{len(missing)} module(s) have no built GLB in the site kit")
        return _done()
    scratch = Path(scratch_root or export_dir.parent) / (export_dir.name + ".backdrop_extract")
    extraction = extract_meshes(glbs, scratch, godot_executable)
    report["extraction"] = extraction
    failed = extraction.get("failed") or {}
    if failed or set(extraction.get("extracted") or {}) != set(modules):
        report["reasons"].append(
            "mesh extraction incomplete: " + "; ".join(f"{k}: {v}" for k, v in sorted(failed.items())))
        return _done()
    dest = export_dir / BACKDROP_DIR
    dest.mkdir(parents=True, exist_ok=True)
    mesh_paths = {}
    for stem in modules:
        rel = str(extraction["extracted"][stem]["path"]).replace("res://", "", 1)
        shutil.copy2(str(scratch / rel), str(dest / f"{stem}.res"))
    for asset in orders_by_asset(manifest):
        mesh_paths[asset] = f"res://{BACKDROP_DIR}/{asset.rsplit('__', 1)[0]}.res"
    shutil.rmtree(scratch, ignore_errors=True)
    site_id = manifest["site_id"]
    try:
        text = scene_text(manifest, mesh_paths, root_name=f"{site_id}_backdrop")
    except DressingSceneError as exc:
        report["reasons"].append(f"dressing_scene refused: {exc}")
        return _done()
    scene_name = f"{site_id}_backdrop.tscn"
    (export_dir / scene_name).write_text(text, encoding="utf-8", newline="\n")
    report.update(summarise(manifest, "multimesh"))
    houses = [o for o in manifest["orders"] if o["species"] == "backdrop_rowhome"]
    report.update({
        "shipped": True, "scene": scene_name, "modules": modules, "mesh_paths": mesh_paths,
        "by_side": {s: sum(1 for o in houses if o["side"] == s) for s in SIDES},
        "towers": sum(1 for o in manifest["orders"] if o["species"] == "water_tower"),
    })
    return _done()
