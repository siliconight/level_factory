"""Stop submitting what a wall is hiding: emit the package's occluders.

THE MEASUREMENT THIS EXISTS FOR. On cold run 9062's package, after Zoo
1.1.0's merge, standing inside the card shop at `interior_c` cost 4,635 draw
calls and 14.36 ms. Attributing that by hiding one top-level branch at a
time and reading the draw count back:

    b0  (the shop you are standing in)     266
    b1  (the country club across the road) 1,599  of 1,602 it owns
    b2  (the market hall)                  1,481  of 1,487 it owns
    street props                             719
    site surface                             566

Two buildings were being submitted essentially whole -- their interiors
included, every shelf and wall of a room no ray from that camera can reach.
Frustum culling cannot reject them, because they are in front of the camera.
Only the wall between can, and nothing in the package was telling the engine
there was a wall.

WHAT THIS SHIPS. `occluders.tscn`, a scene of nothing but
`OccluderInstance3D`, instanced by `site.tscn`. Ordinary scene data: no
addon, no import script, no autoload, so the package's standing promise --
that it opens in somebody else's Godot project with none of our tools
present -- is unchanged. A recipient whose project has occlusion culling
switched off gets inert nodes that cost nothing rather than a broken level.

THE DIVISION OF LABOUR. `assets/godot/bake_occluders.gd` measures, because
Godot is the only thing that has imported these GLBs and a module's filename
carries its width but not its height or thickness. This writes the scene,
because two things Godot's own packer did were wrong for a generated
package, both measured rather than assumed:

  * `ResourceSaver` names sub-resources non-deterministically -- two runs
    over one unchanged package produced two different files.
  * It wrote one `BoxOccluder3D` per occluder: 395 resources for 17 distinct
    sizes. Sharing them is the same rule as never expressing variation as a
    new material.

WHAT IS NOT OCCLUDED, and why each one is deliberate. Glass, because a
storefront shows the street and an occluder across it would cull what is
visibly through it. Doorways, windows and breaches, because the opening is
the module. Props of every kind -- lampposts, rails, bins, signs -- because
they are thin or porous and an occluder is a promise that nothing is
visible past it. The counts are in `occluders.json` so a skip is priced
rather than assumed.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

from packages.core.godot_project import OCCLUSION_KEY

#: The Godot script that measures the modules.
#:   packages/exporting/occluders.py -> exporting -> packages -> <lf>
_LF_ROOT = Path(__file__).resolve().parents[2]
BAKE_SCRIPT = _LF_ROOT / "assets" / "godot" / "bake_occluders.gd"

#: What lands in the package.
OCCLUDER_SCENE = "occluders.tscn"
REPORT_NAME = "occluders.json"
SCHEMA = "lf.occluders.v1"

#: The node `site.tscn` gains. Named, because the patch has to find it again
#: to know the scene has already been wired and not wire it twice.
HOLDER_NODE = "Occluders"
_EXT_ID = "lf_occluders"


class OccluderError(RuntimeError):
    """The bake could not be trusted. Never raised for 'no occluders' --
    that is a legitimate answer for a package with no buildings in it."""


#: Godot's import cache. Its PRESENCE is the precondition this module's bake
#: has, and its ABSENCE is what the shipped package must have.
CACHE_DIR = ".godot"


def ensure_imported(export_dir: Path, godot_executable, *,
                    timeout: int = 1200) -> bool:
    """Import the project if Godot has never imported it. True if it ran.

    THIS IS THE DEFECT COLD RUN 9065 SHIPPED. A Godot project cannot `load()`
    anything until its `.godot` cache exists -- sidecars are the import
    SETTINGS, not the imported resources -- and the export ran this bake
    straight after the sidecar pass, which deletes that cache one line before
    the bake needs it. Reproduced on the shipped
    `LF_club_block_004.portable-godot`, 2026-09-21, Godot 4.7.stable, by
    running the bake script against two clean copies of it:

        cache absent   `[occluders] FAILED: cannot load res://site.tscn`,
                       preceded by `Failed loading resource` on every GLB
                       and `referenced non-existent resource` on every PNG
        cache present  `measured=414 solid=414 porous=41 glass=35
                       filler=85 other=483`, exit 0

    Same package, same script, same engine; the only difference is whether
    `--import` had run. The 0.96.0 measurements passed because they were taken
    against packages a person had already imported by hand.

    Costs one import (18.3 s on that package) and nothing at all on the export
    path, where the sidecar pass has already left the cache in place -- this
    is then an `is_dir()` call. The caller is responsible for removing the
    cache before the package ships; `drop_cache` below is that.
    """
    export_dir = Path(export_dir)
    if (export_dir / CACHE_DIR).is_dir():
        return False
    if not godot_executable:
        raise OccluderError("no Godot executable: occluders cannot be measured")
    try:
        subprocess.run(
            [str(godot_executable), "--headless", "--path", str(export_dir),
             "--import"],
            capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError) as exc:
        raise OccluderError(f"import pass did not run: {exc}") from exc
    if not (export_dir / CACHE_DIR).is_dir():
        raise OccluderError(
            "import pass left no %s cache: the bake cannot load anything"
            % CACHE_DIR)
    return True


def drop_cache(export_dir: Path) -> bool:
    """Remove the import cache. True if there was one.

    The package ships sidecars and not the cache, deliberately: the cache is
    machine-specific and large (75.2 MB against 1.4 MB of sidecars on cold run
    9065's package). Kept here rather than in the sidecar pass so that the one
    step between them that NEEDS the cache can have it.
    """
    cache = Path(export_dir) / CACHE_DIR
    if not cache.is_dir():
        return False
    shutil.rmtree(cache, ignore_errors=True)
    return True


def measure(export_dir: Path, godot_executable, *,
            scene: str = "res://site.tscn",
            script: Path = BAKE_SCRIPT,
            timeout: int = 900) -> dict:
    """Run the bake and return its report.

    The report is the evidence. An exit code is not: the script writes
    ``ok: false`` with a reason for every failure it can name, and a report
    that does not parse, or whose schema is not the one this module knows,
    raises rather than reading as a package with no occluders in it.
    """
    export_dir = Path(export_dir)
    report_path = export_dir / REPORT_NAME
    if not godot_executable:
        raise OccluderError("no Godot executable: occluders cannot be measured")
    if not Path(script).is_file():
        raise OccluderError(f"bake script missing: {script}")
    ensure_imported(export_dir, godot_executable)
    bundled = export_dir / Path(script).name
    bundled.write_bytes(Path(script).read_bytes())
    try:
        subprocess.run(
            [str(godot_executable), "--headless", "--path", str(export_dir),
             "--script", f"res://{Path(script).name}", "--",
             scene, str(report_path)],
            capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError) as exc:
        raise OccluderError(f"bake did not run: {exc}") from exc
    finally:
        bundled.unlink(missing_ok=True)

    if not report_path.is_file():
        raise OccluderError("bake wrote no report")
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise OccluderError(f"report unreadable: {exc}") from exc
    if not isinstance(report, dict) or report.get("schema") != SCHEMA:
        raise OccluderError(
            f"report schema is {report.get('schema')!r}, not {SCHEMA!r}")
    if not report.get("ok"):
        raise OccluderError(f"bake failed: {report.get('error')}")
    if not isinstance(report.get("modules"), list):
        raise OccluderError("report carries no `modules` list")
    return report


def _fmt(v) -> str:
    """A float as Godot writes one, and the same way every run.

    `repr` would emit `1.9600000381469727` for a float32 that came back
    through JSON, and a scene diff between two identical runs is a defect
    report nobody can read.
    """
    f = float(v)
    if f == int(f) and abs(f) < 1e15:
        return str(int(f))
    return f"{f:.4f}".rstrip("0").rstrip(".")


def scene_text(report: dict) -> str:
    """`occluders.tscn` for a bake report -- deterministic, shapes shared.

    Sub-resource ids are `BoxOccluder3D_<n>` over the sizes in first-seen
    order, so the file is a function of the report and of nothing else.
    """
    modules = report.get("modules") or []
    shapes: dict[tuple, int] = {}
    for m in modules:
        key = tuple(_fmt(x) for x in m["size"])
        if key not in shapes:
            shapes[key] = len(shapes)

    out = [f"[gd_scene load_steps={len(shapes) + 1} format=3]", ""]
    for key, idx in shapes.items():
        out.append(f'[sub_resource type="BoxOccluder3D" id="BoxOccluder3D_{idx}"]')
        out.append(f"size = Vector3({key[0]}, {key[1]}, {key[2]})")
        out.append("")
    out.append(f'[node name="{HOLDER_NODE}" type="Node3D"]')
    out.append("")
    for i, m in enumerate(modules):
        key = tuple(_fmt(x) for x in m["size"])
        b = [_fmt(x) for x in m["basis"]]
        o = [_fmt(x) for x in m["origin"]]
        out.append(f'[node name="occ_{i:04d}" type="OccluderInstance3D" '
                   f'parent="."]')
        out.append("transform = Transform3D("
                   + ", ".join(b + o) + ")")
        out.append(f'occluder = SubResource("BoxOccluder3D_{shapes[key]}")')
        out.append("")
    return "\n".join(out)


def wire_into_scene(scene_path: Path) -> bool:
    """Instance `occluders.tscn` from `site.tscn`. True if it changed the file.

    Idempotent by the holder node's name: a package that already carries the
    branch is left alone rather than given a second one, because the export
    is re-runnable and two sets of occluders is twice the raster cost for
    nothing.
    """
    scene_path = Path(scene_path)
    text = scene_path.read_text(encoding="utf-8")
    if f'[node name="{HOLDER_NODE}" parent="."' in text:
        return False

    ext = (f'[ext_resource type="PackedScene" path="res://{OCCLUDER_SCENE}" '
           f'id="{_EXT_ID}"]')
    lines = text.splitlines()

    # After the last ext_resource, which is where a .tscn keeps them. A scene
    # with none is not one of ours and is refused rather than guessed at.
    last_ext = max((i for i, ln in enumerate(lines)
                    if ln.startswith("[ext_resource ")), default=-1)
    if last_ext < 0:
        raise OccluderError(
            f"{scene_path.name} has no ext_resource block to extend")
    lines.insert(last_ext + 1, ext)

    lines.append("")
    lines.append(f'[node name="{HOLDER_NODE}" parent="." '
                 f'instance=ExtResource("{_EXT_ID}")]')
    scene_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return True


#: `occlusion_culling/use_occlusion_culling=true`, tolerant of spacing.
_OCC_SETTING = re.compile(
    r"^\s*" + re.escape(OCCLUSION_KEY) + r"\s*=\s*(\S+)\s*$", re.M)


class OccluderDisagreement(RuntimeError):
    """The culling flag and the occluders in the package do not agree."""


def audit(export_dir: Path) -> dict:
    """What the package ACTUALLY ships, read back off disk. Raises on a lie.

    THE STATE THIS EXISTS TO MAKE IMPOSSIBLE is the one cold run 9065 shipped:
    `use_occlusion_culling=true` and zero `OccluderInstance3D` anywhere in the
    package. The export printed a warning, exited 0, and the package went out
    with the culler's per-frame cost and nothing for it to reject -- the flag
    on, the culling absent, which is worse than neither.

    The other direction is a defect too and is checked with the same breath:
    occluders in the package with the culler off is 414 nodes of software
    rasteriser input that the engine will never consult.

    Counts NODES IN THE SHIPPED SCENES, not the bake report. The report says
    what the bake measured; this says what a recipient will load, and the gap
    between those two is exactly where 9065 lived. `occluders.json` is read
    only to report whether the bake said it succeeded -- never to decide.
    """
    export_dir = Path(export_dir)
    proj = export_dir / "project.godot"
    if not proj.is_file():
        raise OccluderDisagreement(f"no project.godot in {export_dir}")
    hits = _OCC_SETTING.findall(proj.read_text(encoding="utf-8"))
    if len(hits) != 1:
        raise OccluderDisagreement(
            f"project.godot carries {len(hits)} `{OCCLUSION_KEY}` lines, "
            "expected exactly 1 -- the package makes no single statement "
            "about occlusion culling")
    flag = hits[0].strip().lower() == "true"

    nodes = 0
    scenes = 0
    for tscn in sorted(export_dir.rglob("*.tscn")):
        if CACHE_DIR in tscn.parts:
            continue
        try:
            text = tscn.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        n = text.count('type="OccluderInstance3D"')
        if n:
            scenes += 1
        nodes += n

    report_ok = None
    report = export_dir / REPORT_NAME
    if report.is_file():
        try:
            report_ok = bool(json.loads(
                report.read_text(encoding="utf-8")).get("ok"))
        except (OSError, ValueError):
            report_ok = None

    out = {"use_occlusion_culling": flag, "occluder_nodes": nodes,
           "scenes_with_occluders": scenes, "bake_reported_ok": report_ok}
    if flag and nodes == 0:
        raise OccluderDisagreement(
            "use_occlusion_culling=true and 0 OccluderInstance3D nodes in the "
            "package: the culler is switched on with nothing to cull. "
            f"occluders.json ok={report_ok}. This is cold run 9065's state.")
    if nodes and not flag:
        raise OccluderDisagreement(
            f"{nodes} OccluderInstance3D node(s) in the package and "
            "use_occlusion_culling is not true: they will never be consulted.")
    return out


def emit(export_dir: Path, godot_executable, *,
         scene_name: str = "site.tscn") -> dict:
    """Measure, write `occluders.tscn`, and wire it into the site scene.

    Returns the report with `occluder_scene` and `wired` added. Raises
    `OccluderError` when the bake cannot be trusted -- the caller decides
    whether that fails the export or is reported and survived.
    """
    export_dir = Path(export_dir)
    site = export_dir / scene_name
    if not site.is_file():
        raise OccluderError(f"no {scene_name} in {export_dir}")
    report = measure(export_dir, godot_executable,
                     scene=f"res://{scene_name}")
    if int(report.get("occluders") or 0) == 0:
        # NOTHING TO HIDE IS NOT A FAILURE, and it is not a reason to ship an
        # empty branch either. A package with no solid modules in it gets no
        # `occluders.tscn` and no holder node: an instanced scene of nothing
        # is one more node for the tree to carry and one more file in the
        # resource manifest, and the export then writes the culling flag off
        # to match. The bake SUCCEEDED and the report says so.
        report["occluder_scene"] = None
        report["wired"] = False
    else:
        (export_dir / OCCLUDER_SCENE).write_text(
            scene_text(report), encoding="utf-8")
        report["occluder_scene"] = OCCLUDER_SCENE
        report["wired"] = wire_into_scene(site)
    (export_dir / REPORT_NAME).write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report
