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
import os
import re
import shutil
import struct
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
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
#: Tries at the bake, each on a fresh work copy (0.178.6). Cold run 9243's bake opened the
#: scene, baked, and read its lightmap image back EMPTY (`src_image_len == 0`, "Failed
#: creating lightmap images"); the same package baked on the next try. Driving an editor's
#: GUI is not deterministic, and one more try costs one more editor minute on a failure.
BAKE_ATTEMPTS = 2

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

#: THE SKY IS IN THE BAKE (0.164.0), the walker's call on 2026-10-09: "yes
#: bake the sky in". `environment_mode = 1` gathers the scene's environment
#: -- the WorldEnvironment LuxRoot builds, in the editor too, since it is
#: `@tool` -- wherever the sky can reach. 0.131.0 shipped `0`, no sky, with
#: no reason recorded, and a lightmapped surface takes no ambient at run
#: time, so no baked surface had ever received sky light. Measured by
#: re-baking cold run 9214's level slot by slot
#: (`docs/findings/lighting_spec_vs_lux/` at the factory root): a clear
#: afternoon's street cameras +15.1 and +21.4, shade from near black to
#: daylight; Heavy Rain +0.3 to +2.3 and Blue Hour +0.5 to +3.7 outside;
#: Delco Night two outer facades +3.3 and +4.4, the rest 0.2 or less; every
#: room 1.2 or less at every slot, so a sealed room takes none. The bake
#: time did not move, and at run time it costs nothing: the light lives in
#: the lightmap. The root's `tools/lux_rebake.py --bake-environment none`
#: bakes as before, and reads this line, so it stays one literal line.
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
environment_mode = 1
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


#: OBJs a site ships that are NOT lit by the bake (0.194.0): Lot 0.119.0's
#: overhead wires, `site_wires_*.obj`, unshaded tubes whose nodes take no GI
#: (`gi_mode = 0`) -- a 2 cm wire unwrapped into the lightmap would spend its
#: texels on nothing a player sees lit, and its import would make a second UV
#: for nothing. `mark_imports` lists them under `unlit` and leaves their
#: sidecars as the engine wrote them.
UNLIT_PREFIXES = ("site_wires_",)


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
    out = {"baked": [], "dynamic": [], "spawned": [], "spawned_unmatched": [], "unreadable": [],
           "unlit": []}
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
    # THE PAINT'S MESHES (0.177.1, roadmap 231): Lot 0.114.0 ships a site's road
    # markings as an OBJ per paint colour beside site.tscn, so that 227 marking
    # submissions are two and the bake still lights them. The wavefront
    # importer generates no lightmap UV unless asked -- `generate_lightmap_uv2`,
    # read off the engine's own sidecar from a one-quad import -- so each
    # sidecar is asked here and the mesh bakes like a model.
    for sidecar in sorted(Path(export_dir).rglob("*.obj.import")):
        if ".godot" in sidecar.parts:
            continue
        rel = sidecar.with_suffix("").relative_to(export_dir).as_posix()
        if sidecar.name.startswith(UNLIT_PREFIXES):
            out["unlit"].append(rel)
            continue
        text = sidecar.read_text(encoding="utf-8")
        new, k = re.subn(r"^generate_lightmap_uv2=(?:true|false)$",
                         "generate_lightmap_uv2=true", text, flags=re.M)
        if k != 1:
            out["unreadable"].append(rel)
            continue
        if new != text:
            sidecar.write_text(new, encoding="utf-8", newline="\n")
        out["baked"].append(rel)
    out["spawned_unmatched"] = sorted(wanted - set(out["spawned"]) - set(out["unreadable"]))
    return out


def add_primitive_uv2(export_dir: Path, only=None) -> dict:
    """`add_uv2 = true` on every inline primitive mesh in the package's
    scenes. ``{scene: count}``.

    ONLY WHAT THE BAKE DRAWS (0.212.0, the factory's roadmap 251). The
    export passes `only=baked_scenes(export_dir)`. This wrote every scene,
    and the log summed every count as "lightmapped": cold run 9308's 225 was
    the presentation's 112, the content scene's same 112 again, and the
    backdrop's ground, which no bake draws. `only=None` is every scene, as
    before."""
    out = {}
    keep = None if only is None else set(only)
    pat = re.compile(r'^\[sub_resource type="(?:%s)" id="[^"]*"\]$' % "|".join(PRIMITIVES), re.M)
    for scene in sorted(Path(export_dir).rglob("*.tscn")):
        if ".godot" in scene.parts or scene.name == BAKE_SCENE:
            continue
        if keep is not None and scene.relative_to(export_dir).as_posix() not in keep:
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


_PACKED = re.compile(r'^\[ext_resource type="PackedScene"[^\]\n]*\bpath="res://([^"]+\.tscn)"', re.M)


def baked_scenes(export_dir: Path) -> list:
    """The scenes the bake draws, package-relative and sorted: the
    presentation scene `bake.tscn` instances (`bake_scene_text`) and every
    scene it instances, transitively. The content scene `site.tscn`, which
    the presentation was applied from, and `site_backdrop.tscn`, which
    `mission.tscn` loads at run time, are not among them (0.212.0)."""
    export_dir = Path(export_dir)
    seen, todo = set(), [PRESENTATION]
    while todo:
        rel = todo.pop()
        p = export_dir / rel
        if rel in seen or not p.is_file():
            continue
        seen.add(rel)
        todo.extend(_PACKED.findall(p.read_text(encoding="utf-8")))
    return sorted(seen)


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


def _run(cmd, timeout, log_path=None):
    """Run, bounded; on the bound kill the process TREE (the console
    launcher's engine is a grandchild). ``(returncode or None, seconds)``.

    ``log_path`` keeps the process's output (0.178.5). Cold run 9242's bake
    failed with this sending it to DEVNULL, and only a re-run that kept it
    could say why."""
    t0 = time.time()
    out = open(log_path, "wb") if log_path else subprocess.DEVNULL
    try:
        p = subprocess.Popen(cmd, stdout=out, stderr=subprocess.STDOUT if log_path
                             else subprocess.DEVNULL)
    except Exception:
        if log_path:
            out.close()
        raise
    try:
        p.wait(timeout=timeout)
        return p.returncode, time.time() - t0
    except subprocess.TimeoutExpired:
        if sys.platform.startswith("win"):
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(p.pid)], capture_output=True)
        else:
            p.kill()
        return None, time.time() - t0
    finally:
        if log_path:
            out.close()


def _copy_lightmap_import(work: Path, export_dir: Path) -> list:
    """THE EDITOR'S IMPORT OF THE LIGHTMAP, KEPT (0.183.0, factory roadmap 239).

    The editor that bakes imports what it baked: `bake.exr`, a 1024 x 1024
    texture array of 16 slices, VRAM-compressed (BPTC) as its sidecar says.
    The package then imported the same bytes again, and measured on cold run
    9248's export that second `--import` imported that one file and nothing
    else, in 49.5 s. This copies the work copy's cache entries for it into the
    package's cache beside the sidecar `BAKE_FILES` already copies, so the
    import after finds them current: an entry is named for the file's
    `res://` path and checked against its source's hash and its parameters,
    all three the same files in both projects. Returns the names copied;
    none when either cache is missing, and the import after does the work
    as it always did."""
    src = Path(work) / ".godot" / "imported"
    dst = Path(export_dir) / ".godot" / "imported"
    if not src.is_dir() or not dst.is_dir():
        return []
    copied = []
    for name in BAKE_FILES:
        if not name.endswith(".exr"):
            continue
        for p in sorted(src.glob(name + "-*")):
            shutil.copy2(p, dst / p.name)
            copied.append(p.name)
    return copied


#: Threads copying the package into the bake's work copy (0.193.0).
COPY_WORKERS = 8


def _copy_project(src: Path, dst: Path) -> int:
    """`shutil.copytree(src, dst)` for a package: its directories first, then
    its files by `shutil.copy2` across COPY_WORKERS threads. Returns how many
    files it copied.

    THE WORK COPY, ABOUT 5 SECONDS (0.193.0). The bake copies the package and
    its import cache before the editor opens it -- cold run 9258's, 6,058 files
    and 252 MB: `copytree`, a file after a file, 4.7 and 5.3 s; this, 2.1 and
    2.0 s, the same files. A package is directories and files and nothing else
    (`os.walk` does not follow a link to a directory, so one would not be
    copied); a file that fails to copy raises here, as it does in `copytree`.
    """
    src, dst = Path(src), Path(dst)
    jobs = []
    for root, _dirs, files in os.walk(src):
        rel = os.path.relpath(root, src)
        target = dst if rel == "." else dst / rel
        target.mkdir(parents=True, exist_ok=True)
        for f in files:
            jobs.append((Path(root) / f, target / f))
    with ThreadPoolExecutor(COPY_WORKERS) as pool:
        list(pool.map(lambda job: shutil.copy2(job[0], job[1]), jobs))
    return len(jobs)


def _remove_later(work: Path):
    """Remove the bake's work copy while the export goes on (0.193.0).

    Removing it took 2.1 to 2.8 s, after the bake and before anything else in
    the export could start. It is renamed aside, which is immediate, and
    removed by a thread the interpreter waits for at its exit, so the export's
    process still leaves nothing behind it. A copy left aside by an earlier
    export is removed first; a rename that fails removes the copy here, as
    before. Returns the thread, or None when there is none."""
    work = Path(work)
    trash = work.with_name(work.name + ".old")
    if trash.exists():
        shutil.rmtree(trash, ignore_errors=True)
    try:
        work.rename(trash)
    except OSError:
        shutil.rmtree(work, ignore_errors=True)
        return None
    t = threading.Thread(target=shutil.rmtree, args=(trash,), kwargs={"ignore_errors": True},
                         name="light-bake-work-copy")
    t.start()
    return t


def _import(export_dir: Path, godot) -> bool:
    try:
        subprocess.run([str(godot), "--headless", "--path", str(export_dir), "--import"],
                       capture_output=True, text=True, timeout=IMPORT_TIMEOUT_S)
        return True
    except (OSError, subprocess.SubprocessError):
        return False


#: Where an editor keeps the groups of every scene it has read (0.191.0).
SCENE_GROUPS_CACHE = ".godot/scene_groups_cache.cfg"
_NODE_HEAD = re.compile(r'^\[node [^\n]*\]$', re.M)
_GROUPS = re.compile(r'\bgroups=\[([^\]]*)\]')
_GROUP_NAME = re.compile(r'&?"((?:[^"\\]|\\.)*)"')


def scene_groups(text: str) -> list:
    """Every group a scene's nodes are put in, in the order each first appears:
    the `groups=[...]` of its `[node ...]` headers, `"name"` or `&"name"`."""
    out = []
    for head in _NODE_HEAD.finditer(text):
        m = _GROUPS.search(head.group(0))
        if m:
            for name in _GROUP_NAME.findall(m.group(1)):
                if name not in out:
                    out.append(name)
    return out


def write_scene_groups_cache(export_dir: Path) -> int:
    """The scene groups cache the bake's editor would otherwise build first (0.191.0).

    TWENTY SECONDS OF THE BAKE'S EDITOR. The export's headless imports write
    no `scene_groups_cache.cfg`, and a Godot 4.7 editor opened on a project
    whose `.godot` has none starts by reading every scene's groups: cold run
    9256's bake editor, run again with `--verbose`, loaded each of the
    package's 482 models and their textures, its file system saying it was
    scanning all the while, before the plugin could ask for the bake scene
    (the factory's `docs/findings/grader_speed/bake_phases_probe.py`).
    Re-exporting 9256 with a cache an editor had written for the same scenes
    put in the work copy, the file system had stopped scanning by the first
    sample, the editor asked for the scene at 13.1 s where it had asked at
    32.4 and took 68.0 s in all where it had taken 88.0; it opened the scene
    (14.5 s, 14.7 s) and baked it (35.1 s, 35.7 s) in the same time.

    The cache is the groups of each scene that has any, read off the scenes'
    own `[node ...]` headers (`scene_groups`). On 9256's 22 scenes that is the
    editor's own cache: the same three scenes -- the `site.tscn` of
    `lot/deli_a01`, `lot/office` and `lot/pharmacy_a01` -- with the same
    groups. A scene with none is not listed, as the editor lists none. Written
    into the package's `.godot`, so the work copy starts with it and
    `occluders.keep_cache` takes it, with the rest of that directory, to the
    walk copy. Returns how many scenes it lists.
    """
    export_dir = Path(export_dir)
    rows = []
    for scene in sorted(export_dir.rglob("*.tscn")):
        if ".godot" in scene.parts:
            continue
        try:
            groups = scene_groups(scene.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
        if groups:
            rows.append((scene.relative_to(export_dir).as_posix(), groups))
    path = export_dir / SCENE_GROUPS_CACHE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(
        '[res://%s]\n\ngroups=[%s]\n' % (rel, ", ".join('&"%s"' % g for g in groups))
        for rel, groups in rows), encoding="utf-8", newline="\n")
    return len(rows)


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
        report["primitives"] = add_primitive_uv2(export_dir, only=baked_scenes(export_dir))
        report["rigs"] = mark_steady_rigs(pres)
        (export_dir / BAKE_SCENE).write_text(bake_scene_text(), encoding="utf-8", newline="\n")
        # Since 0.187.0 the export writes these marks before its second import
        # pass, so this one finds nothing left to import (5.0 s where it took
        # 55.0, cold run 9252's package re-exported). It stays: the net for a
        # caller that did not, and for any sidecar changed above.
        if not _import(export_dir, godot_executable):
            raise RuntimeError("the UV2 import pass did not run")
        # the groups the editor would load every scene to read before it could
        # open one (0.191.0), written where the work copy takes them from
        report["scene_groups_cached"] = write_scene_groups_cache(export_dir)
        # 0.178.6: up to BAKE_ATTEMPTS tries, each on a fresh copy, each editor's log kept
        attempts = []
        for attempt in range(1, BAKE_ATTEMPTS + 1):
            if work.exists():
                shutil.rmtree(work)
            _copy_project(export_dir, work)   # threads (0.193.0)
            _forward_plus(work / "project.godot")
            plugin = work / PLUGIN_DIR
            plugin.mkdir(parents=True, exist_ok=True)
            shutil.copy(PLUGIN_SCRIPT, plugin / "light_bake_plugin.gd")
            (plugin / "plugin.cfg").write_text(
                '[plugin]\n\nname="lf_light_bake"\ndescription="Bakes bake.tscn and quits."\n'
                'author="level_factory"\nversion="1"\nscript="light_bake_plugin.gd"\n',
                encoding="utf-8", newline="\n")
            # the editor's output, kept beside the package (0.178.5), never inside it
            editor_log = export_dir.parent / (export_dir.name + (
                ".lightbake.log" if attempt == 1 else ".lightbake.%d.log" % attempt))
            code, took = _run([str(godot_executable), "--editor", "--path", str(work),
                               "--resolution", "1280x720"], EDITOR_TIMEOUT_S,
                              log_path=editor_log)
            result_p = work / RESULT
            result = json.loads(result_p.read_text(encoding="utf-8")) if result_p.exists() else None
            attempts.append({"attempt": attempt, "editor_s": round(took, 1),
                             "editor_log": str(editor_log), "timed_out": code is None,
                             "result": result})
            if code is not None and result and result.get("ok"):
                break
        report["attempts"] = attempts
        report["editor_s"] = attempts[-1]["editor_s"]
        report["editor_log"] = attempts[-1]["editor_log"]
        report["result"] = result
        report["room_fills"] = (result or {}).get("room_fills")
        # 0.261.0: the static lamps Lux lent a bake range, -1 when its Lux has none
        report["bake_ranges_lent"] = (result or {}).get("bake_ranges_lent")
        if code is None:
            raise RuntimeError(f"the editor did not finish in {EDITOR_TIMEOUT_S} s")
        if not result or not result.get("ok"):
            raise RuntimeError("the bake did not complete: %s" % (result or "no result written"))
        for f in BAKE_FILES:
            src = work / f
            if not src.exists():
                raise RuntimeError(f"the bake wrote no {f}")
            shutil.copy(src, export_dir / f)
        # the editor's import of the lightmap, kept rather than done again (0.183.0)
        report["lightmap_import_copied"] = _copy_lightmap_import(work, export_dir)
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
               ("no room floor (the level's Lux lays none)" if fills in (None, -1)
                else "%d room fill(s)" % fills)
               + ("" if report["bake_ranges_lent"] in (None, -1)
                  else ", %d lamp(s) lent a bake range" % report["bake_ranges_lent"]),
               result.get("users"), report["editor_s"]))
        if len(attempts) > 1:
            log("[export] light bake: baked on attempt %d of %d; the first failed: %s"
                % (len(attempts), BAKE_ATTEMPTS,
                   (attempts[0]["result"] or {}).get("error") or "no result written"))
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
            _remove_later(work)   # while the export goes on (0.193.0)
    (export_dir / REPORT).write_text(json.dumps(report, indent=1), encoding="utf-8")
    return report
