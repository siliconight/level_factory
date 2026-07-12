"""Canonical, deterministic JSON serialization.

Determinism is a feature (TDD 5.3). Every fingerprint, cache key, and build
lock depends on a stable byte representation of structured data. This module is
the single source of truth for how Level Factory turns Python data into bytes.
"""
from __future__ import annotations

import json
from typing import Any


def canonical_dumps(obj: Any) -> str:
    """Serialize ``obj`` to a canonical string.

    - keys sorted
    - no insignificant whitespace
    - UTF-8 preserved (ensure_ascii=False)
    - trailing newline for POSIX-friendly files
    """
    return json.dumps(
        obj,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ) + "\n"


def canonical_bytes(obj: Any) -> bytes:
    return canonical_dumps(obj).encode("utf-8")


def pretty_dumps(obj: Any) -> str:
    """Human-facing, still deterministic (sorted keys, 2-space indent)."""
    return json.dumps(obj, sort_keys=True, indent=2, ensure_ascii=False) + "\n"
