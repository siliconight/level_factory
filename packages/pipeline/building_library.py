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

THAT DIRECTORY IS ALSO WHERE LEVEL FACTORY WRITES. `deli_counter/build/` is the
source archetype library AND the sink Deli Counter builds this pipeline's own
missions into, so the output sits beside the input wearing the same three
suffixes and indexes as a perfectly good building. `lf_lot_demo_001_5017` — a
composed Level Factory site — was drawn into a lot and measured as an archetype
in the 2026-08-09 sweep. Every count taken off this library was taken against a
library containing the pipeline's own output, and the counts were consistent
with each other and wrong together. `source_exclusion` is where that stops, and
it stops here rather than by deleting files, because the next run writes them
back.

VARIANTS ARE NOT VARIETY. `deli_a01`, `deli_a02` and `deli_a03` are three
authorings of one archetype; a lot of all three is item 37 wearing a different
hat. Selection is by FAMILY first, then a variant within it.

Pure: a directory listing and arithmetic. No workspace, no Lot, no Godot.
"""
from __future__ import annotations

import json
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

#: What a building needs to be PLACED. Do not extend this set casually:
#: `pick_lot` draws from whatever `index` calls complete, so adding a suffix
#: removes archetypes from the pool and reshuffles every existing draw. A seed
#: that has already been built and evaluated would select a different five
#: buildings and wear the same grade.
REQUIRED = (".glb", ".gameplay.json", ".slots.json")

#: What a building additionally needs to be DRESSED AS ITSELF.
#:
#: Zoo's fixtures pass consumes a `.lights.json` and names its output from that
#: manifest's `building_id`. Planned once per mission, one such bake was
#: attached to all five buildings of a varied lot -- measured 2026-08-06, an
#: identical 30.5 x 3.7 x 17.9 fixture box inside five different shells. Per
#: building art needs a per building manifest, and 135 of the library's 138
#: shells already ship one.
#:
#: Deliberately NOT part of `REQUIRED`. See the module patch note and
#: docs/PER_BUILDING_ART.md.
ART_REQUIRED = (".lights.json",)


#: The prefix Level Factory's own composed outputs carry.
#:
#: NOT a guess about names. `apps/cli/commands/__init__.py` builds the Deli
#: Counter spec name as `f"lf_{model.mission_id}"` and
#: `DeliCounterAdapter._level_name` appends `_{seed}`, so
#: `lf_lot_demo_001_5017` is this pipeline's own construction read back off
#: disk. One grep names the line that writes it.
#:
#: A name rule is normally the weak kind of rule -- `module_stem` is the
#: standing example, where a filename that omitted the storey height let one
#: building's modules resolve against another's slots. The difference is
#: authorship: nobody else writes these ids, so this is reading a label the
#: pipeline printed on its own output rather than inferring a kind from a word.
_COMPOSED_PREFIX = "lf_"


def family(archetype_id: str) -> str:
    """The archetype behind a variant id."""
    return _VARIANT.sub("", str(archetype_id))


def source_exclusion(build_dir, archetype_id) -> str:
    """Why ``archetype_id`` is not a SOURCE archetype — ``""`` when it is one.

    Two kinds, and they are found two different ways because they ARE two
    different things.

    **Level Factory's own composed outputs**, by the prefix this pipeline
    writes on them (see `_COMPOSED_PREFIX`). Nine of them sit in the library
    today: `lf_art_probe_001_5017`, five `lf_category5_baie_dore_001_*` and
    three `lf_lot_demo_001_*`.

    **Facades**, by Deli Counter's own word for it. `<id>.validation.json`
    carries `facade`, written by `deli_counter/evidence.py`: `true` for
    `gs_facade_rowhome` and `gs_facade_storefront`, `false` for every building.
    LEVEL FACTORY DOES NOT COMPUTE THIS — the same rule `scoped_verdict` states
    two functions down, for the same reason. A second definition of "facade" in
    a second repo is how two manifests drift apart, and the flag is already
    there. (Measured, so the flag is not taken on faith: both facades carry 0
    markers, 0 rooms and a six-polygon navmesh of three 2-poly islands — three
    floor plates with nothing joining them. A mission placed in one has
    nowhere to go.)

    AN ABSENT VALIDATION MANIFEST IS NOT A FACADE. Deli Counter not having said
    is not Deli Counter saying yes, and this fails open deliberately: exactly
    one complete shell in the library has no validation manifest
    (`cbp_town_finale_midbalanced_schemafixed`) and it is a building. A rule
    that read absence as exclusion would drop it for never having been judged,
    which is the mistake `themed_fitness` refuses to make one direction over.

    Takes the build dir rather than a row so it can be asked about a bare id —
    `library_census.py` and `marker_scope_census.py` walk the directory
    themselves and never build index rows.
    """
    aid = str(archetype_id)
    if aid.startswith(_COMPOSED_PREFIX):
        return (f"Level Factory's own composed output: ids beginning "
                f"{_COMPOSED_PREFIX!r} are written by this pipeline into its "
                f"own source library, not authored as archetypes")
    data = _manifest(Path(str(build_dir)) / (aid + ".validation.json"))
    if (data or {}).get("facade") is True:
        return ("Deli Counter reports facade=true in its validation manifest: "
                "a street wall with no interior, not a building a mission can "
                "be placed inside")
    return ""


def index(build_dir) -> tuple[list[dict], list[dict], list[dict]]:
    """``(complete, incomplete, non_source)`` found in a Deli Counter build dir.

    ``complete`` entries are ``{"id", "family", "glb", "gameplay", "slots",
    "lights", "navgate"}``, sorted by id so a listing order cannot change what
    a seed selects. ``incomplete`` entries say what each one is missing, because a
    silently shorter library is how a lot quietly stops being varied.
    ``non_source`` entries are ``{"id", "reason"}`` — files in this directory
    that are not source archetypes at all, each carrying the sentence
    `source_exclusion` gave for it.

    THREE LISTS, AND THE ARITY CHANGE IS DELIBERATE. This returned a pair until
    2026-08-09 and every caller unpacked two; a filter that simply shortened
    `complete` would have been the silent narrowing this module refuses
    everywhere else. Breaking the signature makes each of the three readers say
    out loud what it does with the third list — which is the whole point, since
    the reason these entries were counted for a week is that nothing was
    obliged to mention them.

    ``lights`` is ``""`` when the archetype has no ``.lights.json``. It is
    reported and never used to EXCLUDE, because completeness here decides what
    `pick_lot` draws from and changing that changes which buildings an already
    evaluated seed selects. The themed path applies the requirement itself, via
    `art_incomplete`.

    NON-SOURCE EXCLUSION IS THE ONE THING THAT DOES NARROW THE POOL, against
    the warning `REQUIRED` gives, and it is worth being exact about what it
    costs. Measured on the library of 2026-08-09: all eleven excluded ids read
    `navigable: null` with `interior_checked: 0`, so `themed_fitness` already
    refused every one of them as UNJUDGED. The THEMED lot is therefore
    bit-identical before and after this filter — `require_themed_shells` had
    already removed exactly these eleven. What changes is the GREYBOX draw,
    which is how `lf_lot_demo_001_5017` came to be placed as a building.
    """
    root = Path(str(build_dir))
    if not root.is_dir():
        return [], [], []
    ids: set[str] = set()
    for f in root.iterdir():
        if f.is_file() and f.name.endswith(".glb"):
            ids.add(f.name[: -len(".glb")])
    complete, incomplete, non_source = [], [], []
    for aid in sorted(ids):
        # WHAT THE FILE IS, before whether it is complete. Asked the other way
        # round, a composed site that happened to be missing a manifest would
        # be reported as an archetype with a hole in it, and send the reader to
        # Deli Counter to rebuild something that should never have been indexed.
        why = source_exclusion(root, aid)
        if why:
            non_source.append({"id": aid, "reason": why})
            continue
        parts = {suf: root / (aid + suf) for suf in REQUIRED}
        missing = [suf for suf, p in parts.items() if not p.is_file()]
        if missing:
            incomplete.append({"id": aid, "missing": missing})
            continue
        lights = root / (aid + ".lights.json")
        navgate = root / (aid + ".navgate.json")
        complete.append({
            "id": aid, "family": family(aid),
            "glb": str(parts[".glb"]),
            "gameplay": str(parts[".gameplay.json"]),
            "slots": str(parts[".slots.json"]),
            "lights": str(lights) if lights.is_file() else "",
            # Reported, never used to EXCLUDE here -- same rule as `lights`.
            # `nav_gate` writes it and `themed_fitness` reads it; adding it to
            # REQUIRED would reshuffle every draw already graded.
            "navgate": str(navgate) if navgate.is_file() else "",
        })
    return complete, incomplete, non_source


def art_incomplete(lot: list[dict]) -> list[dict]:
    """Which of the PICKED buildings cannot be dressed as themselves.

    Reports rather than decides, so the caller can say what it wants to do --
    and so this stays the pure directory-and-arithmetic module it claims to be.
    """
    out = []
    for e in lot or []:
        missing = [suf for suf, key in ((".lights.json", "lights"),)
                   if not e.get(key)]
        if missing:
            out.append({"id": e.get("id", "?"), "missing": missing})
    return out


class ArtInputsMissing(RuntimeError):
    """A themed lot was asked for and a building cannot carry its own art."""


def require_art_inputs(lot: list[dict]) -> None:
    """Raise unless every picked building can be dressed as itself.

    RAISES rather than filtering, and the distinction is the whole point. If a
    building without a light manifest simply dropped out, a five building brief
    would produce a four building site with every stage reporting success --
    which is the failure already recorded in docs/WALKABLE_SITE.md, where five
    composes wrote correct scenes and the site placed the mission shell five
    times because an absence was read as nothing to do.

    A lot that cannot be dressed is not a smaller version of the brief. It is a
    different brief, and nobody asked for it.
    """
    gaps = art_incomplete(lot)
    if not gaps:
        return
    detail = "; ".join(f"{g['id']} (no {', '.join(g['missing'])})"
                       for g in gaps)
    raise ArtInputsMissing(
        f"{len(gaps)} of {len(lot)} building(s) in this lot cannot carry "
        f"per-building art: {detail}. A themed lot dresses each building AS "
        f"ITSELF, so every one needs its own manifest -- build the missing "
        f"ones, or run this mission without --art.")


#: What a building must SAY about itself to be picked for a THEMED lot.
#:
#: `<id>.slots.json` carries `coverage` -- how many slots of each kind the
#: themed kit actually filled. `<id>.navgate.json` carries `navigable`, which
#: Deli Counter's nav gate computes AFTER scoping markers against the
#: building's own footprint.
#:
#: Neither is in `REQUIRED`, for the reason stated there. They decide themed
#: selection only, through `themed_report`.
THEMED_FIT_INPUTS = (".slots.json", ".navgate.json")


def _manifest(path):
    """The JSON object at ``path``, or ``None``.

    Absent, unreadable and not-an-object all answer ``None`` on purpose: a
    truncated manifest is a shell nobody successfully judged, which is what a
    missing one says too. Nothing here raises -- this module is a directory
    listing and arithmetic, and it runs while a plan is being built.
    """
    if not path:
        return None
    try:
        with open(str(path), "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def slot_coverage(entry) -> dict:
    """``coverage`` from a shell's slot manifest -- ``{}`` when there is none.

    Measured 2026-08-08 by walking two buildings out of one site.
    `pharmacy_a02` -- 137 slots, coverage {wall 118, doorway 6, breach 2,
    window 2}, 9 Zoo modules drawn -- stands solid. `final_stand` -- 9 slots,
    coverage {}, 0 modules -- has holes where its walls should be. An empty
    coverage map is a shell the themed kit does not fill.

    Keyed on EMPTY, never on a count: 0 is measured-bad, 128 is measured-good,
    and nothing between them has been measured. A threshold here would be an
    invention wearing a number.
    """
    data = _manifest(entry.get("slots") if isinstance(entry, dict) else entry)
    cov = (data or {}).get("coverage")
    return dict(cov) if isinstance(cov, dict) else {}


def scoped_verdict(entry) -> tuple[str, str]:
    """``(state, detail)`` -- what Deli Counter says about this shell.

    LEVEL FACTORY DOES NOT COMPUTE THIS. `nav_gate` owns the inside/outside
    classification, because the marker positions and the footprint are its
    inputs and a second definition of "exterior" in a second repo is how the
    coverage and layer keys drifted apart twice already. This reads a field.

    States, and why UNSCOPED is not folded into UNJUDGED: a manifest written
    before the 2026-08-08 scope split carries a `navigable` computed over ALL
    markers, and 99 of 135 shells read `false` there purely because their
    extraction point stands on a street Lot has not laid yet. Trusting that
    field would re-import the defect the split removed, so its ABSENCE of
    `markers.interior_checked` is what makes it unreadable, not its value.
    """
    path = entry.get("navgate") if isinstance(entry, dict) else entry
    if not path:
        return "absent", "no navgate manifest: this shell has never been baked"
    data = _manifest(path)
    if data is None:
        return "absent", "navgate manifest unreadable"
    markers = data.get("markers")
    if not isinstance(markers, dict) or "interior_checked" not in markers:
        return "unscoped", (
            "navgate manifest predates the marker scope split -- its verdict "
            "counted extraction points the building bake cannot reach; "
            "re-run nav_gate.py")
    nav = data.get("navigable")
    reason = str(data.get("navigable_reason") or "")
    if nav is True:
        return "navigable", reason
    if nav is False:
        return "broken", reason
    return "unjudged", reason or "nav gate measured nothing about this shell"


def themed_fitness(entry) -> dict:
    """``{"id", "family", "fit", "reasons"}`` -- can this shell wear a theme?

    Two conditions. Coverage says the themed kit fills this shell's walls;
    the nav verdict says a body can reach what the mission needs INSIDE it.

    UNJUDGED IS NOT PASSING, and neither is UNSCOPED. 17 shells check no
    interior marker at all -- no spawn, or nothing of a checked type -- and a
    predicate that reads "not broken" passes every one of them. A check that
    cannot fail is indistinguishable from one that passed, which this repo has
    now written down three times.
    """
    reasons: list[str] = []
    if not slot_coverage(entry):
        reasons.append("empty slot coverage: the themed kit fills nothing "
                       "in this shell")
    state, detail = scoped_verdict(entry)
    if state != "navigable":
        reasons.append(f"{state}: {detail}" if detail else state)
    return {"id": (entry or {}).get("id", "?"),
            "family": (entry or {}).get("family", ""),
            "fit": not reasons, "reasons": reasons}


def themed_report(entries: list[dict]) -> tuple[list[dict], list[dict]]:
    """``(fit, unfit)`` index rows, each unfit one carrying its ``reasons``.

    Reports rather than decides, the same way `art_incomplete` does, so the
    caller owns the sentence and this stays the pure module it claims to be.
    Rows are copies, so `pick_lot` and `footprints_for` read them unchanged.
    """
    fit, unfit = [], []
    for e in entries or []:
        verdict = themed_fitness(e)
        row = dict(e)
        row["reasons"] = verdict["reasons"]
        (fit if verdict["fit"] else unfit).append(row)
    return fit, unfit


class ThemedShellsUnavailable(RuntimeError):
    """A themed lot was asked for and the library cannot fill it."""


def require_themed_shells(entries: list[dict], count: int) -> list[dict]:
    """The fit subset, or raise naming exactly what is short.

    RAISES rather than shortening, and the distinction is the whole point --
    the same one `require_art_inputs` makes one function up. If unfit shells
    simply dropped out, a five building brief would produce a smaller site
    with every stage reporting success, which is the failure already recorded
    in docs/WALKABLE_SITE.md.

    Keyed on FAMILIES, because families are what `pick_lot` draws without
    replacement. Two fit variants of one family cannot fill two places in a
    varied lot without repeating an archetype, which is item 37 again.
    """
    want = max(1, int(count or 1))
    fit, unfit = themed_report(entries)
    families = sorted({e.get("family", "") for e in fit})
    if len(families) >= want:
        return fit
    tally: dict[str, int] = {}
    for e in unfit:
        for reason in e.get("reasons") or ():
            head = str(reason).split(":", 1)[0]
            tally[head] = tally.get(head, 0) + 1
    detail = "; ".join(f"{n} with {head}" for head, n in sorted(tally.items()))
    raise ThemedShellsUnavailable(
        f"a themed lot of {want} needs {want} fit families and the library "
        f"offers {len(families)}: {', '.join(families) or '(none)'}. "
        f"{len(unfit)} of {len(fit) + len(unfit)} indexed shell(s) are unfit "
        f"-- {detail or 'no reason recorded'}. A themed lot dresses each "
        f"building AS ITSELF, so a shell whose slots the kit does not fill, "
        f"or whose own interior the nav bake cannot cross, is not a smaller "
        f"version of this brief -- build or judge the missing shells, or run "
        f"this mission without --art.")


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


def lot_for(library, building_count, candidate_id, *,
            themed: bool = False) -> tuple[list[dict], list[dict]]:
    """``(lot, incomplete)`` -- which buildings this candidate places.

    THE one rule, so that the planner (which must fan art jobs out per
    building), the compose spec and the site spec are not three derivations
    that happen to agree. They agreed by luck until someone changed a
    signature; this is the same answer by construction.

    A varied lot is opt-in on `lot_library` and only means anything when the
    brief asks for more than one building -- otherwise this is the single-shell
    path and the answer is no lot at all.

    Takes primitives rather than a `MissionBrief` so this module stays free of
    `packages.core.models`: it is a directory listing and arithmetic, and it
    should keep being importable by anything.

    Returns `incomplete` rather than printing it. The two existing callers
    describe the same exclusion differently -- one is about what cannot be
    THEMED, the other about what is missing from the ROW -- and a module with
    no side effects should not pick between their sentences.
    """
    count = max(1, int(building_count or 1))
    if not library or count < 2:
        return [], []
    # `non_source` is dropped HERE and nowhere else, on purpose. It is a
    # property of the LIBRARY, identical for every candidate and every brief,
    # so surfacing it through this function would print the same eleven lines
    # once per candidate per stage. The three readers that index the directory
    # directly — the site builder and the two censuses — say it once each.
    complete, incomplete, _non_source = index(library)
    if themed:
        # NARROWS THE POOL, and is off by default for the reason `REQUIRED`
        # gives: `pick_lot` draws from whatever it is handed, so a narrower
        # pool re-selects every lot already built and graded. The greybox path
        # must not pass it; every themed spec builder must, or the compose
        # stage and the site stage select different buildings and the site
        # finds no composed scene for the ones it placed.
        complete = require_themed_shells(complete, count)
    seed = int(str(candidate_id).rsplit("_", 1)[-1])
    return pick_lot(complete, seed, count), incomplete


def footprints_for(lot: list[dict], measure) -> list:
    """Each picked building's footprint, via ``site_variation.shell_footprint``.

    ``measure`` is injected so this module stays free of the GLB reader and the
    caller can hand it a cached one -- measuring the same shell five times, once
    per candidate, is the kind of cost that turns a fast stage slow quietly.
    A shell that cannot be measured yields ``None``, which
    ``site_variation.row_offsets`` already treats as DEFAULT_FOOTPRINT.
    """
    return [measure(e["glb"]) for e in lot]
