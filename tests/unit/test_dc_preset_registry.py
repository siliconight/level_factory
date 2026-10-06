"""Level Factory's preset list is Deli Counter's registry, not a guess at it.

Cold runs 9055 and 9056 (2026-09-14): a brief with `archetype: strip_club` was
refused at graybox because `adapters.deli_counter._VALID_PRESETS` -- a copy of
Deli Counter's preset names -- had learned neither `twin` nor `strip_club`
(Deli Counter 0.133.0), while `new_level.py --list` printed both.

The registry is read as source with `ast`, no import across the boundary.
Skipped when Deli Counter cannot be found, because a check that cannot find
its rule has learned nothing and must not pass as if it had.

WHERE IT LOOKS, AND WHY THAT IS NOW A SEARCH (0.91.0). It was one path,
`parents[3] / "deli_counter"` -- correct for a checkout sitting beside Deli
Counter in `gabagool_factory`, and silently wrong for a git WORKTREE, which is
where the contributing guide says to do the work: from
`gabagool_factory/scratchpad/lf_cardshop/tests/unit/`, `parents[3]` is
`scratchpad`, there is no `deli_counter` in it, and the one test standing
between this repo and a sixth refused cold run SKIPPED. Found by running it
from a worktree while adding `card_shop` -- the preset it exists to catch --
and watching it report a pass it had not made. It now walks up from this file
until it finds a `deli_counter/presets.py`, and `LF_DC_ROOT` overrides.

Run:  python -m pytest tests/unit/test_dc_preset_registry.py
"""
import ast

import pytest

from adapters.deli_counter import UnknownArchetype, _preset_for, _VALID_PRESETS
from tests.siblings import not_found, sibling_repo

#: 0.94.0: the walk this file introduced now lives in `tests/siblings.py`,
#: because three more tests had the same one-path locator and a rule with four
#: copies is four rules. The behaviour is unchanged, `LF_DC_ROOT` included.
_PRESETS_REL = "presets.py"
_DELI = sibling_repo("deli_counter", marker=_PRESETS_REL)
PRESETS = (_DELI / _PRESETS_REL) if _DELI else None


def _registry_keys():
    if PRESETS is None:
        pytest.skip(not_found("deli_counter", marker=_PRESETS_REL))
    tree = ast.parse(PRESETS.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "REGISTRY" for t in node.targets):
            assert isinstance(node.value, ast.Dict), "REGISTRY is not a dict literal"
            return {k.value for k in node.value.keys if isinstance(k, ast.Constant)}
    pytest.fail(f"no REGISTRY assignment in {PRESETS}")


def test_the_adapter_knows_every_preset_deli_counter_registers():
    keys = _registry_keys()
    assert keys, "REGISTRY read as empty"
    assert keys == _VALID_PRESETS, (
        f"missing here: {sorted(keys - _VALID_PRESETS)}; "
        f"not in Deli Counter: {sorted(_VALID_PRESETS - keys)}")


def test_the_9055_brief_resolves_to_the_strip_club_preset():
    assert _preset_for("strip_club") == "strip_club"


def test_the_card_shop_preset_resolves():
    """Deli Counter 0.139.0's `card_shop`, and the names a brief is likely
    to reach for instead. `hobby_shop` is the one that matters: the keyword
    fallback in `_preset_for` only fires when the archetype CONTAINS a
    preset's name, and "hobby_shop" contains none, so it is an alias or it
    is an `UnknownArchetype` five stages into a cold run."""
    assert _preset_for("card_shop") == "card_shop"
    for alias in ("trading_card_shop", "hobby_shop", "comic_shop",
                  "collectibles_shop"):
        assert _preset_for(alias) == "card_shop", alias


def test_the_video_store_preset_resolves():
    """Deli Counter 0.171.0's `video_store`, and the names a brief reaches
    for that contain no preset's name."""
    assert _preset_for("video_store") == "video_store"
    for alias in ("video_rental", "video_rental_store", "vhs_store", "vhs_rental",
                  "movie_rental"):
        assert _preset_for(alias) == "video_store", alias


def test_the_convenience_store_preset_resolves():
    """Deli Counter 0.188.0's `convenience_store`: the Flappahs store, the
    station's shop without the forecourt. Until 0.146.0 this adapter aliased
    the name to the forecourt `gas_station`, so a convenience-store brief
    stood pumps and a canopy. The walker, 2026-10-06: "a03 as convenience
    store; Flappahs store always Flappahs"."""
    assert _preset_for("convenience_store") == "convenience_store"
    for alias in ("convenience", "c_store", "mini_mart", "minimart"):
        assert _preset_for(alias) == "convenience_store", alias
    assert _preset_for("highway_stop") == "gas_station"


def test_the_walkers_three_kinds_resolve_from_a_briefs_words():
    """0.146.0. The walker, 2026-10-06: the detail belongs "in the logic that
    is called when a level calls for a Gas Station, Convient Store, or a
    strip club". Each of these was refused, so the level never got there."""
    for alias in ("gas", "fuel_station", "filling_station", "service_station",
                  "petrol_station"):
        assert _preset_for(alias) == "gas_station", alias
    for alias in ("gentlemens_club", "go_go_bar", "gogo_bar", "topless_bar",
                  "strip_joint"):
        assert _preset_for(alias) == "strip_club", alias


def test_the_words_left_refused_stay_refused():
    """A wrong-but-plausible building is worse than a refusal. `corner_store`
    is as often the deli as the Flappahs store in Philadelphia; a nightclub
    is not a strip club and has no recipe; a truck stop is not the corner
    station."""
    for word in ("corner_store", "nightclub", "night_club", "truck_stop"):
        with pytest.raises(UnknownArchetype):
            _preset_for(word)


def test_this_check_can_actually_find_deli_counter():
    """A test that skips is a test that learned nothing, and this one used
    to skip in exactly the place the work is done. It is allowed to skip on
    a machine with no Deli Counter; it is not allowed to skip on one where
    Deli Counter is sitting two directories up, which is what a worktree
    looks like."""
    if PRESETS is None:
        pytest.skip("Deli Counter is genuinely not on this machine")
    assert PRESETS.is_file()
    assert "card_shop" in _registry_keys(), (
        "found %s but it does not register card_shop" % PRESETS)
