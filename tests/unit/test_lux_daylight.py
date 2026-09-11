"""The window anchors reach the Lux driver (roadmap 96).

`LuxAdapter.fingerprint_inputs` hashed `lights_json` from the day it was
written and `plan_commands` never passed it -- a cache input to a command that
could not read it. Now the command takes `--lights`, the driver calls
`LuxLightLoader.bake_daylight` with it, and the quality record says how many
window anchors the manifest carried and how many became light.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from adapters.lux import LuxAdapter  # noqa: E402

DRIVER = ROOT / "assets" / "godot" / "run_lux_apply.gd"


def _ctx(tmp_path):
    return {"work_dir": str(tmp_path / "work"), "repository": str(tmp_path),
            "godot_executable": "godot"}


def test_the_manifest_reaches_the_command_when_given(tmp_path):
    lights = tmp_path / "site.site.lights.json"
    lights.write_text('{"anchors": []}', encoding="utf-8")
    cmds = LuxAdapter().plan_commands(
        {"preset": "Blue Hour", "lights_json": str(lights)}, _ctx(tmp_path))
    args = cmds[0].arguments
    assert "--lights" in args and args[args.index("--lights") + 1] == str(lights)


def test_no_manifest_means_no_flag(tmp_path):
    cmds = LuxAdapter().plan_commands({"preset": "Blue Hour"}, _ctx(tmp_path))
    assert "--lights" not in cmds[0].arguments


def test_the_manifest_is_in_the_fingerprint_it_always_claimed(tmp_path):
    lights = tmp_path / "site.site.lights.json"
    lights.write_text('{"anchors": []}', encoding="utf-8")
    a = LuxAdapter().fingerprint_inputs({"preset": "x", "lights_json": str(lights)}, _ctx(tmp_path))
    lights.write_text('{"anchors": [{"type": "window"}]}', encoding="utf-8")
    b = LuxAdapter().fingerprint_inputs({"preset": "x", "lights_json": str(lights)}, _ctx(tmp_path))
    assert a != b


def test_the_driver_bakes_daylight_and_reports_it():
    src = DRIVER.read_text(encoding="utf-8")
    assert "bake_daylight" in src
    assert '"lights"' in src or "args.get(\"lights\"" in src
    for key in ("daylight_lights", "daylight_anchors_in_manifest", "LUX_NO_DAYLIGHT"):
        assert key in src, key
    # Ownership is load-bearing: pack() drops unowned nodes silently.
    assert 'NodePath("LuxDaylight")' in src
