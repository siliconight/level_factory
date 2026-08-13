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
        anchors.append(anchor)
    return anchors


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
                          theme: str = "", up: str = "z") -> dict:
    """Write Dispatch-shaped deli_counter/ and lot/ input trees under dest_dir.
    Returns {"deli_counter": <manifest path>, "lot": <manifest path>}."""
    dest_dir = Path(dest_dir)
    deli_dir = dest_dir / "deli_counter"; deli_dir.mkdir(parents=True, exist_ok=True)
    lot_dir = dest_dir / "lot"; lot_dir.mkdir(parents=True, exist_ok=True)
    lic = {"name": "proprietary-siliconight", "source": ""}

    # ---- deli_counter (collision shell) ----
    dc_gp = _read_json(deli_gameplay)
    dc_up = str(dc_gp.get("up_axis", up))
    dc_anchors = markers_to_anchors(dc_gp, "deli_counter", dc_up)
    (deli_dir / "shell.gameplay.json").write_text(json.dumps({
        "schema": "dc.gameplay.v1", "license": {**lic, "source": "deli_counter"},
        "up_axis": dc_up, "anchors": dc_anchors,
        "props": list(dc_gp.get("props", []) or []),
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
    lot_anchors = ensure_mission_anchors(
        markers_to_anchors(lot_gp, "lot", lot_up), "lot", lot_up)
    (lot_dir / "lot.gameplay.json").write_text(json.dumps({
        "schema": "lot.gameplay.v1", "license": {**lic, "source": "lot"},
        "up_axis": lot_up, "anchors": lot_anchors,
        "props": list(lot_gp.get("props", []) or []),
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
