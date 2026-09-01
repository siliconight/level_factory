"""LF driver: compose the themed presentation scene using Deli Counter's OWN
composer, out-of-process.

Level Factory does not reimplement the greybox-fit / collision-alignment logic —
Deli Counter is the source of collision truth, and it already owns the composer
(``portable_building.build_package`` -> ``themed_tscn.write_themed_tscn`` with the
fit-to-greybox rotation). This script just adds the DC repo to ``sys.path`` and
calls it, so the alignment logic stays in DC and LF only orchestrates.

It emits, under ``--out``:
    <bid>.tscn                 themed building: greybox floors+collision base +
                               themed Zoo modules fit onto each slot + markers
    <bid>_base.glb             the stripped greybox (floors/canopy/props + ALL
                               colliders; slot surfaces removed to avoid doubles)
    art/zoo/*.glb              the themed modules (bundled)
    portable_resource_manifest.json   incl. the placement-gate + closure report

``--building-id site`` gives the scene a stable name so the Lux stage can resolve
``<out>/site.tscn`` without knowing DC's building_id at plan time.

Pure Python (DC's serializer is bpy-free); needs pygltflib for the greybox base
strip + placement gate (same dep DC's build already uses).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


#: Copied into the composed package and named by `[importer_defaults]`. Lives in
#: `assets/godot/` beside `run_lux_apply.gd` and the walk bots, because it is a
#: Godot-side asset LF ships rather than a driver LF runs.
_WORLDSKIN = "zoo_worldskin.gd"


def _install_worldskin(out: Path) -> None:
    """Bake world-space UVs onto kit modules at import, for every build.

    ROADMAP 76, 80 and 88, and the reason it is HERE. Zoo box-projects UVs from
    each module's own local box, so a module's texture restarts at its own edges
    and a `wallEnd` scaled 0.15 x 3.30 to fill a remainder stretches its skin
    11:1. glTF cannot express "project from world position" -- it carries UV sets
    and nothing else -- so this can only be a material property set after import.

    Godot's own `import_script/path` hook is the cheapest place to set it: the
    material is edited once inside the imported scene and every instance of that
    GLB shares it. The alternative, a pass over the composed scene, means
    `surface_material_override` per placement -- a separate material for each of
    218 kit modules, which is Deli Counter's one-mesh-in-VRAM discipline undone
    at the material layer for the sake of a boolean.

    PROVEN BEFORE IT WAS WIRED. The same change made at runtime in a scratch walk
    project was confirmed by eye -- the stretched strips and the 2 m module seams
    both gone -- and measured against a null run: 7 of 8 shots cleared the
    instrument\'s own floor, max |delta| 43-217 against floors of 7-16. Baking it
    at import reproduces that to within ~50 pixels of a 1.44 Mpx frame, a
    residual that is real (the null pair differs by 0 pixels at the same
    threshold) and unexplained; the leading candidate is `uv1_scale` being
    derived from the mesh at a different point in the import pipeline. Recorded
    rather than waved away.

    Best-effort: a compose that cannot write the script still produces a valid
    package, it just produces the old look. Saying nothing would be worse than
    either outcome, so it says which.
    """
    src = Path(__file__).resolve().parent.parent / "godot" / _WORLDSKIN
    proj = out / "project.godot"
    if not src.is_file():
        print(f"[compose] worldskin NOT installed: {src} is missing",
              file=sys.stderr)
        return
    decl = 'scene={\n"import_script/path": "res://%s"\n}' % _WORLDSKIN
    try:
        (out / _WORLDSKIN).write_text(src.read_text(encoding="utf-8"),
                                      encoding="utf-8")
        txt = proj.read_text(encoding="utf-8") if proj.exists() else ""
        if "import_script/path" in txt:
            return
        if "[importer_defaults]" in txt:
            # Append INSIDE the existing section. A second `[importer_defaults]`
            # header is a redefinition, and Godot keeps the last one -- which
            # would silently drop whatever the first one set.
            txt = txt.replace("[importer_defaults]",
                              "[importer_defaults]\n\n" + decl, 1)
        else:
            txt = txt.rstrip("\n") + "\n\n[importer_defaults]\n\n" + decl + "\n"
        proj.write_text(txt, encoding="utf-8")
        print("[compose] worldskin: kit modules import with world-space UVs "
              f"(res://{_WORLDSKIN})")
    except OSError as exc:
        print(f"[compose] worldskin NOT installed: {exc}", file=sys.stderr)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--deli-repo", required=True,
                    help="Deli Counter repo (has portable_building.py + siblings)")
    ap.add_argument("--slots", required=True, help="<name>.slots.json from DC")
    ap.add_argument("--gameplay", default="", help="<name>.gameplay.json (markers)")
    ap.add_argument("--modules", required=True, help="themed Zoo kit module dir")
    ap.add_argument("--theme", required=True)
    ap.add_argument("--style", type=int, default=1)
    ap.add_argument("--greybox", default="",
                    help="DC greybox .glb -> floors+collision base (walkable)")
    ap.add_argument("--building-id", default=None,
                    help="stable scene id (default: DC's building_id)")
    ap.add_argument("--dressing", default="",
                    help="zoo dressing GLB (props layer) to bundle + instance")
    ap.add_argument("--fixtures", default="",
                    help="zoo fixtures GLB (light fixtures + LuxEmit markers)")
    ap.add_argument("--out", required=True, help="output dir for the composed scene")
    a = ap.parse_args()

    # LINEAGE GUARD: dressing/fixtures are Patina-placed against ONE specific
    # build's walls and roof. Mixing a layer from a different build variant
    # embeds props inside the wrong geometry (z-fighting roofs, blocked
    # ladders). Refuse when a layer's sibling .built.json names a different
    # spec content than the slots manifest.
    import hashlib
    def _spec_sha(path):
        try:
            man = json.loads(Path(path).read_text(encoding="utf-8"))
            return man.get("spec_sha256_16") or man.get("source_spec_sha")
        except (OSError, json.JSONDecodeError):
            return None
    slots_sha = None
    try:
        slots_sha = json.loads(Path(a.slots).read_text(
            encoding="utf-8")).get("spec_sha256_16")
    except (OSError, json.JSONDecodeError):
        pass
    for layer in (a.dressing, a.fixtures):
        if not layer:
            continue
        side = Path(layer).with_suffix("").as_posix() + ".built.json"
        lsha = _spec_sha(side)
        if slots_sha and lsha and lsha != slots_sha:
            print(f"[compose] ERROR: layer {Path(layer).name} was built for a "
                  f"DIFFERENT build (spec {lsha} != slots {slots_sha}) -- "
                  f"mixing lineages embeds props in the wrong geometry.",
                  file=sys.stderr)
            return 5

    deli_repo = Path(a.deli_repo)
    if not (deli_repo / "portable_building.py").exists():
        print(f"[compose] ERROR: DC composer not found at "
              f"{deli_repo / 'portable_building.py'}", file=sys.stderr)
        return 2
    # DC's composer imports its siblings (themed_tscn, tscn_export) by bare name.
    sys.path.insert(0, str(deli_repo))

    try:
        import portable_building  # DC's authoritative themed-building exporter
    except Exception as exc:  # noqa: BLE001 - report cause plainly
        print(f"[compose] ERROR importing DC composer: {exc!r}", file=sys.stderr)
        if "pygltflib" in repr(exc):
            print("[compose] hint: pip install pygltflib (DC build dependency)",
                  file=sys.stderr)
        return 2

    # Content layers are OPTIONAL kwargs: only pass them when set, so this
    # driver still works against a Deli Counter older than the layer contract
    # (or the test-fixture stub) as long as no layers were requested. When a
    # layer IS requested against an old DC, the TypeError below is the honest
    # failure: the composer genuinely cannot bundle it.
    layer_kwargs = {}
    if a.dressing:
        layer_kwargs["dressing_glb"] = a.dressing
    if a.fixtures:
        layer_kwargs["fixtures_glb"] = a.fixtures
    try:
        man = portable_building.build_package(
            a.slots, (a.gameplay or None), a.modules, a.out,
            theme=a.theme, style=a.style,
            building_id=(a.building_id or None),
            greybox_glb=(a.greybox or None),
            **layer_kwargs,
        )
    except ModuleNotFoundError as exc:
        # DC's greybox base-strip + placement gate use pygltflib (a build dep).
        print(f"[compose] ERROR: {exc}. DC's composer needs pygltflib — "
              f"pip install pygltflib in the Level Factory python env.",
              file=sys.stderr)
        return 2

    # DC's portable project.godot omits config/features; without it Godot 4.7
    # treats the folder as an unversioned project and drops to the Project
    # Manager instead of opening the level. Ensure the feature tag is present so
    # the composed package opens directly (`godot --path <dir> -e`).
    proj = Path(a.out) / "project.godot"
    try:
        if proj.exists():
            txt = proj.read_text(encoding="utf-8")
            if "config/features" not in txt:
                txt = txt.replace(
                    "[application]",
                    '[application]\nconfig/features=PackedStringArray("4.7")', 1)
                proj.write_text(txt, encoding="utf-8")
    except OSError:
        pass

    _install_worldskin(Path(a.out))

    bid = man.get("building_id")
    print(f"[compose] {bid} ({man.get('theme')}): "
          f"{man.get('themed_modules')} themed modules, "
          f"{man.get('greybox_fallback')} greybox-fallback, "
          f"{len(man.get('bundled_modules') or [])} module GLBs bundled, "
          f"{man.get('markers_baked')} markers baked, "
          f"walkable={man.get('walkable')}")
    pc = man.get("placement_check")
    if pc:
        tag = "OK" if pc.get("ok") else "MISMATCH"
        print(f"[compose] placement gate [{tag}]: "
              f"{pc.get('matched')}/{pc.get('checked')} modules sit on the "
              f"greybox collision")
    c = man.get("closure") or {}
    print(f"[compose] closure: portable={c.get('portable')} "
          f"(absolute_paths={c.get('absolute_path_count')}, "
          f"dangling={len(c.get('dangling_refs') or [])})")
    z = man.get("zfight_check") or {}
    ztag = "OK" if z.get("ok") else "FAIL"
    print(f"[compose] z-fight gate [{ztag}]: {z.get('pairs', '?')} coplanar "
          f"pair(s) across {z.get('solids', '?')} solids"
          + (f" ({z.get('error')})" if z.get("error") else ""))
    # Persist a compact compose summary alongside the package for the adapter.
    try:
        Path(a.out, "compose.summary.json").write_text(
            json.dumps({"building_id": bid, "placement_check": pc,
                        "closure": c, "zfight_check": z,
                        "circulation_check": man.get("circulation_check"),
                        "walkable": man.get("walkable")},
                       indent=2, sort_keys=True), encoding="utf-8")
    except OSError:
        pass
    # A package that z-fights must not ship: fail the compose job so the
    # pipeline (and its cache) records a red, not a flickering deliverable.
    if not z.get("ok"):
        print("[compose] ERROR: coplanar surfaces detected -- the package "
              "would flicker. See zfight_check in the manifest.",
              file=sys.stderr)
        return 3
    # LADDER GATE: every ladder in the gameplay export must have baked a
    # climb volume (the climb contract) -- a level whose ladders regressed
    # to inert geometry must not ship as "composed".
    n_ladders = 0
    if a.gameplay:
        try:
            g = json.loads(Path(a.gameplay).read_text(encoding="utf-8"))
            n_ladders = sum(1 for m in (g.get("markers") or [])
                            if m.get("type") == "ladder")
        except (OSError, json.JSONDecodeError):
            pass
    n_baked = int(man.get("ladder_climb_volumes") or 0)
    print(f"[compose] ladder gate "
          f"[{'OK' if n_baked >= n_ladders else 'FAIL'}]: "
          f"{n_baked}/{n_ladders} climb volume(s) baked")
    if n_baked < n_ladders:
        print("[compose] ERROR: ladder(s) present but climb volume(s) "
              "missing -- the package would ship unclimbable ladders "
              "(docs/LADDER_CLIMB_CONTRACT.md).", file=sys.stderr)
        return 4
    # CIRCULATION GATE: when a dressing layer was bundled, no prop may sit in
    # a ladder climb volume, a doorway aperture, or a stair footprint -- a
    # package whose props block circulation is unplayable, not "dressed".
    circ = man.get("circulation_check")
    if circ is not None:
        ctag = "OK" if circ.get("ok") else "FAIL"
        print(f"[compose] circulation gate [{ctag}]: "
              f"{len(circ.get('conflicts') or [])} prop conflict(s) across "
              f"{circ.get('volumes', '?')} circulation volume(s)"
              + (f" ({circ.get('error')})" if circ.get("error") else ""))
        if not circ.get("ok"):
            for c in (circ.get("conflicts") or [])[:10]:
                print(f"[compose]   {c.get('prop')} intrudes "
                      f"{c.get('penetration')}m into {c.get('volume')}",
                      file=sys.stderr)
            print("[compose] ERROR: dressing blocks circulation -- see "
                  "circulation_check in the manifest.", file=sys.stderr)
            return 6
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
