"""Probe: build an EMBEDDED-texture copy of a package, for the size comparison.

KEPT RATHER THAN DELETED, because the figures it produced are the ones
0.105.1 retracted and replaced, and a figure nobody can reproduce is how the
first pair got published. Run it again when there is runtime telemetry to
re-price externalisation against.

Zoo 1.2.0's externalisation has no inverse in the toolchain, so the "before"
side of the ship-size and video-memory figures had nothing real to measure
against. This is that inverse, written for the measurement and nothing else:
it walks a package, pulls each GLB's external images back into its binary
chunk as Blender's exporter would have left them -- one bufferView per image,
4-byte aligned -- and deletes the texture files that nothing references any
more.

It prints what it measured. It names no cause.

    python tools/reembed_textures.py <src package> <dst package>

The output is a valid package with the same geometry and the same pixels,
differing only in where the pixels live -- which is the one variable the
figures are about. `packages.exporting.glb_refs` reads 0 external references
in it and 1,264 in the package it was built from.

Measured 2026-09-22 on `LF_club_block_007.portable-godot`:

    embedded      54,417,170 B   51.90 MiB     676 files
    externalised  28,917,538 B   27.58 MiB   1,064 files   -46.9%

Pair it with `texture_binding_probe.gd` for the video-memory half.
"""
from __future__ import annotations

import json
import shutil
import struct
import sys
import urllib.parse
from pathlib import Path

MAGIC = 0x46546C67
JSONC = 0x4E4F534A
BINC = 0x004E4942
MIME = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}


def _pad4(n):
    return (-n) % 4


def split(data):
    assert struct.unpack_from("<I", data, 0)[0] == MAGIC
    off, js, binc = 12, None, b""
    while off + 8 <= len(data):
        clen, ctype = struct.unpack_from("<II", data, off)
        body = data[off + 8:off + 8 + clen]
        if ctype == JSONC:
            js = json.loads(body.decode("utf-8"))
        elif ctype == BINC:
            binc = body
        off += 8 + clen + _pad4(clen)
    return js, binc


def join(js, binc):
    body = json.dumps(js, separators=(",", ":"), allow_nan=False).encode("utf-8")
    body += b" " * _pad4(len(body))
    binc = binc + b"\0" * _pad4(len(binc))
    out = struct.pack("<III", MAGIC, 2, 12 + 8 + len(body) + (8 + len(binc) if binc else 0))
    out += struct.pack("<II", len(body), JSONC) + body
    if binc:
        out += struct.pack("<II", len(binc), BINC) + binc
    return out


def embed(path: Path) -> tuple[int, int, list[Path]]:
    """Pull `path`'s external images into its binary chunk. Returns
    (images embedded, bytes after, the texture files it consumed)."""
    js, binc = split(path.read_bytes())
    images = js.get("images") or []
    used: list[Path] = []
    n = 0
    views = js.setdefault("bufferViews", [])
    binc = bytearray(binc)
    for im in images:
        uri = im.get("uri")
        if not uri or uri.startswith("data:"):
            continue
        rel = urllib.parse.unquote(uri)
        src = path.parent / rel
        if not src.is_file():
            raise SystemExit("%s names %s and it is not there" % (path, rel))
        blob = src.read_bytes()
        # Blender's exporter appends each image as its own bufferView, 4-byte
        # aligned, which is what `gltf_textures` reads back out.
        binc += b"\0" * _pad4(len(binc))
        views.append({"buffer": 0, "byteOffset": len(binc),
                      "byteLength": len(blob)})
        binc += blob
        im.pop("uri")
        im["bufferView"] = len(views) - 1
        im["mimeType"] = MIME[src.suffix.lower()]
        used.append(src)
        n += 1
    if not n:
        return 0, path.stat().st_size, []
    js["buffers"] = [{"byteLength": len(binc)}]
    path.write_bytes(join(js, bytes(binc)))
    return n, path.stat().st_size, used


def tree_bytes(root: Path) -> tuple[int, int]:
    files = [p for p in root.rglob("*") if p.is_file()]
    return sum(p.stat().st_size for p in files), len(files)


def main(argv):
    if len(argv) != 2:
        raise SystemExit("usage: reembed_textures.py <src package> <dst package>")
    src, dst = Path(argv[0]), Path(argv[1])
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)
    before_bytes, before_files = tree_bytes(dst)
    consumed: set[Path] = set()
    embedded = 0
    glbs = sorted(dst.rglob("*.glb"))
    for g in glbs:
        n, _size, used = embed(g)
        embedded += n
        consumed.update(p.resolve() for p in used)
    # Drop texture files nothing references any more.
    dropped = 0
    for p in sorted(consumed):
        if p.is_file():
            p.unlink()
            dropped += 1
        imp = Path(str(p) + ".import")
        if imp.is_file():
            imp.unlink()
    after_bytes, after_files = tree_bytes(dst)
    print("src %s" % src)
    print("dst %s" % dst)
    print("  glbs                 %d" % len(glbs))
    print("  images embedded      %d" % embedded)
    print("  texture files gone   %d" % dropped)
    print("  bytes  externalised  %d  (%d files)" % (before_bytes, before_files))
    print("  bytes  embedded      %d  (%d files)" % (after_bytes, after_files))
    print("  delta                %+d bytes  (%.1f MiB -> %.1f MiB)"
          % (after_bytes - before_bytes, before_bytes / 1048576.0,
             after_bytes / 1048576.0))


if __name__ == "__main__":
    main(sys.argv[1:])
