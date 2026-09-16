"""Write ``.glb`` files Godot can actually IMPORT, for the import-script tests.

`glb_fixture.py` next door writes a JSON chunk and no binary chunk, because the
collision reader under test parses the container and never loads it. That file
is useless here for exactly that reason: `zoo_worldskin.gd` runs inside Godot's
scene importer, so the fixture has to survive a real import -- vertices in a BIN
chunk, an embedded PNG behind any material that claims a texture, and the node
names Deli Counter really emits.

Frame: metres, glTF's Y-up right-handed convention, which Godot imports without
a basis change. Sizes here are nominal; nothing in these tests measures them.
"""
from __future__ import annotations

import json
import struct
import zlib

_GLB_MAGIC = 0x46546C67
_GLB_JSON = 0x4E4F534A
_GLB_BIN = 0x004E4942

#: A box, as 8 corners and 12 triangles. Winding is not checked by anything
#: here; the importer only needs a well-formed index buffer.
_CORNERS = [(-0.5, -0.5, -0.5), (0.5, -0.5, -0.5), (0.5, 0.5, -0.5),
            (-0.5, 0.5, -0.5), (-0.5, -0.5, 0.5), (0.5, -0.5, 0.5),
            (0.5, 0.5, 0.5), (-0.5, 0.5, 0.5)]
_TRIS = [0, 1, 2, 0, 2, 3, 4, 6, 5, 4, 7, 6, 0, 4, 5, 0, 5, 1,
         1, 5, 6, 1, 6, 2, 2, 6, 7, 2, 7, 3, 3, 7, 4, 3, 4, 0]
#: Any unit normal; these meshes are flat-shaded boxes and no test reads it.
_NORMAL = (0.0, 1.0, 0.0)
_UV = (0.0, 0.0)


def _png(size: int = 4, rgb: tuple = (128, 128, 128)) -> bytes:
    """A solid PNG, written by hand so the fixture needs no imaging library."""
    raw = b"".join(b"\x00" + bytes(rgb) * size for _ in range(size))

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

    ihdr = struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def _pad(buf: bytearray, to: int = 4) -> None:
    while len(buf) % to:
        buf.append(0)


def build_glb(meshes, materials=()) -> bytes:
    """``meshes`` is ``[(node_name, material_index_or_None)]``.

    ``materials`` is ``[(material_name, textured)]``; a textured material gets
    a real embedded PNG, which is what `_kit_material` requires before it will
    take a material as a pack (an untextured one is a greybox fallback, and
    treating it as a skin is the defect this whole pass exists to remove).
    """
    bin_buf = bytearray()
    views: list = []
    accessors: list = []
    textured = any(t for _, t in materials)

    def view(data: bytes, target: int | None = None) -> int:
        _pad(bin_buf)
        off = len(bin_buf)
        bin_buf.extend(data)
        v: dict = {"buffer": 0, "byteOffset": off, "byteLength": len(data)}
        if target is not None:
            v["target"] = target
        views.append(v)
        return len(views) - 1

    pos = b"".join(struct.pack("<3f", *c) for c in _CORNERS)
    nrm = b"".join(struct.pack("<3f", *_NORMAL) for _ in _CORNERS)
    uvs = b"".join(struct.pack("<2f", *_UV) for _ in _CORNERS)
    idx = b"".join(struct.pack("<H", i) for i in _TRIS)
    v_pos, v_nrm, v_uv, v_idx = view(pos), view(nrm), view(uvs), view(idx)
    accessors.append({"bufferView": v_pos, "componentType": 5126, "count": 8,
                      "type": "VEC3",
                      "min": list(min(c[a] for c in _CORNERS) for a in range(3)),
                      "max": list(max(c[a] for c in _CORNERS) for a in range(3))})
    accessors.append({"bufferView": v_nrm, "componentType": 5126, "count": 8,
                      "type": "VEC3"})
    accessors.append({"bufferView": v_uv, "componentType": 5126, "count": 8,
                      "type": "VEC2"})
    accessors.append({"bufferView": v_idx, "componentType": 5123,
                      "count": len(_TRIS), "type": "SCALAR"})

    doc: dict = {"asset": {"version": "2.0"}, "scene": 0,
                 "bufferViews": views, "accessors": accessors}

    if textured:
        img_view = view(_png())
        doc["images"] = [{"bufferView": img_view, "mimeType": "image/png"}]
        doc["samplers"] = [{}]
        doc["textures"] = [{"sampler": 0, "source": 0}]

    mats: list = []
    for name, has_tex in materials:
        pbr: dict = {"baseColorFactor": [0.8, 0.8, 0.8, 1.0]}
        if has_tex:
            pbr["baseColorTexture"] = {"index": 0}
        mats.append({"name": name, "pbrMetallicRoughness": pbr})
    if mats:
        doc["materials"] = mats

    gl_meshes: list = []
    nodes: list = []
    for name, mat_index in meshes:
        prim: dict = {"attributes": {"POSITION": 0, "NORMAL": 1, "TEXCOORD_0": 2},
                      "indices": 3}
        if mat_index is not None:
            prim["material"] = mat_index
        gl_meshes.append({"name": name, "primitives": [prim]})
        nodes.append({"name": name, "mesh": len(gl_meshes) - 1})
    doc["meshes"] = gl_meshes
    doc["nodes"] = nodes
    doc["scenes"] = [{"nodes": list(range(len(nodes)))}]
    doc["buffers"] = [{"byteLength": len(bin_buf)}]

    payload = json.dumps(doc).encode("utf-8")
    payload += b" " * (-len(payload) % 4)
    _pad(bin_buf)
    chunks = (struct.pack("<II", len(payload), _GLB_JSON) + payload
              + struct.pack("<II", len(bin_buf), _GLB_BIN) + bytes(bin_buf))
    return struct.pack("<III", _GLB_MAGIC, 2, 12 + len(chunks)) + chunks


def write_glb(path, meshes, materials=()):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(build_glb(meshes, materials))
    return path
