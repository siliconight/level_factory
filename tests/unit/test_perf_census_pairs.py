"""The light census counts what the renderer pairs, beside what reaches (0.159.0).

`tools/perf_stations.gd`'s census counted, per mesh, every positional light
whose range reaches the mesh's box. Since the light bake (0.131.0) most Lux
rigs are BAKE_STATIC, and Godot 4.7 never pairs a BAKE_STATIC light with a
mesh that has a lightmap -- `servers/rendering/renderer_scene_cull.cpp`,
`_scene_cull`, where a mesh's lights are rebuilt:

    if ((RSG::light_storage->light_get_bake_mode(E->base) == RSE::LIGHT_BAKE_STATIC)
            && idata.instance->lightmap) {
        continue;

The same block skips a light whose cull mask misses the mesh's layers. So the
count stopped being what the cap is spent on: cold run 9204's package read
"33 of 3,954 meshes over 8, worst 31" with its club's stage lamps baked and
with them live (`docs/findings/club_stage_live_price/` at the factory root).

THE RULE RUNS HERE FOR REAL. A headless Godot builds two meshes, a LightmapGI
whose LightmapGIData lists one of them -- no bake is needed, the user list is
what gives a mesh its lightmap -- and four lights, each of which only one
rule can remove, then calls the probe's own `_light_census`. Skipped where no
Godot is installed. The runner's half is driven through the stub Godot
`test_perf_stations_run.py` built.

Run:  python -m pytest tests/unit/test_perf_census_pairs.py -q
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tests.unit.test_perf_stations_run import (  # noqa: E402
    EXIT_OK, ROW, RUNNER, _pkg, _run, _stub_godot)

PROBE = RUNNER.with_name("perf_stations.gd")
MARK_BEGIN, MARK_END = "<<<CENSUS", "CENSUS>>>"

#: Two meshes, one a lightmap user, and four lights that each reach both:
#:   Baked     BAKE_STATIC      -- the lightmap rule removes it from A only
#:   Live      BAKE_DYNAMIC     -- every rule keeps it
#:   LayerOne  cull mask 1      -- the cull rule removes it from B (layer 2)
#:   Hidden    not visible      -- not in the scenario's pairing at all
SCENE = """extends SceneTree


func _initialize() -> void:
\t# A WATCHDOG, because a census that errors kills this coroutine before it
\t# can quit: on 0.158.0, where `_light_census` is not static, the call
\t# failed and the process sat until the test's own timeout.
\tcreate_timer(20.0).timeout.connect(_watchdog)
\t_run()


func _watchdog() -> void:
\tprint("CENSUS_WATCHDOG")
\tquit(3)


## A frame before counting, as the harness's own `_run` waits: during
## `_initialize` nothing added to the root is inside the tree yet, so every
## global transform reads as the origin and every path as "".
func _run() -> void:
\tvar ps = load("res://perf_stations.gd")
\tvar site := Node3D.new()
\tsite.name = "Site"
\troot.add_child(site)
\tvar a := MeshInstance3D.new()
\ta.name = "A"
\ta.mesh = BoxMesh.new()
\ta.layers = 1
\tsite.add_child(a)
\tvar b := MeshInstance3D.new()
\tb.name = "B"
\tb.mesh = BoxMesh.new()
\tb.layers = 2
\tb.position = Vector3(3.0, 0.0, 0.0)
\tsite.add_child(b)
\tvar data := LightmapGIData.new()
\tdata.add_user(NodePath("../A"), Rect2(0.0, 0.0, 1.0, 1.0), 0, -1)
\tvar bake := LightmapGI.new()
\tbake.name = "Bake"
\tbake.light_data = data
\tsite.add_child(bake)
\t_lamp(site, "Baked", Light3D.BAKE_STATIC, 0xFFFFFFFF, true)
\t_lamp(site, "Live", Light3D.BAKE_DYNAMIC, 0xFFFFFFFF, true)
\t_lamp(site, "LayerOne", Light3D.BAKE_DYNAMIC, 1, true)
\t_lamp(site, "Hidden", Light3D.BAKE_DYNAMIC, 0xFFFFFFFF, false)
\tawait process_frame
\tvar nodes: Array = [site]
\tfor c in site.get_children():
\t\tnodes.append(c)
\tvar census: Dictionary = ps.call("_light_census", nodes, 0)
\tprint("<<<CENSUS")
\tprint(JSON.stringify(census))
\tprint("CENSUS>>>")
\tquit()


func _lamp(parent: Node3D, lamp: String, mode: int, mask: int, shown: bool) -> void:
\tvar l := OmniLight3D.new()
\tl.name = lamp
\tl.omni_range = 20.0
\tl.light_bake_mode = mode
\tl.light_cull_mask = mask
\tl.visible = shown
\tl.position = Vector3(1.5, 2.0, 0.0)
\tparent.add_child(l)
"""


def _godot() -> str | None:
    for env in ("LF_GODOT", "DC_GODOT", "LOT_GODOT"):
        p = os.environ.get(env)
        if p and Path(p).is_file():
            return p
    usual = Path("C:/Godot/4.7/Godot_v4.7-stable_win64_console.exe")
    if usual.is_file():
        return str(usual)
    return shutil.which("godot")


godot_required = pytest.mark.skipif(
    _godot() is None, reason="no Godot binary; this test runs the probe's census")


def _census(tmp_path: Path) -> dict:
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "project.godot").write_text('config_version=5\n\n[application]\n\nconfig/name="census"\n',
                                        encoding="utf-8")
    (proj / "perf_stations.gd").write_bytes(PROBE.read_bytes())
    (proj / "census_scene.gd").write_text(SCENE, encoding="utf-8")
    out = subprocess.run([_godot(), "--headless", "--path", str(proj), "--script", "res://census_scene.gd"],
                         capture_output=True, text=True, timeout=90)
    log = out.stdout + out.stderr
    # An unrecognised shape FAILS: no block means the census never ran, which
    # is not a census that counted nothing; and a node outside the tree reads
    # its path as "" and its transform as the origin, which is not a scene.
    assert MARK_BEGIN in log and MARK_END in log, log
    assert "is_inside_tree" not in log, log
    return json.loads(log.split(MARK_BEGIN, 1)[1].split(MARK_END, 1)[0])


def _by_mesh(rows: list) -> dict:
    return {str(r["mesh"]).rsplit("/", 1)[-1]: r for r in rows}


@godot_required
def test_the_reach_count_is_unchanged(tmp_path):
    """Every light reaches both meshes, hidden or masked or baked: the
    top-level fields keep the meaning every older report gave them."""
    c = _census(tmp_path)
    assert c["basis"] == "reach"
    rows = _by_mesh(c["over_list"])
    assert rows["A"]["lights"] == 4 and rows["B"]["lights"] == 4, c
    assert c["over_cap"] == 2 and c["worst"] == 4 and c["lights"] == 4
    assert c["pairs"] == 8 and c["histogram"] == {"4": 2}, c


@godot_required
def test_the_paired_count_applies_each_rule(tmp_path):
    """FAILS ON 0.158.0: the census carries no `paired` count.

    A: Baked is in A's lightmap and Hidden is not drawn, so Live and
       LayerOne -- 3 if the lightmap rule were missing, 3 if the visibility
       rule were.
    B: no lightmap, so Baked pairs; LayerOne's mask misses layer 2 and
       Hidden is not drawn -- 3 if the cull rule were missing."""
    c = _census(tmp_path)
    assert "paired" in c, "the census carries no paired count"
    p = c["paired"]
    assert p["basis"] == "paired"
    rows = _by_mesh(p["over_list"])
    assert rows["A"]["lights"] == 2, p
    assert rows["B"]["lights"] == 2, p
    assert rows["A"]["by_reach"] == 4 and rows["B"]["by_reach"] == 4
    assert p["lightmap_users"] == 1 and p["lights_static"] == 1
    # every pair, under the cap or over it: what a change below the cap moves
    assert p["pairs"] == 4 and p["histogram"] == {"2": 2}, p


PAIRED = {"basis": "paired", "over_cap": 1, "worst": 9, "worst_mesh": "Floor_3",
          "over_list": [{"mesh": "/root/Site/b0/Floor_3", "lights": 9, "by_reach": 23}],
          "over_list_truncated": False, "lightmap_users": 1500, "lights_static": 78}


def test_the_runner_prints_both_counts(tmp_path):
    """FAILS ON 0.158.0: the runner printed one count, and it was the reach."""
    pkg = _pkg(tmp_path)
    row = dict(ROW, light_census=dict(ROW["light_census"], basis="reach", over_cap=3, worst=23,
                                      over_list=[{"mesh": "/root/Site/b0/Floor_3", "lights": 23}],
                                      over_list_truncated=False, paired=PAIRED))
    doc = {"schema": "level_factory.perf_stations.v1", "complete": True, "rows": [row]}
    out = _run(pkg, "--godot", str(_stub_godot(tmp_path, pkg, doc)), "--draws", "2000", "--ms", "11")
    assert "by reach" in out.stdout, out.stdout
    assert "paired" in out.stdout and "23 by reach" in out.stdout, out.stdout


def test_an_older_report_says_it_has_no_paired_count(tmp_path):
    """A report from before 0.159.0 carries only the reach count; the runner
    says so rather than printing nothing, which would read as none over."""
    pkg = _pkg(tmp_path)
    doc = {"schema": "level_factory.perf_stations.v1", "complete": True, "rows": [ROW]}
    out = _run(pkg, "--godot", str(_stub_godot(tmp_path, pkg, doc)), "--draws", "2000", "--ms", "11")
    assert out.returncode == EXIT_OK
    assert "no paired count" in out.stdout, out.stdout
