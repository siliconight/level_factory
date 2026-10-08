"""Stage real Deli Counter + Lot outputs into the file shapes Dispatch 0.3.0
requires (TDD grounding: 24.8 handoff bridge).

Dispatch's resolver (see the tool's docs/FORMATS.md) needs, beside each manifest:

    deli_counter/  shell.gameplay.json (manifest) + shell.glb + shell.nav_hints.json
    lot/           lot.layout.json (manifest) + lot.gameplay.json + lot.nav_hints.json + lot.glb

But DC and Lot natively emit a richer ``markers``/``objectives``/``loot``/``zones``
schema (positions as x/y/z), not Dispatch's ``anchors: [{id,type,pos}]`` +
``nav_hints: {nodes, links}``. This module maps between them.

Design (per the Siliconight pipeline roles): DC+Zoo own collision, Lot owns the
site layout + nav, and Dispatch's mission-objective layer is OPTIONAL — the model
is just a shell. So we map the affordance markers (doors, cover, landmarks, loot)
into anchors as descriptive data, derive a connectivity nav graph, and reuse the
DC shell glb for the (passthrough) lot glb. The mission itself stays minimal and
non-blocking (see _write_dispatch_spec).
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Iterable

# DC / Lot marker "type" -> Dispatch anchor "type" (one of Dispatch's known set:
# player_start, ai_spawn, objective, door, loot, cover, patrol_point,
# extraction, trigger, breach_point, interaction, camera_debug). Unknown types
# are passed through (Dispatch produces nodes for them but doesn't validate).
_TYPE_MAP = {
    "cover_low": "cover", "cover_high": "cover", "cover": "cover",
    "door": "door", "opening": "door", "breach": "breach_point",
    "objective": "objective", "loot": "loot", "landmark": "interaction",
    "player_start": "player_start", "spawn": "player_start",
    "ai_spawn": "ai_spawn", "cop_spawn": "ai_spawn", "patrol": "patrol_point",
    "extraction": "extraction", "exit": "extraction", "interactive": "interaction",
}


def _num(v, default=0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return float(default)


def _pos(rec: dict, up: str) -> list:
    if isinstance(rec.get("pos"), (list, tuple)) and len(rec["pos"]) >= 3:
        return [_num(rec["pos"][0]), _num(rec["pos"][1]), _num(rec["pos"][2])]
    return [_num(rec.get("x")), _num(rec.get("y")), _num(rec.get("z"))]


def _iter_records(gameplay: dict) -> Iterable[tuple]:
    """Yield (record, fallback_type) across the arrays DC/Lot use."""
    for rec in gameplay.get("markers", []) or []:
        yield rec, rec.get("type", "interaction")
    for rec in gameplay.get("objectives", []) or []:
        yield rec, "objective"
    for rec in gameplay.get("loot", []) or []:
        yield rec, "loot"


def markers_to_anchors(gameplay: dict, source: str, up: str = "z") -> list:
    """Map DC/Lot gameplay records to Dispatch anchors. Ids are prefixed with the
    source so they're unique across all inputs (Dispatch requires global id
    uniqueness)."""
    anchors: list = []
    seen: set = set()
    for i, (rec, ftype) in enumerate(_iter_records(gameplay)):
        raw_type = str(rec.get("type", ftype) or ftype)
        atype = _TYPE_MAP.get(raw_type, raw_type)  # pass unknown through
        rid = str(rec.get("id") or rec.get("name") or f"{ftype}_{i}")
        aid = f"{source}:{rid}"
        if aid in seen:
            aid = f"{aid}_{i}"
        seen.add(aid)
        anchor = {"id": aid, "type": atype, "pos": _pos(rec, up)}
        tags = rec.get("tags")
        if isinstance(tags, list) and tags:
            anchor["tags"] = list(tags)
        if rec.get("objective"):
            anchor["objective"] = str(rec["objective"])
        if "rot_y" in rec or "rot" in rec:
            anchor["rot_y"] = _num(rec.get("rot_y", rec.get("rot")))
        # THE BUILDING IT BELONGS TO (0.158.0, roadmap 204). Lot
        # namespaces each marker by its building, and Dispatch writes an
        # anchor's `building` as its `source_building` -- which was "" on
        # every anchor of every package, because this never passed it.
        if rec.get("building"):
            anchor["building"] = str(rec["building"])
        anchors.append(anchor)
    return anchors


#: Lot's SITE-LEVEL markers (its gameplay file's `site_markers`) -> the
#: Dispatch anchor type each becomes and the mission-flow tag it carries.
#: A site-level `crew_spawn` and `extraction` are the mission's own: Lot's
#: `_walk_positions` takes them over any building's, which is how the
#: getaway van (Lot 0.98.0) puts the crew's start and exit at its door. A
#: `responder_spawn` is where responders arrive (Lot 0.99.0, roadmap 212).
_SITE_MARKERS = {
    "crew_spawn": ("player_start", "mission_start"),
    "extraction": ("extraction", "extraction"),
    "responder_spawn": ("ai_spawn", "responder"),
}


def site_marker_anchor_pairs(gameplay: dict, source: str) -> list:
    """``(marker, anchor)`` for each of Lot's site-level markers that becomes a
    Dispatch anchor (0.156.0, roadmap 204). One counting of the ids for every
    reader of them: the staging, and the export's `responder_arrivals.json`,
    which names each arrival by the anchor it is (0.157.0) -- two spellings
    of one id would be two places for it to drift.

    `_iter_records` reads `markers`, `objectives` and `loot`, and the site's
    own markers live in `site_markers` -- so until 0.156.0 no site-level
    marker reached Dispatch. The getaway van's crew spawn and extraction
    never became the package's; `ensure_mission_anchors` synthesized a
    `player_start` at the centroid of every Lot anchor and tagged every
    building's extraction as the mission's (cold run 9198's package:
    `lot:mission_start` at (-7.03, 0.68), 14 m from the van).

    A site marker stands on the plate: `at` is a plan point, and its height
    is the ground's, as `lot._walk_positions` reads it. No facing is
    passed: a Lot slot yaw and a Dispatch `rot_y` have not been shown to
    share a convention, and a yaw read in the wrong one is silently wrong."""
    pairs: list = []
    counts: dict = {}
    for m in gameplay.get("site_markers", []) or []:
        if not isinstance(m, dict):
            continue
        at = m.get("at")
        if not isinstance(at, (list, tuple)) or len(at) < 2:
            continue
        raw = str(m.get("type") or "interaction")
        atype, tag = _SITE_MARKERS.get(raw, (_TYPE_MAP.get(raw, raw), None))
        origin = str(m.get("source") or "site")
        n = counts.get((origin, raw), 0)
        counts[(origin, raw)] = n + 1
        anchor = {"id": f"{source}:{origin}_{raw}_{n}", "type": atype,
                  "pos": [_num(at[0]), _num(at[1]), 0.0]}
        if tag:
            anchor["tags"] = [tag]
        pairs.append((m, anchor))
    return pairs


def site_markers_to_anchors(gameplay: dict, source: str) -> list:
    """Lot's site-level markers as Dispatch anchors: the anchors of
    `site_marker_anchor_pairs`."""
    return [anchor for _m, anchor in site_marker_anchor_pairs(gameplay, source)]


#: anchor type -> the `mission_flow` location_tag that binds to it.
#: `location_tag` matches an anchor's TAGS, never its type, so a type with no
#: tagged instance is invisible to the mission flow no matter how many of them
#: the level contains.
_MISSION_TAG = {"player_start": "mission_start", "extraction": "extraction"}


def ensure_mission_anchors(anchors: list, source: str, up: str = "z") -> list:
    """Guarantee the spawn and extraction TAGS exist, so the mission flow has
    something to bind to -- without inventing a mission.

    Ensuring the tag rather than the type, because the tag is what binds.
    `mission_flow` asks for `location_tag: "extraction"` and the binder reads
    `tags`; an anchor merely TYPED extraction is invisible to it.

    That distinction was the whole defect, and it made correct data worse than
    missing data. Both branches used to be guarded on the type being absent, so
    the tag arrived only when the level had nothing. Measured on lot_demo_001,
    135 anchors: Lot emits no `player_start`, so one was synthesized WITH its
    tag and `spawn` bound; Lot emits five real `extraction` anchors -- BAY,
    CENTER_FIELD_TRUCK, DRIVE, LOT, LOT_11, all `"tags": []` -- so the branch
    was skipped, nothing carried the tag, and Dispatch refused the mission:
    "BLOCKER [assembly] Proposed beat 'extract' binds to no anchor and has no
    trigger." Deleting the five would have made it pass.

    Order: already tagged -> leave it; typed but untagged -> tag them, they ARE
    what the beat asks for; neither -> synthesize at the centroid as before.

    ALL matching anchors get the tag, not the first. `shell_ids` on a beat is a
    list. Tagging one would say "this extraction point is the mission's", which
    is a claim about the mission, and this function's contract is not to make
    those.
    """
    if anchors:
        cx = sum(a["pos"][0] for a in anchors) / len(anchors)
        cy = sum(a["pos"][1] for a in anchors) / len(anchors)
    else:
        cx = cy = 0.0

    for atype, tag in _MISSION_TAG.items():
        tagged = [a for a in anchors if tag in (a.get("tags") or ())]
        if tagged:
            continue
        typed = [a for a in anchors if a.get("type") == atype]
        if typed:
            for a in typed:
                a["tags"] = list(a.get("tags") or ()) + [tag]
            continue
        made = {"id": f"{source}:{tag}", "type": atype,
                "pos": [cx, cy, 0.0], "tags": [tag]}
        if atype == "player_start":
            anchors.insert(0, made)
        else:
            anchors.append(made)
    return anchors


def derive_nav(anchors: list, source: str, up: str = "z") -> dict:
    """A connectivity nav graph over the anchor positions: one node per anchor,
    linked into a connected chain so reachability passes. Lot owns the real
    walkable nav (baked into its walk .tscn); this is the handoff's coarse graph.
    """
    nodes = [{"id": a["id"].split(":", 1)[-1], "pos": a["pos"]} for a in anchors]
    links = [[nodes[i]["id"], nodes[i + 1]["id"]] for i in range(len(nodes) - 1)]
    return {"schema": "dc.nav_hints.v1", "up_axis": up, "nodes": nodes, "links": links}


def _bounds(anchors: list) -> list:
    if not anchors:
        return [[-1, -1, 0], [1, 1, 4]]
    xs = [a["pos"][0] for a in anchors]; ys = [a["pos"][1] for a in anchors]
    zs = [a["pos"][2] for a in anchors]
    pad = 4.0
    return [[min(xs) - pad, min(ys) - pad, min(zs)],
            [max(xs) + pad, max(ys) + pad, max(zs) + 8.0]]


def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def stage_dispatch_inputs(dest_dir: Path, *, deli_gameplay: Path, shell_glb: Path,
                          lot_gameplay: Path, mission_id: str,
                          theme: str = "", up: str = "z",
                          lot_site: Path | None = None) -> dict:
    """Write Dispatch-shaped deli_counter/ and lot/ input trees under dest_dir.
    Returns {"deli_counter": <manifest path>, "lot": <manifest path>}.

    ``lot_site`` is the Lot job's drawn site spec (`site.site.drawn.json`),
    read for which building is the score (0.158.0); without it nothing is
    tagged `score`, and `mission_flow` writes the two beats it always did."""
    dest_dir = Path(dest_dir)
    deli_dir = dest_dir / "deli_counter"; deli_dir.mkdir(parents=True, exist_ok=True)
    lot_dir = dest_dir / "lot"; lot_dir.mkdir(parents=True, exist_ok=True)
    lic = {"name": "proprietary-siliconight", "source": ""}

    # ---- deli_counter (collision shell) ----
    # THE SITE CARRIES ITS BUILDINGS (0.158.0, roadmap 204). Lot's gameplay
    # holds every placed building's markers in site space -- the
    # generated shell's among them, when the lot places it. Staged beside
    # them, the shell's own were wrong either way:
    #   * on a library lot the shell is never placed, so they were the
    #     anchors of a building that is not in the level, listed first
    #     (cold run 9194: its vault objective among them);
    #   * on deli_001 (cold run 9191), where it is placed, as b0 at (6, 0),
    #     all 85 duplicated Lot's b0 anchors by name, in the shell's own
    #     frame, 6 m off.
    # So the shell side is staged only when the site has no markers to
    # stand in for it. Its glb still passes through: it is the resolver's
    # file check, not an anchor.
    site_has_markers = bool(_read_json(Path(lot_gameplay)).get("markers"))
    dc_gp = {} if site_has_markers else _read_json(deli_gameplay)
    dc_up = str(dc_gp.get("up_axis", up))
    dc_anchors = markers_to_anchors(dc_gp, "deli_counter", dc_up)
    (deli_dir / "shell.gameplay.json").write_text(json.dumps({
        "schema": "dc.gameplay.v1", "license": {**lic, "source": "deli_counter"},
        "up_axis": dc_up, "anchors": dc_anchors,
        "props": list(dc_gp.get("props", []) or []),
        # Verbatim pass-through (see the lot side below); on a mission with
        # a Lot site the site-level concatenation wins in Dispatch.
        "interactives": list(dc_gp.get("interactives", []) or []),
        # LADDERS, for the same reason and with the same rule: verbatim. Deli
        # Counter files an off-mesh `nav_link` on each one, and Dispatch's
        # importer turns it into a link the AI can path over. This projection
        # is a whitelist, so a key it does not name is dropped in a way that
        # looks exactly like an upstream that never sent it -- which is why
        # the capability was claimed and falsified twice (roadmap 172).
        "ladders": list(dc_gp.get("ladders", []) or []),
    }, indent=2), encoding="utf-8")
    (deli_dir / "shell.nav_hints.json").write_text(
        json.dumps(derive_nav(dc_anchors or [{"id": "deli_counter:origin",
                    "type": "interaction", "pos": [0, 0, 0]}], "deli_counter", dc_up),
                   indent=2), encoding="utf-8")
    if shell_glb and Path(shell_glb).exists():
        shutil.copyfile(shell_glb, deli_dir / "shell.glb")
    else:  # a valid-enough placeholder so the resolver's file check passes
        (deli_dir / "shell.glb").write_bytes(b"glTF\x02\x00\x00\x00")

    # ---- lot (site layout + nav; glb is a passthrough of the DC shell) ----
    lot_gp = _read_json(lot_gameplay)
    lot_up = str(lot_gp.get("up_axis", up))
    # THE SITE'S OWN MARKERS FIRST (0.156.0, roadmap 204): the getaway van's
    # start and exit carry the mission's tags, so `ensure_mission_anchors`
    # finds them tagged -- it neither synthesizes a start at the centroid
    # nor tags every building's extraction as the mission's.
    lot_anchors = ensure_mission_anchors(
        site_markers_to_anchors(lot_gp, "lot") + markers_to_anchors(lot_gp, "lot", lot_up),
        "lot", lot_up)
    # THE SCORE (0.158.0, roadmap 204): the objective anchors of the site's
    # objective building, tagged so the mission flow can bind a beat to
    # them. Every anchor carried `"objective": ""`, so a package could not
    # say which of its objectives was the job.
    score = str(_read_json(Path(lot_site)).get("objective") or "") if lot_site else ""
    if score:
        for a in lot_anchors:
            if a.get("type") == "objective" and a.get("building") == score:
                a["tags"] = list(a.get("tags") or ()) + [SCORE_TAG]
    (lot_dir / "lot.gameplay.json").write_text(json.dumps({
        "schema": "lot.gameplay.v1", "license": {**lic, "source": "lot"},
        "up_axis": lot_up, "anchors": lot_anchors,
        "props": list(lot_gp.get("props", []) or []),
        # The replicable state machines Lot concatenated from every
        # building's gameplay.json (INTERACTIVES.md). Passed through
        # VERBATIM — no anchor mapping, no id rewriting: the ids are the
        # network handle, and Dispatch ships the declaration whole
        # (interactives.json beside gameplay_anchors.json).
        "interactives": list(lot_gp.get("interactives", []) or []),
        # LADDERS, concatenated by Lot from every building with every position
        # already moved into site space (Lot 0.76.0's `_ladder_to_site`, which
        # refuses on a numeric triple it does not recognise rather than
        # shipping one in the building's frame). Verbatim for the same reason
        # as `interactives`: re-projecting geometry here is how a nav link and
        # a route node end up disagreeing about where one ladder is.
        #
        # THIS LINE IS THE ONE THAT WAS MISSING. Cold run 9076 measured
        # ladders 1 in Lot's `site.site.gameplay.json` and no `ladders` key at
        # all in the file this writes, so Dispatch's Lot importer -- which had
        # been taught to read them in 0.5.1 -- found nothing and the package
        # shipped `links: 0` for the second run running.
        "ladders": list(lot_gp.get("ladders", []) or []),
    }, indent=2), encoding="utf-8")
    (lot_dir / "lot.layout.json").write_text(json.dumps({
        "schema": "lot.layout.v1", "license": {**lic, "source": "lot"},
        "up_axis": lot_up, "site": str(lot_gp.get("site", mission_id)),
        "bounds": _bounds(lot_anchors),
    }, indent=2), encoding="utf-8")
    (lot_dir / "lot.nav_hints.json").write_text(
        json.dumps(derive_nav(lot_anchors, "lot", lot_up), indent=2), encoding="utf-8")
    if shell_glb and Path(shell_glb).exists():
        shutil.copyfile(shell_glb, lot_dir / "lot.glb")
    else:
        (lot_dir / "lot.glb").write_bytes(b"glTF\x02\x00\x00\x00")

    return {"deli_counter": str(deli_dir / "shell.gameplay.json"),
            "lot": str(lot_dir / "lot.layout.json")}


#: The tag the score's objective anchors carry, and the beat that binds them.
SCORE_TAG = "score"


def mission_flow(dest_dir: Path) -> list:
    """The minimal flow for the staged inputs under ``dest_dir``: spawn, the
    score when the staging tagged one, extract (0.158.0).

    Still minimal and non-binding -- the gameplay team authors the real
    objectives -- but a heist has three beats, and the package said two.
    The score beat is written only when some anchor carries the tag:
    Dispatch refuses a mission whose beat binds to no anchor ("BLOCKER
    [assembly] Proposed beat 'extract' binds to no anchor"), which is why
    `ensure_mission_anchors` exists."""
    staged = _read_json(Path(dest_dir) / "lot" / "lot.gameplay.json")
    flow = [{"step": "spawn", "location_tag": "mission_start"}]
    if any(SCORE_TAG in (a.get("tags") or ()) for a in staged.get("anchors", []) or []):
        flow.append({"step": "score", "objective": SCORE_TAG})
    flow.append({"step": "extract", "location_tag": "extraction"})
    return flow
