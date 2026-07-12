"""Selective rebuild classification (TDD 30)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from packages.pipeline.invalidation import (
    AMBIGUOUS, FUNCTIONAL, PRESENTATION, classify_change,
    invalidates_functional_lock, required_reruns,
)


def test_functional_changes_invalidate_lock():
    assert classify_change("collision") == FUNCTIONAL
    assert classify_change("anchor_move") == FUNCTIONAL
    assert invalidates_functional_lock("doorway_width")


def test_presentation_changes_preserve_lock():
    assert classify_change("lux_preset") == PRESENTATION
    assert classify_change("patina_palette") == PRESENTATION
    assert not invalidates_functional_lock("pixelcoat_material")


def test_unknown_change_is_ambiguous_and_conservative():
    assert classify_change("mystery_change") == AMBIGUOUS
    # Ambiguous is treated as functional (conservative, TDD 30.3).
    assert invalidates_functional_lock("mystery_change")


def test_rerun_sets_differ():
    assert "laser_tag" in required_reruns("collision")
    assert "dispatch_presentation" in required_reruns("lux_preset")
