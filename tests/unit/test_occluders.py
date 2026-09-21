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

0.98.0 ADDED THE FOUR BELOW, because every one of the above was true and the
bake still never ran in a real export. Cold run 9065 shipped
`use_occlusion_culling=true` with zero occluder nodes: the export deleted the
import cache one line before the bake that needed it, printed a warning, and
exited 0.

* THE BAKE NEEDS AN IMPORTED PROJECT. Sidecars are the import SETTINGS; the
  imported resources live in `.godot`. Reproduced on the shipped package:
  cache absent, `cannot load res://site.tscn`; cache present, 414 occluders.

* THE FLAG IS A FUNCTION OF THE COUNT. `rendering_block` takes an occluder
  count with no default, so 9065's state has no spelling.

* THE PACKAGE IS AUDITED, NOT THE INTENT. `audit` counts nodes in the scenes
  that ship and never reads `occluders.json` to decide, because the gap
  between the report and the package is where the defect lived.

* A FAILED BAKE WITH A GODOT PRESENT FAILS THE BUILD. A warning nobody reads
  is how this shipped.

Run:  python -m pytest tests/unit/test_occluders.py
"""
import json
from pathlib import Path

import pytest

from packages.core.godot_project import (OCCLUSION_KEY, rendering_block,
                                         set_occlusion_culling)
from packages.exporting.occluders import (BAKE_SCRIPT, CACHE_DIR, HOLDER_NODE,
                                          OCCLUDER_SCENE,
                                          OccluderDisagreement, OccluderError,
                                          audit, drop_cache, ensure_imported,
                                          measure, scene_text,
                                          wire_into_scene)

_OCC_SETTING = "occlusion_culling/use_occlusion_culling=true"
_OCC_OFF = "occlusion_culling/use_occlusion_culling=false"


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
    assert _OCC_SETTING in rendering_block(0, 414)
    assert _OCC_SETTING in rendering_block(84, 414)


def test_rendering_block_refuses_to_claim_culling_with_no_occluders():
    """FAILS ON 0.97.0, which wrote `=true` unconditionally and took no
    occluder count at all.

    This is cold run 9065's state written at its source. The culler costs
    about 0.27 ms of CPU a frame at 1280x720 with nothing to cull; switching
    it on for a package with zero occluders buys that cost and nothing else.
    """
    assert _OCC_OFF in rendering_block(0, 0)
    assert _OCC_OFF in rendering_block(84, 0)
    assert _OCC_SETTING not in rendering_block(84, 0)


def test_the_occlusion_line_is_in_the_rendering_section():
    """It is a `rendering/` setting; under any other header it does nothing."""
    text = rendering_block(84, 414)
    head, _, tail = text.partition(_OCC_SETTING)
    assert "[rendering]" in head
    assert "[" not in head.split("[rendering]", 1)[1]


def test_settling_the_flag_rewrites_the_one_line_in_place(tmp_path):
    """The export writes project.godot before it knows the count, so the line
    is settled afterwards. Appending a second one would leave the engine
    reading whichever came last."""
    text = "[application]\nx=1\n\n" + rendering_block(84, 0) + "[debug]\ny=2\n"
    on = set_occlusion_culling(text, 414)
    assert on.count(OCCLUSION_KEY) == 1
    assert _OCC_SETTING in on
    assert on.index(_OCC_SETTING) < on.index("[debug]")
    assert _OCC_OFF in set_occlusion_culling(on, 0)


def test_settling_refuses_a_file_with_no_line_to_settle():
    """A writer that cannot find what it is editing has learned nothing.
    Appending would land the key after whatever section header came last."""
    with pytest.raises(ValueError, match="0 "):
        set_occlusion_culling("[application]\nconfig_version=5\n", 414)


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

def _already_imported(tmp_path):
    """These pin the REPORT's shape, so put the bake's precondition in place
    and let them get as far as reading one."""
    (tmp_path / CACHE_DIR).mkdir(exist_ok=True)


def test_measure_refuses_without_godot(tmp_path):
    with pytest.raises(OccluderError, match="no Godot"):
        measure(tmp_path, None)


def test_measure_refuses_an_unrecognised_schema(tmp_path, monkeypatch):
    """The shape this does not recognise FAILS. `or []` on a missing key is
    how a checker printed 'closure verdict clean' over a broken export."""
    import packages.exporting.occluders as occ

    _already_imported(tmp_path)
    (tmp_path / "occluders.json").write_text(
        json.dumps({"schema": "something.else.v9", "ok": True, "modules": []}),
        encoding="utf-8")
    monkeypatch.setattr(occ.subprocess, "run",
                        lambda *a, **k: None)
    with pytest.raises(OccluderError, match="schema"):
        occ.measure(tmp_path, "godot.exe")


def test_measure_refuses_a_report_that_says_it_failed(tmp_path, monkeypatch):
    import packages.exporting.occluders as occ

    _already_imported(tmp_path)
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

    _already_imported(tmp_path)
    monkeypatch.setattr(occ.subprocess, "run", lambda *a, **k: None)
    with pytest.raises(OccluderError, match="no report"):
        occ.measure(tmp_path, "godot.exe")


# --------------------------------------------- the bake needs an imported project

def _record_runs(monkeypatch, cache_after_import=True):
    """Capture every subprocess the module launches, and fake `--import`."""
    import packages.exporting.occluders as occ
    calls = []

    def fake_run(argv, **kw):
        calls.append(list(argv))
        if "--import" in argv and cache_after_import:
            (Path(argv[argv.index("--path") + 1]) / CACHE_DIR).mkdir(
                parents=True, exist_ok=True)
        return None

    monkeypatch.setattr(occ.subprocess, "run", fake_run)
    return calls


def test_measure_imports_the_project_when_there_is_no_cache(tmp_path,
                                                            monkeypatch):
    """FAILS ON 0.97.0, WHICH NEVER IMPORTED AT ALL.

    Reproduced on the shipped `LF_club_block_004.portable-godot`, Godot
    4.7.stable, two clean copies of one package: with no `.godot` the bake
    printed `cannot load res://site.tscn`; with one it measured 414
    occluders. Sidecars are import SETTINGS, not imported resources.
    """
    import packages.exporting.occluders as occ

    calls = _record_runs(monkeypatch)
    (tmp_path / "occluders.json").write_text(
        json.dumps(_report([(2.0, 3.0, 0.2)])), encoding="utf-8")
    occ.measure(tmp_path, "godot.exe")
    assert any("--import" in c for c in calls), calls
    # And in that order: importing after the bake helps nobody.
    assert ([i for i, c in enumerate(calls) if "--import" in c][0]
            < [i for i, c in enumerate(calls) if "--script" in c][0])


def test_measure_does_not_reimport_when_the_cache_is_already_there(
        tmp_path, monkeypatch):
    """The export path pays nothing for this: the sidecar pass has already
    imported, and a second pass over a 19 MB package is 18 s of nothing."""
    import packages.exporting.occluders as occ

    calls = _record_runs(monkeypatch)
    (tmp_path / CACHE_DIR).mkdir()
    (tmp_path / "occluders.json").write_text(
        json.dumps(_report([(2.0, 3.0, 0.2)])), encoding="utf-8")
    occ.measure(tmp_path, "godot.exe")
    assert not any("--import" in c for c in calls), calls


def test_an_import_that_produces_no_cache_fails_rather_than_baking(
        tmp_path, monkeypatch):
    """Silence is not success -- the bake would then fail with `cannot load`
    and the export would be back to reading that as 'nothing to hide'."""
    _record_runs(monkeypatch, cache_after_import=False)
    with pytest.raises(OccluderError, match="no .godot cache"):
        ensure_imported(tmp_path, "godot.exe")


def test_dropping_the_cache_is_what_keeps_the_package_cache_free(tmp_path):
    """The bake needs the cache; the deliverable must not carry it. 75.2 MB
    against 1.4 MB of sidecars on cold run 9065's package."""
    (tmp_path / CACHE_DIR / "imported").mkdir(parents=True)
    (tmp_path / CACHE_DIR / "imported" / "x.ctex").write_bytes(b"0")
    assert drop_cache(tmp_path) is True
    assert not (tmp_path / CACHE_DIR).exists()
    assert drop_cache(tmp_path) is False


# --------------------------- the export hands the bake an imported project

def test_the_sidecar_pass_leaves_the_cache_for_the_bake(tmp_path,
                                                        monkeypatch):
    """FAILS ON 0.97.0, AND THIS IS THE LINE THAT SHIPPED 9065.

    `_write_import_sidecars` ended by removing `.godot` -- one line before
    the occluder bake, the only step in the export that has to `load()` a
    scene. Every real export therefore baked against a project Godot had
    never imported, and the 0.96.0 measurements missed it because they were
    taken on packages someone had imported by hand.
    """
    import subprocess as _sp

    from packages.exporting.export import _write_import_sidecars

    def fake_run(argv, **kw):
        if "--import" in argv:
            (Path(argv[argv.index("--path") + 1]) / CACHE_DIR).mkdir(
                parents=True, exist_ok=True)
        return None

    monkeypatch.setattr(_sp, "run", fake_run)
    _write_import_sidecars(tmp_path, "godot.exe")
    assert (tmp_path / CACHE_DIR).is_dir(), (
        "the bake runs next and cannot load anything without this")


def test_the_export_declares_an_occluder_enforcement_switch():
    """A failed bake with a Godot present is this build failing, not a
    warning. Pinned as a named constant so turning it off is a decision
    somebody writes down, the same shape as CLOSURE_ENFORCED."""
    from packages.exporting import export

    assert export.OCCLUDERS_ENFORCED is True
    assert issubclass(export.ExportOccluderError, RuntimeError)


# ------------------------------------------- the flag and the occluders agree

_PROJ = ("config_version=5\n\n[rendering]\n"
         'renderer/rendering_method="gl_compatibility"\n'
         "%s\n\n[debug]\n")
_OCC_SCENE = ('[gd_scene load_steps=2 format=3]\n\n'
              '[sub_resource type="BoxOccluder3D" id="BoxOccluder3D_0"]\n'
              "size = Vector3(2, 3, 0.2)\n\n"
              '[node name="Occluders" type="Node3D"]\n\n'
              '[node name="occ_0000" type="OccluderInstance3D" parent="."]\n')


def test_audit_catches_the_exact_state_cold_run_9065_shipped(tmp_path):
    """THE ONE THAT MATTERS. FAILS ON 0.97.0, which had no audit and shipped
    this package: `use_occlusion_culling=true`, zero `OccluderInstance3D`
    anywhere in the tree, and an `occluders.json` reading
    `{"ok": false, "error": "cannot load res://site.tscn"}` beside them.

    The flag on and the culling absent is worse than neither: the recipient
    pays the software rasteriser's fixed per-frame cost for nothing.
    """
    (tmp_path / "project.godot").write_text(_PROJ % _OCC_SETTING,
                                            encoding="utf-8")
    (tmp_path / "site.tscn").write_text(
        '[gd_scene format=3]\n[node name="Site" type="Node3D"]\n',
        encoding="utf-8")
    (tmp_path / "occluders.json").write_text(
        json.dumps({"schema": "lf.occluders.v1", "ok": False,
                    "error": "cannot load res://site.tscn"}),
        encoding="utf-8")
    with pytest.raises(OccluderDisagreement, match="nothing to cull"):
        audit(tmp_path)


def test_audit_catches_occluders_the_engine_will_never_consult(tmp_path):
    """The other direction, and it is a defect too: 414 occluder nodes with
    the culler off is a scene of input nothing reads."""
    (tmp_path / "project.godot").write_text(_PROJ % _OCC_OFF, encoding="utf-8")
    (tmp_path / "occluders.tscn").write_text(_OCC_SCENE, encoding="utf-8")
    with pytest.raises(OccluderDisagreement, match="never be consulted"):
        audit(tmp_path)


def test_audit_passes_a_package_where_the_two_agree(tmp_path):
    """A check that cannot fail is indistinguishable from one that passed --
    so pin that this one passes on the state the fix is supposed to produce,
    not only that it fails on the state that shipped."""
    (tmp_path / "project.godot").write_text(_PROJ % _OCC_SETTING,
                                            encoding="utf-8")
    (tmp_path / "occluders.tscn").write_text(_OCC_SCENE, encoding="utf-8")
    v = audit(tmp_path)
    assert v == {"use_occlusion_culling": True, "occluder_nodes": 1,
                 "scenes_with_occluders": 1, "bake_reported_ok": None}


def test_audit_passes_a_package_that_decided_against_the_culler(tmp_path):
    """No Godot, no bake, no occluders, flag off. Consistent and honest."""
    (tmp_path / "project.godot").write_text(_PROJ % _OCC_OFF, encoding="utf-8")
    assert audit(tmp_path)["occluder_nodes"] == 0


def test_audit_refuses_a_package_that_makes_no_single_statement(tmp_path):
    """Two `use_occlusion_culling` lines is not a package with an answer, and
    an unrecognised shape FAILS rather than reading as one of the two."""
    (tmp_path / "project.godot").write_text(
        _PROJ % (_OCC_SETTING + "\n" + _OCC_OFF), encoding="utf-8")
    with pytest.raises(OccluderDisagreement, match="expected exactly 1"):
        audit(tmp_path)
    (tmp_path / "project.godot").write_text("config_version=5\n",
                                            encoding="utf-8")
    with pytest.raises(OccluderDisagreement, match="expected exactly 1"):
        audit(tmp_path)


def test_audit_counts_occluders_anywhere_in_the_package(tmp_path):
    """It reads the SCENES a recipient will load, not `occluders.json`. The
    gap between what the bake reported and what shipped is where 9065 lived,
    so the report is never what decides."""
    (tmp_path / "project.godot").write_text(_PROJ % _OCC_SETTING,
                                            encoding="utf-8")
    (tmp_path / "lot").mkdir()
    (tmp_path / "lot" / "shell.tscn").write_text(_OCC_SCENE, encoding="utf-8")
    (tmp_path / "occluders.json").write_text(
        json.dumps({"schema": "lf.occluders.v1", "ok": True, "occluders": 0}),
        encoding="utf-8")
    v = audit(tmp_path)
    assert v["occluder_nodes"] == 1
    assert v["bake_reported_ok"] is True


def test_audit_ignores_the_import_cache(tmp_path):
    """A `.tscn` Godot wrote into `.godot/` is not something that ships."""
    (tmp_path / "project.godot").write_text(_PROJ % _OCC_OFF, encoding="utf-8")
    (tmp_path / CACHE_DIR).mkdir()
    (tmp_path / CACHE_DIR / "c.tscn").write_text(_OCC_SCENE, encoding="utf-8")
    assert audit(tmp_path)["occluder_nodes"] == 0


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
