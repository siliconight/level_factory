"""Every package carries the scout window, and the walk copy calls it (0.235.0, the factory's roadmap 295).

The walker: "Goal is we have the ability to open up a 'window' at runtime that shows the various buildings and their
3d schematics" -- "make sure the window can be called by something on the gameplay layer (seam is clear and visible)".
The export copies `assets/godot/scout/` into the package's `scout/` once `buildings.json` is written; the window's
script states its seam at its head and in the README beside it, and the walk copy's debug overlay is a caller of it.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from packages.exporting import scout_window as SW

LF = Path(__file__).resolve().parents[2]
SEAM = ("open", "close", "is_open", "buildings", "get_screen_texture", "select", "set_points", "turn",
        "set_spread")
SIGNALS = ("opened", "closed", "building_selected")


def test_the_window_ships_with_the_index_and_says_why_not_without_it(tmp_path):
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    out = SW.install(pkg)
    assert out == {"installed": [], "why_not": "no buildings.json to list", "models": 0}
    assert not (pkg / "scout").exists()
    (pkg / "buildings.json").write_text(json.dumps({"buildings": [
        {"node": "b0", "id": "deli_a03", "kind": "building", "scout_model": "res://lot/deli_a03/drawings/scout.glb"},
        {"node": "b1", "id": "deli_a03", "kind": "building", "scout_model": "res://lot/deli_a03/drawings/scout.glb"},
        {"node": "blocker_0", "id": "gs_empty_rowhome_a", "kind": "empty", "scout_model": None}]}), encoding="utf-8")
    out = SW.install(pkg)
    assert out == {"installed": ["scout/scout_window.gd", "scout/README.md"], "why_not": None, "models": 1}
    for f in SW.FILES:
        assert (pkg / "scout" / f).read_bytes() == (SW.SOURCE / f).read_bytes()


def test_the_seam_is_what_the_script_and_its_readme_say_it_is():
    """Every call the README shows is a function of the script, every signal it names is declared, and the script
    names its class -- the seam the walker asked to be clear and visible, held so a rename cannot drift from it."""
    gd = (SW.SOURCE / "scout_window.gd").read_text(encoding="utf-8")
    readme = (SW.SOURCE / "README.md").read_text(encoding="utf-8")
    assert re.search(r"^class_name LFScoutWindow$", gd, re.M)
    for f in SEAM:
        assert re.search(r"^func %s\(" % f, gd, re.M), f
        assert "scout.%s(" % f in readme, f
    for s in SIGNALS:
        assert re.search(r"^signal %s\b" % s, gd, re.M), s
        assert s in readme, s
    # it reads what the export writes, by those names
    assert '"buildings.json"' in gd and '"scout_model"' in gd


def test_the_walk_copy_calls_it_on_f6_debug_builds_only():
    """The stand-in for the gameplay layer: the overlay that rides only in walk copies, in debug builds only, opens
    the window by its path, as a caller would."""
    ov = (LF / "assets" / "godot" / "debug_overlay.gd").read_text(encoding="utf-8")
    assert "KEY_F6" in ov and 'res://scout/scout_window.gd' in ov and '"open", true' in ov
    assert "OS.is_debug_build()" in ov
