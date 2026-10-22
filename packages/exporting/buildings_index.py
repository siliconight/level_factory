"""The buildings a level stands, and their drawings: `buildings.json` at a package's root (the factory's roadmap 296).

The walker, of Deli Counter's exploded axonometric: seen in "both" a review page and a level's export -- "It could
even get into the game where the players can 'scope out' the level and see the buildings the level assembles". Since
Deli Counter 0.257.0 each composed building carries its drawings in its package's `drawings/`, with `drawings.json`
naming them; which buildings a level stands, and where, was written only into its assembly scene, `site.tscn`, as
instances. This reads that scene and those records and writes one index a game or a reviewer reads without parsing a
scene: each standing instance -- a building `b<n>` or an Empty `blocker_<n>` -- with its package id, the spec it was
drawn from, its drawings as `res://` paths (or why it has none), and where it stands: the instance's origin in
`site.tscn`, Godot metres, Y up. The game builds the screen; this is what it reads.

THE SCOUT VIEW (0.233.0). The walker judged the axonometric too busy to scout from -- "simpler but carry all of the
signals needed" -- and Deli Counter 0.258.0 draws each building a second way, with only what a body finds its way
by, as `drawings/scout.svg`. Each entry names it under `scout`; a package composed before 0.258.0 has none, and the
entry says null there rather than guessing a path.

THE PATHS ARE res:// ON PURPOSE. The export's closure scan resolves every `res://` a package's JSON names
(`closure.scan_closure`), so an index naming a drawing the package does not carry fails the package's own verdict.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

INDEX_NAME = "buildings.json"
_EXT = re.compile(r'^\[ext_resource type="PackedScene" path="(lot/([^"/]+)/site\.tscn)" id="([^"]+)"\]', re.M)
_NODE = re.compile(r'^\[node name="([^"]+)" parent="\." instance=ExtResource\("([^"]+)"\)\]', re.M)
_XFORM = re.compile(r'^transform = Transform3D\(([^)]*)\)', re.M)
NO_DRAWINGS = "its package carries no drawings (composed by a Deli Counter before 0.257.0, or named no spec)"


def build(package_dir) -> dict | None:
    """The index for one package, or None where it has no assembly scene (`site.tscn`) to read."""
    root = Path(package_dir)
    scene = root / "site.tscn"
    if not scene.is_file():
        return None
    text = scene.read_text(encoding="utf-8", errors="replace")
    ext = {m.group(3): m.group(2) for m in _EXT.finditer(text)}
    out = []
    for m in _NODE.finditer(text):
        name, rid = m.group(1), m.group(2)
        if rid not in ext:
            continue
        lot_id = ext[rid]
        # a node's properties run to the next section's header
        nxt = text.find("\n[", m.end())
        body = text[m.end():nxt if nxt != -1 else len(text)]
        x = _XFORM.search(body)
        nums = [float(v) for v in x.group(1).split(",")] if x else []
        entry = {"node": name, "id": lot_id, "kind": "empty" if name.startswith("blocker_") else "building",
                 # the Transform3D's last three numbers are its origin, however its basis is written
                 "at": [round(v, 3) for v in nums[9:12]] if len(nums) == 12 else None,
                 "spec": None, "axonometric": None, "scout": None, "plans": []}
        rec_path = root / "lot" / lot_id / "drawings" / "drawings.json"
        if rec_path.is_file():
            rec = json.loads(rec_path.read_text(encoding="utf-8"))
            base = "res://lot/%s/drawings/" % lot_id
            entry["spec"] = rec.get("spec")
            if rec.get("axonometric"):
                entry["axonometric"] = base + rec["axonometric"]
            if rec.get("scout"):
                entry["scout"] = base + rec["scout"]
            entry["plans"] = [{"storey": p["storey"], "file": base + p["file"]} for p in rec.get("plans") or []]
            if rec.get("none_because"):
                entry["none_because"] = rec["none_because"]
        else:
            entry["none_because"] = NO_DRAWINGS
        out.append(entry)
    return {"schema": "level_factory.buildings.v1", "scene": "res://site.tscn",
            "frame": "at: the instance's origin in site.tscn, Godot metres, Y up", "buildings": out}


def write(package_dir) -> dict | None:
    """Write `buildings.json` into the package; returns the index, or None (and writes nothing) where `build` has
    no scene to read."""
    index = build(package_dir)
    if index is None:
        return None
    (Path(package_dir) / INDEX_NAME).write_text(json.dumps(index, indent=2) + "\n", encoding="utf-8", newline="\n")
    return index


def summary(index: dict) -> str:
    """One line for the export's log: how many instances, how many drawn, how many say why not."""
    b = index["buildings"]
    drawn = sum(1 for e in b if e["axonometric"])
    return "%d instance(s) of %d package(s); %d drawn, %d with a reason for none" % (
        len(b), len({e["id"] for e in b}), drawn, sum(1 for e in b if e.get("none_because")))
