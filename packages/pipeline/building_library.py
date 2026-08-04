"""Which buildings exist, and which N a candidate gets — roadmap 41, steps 2-3.

Item 37: `_write_site_spec` measures one `shell.glb` and gives it N placements,
so a four-building site is one building four times and stairs and ladders land
identically in every one. Its cheap fix is a SELECTION problem — Deli Counter
already ships the buildings.

`deli_counter/build/` is a flat directory of ~330 files. An archetype is usable
only if all three of its parts are there:

    <id>.glb              the greybox shell Lot places
    <id>.gameplay.json    the markers Lot resolves spawn/objective/extraction from
    <id>.slots.json       the swap contract Zoo themes against

A GLB missing its `slots.json` cannot be themed. It must drop out HERE, at
selection, and not at compose — a lot that fails three stages downstream because
one of five buildings has no manifest is a bad afternoon, and the check costs a
directory listing.

VARIANTS ARE NOT VARIETY. `deli_a01`, `deli_a02` and `deli_a03` are three
authorings of one archetype; a lot of all three is item 37 wearing a different
hat. Selection is by FAMILY first, then a variant within it.

Pure: a directory listing and arithmetic. No workspace, no Lot, no Godot.
"""
from __future__ import annotations

import re
from pathlib import Path

# One RNG rule for the whole site. `site_variation` already derives placement
# from the candidate seed and the cache fingerprint depends on re-deriving
# exactly what the builder derived; a second stream here would make two modules
# disagree about what seed 5421 means.
from packages.pipeline.site_variation import stream

#: `deli_a01` -> `deli`. Deli Counter's own naming: an archetype plus a
#: two-digit authoring index. Anything that does not match is its own family,
#: which is right for the hand-authored specs (`cr_deli`, `bank_job`,
#: `fuel_stop_heist`) that carry no index at all.
_VARIANT = re.compile(r"_a\d+$")

REQUIRED = (".glb", ".gameplay.json", ".slots.json")


def family(archetype_id: str) -> str:
    """The archetype behind a variant id."""
    return _VARIANT.sub("", str(archetype_id))


def index(build_dir) -> tuple[list[dict], list[dict]]:
    """``(complete, incomplete)`` archetypes found in a Deli Counter build dir.

    ``complete`` entries are ``{"id", "family", "glb", "gameplay", "slots"}``,
    sorted by id so a listing order cannot change what a seed selects.
    ``incomplete`` entries say what each one is missing, because a silently
    shorter library is how a lot quietly stops being varied.
    """
    root = Path(str(build_dir))
    if not root.is_dir():
        return [], []
    ids: set[str] = set()
    for f in root.iterdir():
        if f.is_file() and f.name.endswith(".glb"):
            ids.add(f.name[: -len(".glb")])
    complete, incomplete = [], []
    for aid in sorted(ids):
        parts = {suf: root / (aid + suf) for suf in REQUIRED}
        missing = [suf for suf, p in parts.items() if not p.is_file()]
        if missing:
            incomplete.append({"id": aid, "missing": missing})
            continue
        complete.append({
            "id": aid, "family": family(aid),
            "glb": str(parts[".glb"]),
            "gameplay": str(parts[".gameplay.json"]),
            "slots": str(parts[".slots.json"]),
        })
    return complete, incomplete


def pick_lot(entries: list[dict], seed: int, count: int) -> list[dict]:
    """``count`` archetypes for one candidate, no two from the same family.

    Keyed on the CANDIDATE seed, which is the seed that already diverges
    placement — so five candidates of a mission get five different lots rather
    than one lot shuffled. `cmd_run`'s diversity check exists because "N
    candidates that are all the same" shipped once already; a lot that ignored
    the seed would reintroduce it one level down.

    Families are drawn without replacement. When the library holds fewer
    families than the lot asks for, the remaining places take unused VARIANTS
    (two delis beats one deli and a hole) and only then repeat — each fallback
    is a real degradation and the caller can see it by comparing families to
    count.
    """
    count = max(0, int(count))
    if not entries or not count:
        return []
    rng = stream(seed)
    by_family: dict[str, list[dict]] = {}
    for e in entries:
        by_family.setdefault(e["family"], []).append(e)
    families = sorted(by_family)

    out: list[dict] = []
    pool = list(families)
    while len(out) < count and pool:
        fam = pool.pop(next(rng) % len(pool))
        variants = by_family[fam]
        out.append(variants[next(rng) % len(variants)])
    # Library smaller than the lot: fall back to unused variants, then repeat.
    if len(out) < count:
        used = {e["id"] for e in out}
        spare = [e for e in entries if e["id"] not in used]
        while len(out) < count and spare:
            out.append(spare.pop(next(rng) % len(spare)))
    while len(out) < count:
        out.append(entries[next(rng) % len(entries)])
    return out


def footprints_for(lot: list[dict], measure) -> list:
    """Each picked building's footprint, via ``site_variation.shell_footprint``.

    ``measure`` is injected so this module stays free of the GLB reader and the
    caller can hand it a cached one -- measuring the same shell five times, once
    per candidate, is the kind of cost that turns a fast stage slow quietly.
    A shell that cannot be measured yields ``None``, which
    ``site_variation.row_offsets`` already treats as DEFAULT_FOOTPRINT.
    """
    return [measure(e["glb"]) for e in lot]
