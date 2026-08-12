"""Refuse a walkable scene whose mission points stand over a hole (TDD 24.3).

Laser Tag's ``validate_map()`` fires a ray straight down from above the player
spawn and refuses the map outright if it hits nothing on the World layer
(``NO_WORLD_COLLISION``); its navmesh bake parses static colliders, so a spawn
with no floor beneath it also produces a zero-polygon region and every
reachability test fails. Both come back as ``runs: 0, grade: "BROKEN"`` after
the full evaluation timeout has been spent.

That is worth catching before Godot is ever launched, because the answer is
already sitting in the text of the scene. Lot lays its walkable surface as
explicit ``StaticBody3D`` + ``BoxShape3D`` ground slabs; a mission point with
no slab under it is not a scoring opinion, it is a hole.

The concrete defect this exists to stop: a site whose ground slabs formed a
ring of streets around an unfloored block interior, with the spawn, the
objective, the extraction and every enemy placed inside the void. Lot warned
about the symptom ("isolated buildings", "objective approaches: 0") and the
pipeline ran the evaluation anyway.

What the parser can and cannot see is deliberately explicit. Box colliders
written into the scene text are read; so is the collision baked inside an
instanced ``.glb``, via :mod:`packages.validation.glb_collision`. Whatever is
still unreadable after that is reported as opaque and named in the message --
a scene that declares no readable collision whatsoever is called out as
unreadable rather than quietly passing.

Reading into the ``.glb`` matters more than it sounds. The first version of
this module stopped at the binary and reported a floored site as a void: "12 of
15 mission point(s) have no ground beneath them (collision inside 5 instanced
resource(s) is not readable from the scene text)". The parenthesis is the
module admitting it cannot see, in the same sentence as a hard blocker that
says it is not there. A check gets one of those two positions, not both.

Pure text in, findings out -- the same functions back the adapter's pre-flight
and run in the tests.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from packages.validation import glb_collision

Vec3 = tuple[float, float, float]

#: A point is standing on a slab if the slab's top is no more than this far
#: above it (spawns sit a little inside the surface they rest on).
STAND_TOLERANCE = 0.6
#: ...and no more than this far below it. Beyond this the point is not
#: standing on the slab, it is falling towards it.
MAX_DROP = 4.0
#: Slack on the footprint edges, so a point on a slab's seam still counts.
EDGE_MARGIN = 0.05

#: A basis is honoured when each axis still maps to an axis -- the 90-degree
#: building rotations Lot writes stay exactly describable as a box. Anything
#: else is a footprint this reader cannot state without inventing area, so it
#: is reported opaque instead.
AXIS_EPSILON = 1e-6

#: A ``CollisionShape3D`` only becomes solid ground under a body that stops a
#: ray. ``Area3D`` is a ``CollisionObject3D`` too, but it is a trigger volume:
#: Lot writes one per ladder, and counting a ladder's climb volume as floor
#: would floor a mission point standing in mid-air beside the wall.
#:
#: This is deliberately a list of what to *exclude* rather than a whitelist of
#: solid bodies. A whitelist would silently drop the floor under any body type
#: not thought of here -- CSG shapes, a scripted body, whatever Godot adds next
#: -- and dropping a real floor is exactly the direction that produced the
#: false blocker this module exists to stop. Erring towards "there is ground
#: here" is the safe error for a check whose output refuses a build.
TRIGGER_BODIES = ("Area3D",)

_IDENTITY = ((1.0, 0.0, 0.0, 0.0), (0.0, 1.0, 0.0, 0.0), (0.0, 0.0, 1.0, 0.0))
# The attribute run is matched greedily to the LAST bracket on the line, not
# up to the first one. A section header may legally contain a bracket inside an
# attribute value -- `groups=["ladder"]` is the one Lot writes -- and a pattern
# that stopped at the first `]` did not match those headers at all. Missing a
# header is not a missing attribute: the node never entered `frames` or
# `types`, so its children composed against the identity and its body type was
# unknown. Concretely, Lot's four ladder climb volumes are `Area3D` nodes with
# a group, so every one of them was read as a solid 1.3 x 5 x 1.3 floor slab
# standing at the world origin -- a trigger counted as ground, in a place the
# scene never put it.
_SECTION = re.compile(r"^\[(\w+)(.*)\][ \t]*$", re.M)
_ATTR = re.compile(r'(\w+)=(?:"([^"]*)"|(\S+))')
_TRANSFORM = re.compile(r"^transform\s*=\s*Transform3D\(([^)]*)\)", re.M)
_SIZE = re.compile(r"^size\s*=\s*Vector3\(([^)]*)\)", re.M)
_SHAPE = re.compile(r'^shape\s*=\s*SubResource\("([^"]*)"\)', re.M)
_EXT = re.compile(r'ExtResource\("([^"]*)"\)')
_HOOK_PREFIXES = ("LT_PlayerSpawn", "LT_EnemySpawnPoints", "LT_ObjectivePoint",
                  "LT_PlayerRoutePoints", "LT_CoverTestPoints")


@dataclass(frozen=True)
class Box:
    """An axis-aligned box collider, positioned in scene-root space.

    ``approximate`` marks a box that is the BOUNDING BOX of a collision mesh
    rather than a shape that is genuinely a box. A wall mesh with doorways cut
    in it reduces to a solid box across every opening, so an approximate box
    can seal a building this reader has no way to see into.

    Measured 2026-08-09: `cr_garage` declares seven ground-level entries,
    including two 5 m garage doors, and its collision read as an unbroken ring
    at 0.5 m cells. Under this model no mission point inside any building can
    be reachable.

    Nothing in this module treats the two kinds differently. The flag exists so
    a caller deciding whether to REFUSE A BUILD can tell a wall it measured
    from a wall it inferred -- see `spawn_placement._optimistic_reach`.
    """

    name: str
    centre: Vec3
    size: Vec3
    approximate: bool = False

    @property
    def top(self) -> float:
        return self.centre[1] + self.size[1] / 2.0

    def covers(self, x: float, z: float, *, margin: float = EDGE_MARGIN) -> bool:
        return (abs(x - self.centre[0]) <= self.size[0] / 2.0 + margin
                and abs(z - self.centre[2]) <= self.size[2] / 2.0 + margin)


@dataclass(frozen=True)
class Reading:
    """What could be read out of a scene, including what could not."""

    boxes: tuple[Box, ...]
    opaque: tuple[str, ...]

    @property
    def readable(self) -> bool:
        return bool(self.boxes)


# ---------------------------------------------------------------------------
# reading the scene text
# ---------------------------------------------------------------------------
def _floats(raw: str) -> list[float]:
    out: list[float] = []
    for part in raw.split(","):
        try:
            out.append(float(part.strip()))
        except ValueError:
            return []
    return out


def _attrs(raw: str) -> dict[str, str]:
    return {key: quoted if quoted else bare
            for key, quoted, bare in _ATTR.findall(raw)}


def _sections(text: str) -> list[tuple[str, dict[str, str], str]]:
    """``(kind, attributes, body)`` for every ``[...]`` section, in order."""
    out: list[tuple[str, dict[str, str], str]] = []
    matches = list(_SECTION.finditer(text))
    for i, match in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        out.append((match.group(1), _attrs(match.group(2)), text[match.end():end]))
    return out


def _node_path(name: str, parent: str) -> str:
    """Godot writes the same parent three ways; normalise to one."""
    parent = parent.strip()
    if parent.startswith("./"):
        parent = parent[2:]
    if parent in ("", "."):
        return name
    return f"{parent}/{name}"


def _transform(body: str):
    """The node's own transform as a 3x4 matrix; a missing one is the identity.

    Godot writes ``Transform3D`` as the three basis columns followed by the
    origin, so the row-major matrix this reader uses is a transpose away.
    """
    match = _TRANSFORM.search(body)
    if match is None:
        return _IDENTITY
    values = _floats(match.group(1))
    if len(values) != 12:
        return _IDENTITY
    return tuple(tuple(values[3 * col + row] for col in range(3))
                 + (values[9 + row],) for row in range(3))


def axis_aligned(matrix) -> bool:
    """Whether the basis maps every axis onto an axis (any 90-degree turn)."""
    for col in range(3):
        nonzero = [row for row in range(3)
                   if abs(matrix[row][col]) > AXIS_EPSILON]
        if len(nonzero) != 1:
            return False
    return True


def _origin(matrix) -> Vec3:
    return (matrix[0][3], matrix[1][3], matrix[2][3])


def _placed(matrix, centre: Vec3, size: Vec3) -> tuple[Vec3, Vec3]:
    """A box carried through ``matrix``, as ``(centre, size)``."""
    half = tuple(abs(value) / 2.0 for value in size)
    low, high = glb_collision.hull(
        matrix,
        tuple(centre[a] - half[a] for a in range(3)),
        tuple(centre[a] + half[a] for a in range(3)))
    return (tuple((low[a] + high[a]) / 2.0 for a in range(3)),
            tuple(high[a] - low[a] for a in range(3)))


def read_scene(path: Path, *, _seen: frozenset[Path] = frozenset()) -> Reading:
    """Box colliders and unreadable instances in the scene at ``path``.

    Sub-scenes instanced through a sibling ``.tscn`` are followed and their
    boxes offset by the instance's own position, because that is exactly how
    Lot splits a walkable level: the mission scene instances the greybox, and
    the greybox is where the ground lives.
    """
    path = Path(path)
    if path in _seen or not path.is_file():
        return Reading((), (str(path.name),) if not path.is_file() else ())
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return Reading((), (str(path.name),))
    return read_scene_text(text, resolve=resolver(path.parent),
                           _seen=_seen | {path})


def resolver(scene_dir):
    """An ``ext_resource`` path -> a file on disk, for scenes staged as a pack.

    Three forms turn up in practice and all three have to land. ``res://name``
    is the ordinary project-relative reference. ``res://C:/...`` is what Lot
    writes for a non-portable local preview, where the absolute path after the
    scheme is the real one. And a bare filename is resolved beside the scene.
    Falling back to the basename matters most: a mission scene and the shell it
    instances routinely sit in different job directories, and a resolver that
    only tried the literal path would report the shell opaque and call a
    floored building a hole.
    """
    scene_dir = Path(scene_dir)

    def resolve(target: str):
        raw = str(target)
        rel = raw[len("res://"):] if raw.startswith("res://") else raw
        for candidate in (Path(rel), scene_dir / rel,
                          scene_dir / Path(rel).name):
            try:
                if candidate.is_file():
                    return candidate
            except OSError:
                continue
        return scene_dir / Path(rel).name

    return resolve


def read_scene_text(
    text: str,
    *,
    resolve=None,
    _seen: frozenset[Path] = frozenset(),
) -> Reading:
    """``read_scene`` for text already in hand. ``resolve`` maps a
    ``res://name`` reference to a path, or is ``None`` to not follow any."""
    box_sizes: dict[str, Vec3] = {}
    shape_types: dict[str, str] = {}
    ext_paths: dict[str, str] = {}
    for kind, attrs, body in _sections(text):
        if kind == "ext_resource":
            ext_paths[attrs.get("id", "")] = attrs.get("path", "")
        elif kind == "sub_resource":
            shape_types[attrs.get("id", "")] = attrs.get("type", "")
            if attrs.get("type") != "BoxShape3D":
                continue
            match = _SIZE.search(body)
            values = _floats(match.group(1)) if match else []
            if len(values) == 3:
                box_sizes[attrs.get("id", "")] = (values[0], values[1], values[2])

    frames: dict[str, tuple] = {"": _IDENTITY}
    types: dict[str, str] = {}
    boxes: list[Box] = []
    opaque: list[str] = []

    for kind, attrs, body in _sections(text):
        if kind != "node":
            continue
        name = attrs.get("name", "")
        full = _node_path(name, attrs.get("parent", ""))
        parent = full[:full.rfind("/")] if "/" in full else ""
        world = glb_collision.compose(frames.get(parent, _IDENTITY),
                                      _transform(body))
        frames[full] = world
        types[full] = attrs.get("type", "")

        instance = attrs.get("instance", "")
        if instance:
            ref = _EXT.search(instance)
            target = ext_paths.get(ref.group(1), "") if ref else ""
            sub = _instanced(target, world, resolve, _seen)
            boxes.extend(sub.boxes)
            opaque.extend(sub.opaque)
            continue

        if attrs.get("type") != "CollisionShape3D":
            continue
        if types.get(parent, "") in TRIGGER_BODIES:
            # A trigger volume, not a surface. Not opaque either: what it is is
            # known exactly, and it is known not to be ground.
            continue
        shape = _SHAPE.search(body)
        if shape is None or shape.group(1) not in box_sizes:
            # Name the shape. "Player/col" leaves an operator hunting; "Player/
            # col (CapsuleShape3D)" says at a glance that this is a character
            # capsule the reader was never going to size, not a missing floor.
            kind_of = shape_types.get(shape.group(1), "") if shape else ""
            opaque.append(f"{full} ({kind_of})" if kind_of
                          else f"{full} (no box shape)")
            continue
        if not axis_aligned(world):
            # The footprint is no longer axis-aligned and this reader cannot
            # honestly describe it as a box.
            opaque.append(full)
            continue
        centre, size = _placed(world, (0.0, 0.0, 0.0), box_sizes[shape.group(1)])
        boxes.append(Box(full, centre, size))

    return Reading(tuple(boxes), tuple(opaque))


def _instanced(target: str, at, resolve, seen: frozenset[Path]) -> Reading:
    """The collision an instanced resource brings, placed by ``at``."""
    name = target.rsplit("/", 1)[-1]
    label = name or "<unnamed instance>"
    if resolve is None:
        return Reading((), (label,))

    lower = name.lower()
    if lower.endswith((".glb", ".gltf")):
        # The collision is inside an imported binary, but the binary describes
        # it: Godot bodies the `-col` nodes, and their extent is in the glTF
        # JSON. Read it rather than calling the building a hole.
        reading = glb_collision.collision_solids(resolve(target))
        if not reading.read:
            return Reading((), (f"{label} ({reading.detail})",))
        if not axis_aligned(at):
            return Reading((), (f"{label} (placed at a non-axis rotation)",))
        placed = []
        for solid in reading.solids:
            centre, size = _placed(at, solid.centre, solid.size)
            # APPROXIMATE by construction: `collision_solids` reports each
            # collision MESH's bounding box, and a mesh is where the doorways
            # are. See `Box`.
            placed.append(Box(f"{label}:{solid.name}", centre, size,
                              approximate=True))
        return Reading(tuple(placed), ())

    if not lower.endswith((".tscn", ".scn")):
        return Reading((), (label,))
    if lower.endswith(".scn"):
        return Reading((), (f"{label} (binary scene is not readable as text)",))

    sub = read_scene(Path(resolve(target)), _seen=seen)
    if sub.boxes and not axis_aligned(at):
        return Reading((), (f"{label} (placed at a non-axis rotation)",))
    moved = []
    for box in sub.boxes:
        centre, size = _placed(at, box.centre, box.size)
        # The flag rides through the instance transform with the box: geometry
        # inferred inside the sub-scene is still inferred out here.
        moved.append(Box(f"{name}:{box.name}", centre, size,
                         approximate=box.approximate))
    return Reading(tuple(moved), tuple(f"{name}:{o}" for o in sub.opaque))


# ---------------------------------------------------------------------------
# the points that have to stand on something
# ---------------------------------------------------------------------------
def mission_points(text: str) -> dict[str, Vec3]:
    """Every position the mission needs to be standable, in scene-root space.

    Declared ``LT_*`` hook nodes are preferred; a scene that has not been
    staged yet carries the same information as ``spawn_pos`` / ``objective_pos``
    / ``extraction_pos`` on its root node, and those are read instead.
    """
    from packages.staging.lt_hooks import read_root_positions

    points: dict[str, Vec3] = {}
    frames: dict[str, tuple] = {"": _IDENTITY}
    for kind, attrs, body in _sections(text):
        if kind != "node":
            continue
        name = attrs.get("name", "")
        full = _node_path(name, attrs.get("parent", ""))
        parent = full[:full.rfind("/")] if "/" in full else ""
        matrix = glb_collision.compose(frames.get(parent, _IDENTITY),
                                       _transform(body))
        frames[full] = matrix
        world = _origin(matrix)
        if any(part.startswith(_HOOK_PREFIXES) for part in full.split("/")):
            # The group nodes themselves carry no position worth testing; their
            # children are the spawns.
            if name.startswith(("LT_EnemySpawnPoints", "LT_PlayerRoutePoints",
                                "LT_CoverTestPoints")):
                continue
            points[full] = world

    if points:
        return points
    return {f"root.{key}": value for key, value in read_root_positions(text).items()}


# ---------------------------------------------------------------------------
# the check
# ---------------------------------------------------------------------------
def support_under(point: Vec3, boxes) -> Box | None:
    """The highest box the point could be standing on, or ``None``."""
    best: Box | None = None
    for box in boxes:
        if not box.covers(point[0], point[2]):
            continue
        drop = point[1] - box.top
        if drop > MAX_DROP or drop < -STAND_TOLERANCE:
            continue
        if best is None or box.top > best.top:
            best = box
    return best


def check_ground_contact(scene: Path) -> list[str]:
    """Problems that would make Laser Tag refuse the scene at ``scene``."""
    scene = Path(scene)
    if not scene.is_file():
        return []
    text = scene.read_text(encoding="utf-8", errors="replace")
    return check_ground_contact_text(
        text, read_scene_text(text, resolve=resolver(scene.parent),
                              _seen=frozenset({scene})))


def check_ground_contact_text(text: str, reading: Reading) -> list[str]:
    """The pure form: scene text plus what was read out of it and its subscenes."""
    points = mission_points(text)
    if not points:
        # Nothing to stand anywhere. check_scene_hooks owns that complaint;
        # staying silent here keeps one defect to one message.
        return []

    if not reading.readable:
        where = ", ".join(reading.opaque[:4]) or "nothing"
        return [
            "walkable scene declares no readable box collision "
            f"({where}) — Laser Tag's world-collision ray would have nothing "
            "to hit and its navmesh would bake zero polygons"
        ]

    floating = [name for name, point in points.items()
                if support_under(point, reading.boxes) is None]
    if not floating:
        return []

    shown = ", ".join(sorted(floating)[:6])
    if len(floating) > 6:
        shown += f", and {len(floating) - 6} more"
    detail = ""
    if reading.opaque:
        # Name them. "N resources are unreadable" tells an operator that the
        # verdict is partly a guess without telling them which file to go and
        # look at, which is most of the way back to saying nothing at all.
        named = "; ".join(sorted(reading.opaque)[:3])
        if len(reading.opaque) > 3:
            named += f"; and {len(reading.opaque) - 3} more"
        detail = (f" (collision in {len(reading.opaque)} instanced "
                  f"resource(s) could not be read, so some of these may be "
                  f"floored after all: {named})")
    return [
        f"{len(floating)} of {len(points)} mission point(s) have no ground "
        f"beneath them: {shown}{detail}; Laser Tag would refuse the map with "
        "NO_WORLD_COLLISION and complete zero runs"
    ]
