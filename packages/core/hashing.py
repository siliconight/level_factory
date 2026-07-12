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
