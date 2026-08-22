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
#: `_collision_signature` and `_anchor_registry` use, written
#: once so the coverage report cannot drift away from what is hashed. A key
#: added to a signature gets added here in the same edit.
PROTECTED_KEYS: dict[str, tuple[str, ...]] = {
    "collision_fingerprint": ("stair_systems", "ladders", "platforms",
                              "fire_escapes", "openings",
                              "vertical_links", "surfaces", "ground"),
    "anchor_registry_hash": ("markers", "anchors"),
    # The replicable state machines (INTERACTIVES.md). The collision
    # fingerprint stays single-state -- it hashes the level AT REST, the
    # default state everything offline builds and measures -- and the
    # per-state truth (states, transitions, collision_per_state) is
    # protected here as DATA. See docs/FUNCTIONAL_LOCK.md, "Interactive
    # fixtures: two collision states, one hash".
    "interactive_registry_hash": ("interactives",),
}

#: The schema a lock written by THIS code carries. Bumped whenever a
#: signature changes definition, because two locks with different
#: definitions are not comparable and diffing them produces drift
#: reports that mean nothing. See docs/FUNCTIONAL_LOCK.md.
SCHEMA = "level_factory.functional_lock.v0.3"

#: Which keys `_merged_gameplay` backfills from the Deli side. These can carry
#: content while the SITE contributes nothing, which is precisely how a lock
#: that protects no site data still produces a non-empty signature and looks
#: healthy from the outside.
BACKFILLED_FROM_DELI = frozenset(
    {"stair_systems", "ladders", "platforms", "fire_escapes",
     # `_merged_gameplay` has always backfilled this, and
     # `_anchor_registry` still falls back to it. 0.29.0 removed it from
     # this set while leaving both behaviours in place.
     "anchors",
     # Lot concatenates every building's interactives into the site
     # (ids are globally unique, so it is a concatenation, not a merge);
     # a site file written before Lot carried them omits the key, and
     # the building's own declaration is then the truth.
     "interactives"})

#: Keys where BOTH tools publish real content and neither restates the
#: other, so the lock protects the UNION.
#:
#: `_merged_gameplay` had exactly one rule for a shared key -- the site
#: wins -- which is right when Lot restates what Deli said and wrong
#: when they each say something the other does not. Measured
#: 2026-08-14 by tools/probe_site_vocabulary.py: of Deli's 14 markers,
#: ONE appeared in Lot's 42. The other thirteen -- CREW_SPAWN_A,
#: RESPONDER_SPAWN_1 and eleven cover points -- were being dropped from
#: the gameplay-anchor registry by a rule written for the other case.
#:
#: `surfaces` is deliberately NOT here: 25 of Deli's 238 collision
#: nodes are story -1 and window sub-parts that Lot appears never to
#: place, and hashing geometry the package does not contain would
#: report drift the day Lot legitimately stops emitting it.
UNIONED_WITH_DELI = frozenset({"markers"})

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
#: FLIPPED 2026-08-14. The mission that earned it is `lot_demo_001`,
#: recomputed under schema v0.2 after 0.30.0:
#:
#:     counts       markers 55, openings 76, surfaces 1029,
#:                  vertical_links 4, ground 5, stair_systems 2
#:     site_counts  markers 42, openings 76, surfaces 1029,
#:                  vertical_links 4, ground 5, stair_systems 0
#:
#: markers 55 against 42 is the union -- the thirteen Deli anchors
#: 0.30.0 stopped dropping. stair_systems 2 against 0 is the Deli
#: backfill, and it is ALL this lock protected before 0.29.0: two
#: records, for months. It now carries 1,171. vacuous False,
#: guards_no_site False, unguarded empty.
#:
#: THIS REFUSES A VACUOUS LOCK ONLY -- every signature empty. It does
#: NOT refuse `guards_no_site`, which is stricter and more meaningful,
#: because exactly ONE mission has been measured under this spec.
#: Refusing on the stricter test would fail missions nobody has looked
#: at. Widen it when a second and third have been measured, and name
#: them here the way this names lot_demo_001.
LOCK_COVERAGE_ENFORCED = True


def _size(d: dict, key: str) -> int:
    """How many records a key carries. 0 when absent or empty.

    THE NUMBER `guarding` DOES NOT CARRY. `markers: guarding=True`
    reads the same whether the registry holds fifty-five anchors or
    one, and before 0.29.0 the collision signature reported guarding
    while carrying two Deli stair systems and nothing else. Every
    report agreed with it. A count would not have.
    """
    v = d.get(key)
    if isinstance(v, (list, dict, str)):
        return len(v)
    return 0 if v is None else 1


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
            # Visible for the same reason the backfill is: a signature
            # carrying two tools' records should say so.
            "unioned_with_deli": [k for k in keys
                                  if k in UNIONED_WITH_DELI],
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
        # WHAT IS HASHED, and what the site alone published. The pair is
        # the point: for a unioned key they differ by exactly what the
        # other tool contributed, so a reader can do the subtraction
        # from the lock file without a probe.
        "counts": {k: _size(gameplay, k) for k in sorted(read)},
        "site_counts": {k: _size(site_gameplay, k)
                        for k in sorted(read)},
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


def _anchor_identity(a: dict) -> str:
    """The name that identifies one anchor across the whole site.

    NOT `id`. Lot's markers carry `id: "FRONT"` scoped to a building,
    and every building has one -- `_anchor_registry` sorted and keyed on
    `id`, so two distinct anchors normalised to identical entries and
    the registry silently under-counted. `name` is already namespaced
    (`b0/ATTACKER_SPAWN_FRONT`); `ids.namespaced_anchor` exists for the
    same reason.
    """
    name = a.get("name")
    if name:
        return str(name)
    ident = a.get("id") or a.get("shell_id")
    building = a.get("building")
    return f"{building}/{ident}" if building and ident else str(ident)


def _anchor_registry(gameplay: dict) -> list[dict]:
    """Stable, order-independent view of the gameplay anchors.

    Reads Lot's `markers` first, Deli's `anchors` second. The fallback is
    not compatibility scaffolding: a Deli-shaped anchor list is a real
    input, and the unit fixtures are written that way.

    POSITION IS PART OF THE REGISTRY. It was not, so the art pass could
    move every spawn point in the level and this hash would not change.
    Nothing else checks anchor position either. See
    docs/FUNCTIONAL_LOCK.md -- this is a change of meaning, not a rename.
    """
    anchors = gameplay.get("markers") or gameplay.get("anchors") or []
    norm = []
    for a in anchors:
        norm.append({
            "id": _anchor_identity(a),
            "type": a.get("type") or a.get("anchor_type"),
            "authority": a.get("required_authority") or a.get("authoritative_owner"),
            "at": [a.get("x"), a.get("y"), a.get("z")],
            "facing": a.get("facing"),
        })
    return sorted(norm, key=lambda x: str(x["id"]))


def _collision_nodes(gameplay: dict) -> list[str]:
    """Every collision node name Lot published, sorted and de-duped."""
    out = set()
    for s in gameplay.get("surfaces") or []:
        if isinstance(s, dict) and s.get("node"):
            out.add(str(s["node"]))
    return sorted(out)


def _ground_sources(gameplay: dict) -> dict:
    """Each building -> the mesh its collision came from."""
    ground = gameplay.get("ground") or {}
    if not isinstance(ground, dict):
        return {}
    return {str(k): (v or {}).get("source")
            for k, v in sorted(ground.items())
            if isinstance(v, dict)}


def _collision_signature(gameplay: dict) -> dict:
    """Everything that shapes collision/traversal, independent of GLB byte layout."""
    return {
        "stair_systems": gameplay.get("stair_systems", []),
        "ladders": gameplay.get("ladders", []),
        "platforms": gameplay.get("platforms", []),
        "fire_escapes": gameplay.get("fire_escapes", []),
        # Lot's vocabulary. `collision_hulls` and `doorways` were read
        # here and Lot has never published either; see
        # docs/FUNCTIONAL_LOCK.md for what it publishes instead.
        "openings": gameplay.get("openings", []),
        "vertical_links": gameplay.get("vertical_links", []),
        # NODE NAMES ONLY. The material dict beside them is rewritten by
        # Patina and Pixelcoat during the art pass; hashing it would
        # report drift on every normal run, and a gate that cries drift
        # gets switched off.
        "collision_nodes": _collision_nodes(gameplay),
        # Which mesh each building's collision came from. Swapping a
        # source glb is exactly this gate's job and need not rename a
        # single node.
        "ground_sources": _ground_sources(gameplay),
    }


def _interactive_registry(gameplay: dict) -> list[dict]:
    """Stable, order-independent view of the interactive state machines.

    KEYED ON `id`, and that is the OPPOSITE call from `_anchor_identity` --
    deliberately. Anchor ids are building-scoped ("FRONT" everywhere), so
    identity there is the namespaced name. Interactive ids are globally
    unique BY CONSTRUCTION ("<building>:if:<hash>", position-derived --
    INTERACTIVES.md, "Stable ids") and are the network handle every client,
    snapshot and saved game references. Rewriting them here would hash a
    name the shipped package never uses.

    THE WHOLE MACHINE IS FUNCTIONAL. states, default, transitions,
    state_geometry, collision_per_state, transform -- no field here is one
    a presentation stage may write. A dressing pass that changes which
    fixtures exist, what states they have, or whether a breached wall stops
    colliding moves this hash without moving a single vertex.
    """
    norm = []
    for i in gameplay.get("interactives") or []:
        if not isinstance(i, dict):
            continue
        norm.append({
            "id": i.get("id"),
            "kind": i.get("kind"),
            "slot_ref": i.get("slot_ref"),
            "building": i.get("building"),
            "states": i.get("states"),
            "default": i.get("default"),
            "transitions": i.get("transitions"),
            "state_geometry": i.get("state_geometry"),
            "collision_per_state": i.get("collision_per_state"),
            "reversible": i.get("reversible"),
            "transform": i.get("transform"),
        })
    return sorted(norm, key=lambda x: str(x["id"]))


@dataclass
class FunctionalLock:
    mission_id: str
    candidate_id: str
    seed: int
    schema: str = SCHEMA
    deli_spec_hash: str = ""
    lot_spec_hash: str = ""
    collision_fingerprint: str = ""
    anchor_registry_hash: str = ""
    interactive_registry_hash: str = ""
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
            "interactive_registry_hash": self.interactive_registry_hash,
            "clearance_metrics": self.clearance_metrics,
            "locked_at": self.locked_at,
            "coverage": self.coverage,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "FunctionalLock":
        known = {k: v for k, v in d.items() if k in cls.__dataclass_fields__}
        return cls(**known)


def _tail(ident: str) -> str:
    """The part of an identity after its namespace prefix."""
    return str(ident).rsplit("/", 1)[-1]


def _union_by_tail(site_records: list, deli_records: list) -> list:
    """Site records, plus Deli records the site does not already carry.

    DEDUPED BY NAME-TAIL, not by exact identity. Lot namespaces the
    anchors it does restate -- Deli's `VAULT` becomes `b0/VAULT` -- so
    an exact-match dedupe would keep both and count one anchor twice.
    Of Deli's 14 markers in lot_demo_001, exactly one matches this way;
    the rule exists for that one.
    """
    out = list(site_records)
    have = {_tail(_anchor_identity(r)) for r in site_records
            if isinstance(r, dict)}
    for r in deli_records:
        if not isinstance(r, dict):
            continue
        if _tail(_anchor_identity(r)) in have:
            continue
        out.append(r)
    return out


def _merged_gameplay(site_gameplay_path: Path, deli_gameplay_path: Path | None) -> dict:
    """The functional gameplay view, merging DC collision/anchors into the Lot
    site. compute_lock and verify_no_drift MUST use this same extraction so an
    unchanged shell produces an identical signature (no false drift)."""
    gameplay = _load(site_gameplay_path)
    if deli_gameplay_path and deli_gameplay_path.exists():
        deli_gp = _load(deli_gameplay_path)
        merged = dict(gameplay)
        for k in ("stair_systems", "ladders", "platforms", "fire_escapes",
                  "interactives"):
            merged.setdefault(k, deli_gp.get(k, []))
        if not merged.get("anchors"):
            merged["anchors"] = deli_gp.get("anchors", [])
        # UNION, not overwrite. See UNIONED_WITH_DELI.
        for k in UNIONED_WITH_DELI:
            merged[k] = _union_by_tail(merged.get(k) or [],
                                       deli_gp.get(k) or [])
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
        interactive_registry_hash=hash_json(_interactive_registry(gameplay)),
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
    #: The lock predates the current signature definitions, so nothing
    #: was compared. NOT drift -- reporting a version skew as drift
    #: would block every export on a schema bump and teach the reader
    #: that drift means nothing. `passed` is False with no drift
    #: entries: a comparison that did not happen did not pass.
    needs_recompute: bool = False
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
                "needs_recompute": self.needs_recompute,
                "coverage": self.coverage}


def blocks_export(result: RegressionResult) -> bool:
    """Does this result stop an export?

    ONE PREDICATE, HERE, so it can be tested. The first cut of 0.29.0
    left the decision inline in `cmd_export` as `if not
    result.passed`, and a schema mismatch -- which sets `passed` False
    because nothing was compared -- blocked every export. The doc had
    argued against exactly that, in those words, one release earlier.

    A schema mismatch does NOT block. The lock is regenerable, the skew
    is this release's own doing, and refusing to ship a level because a
    hash format changed is how a gate gets deleted. `passed` stays False
    -- a comparison that did not happen did not pass -- it simply is not
    what gates the export.
    """
    return not result.passed and not result.needs_recompute


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
    coverage = signature_coverage(
        gameplay, _load(post_art_site_gameplay_path))
    if str(getattr(lock, "schema", "")) != SCHEMA:
        return RegressionResult(
            mission_id=lock.mission_id, passed=False, drift=[],
            needs_recompute=True,
            vacuous_lock=bool(coverage.get("vacuous")),
            site_unguarded=bool(coverage.get("guards_no_site")),
            coverage=coverage)
    drift: list[str] = []
    if hash_json(_collision_signature(gameplay)) != lock.collision_fingerprint:
        drift.append("collision_fingerprint changed after art pass")
    if hash_json(_anchor_registry(gameplay)) != lock.anchor_registry_hash:
        drift.append("gameplay-anchor registry changed after art pass")
    if hash_json(_interactive_registry(gameplay)) != lock.interactive_registry_hash:
        drift.append("interactive registry changed after art pass")
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
