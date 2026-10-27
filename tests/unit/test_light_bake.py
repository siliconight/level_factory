"""The light bake (0.131.0): what it marks, what it ships, and that a bake
that fails ships the package unbaked."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from packages.exporting import light_bake as LB
from tests.unit.glb_fixture import pack_glb

_SIDECAR = """[remap]

importer="scene"
type="PackedScene"

[params]

meshes/ensure_tangents=true
meshes/light_baking=1
meshes/lightmap_texel_size=0.2
"""


def _glb(path: Path, uv2: bool) -> None:
    attrs = {"POSITION": 0, "NORMAL": 1}
    if uv2:
        attrs["TEXCOORD_1"] = 2
    doc = {"asset": {"version": "2.0"}, "meshes": [{"primitives": [{"attributes": attrs}]}]}
    path.write_bytes(pack_glb(doc))


def test_static_lightmaps_on_every_model_but_those_whose_uv2_is_shader_data(tmp_path):
    _glb(tmp_path / "shell.glb", uv2=False)
    _glb(tmp_path / "grill.glb", uv2=True)
    (tmp_path / "shell.glb.import").write_text(_SIDECAR, encoding="utf-8")
    (tmp_path / "grill.glb.import").write_text(_SIDECAR, encoding="utf-8")
    _glb(tmp_path / "odd.glb", uv2=False)
    (tmp_path / "odd.glb.import").write_text("[remap]\nimporter=\"scene\"\n", encoding="utf-8")
    got = LB.mark_imports(tmp_path)
    # the report's `unlit` (0.194.0): a site's wires, none here
    assert got == {"baked": ["shell.glb"], "dynamic": ["grill.glb"], "spawned": [],
                   "spawned_unmatched": [], "unreadable": ["odd.glb"], "unlit": []}
    assert "meshes/light_baking=2" in (tmp_path / "shell.glb.import").read_text(encoding="utf-8")
    assert "meshes/light_baking=1" in (tmp_path / "grill.glb.import").read_text(encoding="utf-8")


def test_a_spawned_model_is_set_dynamic_not_baked(tmp_path):
    """0.162.1: the responders' car is spawned by the gameplay layer and never
    in the bake, so its import is Dynamic (3), which samples the lightmap's
    probes; Static Lightmaps (2) would leave a spawned car unlit by either.
    A spawned path with no sidecar is said, not dropped."""
    (tmp_path / "cover").mkdir()
    _glb(tmp_path / "shell.glb", uv2=False)
    _glb(tmp_path / "cover" / "car.glb", uv2=False)
    (tmp_path / "shell.glb.import").write_text(_SIDECAR, encoding="utf-8")
    (tmp_path / "cover" / "car.glb.import").write_text(_SIDECAR, encoding="utf-8")
    got = LB.mark_imports(tmp_path, spawned=["cover/car.glb", "cover/gone.glb"])
    assert got["baked"] == ["shell.glb"] and got["spawned"] == ["cover/car.glb"]
    assert got["spawned_unmatched"] == ["cover/gone.glb"]
    assert "meshes/light_baking=3" in (tmp_path / "cover" / "car.glb.import").read_text(encoding="utf-8")
    assert "meshes/light_baking=2" in (tmp_path / "shell.glb.import").read_text(encoding="utf-8")
    assert LB.DYNAMIC == 3 and LB.STATIC_LIGHTMAPS == 2


def test_inline_primitives_unwrap_themselves_once(tmp_path):
    scene = tmp_path / "site.tscn"
    scene.write_text('[gd_scene format=3]\n\n[sub_resource type="BoxMesh" id="a"]\nsize = Vector3(1, 1, 1)\n\n'
                     '[sub_resource type="QuadMesh" id="b"]\n\n[sub_resource type="ArrayMesh" id="c"]\n\n'
                     '[sub_resource type="BoxMesh" id="d"]\n', encoding="utf-8")
    assert LB.add_primitive_uv2(tmp_path) == {"site.tscn": 3}
    assert scene.read_text(encoding="utf-8").count("add_uv2 = true") == 3
    assert LB.add_primitive_uv2(tmp_path) == {}


_RIGS = """[gd_scene format=3]

[ext_resource type="Script" path="res://runtime/lux/resources/lux_light_rig.gd" id="49_x"]

[sub_resource type="Resource" id="steady"]
script = ExtResource("49_x")
rig_name = &"Streetlight (baked)"

[sub_resource type="Resource" id="was_realtime"]
script = ExtResource("49_x")
bake_mode = 0
rig_name = &"Fluorescent"

[sub_resource type="Resource" id="cycling"]
script = ExtResource("49_x")
failing_kind = 2
rig_name = &"Streetlight (baked)"

[node name="Site" type="Node3D"]
"""


def test_steady_rigs_bake_static_and_failing_ones_stay_live(tmp_path):
    scene = tmp_path / "lux.applied.tscn"
    scene.write_text(_RIGS, encoding="utf-8")
    assert LB.mark_steady_rigs(scene) == {"static": 2, "live": 1, "cycling": 0}
    text = scene.read_text(encoding="utf-8")
    assert text.count("bake_mode = 1") == 2 and "bake_mode = 0" not in text
    cycling = text.split('id="cycling"]')[1].split("[")[0]
    assert "bake_mode" not in cycling


def test_a_scene_without_lux_rigs_is_refused(tmp_path):
    scene = tmp_path / "x.tscn"
    scene.write_text("[gd_scene format=3]\n", encoding="utf-8")
    try:
        LB.mark_steady_rigs(scene)
    except ValueError as exc:
        assert "lux_light_rig" in str(exc)
    else:
        raise AssertionError("refused nothing")


def _package(tmp_path: Path) -> Path:
    pkg = tmp_path / "LF_t.portable-godot"
    (pkg / "presentation").mkdir(parents=True)
    (pkg / "presentation" / "lux.applied.tscn").write_text(_RIGS, encoding="utf-8")
    (pkg / "mission.tscn").write_text(
        "\tvar packed_0 := load('res://presentation/lux.applied.tscn') as PackedScene\n", encoding="utf-8")
    (pkg / "project.godot").write_text('[rendering]\nrenderer/rendering_method="gl_compatibility"\n',
                                       encoding="utf-8")
    return pkg


def test_no_godot_bakes_nothing_and_says_so(tmp_path):
    pkg = _package(tmp_path)
    before = (pkg / "presentation" / "lux.applied.tscn").read_bytes()
    r = LB.bake(pkg, None, log=lambda *a: None)
    assert r["ok"] is False and "no Godot" in r["reason"]
    assert (pkg / "presentation" / "lux.applied.tscn").read_bytes() == before
    assert json.loads((pkg / LB.REPORT).read_text(encoding="utf-8"))["ok"] is False


def test_a_bake_that_fails_ships_the_package_unbaked(tmp_path, monkeypatch):
    pkg = _package(tmp_path)
    pres = (pkg / "presentation" / "lux.applied.tscn").read_bytes()
    entry = (pkg / "mission.tscn").read_bytes()
    monkeypatch.setattr(LB, "_import", lambda d, g: True)
    monkeypatch.setattr(LB, "_run", lambda cmd, timeout, log_path=None: (None, float(timeout)))
    r = LB.bake(pkg, "godot.exe", log=lambda *a: None)
    assert r["ok"] is False and "did not finish" in r["reason"]
    assert (pkg / "presentation" / "lux.applied.tscn").read_bytes() == pres
    assert (pkg / "mission.tscn").read_bytes() == entry
    assert not any((pkg / f).exists() for f in LB.BAKE_FILES)
    assert not (tmp_path / "LF_t.portable-godot.lightbake").exists()


def test_a_bake_that_works_ships_the_lightmap_and_points_the_entry_at_it(tmp_path, monkeypatch):
    pkg = _package(tmp_path)
    monkeypatch.setattr(LB, "_import", lambda d, g: True)

    def fake_editor(cmd, timeout, log_path=None):
        work = Path(cmd[cmd.index("--path") + 1])
        assert 'renderer/rendering_method="forward_plus"' in (work / "project.godot").read_text(encoding="utf-8")
        assert (work / LB.PLUGIN_DIR / "light_bake_plugin.gd").exists()
        (work / LB.RESULT).write_text(json.dumps({"ok": True, "users": 12}), encoding="utf-8")
        (work / "bake.tscn").write_text(
            '[ext_resource type="LightmapGIData" uid="uid://abc" path="res://bake.lmbake" id="1"]\n', encoding="utf-8")
        for f in ("bake.lmbake", "bake.exr", "bake.exr.import"):
            (work / f).write_text("x", encoding="utf-8")
        return 0, 3.0
    monkeypatch.setattr(LB, "_run", fake_editor)
    r = LB.bake(pkg, "godot.exe", log=lambda *a: None)
    assert r["ok"] is True, r
    assert all((pkg / f).exists() for f in LB.BAKE_FILES)
    assert "load('res://bake.tscn')" in (pkg / "mission.tscn").read_text(encoding="utf-8")
    assert 'uid="' not in (pkg / "bake.tscn").read_text(encoding="utf-8") and r["uids_stripped"] == 1
    assert r["rigs"] == {"static": 2, "live": 1, "cycling": 0}
    assert not (tmp_path / "LF_t.portable-godot.lightbake").exists()


def test_the_bake_scene_holds_the_presentation_and_one_lightmap():
    t = LB.bake_scene_text()
    assert 'path="res://presentation/lux.applied.tscn"' in t
    assert t.count('type="LightmapGI"') == 1 and "quality = 0" in t and "bounces = 2" in t


def test_the_bake_takes_the_sky():
    """FAILS ON 0.163.1. The walker, 2026-10-09: "yes bake the sky in". 0.131.0
    to 0.163.1 baked with `environment_mode = 0`, no sky, and a lightmapped
    surface takes no ambient at run time, so shade on a clear afternoon came
    out near black (`docs/findings/lighting_spec_vs_lux/` at the factory
    root). 1 is the scene's environment. One literal line: the root's
    `tools/lux_rebake.py --bake-environment` rewrites it by pattern."""
    t = LB.bake_scene_text()
    assert t.count("environment_mode = ") == 1, t
    assert "environment_mode = 1\n" in t, t


def test_the_export_profile_does_not_bake_unless_asked():
    from packages.exporting.export import ExportProfile
    assert ExportProfile().bake_lights is False


def test_the_export_command_bakes_unless_told_not_to():
    """0.144.0: on at the command line, off in the profile (above)."""
    from apps.cli.main import build_parser
    parse = build_parser().parse_args
    assert parse(["export", "m"]).bake_lights is True
    # the spelling every cold run before 0.144.0 used still parses
    assert parse(["export", "m", "--bake-lights"]).bake_lights is True
    assert parse(["export", "m", "--no-bake-lights"]).bake_lights is False


def test_a_failed_bake_leaves_a_package_the_closure_scan_accepts(tmp_path):
    """0.144.0 made the bake the export's default, and the suite's first
    failed bake put the package's absolute path into the report's `reason`;
    the closure scan then refused an export the bake had already abandoned
    cleanly. The report is LF's log of a build step and is exempt, as
    `glb_reference_scan.json` is."""
    from packages.exporting.closure import scan_closure
    pkg = tmp_path / "LF_t.portable-godot"
    (pkg / "presentation").mkdir(parents=True)
    (pkg / LB.PRESENTATION).write_text("[gd_scene format=3]\n", encoding="utf-8")
    (pkg / "mission.tscn").write_text("[gd_scene format=3]\n", encoding="utf-8")
    r = LB.bake(pkg, "godot.exe", log=lambda *a: None)
    # the shape that tripped the scan: a failure whose reason names the package
    assert r["ok"] is False and str(pkg) in r["reason"], r
    issues = [i for i in scan_closure(pkg).issues if i.startswith(LB.REPORT)]
    assert issues == [], issues


def test_the_bake_lays_the_rooms_floor_and_frees_it_before_it_saves():
    """THE ROOMS' FLOOR (0.151.0). Lux >= 0.68.0 lays bake-only fills over the
    level's room probes (`LuxLightLoader.add_bake_fills`): the lightmap must
    keep their light and the shipped scene must not keep them. The plugin
    runs only inside the editor, so its order is read off its source: laid
    before the button is pressed, freed before the scene is saved, counted in
    the result."""
    src = LB.PLUGIN_SCRIPT.read_text(encoding="utf-8")
    lay = src.find("_fill = _lay_room_fill(")
    press = src.find("b.pressed.emit()")
    # by ORDER, not adjacency (0.261.0 gives the rows' range back between the
    # two): freed after Bake is pressed and before the scene is saved
    free = src.find("\t\t\t_free_room_fill()\n")
    save = src.find("EditorInterface.save_scene()")
    assert '"add_bake_fills"' in src, "the plugin never asks Lux for the rooms' floor"
    assert 0 <= lay < press, "the floor must be laid before Bake is pressed"
    assert press < free < save, "the floor must be freed after the bake and before the save"
    assert '"room_fills": _fill_count' in src, "the result must say how many fills the bake held"


def test_a_bake_reports_its_room_fills(tmp_path, monkeypatch):
    """What the plugin counted reaches `light_bake.json` and the export log."""
    pkg = _package(tmp_path)
    monkeypatch.setattr(LB, "_import", lambda d, g: True)

    def fake_editor(cmd, timeout, log_path=None):
        work = Path(cmd[cmd.index("--path") + 1])
        (work / LB.RESULT).write_text(json.dumps({"ok": True, "users": 12, "room_fills": 30}), encoding="utf-8")
        (work / "bake.tscn").write_text("[gd_scene format=3]\n", encoding="utf-8")
        for f in ("bake.lmbake", "bake.exr", "bake.exr.import"):
            (work / f).write_text("x", encoding="utf-8")
        return 0, 3.0
    monkeypatch.setattr(LB, "_run", fake_editor)
    said = []
    r = LB.bake(pkg, "godot.exe", log=said.append)
    assert r["ok"] is True, r
    assert r["room_fills"] == 30
    assert json.loads((pkg / LB.REPORT).read_text(encoding="utf-8"))["room_fills"] == 30
    assert any("30 room fill(s)" in s for s in said), said


def test_the_bake_lends_the_rows_their_bake_range_and_gives_it_back_before_it_saves():
    """THE ROWS' BAKE RANGE (0.261.0). Lux >= 0.80.0 lets a static lamp bake
    further than it claims live (`stretch_bake_ranges`, `restore_bake_ranges`):
    lent before Bake is pressed, given back before the save, counted in the
    result. Read off the plugin's source, as the floor is."""
    src = LB.PLUGIN_SCRIPT.read_text(encoding="utf-8")
    lend = src.find("_lend_bake_ranges(EditorInterface.get_edited_scene_root())")
    press = src.find("b.pressed.emit()")
    back = src.find("\t\t\t_give_back_bake_ranges()\n")
    save = src.find("EditorInterface.save_scene()")
    assert '"stretch_bake_ranges"' in src and '"restore_bake_ranges"' in src
    assert 0 <= lend < press, "the range must be lent before Bake is pressed"
    assert press < back < save, "the range must be given back after the bake and before the save"
    assert '"bake_ranges_lent": _lent_count' in src, "the result must say how many lamps were lent one"


def test_a_bake_reports_the_lamps_lent_a_range(tmp_path, monkeypatch):
    """What the plugin counted reaches `light_bake.json` and the export log; a
    Lux with no such call (-1) says nothing about it."""
    for lent, line in ((50, "50 lamp(s) lent a bake range"), (-1, None)):
        pkg = _package(tmp_path / str(lent))
        monkeypatch.setattr(LB, "_import", lambda d, g: True)

        def fake_editor(cmd, timeout, log_path=None, lent=lent):
            work = Path(cmd[cmd.index("--path") + 1])
            (work / LB.RESULT).write_text(json.dumps({"ok": True, "users": 12, "room_fills": 30,
                                                      "bake_ranges_lent": lent}), encoding="utf-8")
            (work / "bake.tscn").write_text("[gd_scene format=3]\n", encoding="utf-8")
            for f in ("bake.lmbake", "bake.exr", "bake.exr.import"):
                (work / f).write_text("x", encoding="utf-8")
            return 0, 3.0
        monkeypatch.setattr(LB, "_run", fake_editor)
        said = []
        r = LB.bake(pkg, "godot.exe", log=said.append)
        assert r["ok"] is True and r["bake_ranges_lent"] == lent, r
        assert json.loads((pkg / LB.REPORT).read_text(encoding="utf-8"))["bake_ranges_lent"] == lent
        if line:
            assert any(line in s for s in said), said
        else:
            assert not any("lent a bake range" in s for s in said), said



_OBJ_SIDECAR = """[remap]

importer="wavefront_obj"
importer_version=1
type="Mesh"
path="res://.godot/imported/site_marks.obj-0000.mesh"

[deps]

source_file="res://site_marks.obj"

[params]

generate_tangents=true
generate_lods=true
generate_shadow_mesh=true
generate_lightmap_uv2=false
generate_lightmap_uv2_texel_size=0.2
scale_mesh=Vector3(1, 1, 1)
offset_mesh=Vector3(0, 0, 0)
force_disable_mesh_compression=false
"""


def test_the_paints_obj_meshes_are_asked_for_a_lightmap_uv(tmp_path):
    """0.177.1: Lot 0.114.0 ships the road paint as an OBJ a colour; the wavefront
    importer's sidecar (read off the engine) says `generate_lightmap_uv2=false`
    until asked, and an unasked mesh is not lightmapped."""
    _glb(tmp_path / "shell.glb", uv2=False)
    (tmp_path / "shell.glb.import").write_text(_SIDECAR, encoding="utf-8")
    (tmp_path / "site_marks.obj").write_text("o marks\nv 0 0 0\n", encoding="utf-8")
    (tmp_path / "site_marks.obj.import").write_text(_OBJ_SIDECAR, encoding="utf-8")
    got = LB.mark_imports(tmp_path)
    assert got["baked"] == ["shell.glb", "site_marks.obj"] and got["unreadable"] == []
    text = (tmp_path / "site_marks.obj.import").read_text(encoding="utf-8")
    assert "generate_lightmap_uv2=true" in text and "generate_lightmap_uv2=false" not in text
    assert "generate_lightmap_uv2_texel_size=0.2" in text       # the texel size is left alone
    # asked twice, the sidecar is left as it is
    again = LB.mark_imports(tmp_path)
    assert again["baked"] == got["baked"]


def test_an_obj_sidecar_without_the_line_is_said_not_guessed(tmp_path):
    (tmp_path / "odd.obj").write_text("o odd\n", encoding="utf-8")
    (tmp_path / "odd.obj.import").write_text("[remap]\nimporter=\"wavefront_obj\"\n", encoding="utf-8")
    got = LB.mark_imports(tmp_path)
    assert got["baked"] == [] and got["unreadable"] == ["odd.obj"]


def test_the_editor_stays_awake_and_the_scene_is_asked_for_until_it_opens():
    """0.178.5, cold run 9242: `bake.tscn did not open` after 83.7 s, and 371.8 s on a re-run.
    An unfocused editor sleeps between frames, and the open was asked once and waited on in
    frames. The same plugin with these three changes opened 9242's scene in 21 s and baked it."""
    src = LB.PLUGIN_SCRIPT.read_text(encoding="utf-8")
    assert src.count("OS.low_processor_usage_mode = false") == 2, "held off at start and every frame"
    assert "_frames > 3000" not in src, "the open's wait is a clock, not a frame count"
    assert "if waited > OPEN_LIMIT_MS:" in src
    assert src.count("EditorInterface.open_scene_from_path(SCENE)") == 2, "asked, then asked again"
    assert src.count("get_resource_filesystem().is_scanning()") == 2


def test_the_editor_s_output_is_kept_beside_the_package(tmp_path, monkeypatch):
    """0.178.5: 9242's bake sent the editor's output to DEVNULL, so the failure said nothing."""
    log = tmp_path / "out.log"
    code, _took = LB._run([sys.executable, "-c", "print('BAKE hello from the editor')"], 60, log_path=log)
    assert code == 0
    assert "BAKE hello from the editor" in log.read_text(encoding="utf-8", errors="replace")
    pkg = _package(tmp_path)
    monkeypatch.setattr(LB, "_import", lambda d, g: True)
    seen = []

    def fake_editor(cmd, timeout, log_path=None):
        seen.append(log_path)
        return None, float(timeout)
    monkeypatch.setattr(LB, "_run", fake_editor)
    r = LB.bake(pkg, "godot.exe", log=lambda *a: None)
    # 0.178.6: a failed bake is tried once more, and each try keeps its own log
    assert seen == [tmp_path / "LF_t.portable-godot.lightbake.log",
                    tmp_path / "LF_t.portable-godot.lightbake.2.log"]
    assert r["editor_log"] == str(seen[-1])
    assert not any(str(s).startswith(str(pkg) + os.sep) for s in seen), "no log is shipped"


def _baked_editor(work, users=12):
    (work / LB.RESULT).write_text(json.dumps({"ok": True, "users": users}), encoding="utf-8")
    (work / "bake.tscn").write_text("[gd_scene format=3]\n", encoding="utf-8")
    for f in ("bake.lmbake", "bake.exr", "bake.exr.import"):
        (work / f).write_text("x", encoding="utf-8")


def test_a_bake_that_fails_once_is_tried_once_more_on_a_fresh_copy(tmp_path, monkeypatch):
    """0.178.6, cold run 9243: the bake read its lightmap image back empty and raised a dialog;
    the same package baked on the next try."""
    pkg = _package(tmp_path)
    monkeypatch.setattr(LB, "_import", lambda d, g: True)
    calls = []

    def flaky_editor(cmd, timeout, log_path=None):
        work = Path(cmd[cmd.index("--path") + 1])
        calls.append(log_path)
        assert not (work / LB.RESULT).exists(), "each try starts from a fresh copy"
        if len(calls) == 1:
            (work / LB.RESULT).write_text(json.dumps({"ok": False, "error": "the bake raised a dialog"}),
                                          encoding="utf-8")
        else:
            _baked_editor(work)
        return 0, 3.0
    monkeypatch.setattr(LB, "_run", flaky_editor)
    said = []
    r = LB.bake(pkg, "godot.exe", log=said.append)
    assert r["ok"] is True, r
    assert [a["attempt"] for a in r["attempts"]] == [1, 2]
    assert r["attempts"][0]["result"]["error"] == "the bake raised a dialog"
    assert any("baked on attempt 2 of 2" in s for s in said), said
    assert all((pkg / f).exists() for f in LB.BAKE_FILES)


def test_a_bake_that_works_first_time_is_not_tried_again(tmp_path, monkeypatch):
    pkg = _package(tmp_path)
    monkeypatch.setattr(LB, "_import", lambda d, g: True)
    calls = []

    def good_editor(cmd, timeout, log_path=None):
        calls.append(log_path)
        _baked_editor(Path(cmd[cmd.index("--path") + 1]))
        return 0, 3.0
    monkeypatch.setattr(LB, "_run", good_editor)
    r = LB.bake(pkg, "godot.exe", log=lambda *a: None)
    assert r["ok"] is True and len(calls) == 1 and len(r["attempts"]) == 1
