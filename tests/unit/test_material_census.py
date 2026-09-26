"""The census reads what a material POINTS AT, not what slot holds it.

Every test here is a way the obvious version of this check goes wrong. The
first one is the expensive one: on a real package the writer emits a separate
texture entry per material even when every entry resolves to the same image, so
comparing the glTF dicts as written finds no colour variation anywhere and
reports a package clean that is 76% colour variation.
"""
from __future__ import annotations

import json
import struct

from packages.validation import material_census as mc

_TEX = {"index": 0, "texCoord": 0}


def _glb(doc: dict) -> bytes:
    """A minimal binary glTF carrying ``doc`` as its JSON chunk."""
    payload = json.dumps(doc).encode("utf-8")
    payload += b" " * (-len(payload) % 4)
    header = struct.pack("<III", 0x46546C67, 2, 12 + 8 + len(payload))
    return header + struct.pack("<II", len(payload), 0x4E4F534A) + payload


def _write(tmp_path, name: str, doc: dict):
    p = tmp_path / name
    p.write_bytes(_glb(doc))
    return p


def _tinted(name: str, rgb, tex_index: int) -> dict:
    return {"name": name,
            "pbrMetallicRoughness": {
                "baseColorFactor": list(rgb) + [1],
                "baseColorTexture": {"index": tex_index, "texCoord": 0},
                "metallicFactor": 0}}


def _doc_with_duplicate_texture_entries() -> dict:
    """Three materials, three texture entries, ONE image -- the real shape.

    Measured on `prop_fire_hydrant_delco_1997_01...glb`: 4 materials, 8
    texture entries, 4 distinct image payloads.
    """
    return {
        "asset": {"version": "2.0"},
        "images": [{"uri": "_tex/plastic_neutral_albedo_50ed9ac2.png"}],
        "textures": [{"source": 0}, {"source": 0}, {"source": 0}],
        "materials": [_tinted("M_plastic_731a14", [0.45, 0.10, 0.08], 0),
                      _tinted("M_plastic_d1ccc2", [0.82, 0.80, 0.76], 1),
                      _tinted("M_plastic_cc241f", [0.80, 0.14, 0.12], 2)],
    }


def test_a_tint_family_is_found_through_duplicate_texture_entries(tmp_path):
    _write(tmp_path, "props.glb", _doc_with_duplicate_texture_entries())
    c = mc.census(sorted(tmp_path.rglob("*.glb")))

    assert c.files_read == 1
    assert c.entries == 3 and c.distinct == 3
    assert len(c.tint_families) == 1
    fam = c.tint_families[0]
    assert fam.size == 3
    assert fam.colours == ("#731a14", "#cc241f", "#d1ccc2")


def test_a_real_difference_is_not_a_tint_family(tmp_path):
    """Same stem, same image, different roughness: two materials, not one."""
    doc = _doc_with_duplicate_texture_entries()
    doc["materials"] = doc["materials"][:2]
    doc["materials"][1]["pbrMetallicRoughness"]["roughnessFactor"] = 0.2
    _write(tmp_path, "props.glb", doc)

    assert mc.census(sorted(tmp_path.rglob("*.glb"))).tint_families == []


def test_the_same_image_at_a_different_rect_is_a_different_surface(tmp_path):
    """An atlas rect is structure. Two materials reading different cells of
    one sheet are not one material wearing two colours."""
    doc = _doc_with_duplicate_texture_entries()
    doc["materials"] = doc["materials"][:2]
    doc["materials"][1]["pbrMetallicRoughness"]["baseColorTexture"][
        "extensions"] = {"KHR_texture_transform": {"offset": [0, 0.5]}}
    _write(tmp_path, "props.glb", doc)

    assert mc.census(sorted(tmp_path.rglob("*.glb"))).tint_families == []


def test_one_material_repeated_across_files_is_duplication_not_variation(tmp_path):
    """The brick skin appears 19 times under one name on a real package.

    Merging it with itself buys nothing, so it must not be reported as colour
    variation -- `entries` against `distinct_names` already says it is
    duplicated.
    """
    doc = {"asset": {"version": "2.0"},
           "images": [{"uri": "brick.png"}],
           "textures": [{"source": 0}],
           "materials": [_tinted("M_Skin_brick", [0.5, 0.5, 0.5], 0)]}
    for i in range(19):
        _write(tmp_path, "b%02d.glb" % i, doc)

    c = mc.census(sorted(tmp_path.rglob("*.glb")))
    assert c.entries == 19 and c.distinct == 1
    assert c.tint_families == []


def test_two_names_at_one_colour_are_not_a_tint_family(tmp_path):
    """Identical definitions under two names are redundancy, and saying
    "these differ only in a colour" about them would be false."""
    doc = _doc_with_duplicate_texture_entries()
    doc["materials"] = doc["materials"][:2]
    doc["materials"][1]["pbrMetallicRoughness"]["baseColorFactor"] = (
        doc["materials"][0]["pbrMetallicRoughness"]["baseColorFactor"])
    _write(tmp_path, "props.glb", doc)

    assert mc.census(sorted(tmp_path.rglob("*.glb"))).tint_families == []


def test_an_unreadable_file_is_unknown_and_not_zero(tmp_path):
    _write(tmp_path, "good.glb", _doc_with_duplicate_texture_entries())
    (tmp_path / "bad.glb").write_bytes(b"not a glb at all")

    c = mc.census(sorted(tmp_path.rglob("*.glb")))
    assert c.files_read == 1
    assert c.unreadable == ["bad.glb"]

    codes = [i["code"] for i in mc.issues(sorted(tmp_path.rglob("*.glb")))]
    assert "PRESENTATION_MATERIALS_UNREADABLE" in codes


def test_the_finding_reports_and_does_not_block(tmp_path):
    """A count is not a frame cost, so this cannot be a gate yet."""
    _write(tmp_path, "props.glb", _doc_with_duplicate_texture_entries())
    found = [i for i in mc.issues(sorted(tmp_path.rglob("*.glb")))
             if i["code"] == mc.CODE]

    assert len(found) == 1
    assert found[0]["blocking"] is False
    assert found[0]["category"] == "performance"
    assert "3 material(s) in 1 family" in found[0]["message"]


def test_a_clean_package_raises_nothing(tmp_path):
    doc = {"asset": {"version": "2.0"},
           "images": [{"uri": "brick.png"}],
           "textures": [{"source": 0}],
           "materials": [_tinted("M_brick", [0.5, 0.5, 0.5], 0),
                         _tinted("M_tile", [0.5, 0.5, 0.5], 0)]}
    doc["materials"][1]["pbrMetallicRoughness"]["roughnessFactor"] = 0.3
    _write(tmp_path, "one.glb", doc)

    assert mc.issues(sorted(tmp_path.rglob("*.glb"))) == []
