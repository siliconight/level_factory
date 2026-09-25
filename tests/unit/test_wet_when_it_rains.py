"""A brief that says it is raining gets a wet road.

THE LAST LINK IN A CHAIN THAT WAS BUILT BACKWARDS. Pixelcoat has written
`wet_albedo` / `wet_roughness` into every ground pack since 0.47.0; Zoo 1.3.0
chooses them with `--wet`. Nothing asked. Cold run 9078's brief said
`weather: rain`, Lux rained on it, and the road shipped dry.

ONE PREDICATE FOR THE SKY AND THE GROUND. `_preset_for` reads `_RAIN_WEATHER`
to pick Lux's "Heavy Rain"; `_is_raining` reads the same set. A second spelling
of "is it raining" is exactly how a level comes to rain on a dry road.

AND THE FINGERPRINT CARRIES IT. This adapter was caught by the neighbouring
defect a day earlier -- `skin_hashes` hashed pack manifests and not their maps,
so a retuned texture cache-hit and shipped the previously baked material
(LF 0.111.0). A `wet` flag outside the fingerprint is the same shape: the same
mission rebuilt with the weather changed would read `cache` and ship the dry
road.

Run:  python -m pytest tests/unit/test_wet_when_it_rains.py
"""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from adapters.zoo import ZooAdapter  # noqa: E402
from apps.cli.commands import _is_raining, _RAIN_WEATHER  # noqa: E402


class _Brief:
    def __init__(self, weather):
        self.weather = weather


def _ctx(tmp_path):
    return {"work_dir": str(tmp_path / "work"),
            "repository": str(tmp_path / "repo"),
            "python_executable": "python", "blender_executable": "blender"}


def _args(tmp_path, spec):
    return list(ZooAdapter().plan_commands(spec, _ctx(tmp_path))[0].arguments)


# --------------------------------------------------------------------------- #
# The predicate
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("word", sorted(_RAIN_WEATHER))
def test_every_rain_word_lux_honours_also_wets_the_ground(word):
    """If a word is added to _RAIN_WEATHER for the sky, the ground follows.
    That is the whole reason this reads the same set rather than its own."""
    assert _is_raining(_Brief(word))


@pytest.mark.parametrize("word", ["clear", "overcast", "", None, "  Fog "])
def test_anything_else_is_dry(word):
    assert not _is_raining(_Brief(word))


def test_the_word_is_matched_case_and_space_insensitively():
    assert _is_raining(_Brief("  RAIN  "))


# --------------------------------------------------------------------------- #
# The flag reaches the three builds that dress surfaces
# --------------------------------------------------------------------------- #

def _kit(tmp_path, **extra):
    return {"mode": "kit", "slots_path": str(tmp_path / "b.slots.json"),
            "theme": "delco_1997", "seed": 7,
            "skins_dir": str(tmp_path / "px"), **extra}


def _dress(tmp_path, **extra):
    return {"mode": "dress", "manifest_path": str(tmp_path / "b.dressing.json"),
            "theme": "delco_1997", "seed": 7,
            "skins_dir": str(tmp_path / "px"), **extra}


def _habitat(tmp_path, **extra):
    return {"mode": "habitat", "habitat": "pebble", "theme": "delco_1997",
            "seed": 7, "skins_dir": str(tmp_path / "px"), **extra}


@pytest.mark.parametrize("build", [_kit, _dress, _habitat])
def test_wet_adds_the_flag(tmp_path, build):
    assert "--wet" in _args(tmp_path, build(tmp_path, wet=True))


@pytest.mark.parametrize("build", [_kit, _dress, _habitat])
def test_no_wet_no_flag(tmp_path, build):
    """The regression guard: every build that is not raining must plan the
    command it always planned."""
    assert "--wet" not in _args(tmp_path, build(tmp_path))
    assert "--wet" not in _args(tmp_path, build(tmp_path, wet=False))


def test_the_kit_build_is_the_one_that_wets_the_road(tmp_path):
    """Dressing and clutter are props ON a surface; the kit build IS the
    walls, floors and ground slabs. A wet street reaching only the props
    would be the wrong half of the effect."""
    args = _args(tmp_path, _kit(tmp_path, wet=True))
    assert "--build-kit" in args and "--wet" in args


def test_the_flag_needs_a_skin_library(tmp_path):
    """`--wet` without `--skins` asks a flat material to be wet, which is not
    a thing. It rides with the library on every branch."""
    spec = {"mode": "kit", "slots_path": str(tmp_path / "b.slots.json"),
            "theme": "delco_1997", "seed": 7, "wet": True}
    assert "--wet" not in _args(tmp_path, spec)


# --------------------------------------------------------------------------- #
# The fingerprint
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("build", [_kit, _dress, _habitat])
def test_changing_the_weather_changes_the_fingerprint(tmp_path, build):
    """Without this the same mission rebuilt in the rain reads `cache` and
    ships the dry road -- the defect LF 0.111.0 fixed one field along."""
    a = ZooAdapter().fingerprint_inputs(build(tmp_path), _ctx(tmp_path))
    b = ZooAdapter().fingerprint_inputs(build(tmp_path, wet=True),
                                        _ctx(tmp_path))
    assert a != b
    assert b.get("wet") is True


@pytest.mark.parametrize("build", [_kit, _dress, _habitat])
def test_a_dry_build_carries_no_wet_key_at_all(tmp_path, build):
    """Folded in only when true, on the rule the `habitat` key states: a new
    key on every zoo fingerprint would retire every cached kit, dressing and
    clutter bake in every workspace for a flag none of them carries."""
    for spec in (build(tmp_path), build(tmp_path, wet=False)):
        assert "wet" not in ZooAdapter().fingerprint_inputs(spec, _ctx(tmp_path))
