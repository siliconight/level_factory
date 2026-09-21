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
import subprocess
from pathlib import Path

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
    (export_dir / OCCLUDER_SCENE).write_text(
        scene_text(report), encoding="utf-8")
    report["occluder_scene"] = OCCLUDER_SCENE
    report["wired"] = wire_into_scene(site)
    (export_dir / REPORT_NAME).write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report
