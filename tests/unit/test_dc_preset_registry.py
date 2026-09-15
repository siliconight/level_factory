"""Level Factory's preset list is Deli Counter's registry, not a guess at it.

Cold runs 9055 and 9056 (2026-09-14): a brief with `archetype: strip_club` was
refused at graybox because `adapters.deli_counter._VALID_PRESETS` -- a copy of
Deli Counter's preset names -- had learned neither `twin` nor `strip_club`
(Deli Counter 0.133.0), while `new_level.py --list` printed both.

The registry is read as source with `ast`, no import across the boundary.
Skipped when Deli Counter is not beside this repo, because a check that cannot
find its rule has learned nothing and must not pass as if it had.

Run:  python -m pytest tests/unit/test_dc_preset_registry.py
"""
import ast
from pathlib import Path

import pytest

from adapters.deli_counter import _preset_for, _VALID_PRESETS

PRESETS = Path(__file__).resolve().parents[3] / "deli_counter" / "presets.py"


def _registry_keys():
    if not PRESETS.is_file():
        pytest.skip(f"Deli Counter not beside this repo ({PRESETS})")
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
