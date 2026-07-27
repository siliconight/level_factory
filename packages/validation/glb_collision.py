"""Read the collision a ``.glb`` actually brings, instead of guessing.

The ground-contact pre-flight used to stop at the edge of an imported binary:
a ``.glb`` instanced into a scene was recorded as opaque, and a mission point
standing on a floor inside that ``.glb`` looked exactly like a mission point
standing over a hole. The pre-flight then refused the map and said so in the
same breath as admitting it could not see -- "12 of 15 mission point(s) have no
ground beneath them (collision inside 5 instanced resource(s) is not readable
from the scene text)". That is "I cannot see it" reported as "it is not there",
which is the failure mode the whole guardrail family exists to refuse.

It is not necessary. Godot's glTF importer generates a physics body for a node
whose name ends in the ``-col`` family of suffixes, and the position and extent
of that body are fully described by the file's JSON chunk: the node hierarchy
carries the transforms and each mesh primitive's ``POSITION`` accessor carries
``min``/``max``. So the floor slabs inside a baked shell can be located without
decoding a single vertex buffer, without Blender, and without Godot.

The boxes returned are axis-aligned hulls of the collider meshes. For the slabs
and wall segments Deli Counter bakes, which are boxes, the hull is the shape.
For anything concave the hull is larger than the collider, which makes this
reader err towards "there is a floor here" -- the right direction for a check
whose output is a hard blocker.

Pure: bytes in, boxes out. Stdlib only, no Godot, no Blender.
"""
from __future__ import annotations

import json
import re
import struct
from dataclasses import dataclass
from pathlib import Path

Vec3 = tuple[float, float, float]
#: A 3x4 affine transform, row-major: three rows of (bx, by, bz, origin).
Mat = tuple[tuple[float, float, float, float], ...]

#: Godot's glTF importer generates a physics body for a node whose name ends in
#: one of these (docs: "Importing 3D scenes / Node type customization").
COLLISION_SUFFIXES = ("-col", "-convcol", "-colonly", "-convcolonly",
                      "-rigid", "-vehicle", "-wheel")

_GLB_MAGIC = 0x46546C67   # 'glTF'
_GLB_JSON = 0x4E4F534A    # 'JSON'
#: Blender appends `.001` to duplicated names, after the suffix Godot matches.
_DUP = re.compile(r"\.\d+$")
_PHYSICS = re.compile(r'"?generate/physics"?\s*[:=]\s*true')
#: A shell that nests deeper than this is malformed, or is trying to be a graph.
MAX_NODE_DEPTH = 64

_IDENTITY: Mat = ((1.0, 0.0, 0.0, 0.0),
                  (0.0, 1.0, 0.0, 0.0),
                  (0.0, 0.0, 1.0, 0.0))


@dataclass(frozen=True)
class Solid:
    """An axis-aligned collider hull, in the file's own coordinate space."""

    name: str
    centre: Vec3
    size: Vec3


@dataclass(frozen=True)
class GlbReading:
    """What a ``.glb`` contributes, and whether it could be read at all.

    ``read`` is the part that matters downstream. A file that parsed and holds
    no collider is a confident "this shell brings nothing"; a file that could
    not be parsed is "unknown", and the two must not collapse into one silence.
    """

    solids: tuple[Solid, ...]
    read: bool
    detail: str = ""


def name_generates_collision(name: str) -> bool:
    """Godot matches the suffix case-insensitively and tolerates `-col.001`."""
    return _DUP.sub("", str(name).strip().lower()).endswith(COLLISION_SUFFIXES)


def import_requests_physics(path: Path) -> bool:
    """A ``.glb`` can also be given collision by its sibling ``.import`` file,
    which is where the editor records per-node physics choices. When it is set,
    every mesh in the file becomes a collider, not just the suffixed ones."""
    try:
        text = Path(str(path) + ".import").read_text(encoding="utf-8",
                                                     errors="replace")
    except OSError:
        return False
    return bool(_PHYSICS.search(text))


# ---------------------------------------------------------------------------
# the container
# ---------------------------------------------------------------------------
def json_chunk(data: bytes) -> dict | None:
    """The glTF document out of a binary ``.glb``, or ``None``.

    Malformed input yields ``None`` rather than raising: the caller reports it
    as unreadable, and a pre-flight must not die on the asset it is inspecting.
    """
    if len(data) < 20:
        return None
    magic, _version, _length = struct.unpack_from("<III", data, 0)
    if magic != _GLB_MAGIC:
        return None
    offset = 12
    while offset + 8 <= len(data):
        length, kind = struct.unpack_from("<II", data, offset)
        if kind == _GLB_JSON:
            try:
                doc = json.loads(data[offset + 8: offset + 8 + length]
                                 .decode("utf-8"))
            except (UnicodeDecodeError, ValueError):
                return None
            return doc if isinstance(doc, dict) else None
        offset += 8 + length + (-length % 4)
    return None


# ---------------------------------------------------------------------------
# transforms
# ---------------------------------------------------------------------------
def _node_matrix(node: dict) -> Mat:
    """glTF gives a node either a 4x4 ``matrix`` or a TRS triple."""
    raw = node.get("matrix")
    if isinstance(raw, list) and len(raw) == 16:
        # glTF stores it column-major.
        return tuple(tuple(float(raw[4 * col + row]) for col in range(4))
                     for row in range(3))
    tx, ty, tz = (list(node.get("translation", (0.0, 0.0, 0.0))) + [0.0, 0.0, 0.0])[:3]
    qx, qy, qz, qw = (list(node.get("rotation", (0.0, 0.0, 0.0, 1.0)))
                      + [0.0, 0.0, 0.0, 1.0])[:4]
    sx, sy, sz = (list(node.get("scale", (1.0, 1.0, 1.0))) + [1.0, 1.0, 1.0])[:3]
    rot = ((1 - 2 * (qy * qy + qz * qz), 2 * (qx * qy - qz * qw), 2 * (qx * qz + qy * qw)),
           (2 * (qx * qy + qz * qw), 1 - 2 * (qx * qx + qz * qz), 2 * (qy * qz - qx * qw)),
           (2 * (qx * qz - qy * qw), 2 * (qy * qz + qx * qw), 1 - 2 * (qx * qx + qy * qy)))
    scale = (sx, sy, sz)
    origin = (tx, ty, tz)
    return tuple(tuple(rot[r][c] * scale[c] for c in range(3)) + (origin[r],)
                 for r in range(3))


def compose(outer: Mat, inner: Mat) -> Mat:
    """``outer`` applied to ``inner``: the child's transform in the parent's
    space."""
    return tuple(
        tuple(sum(outer[r][k] * inner[k][c] for k in range(3)) for c in range(3))
        + (sum(outer[r][k] * inner[k][3] for k in range(3)) + outer[r][3],)
        for r in range(3))


def apply(matrix: Mat, point: Vec3) -> Vec3:
    return tuple(sum(matrix[r][c] * point[c] for c in range(3)) + matrix[r][3]
                 for r in range(3))


def hull(matrix: Mat, low: Vec3, high: Vec3) -> tuple[Vec3, Vec3]:
    """The axis-aligned bounds of a box carried through ``matrix``."""
    lo = [float("inf")] * 3
    hi = [float("-inf")] * 3
    for x in (low[0], high[0]):
        for y in (low[1], high[1]):
            for z in (low[2], high[2]):
                for axis, value in enumerate(apply(matrix, (x, y, z))):
                    lo[axis] = min(lo[axis], value)
                    hi[axis] = max(hi[axis], value)
    return tuple(lo), tuple(hi)


# ---------------------------------------------------------------------------
# the file
# ---------------------------------------------------------------------------
def collision_solids(path) -> GlbReading:
    """Every collider in the ``.glb`` at ``path``, positioned in its own space."""
    path = Path(path)
    if not path.is_file():
        return GlbReading((), False, "geometry file not found on disk")
    if path.suffix.lower() == ".gltf":
        try:
            doc = json.loads(path.read_text(encoding="utf-8", errors="replace"))
        except (OSError, ValueError):
            return GlbReading((), False, "glTF JSON could not be parsed")
        if not isinstance(doc, dict):
            return GlbReading((), False, "glTF JSON could not be parsed")
    else:
        try:
            doc = json_chunk(path.read_bytes())
        except OSError as exc:
            return GlbReading((), False, f"unreadable: {exc}")
        if doc is None:
            return GlbReading((), False, "glTF JSON chunk could not be read")
    return solids_in(doc, every_mesh=import_requests_physics(path))


def solids_in(doc: dict, *, every_mesh: bool = False) -> GlbReading:
    """``collision_solids`` for a glTF document already in hand.

    ``every_mesh`` is the ``generate/physics`` case: the import settings ask
    Godot to body every mesh, so the ``-col`` naming convention does not apply.
    """
    nodes = doc.get("nodes")
    if not isinstance(nodes, list):
        return GlbReading((), False, "glTF document declares no nodes")
    meshes = doc.get("meshes") or []
    accessors = doc.get("accessors") or []
    scenes = doc.get("scenes") or []
    index = doc.get("scene", 0)
    roots = []
    if isinstance(index, int) and 0 <= index < len(scenes):
        roots = list(scenes[index].get("nodes") or [])
    if not roots:
        # A file with no scene declared is still a node list; walking every
        # node that nothing claims as a child recovers the same tree.
        claimed = {child for node in nodes if isinstance(node, dict)
                   for child in (node.get("children") or [])}
        roots = [i for i in range(len(nodes)) if i not in claimed]

    def bounds(mesh_index: int):
        low = [float("inf")] * 3
        high = [float("-inf")] * 3
        if not isinstance(mesh_index, int) or not 0 <= mesh_index < len(meshes):
            return None
        for prim in meshes[mesh_index].get("primitives") or []:
            ref = (prim.get("attributes") or {}).get("POSITION")
            if not isinstance(ref, int) or not 0 <= ref < len(accessors):
                continue
            accessor = accessors[ref]
            lo, hi = accessor.get("min"), accessor.get("max")
            if not (isinstance(lo, list) and isinstance(hi, list)
                    and len(lo) >= 3 and len(hi) >= 3):
                continue
            for axis in range(3):
                low[axis] = min(low[axis], float(lo[axis]))
                high[axis] = max(high[axis], float(hi[axis]))
        if any(v == float("inf") for v in low):
            return None
        return tuple(low), tuple(high)

    out: list[Solid] = []
    unbounded = 0
    stack = [(i, _IDENTITY, 0) for i in reversed(roots)]
    seen: set[int] = set()
    while stack:
        i, parent, depth = stack.pop()
        if not isinstance(i, int) or not 0 <= i < len(nodes) or depth > MAX_NODE_DEPTH:
            continue
        if i in seen:
            continue
        seen.add(i)
        node = nodes[i]
        if not isinstance(node, dict):
            continue
        world = compose(parent, _node_matrix(node))
        name = str(node.get("name", ""))
        if "mesh" in node and (every_mesh or name_generates_collision(name)):
            box = bounds(node["mesh"])
            if box is None:
                unbounded += 1
            else:
                low, high = hull(world, box[0], box[1])
                out.append(Solid(
                    name or f"node{i}",
                    tuple((low[a] + high[a]) / 2.0 for a in range(3)),
                    tuple(high[a] - low[a] for a in range(3))))
        for child in node.get("children") or []:
            stack.append((child, world, depth + 1))

    if out:
        detail = f"{len(out)} collider(s), e.g. {out[0].name}"
    elif every_mesh:
        detail = "import settings generate physics, but the file has no meshes"
    else:
        detail = (f"{len(seen)} node(s), none named with a "
                  f"{'/'.join(COLLISION_SUFFIXES[:2])} suffix")
    if unbounded:
        detail += f" ({unbounded} collider mesh(es) declare no POSITION bounds)"
    return GlbReading(tuple(out), True, detail)
