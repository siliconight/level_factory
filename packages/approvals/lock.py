"""Functional lock computation and post-art regression (TDD 23.4, 31, 15.3).

The functional lock captures a fingerprint of everything that must NOT change
during the art pass: collision, gameplay-anchor registry, route graph, and
critical clearance metrics. After Lux apply, we recompute the same signature
from the post-art scene and diff it. Any drift blocks the handoff (44.6).
"""
from __future__ import annotations

import datetime as _dt
import json
from dataclasses import dataclass, field
from pathlib import Path

from packages.core.hashing import hash_json


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat()


def _load(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _anchor_registry(gameplay: dict) -> list[dict]:
    """Stable, order-independent view of the gameplay anchors."""
    anchors = gameplay.get("anchors", [])
    norm = []
    for a in anchors:
        norm.append({
            "id": a.get("id") or a.get("shell_id"),
            "type": a.get("type") or a.get("anchor_type"),
            "authority": a.get("required_authority") or a.get("authoritative_owner"),
        })
    return sorted(norm, key=lambda x: str(x["id"]))


def _collision_signature(gameplay: dict) -> dict:
    """Everything that shapes collision/traversal, independent of GLB byte layout."""
    return {
        "stair_systems": gameplay.get("stair_systems", []),
        "ladders": gameplay.get("ladders", []),
        "platforms": gameplay.get("platforms", []),
        "fire_escapes": gameplay.get("fire_escapes", []),
        "collision_hulls": gameplay.get("collision_hulls", []),
        "doorways": gameplay.get("doorways", []),
    }


def _route_graph(gameplay: dict) -> dict:
    return {
        "route": gameplay.get("route", gameplay.get("route_graph", {})),
        "nav_hints": gameplay.get("nav_hints", {}),
    }


@dataclass
class FunctionalLock:
    mission_id: str
    candidate_id: str
    seed: int
    schema: str = "level_factory.functional_lock.v0.1"
    deli_spec_hash: str = ""
    lot_spec_hash: str = ""
    collision_fingerprint: str = ""
    anchor_registry_hash: str = ""
    route_graph_hash: str = ""
    clearance_metrics: dict = field(default_factory=dict)
    locked_at: str = field(default_factory=_now)

    def as_dict(self) -> dict:
        return {
            "schema": self.schema,
            "mission_id": self.mission_id,
            "candidate_id": self.candidate_id,
            "seed": self.seed,
            "deli_spec_hash": self.deli_spec_hash,
            "lot_spec_hash": self.lot_spec_hash,
            "collision_fingerprint": self.collision_fingerprint,
            "anchor_registry_hash": self.anchor_registry_hash,
            "route_graph_hash": self.route_graph_hash,
            "clearance_metrics": self.clearance_metrics,
            "locked_at": self.locked_at,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "FunctionalLock":
        known = {k: v for k, v in d.items() if k in cls.__dataclass_fields__}
        return cls(**known)


def _merged_gameplay(site_gameplay_path: Path, deli_gameplay_path: Path | None) -> dict:
    """The functional gameplay view, merging DC collision/anchors into the Lot
    site. compute_lock and verify_no_drift MUST use this same extraction so an
    unchanged shell produces an identical signature (no false drift)."""
    gameplay = _load(site_gameplay_path)
    if deli_gameplay_path and deli_gameplay_path.exists():
        deli_gp = _load(deli_gameplay_path)
        merged = dict(gameplay)
        for k in ("stair_systems", "ladders", "platforms", "fire_escapes"):
            merged.setdefault(k, deli_gp.get(k, []))
        if not merged.get("anchors"):
            merged["anchors"] = deli_gp.get("anchors", [])
        gameplay = merged
    return gameplay


def compute_lock(
    *, mission_id: str, candidate_id: str, seed: int,
    site_gameplay_path: Path, deli_gameplay_path: Path | None = None,
    deli_spec_hash: str = "", lot_spec_hash: str = "",
) -> FunctionalLock:
    """Compute a functional lock from the selected candidate's Lot site."""
    gameplay = _merged_gameplay(site_gameplay_path, deli_gameplay_path)
    return FunctionalLock(
        mission_id=mission_id, candidate_id=candidate_id, seed=seed,
        deli_spec_hash=deli_spec_hash, lot_spec_hash=lot_spec_hash,
        collision_fingerprint=hash_json(_collision_signature(gameplay)),
        anchor_registry_hash=hash_json(_anchor_registry(gameplay)),
        route_graph_hash=hash_json(_route_graph(gameplay)),
        clearance_metrics=gameplay.get("clearance_metrics", {}),
    )


@dataclass
class RegressionResult:
    mission_id: str
    passed: bool
    drift: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {"mission_id": self.mission_id, "passed": self.passed,
                "drift": self.drift}


def verify_no_drift(
    lock: FunctionalLock,
    post_art_site_gameplay_path: Path,
    post_art_deli_gameplay_path: Path | None = None,
) -> RegressionResult:
    """Post-art regression: recompute the protected signatures and diff (31).

    Uses the same merged-gameplay extraction as ``compute_lock`` so an unchanged
    functional shell yields identical signatures.
    """
    gameplay = _merged_gameplay(post_art_site_gameplay_path, post_art_deli_gameplay_path)
    drift: list[str] = []
    if hash_json(_collision_signature(gameplay)) != lock.collision_fingerprint:
        drift.append("collision_fingerprint changed after art pass")
    if hash_json(_anchor_registry(gameplay)) != lock.anchor_registry_hash:
        drift.append("gameplay-anchor registry changed after art pass")
    if hash_json(_route_graph(gameplay)) != lock.route_graph_hash:
        drift.append("route graph changed after art pass")
    return RegressionResult(mission_id=lock.mission_id, passed=not drift, drift=drift)
