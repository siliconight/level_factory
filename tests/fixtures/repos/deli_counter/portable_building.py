"""Stub Deli Counter composer (portable_building.build_package shape).

The REAL portable_building.py strips the greybox to a floors+collision base and
fits themed Zoo modules onto each slot with the greybox-footprint rotation, then
runs a placement gate + closure check. This stub reproduces the same OUTPUT
CONTRACT (a self-contained themed <bid>.tscn + <bid>_base.glb + art/zoo/*.glb +
portable_resource_manifest.json) without pygltflib/Blender, so the Level Factory
presentation-compose wiring runs end-to-end in CI against fixture repos.
"""
from __future__ import annotations

import json
import os
import shutil


def build_package(slots_path, gameplay_path, module_dir, out_dir, *,
                  theme, style=1, building_id=None, greybox_glb=None,
                  dressing_glb=None, fixtures_glb=None):
    if os.path.exists(out_dir):
        shutil.rmtree(out_dir)
    art = os.path.join(out_dir, "art", "zoo")
    os.makedirs(art, exist_ok=True)

    # content layers (real DC >= 0.88 bundles these to art/<layer>/ and
    # instances them at identity; the stub just records the bundling).
    content_layers = {}
    for layer_name, layer_glb in (("dressing", dressing_glb),
                                  ("fixtures", fixtures_glb)):
        if layer_glb and os.path.exists(layer_glb):
            ldir = os.path.join(out_dir, "art", layer_name)
            os.makedirs(ldir, exist_ok=True)
            shutil.copy2(layer_glb, os.path.join(
                ldir, os.path.basename(layer_glb)))
            content_layers[layer_name] = os.path.basename(layer_glb)

    slots = json.load(open(slots_path, encoding="utf-8"))
    bid = building_id or slots.get("building_id") or "building"

    # 0. greybox floors+collision base (walkable shell under the themed art).
    base_res = None
    walkable = False
    if greybox_glb and os.path.exists(greybox_glb):
        base_name = f"{bid}_base.glb"
        shutil.copy2(greybox_glb, os.path.join(out_dir, base_name))
        base_res = f"res://{base_name}"
        walkable = True

    # 1. bundle the themed module glbs from the Zoo kit dir into art/zoo/.
    bundled = []
    if module_dir and os.path.isdir(module_dir):
        for name in sorted(os.listdir(module_dir)):
            if name.endswith(".glb"):
                shutil.copy2(os.path.join(module_dir, name),
                             os.path.join(art, name))
                bundled.append(name)

    # 2. themed building .tscn: base + one instance per bundled module.
    lines = [f"[gd_scene load_steps={len(bundled) + 2} format=3]", ""]
    ext_id = 1
    if base_res:
        lines.append(f'[ext_resource type="PackedScene" path="{base_res}" '
                     f'id="{ext_id}_base"]')
        ext_id += 1
    mod_ids = []
    for name in bundled:
        mid = f"{ext_id}_{name.replace('.glb', '')}"
        lines.append(f'[ext_resource type="PackedScene" '
                     f'path="res://art/zoo/{name}" id="{mid}"]')
        mod_ids.append(mid)
        ext_id += 1
    lines += ["", f'[node name="{bid}" type="Node3D"]', ""]
    if base_res:
        lines.append('[node name="GreyboxBase" parent="." '
                     f'instance=ExtResource("1_base")]')
        lines.append("")
    for i, (name, mid) in enumerate(zip(bundled, mod_ids)):
        lines.append(f'[node name="module_{i}" parent="." '
                     f'instance=ExtResource("{mid}")]')
        lines.append("transform = Transform3D(1, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0)")
        lines.append("")
    tscn_path = os.path.join(out_dir, f"{bid}.tscn")
    open(tscn_path, "w", encoding="utf-8").write("\n".join(lines) + "\n")

    # 3. bake markers as plain grouped Node3D nodes.
    markers = 0
    if gameplay_path and os.path.exists(gameplay_path):
        gp = json.load(open(gameplay_path, encoding="utf-8"))
        markers = len(gp.get("markers") or [])

    # 4. entry scene + project.godot (self-contained).
    main_name = f"{bid}_main.tscn"
    open(os.path.join(out_dir, main_name), "w", encoding="utf-8").write(
        "[gd_scene load_steps=2 format=3]\n\n"
        f'[ext_resource type="PackedScene" path="res://{bid}.tscn" id="1_b"]\n\n'
        '[node name="Main" type="Node3D"]\n\n'
        f'[node name="Building" parent="." instance=ExtResource("1_b")]\n')
    open(os.path.join(out_dir, "project.godot"), "w", encoding="utf-8").write(
        "config_version=5\n\n[application]\n"
        f'config/name="{bid} (portable building)"\n'
        f'run/main_scene="res://{main_name}"\n')
    open(os.path.join(out_dir, "HANDOFF.md"), "w", encoding="utf-8").write(
        f"# {bid} -- portable themed building ({theme})\n")

    manifest = {
        "schema": "portable_building.v0.1", "building_id": bid, "theme": theme,
        "themed_modules": len(bundled), "greybox_fallback": 0,
        "bundled_modules": bundled, "missing_modules": [],
        "markers_baked": markers,
        "greybox_base": ({"kept_colliders": 1, "kept_greybox_visuals": 1,
                          "dropped_slot_visuals": 0} if walkable else None),
        "walkable": walkable,
        "placement_check": {"checked": len(bundled), "matched": len(bundled),
                            "mismatched": 0, "mismatches": [],
                            "height_warnings": [], "height_warning_count": 0,
                            "ok": True},
        "instancing": {"distinct_meshes": len(bundled),
                       "module_instances": len(bundled)},
        "closure": {"absolute_path_count": 0, "absolute_paths": [],
                    "dangling_refs": [], "portable": True},
        # real DC >= 0.88 manifest keys the LF compose driver gates on:
        # a composer that doesn't report its z-fight check doesn't ship.
        "zfight_check": {"ok": True, "pairs": 0,
                         "solids": len(bundled) + (1 if walkable else 0)},
        "ladder_climb_volumes": 0,
        "style_fallback_to_01": 0,
        "content_layers": content_layers,
    }
    open(os.path.join(out_dir, "portable_resource_manifest.json"), "w",
         encoding="utf-8").write(json.dumps(manifest, indent=2, sort_keys=True))
    return manifest
