"""Set or clear the collision a ``.glb`` generates, one policy per file.

THE FLAG IS A NODE NAME. Godot's glTF importer has no collision field to
toggle: it reads the node's NAME and generates a physics body when that name
ends in one of the `-col` family. So "flipping collision on a .glb" is a rename
inside the JSON chunk, and nothing else in the file moves -- no vertex is
touched, no accessor shifts, the BIN chunk is copied through byte for byte.

WHY WHOLE-FILE AND NOT PER-NODE. An asset has one answer to "does this collide"
in every place this pipeline asks. Surface dressing is collisionless BY
DEFINITION -- `dressing_scene.check_manifest` refuses to write a scene whose
orders carry a collision policy -- and a shell exists to be stood on. Naming
individual nodes would let a file be half of each, which is a state no consumer
here can represent.

THE VOCABULARY IS THE READER'S, NOT A SECOND COPY.
`packages.validation.glb_collision` already knows which suffixes Godot matches,
that the match is case-insensitive, and that Blender appends `.001` AFTER the
marker. This module imports all three facts. If Godot's list ever changes, it
changes in one file and both directions follow.

WHAT THIS REFUSES TO DO, AND WHY IT MATTERS MOST.
A sibling ``<file>.glb.import`` carrying `generate/physics=true` makes Godot
body EVERY mesh regardless of what the nodes are called. Clearing the suffixes
under that setting produces a file that reads as collisionless and imports with
collision on everything. This refuses rather than reporting a success the
engine will contradict -- the same failure shape as measuring a MultiMesh
buffer through the dummy renderer and believing the answer.

Every write is verified by re-reading the result through the reader, which is
an independent implementation of the question. Bytes out, boxes back in.
"""
from __future__ import annotations

import json
import struct
from dataclasses import dataclass, field
from pathlib import Path

from packages.validation.glb_collision import (
    COLLISION_SUFFIXES, collision_solids, import_requests_physics, json_chunk,
    name_generates_collision, strip_duplicate)

_GLB_MAGIC = 0x46546C67
_GLB_JSON = 0x4E4F534A

#: `none` clears; every other policy is a suffix from the reader's list, named
#: without its hyphen. Derived, so a new suffix over there appears here.
NONE = "none"
POLICIES = (NONE,) + tuple(s[1:] for s in COLLISION_SUFFIXES)


class GlbCollisionError(ValueError):
    """The file cannot be rewritten, and writing it anyway would be worse."""


@dataclass
class Report:
    """What changed, and what the result reads back as."""

    policy: str
    renamed: list = field(default_factory=list)   # (before, after)
    mesh_nodes: int = 0
    colliders_before: int = 0
    colliders_after: int = 0
    detail: str = ""

    def as_dict(self) -> dict:
        return {"policy": self.policy, "mesh_nodes": self.mesh_nodes,
                "renamed": [{"from": a, "to": b} for a, b in self.renamed],
                "colliders_before": self.colliders_before,
                "colliders_after": self.colliders_after,
                "detail": self.detail}


def suffix_for(policy: str) -> str | None:
    """The suffix a policy writes, or ``None`` for `none`."""
    if policy == NONE:
        return None
    if policy not in POLICIES:
        raise GlbCollisionError(
            f"unknown collision policy {policy!r}; expected one of "
            + ", ".join(POLICIES))
    return "-" + policy


def strip_collision(name: str) -> str:
    """``name`` with any collision suffix removed, keeping Blender's tail.

    `floor-colonly.001` -> `floor.001`. A name that generates no collision
    comes back unchanged, INCLUDING its surrounding whitespace being trimmed
    only when there was a suffix to remove -- so a no-op is a true no-op and
    the rename list stays honest about what moved.
    """
    if not name_generates_collision(name):
        return name
    stem, tail = strip_duplicate(name)
    lowered = stem.lower()
    for suffix in sorted(COLLISION_SUFFIXES, key=len, reverse=True):
        if lowered.endswith(suffix):
            return stem[:-len(suffix)] + tail
    return name          # unreachable while the two agree; not a silent pass


def with_collision(name: str, suffix: str) -> str:
    """``name`` carrying exactly ``suffix``, before Blender's `.001` tail."""
    bare = strip_collision(name)
    stem, tail = strip_duplicate(bare)
    return stem + suffix + tail


def retag(doc: dict, policy: str) -> tuple[dict, Report]:
    """A copy of ``doc`` with the policy applied. Pure -- no file, no bytes.

    ONLY NODES THAT CARRY A MESH GAIN A SUFFIX. A suffix on a node with no mesh
    generates nothing in Godot and leaves a name that lies about the file.
    Clearing, by contrast, applies to EVERY node: if a stale marker is sitting
    on an empty, `none` means none.
    """
    suffix = suffix_for(policy)
    nodes = doc.get("nodes")
    if not isinstance(nodes, list):
        raise GlbCollisionError("glTF document declares no nodes")

    out = json.loads(json.dumps(doc))
    report = Report(policy=policy)
    for node in out["nodes"]:
        if not isinstance(node, dict):
            continue
        before = node.get("name")
        if not isinstance(before, str):
            continue
        has_mesh = isinstance(node.get("mesh"), int)
        if has_mesh:
            report.mesh_nodes += 1
        if name_generates_collision(before):
            report.colliders_before += 1
        after = (with_collision(before, suffix)
                 if suffix is not None and has_mesh else strip_collision(before))
        if after != before:
            node["name"] = after
            report.renamed.append((before, after))
        if name_generates_collision(after):
            report.colliders_after += 1
    return out, report


def repack(data: bytes, doc: dict) -> bytes:
    """``data`` with its JSON chunk replaced by ``doc``, everything else kept.

    The JSON chunk is padded with SPACES and a BIN chunk with zeroes -- that is
    the spec, not a preference, and a zero-padded JSON chunk is rejected by
    strict readers. Trailing chunks are copied through untouched, which is what
    makes this safe for a real Blender export: the geometry never moves, so the
    accessor offsets that point into it stay correct by construction.
    """
    if len(data) < 20:
        raise GlbCollisionError("not a .glb: shorter than a GLB header")
    magic, version, _length = struct.unpack_from("<III", data, 0)
    if magic != _GLB_MAGIC:
        raise GlbCollisionError("not a .glb: bad magic")

    payload = json.dumps(doc, ensure_ascii=False, separators=(",", ":")
                         ).encode("utf-8")
    payload += b" " * (-len(payload) % 4)

    offset, rebuilt, replaced = 12, [], False
    while offset + 8 <= len(data):
        size, kind = struct.unpack_from("<II", data, offset)
        end = offset + 8 + size + (-size % 4)
        if kind == _GLB_JSON and not replaced:
            rebuilt.append(struct.pack("<II", len(payload), _GLB_JSON) + payload)
            replaced = True
        else:
            rebuilt.append(data[offset:end])
        offset = end
    if not replaced:
        raise GlbCollisionError("not a .glb: no JSON chunk to replace")

    body = b"".join(rebuilt)
    return struct.pack("<III", _GLB_MAGIC, version, 12 + len(body)) + body


def apply_to_file(path, policy: str, *, out=None, in_place: bool = False) -> Report:
    """Rewrite one ``.glb``, then read the result back to check the claim."""
    path = Path(path)
    suffix_for(policy)                     # reject an unknown policy up front
    if out is None and not in_place:
        raise GlbCollisionError(
            "refusing to guess: pass out= for a copy, or in_place=True")
    if out is not None and in_place:
        raise GlbCollisionError("out= and in_place are mutually exclusive")
    destination = Path(out) if out is not None else path
    if not path.is_file():
        raise GlbCollisionError(f"no such file: {path}")

    if policy == NONE and import_requests_physics(path):
        raise GlbCollisionError(
            f"{path.name} has a sibling .import with generate/physics=true, "
            "which bodies EVERY mesh whatever the nodes are called. Clearing "
            "the suffixes here would produce a file that reads as "
            "collisionless and imports with collision on everything. Change "
            "the import setting, or accept that this file collides.")

    data = path.read_bytes()
    doc = json_chunk(data)
    if doc is None:
        raise GlbCollisionError(f"{path.name}: glTF JSON chunk could not be read")

    new_doc, report = retag(doc, policy)
    rewritten = repack(data, new_doc)

    # THE CLAIM, CHECKED BY THE OTHER IMPLEMENTATION. `collision_solids` walks
    # the container and the node tree independently of everything above; if it
    # disagrees, the write is abandoned rather than explained.
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(rewritten)
    reading = collision_solids(destination)
    if not reading.read:
        destination.unlink(missing_ok=True) if out is not None else None
        raise GlbCollisionError(
            f"the rewritten file did not read back: {reading.detail}")
    want_none = policy == NONE
    if want_none and reading.solids:
        raise GlbCollisionError(
            f"asked for {policy}, but the result still reads "
            f"{len(reading.solids)} collider(s)")
    if not want_none and report.mesh_nodes and not reading.solids:
        raise GlbCollisionError(
            f"asked for {policy}, but the result reads no colliders at all")
    report.detail = (f"{destination.name}: {len(reading.solids)} collider(s) "
                     f"after, {report.colliders_before} before")
    return report


def main(argv=None) -> int:
    import argparse
    import sys

    ap = argparse.ArgumentParser(
        prog="glb_collision_flag",
        description="Set or clear the collision a .glb generates in Godot.")
    ap.add_argument("glb", nargs="+")
    ap.add_argument("--collision", required=True, choices=POLICIES,
                    help="none clears every marker; the rest name the suffix "
                         "Godot matches (colonly renders nothing and collides, "
                         "col does both)")
    ap.add_argument("--out", help="write here instead (single input only)")
    ap.add_argument("--in-place", action="store_true")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)

    if a.out and len(a.glb) > 1:
        sys.stderr.write("[glb-col] --out takes a single input\n")
        return 2
    reports = []
    for name in a.glb:
        try:
            reports.append(apply_to_file(name, a.collision, out=a.out,
                                         in_place=a.in_place))
        except GlbCollisionError as exc:
            sys.stderr.write(f"[glb-col] refused: {exc}\n")
            return 2
    if a.json:
        print(json.dumps([r.as_dict() for r in reports], indent=2))
    else:
        for name, r in zip(a.glb, reports):
            sys.stderr.write(
                f"[glb-col] {Path(name).name} -> {r.policy}: "
                f"{len(r.renamed)} of {r.mesh_nodes} mesh node(s) renamed, "
                f"colliders {r.colliders_before} -> {r.colliders_after}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
