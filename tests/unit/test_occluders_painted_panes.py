"""A window with a painted pane occludes (0.274.0).

`bake_occluders.gd` left every `window_` module porous: "the opening IS the module". A PAINTED pane is not an opening:
Zoo paints it over the sealed, full-thickness collider Deli Counter cuts every window with, and names it `_p<state>`
(`zoo_keeper.core.kit`, 1.64.0) -- every Empty's windows, and since Deli Counter 0.295.0 a storey nobody reaches. Left
porous, the slice's bank's 32 painted upper windows opened the culler: from the camera socket on that storey, 259 ->
1,224 draws (the factory's `docs/findings/slice_look/`, slice 22).

THE GODOT HALF RUNS HERE FOR REAL: `classify` is called on real module stems from the slice's package. Skipped where no
Godot is installed. FAILS ON 0.273.0: a painted window classifies `porous`.

Run:  python -m pytest tests/unit/test_occluders_painted_panes.py -q
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "assets" / "godot" / "bake_occluders.gd"

#: real stems from the slice's package, and what each must classify as
STEMS = {
    "window_delco_1997_01_w160_plit_blind_cool_o92c863": "solid",        # the bank's painted upper window
    "window_delco_1997_01_w95_mbrick_orange_plit_blind_cool_o173e47": "solid",  # an Empty's
    "window_delco_1997_01_w95_mbrick_orange_pdark_o173e47": "solid",
    "window_delco_1997_01_w95_mbrick_orange_pboarded_o173e47": "solid",
    "window_delco_1997_01_w300_pshop_deli_o173e47": "solid",
    "window_delco_1997_01_w160_o92c863": "porous",                       # a clear window: the opening is the module
    "window_delco_1997_01_w240_mglass_o92c863": "glass",
    "doorway_delco_1997_01_w180_plit_o92c863": "porous",                 # only a window's pane is painted shut
    "wall_delco_1997_01_w300": "solid",
}

PROBE = """extends SceneTree
func _initialize() -> void:
	var b: Object = load("res://bake_occluders.gd").new()
	var out := {}
	for s in %s:
		out[s] = b.call("classify", s)
	print("RESULT " + JSON.stringify(out))
	quit(0)
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


@pytest.mark.skipif(_godot() is None, reason="no Godot binary; this test calls classify")
def test_a_painted_window_is_solid_and_a_clear_one_stays_porous(tmp_path):
    proj = tmp_path / "p"
    proj.mkdir()
    (proj / "project.godot").write_text('config_version=5\n[application]\nconfig/name="occ"\n', encoding="utf-8")
    shutil.copyfile(SCRIPT, proj / "bake_occluders.gd")
    (proj / "probe.gd").write_text(PROBE % json.dumps(sorted(STEMS)), encoding="utf-8")
    r = subprocess.run([_godot(), "--headless", "--path", str(proj), "--script", "res://probe.gd"],
                       capture_output=True, text=True, timeout=180)
    line = next((ln for ln in r.stdout.splitlines() if ln.startswith("RESULT ")), None)
    assert line, r.stdout + r.stderr
    got = json.loads(line[len("RESULT "):])
    assert got == STEMS
