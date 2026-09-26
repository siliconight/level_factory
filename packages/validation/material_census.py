"""Count the materials a package ships, and find the ones that differ only in
a colour.

WHY THIS EXISTS. Draw calls are this repo's budget, and the first rule under
that heading is "never express colour-only variation as a new material" --
Zoo's `pennant_row` shipped 89 meshes and 13 materials that differed in nothing
but `baseColorFactor`. Nothing counted materials afterwards, so the rule has
been a paragraph rather than a check, and a package can break it silently. Cold
run 9080's package was read by hand on 2026-09-26 and ships 908 material
entries across 242 distinct names in 295 `.glb` files.

WHAT IT DOES NOT DO. It does not price anything. A material count is NOT a
frame cost -- measured on that same package five hours before this file was
written, 13.16x the material resources cost 4.65x the milliseconds -- so this
reports what a package contains and names the families involved, and a person
decides whether to spend a measurement on them. The finding it raises says
"these differ only in a colour", which is a fact about the file, not "this is
slow", which would be a guess.

READ THE MATERIALS, NOT THE NAMES. The obvious version of this check clusters
material names and reports the ones sharing a stem. That version is wrong in
both directions, and the second way is the expensive one:

  * `M_Skin_metal_painted_delco_1997_<hex>` looks like a tint family from its
    name, and IS one -- but only after resolving what it points at. Its three
    materials in `prop_fire_hydrant_...glb` carry three DIFFERENT texture
    indices (0/1, 4/5, 6/7) out of 8 texture entries, which reads as three
    materials with three textures until the indices are followed: all three
    resolve to the same two images, `metal_painted_neutral_albedo` and
    `..._roughness`, at the same atlas rect. One neutral texture, tinted per
    material. Comparing the raw glTF dicts would have found no cluster at all
    and reported the package clean.
  * a name-only cluster would equally group two materials that share a stem and
    genuinely differ in roughness, texture or transform, and send somebody to
    merge two things that are not the same material.

So the key is the whole material definition with the TINT FIELDS removed and
every texture reference resolved to what it actually points at.

Pure: paths in, facts out. Stdlib only, no Godot, no Blender. The glTF JSON
chunk reader is `glb_collision.json_chunk` rather than a second copy of the
same 20 lines.
"""
from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from packages.validation.glb_collision import json_chunk

#: The fields a tint variant is allowed to differ in. Everything else is
#: structure and makes two materials genuinely different.
#:
#: `alphaCutoff` is deliberately NOT here: two materials with different cutoffs
#: shade differently at the same colour. `emissiveFactor` is, because a sign
#: lit in two colours off one emissive texture is the same defect as a hydrant
#: painted in two colours off one albedo.
TINT_FIELDS = ("baseColorFactor", "emissiveFactor", "emissiveStrength")


@dataclass(frozen=True)
class TintFamily:
    """Materials whose definitions differ only in a tint field."""

    members: tuple[str, ...]
    files: tuple[str, ...]
    colours: tuple[str, ...]

    @property
    def size(self) -> int:
        return len(self.members)


@dataclass
class Census:
    """What a package's `.glb` files carry, and what could not be read.

    `unreadable` is kept apart from a zero count for the reason the collision
    reader keeps its own: a file that parsed and holds no material is "this
    package brings nothing here", a file that would not parse is "unknown",
    and collapsing the two reports a silence as a fact.
    """

    files_read: int = 0
    unreadable: list[str] = field(default_factory=list)
    entries: int = 0
    names: Counter = field(default_factory=Counter)
    tint_families: list[TintFamily] = field(default_factory=list)

    @property
    def distinct(self) -> int:
        return len(self.names)

    @property
    def tinted_materials(self) -> int:
        return sum(f.size for f in self.tint_families)

    def to_dict(self) -> dict:
        return {
            "schema": "lf.material_census.v1",
            "files_read": self.files_read,
            "unreadable": list(self.unreadable),
            "entries": self.entries,
            "distinct_names": self.distinct,
            "tint_families": [
                {"size": f.size, "members": list(f.members),
                 "files": list(f.files), "colours": list(f.colours)}
                for f in self.tint_families],
        }


def _texture_identity(doc: dict, ref) -> object:
    """What a texture reference POINTS AT, not which slot holds it.

    A glTF texture index is file-local and a writer may emit one entry per
    material even when every entry resolves to the same image. Comparing
    indices therefore answers a question nobody asked.
    """
    if not isinstance(ref, dict):
        return ref
    out = {k: v for k, v in ref.items() if k not in ("index", "extensions")}
    idx = ref.get("index")
    tex = (doc.get("textures") or [])
    if isinstance(idx, int) and 0 <= idx < len(tex):
        entry = tex[idx] or {}
        src = entry.get("source")
        img = (doc.get("images") or [])
        if isinstance(src, int) and 0 <= src < len(img):
            im = img[src] or {}
            # A URI names the file; a bufferView-backed image is identified by
            # the view it occupies, which is stable within the document.
            out["image"] = im.get("uri", ("bufferView", im.get("bufferView")))
        else:
            out["image"] = ("unresolved", src)
        out["sampler"] = entry.get("sampler")
    else:
        out["image"] = ("unresolved", idx)
    # The atlas rect is structure: same image at a different rect is a
    # different surface, not a different colour.
    kt = (ref.get("extensions") or {}).get("KHR_texture_transform")
    if kt is not None:
        out["transform"] = kt
    return out


def _canonical(doc: dict, mat: dict) -> str:
    """The material with its name and tint removed, textures resolved."""

    def walk(node):
        if isinstance(node, dict):
            if "index" in node and ("texCoord" in node or "extensions" in node
                                    or len(node) == 1):
                return _texture_identity(doc, node)
            return {k: walk(v) for k, v in sorted(node.items())
                    if k not in TINT_FIELDS and k != "name"}
        if isinstance(node, list):
            return [walk(v) for v in node]
        return node

    return json.dumps(walk(mat), sort_keys=True, default=str)


def _colour(mat: dict) -> str:
    pbr = mat.get("pbrMetallicRoughness") or {}
    rgba = pbr.get("baseColorFactor")
    if not isinstance(rgba, list) or len(rgba) < 3:
        return "-"
    return "#" + "".join("%02x" % max(0, min(255, round(float(c) * 255)))
                         for c in rgba[:3])


def census(paths) -> Census:
    """Read every `.glb` in ``paths`` and report what it carries."""
    out = Census()
    groups: dict[str, list[tuple[str, dict]]] = {}
    for p in paths:
        path = Path(p)
        if path.suffix.lower() != ".glb":
            continue
        try:
            doc = json_chunk(path.read_bytes())
        except OSError:
            doc = None
        if doc is None:
            out.unreadable.append(path.name)
            continue
        out.files_read += 1
        for mat in (doc.get("materials") or []):
            if not isinstance(mat, dict):
                continue
            name = str(mat.get("name", ""))
            out.entries += 1
            out.names[name] += 1
            groups.setdefault(_canonical(doc, mat), []).append(
                (name, {"file": path.name, "colour": _colour(mat)}))

    for members in groups.values():
        # A family needs two DIFFERENT names. The same material repeated across
        # files is duplication, which `entries` against `distinct_names`
        # already reports; it is not colour variation and must not be counted
        # as it -- the brick skin appears 19 times under one name and merging
        # it with itself would buy nothing.
        names = sorted({n for n, _ in members})
        if len(names) < 2:
            continue
        colours = sorted({m["colour"] for _, m in members})
        if len(colours) < 2:
            continue
        out.tint_families.append(TintFamily(
            members=tuple(names),
            files=tuple(sorted({m["file"] for _, m in members})),
            colours=tuple(colours)))
    out.tint_families.sort(key=lambda f: (-f.size, f.members[0]))
    return out


#: The one finding this raises. Non-blocking and it stays that way until
#: somebody measures what a tint family costs in draw calls on this renderer:
#: a count is not a price, and a gate built on one would be a threshold chosen
#: rather than derived.
CODE = "PRESENTATION_TINT_MATERIALS"


def issues(paths, *, source: str = "") -> list[dict]:
    """Normalized findings for a composed package's `.glb` files."""
    c = census(paths)
    if not c.files_read and not c.unreadable:
        return []
    out: list[dict] = []
    if c.tint_families:
        worst = "; ".join(
            "%s x%d (%s)" % (f.members[0], f.size, ", ".join(f.colours[:4]))
            for f in c.tint_families[:3])
        out.append({
            "code": CODE,
            "severity": "moderate", "category": "performance",
            "message": (
                f"{c.tinted_materials} material(s) in {len(c.tint_families)} "
                f"family/families differ only in a colour factor -- same "
                f"textures, same transform, same everything else. The package "
                f"ships {c.entries} material entries under {c.distinct} "
                f"distinct names across {c.files_read} .glb file(s). "
                f"Worst: {worst}"),
            "suggested_fix": (
                "carry the colour as instance data, a vertex colour channel "
                "or an atlas UV rather than as a material. Measure the draw "
                "calls before and after -- a material count is not a frame "
                "cost."),
            "blocking": False, "raw_source_path": source})
    if c.unreadable:
        out.append({
            "code": "PRESENTATION_MATERIALS_UNREADABLE",
            "severity": "minor", "category": "provenance",
            "message": (
                f"{len(c.unreadable)} .glb file(s) could not be read, so this "
                f"package's material count is a floor and not a total: "
                f"{', '.join(sorted(c.unreadable)[:5])}"),
            "blocking": False, "raw_source_path": source})
    return out


def _main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(
        prog="material_census",
        description="count a package's materials and name the tint families")
    ap.add_argument("root", type=Path, help="a directory holding .glb files")
    ap.add_argument("--json", type=Path, default=None)
    args = ap.parse_args(argv)

    c = census(sorted(Path(args.root).rglob("*.glb")))
    print(f"  files read      {c.files_read}"
          + (f"  ({len(c.unreadable)} unreadable)" if c.unreadable else ""))
    print(f"  material entries{c.entries:6d}")
    print(f"  distinct names  {c.distinct:6d}"
          + (f"   ({c.entries / c.distinct:.2f} entries per name)"
             if c.distinct else ""))
    print(f"  tint families   {len(c.tint_families):6d}"
          f"   ({c.tinted_materials} materials)")
    for f in c.tint_families[:12]:
        print("    %-52s x%-3d %s" % (f.members[0][:52], f.size,
                                      ", ".join(f.colours[:6])))
    if args.json:
        args.json.write_text(json.dumps(c.to_dict(), indent=1),
                             encoding="utf-8")
        print(f"  wrote {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
