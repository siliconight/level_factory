"""Functional lock computation and post-art regression (TDD 23.4, 31, 15.3).

The functional lock captures a fingerprint of everything that must NOT change
during the art pass: collision, gameplay-anchor registry, route graph, and
critical clearance metrics. After Lux apply, we recompute the same signature
from the post-art scene and diff it. Any drift blocks the handoff (44.6).
"""
from __future__ import annotations

import datetime as _dt
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

from packages.core.hashing import hash_json


#: The keys each protected signature actually reads. This is the same list
#: `_collision_signature`, `_anchor_registry` and `_route_graph` use, written
#: once so the coverage report cannot drift away from what is hashed. A key
#: added to a signature gets added here in the same edit.
PROTECTED_KEYS: dict[str, tuple[str, ...]] = {
    "collision_fingerprint": ("stair_systems", "ladders", "platforms",
                              "fire_escapes", "collision_hulls", "doorways"),
    "anchor_registry_hash": ("anchors",),
    "route_graph_hash": ("route", "route_graph", "nav_hints"),
}

#: Which keys `_merged_gameplay` backfills from the Deli side. These can carry
#: content while the SITE contributes nothing, which is precisely how a lock
#: that protects no site data still produces a non-empty signature and looks
#: healthy from the outside.
BACKFILLED_FROM_DELI = frozenset(
    {"stair_systems", "ladders", "platforms", "fire_escapes", "anchors"})

COVERAGE_SCHEMA = "level_factory.lock_coverage.v0.1"


class VacuousLockError(RuntimeError):
    """A functional lock whose signatures protect nothing."""


#: Whether a lock that protects nothing is refused outright.
#:
#: FALSE, for the reason `export.py`'s CLOSURE_ENFORCED was False: no lock had
#: ever been measured, the first measurement found EVERY lock this factory has
#: written to be vacuous, and refusing on day one would fail
#: `approve --gate functional_shell_locked` for every mission, including ones
#: whose art pass is already running.
#:
#: The cause is known and is not a bug in this file: `site.site.gameplay.json`
#: publishes twenty top-level keys and none of the eleven above. Lot and Deli
#: name the same concepts differently and the extraction is in Deli's
#: vocabulary. Mapping them is a contract question between two tool repos and
#: wants its own release.
#:
#: The measurement ALWAYS runs and ALWAYS lands in the lock file. This flag
#: decides only whether it stops the gate. Flip it once a mapping exists and
#: one real mission produces a non-vacuous lock -- and name that mission here.
LOCK_COVERAGE_ENFORCED = False


def _has_content(d: dict, key: str) -> bool:
    """Present AND not empty. `[]` is the shape this whole defect wore."""
    return bool(d.get(key))


def signature_coverage(gameplay: dict, site_gameplay: dict) -> dict:
    """What the three signatures are actually protecting.

    `gameplay` is the merged view that gets hashed; `site_gameplay` is the raw
    Lot file, needed separately because the merge backfills from Deli and the
    interesting question is what the SITE contributed.
    """
    read = {k for keys in PROTECTED_KEYS.values() for k in keys}
    sigs: dict[str, dict] = {}
    for name, keys in PROTECTED_KEYS.items():
        have = [k for k in keys if _has_content(gameplay, k)]
        sigs[name] = {
            "keys_with_content": have,
            "from_the_site": [k for k in keys
                              if _has_content(site_gameplay, k)],
            "backfilled_from_deli": [k for k in have
                                     if k in BACKFILLED_FROM_DELI
                                     and not _has_content(site_gameplay, k)],
            "guarding": bool(have),
        }
    unguarded = sorted(n for n, v in sigs.items() if not v["guarding"])
    return {
        "schema": COVERAGE_SCHEMA,
        "signatures": sigs,
        "unguarded": unguarded,
        "site_contributes": sorted(k for k in read
                                   if _has_content(site_gameplay, k)),
        # THE FIELD THAT WOULD HAVE FOUND THIS. The vocabulary gap, written
        # into the lock beside the hashes instead of left for a probe.
        "site_publishes_unread": sorted(set(site_gameplay) - read),
        # NOT the same question as `vacuous`, and this is the one that
        # is true here.
        "guards_no_site": not any(_has_content(site_gameplay, k)
                                  for k in read),
        "vacuous": len(unguarded) == len(PROTECTED_KEYS),
    }


def describe_coverage(cov: dict, mission_id: str) -> str:
    lines = [f"[lock] {mission_id}: "
             + ("THIS LOCK PROTECTS NOTHING." if cov["vacuous"]
                else "signatures with no content: "
                     + ", ".join(cov["unguarded"]))]
    if cov["guards_no_site"]:
        lines.append("[lock]   the site file contributed NO protected key; "
                     "every non-empty signature is backfilled from Deli")
    unread = cov["site_publishes_unread"]
    if unread:
        lines.append("[lock]   the site publishes %d key(s) nothing here "
                     "reads: %s" % (len(unread), ", ".join(unread[:12])
                                    + (" ..." if len(unread) > 12 else "")))
    lines.append("[lock]   see docs / probe_selection_drift.py; "
                 "LOCK_COVERAGE_ENFORCED is %s" % LOCK_COVERAGE_ENFORCED)
    return "\n".join(lines)



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
    #: What this lock protects. Empty on locks written before 0.28.0 --
    #: `from_dict` filters to known fields, so an old lock loads with
    #: no coverage rather than failing, and an absent report is not a
    #: claim that the lock was covered.
    coverage: dict = field(default_factory=dict)

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
            "coverage": self.coverage,
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
    """Compute a functional lock from the selected candidate's Lot site.

    MEASURES WHAT IT IS PROTECTING, always, and records it. A lock whose
    signatures are hashes of empty collections passes `verify_no_drift`
    against anything, and reported success for months because nothing
    ever asked it what it covered.
    """
    gameplay = _merged_gameplay(site_gameplay_path, deli_gameplay_path)
    coverage = signature_coverage(gameplay, _load(site_gameplay_path))
    if coverage["unguarded"]:
        note = describe_coverage(coverage, mission_id)
        if LOCK_COVERAGE_ENFORCED and coverage["vacuous"]:
            raise VacuousLockError(note)
        print(note, file=sys.stderr)
    return FunctionalLock(
        mission_id=mission_id, candidate_id=candidate_id, seed=seed,
        deli_spec_hash=deli_spec_hash, lot_spec_hash=lot_spec_hash,
        collision_fingerprint=hash_json(_collision_signature(gameplay)),
        anchor_registry_hash=hash_json(_anchor_registry(gameplay)),
        route_graph_hash=hash_json(_route_graph(gameplay)),
        clearance_metrics=gameplay.get("clearance_metrics", {}),
        coverage=coverage,
    )


@dataclass
class RegressionResult:
    mission_id: str
    passed: bool
    drift: list[str] = field(default_factory=list)
    #: The lock this was checked against protects nothing, so `passed`
    #: means only that nothing was compared. Carried rather than folded
    #: into `drift`: a vacuous lock is not drift, and reporting it as
    #: drift would block exports on a defect in the lock.
    vacuous_lock: bool = False
    #: No protected key came from the SITE. Weaker than vacuous_lock and
    #: far more common -- it is the state every lock here is in. A
    #: signature kept alive entirely by Deli's backfill is not guarding
    #: the assembled site, however non-empty its hash looks.
    site_unguarded: bool = False
    #: What THIS COMPARISON protected, measured from the files handed
    #: in. Distinct from `lock.coverage`, which is what the lock
    #: protected when it was WRITTEN. Not merged: if they disagree the
    #: site's shape changed between locking and checking, and that is
    #: worth seeing rather than reconciling away.
    coverage: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {"mission_id": self.mission_id, "passed": self.passed,
                "drift": self.drift, "vacuous_lock": self.vacuous_lock,
                "site_unguarded": self.site_unguarded,
                "coverage": self.coverage}


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
    # MEASURED HERE, NOT READ OFF THE LOCK. The first version of this
    # took `lock.coverage`, which only exists on locks written by 0.28.0
    # or later -- so on every lock that exists today it was empty, and
    # the warning this release was built to produce could not fire. The
    # evidence was never absent: both files are open right here, and
    # `gameplay` above is already the merge of them.
    coverage = signature_coverage(
        gameplay, _load(post_art_site_gameplay_path))
    return RegressionResult(
        mission_id=lock.mission_id, passed=not drift, drift=drift,
        vacuous_lock=bool(coverage.get("vacuous")),
        site_unguarded=bool(coverage.get("guards_no_site")),
        coverage=coverage)
