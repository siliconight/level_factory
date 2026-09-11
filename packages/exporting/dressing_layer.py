"""Ship the Layer 3 surface dressing: a manifest and four GLBs become a scene.

The last stage of the chain `docs/SURFACE_DRESSING.md` section 2 describes
and roadmap 110 found connected to nothing. Zoo built the clutter species and
measured them, Lot said where dressing may go, Patina decided what goes where
and wrote `<site>.surface_dressing.json`. This turns that decision into
`<site>_dressing.tscn` at the package root, which the entry scene instances
BESIDE the level -- never inside it, because the shell is locked and a
dressing pass that edits the locked scene has already broken the one promise
the layer makes.

THE MESH QUESTION, ANSWERED HERE AND NOWHERE ELSE. `dressing_scene.scene_text`
needs, per asset, a resource path that resolves to a MESH, and refuses to
guess one: a `.glb` imports as a PackedScene, a MultiMesh needs a Mesh. The
answer is `assets/godot/extract_meshes.gd`, run in a scratch project that
holds nothing but the clutter GLBs: it imports them, merges every
MeshInstance3D of each into one ArrayMesh with the placement baked in, and
saves a self-contained `.res` per asset. Those land in `dressing/` and the
scene names them as `res://dressing/<asset>.res`. Godot does the conversion
because Godot is the only thing that knows its own import; Python verifies
it from the report the script writes rather than trusting the exit code.

NO GODOT, NO LAYER -- SAID, NOT SKIPPED. `godot_executable` is optional
everywhere in the export because a missing Godot is a setup problem, not an
export failure. Here it means the dressing cannot ship, and the report says
so in the package (`dressing_layer.json`) and on stdout, so an undressed
package reads as undressed rather than as one that never planned any.

What this does NOT do: ship the GLBs. The `.res` bundles mesh, materials and
textures, so the GLB would be a second copy of the same geometry.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from packages.core.canonical import pretty_dumps
from packages.exporting.dressing_scene import (DressingSceneError,
                                               orders_by_asset, scene_text,
                                               summarise)

#: The Godot script that turns imported GLBs into Mesh resources.
#:   packages/exporting/dressing_layer.py -> exporting -> packages -> <lf>
_LF_ROOT = Path(__file__).resolve().parents[2]
EXTRACT_SCRIPT = _LF_ROOT / "assets" / "godot" / "extract_meshes.gd"

#: Where the meshes live inside the package, and the report beside the scene.
DRESSING_DIR = "dressing"
REPORT_NAME = "dressing_layer.json"

_PROJECT_GODOT = (
    "; Scratch project for extract_meshes.gd -- nothing in it ships.\n"
    "config_version=5\n\n[application]\n\n"
    'config/name="dressing_extract"\n'
)


def find_clutter_glbs(clutter_dir: Path, assets) -> tuple[dict, list[str]]:
    """``{asset_id: glb_path}`` for the assets a manifest orders, and what is missing.

    Zoo names a specimen `<species>_<hash>.glb` and lists it under the habitat
    index's `members[].files.glb`; the index is read first, and a bare glob
    over `<species>_*.glb` is the fallback for a directory with no index.
    Two specimens of one species is an ambiguity, not a choice: reported as
    missing rather than resolved by sort order.
    """
    clutter_dir = Path(clutter_dir)
    found: dict = {}
    missing: list[str] = []
    by_species: dict = {}
    for index in sorted(clutter_dir.glob("*.habitat.json")):
        try:
            doc = json.loads(index.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for m in doc.get("members") or []:
            if not isinstance(m, dict):
                continue
            glb = (m.get("files") or {}).get("glb")
            if glb and m.get("status") != "fail":
                by_species.setdefault(str(m.get("species")), []).append(
                    clutter_dir / str(glb))
    for asset in sorted(assets):
        hits = [p for p in by_species.get(asset, []) if p.is_file()]
        if not hits:
            hits = sorted(clutter_dir.glob(f"{asset}_*.glb"))
        if len(hits) == 1:
            found[asset] = hits[0]
        elif not hits:
            missing.append(f"{asset}: no built GLB under {clutter_dir}")
        else:
            missing.append(f"{asset}: {len(hits)} GLBs under {clutter_dir}, "
                           f"which one is not a sort-order decision")
    return found, missing


def extract_meshes(glbs: dict, scratch: Path, godot_executable,
                   *, script: Path = EXTRACT_SCRIPT,
                   timeout: int = 600) -> dict:
    """Run the extraction in a scratch Godot project; return the script's report.

    The report is the evidence: ``extracted`` maps asset -> {path, surfaces,
    vertices, parts, aabb}; ``failed`` maps asset -> reason. A run that could
    not happen at all is reported the same way under ``failed`` with the
    reason, never as an empty success.
    """
    scratch = Path(scratch)
    if scratch.exists():
        shutil.rmtree(scratch)
    scratch.mkdir(parents=True)
    (scratch / "project.godot").write_text(_PROJECT_GODOT, encoding="utf-8")
    shutil.copy2(str(script), str(scratch / script.name))
    assets = {}
    for asset, src in sorted(glbs.items()):
        shutil.copy2(str(src), str(scratch / f"{asset}.glb"))
        assets[asset] = f"res://{asset}.glb"
    (scratch / "extract.json").write_text(pretty_dumps({
        "assets": assets, "out_dir": f"res://{DRESSING_DIR}"}),
        encoding="utf-8")
    report: dict = {"extracted": {}, "failed": {}}
    if not godot_executable:
        report["failed"]["*"] = ("no godot_executable configured; the Mesh "
                                 "resources cannot be extracted")
        return report
    runs = (
        ["--headless", "--path", str(scratch), "--import"],
        ["--headless", "--path", str(scratch), "--script",
         f"res://{script.name}"],
    )
    for args in runs:
        try:
            proc = subprocess.run([str(godot_executable), *args],
                                  capture_output=True, text=True,
                                  timeout=timeout)
        except (OSError, subprocess.SubprocessError) as exc:
            # Short, and without the command line: this string lands in the
            # package's report, and the closure scan reads every res:// and
            # repo path in a shipped JSON as a reference to resolve.
            report["failed"]["*"] = (f"godot {args[-1].split('/')[-1]} pass: "
                                     f"{type(exc).__name__}")
            return report
        report.setdefault("log", []).append({
            "args": args, "returncode": proc.returncode,
            "stdout_tail": (proc.stdout or "")[-2000:],
            "stderr_tail": (proc.stderr or "")[-2000:]})
    written = scratch / "extract.report.json"
    if not written.is_file():
        report["failed"]["*"] = ("extract_meshes.gd wrote no report; see log "
                                 "(the script did not run, or crashed before "
                                 "_finish)")
        return report
    try:
        doc = json.loads(written.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        report["failed"]["*"] = f"extract.report.json unreadable: {exc}"
        return report
    report["extracted"] = dict(doc.get("extracted") or {})
    report["failed"].update(doc.get("failed") or {})
    # VERIFIED, NOT TRUSTED: a reported path that is not on disk is a failure.
    for asset, entry in list(report["extracted"].items()):
        rel = str(entry.get("path", "")).replace("res://", "", 1)
        if not (scratch / rel).is_file():
            report["failed"][asset] = f"reported {entry.get('path')} but no file"
            del report["extracted"][asset]
    return report


def ship_dressing(export_dir: Path, manifest_path, clutter_dir,
                  godot_executable, *, scratch_root: Path | None = None,
                  mode: str = "multimesh") -> dict:
    """Put `<site>_dressing.tscn` and its meshes into the package.

    Returns the report that is also written to `dressing_layer.json` in the
    package: ``shipped`` (bool), ``scene``, ``instances``, ``meshes``,
    ``draw_calls``, and the extraction evidence or the reasons it did not
    ship. Refuses to write a scene that names a mesh it could not extract --
    `scene_text` would refuse too, but this says which and why first.
    """
    export_dir = Path(export_dir)
    report: dict = {"shipped": False, "manifest": str(manifest_path or ""),
                    "clutter_dir": str(clutter_dir or ""), "reasons": []}

    def _done() -> dict:
        # TWO REPORTS. The one in the package says what shipped and why not,
        # in words; the extraction log -- Godot's command lines and output,
        # full of res:// and repository paths -- goes BESIDE the package,
        # because the closure scan reads every such string in a shipped JSON
        # as a reference to resolve, and the first export of this layer
        # failed closure on its own diagnostics.
        shipped = {k: v for k, v in report.items() if k != "extraction"}
        ext = report.get("extraction") or {}
        if ext:
            shipped["extracted"] = {a: {k: v for k, v in e.items() if k != "path"}
                                    for a, e in (ext.get("extracted") or {}).items()}
            shipped["extraction_failed"] = sorted(ext.get("failed") or {})
        (export_dir / REPORT_NAME).write_text(pretty_dumps(shipped),
                                              encoding="utf-8")
        if ext:
            (export_dir.parent / (export_dir.name + ".dressing_extract.log.json")
             ).write_text(pretty_dumps(ext), encoding="utf-8")
        return report

    if not manifest_path or not Path(manifest_path).is_file():
        report["reasons"].append("no surface_dressing manifest to ship")
        return _done()
    if not clutter_dir or not Path(clutter_dir).is_dir():
        report["reasons"].append("no clutter build directory to take meshes from")
        return _done()
    try:
        manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        report["reasons"].append(f"manifest unreadable: {exc}")
        return _done()
    assets = sorted(orders_by_asset(manifest))
    if not assets:
        report["reasons"].append("the manifest places nothing")
        return _done()
    glbs, missing = find_clutter_glbs(Path(clutter_dir), assets)
    report["missing_glbs"] = missing
    if missing:
        report["reasons"].append(f"{len(missing)} asset(s) have no built GLB")
        return _done()
    scratch = Path(scratch_root or export_dir.parent) / (
        export_dir.name + ".dressing_extract")
    extraction = extract_meshes(glbs, scratch, godot_executable)
    report["extraction"] = extraction
    failed = extraction.get("failed") or {}
    if failed or set(extraction.get("extracted") or {}) != set(assets):
        report["reasons"].append(
            "mesh extraction incomplete: "
            + "; ".join(f"{k}: {v}" for k, v in sorted(failed.items())))
        return _done()
    dest = export_dir / DRESSING_DIR
    dest.mkdir(parents=True, exist_ok=True)
    mesh_paths = {}
    for asset in assets:
        rel = str(extraction["extracted"][asset]["path"]).replace("res://", "", 1)
        shutil.copy2(str(scratch / rel), str(dest / f"{asset}.res"))
        mesh_paths[asset] = f"res://{DRESSING_DIR}/{asset}.res"
    shutil.rmtree(scratch, ignore_errors=True)
    site_id = str(manifest.get("site_id") or "site")
    try:
        text = scene_text(manifest, mesh_paths, mode=mode)
    except DressingSceneError as exc:
        report["reasons"].append(f"dressing_scene refused: {exc}")
        return _done()
    scene_name = f"{site_id}_dressing.tscn"
    (export_dir / scene_name).write_text(text, encoding="utf-8",
                                         newline="\n")
    report.update(summarise(manifest, mode))
    report.update({"shipped": True, "scene": scene_name,
                   "mesh_paths": mesh_paths})
    return _done()
