"""Write real ``.glb`` files for the collision tests.

The reader under test parses the glTF container itself, so feeding it a
hand-rolled dict would test nothing that ships. These helpers emit an actual
binary: the 12-byte header, a JSON chunk, and node/mesh/accessor tables shaped
the way Blender's glTF exporter shapes them. Only ``min``/``max`` on the
``POSITION`` accessor is populated, because that -- deliberately -- is all the
reader needs.
"""
from __future__ import annotations

import json
import struct

_GLB_MAGIC = 0x46546C67
_GLB_JSON = 0x4E4F534A


def gltf_doc(boxes, *, children=None) -> dict:
    """A glTF document with one node per ``(name, centre, size)`` box.

    ``children`` maps a parent name to a list of child names, so a test can
    check that a nested node inherits its parent's transform.
    """
    nodes = []
    meshes = []
    accessors = []
    index = {}
    for name, centre, size in boxes:
        low = [centre[a] - size[a] / 2.0 for a in range(3)]
        high = [centre[a] + size[a] / 2.0 for a in range(3)]
        accessors.append({"type": "VEC3", "componentType": 5126, "count": 8,
                          "min": low, "max": high})
        meshes.append({"name": f"{name}_mesh",
                       "primitives": [{"attributes": {"POSITION": len(accessors) - 1}}]})
        index[name] = len(nodes)
        nodes.append({"name": name, "mesh": len(meshes) - 1})

    claimed = set()
    for parent, kids in (children or {}).items():
        nodes[index[parent]]["children"] = [index[k] for k in kids]
        claimed.update(index[k] for k in kids)

    return {"asset": {"version": "2.0"},
            "scene": 0,
            "scenes": [{"nodes": [i for i in range(len(nodes))
                                  if i not in claimed]}],
            "nodes": nodes, "meshes": meshes, "accessors": accessors}


def pack_glb(doc: dict) -> bytes:
    """``doc`` in a glTF binary container."""
    payload = json.dumps(doc).encode("utf-8")
    payload += b" " * (-len(payload) % 4)
    chunk = struct.pack("<II", len(payload), _GLB_JSON) + payload
    return struct.pack("<III", _GLB_MAGIC, 2, 12 + len(chunk)) + chunk


def write_glb(path, boxes, *, children=None):
    """Write a ``.glb`` at ``path`` holding ``boxes``; return ``path``."""
    path.write_bytes(pack_glb(gltf_doc(boxes, children=children)))
    return path


def slab(name: str, centre=(0.0, -0.15, 0.0), size=(44.0, 0.3, 32.0)):
    """A floor slab the size Deli Counter bakes, with its top at ``y=0``."""
    return (name, centre, size)
