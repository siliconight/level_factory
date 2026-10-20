"""Every one of the walker's five times of day names a Lux preset of its own (0.225.0, the factory's roadmap 217).

The walker, 2026-10-07: a level is set at morning, high noon, afternoon, evening or midnight. `_preset_for` named three,
and morning, noon and "midnight" fell through to Gas Station Fluorescent, an interior look. Lux 0.79.0 draws the
morning and the high noon. A name Lux does not register makes `blend_to_preset` a silent no-op, so the names are held
to the ones Lux's preset folder carries, read off the sibling repo where `tests.siblings` finds one.

FAILS ON 0.224.0: morning, noon and midnight return Gas Station Fluorescent.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from apps.cli.commands import _preset_for  # noqa: E402
from tests.siblings import not_found, sibling_repo  # noqa: E402

_PRESETS_REL = "addons/lux/presets"

FIVE = {"morning": "Delco Morning", "noon": "Delco High Noon", "afternoon": "Delco Summer Afternoon",
        "evening": "Blue Hour", "midnight": "Delco Night"}


def _brief(tod, weather="clear"):
    return SimpleNamespace(time_of_day=tod, weather=weather)


@pytest.mark.parametrize("tod,preset", sorted(FIVE.items()))
def test_each_of_the_five_times_names_its_own_preset(tod, preset):
    assert _preset_for(_brief(tod)) == preset


def test_the_spellings_a_brief_uses_today_still_name_theirs():
    assert _preset_for(_brief("night")) == "Delco Night"
    assert _preset_for(_brief("NIGHT")) == "Delco Night"
    for noon in ("high noon", "high_noon", "midday"):
        assert _preset_for(_brief(noon)) == "Delco High Noon"


def test_rain_still_wins_and_an_unknown_time_still_falls_through():
    assert _preset_for(_brief("morning", "rain")) == "Heavy Rain"
    assert _preset_for(_brief("dawn")) == "Gas Station Fluorescent"


def test_every_name_it_returns_is_a_preset_lux_registers():
    lux = sibling_repo("lux", marker=_PRESETS_REL)
    if lux is None:
        pytest.skip(not_found("lux", marker=_PRESETS_REL))
    names = set()
    for f in (lux / _PRESETS_REL).glob("*.tres"):
        m = re.search(r'^preset_name = &"([^"]+)"', f.read_text(encoding="utf-8"), re.M)
        if m:
            names.add(m.group(1))
    returned = {_preset_for(_brief(t)) for t in list(FIVE) + ["dawn"]} | {_preset_for(_brief("x", "rain"))}
    assert returned <= names, sorted(returned - names)
