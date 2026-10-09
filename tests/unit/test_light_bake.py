"""The light bake (0.131.0): what it marks, what it ships, and that a bake
that fails ships the package unbaked."""
from __future__ import annotations

import json
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
    assert got == {"baked": ["shell.glb"], "dynamic": ["grill.glb"], "spawned": [],
                   "spawned_unmatched": [], "unreadable": ["odd.glb"]}
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
    monkeypatch.setattr(LB, "_run", lambda cmd, timeout: (None, float(timeout)))
    r = LB.bake(pkg, "godot.exe", log=lambda *a: None)
    assert r["ok"] is False and "did not finish" in r["reason"]
    assert (pkg / "presentation" / "lux.applied.tscn").read_bytes() == pres
    assert (pkg / "mission.tscn").read_bytes() == entry
    assert not any((pkg / f).exists() for f in LB.BAKE_FILES)
    assert not (tmp_path / "LF_t.portable-godot.lightbake").exists()


def test_a_bake_that_works_ships_the_lightmap_and_points_the_entry_at_it(tmp_path, monkeypatch):
    pkg = _package(tmp_path)
    monkeypatch.setattr(LB, "_import", lambda d, g: True)

    def fake_editor(cmd, timeout):
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
    free = src.find("_free_room_fill()\n\t\t\t_busy = true\n\t\t\tEditorInterface.save_scene()")
    assert '"add_bake_fills"' in src, "the plugin never asks Lux for the rooms' floor"
    assert 0 <= lay < press, "the floor must be laid before Bake is pressed"
    assert free > press, "the floor must be freed after the bake and before the save"
    assert '"room_fills": _fill_count' in src, "the result must say how many fills the bake held"


def test_a_bake_reports_its_room_fills(tmp_path, monkeypatch):
    """What the plugin counted reaches `light_bake.json` and the export log."""
    pkg = _package(tmp_path)
    monkeypatch.setattr(LB, "_import", lambda d, g: True)

    def fake_editor(cmd, timeout):
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
