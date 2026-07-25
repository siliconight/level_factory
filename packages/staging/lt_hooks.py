"""Bake the Laser Tag map contract into a staged scene (TDD 8, 24.3).

Laser Tag's harness finds what it needs by walking the scene tree for nodes
whose names begin with a fixed set of prefixes -- ``LT_PlayerSpawn``,
``LT_EnemySpawnPoints``, ``LT_ObjectivePoint`` and the optional
``LT_PlayerRoutePoints`` / ``LT_CoverTestPoints``. If they are absent,
``validate_map()`` fails, ``run_evaluation`` returns before a single run, and
the report comes back ``runs: 0, overall_score: 0, grade: "BROKEN"``.

Level Factory had never written any of those nodes. Every Laser Tag job in the
pipeline's history therefore evaluated nothing while reporting a grade, which
reads as "the map is bad" rather than "the map was never played". Lot's walkable
scene already carries the three positions the contract needs on its root node
(``spawn_pos`` / ``objective_pos`` / ``extraction_pos``), so the hooks are
derivable rather than authored: this module reads them and emits the node
blocks.

Pure text in, text out -- the same function stages the scene, backs the
pre-flight check and runs in the tests.
"""
from __future__ import annotations

import math
import re

HOOK_PLAYER_SPAWN = "LT_PlayerSpawn"
HOOK_ENEMY_SPAWNS = "LT_EnemySpawnPoints"
HOOK_OBJECTIVE = "LT_ObjectivePoint"
HOOK_ROUTE = "LT_PlayerRoutePoints"
HOOK_COVER = "LT_CoverTestPoints"

REQUIRED_HOOKS = (HOOK_PLAYER_SPAWN, HOOK_ENEMY_SPAWNS, HOOK_OBJECTIVE)

_ROOT_KEYS = ("spawn_pos", "objective_pos", "extraction_pos")
_VEC3 = re.compile(r'^\s*(\w+)\s*=\s*Vector3\(([^)]*)\)\s*$', re.M)
_SECTION = re.compile(r'^\[', re.M)
_NODE_NAME = re.compile(r'^\[node\s+name="([^"]*)"', re.M)

Vec3 = tuple[float, float, float]


# ---------------------------------------------------------------------------
# reading what the scene already says
# ---------------------------------------------------------------------------
def _root_block(text: str) -> str:
    """The property lines belonging to the first ``[node ...]`` header."""
    start = text.find("[node ")
    if start == -1:
        return ""
    body_start = text.find("\n", start)
    if body_start == -1:
        return ""
    nxt = _SECTION.search(text, body_start + 1)
    return text[body_start:nxt.start()] if nxt else text[body_start:]


def read_root_positions(text: str) -> dict[str, Vec3]:
    """``spawn_pos`` / ``objective_pos`` / ``extraction_pos`` off the root node.

    Only the root node's own block is read: a Vector3 further down the file
    belongs to some other node and would silently move the player spawn.
    """
    found: dict[str, Vec3] = {}
    for key, args in _VEC3.findall(_root_block(text)):
        if key not in _ROOT_KEYS:
            continue
        parts = [p.strip() for p in args.split(",")]
        if len(parts) != 3:
            continue
        try:
            found[key] = (float(parts[0]), float(parts[1]), float(parts[2]))
        except ValueError:
            continue
    return found


def scene_hooks(text: str) -> set[str]:
    """Which contract hook prefixes the scene already declares."""
    names = _NODE_NAME.findall(text)
    return {hook for hook in
            (HOOK_PLAYER_SPAWN, HOOK_ENEMY_SPAWNS, HOOK_OBJECTIVE,
             HOOK_ROUTE, HOOK_COVER)
            if any(n.startswith(hook) for n in names)}


def check_scene_hooks(text: str) -> list[str]:
    """Problems that would make Laser Tag refuse to run this scene.

    A scene passes either because it already carries the hooks or because it
    carries the root positions they can be derived from -- the second case is
    what Lot produces and what staging fills in.
    """
    present = scene_hooks(text)
    missing = [h for h in REQUIRED_HOOKS if h not in present]
    if not missing:
        return []
    if "spawn_pos" in read_root_positions(text):
        return []
    return [
        "scene declares no " + ", ".join(missing)
        + " and no spawn_pos on its root node to derive them from; "
          "Laser Tag would report grade BROKEN without running"
    ]


# ---------------------------------------------------------------------------
# deriving the hooks
# ---------------------------------------------------------------------------
def _lerp(a: Vec3, b: Vec3, t: float) -> Vec3:
    return (a[0] + (b[0] - a[0]) * t,
            a[1] + (b[1] - a[1]) * t,
            a[2] + (b[2] - a[2]) * t)


def _perp_xz(a: Vec3, b: Vec3) -> Vec3:
    dx, dz = b[0] - a[0], b[2] - a[2]
    length = math.hypot(dx, dz)
    if length < 1e-6:
        return (1.0, 0.0, 0.0)
    return (-dz / length, 0.0, dx / length)


def enemy_positions(route: list[Vec3], count: int, *, lateral: float = 1.5) -> list[Vec3]:
    """Spread ``count`` enemy spawns along the mission route.

    Sampling the route rather than ringing the objective matters: the route's
    endpoints are the positions Lot already resolved as standable, and Laser Tag
    fails a spawn that lands inside collision or off the navmesh. Sides
    alternate so two enemies never stack on the centre line.
    """
    count = max(1, int(count))
    pts = [p for p in route if p is not None]
    if len(pts) < 2:
        pts = pts * 2 if pts else [(0.0, 0.0, 0.0)] * 2
    segments = list(zip(pts, pts[1:]))
    lengths = [max(1e-6, math.dist(a, b)) for a, b in segments]
    total = sum(lengths)
    out: list[Vec3] = []
    for i in range(count):
        target = total * (i + 1) / (count + 1)
        walked = 0.0
        pos = pts[-1]
        seg = segments[-1]
        for (a, b), length in zip(segments, lengths):
            if walked + length >= target:
                pos = _lerp(a, b, (target - walked) / length)
                seg = (a, b)
                break
            walked += length
        side = lateral if i % 2 == 0 else -lateral
        px, _, pz = _perp_xz(*seg)
        out.append((round(pos[0] + px * side, 3), round(pos[1], 3),
                    round(pos[2] + pz * side, 3)))
    return out


def cover_positions(objective: Vec3, *, radius: float = 5.0) -> list[Vec3]:
    x, y, z = objective
    return [(round(x + radius, 3), y, round(z, 3)),
            (round(x - radius, 3), y, round(z, 3)),
            (round(x, 3), y, round(z + radius, 3)),
            (round(x, 3), y, round(z - radius, 3))]


# ---------------------------------------------------------------------------
# emitting them
# ---------------------------------------------------------------------------
def _node(name: str, parent: str, pos: Vec3) -> str:
    return (f'\n[node name="{name}" type="Node3D" parent="{parent}"]\n'
            f"transform = Transform3D(1, 0, 0, 0, 1, 0, 0, 0, 1, "
            f"{pos[0]}, {pos[1]}, {pos[2]})\n")


def _insert_at(text: str) -> int:
    """Nodes must precede ``[connection]`` / ``[editable]`` sections."""
    idx = len(text)
    for marker in ("\n[connection ", "\n[editable "):
        found = text.find(marker)
        if found != -1:
            idx = min(idx, found + 1)
    return idx


def inject_lt_hooks(
    text: str, *, enemy_count: int = 6, lateral: float = 1.5,
) -> tuple[str, dict]:
    """Add the Laser Tag hook nodes to a staged scene.

    Returns ``(text, report)``. ``report["injected"]`` names what was added and
    ``report["reason"]`` explains any no-op, so a staging run that could not
    satisfy the contract says so instead of handing Godot a scene that will come
    back ``runs: 0``.
    """
    report: dict = {"injected": [], "reason": "", "enemy_count": 0}
    present = scene_hooks(text)
    if all(h in present for h in REQUIRED_HOOKS):
        report["reason"] = "scene already declares the Laser Tag hooks"
        return text, report

    positions = read_root_positions(text)
    spawn = positions.get("spawn_pos")
    if spawn is None:
        report["reason"] = ("no spawn_pos on the root node; nothing to derive "
                            "the Laser Tag hooks from")
        return text, report
    objective = positions.get("objective_pos")
    extraction = positions.get("extraction_pos")
    derived: list[str] = []
    if objective is None:
        # Better a stated fallback than a scene that cannot be evaluated; the
        # report names it so a missing objective never reads as a real one.
        objective = (spawn[0] + 12.0, spawn[1], spawn[2])
        derived.append("objective_pos")
    route = [spawn, objective] + ([extraction] if extraction is not None else [])

    blocks: list[str] = []
    injected: list[str] = []
    if HOOK_PLAYER_SPAWN not in present:
        blocks.append(_node(HOOK_PLAYER_SPAWN, ".", spawn))
        injected.append(HOOK_PLAYER_SPAWN)
    enemies = enemy_positions(route, enemy_count, lateral=lateral)
    if HOOK_ENEMY_SPAWNS not in present:
        blocks.append(f'\n[node name="{HOOK_ENEMY_SPAWNS}" type="Node3D" parent="."]\n')
        for i, pos in enumerate(enemies):
            blocks.append(_node(f"Enemy_{i}", HOOK_ENEMY_SPAWNS, pos))
        injected.append(HOOK_ENEMY_SPAWNS)
        report["enemy_count"] = len(enemies)
    if HOOK_OBJECTIVE not in present:
        blocks.append(_node(HOOK_OBJECTIVE, ".", objective))
        injected.append(HOOK_OBJECTIVE)
    if HOOK_ROUTE not in present:
        blocks.append(f'\n[node name="{HOOK_ROUTE}" type="Node3D" parent="."]\n')
        for i, pos in enumerate(route):
            blocks.append(_node(f"Route_{i}", HOOK_ROUTE, pos))
        injected.append(HOOK_ROUTE)
    if HOOK_COVER not in present:
        blocks.append(f'\n[node name="{HOOK_COVER}" type="Node3D" parent="."]\n')
        for i, pos in enumerate(cover_positions(objective)):
            blocks.append(_node(f"Cover_{i}", HOOK_COVER, pos))
        injected.append(HOOK_COVER)

    cut = _insert_at(text)
    out = text[:cut] + "".join(blocks) + text[cut:]
    report.update({"injected": injected, "derived": derived,
                   "spawn": spawn, "objective": objective,
                   "reason": "derived from the walkable scene's root positions"})
    return out, report
