"""The light bake counts, and gives a second UV set to, only what it bakes (0.212.0, the factory's roadmap 251).

`add_primitive_uv2` wrote `add_uv2 = true` on every inline primitive in every scene of the package, and the
export's log summed those counts as "primitive mesh(es) lightmapped". Measured on cold run 9308's
`light_bake.json`: `site.tscn` 112, `presentation/lux.applied.tscn` 112, `site_backdrop.tscn` 1 -- the log's 225.
`bake.tscn` instances the presentation alone, so the content scene's 112 were the same primitives counted again,
and the backdrop's ground, which `mission.tscn` loads at run time outside the bake, is never lightmapped.
"""
from __future__ import annotations

from pathlib import Path

from packages.exporting import light_bake as LB

_PRES = ('[gd_scene load_steps=4 format=3]\n\n'
         '[ext_resource type="PackedScene" uid="uid://abc" path="res://lot/a/site.tscn" id="1_a"]\n\n'
         '[sub_resource type="BoxMesh" id="g1"]\n\n[sub_resource type="BoxMesh" id="g2"]\n\n'
         '[node name="Site" type="Node3D"]\n\n[node name="a" parent="." instance=ExtResource("1_a")]\n')
_LOT = '[gd_scene format=3]\n\n[sub_resource type="QuadMesh" id="q"]\n\n[node name="a" type="Node3D"]\n'
_SITE = '[gd_scene format=3]\n\n[sub_resource type="BoxMesh" id="g1"]\n\n[sub_resource type="BoxMesh" id="g2"]\n'
_BACKDROP = '[gd_scene format=3]\n\n[sub_resource type="PlaneMesh" id="BackdropGround_mesh"]\n'


def _package(root: Path) -> Path:
    for rel, text in ((LB.PRESENTATION, _PRES), ("lot/a/site.tscn", _LOT), ("site.tscn", _SITE),
                      ("site_backdrop.tscn", _BACKDROP)):
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    return root


def test_the_bake_draws_the_presentation_and_what_it_instances(tmp_path):
    pkg = _package(tmp_path)
    assert LB.baked_scenes(pkg) == ["lot/a/site.tscn", LB.PRESENTATION]


def test_only_the_baked_scenes_get_a_second_uv_set_and_are_counted(tmp_path):
    pkg = _package(tmp_path)
    got = LB.add_primitive_uv2(pkg, only=LB.baked_scenes(pkg))
    assert got == {LB.PRESENTATION: 2, "lot/a/site.tscn": 1}
    assert sum(got.values()) == 3
    assert "add_uv2" not in (pkg / "site.tscn").read_text(encoding="utf-8")
    assert "add_uv2" not in (pkg / "site_backdrop.tscn").read_text(encoding="utf-8")


def test_no_presentation_bakes_nothing(tmp_path):
    (tmp_path / "site.tscn").write_text(_SITE, encoding="utf-8")
    assert LB.baked_scenes(tmp_path) == []
    assert LB.add_primitive_uv2(tmp_path, only=LB.baked_scenes(tmp_path)) == {}
    assert "add_uv2" not in (tmp_path / "site.tscn").read_text(encoding="utf-8")


def test_the_export_counts_through_the_baked_scenes():
    # the call site, read off the source: the bake hands add_primitive_uv2 the scenes it draws
    src = Path(LB.__file__).read_text(encoding="utf-8")
    assert "add_primitive_uv2(export_dir, only=baked_scenes(export_dir))" in src
