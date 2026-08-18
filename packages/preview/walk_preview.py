"""Build a throwaway first-person WALK PREVIEW project that wraps the portable
export of a mission so you can walk it and make refinements.

Why this is separate from the presentation-compose output: the compose output is
a DROP-IN CONTENT package — a stranger instances ``res://<level>.tscn`` into
their OWN Godot project, so it must stay project-agnostic (no player, no forced
main scene). A player/walk scene is the opposite: it only means something inside
a running project (it needs project.godot + a main scene + a camera + input).

So we never bake the player into the package. Instead this builder makes a
SEPARATE, clearly dev-only project that INSTANCES the deliverable and adds LF's
dependency-free walk controller at a spawn marker. The PREVIEW PROJECT is never
exported (the deliverable stays pure content); it exists purely for local
iteration.

What it instances is the PORTABLE EXPORT, not the job outputs. ``cmd_walk``
runs ``export_mission`` first and wraps the ``mission.tscn`` that comes out of
it, so what you walk is the package a stranger receives -- localized,
addon-free and closure-scanned. Walking the job outputs meant walking a level
that renders only with the Lux checkout on disk, which is the definition of an
instrument that escaped.

Godot ``res://`` is rooted at the project dir and can't reach a sibling folder,
so the preview copies the content in — a cheap, disposable duplicate. The package
is left untouched.
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
import re
import shutil
from pathlib import Path

# Marker groups worth spawning the player at, best first. These are the groups
# portable_building bakes onto the marker nodes (``groups=["<type>", ...]``).
# Extraction/objective/loot are ground-level gameplay points -- fine spawns
# when a level carries no explicit spawn/entrance markers.
_SPAWN_PRIORITY = ("player_start", "spawn", "attacker_spawn", "entrance",
                   "door", "front_door", "extraction", "objective", "loot")

# Never spawn AT a vertical anchor: a ladder marker sits at the ladder's own
# base (inside its collision plane -- the player wedges and can't move), and
# hatch/camera markers hang in the air or in a ceiling.
_SPAWN_EXCLUDE = {"ladder", "hatch", "camera_socket", "floor_hole"}

# Package-harness / metadata files we do NOT copy into the preview: we write our
# own project.godot + walk main scene, and the package's *_main.tscn / manifests
# are its standalone self-check chrome, irrelevant to the preview.
_SKIP_NAMES = {"project.godot", "compose.summary.json", "HANDOFF.md",
               "portable_resource_manifest.json"}

_MARKER_NODE = re.compile(
    r'\[node name="[^"]*"[^\]]*parent="Markers"[^\]]*groups=\[([^\]]*)\][^\]]*\]')
_TRANSFORM = re.compile(r'transform\s*=\s*Transform3D\(([^)]*)\)')

_PROJECT = """; Level Factory WALK PREVIEW -- DEV ONLY, not a deliverable.
; Wraps the drop-in content scene ({level}) and adds a first-person player so
; you can walk the level and make refinements. Never exported.
config_version=5

[application]
config/features=PackedStringArray("4.7")
config/name="{name} (walk preview)"
run/main_scene="res://walk.tscn"

[rendering]
renderer/rendering_method="gl_compatibility"
; PER-OBJECT LIGHT CAP. The compatibility renderer selects at most N
; lights per MESH and re-selects as geometry moves through range, so a
; mesh over the cap drops lights and appears to blink. Measured on
; lot_demo_001, 2026-08-18, 136 fixture lights over five buildings: 111
; of 920 meshes exceed the engine default of 8, 39 exceed 16, and exactly
; one -- pvp_station_ref's roof -- exceeds 32, at 36. Every offender is a
; building-wide roof or floor/ceiling plate 34-52 m across, competing for
; the same slots as a 2 m wall segment; when one loses, a whole room goes
; dark at once. Confirmed in the walk preview: heavy blinking at the
; default, mostly gone at 32 with certain rooms still dropping, none under
; forward_plus -- the response tracks the NUMBER, which is what pins it.
; 64 clears the measured worst case and keeps gl_compatibility, which is
; the property this profile exists for. IT IS A MITIGATION. The fix is
; that one mesh should not span a building -- roadmap 54.
limits/opengl/max_lights_per_object=64

[debug]
; Verbatim from export.py::_write_project_godot, and it must stay verbatim:
; localized tool scripts are strict-clean under their home projects' warning
; config, while engine DEFAULTS escalate inference-on-Variant to a load-killing
; error. Proven on hardware -- lux_root.gd:218 took two dependents down as
; compile knock-ons -- and proven again here on 2026-08-12, where the preview
; lacked this block and lux_area_light_rig.gd:61 failed to parse in a walk of
; the same package the export's portability test scored parser_error_count 0.
; Two projects disagreeing about what a complete project.godot contains is how
; a human signs off lighting that was missing a rig.
gdscript/warnings/inference_on_variant=1
"""


#: The entry `write_entry_scene` synthesizes in an export. A plain Node3D whose
#: script instances the level -- "Self-contained (no addons)", in its own words.
ENTRY_SCENE = "mission.tscn"


def _find_level_scene(content_dir: Path) -> str | None:
    """The scene to walk: the export's entry, else the drop-in content scene.

    ``mission.tscn`` comes first because in an export root it IS the level, and
    `site.tscn` beside it is a dependency the presentation scene resolves by
    name rather than a second level standing next to it -- `write_entry_scene`
    makes that call and this defers to it instead of making it again.

    The `site_lux.tscn` preference below is KEPT AND DEAD, deliberately.
    `lux_apply` writes `lux.applied.tscn`; nothing has ever written this name,
    which is why the branch never fired. It stays because deleting it would
    erase the evidence that the two halves of this contract were never the same
    string -- and because the fix was not to satisfy it. The applied scene
    references `res://addons/lux/` six times and renders nothing without the
    Lux checkout on disk; the export localizes that, and walking the export is
    how the preview gets the lit look without an instrument escaping.
    """
    tscns = [p.name for p in sorted(content_dir.glob("*.tscn"))
             if not p.name.endswith("_main.tscn")
             and not p.name.endswith("_walk.tscn")]
    if ENTRY_SCENE in tscns:
        return ENTRY_SCENE
    if "site_lux.tscn" in tscns:
        return "site_lux.tscn"
    if "site.tscn" in tscns:
        return "site.tscn"
    return tscns[0] if tscns else None


def _spawn_from_scene(scene_path: Path):
    """Read the baked marker nodes from the content scene and return
    ((12 Transform3D floats), source_label). Markers are already in Godot Y-up
    (portable_building converts on bake), so we use their origin directly, lifted
    a little so the player drops onto the floor under gravity."""
    default = ((1, 0, 0, 0, 1, 0, 0, 0, 1, 0.0, 1.5, 3.0), "default (no markers)")
    try:
        lines = scene_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return default

    # Collect (groups_set, origin) for every marker node.
    found = []
    i = 0
    while i < len(lines):
        m = _MARKER_NODE.search(lines[i])
        if m:
            groups = {g.strip().strip('"').lower()
                      for g in m.group(1).split(",") if g.strip()}
            origin = None
            for j in range(i + 1, min(i + 4, len(lines))):
                tm = _TRANSFORM.search(lines[j])
                if tm:
                    nums = [float(x) for x in tm.group(1).split(",")]
                    if len(nums) >= 12:
                        origin = nums[9], nums[10], nums[11]
                    break
            if origin is not None:
                found.append((groups, origin))
        i += 1

    if not found:
        return default
    chosen = None
    for want in _SPAWN_PRIORITY:
        chosen = next((o for g, o in found if want in g), None)
        if chosen:
            src = want
            break
    if chosen is None:
        # No spawn-class marker: take the LOWEST non-vertical marker (ground
        # floor beats a rooftop camera), never a ladder/hatch anchor.
        pool = [o for g, o in found if not (g & _SPAWN_EXCLUDE)] \
            or [o for _, o in found]
        chosen = min(pool, key=lambda o: o[1])
        src = "lowest ground marker"
    gx, gy, gz = chosen
    return ((1, 0, 0, 0, 1, 0, 0, 0, 1, round(gx, 3), round(gy + 0.6, 3),
             round(gz, 3)), f"marker:{src}")


def _overlay_steps(dest) -> int:
    return 1 if _overlay_res(dest) else 0


def _overlay_res(dest) -> str:
    """The overlay's ext_resource line, or "" when assets/godot has no overlay.

    Written conditionally for the same reason the bots are copied
    conditionally: an older `assets/godot` should still produce a usable
    preview. A scene referencing a script that is not there fails to load, and
    a preview that will not open is worse than one without a HUD.
    """
    from pathlib import Path as _P
    if not (_P(dest) / "debug_overlay.gd").is_file():
        return ""
    return '[ext_resource type="Script" path="res://debug_overlay.gd" id="3_dbg"]\n'


def _overlay_node(dest) -> str:
    from pathlib import Path as _P
    if not (_P(dest) / "debug_overlay.gd").is_file():
        return ""
    return ('\n[node name="DebugOverlay" type="Node" parent="."]\n'
            'script = ExtResource("3_dbg")\n')


def _provenance(content_dir: Path, dest: Path, level: str) -> dict:
    """A digest of the content this preview was built from.

    Over the RELATIVE PATH AND CONTENT of every copied file, sorted. Not the
    directory mtime -- that moves when nothing did, and a copy sets it on every
    build. Not a job id either: the preview is handed a directory and cannot
    see the graph it came from. Bytes are the thing both readers can compare.

    The player, the bots and this file are excluded: they are the preview's own
    scaffolding, not the content under test, and a new overlay script should
    not read as a different level.
    """
    ours = {"player_walk.gd", "player_walk.tscn", "walk.tscn", "project.godot",
            "walk_bot.gd", "shot_bot.gd", "debug_overlay.gd",
            "walk.source.json", "walkbot.json", "shotbot.json"}
    h = hashlib.sha256()
    n = 0
    for p in sorted(dest.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(dest).as_posix()
        if rel in ours or rel.endswith(".uid") or rel.startswith(".godot/"):
            continue
        h.update(rel.encode("utf-8"))
        h.update(hashlib.sha256(p.read_bytes()).digest())
        n += 1
    return {
        "schema": "level_factory.walk_provenance.v0.1",
        "source": str(content_dir),
        "level_scene": level,
        "content_digest": "sha256:" + h.hexdigest()[:16],
        "file_count": n,
        "built_at": _dt.datetime.now(_dt.timezone.utc).isoformat(),
    }


def build_walk_preview(content_dir, player_src, dest, *, name="level"):
    """Assemble a self-contained walk-preview project at ``dest`` that wraps the
    content in ``content_dir`` and adds LF's player. Returns a report dict.

    Raises FileNotFoundError if there's no content scene or the player assets are
    missing.
    """
    content_dir = Path(content_dir)
    player_src = Path(player_src)
    dest = Path(dest)

    level = _find_level_scene(content_dir)
    if not level:
        raise FileNotFoundError(
            f"no content scene (*.tscn) found in {content_dir} — run the "
            f"presentation compose (--art) first")
    ptscn = player_src / "player_walk.tscn"
    pgd = player_src / "player_walk.gd"
    if not (ptscn.exists() and pgd.exists()):
        raise FileNotFoundError(
            f"player controller assets missing under {player_src}")

    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)

    # 1. copy the drop-in content in (disposable duplicate; package untouched).
    copied = []
    for item in sorted(content_dir.iterdir()):
        if item.name in _SKIP_NAMES or item.name.endswith("_main.tscn"):
            continue
        if item.is_dir():
            shutil.copytree(item, dest / item.name)
        else:
            shutil.copy2(item, dest / item.name)
        copied.append(item.name)

    # 2. LF's dependency-free player controller.
    shutil.copy2(ptscn, dest / "player_walk.tscn")
    shutil.copy2(pgd, dest / "player_walk.gd")

    # 2b. The bots that walk and look at this preview without a human. They ride
    # along in the preview project rather than the package for the same reason
    # the player does: they are dev instrumentation, and the deliverable stays
    # pure content. Copied opportunistically -- an older assets/godot without
    # them still builds a usable preview, it just cannot self-check.
    bots = []
    for bot in ("walk_bot.gd", "shot_bot.gd", "debug_overlay.gd"):
        src = player_src / bot
        if src.exists():
            shutil.copy2(src, dest / bot)
            bots.append(bot)

    # 3. spawn from the baked markers.
    spawn, spawn_src = _spawn_from_scene(dest / level)
    tf = ", ".join(str(v) for v in spawn)

    # 4. the walk scene: content instance + player at the spawn. Lighting depends
    # on what the content carries:
    #   - A Lux-applied scene (LuxRoot inside) lights itself on ready — adding a
    #     preview rig on top would fight Lux's WorldEnvironment and wash out the
    #     applied look, so the preview stands down and lets Lux own the light.
    #   - Pre-Lux content carries no lighting and renders pitch black, so the
    #     preview adds a basic dev rig: sky + strong colour ambient (geometry is
    #     always visible, independent of renderer/sky quirks) + a sun for
    #     definition. Preview-only chrome — never ships, not Lux's final look.
    # WHO OWNS THE LIGHT. This used to grep the level scene for `addons/lux`,
    # which works on a lux_apply intermediate and is exactly wrong on an export:
    # `localize_export` removes that string BY DESIGN -- a portable package
    # carries no addons by contract. The old test would have found nothing,
    # added the dev rig on top of Lux's own WorldEnvironment, and washed out the
    # applied look it was written to protect.
    #
    # So it asks the question the export answers: is there a presentation scene
    # in here. That is the same thing `write_entry_scene` keys on when it
    # decides what `mission.tscn` instances, so the two cannot disagree.
    has_lux = (dest / "presentation" / "lux.applied.tscn").is_file()
    if not has_lux:
        try:
            has_lux = "addons/lux" in (dest / level).read_text(encoding="utf-8")
        except OSError:
            pass
    if has_lux:
        (dest / "walk.tscn").write_text(
            f"[gd_scene load_steps={3 + _overlay_steps(dest)} format=3]\n\n"
            f'[ext_resource type="PackedScene" path="res://{level}" id="1_lvl"]\n'
            '[ext_resource type="PackedScene" path="res://player_walk.tscn" id="2_ply"]\n'
            + _overlay_res(dest) +
            '\n[node name="Walk" type="Node3D"]\n\n'
            f'[node name="Level" parent="." instance=ExtResource("1_lvl")]\n\n'
            '[node name="Player" parent="." instance=ExtResource("2_ply")]\n'
            f"transform = Transform3D({tf})\n" + _overlay_node(dest),
            encoding="utf-8")
    else:
        (dest / "walk.tscn").write_text(
            f"[gd_scene load_steps={5 + _overlay_steps(dest)} format=3]\n\n"
            f'[ext_resource type="PackedScene" path="res://{level}" id="1_lvl"]\n'
            '[ext_resource type="PackedScene" path="res://player_walk.tscn" id="2_ply"]\n'
            + _overlay_res(dest) + "\n"
            '[sub_resource type="ProceduralSkyMaterial" id="Sky_mat"]\n\n'
            '[sub_resource type="Sky" id="Sky"]\n'
            'sky_material = SubResource("Sky_mat")\n\n'
            '[sub_resource type="Environment" id="Env"]\n'
            'background_mode = 2\n'
            'sky = SubResource("Sky")\n'
            'ambient_light_source = 2\n'
            'ambient_light_color = Color(0.72, 0.73, 0.77, 1)\n'
            # FILL, not the main light. Ambient is directionless: it adds the
            # same amount to a face pointing up and a face pointing sideways,
            # so it cannot shade form -- form shading IS the difference
            # between orientations. At 1.4 against a 0.6 sun it was better
            # than 2:1 in favour of the term that flattens, and a wall read
            # the same value as the floor it stood on. It does not go to zero:
            # with shadows on, a face turned fully away would be black, and an
            # unreadable dark is no better than an unreadable flat.
            'ambient_light_energy = 0.3\n\n'
            '[node name="Walk" type="Node3D"]\n\n'
            '[node name="PreviewLighting" type="Node3D" parent="."]\n\n'
            '[node name="WorldEnvironment" type="WorldEnvironment" parent="PreviewLighting"]\n'
            'environment = SubResource("Env")\n\n'
            '[node name="Sun" type="DirectionalLight3D" parent="PreviewLighting"]\n'
            # Pitch AND yaw. The old basis was a pure rotation about X, so the
            # sun pointed at (0, -0.91, -0.41): square-on to perim_N and
            # perim_S and exactly grazing perim_E and perim_W, which left the
            # two pairs lit identically. 40 degrees of yaw gives
            # (-0.26, -0.91, -0.31) and every cardinal wall takes a different
            # amount. Orthonormal to 1e-6; `patch_lf_preview_lighting.py --rig`
            # recomputes and checks it.
            'transform = Transform3D(0.766, 0, -0.6428, -0.5872, 0.4067, -0.6998, 0.2614, 0.9135, 0.3116, 0, 40, 0)\n'
            'light_energy = 1.7\n'
            # Shadows are the other half of reading geometry: they say which
            # solid is in front of which, and where a solid meets the ground.
            # 260 m covers the long axis of a generated site (measured: the
            # lot_demo plate runs 309 m) without splitting the cascade so thin
            # it shimmers.
            'shadow_enabled = true\n'
            'directional_shadow_mode = 2\n'
            'directional_shadow_max_distance = 260.0\n'
            'shadow_bias = 0.06\n'
            'shadow_normal_bias = 2.0\n\n'
            f'[node name="Level" parent="." instance=ExtResource("1_lvl")]\n\n'
            '[node name="Player" parent="." instance=ExtResource("2_ply")]\n'
            f"transform = Transform3D({tf})\n" + _overlay_node(dest),
            encoding="utf-8")
    lighting = "lux (content-owned)" if has_lux else "preview rig"

    # 5. the preview project (main scene = walk.tscn).
    (dest / "project.godot").write_text(
        _PROJECT.format(name=name, level=level), encoding="utf-8")

    # 6. WHAT THIS WAS BUILT FROM. `walk` rmtree's and rebuilds, so a preview
    # is current at the moment it is made -- and nothing recorded that, so
    # reading the folder after a later `run` (which does not touch it) shows
    # the previous walk with no way to tell. Roadmap addendum item F: "cost
    # about an hour and five refuted hypotheses."
    prov = _provenance(content_dir, dest, level)
    (dest / "walk.source.json").write_text(
        json.dumps(prov, indent=2, sort_keys=True), encoding="utf-8")

    return {"dest": str(dest), "level_scene": level, "walk_scene": "walk.tscn",
            "spawn_transform": list(spawn), "spawn_source": spawn_src,
            "lighting": lighting, "content_copied": copied, "bots": bots,
            "provenance": prov}
