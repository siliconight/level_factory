"""A brief that asks for rain gets the rain preset, the cache knows, and the
driver keeps the buildings dry.

`MissionBrief.weather` was read by nothing: `_preset_for` chose from
`time_of_day` alone, so the two briefs in examples/ that say "rain" and
"hurricane" shipped dry. Lux 0.35.0 gives Heavy Rain a rain profile; this pins
the three places Level Factory has to agree with it.

The driver half is a SOURCE-SHAPE test, for the reason
`test_lux_preset_readback.py` gives: unit CI has no headless Godot. The
hardware evidence is the walk-copy frames in the 0.83.0 changelog entry.

Run:  python -m pytest tests/unit/test_lux_rain.py
"""
import re
from pathlib import Path

import pytest

from adapters.lux import LuxAdapter
from apps.cli.commands import _preset_for
from packages.core.models import MissionBrief

DRIVER = (Path(__file__).resolve().parents[2]
          / "assets" / "godot" / "run_lux_apply.gd")
COMMANDS = (Path(__file__).resolve().parents[2]
            / "apps" / "cli" / "commands" / "__init__.py")


def _brief(**kw) -> MissionBrief:
    return MissionBrief(mission_id="m", display_name="m", **kw)


@pytest.mark.parametrize("weather", ["rain", "storm", "hurricane", "Rain",
                                     " HURRICANE "])
def test_wet_weather_gets_heavy_rain(weather):
    assert _preset_for(_brief(weather=weather)) == "Heavy Rain"


@pytest.mark.parametrize("tod", ["afternoon", "night", "evening", "morning", ""])
def test_rain_wins_over_time_of_day(tod):
    """Deliberate and recorded in `_preset_for`: Heavy Rain is an overcast
    day, so a night brief that asks for rain gets daylight rain."""
    assert _preset_for(_brief(weather="rain", time_of_day=tod)) == "Heavy Rain"


@pytest.mark.parametrize("tod,preset", [
    ("afternoon", "Delco Summer Afternoon"),
    ("night", "Blue Hour"),
    ("evening", "Blue Hour"),
    ("morning", "Gas Station Fluorescent"),
])
def test_clear_weather_keeps_the_time_of_day_choice(tod, preset):
    assert _preset_for(_brief(weather="clear", time_of_day=tod)) == preset


@pytest.mark.parametrize("weather", ["clear", "", "overcast", "fog", "snow"])
def test_other_weather_is_not_rain(weather):
    """Only water from the sky. An unrecognised word falls through to the
    time-of-day choice rather than guessing."""
    assert _preset_for(_brief(weather=weather)) == "Delco Summer Afternoon"


def test_the_default_brief_is_unchanged():
    assert _preset_for(_brief()) == "Delco Summer Afternoon"


def test_the_preset_name_moves_the_lux_fingerprint(tmp_path):
    """The cache must not serve a dry lux.applied.tscn to a rain brief. The
    preset NAME is the input that changes; nothing else about the job does."""
    scene = tmp_path / "site.tscn"
    scene.write_text("[gd_scene load_steps=1 format=3]\n", encoding="utf-8")
    base = {"composed_scene": str(scene)}
    dry = LuxAdapter().fingerprint_inputs({**base, "preset": "Delco Summer Afternoon"}, {})
    wet = LuxAdapter().fingerprint_inputs({**base, "preset": "Heavy Rain"}, {})
    assert dry != wet
    moved = [k for k in set(dry) | set(wet) if dry.get(k) != wet.get(k)]
    assert moved == ["preset"], moved


@pytest.fixture(scope="module")
def driver() -> str:
    assert DRIVER.is_file(), f"driver missing at {DRIVER}"
    return DRIVER.read_text(encoding="utf-8")


def test_the_driver_builds_the_colliders_from_lux(driver):
    assert "res://addons/lux/runtime/lux_rain_collision.gd" in driver
    assert ".build(scene, weather" in driver


def test_the_driver_owns_the_colliders_or_pack_drops_them(driver):
    """pack() silently drops unowned nodes -- the rule the fixture rigs and
    the daylight rigs already follow in the same file."""
    assert 'get_node_or_null(NodePath("LuxRainColliders"))' in driver
    assert "_own_recursive(rcontainer, scene)" in driver


def test_the_building_pattern_matches_the_ids_this_pipeline_writes(driver):
    """The driver finds buildings by `b<index>`; `_write_site_spec` is what
    writes those ids. If either side changes alone, rain falls indoors."""
    m = re.search(r'\.build\(scene, weather, "([^"]+)"', driver)
    assert m, "driver no longer passes a building pattern"
    pattern = m.group(1).replace("\\\\", "\\")
    src = COMMANDS.read_text(encoding="utf-8")
    assert '{"id": f"b{i}"' in src
    for i in (0, 1, 12):
        assert re.fullmatch(pattern, f"b{i}")
    for other in ("sign_b0", "blocker_0", "Ground", "b", "bx1"):
        assert not re.fullmatch(pattern, other), other


def test_uncontained_rain_is_a_finding_and_is_recorded(driver):
    assert "LUX_RAIN_NOT_CONTAINED" in driver
    for key in ('"rain_drops"', '"rain_colliders"', '"rain_msg"', '"rain_asked"'):
        assert key in driver, key
