"""The Empties, merged one mesh a side per material (0.143.0, roadmap 182).

The Godot half runs only inside Godot; it is exercised by a cold run. This
is the Python half: which scenes it asks for, what it refuses to believe,
and where in the export it runs. A stub Godot writes the report, as
`test_perf_stations_run.py` does it, so `merge` goes through its own reading
of a report rather than around it.
"""
import json
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from packages.exporting import merge_empties as M  # noqa: E402

_REPO = Path(__file__).resolve().parents[2]

SITE = '''[gd_scene load_steps=4 format=3]

[ext_resource type="PackedScene" path="lot/gs_empty_rowhome_d/site.tscn" id="b4"]
[ext_resource type="PackedScene" path="lot/gs_empty_rowhome_h/site.tscn" id="b5"]
[ext_resource type="PackedScene" path="lot/gas_station_a01/site.tscn" id="b0"]

[node name="Site" type="Node3D"]

[node name="b0" parent="." instance=ExtResource("b0")]

[node name="blocker_0" parent="." instance=ExtResource("b4")]

[node name="blocker_1" parent="." instance=ExtResource("b5")]

[node name="blocker_2" parent="." instance=ExtResource("b4")]
'''
ASKED = ["res://lot/gs_empty_rowhome_d/site.tscn", "res://lot/gs_empty_rowhome_h/site.tscn"]


def _pkg(tmp_path, site=SITE):
    p = tmp_path / "pkg"
    p.mkdir()
    (p / "site.tscn").write_text(site, encoding="utf-8")
    (p / ".godot").mkdir()
    return p


def _row(scene, **kw):
    r = {"scene": scene, "meshes_in": 95, "surfaces_in": 161, "merged": 13, "unwrapped": 13,
         "colliders": 86, "doors_dropped": 2, "error": None}
    r.update(kw)
    return r


def _report(rows, **kw):
    r = {"schema": M.SCHEMA, "ok": True, "error": None, "scenes": rows}
    r.update(kw)
    return r


def _stub_godot(tmp_path, pkg, doc):
    """A stand-in for Godot that writes `doc` as the merge's report."""
    src = tmp_path / "report_src.json"
    src.write_text(json.dumps(doc), encoding="utf-8")
    dst = pkg / M.REPORT_NAME
    if sys.platform == "win32":
        s = tmp_path / "godot.cmd"
        body = '@echo off\r\ncopy /y "{0}" "{1}" >nul\r\nexit /b 0\r\n'.format(src, dst)
    else:
        s = tmp_path / "godot.sh"
        body = "#!/bin/sh\ncp '{0}' '{1}'\nexit 0\n".format(src, dst)
    s.write_text(body, encoding="utf-8")
    if sys.platform != "win32":
        s.chmod(0o755)
    return s


def test_the_empties_are_the_scenes_the_blockers_instance(tmp_path):
    """FAILS ON 0.142.0: nothing merged anything."""
    assert M.empty_scenes(_pkg(tmp_path)) == ASKED


def test_a_blocker_that_is_not_a_lot_scene_refuses(tmp_path):
    odd = SITE.replace('path="lot/gs_empty_rowhome_h/site.tscn"', 'path="props/crate.tscn"')
    with pytest.raises(M.MergeError):
        M.empty_scenes(_pkg(tmp_path, odd))


def test_a_site_without_empties_asks_for_nothing_and_runs_nothing(tmp_path):
    site = "\n".join(ln for ln in SITE.splitlines() if "blocker_" not in ln)
    rep = M.merge(_pkg(tmp_path, site), None)
    assert rep["ok"] and rep["scenes"] == []


def test_no_godot_with_empties_refuses(tmp_path):
    with pytest.raises(M.MergeError):
        M.merge(_pkg(tmp_path), None)


def test_a_finished_merge_is_believed(tmp_path):
    pkg = _pkg(tmp_path)
    rep = M.merge(pkg, _stub_godot(tmp_path, pkg, _report([_row(s) for s in ASKED])))
    assert [r["scene"] for r in rep["scenes"]] == ASKED
    assert not (pkg / M.MERGE_SCRIPT.name).exists()          # the bundled script is gone


@pytest.mark.parametrize("doc", [
    _report([_row(ASKED[0])]),                                   # a scene missing
    _report([_row(s) for s in ASKED], schema="something.else"),  # not this report
    _report([_row(s) for s in ASKED], ok=False, error="boom"),   # said it failed
    _report([_row(ASKED[0]), _row(ASKED[1], unwrapped=12)]),     # a mesh with no lightmap UV
    _report([_row(ASKED[0]), _row(ASKED[1], merged=0)]),         # merged nothing
    _report([_row(ASKED[0]), _row(ASKED[1], colliders=0)]),      # lost the collision
    _report([_row(ASKED[0]), _row(ASKED[1], error="cannot load")]),
    _report([_row(ASKED[0]), {"scene": ASKED[1]}]),              # a row of nothing
])
def test_an_unfinished_or_unrecognised_merge_refuses(tmp_path, doc):
    pkg = _pkg(tmp_path)
    with pytest.raises(M.MergeError):
        M.merge(pkg, _stub_godot(tmp_path, pkg, doc))


def test_it_runs_after_the_occluder_bake_and_before_the_light_bake():
    """The occluders are measured on the modules, world-space, and stay true
    of the merged geometry; the light bake's users are node paths, so the
    merged meshes must exist before it."""
    src = (_REPO / "packages" / "exporting" / "export.py").read_text(encoding="utf-8")
    occ = src.index("occ = emit(export_dir, godot_executable)")
    mrg = src.index("_merge_empties(export_dir, godot_executable)")
    bake = src.index("_bake_lights(export_dir, godot_executable)")
    assert occ < mrg < bake


def test_the_godot_half_ships_with_the_python_half():
    assert M.MERGE_SCRIPT.is_file()
    text = M.MERGE_SCRIPT.read_text(encoding="utf-8")
    assert re.search(r'^const SCHEMA := "' + re.escape(M.SCHEMA) + '"$', text, re.M)
