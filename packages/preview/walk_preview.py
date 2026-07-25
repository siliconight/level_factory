"""Build a throwaway first-person WALK PREVIEW project that wraps a composed
themed level so you can walk it and make refinements.

Why this is separate from the presentation-compose output: the compose output is
a DROP-IN CONTENT package — a stranger instances ``res://<level>.tscn`` into
their OWN Godot project, so it must stay project-agnostic (no player, no forced
main scene). A player/walk scene is the opposite: it only means something inside
a running project (it needs project.godot + a main scene + a camera + input).

So we never bake the player into the package. Instead this builder makes a
SEPARATE, clearly dev-only project that INSTANCES the same content scene and adds
LF's dependency-free walk controller at a spawn marker. It's never exported (the
deliverable stays pure content); it exists purely for local iteration.

Godot ``res://`` is rooted at the project dir and can't reach a sibling folder,
so the preview copies the content in — a cheap, disposable duplicate. The package
is left untouched.
"""
from __future__ import annotations

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
"""


def _find_level_scene(content_dir: Path) -> str | None:
    """The drop-in content scene: the .tscn that is neither the package's
    ``*_main.tscn`` harness nor a ``*_walk.tscn`` preview. Prefer ``site.tscn``."""
    tscns = [p.name for p in sorted(content_dir.glob("*.tscn"))
             if not p.name.endswith("_main.tscn")
             and not p.name.endswith("_walk.tscn")]
    # Prefer the Lux-applied scene when the art pass produced one: walking the
    # final runtime look beats walking the unlit compose intermediate.
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
    has_lux = False
    try:
        has_lux = "addons/lux" in (dest / level).read_text(encoding="utf-8")
    except OSError:
        pass
    if has_lux:
        (dest / "walk.tscn").write_text(
            "[gd_scene load_steps=3 format=3]\n\n"
            f'[ext_resource type="PackedScene" path="res://{level}" id="1_lvl"]\n'
            '[ext_resource type="PackedScene" path="res://player_walk.tscn" id="2_ply"]\n\n'
            '[node name="Walk" type="Node3D"]\n\n'
            f'[node name="Level" parent="." instance=ExtResource("1_lvl")]\n\n'
            '[node name="Player" parent="." instance=ExtResource("2_ply")]\n'
            f"transform = Transform3D({tf})\n", encoding="utf-8")
    else:
        (dest / "walk.tscn").write_text(
            "[gd_scene load_steps=5 format=3]\n\n"
            f'[ext_resource type="PackedScene" path="res://{level}" id="1_lvl"]\n'
            '[ext_resource type="PackedScene" path="res://player_walk.tscn" id="2_ply"]\n\n'
            '[sub_resource type="ProceduralSkyMaterial" id="Sky_mat"]\n\n'
            '[sub_resource type="Sky" id="Sky"]\n'
            'sky_material = SubResource("Sky_mat")\n\n'
            '[sub_resource type="Environment" id="Env"]\n'
            'background_mode = 2\n'
            'sky = SubResource("Sky")\n'
            'ambient_light_source = 2\n'
            'ambient_light_color = Color(0.72, 0.73, 0.77, 1)\n'
            'ambient_light_energy = 1.4\n\n'
            '[node name="Walk" type="Node3D"]\n\n'
            '[node name="PreviewLighting" type="Node3D" parent="."]\n\n'
            '[node name="WorldEnvironment" type="WorldEnvironment" parent="PreviewLighting"]\n'
            'environment = SubResource("Env")\n\n'
            '[node name="Sun" type="DirectionalLight3D" parent="PreviewLighting"]\n'
            'transform = Transform3D(1, 0, 0, 0, 0.4, -0.9, 0, 0.9, 0.4, 0, 15, 0)\n'
            'light_energy = 0.6\n'
            'shadow_enabled = false\n\n'
            f'[node name="Level" parent="." instance=ExtResource("1_lvl")]\n\n'
            '[node name="Player" parent="." instance=ExtResource("2_ply")]\n'
            f"transform = Transform3D({tf})\n", encoding="utf-8")
    lighting = "lux (content-owned)" if has_lux else "preview rig"

    # 5. the preview project (main scene = walk.tscn).
    (dest / "project.godot").write_text(
        _PROJECT.format(name=name, level=level), encoding="utf-8")

    return {"dest": str(dest), "level_scene": level, "walk_scene": "walk.tscn",
            "spawn_transform": list(spawn), "spawn_source": spawn_src,
            "lighting": lighting, "content_copied": copied}
