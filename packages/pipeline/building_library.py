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

import hashlib
import json
import re
from pathlib import Path

# One RNG rule for the whole site. `site_variation` already derives placement
# from the candidate seed and the cache fingerprint depends on re-deriving
# exactly what the builder derived; a second stream here would make two modules
# disagree about what seed 5421 means.
from packages.core.models import EMPTIES_ACROSS, empties_effective, streetscape_effective
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

    Three kinds, found two different ways because they ARE different
    things: one by the prefix this pipeline writes, two by Deli Counter's own
    word.

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

    **Demos**, by Deli Counter's own word for that too (0.144.4, roadmap 185):
    `demo` in the same manifest, written by Deli Counter 0.187.0 for a spec
    that exists to demonstrate or test a capability. The breadth sweep drew
    `setback_demo` and `pvp_station_ref` into card_block_001's lots (cold runs
    9170 and 9174): complete builds carrying every manifest a building does,
    with nothing but the name to say otherwise -- and a name is not read here.

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
    if (data or {}).get("demo") is True:
        return ("Deli Counter reports demo=true in its validation manifest: a "
                "spec that demonstrates or tests a capability, not a building "
                "a level stands")
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


def _geometry_sources(src: Path) -> list[Path] | None:
    """The files `build_freshness.py` compares against, READ from it.

    That tool owns the freshness rule and names the geometry modules in a
    `GEOMETRY_SOURCES` tuple. Copying the list here would be two copies of one
    rule in two repos -- the objection `Building._cap_thick` states as "one
    rule, one place, because both wall emitters need it and two copies drift".
    So it is read out of the assignment, with no import and no subprocess
    across the boundary.

    Comparing against every `*.py` instead is not close enough. Measured
    2026-08-12, minutes apart on one library: the owning tool said "138
    shell(s) newer than deli_counter.py -- up to date" while a newest-of-all-py
    rule said 7.2 days behind, because `check.py` had just been edited and
    `check.py` builds no geometry.

    REFUTED, 2026-09-14: "a check that cannot find the rule should be silent".
    This used to cut the tuple out with a regex matching "(" then anything
    but ")" then ")", and return []
    on any failure. Deli Counter 0.116.0 wrote a comment inside the tuple --
    `# the light manifest is a build output (0.116.0)` -- whose `)` ended the
    match, `literal_eval` failed, and this guard said nothing on every run from
    then on. Cold run 9053 composed 130 stale shells of 132 under it, and the
    placement gate refused the export. It now parses the module with `ast`,
    where a comment is not text, and distinguishes the two absences:

      * ``[]``   -- no `build_freshness.py` beside the build: no rule to apply;
      * ``None`` -- the tool is there and its rule could not be read: the
        caller must say so, because silence here reads as "fresh".
    """
    tool = src / "build_freshness.py"
    if not tool.is_file():
        return []
    try:
        import ast
        tree = ast.parse(tool.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, SyntaxError, ValueError):
        return None
    names = None
    for node in tree.body:
        targets = (node.targets if isinstance(node, ast.Assign)
                   else [node.target] if isinstance(node, ast.AnnAssign) else [])
        if any(isinstance(tg, ast.Name) and tg.id == "GEOMETRY_SOURCES"
               for tg in targets):
            try:
                names = ast.literal_eval(node.value)
            except (ValueError, SyntaxError):
                return None
    if names is None:
        return None
    if isinstance(names, str):
        names = (names,)
    found = [src / n for n in names if isinstance(n, str) and (src / n).is_file()]
    return found or None


def _manifest_mismatch(glb: Path) -> bool:
    """Does the manifest beside ``glb`` record other bytes for it?

    Deli Counter 0.131.1 writes `outputs_sha256_16` into the tracked manifest
    of every build. `build/*.glb` is gitignored, so a checkout moves the
    manifest to a new build while the old shell stays on disk; mtime sees that
    only when a geometry source moved too. A manifest without the field (built
    before 0.131.1) is not judged on it."""
    import hashlib
    import json
    mpath = glb.with_name(glb.stem + ".manifest.json")
    try:
        man = json.loads(mpath.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    want = (man.get("outputs_sha256_16") or {}).get(glb.name)
    if not want:
        return False
    h = hashlib.sha256()
    with glb.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:16] != want


def stale_shells(build_dir) -> tuple[list[str] | None, float]:
    """``(names, worst_gap_days)`` for shells older than the code building them
    or not the build their manifest records; ``(None, 0.0)`` when Deli
    Counter's rule is present and could not be read (see `_geometry_sources`).

    THE CONSUMER'S GUARD, NOT THE AUTHORITY. `deli_counter/build_freshness.py`
    owns this question, was written for it on 2026-08-05 after `nav_gate --all`
    graded ten stairs across seven fossil shells, and names every stale file
    with `--list`. This is the cheap version at the point of USE, because a
    Level Factory run reads this library every time and printed three lines
    about its health on 2026-08-12 while every shell in it was 4.2 days behind.

    Deli Counter's sources sit one directory up from its `build/`, which is the
    same relationship `build_freshness.py` assumes. If that stops being true
    this returns nothing rather than guessing.

    mtime, with the caveat the owning tool records: a fresh clone or a checkout
    that rewrites sources marks everything stale, asking for a rebuild that was
    not needed -- the safe direction. The unsafe direction needs a source
    written with an OLDER timestamp than the build, which git does not do in
    normal use -- or an untracked shell left behind by a checkout, which is
    what `_manifest_mismatch` answers.
    """
    build = Path(build_dir)
    src = build.parent
    if not build.is_dir() or not src.is_dir():
        return [], 0.0
    sources = _geometry_sources(src)
    if sources is None:
        return None, 0.0
    if not sources:
        return [], 0.0
    try:
        newest = max((p.stat().st_mtime for p in sources), default=0.0)
        if not newest:
            return [], 0.0
        gaps = []
        for p in sorted(build.glob("*.glb")):
            gap = newest - p.stat().st_mtime
            if gap > 0 or _manifest_mismatch(p):
                gaps.append((p.name, max(gap, 0.0)))
    except OSError:
        return [], 0.0
    worst = max((g for _n, g in gaps), default=0.0) / 86400.0
    return [n for n, _g in gaps], worst


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


def anchor_families(entries: list[dict], archetype: str) -> list[str]:
    """The library families that ARE the brief's archetype, sorted.

    A bank brief's lot must contain a bank. Cold run 9007 (2026-09-12) set
    `archetype: urban_bank`, `building_count: 3`, `lot_library` -- and
    `pick_lot` drew `arena_a03`, `clinic_a01`, `landmark_hall_a01`, because it
    took a seed and a count and nothing about the brief. Every stage passed;
    the deliverable was a bank block with no bank in it, which is the
    `_preset_for` failure ("a wrong-but-plausible building") one level up.

    Matching is by NAME PARTS, the way `_preset_for` strips a qualifier:
    the family equal to the archetype (`bank`), a family that begins with it
    (`bank_branch`, `bank_tower`, `bank_job` for `bank`), or one whose first
    token is the archetype's last (`urban_bank` -> `bank_*`). Empty when the
    library has no such family, and the caller says so rather than
    guessing -- a `hospital` brief against this library gets no anchor
    today, and that is a true fact about the library.
    """
    a = str(archetype or "").strip().lower()
    if not a:
        return []
    fams = sorted({e.get("family", "") for e in entries if e.get("family")})
    last = a.rsplit("_", 1)[-1]
    out = []
    for f in fams:
        fl = f.lower()
        if fl == a or fl.startswith(a + "_") or fl.split("_", 1)[0] == last:
            out.append(f)
    return out


def score_building(entries: list[dict], archetype: str):
    """The site building that IS the score: ``"b0"`` when a library family
    answers to the brief's archetype, ``None`` when none does.

    `pick_lot` places a variant of an anchor family FIRST, so the archetype's
    building is always b0 on an anchored lot. With no such family the
    archetype is not on the site at all, and the seeded pick stands rather
    than a guess (0.152.0, roadmap 201).
    """
    return "b0" if anchor_families(entries, archetype) else None


def pick_lot(entries: list[dict], seed: int, count: int,
             anchor: str = None, preferred=None) -> list[dict]:
    """``count`` archetypes for one candidate, no two from the same family.

    ``anchor`` (roadmap 44 / cold run 9007): the brief's archetype. When a
    family answers to it (`anchor_families`), the FIRST place is a variant of
    one of those families -- drawn by the same stream, so five candidates
    still get five lots -- and the rest are drawn as before without it. No
    anchor, or none in the library, is the draw that always was.

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
    anchors = anchor_families(entries, anchor) if anchor else []
    if anchors:
        fam = anchors[next(rng) % len(anchors)]
        pool.remove(fam)
        variants = by_family[fam]
        out.append(variants[next(rng) % len(variants)])
    # THE TEMPLATE'S FAMILIES FIRST (0.176.0, roadmap 230): in the order the
    # guide lists them, each drawn from the pool when the library has it, the
    # stream spent on the variant alone -- so a brief with no template keeps
    # 0.175.1's draw byte for byte, and a family the library lacks is skipped.
    for fam in (preferred or ()):
        if len(out) >= count:
            break
        if fam in pool:
            pool.remove(fam)
            variants = by_family[fam]
            out.append(variants[next(rng) % len(variants)])
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


#: A HOLE IN A FLOOR IS RARE (0.221.0, factory roadmap 269). The walker,
#: 2026-10-20: "stairs and ladders should be the primary way to get between
#: floors in this game...with the holes in floors being somewhat rare...but
#: still at our disposal to use if needed/desired to add some more ways to
#: navigate levels". The chance that one candidate's level carries a hole in
#: a floor, where its buildings can hold one.
#:
#: A CALL, made 2026-10-20 and meant to be changed. Measured before it (the
#: factory's docs/findings/hole_frequency/, Level Factory's own draw replayed
#: over every staged brief): 54 of 288 lot levels carried one, and every level
#: of restaurant_row_001 and urban_row_001 among them -- the deli anchors both
#: and both of its themeable variants carried the cut drop -- and every level
#: of the single-building deli and county-hospital missions, whose presets
#: author one. A brief's `floor_holes` overrides it: 0 never, 1 wherever the
#: lot can hold one.
FLOOR_HOLE_RATE = 0.25


def floor_hole_rate(model) -> float:
    """The brief's `floor_holes`, held to 0..1, or FLOOR_HOLE_RATE when it names none."""
    raw = getattr(model, "floor_holes", None)
    if raw is None:
        return FLOOR_HOLE_RATE
    return min(1.0, max(0.0, float(raw)))


def holes_wanted(candidate, rate) -> bool:
    """Does this candidate's level carry a hole in a floor?

    Keyed on the CANDIDATE ID (`packages.core.ids.candidate_id`), the string
    every caller names a level by -- so the lot's draw and the mission's own
    building ask the same question and get the same answer -- on a stream of
    its own (`_unit`, not `stream`), so it moves no other draw. 0 is never and
    1 always.
    """
    rate = float(rate)
    if rate <= 0.0:
        return False
    if rate >= 1.0:
        return True
    return _unit("floor_holes:%s" % candidate) < rate


def _unit(key: str) -> float:
    """A number in [0, 1) that is `key`'s alone: the first eight bytes of its SHA-256.

    NOT CRC32, measured while this was written: CRC is affine over GF(2), so
    two keys that differ only in a prefix -- `restaurant_row_001.candidate.
    seed_<n>` and `urban_row_001.candidate.seed_<n>` -- XOR to one constant for
    every n, and at a rate of 0.5 the two missions came out with the same
    answer for 200 seeds of 200.
    """
    return int.from_bytes(hashlib.sha256(key.encode("utf-8")).digest()[:8], "big") / 18446744073709551616.0


def carries_hole(entry) -> bool:
    """Does this built building have a hole in a floor a player sees?

    Deli Counter marks a drop by giving its vertical link a `cause` (0.236.0)
    -- a roof hatch has none -- and a drop whose cause is `stair` opens into a
    stair's own well, where nothing of it shows. LEVEL FACTORY DOES NOT
    COMPUTE THIS, for the reason `scoped_verdict` gives: it reads a field. An
    unreadable record carries none, because this module lists and counts and
    never raises while a plan is built.
    """
    data = _manifest(entry.get("gameplay") if isinstance(entry, dict) else entry)
    links = (data or {}).get("vertical_links") or []
    return any(isinstance(v, dict) and "cause" in v and v.get("cause") != "stair"
               for v in links)


def apply_hole_rule(lot, entries, candidate, rate):
    """``(lot, wanted, swaps)``: `lot` with its buildings' VARIANTS swapped so
    the level carries a hole in a floor only when `holes_wanted` says so.
    ``swaps`` is ``[(from id, to id or None)]``, None where the family had no
    variant to swap to.

    NOT WANTED: each building with a hole swaps for a variant of its family
    without one that is not already in the lot; a family with none keeps its
    building, and the swap says so. WANTED: a lot that already holds one
    stands as drawn; otherwise the first building whose family has a variant
    with a hole swaps for it, and a lot whose families have none stands too.

    THE FAMILY IS KEPT, never the family's place: `pick_lot`'s draw --
    families without replacement, the anchor first -- stands, so a lot the
    rule does not touch is the lot it always was, and the score building is
    still the brief's archetype. Which variant: sorted by id, picked on the
    candidate's own stream. Only the swapped building's family is read, so a
    lot costs a handful of manifests, not the library.
    """
    wanted = holes_wanted(candidate, rate)
    out = list(lot)
    have = [carries_hole(e) for e in out]
    swaps: list = []
    if wanted and any(have):
        return out, wanted, swaps
    used = {e.get("id") for e in out}
    for i, e in enumerate(out):
        if have[i] == wanted:
            continue
        fam = e.get("family", "")
        alts = sorted((x for x in entries
                       if x.get("family", "") == fam and x.get("id") not in used
                       and carries_hole(x) == wanted),
                      key=lambda x: x.get("id", ""))
        if not alts:
            if not wanted:
                swaps.append((e.get("id"), None))
            continue
        pick = alts[int(_unit("floor_hole_variant:%s:%d" % (candidate, i)) * len(alts))]
        used.discard(e.get("id"))
        used.add(pick.get("id"))
        out[i] = pick
        swaps.append((e.get("id"), pick.get("id")))
        if wanted:
            break
    return out, wanted, swaps


def draw_lot(entries: list[dict], seed: int, count: int, *, anchor: str = None,
             preferred=None, candidate: str = "", hole_rate: float = None) -> list[dict]:
    """THE DRAW: `pick_lot`, then the hole rule (0.221.0).

    The one place the two meet. `lot_for` comes here, and so does the site
    spec's own draw (`apps.cli.commands._write_site_spec`, the fourth draw,
    which indexes and filters the library itself), so the buildings the
    planner fans out, the compose spec dresses and the site places are one lot
    by construction rather than four derivations that agree. ``candidate`` is
    the candidate id; ``hole_rate`` None is FLOOR_HOLE_RATE.
    """
    lot = pick_lot(entries, seed, count, anchor=anchor, preferred=preferred)
    rate = FLOOR_HOLE_RATE if hole_rate is None else hole_rate
    return apply_hole_rule(lot, entries, candidate or str(seed), rate)[0]


def lot_for(library, building_count, candidate_id, *,
            themed: bool = False, anchor: str = None,
            preferred=None, hole_rate: float = None) -> tuple[list[dict], list[dict]]:
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
    # A HOLE IN A FLOOR IS RARE (0.221.0): `draw_lot` swaps a drawn family's
    # VARIANT, never the family, so only a lot the rule touches changes.
    return draw_lot(complete, seed, count, anchor=anchor, preferred=preferred,
                    candidate=str(candidate_id), hole_rate=hole_rate), incomplete


def preferred_for_brief(model):
    """The cluster template's families for a brief, or None (0.176.1): the one
    place the template is read off a brief, so the site spec's own draw and
    `lot_for_brief` cannot disagree about it. Cold run 9231: the planner and
    the compose spec drew the template's lot and the site spec drew the old
    one, the art leg dressed a pharmacy the site never placed, and the
    export's closure gate stopped the run on the station's unresolved glb."""
    from packages.pipeline import cluster
    template = cluster.template_for(getattr(model, "cluster", ""),
                                    getattr(model, "archetype", "") or "")
    return cluster.preferred_families(template) if template else None


def lot_for_brief(model, candidate_id, *, themed: bool = False):
    """`lot_for` read off a brief: library, count and ARCHETYPE from one
    object, so the three callers cannot disagree by construction.

    0.73.0 threaded the anchor through the planner alone, and cold run 9008
    fired the guard written for exactly that: "zoo_fixtures_build.
    bank_branch_a02 is planned for archetype 'bank_branch_a02', which is not
    in this candidate's lot -- the planner and the spec builder disagree".
    The compose spec and the site spec had drawn unanchored lots
    (marina / pawn_shop / strip_club for `urban_bank`). Three call sites
    reading three subsets of one brief is how that happens; this is the
    subset.
    """
    # the cluster template's families, when the brief names one (0.176.0),
    # read by the one function the site spec builder also asks (0.176.1)
    return lot_for(getattr(model, "lot_library", None),
                   getattr(model, "building_count", 1),
                   candidate_id, themed=themed,
                   anchor=getattr(model, "archetype", "") or "",
                   preferred=preferred_for_brief(model),
                   hole_rate=floor_hole_rate(model))


def footprints_for(lot: list[dict], measure) -> list:
    """Each picked building's footprint, via ``site_variation.shell_footprint``.

    ``measure`` is injected so this module stays free of the GLB reader and the
    caller can hand it a cached one -- measuring the same shell five times, once
    per candidate, is the kind of cost that turns a fast stage slow quietly.
    A shell that cannot be measured yields ``None``, which
    ``site_variation.row_offsets`` already treats as DEFAULT_FOOTPRINT.
    """
    return [measure(e["glb"]) for e in lot]


def has_roof_slot(entry) -> bool:
    """Does this library building's slot manifest carry a roof slot -- the
    hook Zoo's roof props are planned on (0.179.0, roadmap 181)? False for
    a manifest that cannot be read: a building whose slots are unreadable
    gets no roof job rather than one that fails in Blender, and
    `require_art_inputs` has already judged what the mission needs."""
    data = _manifest(entry.get("slots") if isinstance(entry, dict) else entry)
    return any(isinstance(s, dict) and s.get("role") == "roof"
               for s in ((data or {}).get("slots") or []))


#: EMPTIES (0.137.0): Deli Counter's non-enterable shells with real fronts
#: (roadmap 106; Deli Counter 0.174.0 builds the rowhome family), by the id
#: prefix it gives them. `gs_facade_rowhome` and `gs_facade_storefront`, the
#: two sealed boxes from before, do not carry it and are not offered.
EMPTY_PREFIX = "gs_empty_"
#: THE MID-RISE EMPTIES (0.200.0, factory roadmap 241): Deli Counter 0.213.0's
#: family, named out of `EMPTY_PREFIX` so no strip terrace draws them; an
#: urban brief draws them instead of the rowhomes.
MIDRISE_PREFIX = "gs_midrise_"
#: THE CORNER BLOCKS (0.206.0, factory roadmap 241): Deli Counter 0.218.0's
#: mid-rises whose ground-floor front is a shop. An urban brief draws them
#: as their own family, and the wall stands one only where a run of it opens
#: or closes (`empties.terrace`). Not `gs_corner_`: that is
#: `gs_corner_station`'s, an enterable gas station.
CORNER_PREFIX = "gs_cornershop_"


def empty_rows(build_dir, prefix=EMPTY_PREFIX, family="empty") -> list[dict]:
    """Every Empty in a Deli Counter build dir that can be themed, sorted by
    id: ``{"id", "family", "glb", "gameplay", "slots"}``, ``family`` as
    given -- ``empty``, or ``corner`` for the corner blocks (0.206.0). An Empty is one
    Deli Counter says is (`facade` true in its validation manifest) and whose
    id carries `EMPTY_PREFIX`; it has no lights by design (its lit windows
    are paint), so `.lights.json` is not asked for."""
    d = Path(str(build_dir))
    out = []
    for glb in sorted(d.glob(prefix + "*.glb")):
        aid = glb.stem
        row = {"id": aid, "family": family, "glb": str(glb),
               "gameplay": str(d / f"{aid}.gameplay.json"),
               "slots": str(d / f"{aid}.slots.json")}
        if not all(Path(row[k]).exists() for k in ("gameplay", "slots")):
            continue
        if (_manifest(d / (aid + ".validation.json")) or {}).get("facade") is not True:
            continue
        out.append(row)
    return out


def empties_for_brief(model) -> list[dict]:
    """The Empties a brief gets: every themeable one in its lot library when
    `models.empties_effective` says a terrace stands -- `empties: across`,
    the default since 0.144.0, and a varied lot -- [] otherwise. ONE list
    for the planner (which fans their art jobs out), the compose rows and the
    site spec, the way `lot_for_brief` is one lot. A model with no `empties`
    attribute at all reads as the default."""
    library = getattr(model, "lot_library", None)
    if not empties_effective(getattr(model, "empties", EMPTIES_ACROSS), library,
                             getattr(model, "building_count", 1)):
        return []
    empties = empties_effective(getattr(model, "empties", EMPTIES_ACROSS), library,
                                getattr(model, "building_count", 1))
    if streetscape_effective(getattr(model, "streetscape", ""), empties):
        # and the corner blocks (0.206.0, roadmap 241), as their own family:
        # the wall stands them only where a run of it opens or closes
        return (empty_rows(library, MIDRISE_PREFIX)
                + empty_rows(library, CORNER_PREFIX, family="corner"))
    return empty_rows(library)
