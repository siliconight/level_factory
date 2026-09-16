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
import os
from pathlib import Path

import pytest

from adapters.deli_counter import _preset_for, _VALID_PRESETS


def _presets_path():
    """The nearest `deli_counter/presets.py` at or above this file, or None.

    `LF_DC_ROOT` first, then every ancestor directory. Returning the path
    rather than a bool so the skip message can say where it looked.
    """
    env = os.environ.get("LF_DC_ROOT")
    if env:
        p = Path(env) / "presets.py"
        return p if p.is_file() else (Path(env) / "deli_counter" / "presets.py")
    here = Path(__file__).resolve()
    for parent in here.parents:
        p = parent / "deli_counter" / "presets.py"
        if p.is_file():
            return p
    return None


PRESETS = _presets_path()


def _registry_keys():
    if PRESETS is None or not PRESETS.is_file():
        pytest.skip("Deli Counter not found above %s (set LF_DC_ROOT)"
                    % Path(__file__).resolve().parent)
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
