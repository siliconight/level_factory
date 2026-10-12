"""The light bake's editor stops its clock and looks for the scene at once (0.192.0).

Lux's failing fixtures keep a clock in the bake's editor (`_fail_t += delta`) and dim their lenses
with their lamps; a lens's emission is baked, so every bake kept each failing lens at whatever
level it had when Bake was pressed, and two exports of one level shipped different lightmaps.
With the clock stopped from the plugin's start, cold run 9257's level baked byte for byte the same
`bake.exr`, `bake.lmbake` and `bake.exr.import` whether Bake was pressed 4.4 s earlier or not (the
factory's docs/findings/grader_speed/bake_phases_probe.py, --freeze-time). And the scene was open
at the plugin's first look in every bake, which it made at frame 240; it looks at frame 1. The
plugin runs only inside an editor, so what it does is read off its source.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from packages.exporting import light_bake as LB  # noqa: E402


def _src():
    return LB.PLUGIN_SCRIPT.read_text(encoding="utf-8")


def _code(src):
    """The script without its comment lines, which name the clock too."""
    return "\n".join(ln for ln in src.splitlines() if not ln.lstrip().startswith("#"))


def _func(src, name):
    body = src[src.index("func %s(" % name):]
    nxt = body.find("\nfunc ", 1)
    return body if nxt < 0 else body[:nxt]


def test_the_clock_is_stopped_as_the_plugin_starts():
    enter = _func(_src(), "_enter_tree")
    assert "Engine.time_scale = 0.0" in enter
    assert enter.index("Engine.time_scale = 0.0") < enter.index("set_process(true)"), \
        "stopped before the first frame the plugin counts, so before the scene is asked for"


def test_nothing_starts_the_clock_again():
    src = _src()
    assert _code(src).count("Engine.time_scale") == 1, "set once, to 0, and never back"


def test_the_open_is_looked_for_from_the_first_frame():
    src = _src()
    assert "const OPEN_FLOOR_FRAMES := 1\n" in src
    assert "if _frames < OPEN_FLOOR_FRAMES:" in src
    assert "if _frames < 240:" not in src


def test_an_open_that_has_not_landed_is_still_asked_again_and_bounded():
    src = _src()
    assert src.count("EditorInterface.open_scene_from_path(SCENE)") == 2
    assert "if waited > OPEN_LIMIT_MS:" in src
