"""Everything Laser Tag will play and then mark down, as findings (TDD 5.5, 24.3).

The refusals have a home already: `spawn_placement.check_spawn_placement`,
`ground_contact.check_ground_contact` and `lt_hooks.check_scene_hooks` say when
the evaluator will hand the map back before playing a single run, and the
adapter's pre-flight stops the build on them because 900 seconds of Godot would
buy a report about a match nobody played.

This module is the other half, and it exists because that half kept being
treated as the whole. A firefight evaluator is a design instrument, not a
building code. "The crew and Enemy_3 can see each other across ninety-two
metres of empty street" is a true and useful statement about a level that
absolutely does exist, loads, bakes and plays. Refusing to build it converts a
note about where cover belongs into a level that is not there to put cover in.

So: three sources, one shape, nothing blocking.

* the standoff and the floating markers, from `spawn_placement`'s advisory
  pass -- an enemy inside the range somebody opens fire at, and a marker naming
  a position in the air rather than on a floor;
* the open sightlines, from `sightlines` -- with a coordinate attached, because
  "put a solid near (52.1, -12.4)" is the form Lot can act on and "the map is
  too open" is not;
* the engagement contract itself, from `lasertag_contract` -- whether the range
  the producer sized its placement against is still the range the evaluator
  opens fire at, and whether that range is even settable from the scenario
  resource somebody would go looking in.

The third one is the only check in either repository that can catch the two
numbers drifting apart, because it is the only place that can see both
checkouts at once. Lot carries `site_spawns.OPENING_RANGE` and states where the
number came from; this reads Lot's source for that statement and Laser Tag's
files for the truth, and says so when they stop agreeing. That is a weaker
coupling than importing across tools and a much stronger one than a comment.

Pure text and paths in, normalized finding dicts out. No Godot, no scheduler.
"""
from __future__ import annotations

import re
from pathlib import Path

from packages.validation import lasertag_contract, model, sightlines
from packages.validation.ground_contact import (
    Reading, mission_points, read_scene_text, resolver)
from packages.validation.spawn_placement import (
    CODE_FLOATING, CODE_STANDOFF, advise_spawn_placement_coded, classify)

#: Open ground somebody can open fire across. The one finding that is a
#: placement instruction rather than a complaint.
CODE_SIGHTLINE = "LT_OPEN_SIGHTLINE"

#: The producer's stated opening range no longer matches the evaluator's.
CODE_DRIFT = "LT_ENGAGEMENT_DRIFT"

#: The scenario resource does not expose the number that decides first contact.
CODE_NOT_CONFIGURABLE = "LT_ENGAGEMENT_NOT_CONFIGURABLE"

#: Severity and category per code. Every one of these is a design signal, so
#: none of them is a blocker and the scheduler forces that regardless -- what
#: the severity decides is reading order, not whether a level gets made.
_FILING = {
    CODE_STANDOFF: (model.MODERATE, "spawn"),
    CODE_FLOATING: (model.MINOR, "spawn"),
    CODE_SIGHTLINE: (model.MODERATE, "combat_structure"),
    CODE_DRIFT: (model.MODERATE, "configuration"),
    CODE_NOT_CONFIGURABLE: (model.MINOR, "configuration"),
}

#: What Lot states its placement is sized against. Read rather than assumed:
#: the constant is the producer's claim about the evaluator, and a claim is
#: exactly the kind of thing that goes stale without anything failing.
_LOT_OPENING = re.compile(r'^OPENING_RANGE\s*=\s*([0-9]+(?:\.[0-9]*)?)', re.M)
_LOT_SOURCE = "site_spawns.py"


def _finding(code: str, message: str, *, fix: str = "",
             location: str = "") -> dict:
    severity, category = _FILING.get(code, (model.MINOR, "configuration"))
    return {"code": code, "severity": severity, "category": category,
            "message": message, "suggested_fix": fix, "location": location,
            # Stated rather than implied. This dict travels to a model whose
            # default is "blocking when severity is blocker", and every reader
            # of a finding from this module is entitled to see, on the finding,
            # that it was never going to stop anything.
            "blocking": False}


def lot_opening_range(repository) -> float | None:
    """The opening range Lot places enemies against, read from its source.

    ``None`` when there is no Lot checkout to read or the constant is not in
    it, which is the honest answer and not a finding: a run configured without
    Lot has no producer claim to check, and a missing constant means the module
    was reorganized rather than that the number is wrong.
    """
    if not repository:
        return None
    try:
        text = (Path(repository) / _LOT_SOURCE).read_text(
            encoding="utf-8", errors="replace")
    except OSError:
        return None
    match = _LOT_OPENING.search(text)
    return float(match.group(1)) if match else None


def engagement_findings(engagement, assumed: float | None = None) -> list[dict]:
    """What the two checkouts disagree about, if anything.

    ``assumed`` is the producer's number, or ``None`` when it could not be read.
    Nothing is invented in that case -- a drift check against a default would be
    a check of this module's memory rather than of the pipeline.
    """
    out = [_finding(CODE_NOT_CONFIGURABLE, message,
                    location="LT_MapEvalHarness.gd")
           for message in lasertag_contract.check_configurability(engagement)]
    if assumed is not None:
        out.extend(
            _finding(CODE_DRIFT, message,
                     fix=(f"set {_LOT_SOURCE}'s OPENING_RANGE to "
                          f"{engagement.opening_range:g}"),
                     location=f"lot/{_LOT_SOURCE}")
            for message in lasertag_contract.check_drift(assumed, engagement,
                                                         who="Lot"))
    return out


#: Which name survives when two mission markers stand on the same spot, most
#: informative first. A sightline is named by its endpoints, so the name decides
#: what the reader goes looking for.
_RANK = ("LT_PlayerSpawn", "LT_ObjectivePoint")


def _one_name_per_position(named: dict) -> dict:
    """Collapse markers that name the same position under two names.

    `spawn_placement.classify` already does this among the destinations, for
    the reason spelled out there -- Lot emits its objective a second time as
    ``Route_1`` -- but the crew spawn is not a destination and escapes it. A
    mission whose objective is the place the crew starts (defend the site, hold
    the ground) then draws every street twice: once from the spawn and once
    from the objective standing on it, at identical lengths, with identical
    cover proposals. That does not read as a duplicate. It reads as a site
    twice as open as it is, which is the wrong number to hand someone deciding
    how much cover to build.
    """
    best: dict = {}
    for name, point in named.items():
        key = tuple(round(c, 3) for c in point)
        rank = _RANK.index(name) if name in _RANK else len(_RANK)
        keep = best.get(key)
        if keep is None or (rank, name) < (keep[0], keep[1]):
            best[key] = (rank, name, point)
    return {name: point for _rank, name, point in best.values()}


def scene_findings(text: str, reading: Reading, *,
                   opening_range: float) -> list[dict]:
    """The tactical findings readable out of one staged scene.

    ``opening_range`` is passed rather than looked up so this stays pure and so
    a caller that read the real scenario for this run reports against it, not
    against `lasertag_contract.MEASURED`'s snapshot.
    """
    out = [_finding(code, message) for code, message in
           advise_spawn_placement_coded(text, reading,
                                        opening_range=opening_range)]

    points = mission_points(text)
    player, enemies, destinations = classify(points)
    if player is None:
        # No crew spawn is `check_scene_hooks`' finding, and every sightline
        # worth drawing on a mission map starts or ends at the crew.
        return out
    lines = sightlines.open_sightlines(
        _one_name_per_position({"LT_PlayerSpawn": player,
                                **enemies, **destinations}),
        reading.boxes, limit=opening_range)
    out.extend(_finding(CODE_SIGHTLINE, message, fix=fix.lstrip("; "))
               for message, fix in sightlines.advise(lines, limit=opening_range,
                                                     boxes=reading.boxes))
    return out


def advise_scene(scene, *, engagement=None, lot_repository=None) -> list[dict]:
    """Every advisory for the scene at ``scene``, engagement contract included.

    A missing or unreadable scene is silence rather than a finding: the adapter's
    pre-flight owns "there is no scene here", and saying it twice in two
    different registers makes one defect read as two.
    """
    engagement = engagement or lasertag_contract.MEASURED
    out = engagement_findings(engagement, lot_opening_range(lot_repository))
    scene = Path(scene) if scene else None
    if scene is None or not scene.is_file():
        return out
    text = scene.read_text(encoding="utf-8", errors="replace")
    reading = read_scene_text(text, resolve=resolver(scene.parent),
                              _seen=frozenset({scene}))
    return out + scene_findings(text, reading,
                                opening_range=engagement.opening_range)
