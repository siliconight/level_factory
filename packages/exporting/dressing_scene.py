"""A `surface-dressing/1` manifest as a Godot scene of MultiMesh instances.

The last stage of the Layer 3 chain (`docs/SURFACE_DRESSING.md` section 2).
Lot said where dressing may go, Patina decided what goes where, and this turns
that decision into something the engine loads.

WHY A SEPARATE SCENE AND NOT NODES IN THE SITE. The site `.tscn` is the
functional shell, and the shell is LOCKED. Dressing is defined by not touching
it: this writes `<site>_dressing.tscn`, which the site instances (or does not).
A dressing pass that edits the locked scene has already broken the one promise
the layer makes, whatever the geometry does.

WHY MULTIMESH. 3,948 instances of four meshes is the case instancing exists
for -- as MultiMeshes that is four draw calls, and the per-instance transform
lives in a buffer rather than a node. Emitting 3,948 `MeshInstance3D` nodes
would produce a scene that technically renders and practically is the load
hitch this layer was told not to cause.

THE COORDINATE CONVERSION IS LOT'S, NOT A NEW ONE. `lot.py:_godot_transform`
already solved it and wrote it down:

    site XY ground -> Godot XZ, site Z height -> Godot Y
    origin: site (x, y, z) -> Godot (x, z, -y)
    yaw about site Z becomes yaw about Godot Y, NEGATED -- the handedness flip
    that comes with the Z-up -> Y-up axis swap

Re-deriving it here would have given this repo two answers to a question it
has already answered once, so the formula below is transcribed. But "NEGATED"
is a summary that loses the thing you need, and this module paid for that.
`godot_transform` returns basis ROWS; a reader who takes them for basis
vectors transposes the matrix, and for a pure yaw a transpose IS the negation
-- so the rule and the mistake are spelled the same way and cancel out in your
head. The unlossy form is a column: site +X under yaw r must land on Godot
(cos r, 0, -sin r), and basis column 0 is (row0[0], row1[0], row2[0]).
`tests/test_dressing_scene.py` asserts exactly that, at a yaw whose sine is
not zero -- because at zero yaw the transpose is the same matrix, which is how
this got shipped past a full test file.

TWO THINGS THIS MODULE DOES NOT KNOW, AND SAYS SO RATHER THAN GUESSING.

1. The MultiMesh buffer layout -- SETTLED 2026-08-19, and the answer was that
   it was wrong. Godot stores each instance as 12 floats and which 12 could
   not be checked from Python, so it was isolated in `multimesh_floats()`
   behind a docstring saying so, and `scene_text(mode="nodes")` was built
   beside it emitting the same placements through the string form Lot already
   ships. That pairing is what made the answer cheap: `tools/dressing_ab.ps1`
   loads both scenes in a real Godot window and compares transform against
   transform. It found the buffer transposed -- 4372 of 4374 instances
   disagreed, and the 2 that agreed were at zero yaw. The layout is now
   row-major with the origin interleaved, the A/B agrees instance for
   instance, and `mode="nodes"` stays -- not as a fallback but as the
   reference the next question of this shape gets measured against.

2. How a mesh resource is addressed. A `.glb` imports as a PackedScene, and a
   MultiMesh needs a Mesh. Whether that is a `.tres`, a `.res`, or a
   `res://x.glb::Mesh_y` subresource path depends on the import settings, so
   the caller SUPPLIES the path per asset and this module refuses to invent
   one. An asset with no path is an error, not a silently empty layer.
"""
from __future__ import annotations

import json
import math

SCHEMA = "surface-dressing/1"

# Godot's MultiMesh.transform_format for 3D.
TRANSFORM_3D = 1


class DressingSceneError(ValueError):
    """The scene cannot be written, and writing an empty one would be worse."""


def godot_transform(pos, yaw_rad, scale=1.0):
    """(row0, row1, row2, origin) of the Godot transform for one placement.

    THESE ARE BASIS ROWS, NOT BASIS VECTORS. They were called `bx, by, bz`
    here for one release and that name is what caused the transpose the Godot
    A/B eventually caught. `lot.py:_godot_transform` uses the same three
    letters but its comment says "Godot Basis ROWS", and the comment is the
    true one: Godot reads BOTH the `.tscn` `Transform3D(...)` literal and the
    MultiMesh instance buffer row-major, so a tuple that is a row in one form
    is a row in the other, and neither is ever a column.

    `pos` is spec/Blender Z-up (x, y, z) and `yaw_rad` is about spec Z.
    Transcribed from `lot.py:_godot_transform` -- see the module docstring for
    why this is transcribed rather than re-derived. `scale` is uniform and
    folds into the basis, which is what a MultiMesh instance transform carries
    (there is no separate scale channel).

    The checkable claim, which is what "the yaw is negated" was a lossy
    summary of: site +X under yaw r is site (cos r, sin r, 0), and the axis
    map (x, y, z) -> (x, z, -y) sends that to Godot (cos r, 0, -sin r). That
    is basis COLUMN 0 -- read DOWN the rows, (row0[0], row1[0], row2[0]).
    Stated as a column it is a test; stated as "negated" it is a sign you have
    to keep in your head, and a transpose keeps it there too.
    """
    c, s = math.cos(yaw_rad), math.sin(yaw_rad)
    k = float(scale)
    r0 = (c * k, 0.0, s * k)
    r1 = (0.0, 1.0 * k, 0.0)
    r2 = (-s * k, 0.0, c * k)
    origin = (float(pos[0]), float(pos[2]), -float(pos[1]))
    return r0, r1, r2, origin


def _g(n):
    """Format a float for a .tscn, with negative zero normalised away.

    `-sin(0) * k` is -0.0, which `%g` renders as `-0`. Godot reads it fine and
    Lot emits it too, but it makes two scenes that place things identically
    differ as text -- and byte comparison is how this repo checks that a
    rebuild changed nothing. A sign on a zero is not information.
    """
    v = float(n)
    return f"{0.0 if v == 0 else v:g}"


def transform3d_string(r0, r1, r2, origin):
    """The `Transform3D(...)` literal, in the argument order Lot emits.

    Godot parses this row-major: three numbers for basis row 0, three for row
    1, three for row 2, then the origin. Lot has shipped this ordering on
    hardware, which is what made it usable as the reference the A/B measured
    the buffer against.
    """
    nums = [r0[0], r0[1], r0[2], r1[0], r1[1], r1[2], r2[0], r2[1], r2[2],
            origin[0], origin[1], origin[2]]
    return "Transform3D(" + ", ".join(_g(n) for n in nums) + ")"


def multimesh_floats(r0, r1, r2, origin):
    """The 12 floats Godot stores per MultiMesh instance.

    Row-major with the origin interleaved: each basis row, then that row's
    origin component. This is the SAME ordering as the `Transform3D(...)`
    literal in `transform3d_string()`. The only difference between the two
    forms is where the origin sits -- appended at the end there, every fourth
    float here.

    THIS FUNCTION WAS WRONG FOR ONE RELEASE AND THE WAY IT WAS WRONG IS THE
    POINT. Its docstring claimed the two forms used different orderings, and
    on that belief it read `godot_transform`'s three tuples as basis COLUMNS
    and interleaved them into rows -- which transposes the basis. For a pure
    yaw the transpose is the inverse rotation, so nothing crashed and nothing
    looked broken: every dressed object simply faced the mirrored way, in a
    scatter layer where no one direction is expected. Four tests covered this
    function and none could see it. Three used a yaw of zero, where the
    transpose is the same matrix. The fourth used a real yaw and compared
    `sorted(floats)` against `sorted(literal)`, because it also believed the
    orderings differed -- and a transpose is a permutation, which a multiset
    cannot detect. What caught it was `tools/dressing_ab.ps1`, reading the
    numbers back out of a running engine.
    """
    return [r0[0], r0[1], r0[2], origin[0],
            r1[0], r1[1], r1[2], origin[1],
            r2[0], r2[1], r2[2], origin[2]]


def orders_by_asset(manifest):
    """Placements grouped by asset_id, in manifest order.

    Grouping is what makes this cheap: one MultiMesh per asset, so the draw
    calls are the number of distinct meshes and not the number of objects.
    """
    out = {}
    for o in manifest.get("orders", []):
        out.setdefault(o["asset_id"], []).append(o)
    return out


def check_manifest(manifest):
    """Findings that must stop a scene being written. Empty list means clean.

    The honesty rule is re-checked HERE, at the last stage, deliberately. A
    manifest is data and data travels; the gate that matters is the one
    standing where the geometry is about to become real.
    """
    problems = []
    if manifest.get("schema") != SCHEMA:
        problems.append(f"not a {SCHEMA} manifest: {manifest.get('schema')!r}")
    if manifest.get("space") != "spec/Blender Z-up raw coords":
        problems.append(
            f"manifest space is {manifest.get('space')!r}; this writer converts "
            "from spec Z-up and would place a Y-up manifest on its side")
    step = (manifest.get("capsule") or {}).get("unassisted_step_max_m")
    for o in manifest.get("orders", []):
        if o.get("collision_policy") != "none":
            problems.append(
                f"{o.get('asset_id')} carries collision_policy "
                f"{o.get('collision_policy')!r}; surface dressing is "
                "collisionless by definition and this scene would put a "
                "collider next to a locked shell")
        if step and o.get("in_traversed_space") and o.get("height_m", 0) > step:
            problems.append(
                f"{o.get('asset_id')} stands {o['height_m']} m in traversed "
                f"space against a limit of {step} m")
    return problems


def scene_text(manifest, mesh_paths, *, mode="multimesh", root_name=None):
    """The `.tscn` text for a dressing layer.

    `mesh_paths` maps asset_id -> a Godot resource path that resolves to a
    MESH. See the module docstring: a .glb imports as a PackedScene, so which
    form is right depends on import settings and this module will not guess.
    """
    if mode not in ("multimesh", "nodes"):
        raise DressingSceneError(f"unknown mode {mode!r}")
    problems = check_manifest(manifest)
    if problems:
        raise DressingSceneError("; ".join(problems))

    grouped = orders_by_asset(manifest)
    missing = sorted(a for a in grouped if a not in mesh_paths)
    if missing:
        raise DressingSceneError(
            "no mesh resource path for " + ", ".join(missing)
            + ". A dressing layer missing an asset is not a smaller layer, it "
              "is a layer that silently forgot one of its species.")

    root = root_name or f"{manifest.get('site_id', 'site')}_dressing"
    ext = []
    subs = []
    nodes = [f'[node name="{root}" type="Node3D"]', '']

    for i, asset in enumerate(sorted(grouped)):
        ext.append(f'[ext_resource type="Mesh" path="{mesh_paths[asset]}" '
                   f'id="Mesh_{asset}"]')

    if mode == "multimesh":
        for asset in sorted(grouped):
            placements = grouped[asset]
            buf = []
            for o in placements:
                r0, r1, r2, org = godot_transform(
                    o["pos"], float(o.get("yaw", 0.0)),
                    float(o.get("scale", 1.0)))
                buf.extend(multimesh_floats(r0, r1, r2, org))
            subs += [
                f'[sub_resource type="MultiMesh" id="MM_{asset}"]',
                f'transform_format = {TRANSFORM_3D}',
                f'instance_count = {len(placements)}',
                f'mesh = ExtResource("Mesh_{asset}")',
                'buffer = PackedFloat32Array(' +
                ", ".join(_g(v) for v in buf) + ')',
                '',
            ]
            nodes += [
                f'[node name="dress_{asset}" type="MultiMeshInstance3D" '
                f'parent="."]',
                f'multimesh = SubResource("MM_{asset}")',
                '',
            ]
    else:
        for asset in sorted(grouped):
            nodes += [f'[node name="dress_{asset}" type="Node3D" parent="."]',
                      '']
            for j, o in enumerate(grouped[asset]):
                r0, r1, r2, org = godot_transform(
                    o["pos"], float(o.get("yaw", 0.0)),
                    float(o.get("scale", 1.0)))
                nodes += [
                    f'[node name="{asset}_{j:05d}" type="MeshInstance3D" '
                    f'parent="./dress_{asset}"]',
                    f'transform = {transform3d_string(r0, r1, r2, org)}',
                    f'mesh = ExtResource("Mesh_{asset}")',
                    '',
                ]

    load_steps = 1 + len(ext) + sum(1 for l in subs if l.startswith("[sub_resource"))
    head = [f'[gd_scene load_steps={load_steps} format=3]', '']
    return "\n".join(head + ext + [''] + subs + nodes) + "\n"


def summarise(manifest, mode="multimesh"):
    """What this scene will cost, for the log line that says it was cheap."""
    grouped = orders_by_asset(manifest)
    instances = sum(len(v) for v in grouped.values())
    return {
        "instances": instances,
        "meshes": len(grouped),
        # One MultiMesh is one draw call; one node per instance is not.
        "draw_calls": len(grouped) if mode == "multimesh" else instances,
        "mode": mode,
    }


def main(argv=None):
    import argparse
    import sys

    ap = argparse.ArgumentParser(
        prog="dressing_scene",
        description="Write a Godot dressing scene from a surface-dressing/1 "
                    "manifest.")
    ap.add_argument("manifest")
    ap.add_argument("--mesh-paths", required=True,
                    help='JSON mapping asset_id -> Godot resource path that '
                         'resolves to a Mesh')
    ap.add_argument("--out", required=True)
    ap.add_argument("--mode", default="multimesh",
                    choices=("multimesh", "nodes"),
                    help="`nodes` emits one MeshInstance3D per placement using "
                         "the Transform3D form Lot already ships. Slow and "
                         "verified -- the reference to compare multimesh "
                         "against in the editor.")
    ap.add_argument("--root-name")
    a = ap.parse_args(argv)

    with open(a.manifest, encoding="utf-8") as fh:
        man = json.load(fh)
    with open(a.mesh_paths, encoding="utf-8") as fh:
        paths = json.load(fh)

    try:
        text = scene_text(man, paths, mode=a.mode, root_name=a.root_name)
    except DressingSceneError as exc:
        sys.stderr.write(f"[dress-scene] refused: {exc}\n")
        return 2
    with open(a.out, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    s = summarise(man, a.mode)
    sys.stderr.write(
        f"[dress-scene] {s['instances']} instances of {s['meshes']} meshes -> "
        f"{s['draw_calls']} draw calls ({s['mode']})\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
