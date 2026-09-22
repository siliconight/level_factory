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

0.102.0 ADDED THE REACHABILITY SET, because every one of the above was true
and cold run 9066's package STILL shipped the culler switched on with nothing
to cull. 301 `OccluderInstance3D` were in it and 0 were in the tree
`run/main_scene` builds: `occluders.tscn` was instanced from `site.tscn`, and
the entry scene instances `presentation/lux.applied.tscn` and the dressing
layer and never names `site.tscn`. Verified twice on the shipped package, on
4.7.stable and 4.8-dev6.

The 0.98.0 audit passed it, and the reason is the reason these exist:
`rglob("*.tscn")` asked whether the nodes are in the box when the question
was whether the engine will load them, and a check that cannot fail on the
defect it was written for is indistinguishable from one that passed.

* THE RULE IS REACHABILITY, NOT PRESENCE. `reachable_occluders` walks from
  `run/main_scene` down, following the two kinds of edge the package really
  uses -- an `ext_resource` PackedScene that a node INSTANCES, and a
  `load()` of a `res://` path from an embedded script, which is the only way
  `mission.tscn` reaches its content.

* DECLARING IS NOT INSTANCING. That distinction IS the defect: `site.tscn`
  declared `occluders.tscn` and nothing instanced `site.tscn`.

* TWO INSTRUMENTS, AND A DISAGREEMENT IS A BUILD FAILURE. The text walk needs
  no Godot and runs on every export; `assets/godot/count_occluders.gd` loads
  the entry scene the way a recipient does and counts the tree. When they
  differ, one of them is wrong and neither is evidence.

* THE A/B PROBE MEASURES THE SCENE THE PACKAGE RUNS. `tools/occlusion_ab.gd`
  loaded `res://site.tscn` by name, so every occlusion figure this repo
  published before 0.102.0 described a scene the mission does not load.

Run:  python -m pytest tests/unit/test_occluders.py
"""
import json
from pathlib import Path

import pytest

from packages.core.godot_project import (OCCLUSION_KEY, rendering_block,
                                         set_occlusion_culling)
from packages.exporting.occluders import (BAKE_SCRIPT, CACHE_DIR, COUNT_SCRIPT,
                                          ENTRY_SCENE, HOLDER_NODE,
                                          OCCLUDER_SCENE, RUNTIME_SCHEMA,
                                          OccluderDisagreement, OccluderError,
                                          audit, drop_cache, ensure_imported,
                                          measure, reachable_occluders,
                                          scene_text, wire_into_scene)

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


def test_wiring_a_scene_with_no_ext_resource_block(tmp_path):
    """FAILS ON 0.101.0, WHICH REFUSED THIS SHAPE -- AND IT IS THE ENTRY
    SCENE'S SHAPE.

    `mission.tscn` carries its entry script as a `sub_resource` and instances
    its content by `load()`, so it has no `ext_resource` block at all. The old
    refusal read as caution about "a scene that is not ours" and was in fact
    aimed at the one scene the occluders now have to go into. Read off cold
    run 9066's package, not imagined: its entry scene is exactly this shape.
    """
    entry = tmp_path / ENTRY_SCENE
    entry.write_text(
        '[gd_scene load_steps=2 format=3]\n\n'
        '[sub_resource type="GDScript" id="mission_entry"]\n'
        'script/source = "extends Node3D"\n\n'
        '[node name="Mission" type="Node3D"]\n', encoding="utf-8")
    assert wire_into_scene(entry) is True
    text = entry.read_text(encoding="utf-8")
    assert text.count(f'path="res://{OCCLUDER_SCENE}"') == 1
    assert text.count(f'[node name="{HOLDER_NODE}" parent="."') == 1
    # The reference goes straight after the header, where Godot writes the
    # first one -- not after the sub_resource, and not after a node.
    assert (text.index(f'path="res://{OCCLUDER_SCENE}"')
            < text.index("[sub_resource "))
    # And the scene stops lying about how many resources it loads.
    assert text.splitlines()[0] == "[gd_scene load_steps=3 format=3]"


def test_wiring_a_scene_with_no_load_steps_gives_it_one(tmp_path):
    """Godot omits `load_steps` for a scene with no resources. Adding one
    resource to such a scene means adding the count too."""
    entry = tmp_path / ENTRY_SCENE
    entry.write_text('[gd_scene format=3]\n\n[node name="M" type="Node3D"]\n',
                     encoding="utf-8")
    assert wire_into_scene(entry) is True
    assert entry.read_text(encoding="utf-8").splitlines()[0] == (
        "[gd_scene format=3 load_steps=2]")


def test_wiring_refuses_a_file_that_is_not_a_scene(tmp_path):
    """The refusal that is still right: a file with no `[gd_scene]` header is
    not something a holder can be put into by guessing."""
    entry = tmp_path / ENTRY_SCENE
    entry.write_text("extends Node3D\n", encoding="utf-8")
    with pytest.raises(OccluderError, match="no .gd_scene. header"):
        wire_into_scene(entry)


def test_wiring_keeps_the_scene_s_own_line_endings(tmp_path):
    """`write_text` translates to `os.linesep`, so a rewrite on Windows turns
    an LF scene CRLF and every line of the diff is the rewrite. The same trap
    put 81 bare LF lines into a CRLF CLAUDE.md."""
    entry = tmp_path / ENTRY_SCENE
    entry.write_bytes(_SITE.replace("\n", "\r\n").encode("utf-8"))
    wire_into_scene(entry)
    raw = entry.read_bytes()
    assert raw.count(b"\r\n") == raw.count(b"\n")

    lf = tmp_path / "lf.tscn"
    lf.write_bytes(_SITE.encode("utf-8"))
    wire_into_scene(lf)
    assert b"\r\n" not in lf.read_bytes()


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

_PROJ = ('config_version=5\n\n[application]\nrun/main_scene="res://%s"\n\n'
         "[rendering]\n"
         'renderer/rendering_method="gl_compatibility"\n'
         "%%s\n\n[debug]\n") % ENTRY_SCENE
_OCC_SCENE = ('[gd_scene load_steps=2 format=3]\n\n'
              '[sub_resource type="BoxOccluder3D" id="BoxOccluder3D_0"]\n'
              "size = Vector3(2, 3, 0.2)\n\n"
              '[node name="Occluders" type="Node3D"]\n\n'
              '[node name="occ_0000" type="OccluderInstance3D" parent="."]\n')

#: THE ENTRY SCENE, copied in shape from cold run 9066's shipped
#: `mission.tscn` rather than imagined: no `ext_resource` block at all, an
#: entry script as a `sub_resource`, and the level reached by `load()` of a
#: `res://` path from `_ready()`. A walker written against a guessed shape
#: would find nothing here and read a healthy package as broken.
_ENTRY = (
    "[gd_scene load_steps=2 format=3]\n"
    "\n"
    '[sub_resource type="GDScript" id="mission_entry"]\n'
    'script/source = "extends Node3D\n'
    "\n"
    "func _ready() -> void:\n"
    "\tvar packed_0 := load('res://presentation/lux.applied.tscn') "
    "as PackedScene\n"
    "\tif packed_0 != null:\n"
    "\t\tadd_child(packed_0.instantiate())\n"
    '"\n'
    "\n"
    '[node name="Mission" type="Node3D"]\n'
    'script = SubResource("mission_entry")\n'
)

#: The relit scene the entry loads. It pulls the buildings by `res://` path
#: and instances them; it never names the root `site.tscn`.
_LUX = (
    "[gd_scene load_steps=2 format=3]\n\n"
    '[ext_resource type="PackedScene" path="res://lot/a/site.tscn" '
    'id="35_wrrlu"]\n\n'
    '[node name="Site" type="Node3D"]\n\n'
    '[node name="b0" type="Node3D" parent="." '
    'instance=ExtResource("35_wrrlu")]\n'
)


def _package(tmp_path, flag=_OCC_SETTING, entry=_ENTRY):
    """A package of the shape cold run 9066 shipped: an entry scene that
    loads a presentation scene, which instances a building."""
    (tmp_path / "project.godot").write_text(_PROJ % flag, encoding="utf-8")
    (tmp_path / ENTRY_SCENE).write_text(entry, encoding="utf-8")
    (tmp_path / "presentation").mkdir(exist_ok=True)
    (tmp_path / "presentation" / "lux.applied.tscn").write_text(
        _LUX, encoding="utf-8")
    (tmp_path / "lot" / "a").mkdir(parents=True, exist_ok=True)
    (tmp_path / "lot" / "a" / "site.tscn").write_text(
        '[gd_scene format=3]\n[node name="Bldg" type="Node3D"]\n',
        encoding="utf-8")
    return tmp_path


def test_audit_catches_the_state_cold_run_9066_SHIPPED(tmp_path):
    """THE ONE THAT MATTERS NOW, AND IT PASSES ON 0.101.0.

    Flag on, 1 `OccluderInstance3D` in the package, and the scene
    `run/main_scene` names reaching none of it -- because `occluders.tscn` is
    instanced from a root `site.tscn` that nothing instances. 0.101.0's audit
    counted nodes with `rglob` and returned
    `{use_occlusion_culling: True, occluder_nodes: 1, ...}` for this package,
    which is the verdict cold run 9066 shipped on.

    Verified against the real artefact, not only here: on
    `LF_club_block_005.portable-godot`, Godot 4.7.stable and 4.8-dev6,
    `count_occluders.gd` reports 0 occluders in a tree of 8,319 nodes, and
    this walk reports 0 reachable of 301 shipped over 6 scenes.
    """
    _package(tmp_path)
    (tmp_path / OCCLUDER_SCENE).write_text(_OCC_SCENE, encoding="utf-8")
    # The 0.98.0 wiring, verbatim: declared and instanced in `site.tscn`...
    (tmp_path / "site.tscn").write_text(
        "[gd_scene load_steps=2 format=3]\n\n"
        f'[ext_resource type="PackedScene" path="res://{OCCLUDER_SCENE}" '
        'id="lf_occluders"]\n\n'
        '[node name="Site" type="Node3D"]\n\n'
        f'[node name="{HOLDER_NODE}" parent="." '
        'instance=ExtResource("lf_occluders")]\n', encoding="utf-8")
    # ...and nothing instances `site.tscn`.
    with pytest.raises(OccluderDisagreement, match="0 reachable"):
        audit(tmp_path)


def test_audit_catches_the_exact_state_cold_run_9065_shipped(tmp_path):
    """FAILS ON 0.97.0, which had no audit and shipped this package:
    `use_occlusion_culling=true`, zero `OccluderInstance3D` anywhere in the
    tree, and an `occluders.json` reading
    `{"ok": false, "error": "cannot load res://site.tscn"}` beside them.

    The flag on and the culling absent is worse than neither: the recipient
    pays the software rasteriser's fixed per-frame cost for nothing. Kept
    apart from 9066's state above because the two have different fixes and a
    shared message would hide which one a package is in.
    """
    _package(tmp_path)
    (tmp_path / "occluders.json").write_text(
        json.dumps({"schema": "lf.occluders.v1", "ok": False,
                    "error": "cannot load res://site.tscn"}),
        encoding="utf-8")
    with pytest.raises(OccluderDisagreement, match="9065"):
        audit(tmp_path)


def test_audit_catches_occluders_the_engine_will_never_consult(tmp_path):
    """The other direction, and it is a defect too: 414 occluder nodes with
    the culler off is a scene of input nothing reads."""
    _package(tmp_path, flag=_OCC_OFF)
    (tmp_path / OCCLUDER_SCENE).write_text(_OCC_SCENE, encoding="utf-8")
    with pytest.raises(OccluderDisagreement, match="never be consulted"):
        audit(tmp_path)


def _wired_entry():
    """The entry scene after `wire_into_scene` -- the state the fix produces."""
    return (
        "[gd_scene load_steps=3 format=3]\n"
        f'[ext_resource type="PackedScene" path="res://{OCCLUDER_SCENE}" '
        'id="lf_occluders"]\n'
        + _ENTRY.split("\n", 1)[1]
        + f'\n[node name="{HOLDER_NODE}" parent="." '
          'instance=ExtResource("lf_occluders")]\n')


def test_audit_passes_a_package_whose_entry_scene_reaches_them(tmp_path):
    """A check that cannot fail is indistinguishable from one that passed --
    so pin that this one passes on the state the fix is supposed to produce,
    not only that it fails on the two states that shipped."""
    _package(tmp_path, entry=_wired_entry())
    (tmp_path / OCCLUDER_SCENE).write_text(_OCC_SCENE, encoding="utf-8")
    v = audit(tmp_path)
    assert v["use_occlusion_culling"] is True
    assert v["occluder_nodes"] == 1            # reachable
    assert v["occluder_nodes_in_package"] == 1
    assert v["main_scene"] == ENTRY_SCENE
    assert v["occluder_scenes_reached"] == [OCCLUDER_SCENE]
    assert v["scenes_walked"] == 4             # entry, occluders, lux, bldg


def test_audit_passes_a_package_that_decided_against_the_culler(tmp_path):
    """No Godot, no bake, no occluders, flag off. Consistent and honest."""
    _package(tmp_path, flag=_OCC_OFF)
    assert audit(tmp_path)["occluder_nodes"] == 0


def test_audit_refuses_a_package_that_makes_no_single_statement(tmp_path):
    """Two `use_occlusion_culling` lines is not a package with an answer, and
    an unrecognised shape FAILS rather than reading as one of the two."""
    _package(tmp_path, flag=_OCC_SETTING + "\n" + _OCC_OFF)
    with pytest.raises(OccluderDisagreement, match="expected exactly 1"):
        audit(tmp_path)
    (tmp_path / "project.godot").write_text("config_version=5\n",
                                            encoding="utf-8")
    with pytest.raises(OccluderDisagreement, match="expected exactly 1"):
        audit(tmp_path)


def test_audit_catches_an_occluder_scene_the_entry_cannot_reach(tmp_path):
    """FAILS ON 0.101.0, which counted a node in any `.tscn` in the tree and
    called it shipped occlusion.

    An orphan is its own finding and gets its own message, so the residue
    after a fix is diagnostic rather than a surprise -- LF 0.94.0 dropped an
    orphan `site_base.glb` for the same reason. Here the entry DOES reach one
    occluder and a second one sits in a scene nothing loads.
    """
    _package(tmp_path, entry=_wired_entry())
    (tmp_path / OCCLUDER_SCENE).write_text(_OCC_SCENE, encoding="utf-8")
    (tmp_path / "lot" / "orphan.tscn").write_text(_OCC_SCENE, encoding="utf-8")
    with pytest.raises(OccluderDisagreement, match="in no scene the engine"):
        audit(tmp_path)


def test_audit_fails_when_the_two_instruments_disagree(tmp_path):
    """When two instruments disagree, one of them is wrong -- and nothing
    gets built on either until that is settled. Godot loading the entry scene
    and this walk of its text answer the same question two ways, and the
    export runs both precisely so a gap is a failure and not a preference."""
    _package(tmp_path, entry=_wired_entry())
    (tmp_path / OCCLUDER_SCENE).write_text(_OCC_SCENE, encoding="utf-8")
    (tmp_path / "occluders.json").write_text(json.dumps({
        "schema": "lf.occluders.v1", "ok": True, "occluders": 1,
        "runtime": {"schema": RUNTIME_SCHEMA, "ok": True,
                    "main_scene": f"res://{ENTRY_SCENE}",
                    "occluder_nodes": 7},
    }), encoding="utf-8")
    with pytest.raises(OccluderDisagreement, match="two instruments disagree"):
        audit(tmp_path)


def test_a_runtime_block_of_an_unknown_shape_reads_as_absent(tmp_path):
    """Not as zero. A missing key that becomes a zero is how a `--verify`
    printed `closure verdict clean` three lines under a broken export."""
    _package(tmp_path, entry=_wired_entry())
    (tmp_path / OCCLUDER_SCENE).write_text(_OCC_SCENE, encoding="utf-8")
    (tmp_path / "occluders.json").write_text(json.dumps({
        "schema": "lf.occluders.v1", "ok": True, "occluders": 1,
        "runtime": {"schema": "something.else.v9", "occluder_nodes": 0},
    }), encoding="utf-8")
    assert audit(tmp_path)["runtime_occluder_nodes"] is None


def test_audit_ignores_the_import_cache(tmp_path):
    """A `.tscn` Godot wrote into `.godot/` is not something that ships."""
    _package(tmp_path, flag=_OCC_OFF)
    (tmp_path / CACHE_DIR).mkdir()
    (tmp_path / CACHE_DIR / "c.tscn").write_text(_OCC_SCENE, encoding="utf-8")
    assert audit(tmp_path)["occluder_nodes"] == 0


# ------------------------------------------------- what the entry can REACH

def test_the_walk_follows_load_from_the_entry_script(tmp_path):
    """`mission.tscn` reaches its content ONLY this way -- its entry script is
    a `sub_resource` and the scenes it adds appear in no resource block. A
    walker that followed `ext_resource` alone would report every package
    empty and this whole rule would be a check that cannot fail."""
    _package(tmp_path)
    w = reachable_occluders(tmp_path)
    assert w["main_scene"] == ENTRY_SCENE
    assert w["scenes_walked"] == [ENTRY_SCENE, "presentation/lux.applied.tscn",
                                  "lot/a/site.tscn"]


def test_declaring_a_packed_scene_is_not_instancing_it(tmp_path):
    """THE DISTINCTION THE RULE RESTS ON, and the defect in one line:
    `site.tscn` DECLARED `occluders.tscn` and nothing instanced `site.tscn`.
    A declared-but-uninstanced PackedScene is a resource the loader may build
    and no node ever adds to the tree."""
    _package(tmp_path)
    (tmp_path / "presentation" / "lux.applied.tscn").write_text(
        "[gd_scene load_steps=2 format=3]\n\n"
        f'[ext_resource type="PackedScene" path="res://{OCCLUDER_SCENE}" '
        'id="declared"]\n\n'
        '[node name="Site" type="Node3D"]\n', encoding="utf-8")
    (tmp_path / OCCLUDER_SCENE).write_text(_OCC_SCENE, encoding="utf-8")
    w = reachable_occluders(tmp_path)
    assert OCCLUDER_SCENE not in w["scenes_walked"]
    assert w["occluder_nodes"] == 0


def test_a_relative_ext_resource_path_resolves_against_its_own_scene(tmp_path):
    """Read off cold run 9066's `site.tscn`, which carries BOTH spellings:
    `lot/strip_club_a02/site.tscn` with no prefix beside
    `res://occluders.tscn` with one. Godot resolves the bare one relative to
    the scene that names it."""
    _package(tmp_path)
    (tmp_path / "presentation" / "sub").mkdir()
    (tmp_path / "presentation" / "sub" / "inner.tscn").write_text(
        _OCC_SCENE, encoding="utf-8")
    (tmp_path / "presentation" / "lux.applied.tscn").write_text(
        "[gd_scene load_steps=2 format=3]\n\n"
        '[ext_resource type="PackedScene" path="sub/inner.tscn" id="r"]\n\n'
        '[node name="Site" type="Node3D"]\n\n'
        '[node name="i" parent="." instance=ExtResource("r")]\n',
        encoding="utf-8")
    w = reachable_occluders(tmp_path)
    assert "presentation/sub/inner.tscn" in w["scenes_walked"]
    assert w["occluder_nodes"] == 1


def test_the_walk_refuses_a_package_that_does_not_say_what_it_runs(tmp_path):
    """A walk with no starting point has learned nothing and must say so,
    rather than reporting an empty reachable set that reads as a defect."""
    _package(tmp_path)
    (tmp_path / "project.godot").write_text(
        "config_version=5\n\n[rendering]\n" + _OCC_OFF + "\n",
        encoding="utf-8")
    with pytest.raises(OccluderDisagreement, match="run/main_scene"):
        reachable_occluders(tmp_path)


def test_the_walk_refuses_a_main_scene_the_package_does_not_contain(tmp_path):
    _package(tmp_path)
    (tmp_path / ENTRY_SCENE).unlink()
    with pytest.raises(OccluderDisagreement, match="does not contain it"):
        reachable_occluders(tmp_path)


def test_a_missing_scene_reference_is_recorded_and_not_raised_on(tmp_path):
    """Unresolved resources are `closure.scan_closure`'s verdict to give.
    Two gates shouting about one defect is how a fix looks like it did not
    work -- `LOT_STEP_BLOCKS_A_ROUTE`'s seven findings were three defects."""
    _package(tmp_path)
    (tmp_path / "lot" / "a" / "site.tscn").unlink()
    w = reachable_occluders(tmp_path)
    assert w["unresolved_scene_refs"] == [
        "presentation/lux.applied.tscn -> res://lot/a/site.tscn"]


def test_the_walk_names_the_scenes_nothing_loads(tmp_path):
    """A REPORT, NOT A RAISE. On cold run 9066's package this is `site.tscn`
    -- 312 KB the entry never names, because the relit scene instances the
    three `lot/<archetype>/site.tscn` buildings directly. LF 0.94.0 dropped
    an orphan `site_base.glb` for this reason; dropping THIS one by the same
    reflex would be wrong, because a single-shell mission's presentation
    scene does name `res://site.tscn` and deleting it broke closure once.
    So it is said out loud and the decision stays with the reader."""
    _package(tmp_path)
    (tmp_path / "site.tscn").write_text(
        '[gd_scene format=3]\n[node name="Site" type="Node3D"]\n',
        encoding="utf-8")
    assert reachable_occluders(tmp_path)["unreachable_scenes"] == ["site.tscn"]


def test_a_cycle_between_scenes_terminates(tmp_path):
    """Two scenes that load each other is not a package this can hang on."""
    _package(tmp_path)
    (tmp_path / "lot" / "a" / "site.tscn").write_text(
        "[gd_scene load_steps=2 format=3]\n\n"
        '[ext_resource type="PackedScene" '
        'path="res://presentation/lux.applied.tscn" id="back"]\n\n'
        '[node name="Bldg" type="Node3D"]\n\n'
        '[node name="b" parent="." instance=ExtResource("back")]\n',
        encoding="utf-8")
    assert len(reachable_occluders(tmp_path)["scenes_walked"]) == 3


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


# --------------------------------------- the holder goes where the mission is

def test_the_occluders_are_wired_into_the_scene_the_package_runs():
    """FAILS ON 0.101.0, whose `emit` defaulted `scene_name` to `site.tscn`.

    The package names its entry in `run/main_scene` and `localize.py` writes
    that name in exactly one place; if these two ever spell it differently
    the occluders go into a scene the recipient does not load, which is the
    whole of cold run 9066's defect.
    """
    from packages.exporting import localize
    from packages.exporting.export import ExportProfile

    assert ENTRY_SCENE == "mission.tscn"
    assert f'(export_dir / "{ENTRY_SCENE}").write_text' in (
        Path(localize.__file__).read_text(encoding="utf-8"))
    assert ExportProfile.entry_scene == ENTRY_SCENE


def test_emit_refuses_a_package_with_no_entry_scene(tmp_path):
    """Rather than baking, writing a scene and wiring it into nothing. The
    entry is written by `localize.write_entry_scene` well before this runs,
    so its absence is a broken build and not a mode."""
    import packages.exporting.occluders as occ

    with pytest.raises(OccluderError, match=ENTRY_SCENE):
        occ.emit(tmp_path, "godot.exe")


def test_the_bake_is_run_against_the_scene_it_is_wired_into(tmp_path,
                                                            monkeypatch):
    """FAILS ON 0.101.0, WHICH BAKED `site.tscn` AND WIRED `site.tscn` -- so
    the question never came up, and then the holder moved and it did.

    The bake reports every transform relative to the ROOT OF THE SCENE IT WAS
    HANDED. Baking one scene and wiring the result into another is a silent
    assertion that the two frames coincide. They did on cold run 9066's
    package -- the same bake against `res://site.tscn` and `res://mission.tscn`
    produced byte-identical `modules` lists, 301 occluders each -- and an
    assertion nothing checks is how this feature shipped broken twice.
    """
    import packages.exporting.occluders as occ

    scenes = []

    def fake_measure(export_dir, godot, *, scene, **kw):
        scenes.append(scene)
        return {"schema": occ.SCHEMA, "ok": True, "occluders": 0,
                "modules": [], "classified": {}}

    monkeypatch.setattr(occ, "measure", fake_measure)
    (tmp_path / ENTRY_SCENE).write_text(_ENTRY, encoding="utf-8")
    occ.emit(tmp_path, "godot.exe")
    assert scenes == [f"res://{ENTRY_SCENE}"]


# ----------------------------------------------------------- the probes agree

def test_the_runtime_count_script_ships_and_reads_the_main_scene_setting():
    """The arbiter. It must ask the PACKAGE which scene it runs rather than
    naming one, or it is the same defect in the instrument."""
    assert COUNT_SCRIPT.is_file()
    text = COUNT_SCRIPT.read_text(encoding="utf-8")
    assert 'MAIN_SCENE_KEY := "application/run/main_scene"' in text
    assert "ProjectSettings.get_setting(MAIN_SCENE_KEY" in text
    assert "res://site.tscn" not in text
    # `godot --script` runs the script AS the main loop, so it has to be a
    # SceneTree and drive itself. Launched any other way the engine raises a
    # modal dialog -- on the walker's machine. CLAUDE.md, twice on 2026-09-21.
    assert text.splitlines()[0] == "extends SceneTree"
    assert "quit(" in text


def test_the_ab_probe_measures_the_scene_the_package_runs():
    """FAILS ON 0.101.0, and this is the other half of the defect.

    `tools/occlusion_ab.gd` loaded `res://site.tscn` by name, so every
    occlusion figure this repo published -- 13 draw calls against 2,490
    inside the shop, 1,854 against 3,334 at exterior_sw -- was measured on a
    Lux-less, undressed scene the mission never loads. An instrument that
    names its own subject cannot notice that the subject moved.
    """
    probe = Path(__file__).resolve().parents[2] / "tools" / "occlusion_ab.gd"
    assert probe.is_file()
    text = probe.read_text(encoding="utf-8")
    body = "\n".join(ln for ln in text.splitlines()
                     if not ln.lstrip().startswith("##"))
    assert 'load("res://site.tscn")' not in body
    assert 'ProjectSettings.get_setting(\n\t\t"application/run/main_scene"' in body
    # And it says which scene it measured, in the artefact -- two runs over
    # two entry scenes are not an A/B and there was no way to tell.
    assert '"main_scene": main_scene' in body
