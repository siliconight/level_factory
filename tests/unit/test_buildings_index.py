"""A level's package names the buildings it stands, where, and their drawings (0.232.0, the factory's roadmap 296).

`buildings_index` reads the shipped assembly scene and each building package's own `drawings/drawings.json` (Deli
Counter 0.257.0) and writes `buildings.json` at the package's root. A synthetic package: two buildings and an Empty in
`site.tscn`, the scene's shape read off cold run 9376's package (`[ext_resource ... path="lot/<id>/site.tscn"]`,
`[node name="b0" parent="." instance=ExtResource("b1")]`, `transform = Transform3D(...)`).
"""
from __future__ import annotations

import json
from pathlib import Path

from packages.exporting import buildings_index as BI
from packages.exporting.closure import scan_closure

SCENE = """[gd_scene load_steps=4 format=3]

[ext_resource type="PackedScene" path="lot/deli_a03/site.tscn" id="b1"]
[ext_resource type="PackedScene" path="lot/office/site.tscn" id="b2"]
[ext_resource type="PackedScene" path="lot/gs_empty_rowhome_a/site.tscn" id="b3"]

[node name="site" type="Node3D"]

[node name="b0" parent="." instance=ExtResource("b1")]
transform = Transform3D(1, 0, 0, 0, 1, 0, -0, 0, 1, -51, 0, -2.51)

[node name="b1" parent="." instance=ExtResource("b2")]
transform = Transform3D(1, 0, 0, 0, 1, 0, 0, 0, 1, 12.5, 0, 4)

[node name="blocker_0" parent="." instance=ExtResource("b3")]
transform = Transform3D(-1, 0, 1.22465e-16, 0, 1, 0, -1.22465e-16, 0, -1, -83.2, 0, 37.815)
"""


def _package(tmp_path: Path, *, office_drawn=True) -> Path:
    root = tmp_path / "pkg"
    root.mkdir()
    (root / "site.tscn").write_text(SCENE, encoding="utf-8")
    for lot_id in ("deli_a03", "office", "gs_empty_rowhome_a"):
        (root / "lot" / lot_id).mkdir(parents=True)
        (root / "lot" / lot_id / "site.tscn").write_text('[gd_scene format=3]\n\n[node name="site" type="Node3D"]\n',
                                                          encoding="utf-8")
    d = root / "lot" / "deli_a03" / "drawings"
    d.mkdir()
    for f in ("axonometric.svg", "floorB1.svg", "floor0.svg"):
        (d / f).write_text("<svg/>", encoding="utf-8")
    (d / "drawings.json").write_text(json.dumps({
        "schema": "deli_counter.drawings.v1", "spec": "deli_a03", "axonometric": "axonometric.svg",
        "plans": [{"storey": -1, "file": "floorB1.svg"}, {"storey": 0, "file": "floor0.svg"}]}), encoding="utf-8")
    if office_drawn:
        d = root / "lot" / "office" / "drawings"
        d.mkdir()
        (d / "axonometric.svg").write_text("<svg/>", encoding="utf-8")
        (d / "drawings.json").write_text(json.dumps({
            "schema": "deli_counter.drawings.v1", "spec": "office", "axonometric": "axonometric.svg",
            "plans": []}), encoding="utf-8")
    d = root / "lot" / "gs_empty_rowhome_a" / "drawings"
    d.mkdir()
    (d / "drawings.json").write_text(json.dumps({
        "schema": "deli_counter.drawings.v1", "spec": "gs_empty_rowhome_a", "axonometric": None, "plans": [],
        "none_because": "a facade: a street wall with no interior"}), encoding="utf-8")
    return root


def test_every_standing_instance_is_named_with_where_it_stands_and_its_drawings(tmp_path):
    root = _package(tmp_path)
    index = BI.write(root)
    assert json.loads((root / BI.INDEX_NAME).read_text(encoding="utf-8")) == index
    by_node = {e["node"]: e for e in index["buildings"]}
    assert list(by_node) == ["b0", "b1", "blocker_0"]
    deli = by_node["b0"]
    assert (deli["id"], deli["kind"], deli["spec"], deli["at"]) == ("deli_a03", "building", "deli_a03",
                                                                    [-51.0, 0.0, -2.51])
    assert deli["axonometric"] == "res://lot/deli_a03/drawings/axonometric.svg"
    assert deli["plans"] == [{"storey": -1, "file": "res://lot/deli_a03/drawings/floorB1.svg"},
                             {"storey": 0, "file": "res://lot/deli_a03/drawings/floor0.svg"}]
    empty = by_node["blocker_0"]
    assert (empty["kind"], empty["at"], empty["axonometric"]) == ("empty", [-83.2, 0.0, 37.815], None)
    assert "facade" in empty["none_because"]


def test_a_package_without_drawings_says_so(tmp_path):
    root = _package(tmp_path, office_drawn=False)
    office = {e["node"]: e for e in BI.write(root)["buildings"]}["b1"]
    assert office["axonometric"] is None and office["none_because"] == BI.NO_DRAWINGS


def test_a_package_with_no_assembly_scene_gets_no_index(tmp_path):
    root = tmp_path / "pkg"
    root.mkdir()
    assert BI.write(root) is None and not (root / BI.INDEX_NAME).exists()


def test_the_closure_verdict_proves_every_drawing_the_index_names(tmp_path):
    """The index names its drawings res://, which the closure scan resolves: with every drawing present it raises
    nothing about the index; take one away and the verdict names the index's reference to it."""
    root = _package(tmp_path)
    BI.write(root)
    assert not [i for i in scan_closure(root).issues if i.startswith(BI.INDEX_NAME)]
    (root / "lot" / "deli_a03" / "drawings" / "floor0.svg").unlink()
    issues = [i for i in scan_closure(root).issues if i.startswith(BI.INDEX_NAME)]
    assert issues == ["%s: unresolved res://lot/deli_a03/drawings/floor0.svg" % BI.INDEX_NAME], issues
