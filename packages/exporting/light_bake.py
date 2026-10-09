"""Bake a package's steady lights into a lightmap (roadmap item 31).

THE PRICE IT PAYS FOR. The light-bake probe (`docs/findings/light_bake/
NOTES.md` at the factory root) baked the gas station lot's steady lights and
measured it on the fixed-station harness, quiet machine, GL Compatibility,
the baked and unbaked packages alternated twice: -0.8 ms median frame
(-16 %), -0.45 ms GPU, controls 0.04-0.10 ms, the heaviest views ~3 ms
faster, no view slower by more than 0.3 ms. Draw calls fall 13 % on average:
a static light no longer adds a pass on the surfaces the lightmap covers.

WHAT A BAKE NEEDS, AND WHO SUPPLIES IT:

  * a SECOND UV SET on every static surface. Deli Counter's shells and most
    of Zoo's props carry none; Godot unwraps one on import when the model's
    sidecar says `meshes/light_baking=2` (Static Lightmaps). A model that
    ALREADY carries TEXCOORD_1 is left alone: those are the moving and
    flickering props (turn pivots, slush churn, crown sway, screen shutter
    schedules), whose second UV set is data their shader reads. The ground,
    roads and walks are inline primitive meshes, which unwrap themselves
    with `add_uv2`. The unwrap is deterministic: the probe's digest of 1,603
    surfaces' UV2 was identical as baked, after a fresh import, and after a
    second one -- so a recipient's import lands the lightmap where it was
    baked.
  * the steady lights marked STATIC: every Lux rig in the presentation scene
    whose resource carries no `failing_kind` gets `bake_mode = 1`. A failing
    fixture (a stuttering tube, a cycling pole, a wavering bulb) stays live,
    and so does a rig a CYCLING node uses -- a club's stage (0.160.0).
  * a BAKE, which Godot 4.7 exposes to no script (`LightmapGI` has settings
    and no `bake()`; godot-proposals #8656 is open). So the package is copied
    to a Forward+ working copy -- only a RenderingDevice can bake -- with an
    editor plugin (`assets/godot/light_bake_plugin.gd`) that opens
    `bake.tscn`, presses the editor's own Bake Lightmaps button, answers the
    one dialog that follows, saves and quits. It needs a GPU and a display;
    the editor window shows for about a minute. Bounded, and the process tree
    is killed on the bound.

THE ROOMS' FLOOR (0.151.0). A lightmapped surface takes its light from the
lightmap alone, so a room probe's ambient -- the floor Lux puts under a
room's fixtures -- stopped reaching any wall or floor when this bake
shipped, and a corner no lamp reaches baked to black
(`docs/findings/night_interiors/` at the factory root). The plugin asks the
level's Lux (>= 0.68.0) to lay bake-only fills over its room probes before
Bake is pressed and frees them before the save: the lightmap holds their
light and the package carries no fill. `room_fills` in the report counts
them; -1 means the level's Lux lays none.

WHAT SHIPS. `bake.tscn` at the package root (the presentation scene and its
`LightmapGI`), `bake.lmbake`, `bake.exr` and the texture's sidecar, the
presentation scene's steady rigs static, and `mission.tscn` instancing
`bake.tscn` in place of the presentation scene. Lux 0.66.0 binds the
lightmap at load and switches it with the level's state (the power cut, a
preset other than the baked one). A bake that fails, for any reason,
restores the presentation scene and the entry and ships the package unbaked;
the UV2 import settings stay, since a second UV set changes nothing without
a lightmap. `light_bake.json` says which.
"""
from __future__ import annotations

import json
import re
import shutil
import struct
import subprocess
import sys
import time
from pathlib import Path

_LF_ROOT = Path(__file__).resolve().parents[2]
PLUGIN_SCRIPT = _LF_ROOT / "assets" / "godot" / "light_bake_plugin.gd"

PRESENTATION = "presentation/lux.applied.tscn"
BAKE_SCENE = "bake.tscn"
BAKE_FILES = ("bake.tscn", "bake.lmbake", "bake.exr", "bake.exr.import")
REPORT = "light_bake.json"
PLUGIN_DIR = "addons/lf_light_bake"
RESULT = "light_bake_result.json"

#: The probe's settings: quality Low (0) baked the lot in 22 s and is what
#: was priced; two bounces; a 4096 ceiling on one lightmap layer.
QUALITY = 0
BOUNCES = 2
MAX_TEXTURE = 4096
#: The editor's bound, seconds: the lot baked in 22 s and the editor's own
#: start and import took ~35 more.
EDITOR_TIMEOUT_S = 900
IMPORT_TIMEOUT_S = 1800

LIGHT_BAKING = "meshes/light_baking"
STATIC_LIGHTMAPS = 2
#: `meshes/light_baking` Dynamic (0.162.1). A model the gameplay layer spawns
#: is never in the bake, so its light has to come from the `LightmapGI`'s
#: probes, which only a GI_MODE_DYNAMIC mesh samples. Measured 2026-10-08 on
#: Godot 4.7, the responders' cruiser imported at 2 gave its five meshes
#: gi_mode STATIC, and at 3 gi_mode DYNAMIC (cold run 9208's notes at the
#: factory root).
DYNAMIC = 3
PRIMITIVES = ("BoxMesh", "QuadMesh", "PlaneMesh", "CylinderMesh", "PrismMesh")

BAKE_TSCN = """[gd_scene load_steps=2 format=3]

[ext_resource type="PackedScene" path="res://{presentation}" id="site"]

[node name="Bake" type="Node3D"]

[node name="Site" parent="." instance=ExtResource("site")]

[node name="Lightmap" type="LightmapGI" parent="."]
quality = {quality}
bounces = {bounces}
directional = false
use_denoiser = true
max_texture_size = {max_texture}
environment_mode = 0
"""


def glb_has_uv2(path: Path) -> bool:
    """Whether any primitive in a .glb carries TEXCOORD_1."""
    raw = Path(path).read_bytes()
    if len(raw) < 20:
        return False
    n = struct.unpack("<I", raw[12:16])[0]
    doc = json.loads(raw[20:20 + n])
    return any("TEXCOORD_1" in p.get("attributes", {})
               for m in doc.get("meshes", []) for p in m.get("primitives", []))


def mark_imports(export_dir: Path, spawned=()) -> dict:
    """Static Lightmaps on every model's sidecar but those whose own second
    UV set is shader data. ``{"baked": [...], "dynamic": [...], ...}``,
    package-relative paths. A sidecar with no `meshes/light_baking` line is
    an import Godot has not written yet, and is said rather than guessed.

    ``spawned`` (0.162.1): the package-relative paths of models the gameplay
    layer spawns -- the responders' car. Each is set to `DYNAMIC` and listed
    under ``spawned``, ahead of the second-UV test; a path with no sidecar is
    listed under ``spawned_unmatched``. 0.162.0 baked the car's import static
    like any prop, and a spawned one would have had neither the lightmap nor
    the probes."""
    out = {"baked": [], "dynamic": [], "spawned": [], "spawned_unmatched": [], "unreadable": []}
    wanted = set(spawned)
    for sidecar in sorted(Path(export_dir).rglob("*.glb.import")):
        if ".godot" in sidecar.parts:
            continue
        glb = sidecar.with_suffix("")
        rel = glb.relative_to(export_dir).as_posix()
        if rel in wanted:
            value, bucket = DYNAMIC, "spawned"
        elif glb_has_uv2(glb):
            out["dynamic"].append(rel)
            continue
        else:
            value, bucket = STATIC_LIGHTMAPS, "baked"
        text = sidecar.read_text(encoding="utf-8")
        new, k = re.subn(rf"^{re.escape(LIGHT_BAKING)}=\d+$", f"{LIGHT_BAKING}={value}",
                         text, flags=re.M)
        if k != 1:
            out["unreadable"].append(rel)
            continue
        if new != text:
            sidecar.write_text(new, encoding="utf-8", newline="\n")
        out[bucket].append(rel)
    out["spawned_unmatched"] = sorted(wanted - set(out["spawned"]) - set(out["unreadable"]))
    return out


def add_primitive_uv2(export_dir: Path) -> dict:
    """`add_uv2 = true` on every inline primitive mesh in the package's
    scenes. ``{scene: count}``."""
    out = {}
    pat = re.compile(r'^\[sub_resource type="(?:%s)" id="[^"]*"\]$' % "|".join(PRIMITIVES), re.M)
    for scene in sorted(Path(export_dir).rglob("*.tscn")):
        if ".godot" in scene.parts or scene.name == BAKE_SCENE:
            continue
        text = scene.read_text(encoding="utf-8")
        count = 0

        def add(m):
            nonlocal count
            count += 1
            return m.group(0) + "\nadd_uv2 = true"
        # a scene this already touched is left as it is
        if "add_uv2 = true" in text:
            continue
        new = pat.sub(add, text)
        if count:
            scene.write_text(new, encoding="utf-8", newline="\n")
            out[scene.relative_to(export_dir).as_posix()] = count
    return out


def _cycling_rigs(blocks: list) -> set:
    """The rig resource ids a CYCLING node uses (0.160.0, roadmap 213): a node
    whose `cycle_period_s` is over 0 across two or more `colors` --
    `LuxStageLightRig._cycles()`'s own test, read off the scene text. The
    cycle is the node's and the bake mode is the resource's, so this is the
    only place the two meet."""
    out = set()
    for b in blocks:
        if not b.startswith("[node "):
            continue
        rig = re.search(r'^rig = SubResource\("([^"]+)"\)$', b, flags=re.M)
        period = re.search(r"^cycle_period_s = ([0-9.eE+-]+)$", b, flags=re.M)
        colors = re.search(r"^colors = PackedColorArray\(([^)]*)\)$", b, flags=re.M)
        if not (rig and period and colors):
            continue
        n_colors = len([v for v in colors.group(1).split(",") if v.strip()]) // 4
        if float(period.group(1)) > 0.0 and n_colors > 1:
            out.add(rig.group(1))
    return out


def mark_steady_rigs(scene: Path) -> dict:
    """`bake_mode = 1` on every Lux rig resource in `scene` that carries no
    `failing_kind` and no cycling node uses (`_cycling_rigs`, 0.160.0).
    ``{"static": n, "live": n, "cycling": n}`` -- `live` the failing ones.
    A resource a cycling node uses is left as Lux wrote it: baked, a stage
    rig stops cycling. Refuses a scene with no rig script, which is a scene
    this does not understand."""
    text = Path(scene).read_text(encoding="utf-8")
    m = re.search(r'\[ext_resource type="Script" (?:uid="[^"]*" )?path="res://[^"]*lux_light_rig\.gd" id="([^"]+)"\]', text)
    if m is None:
        raise ValueError(f"{scene}: no lux_light_rig.gd script resource")
    rig = m.group(1)
    blocks = re.split(r"(?=^\[)", text, flags=re.M)
    cycling_ids = _cycling_rigs(blocks)
    static = live = cycling = 0
    for i, b in enumerate(blocks):
        if not b.startswith('[sub_resource type="Resource"') or f'script = ExtResource("{rig}")' not in b:
            continue
        if re.search(r"^failing_kind = [1-9]", b, flags=re.M):
            live += 1
            continue
        rid = re.match(r'\[sub_resource type="Resource" id="([^"]+)"\]', b)
        if rid and rid.group(1) in cycling_ids:
            cycling += 1
            continue
        if re.search(r"^bake_mode = ", b, flags=re.M):
            blocks[i] = re.sub(r"^bake_mode = \d+$", "bake_mode = 1", b, flags=re.M)
        else:
            blocks[i] = b.replace(f'script = ExtResource("{rig}")\n',
                                  f'script = ExtResource("{rig}")\nbake_mode = 1\n', 1)
        static += 1
    Path(scene).write_text("".join(blocks), encoding="utf-8", newline="\n")
    return {"static": static, "live": live, "cycling": cycling}


def bake_scene_text() -> str:
    return BAKE_TSCN.format(presentation=PRESENTATION, quality=QUALITY, bounces=BOUNCES,
                            max_texture=MAX_TEXTURE)


def retarget_entry(export_dir: Path, to: str) -> bool:
    """Point the mission entry's instance of the presentation scene at `to`.
    True when it changed."""
    entry = Path(export_dir) / "mission.tscn"
    text = entry.read_text(encoding="utf-8")
    old_pres, old_bake = f"load('res://{PRESENTATION}')", f"load('res://{BAKE_SCENE}')"
    new_ref = f"load('res://{to}')"
    for old in (old_pres, old_bake):
        if text.count(old) == 1 and old != new_ref:
            entry.write_text(text.replace(old, new_ref), encoding="utf-8", newline="\n")
            return True
    return False


def strip_uids(scene: Path) -> int:
    """Drop `uid="..."` from a scene's ext_resources: the package ships
    paths (its sidecar policy, `export._write_import_sidecars`), and a
    recipient's import regenerates every uid."""
    text = Path(scene).read_text(encoding="utf-8")
    new, k = re.subn(r'(\[ext_resource [^\]]*?) uid="uid://[^"]*"', r"\1", text)
    if k:
        Path(scene).write_text(new, encoding="utf-8", newline="\n")
    return k


def _forward_plus(project_godot: Path) -> None:
    """The working copy's renderer: Forward+, and the bake plugin enabled."""
    text = project_godot.read_text(encoding="utf-8")
    text = re.sub(r"^renderer/rendering_method=.*\n", "", text, flags=re.M)
    text, k = re.subn(r"^\[rendering\]\n", '[rendering]\nrenderer/rendering_method="forward_plus"\n',
                      text, flags=re.M)
    if k != 1:
        text += '\n[rendering]\nrenderer/rendering_method="forward_plus"\n'
    text += f'\n[editor_plugins]\n\nenabled=PackedStringArray("res://{PLUGIN_DIR}/plugin.cfg")\n'
    project_godot.write_text(text, encoding="utf-8", newline="\n")


def _run(cmd, timeout):
    """Run, bounded; on the bound kill the process TREE (the console
    launcher's engine is a grandchild). ``(returncode or None, seconds)``."""
    t0 = time.time()
    p = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        p.wait(timeout=timeout)
        return p.returncode, time.time() - t0
    except subprocess.TimeoutExpired:
        if sys.platform.startswith("win"):
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(p.pid)], capture_output=True)
        else:
            p.kill()
        return None, time.time() - t0


def _import(export_dir: Path, godot) -> bool:
    try:
        subprocess.run([str(godot), "--headless", "--path", str(export_dir), "--import"],
                       capture_output=True, text=True, timeout=IMPORT_TIMEOUT_S)
        return True
    except (OSError, subprocess.SubprocessError):
        return False


def bake(export_dir, godot_executable, *, log=print, spawned=()) -> dict:
    """Bake `export_dir`'s steady lights; see the module docstring. Returns
    the report it also writes to `light_bake.json`."""
    export_dir = Path(export_dir)
    report = {"ok": False}
    pres = export_dir / PRESENTATION
    if not godot_executable:
        report["reason"] = "no Godot executable: nothing could be baked"
    elif not pres.exists():
        report["reason"] = f"no {PRESENTATION}: no lights to bake"
    if "reason" in report:
        (export_dir / REPORT).write_text(json.dumps(report, indent=1), encoding="utf-8")
        return report
    keep_pres = pres.read_bytes()
    keep_entry = (export_dir / "mission.tscn").read_bytes()
    work = export_dir.parent / (export_dir.name + ".lightbake")
    try:
        report["imports"] = mark_imports(export_dir, spawned)
        report["primitives"] = add_primitive_uv2(export_dir)
        report["rigs"] = mark_steady_rigs(pres)
        (export_dir / BAKE_SCENE).write_text(bake_scene_text(), encoding="utf-8", newline="\n")
        if not _import(export_dir, godot_executable):
            raise RuntimeError("the UV2 import pass did not run")
        if work.exists():
            shutil.rmtree(work)
        shutil.copytree(export_dir, work)
        _forward_plus(work / "project.godot")
        plugin = work / PLUGIN_DIR
        plugin.mkdir(parents=True, exist_ok=True)
        shutil.copy(PLUGIN_SCRIPT, plugin / "light_bake_plugin.gd")
        (plugin / "plugin.cfg").write_text(
            '[plugin]\n\nname="lf_light_bake"\ndescription="Bakes bake.tscn and quits."\n'
            'author="level_factory"\nversion="1"\nscript="light_bake_plugin.gd"\n',
            encoding="utf-8", newline="\n")
        code, took = _run([str(godot_executable), "--editor", "--path", str(work),
                           "--resolution", "1280x720"], EDITOR_TIMEOUT_S)
        report["editor_s"] = round(took, 1)
        result_p = work / RESULT
        result = json.loads(result_p.read_text(encoding="utf-8")) if result_p.exists() else None
        report["result"] = result
        report["room_fills"] = (result or {}).get("room_fills")
        if code is None:
            raise RuntimeError(f"the editor did not finish in {EDITOR_TIMEOUT_S} s")
        if not result or not result.get("ok"):
            raise RuntimeError("the bake did not complete: %s" % (result or "no result written"))
        for f in BAKE_FILES:
            src = work / f
            if not src.exists():
                raise RuntimeError(f"the bake wrote no {f}")
            shutil.copy(src, export_dir / f)
        report["uids_stripped"] = strip_uids(export_dir / BAKE_SCENE)
        if not retarget_entry(export_dir, BAKE_SCENE):
            raise RuntimeError("mission.tscn does not instance the presentation scene")
        _import(export_dir, godot_executable)
        report["ok"] = True
        fills = report["room_fills"]
        log("[export] light bake: %d model(s) and %d primitive mesh(es) lightmapped, %d kept dynamic, "
            "%d spawned set dynamic; "
            "%d steady rig(s) baked, %d failing and %d cycling left live; %s; %d users, %s s in the editor"
            % (len(report["imports"]["baked"]), sum(report["primitives"].values()),
               len(report["imports"]["dynamic"]), len(report["imports"]["spawned"]),
               report["rigs"]["static"], report["rigs"]["live"],
               report["rigs"]["cycling"],
               "no room floor (the level's Lux lays none)" if fills in (None, -1)
               else "%d room fill(s)" % fills,
               result.get("users"), report["editor_s"]))
    except Exception as exc:  # any failure ships the package unbaked
        pres.write_bytes(keep_pres)
        (export_dir / "mission.tscn").write_bytes(keep_entry)
        for f in BAKE_FILES:
            (export_dir / f).unlink(missing_ok=True)
        report["ok"] = False
        report["reason"] = str(exc)
        log("[export] WARNING light bake failed, the package ships unbaked: %s" % exc)
    finally:
        if work.exists():
            shutil.rmtree(work, ignore_errors=True)
    (export_dir / REPORT).write_text(json.dumps(report, indent=1), encoding="utf-8")
    return report
