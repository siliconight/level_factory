"""Identifier and slug helpers.

Ids are deterministic and human-legible. We never use random UUIDs for things
that should be reproducible from the same inputs (candidate ids, job ids).
"""
from __future__ import annotations

import re

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def slugify(text: str) -> str:
    s = _SLUG_RE.sub("_", text.strip().lower()).strip("_")
    return s or "unnamed"


def candidate_id(mission_id: str, seed: int) -> str:
    return f"{mission_id}.candidate.seed_{seed}"


def job_id(mission_id: str, stage: str, *, candidate: str | None = None) -> str:
    if candidate:
        # candidate ids already carry the mission prefix; keep the suffix only.
        suffix = candidate.split(".", 1)[-1]
        return f"{mission_id}.{stage}.{suffix}"
    return f"{mission_id}.{stage}"


def namespaced_anchor(mission_id: str, anchor_id: str) -> str:
    if anchor_id.startswith(f"{mission_id}/"):
        return anchor_id
    return f"{mission_id}/{anchor_id}"
