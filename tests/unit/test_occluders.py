"""A package stops submitting what a wall is hiding.

WHAT THESE PIN, and what each one cost to learn. Measured on cold run 9062's
package after Zoo 1.1.0, Godot 4.7.stable, gl_compatibility, RTX 2060:

* THE SETTING HAS TO BE WRITTEN. `use_occlusion_culling` defaults to FALSE --
  read off the engine, not off a page. Emitting occluders into a package that
  does not switch the culler on is emitting 395 inert nodes, and every
  measurement below would have read zero with nothing to say why.

* THE SCENE HAS TO BE DETERMINISTIC. Godot's own `ResourceSaver` is not: two
  bakes over one unchanged package produced two different files. That is why
  the scene is written here in Python from the bake's report, and why the
  first test below runs the writer twice.

* THE SHAPES HAVE TO BE SHARED. That same packer wrote one `BoxOccluder3D`
  per occluder: 395 resources for 17 distinct sizes. Variation is never a new
  resource, and 395 near-identical sub-resources is that rule broken in the
  one file whose whole job is to be cheap.

* WIRING HAS TO BE IDEMPOTENT. The export is re-runnable. Two `Occluders`
  branches is twice the software-raster cost for exactly nothing.

* AN UNRECOGNISED REPORT MUST FAIL. A checker that cannot find the field it
  wants has learned nothing and must say so -- the export prints "no
  occluders in this package" and why, rather than shipping a package that
  reads as having had nothing to hide.

Run:  python -m pytest tests/unit/test_occluders.py
"""
import json

import pytest

from packages.core.godot_project import rendering_block
from packages.exporting.occluders import (BAKE_SCRIPT, HOLDER_NODE,
                                          OCCLUDER_SCENE, OccluderError,
                                          measure, scene_text,
                                          wire_into_scene)

_OCC_SETTING = "occlusion_culling/use_occlusion_culling=true"


def _report(sizes):
    """A bake report with one module per size, placed a metre apart."""
    return {
        "schema": "lf.occluders.v1",
        "ok": True,
        "occluders": len(sizes),
        "modules": [
            {
                "node": f"ext_{i}",
                "module": "wall_delco_1997_01_w200_mbrick",
                "size": list(s),
                "basis": [1, 0, 0, 0, 1, 0, 0, 0, 1],
                "origin": [float(i), 0.0, 0.0],
            }
            for i, s in enumerate(sizes)
        ],
    }


# --------------------------------------------------------------- the setting

def test_rendering_block_switches_occlusion_culling_on():
    """Fails on 0.95.0, which wrote no occlusion line at all.

    The engine default is false, verified on 4.7.stable. A package that ships
    occluders and leaves this out ships inert nodes.
    """
    assert _OCC_SETTING in rendering_block(0)
    assert _OCC_SETTING in rendering_block(84)


def test_the_occlusion_line_is_in_the_rendering_section():
    """It is a `rendering/` setting; under any other header it does nothing."""
    text = rendering_block(84)
    head, _, tail = text.partition(_OCC_SETTING)
    assert "[rendering]" in head
    assert "[" not in head.split("[rendering]", 1)[1]


# ------------------------------------------------------------- the scene text

def test_scene_text_is_byte_identical_across_runs():
    """Godot's packer was not, which is the whole reason this writer exists."""
    report = _report([(2.0, 3.0, 0.2), (2.0, 3.0, 0.2), (19.96, 0.21, 17.96)])
    assert scene_text(report) == scene_text(report)


def test_equal_sizes_share_one_sub_resource():
    """395 occluders over 17 sizes is 17 resources, not 395."""
    report = _report([(2.0, 3.0, 0.2)] * 40 + [(1.0, 1.0, 1.0)] * 5)
    text = scene_text(report)
    assert text.count("[sub_resource ") == 2
    assert text.count('type="OccluderInstance3D"') == 45
    assert text.count("occluder = SubResource(") == 45


def test_every_node_names_a_declared_sub_resource():
    """A node pointing at an id the file never declares is an empty occluder
    that still costs a node -- the worst of both."""
    text = scene_text(_report([(2.0, 3.0, 0.2), (4.0, 3.0, 0.2)]))
    declared = {ln.split('id="')[1].rstrip('"]')
                for ln in text.splitlines() if ln.startswith("[sub_resource ")}
    used = {ln.split('SubResource("')[1].rstrip('")')
            for ln in text.splitlines() if ln.startswith("occluder = ")}
    assert used
    assert used <= declared


def test_load_steps_counts_the_sub_resources():
    """Godot reads `load_steps` to size its load; a short one has bitten this
    repo's generated scenes before."""
    text = scene_text(_report([(2.0, 3.0, 0.2)] * 3 + [(9.0, 1.0, 1.0)]))
    head = text.splitlines()[0]
    assert "load_steps=3" in head          # two shapes plus the scene itself
    assert text.count("[sub_resource ") == 2


def test_an_empty_report_is_a_scene_with_no_occluders_not_a_crash():
    """A package with no buildings has nothing to hide, and that is legal."""
    text = scene_text(_report([]))
    assert f'[node name="{HOLDER_NODE}" type="Node3D"]' in text
    assert 'type="OccluderInstance3D"' not in text


# ------------------------------------------------------------------- wiring

_SITE = (
    "[gd_scene load_steps=2 format=3]\n"
    "\n"
    '[ext_resource type="PackedScene" path="lot/a/site.tscn" id="b1"]\n'
    "\n"
    '[node name="Site" type="Node3D"]\n'
    "\n"
    '[node name="b0" parent="." instance=ExtResource("b1")]\n'
)


def test_wiring_adds_one_ext_resource_and_one_node(tmp_path):
    site = tmp_path / "site.tscn"
    site.write_text(_SITE, encoding="utf-8")
    assert wire_into_scene(site) is True
    text = site.read_text(encoding="utf-8")
    assert text.count(f'path="res://{OCCLUDER_SCENE}"') == 1
    assert text.count(f'[node name="{HOLDER_NODE}" parent="."') == 1
    # The reference has to sit in the ext_resource block, not after a node.
    assert (text.index(f'path="res://{OCCLUDER_SCENE}"')
            < text.index('[node name="Site"'))


def test_wiring_twice_does_not_wire_twice(tmp_path):
    """The export is re-runnable; two sets of occluders is double the raster
    cost of the one that was working."""
    site = tmp_path / "site.tscn"
    site.write_text(_SITE, encoding="utf-8")
    wire_into_scene(site)
    first = site.read_text(encoding="utf-8")
    assert wire_into_scene(site) is False
    assert site.read_text(encoding="utf-8") == first


def test_wiring_refuses_a_scene_with_no_ext_resource_block(tmp_path):
    """Rather than guessing where the line goes in a scene that is not ours."""
    site = tmp_path / "site.tscn"
    site.write_text('[gd_scene format=3]\n[node name="S" type="Node3D"]\n',
                    encoding="utf-8")
    with pytest.raises(OccluderError):
        wire_into_scene(site)


# ------------------------------------------------------- the report is a gate

def test_measure_refuses_without_godot(tmp_path):
    with pytest.raises(OccluderError, match="no Godot"):
        measure(tmp_path, None)


def test_measure_refuses_an_unrecognised_schema(tmp_path, monkeypatch):
    """The shape this does not recognise FAILS. `or []` on a missing key is
    how a checker printed 'closure verdict clean' over a broken export."""
    import packages.exporting.occluders as occ

    (tmp_path / "occluders.json").write_text(
        json.dumps({"schema": "something.else.v9", "ok": True, "modules": []}),
        encoding="utf-8")
    monkeypatch.setattr(occ.subprocess, "run",
                        lambda *a, **k: None)
    with pytest.raises(OccluderError, match="schema"):
        occ.measure(tmp_path, "godot.exe")


def test_measure_refuses_a_report_that_says_it_failed(tmp_path, monkeypatch):
    import packages.exporting.occluders as occ

    (tmp_path / "occluders.json").write_text(
        json.dumps({"schema": "lf.occluders.v1", "ok": False,
                    "error": "cannot load res://site.tscn"}),
        encoding="utf-8")
    monkeypatch.setattr(occ.subprocess, "run", lambda *a, **k: None)
    with pytest.raises(OccluderError, match="cannot load"):
        occ.measure(tmp_path, "godot.exe")


def test_measure_refuses_when_the_bake_wrote_nothing(tmp_path, monkeypatch):
    """Silence is not success. An export that shipped no occluders because
    Godot never ran must say that, not report a package with nothing to hide."""
    import packages.exporting.occluders as occ

    monkeypatch.setattr(occ.subprocess, "run", lambda *a, **k: None)
    with pytest.raises(OccluderError, match="no report"):
        occ.measure(tmp_path, "godot.exe")


# ------------------------------------------------------------ the bake script

def test_the_bake_script_ships_and_keeps_glass_open():
    """The classification lives in the GDScript because Godot measures. The
    one rule that is a correctness question rather than a performance one --
    a storefront you can see the street through is not an occluder -- is
    pinned here so it cannot be dropped as an optimisation."""
    assert BAKE_SCRIPT.is_file()
    text = BAKE_SCRIPT.read_text(encoding="utf-8")
    assert 'GLASS_TOKEN := "mglass"' in text
    assert '"window_", "doorway_", "breach_"' in text
    for prefix in ("wall_", "roof_", "floor_", "ceiling_"):
        assert f'"{prefix}"' in text
    # Props are never occluders: nothing thin or porous makes the solid list.
    solid_line = next(ln for ln in text.splitlines()
                      if ln.startswith("const SOLID_PREFIXES"))
    assert "prop_" not in solid_line
