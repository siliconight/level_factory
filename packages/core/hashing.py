"""Content hashing.

All hashes are SHA-256 and are rendered as ``sha256:<hex>`` so a hash string
is self-describing wherever it appears (artifact ids, cache keys, provenance).
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from packages.core.canonical import canonical_bytes

_CHUNK = 1024 * 1024


def hash_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def hash_text(text: str) -> str:
    return hash_bytes(text.encode("utf-8"))


def hash_json(obj: Any) -> str:
    """Hash of the canonical serialization of ``obj``."""
    return hash_bytes(canonical_bytes(obj))


def hash_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while True:
            chunk = fh.read(_CHUNK)
            if not chunk:
                break
            h.update(chunk)
    return "sha256:" + h.hexdigest()


def short(hash_str: str, n: int = 12) -> str:
    """Short form of a ``sha256:<hex>`` string, hex portion only."""
    hexpart = hash_str.split(":", 1)[-1]
    return hexpart[:n]


#: What a composed scene points at by PATH rather than by value.
PAYLOAD_SUFFIXES = (".glb", ".gltf", ".bin", ".png", ".jpg", ".jpeg",
                    ".tres", ".res", ".material", ".mesh")


def scene_payload_hashes(scene: Path) -> dict:
    """Content hashes for the art a composed ``.tscn`` references by path.

    A ``.tscn`` names its art -- dressing GLBs, kit GLBs, textures -- with
    stable relative paths, so a rebuilt art pass rewrites 10 MB of GLB while
    the scene's own bytes do not move by one character. An adapter that
    fingerprints the scene with ``hash_file`` alone therefore matches, serves
    the previous answer, and calls it a hit. The only symptom is that nothing
    looks different.

    Observed on 2026-08-03 as ``themed_site_assemble cache`` and
    ``lux_apply cache`` behind a succeeded dressing pass; and again through the
    whole of 2026-08-04, where six fixes landed, every stage above ``lux_apply``
    re-ran, and the shipped LIT scene stayed stale all day.

    Returns ``{}`` for anything that is not a ``.tscn``, so a plain
    ``shell.glb`` input does not start hashing its whole job directory.

    THIS LIVES HERE BECAUSE TWO ADAPTERS NEED IT. It was written inside the Lot
    adapter for the edge that was actively shipping stale art; Lux needed the
    identical rule a day later. A second copy is the drift this toolchain keeps
    paying for -- ``factory_paths`` argues the same about the factory root --
    so it is one function with two importers.

    STILL THE NARROW FIX. The general one is
    ``BuildFingerprint.upstream_artifact_hashes``, which the scheduler reads
    from ``job_spec["upstream_hashes"]`` and which nothing populates, so every
    DAG edge carries this blindness. That stays open (roadmap 39).
    """
    if scene.suffix.lower() != ".tscn" or not scene.is_file():
        return {}
    root = scene.parent
    out: dict[str, str] = {}
    for f in sorted(root.rglob("*")):
        if f.is_file() and f.suffix.lower() in PAYLOAD_SUFFIXES:
            out[str(f.relative_to(root)).replace("\\", "/")] = hash_file(f)
    return out
