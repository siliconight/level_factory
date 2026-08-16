"""Roadmap 48: which buildings a mission places may not depend on WHICH
COMMAND is running.

THE DEFECT THIS PINS. `_write_site_spec` chooses the lot by handing a pool to
`building_library.pick_lot`. That pool used to be narrowed only when the
CURRENT invocation had planned a `themed_site_assemble` job -- `_art_run`,
read off `plan.graph.jobs()`. `batch create` plans no art layer and `run
--art` plans one, so the same mission at the same seed drew from 123 shells
in one command and 98 in the other, and produced two different buildings.

Measured on unlit_probe_001 (2026-08-15, one workspace, seed 5017): graybox
drew `cr_garage`, the art pass drew `landmark_hall_a03`. Everything that
graded the mission -- walktest, Laser Tag, the structural checks, the
functional lock -- ran under `batch create` and measured the first. The
export would have shipped the second. The functional lock refused it, which
is the only reason anybody found out. Full evidence:
`docs/findings/ITEM48_THE_DRAW_MOVED.md`.

WHAT THIS TEST CHECKS, AND WHAT IT DOES NOT. It checks that the flag is gone
and cannot come back by accident: no `art_run` parameter, no `_art_run`
binding, nothing threading an art-layer flag into the site spec builder. That
is a STRUCTURAL check. It does NOT run two invocations and compare the
archetypes they select -- that needs a workspace, Deli Counter output and a
library on disk, which is `tests/integration`'s job. Said plainly here so
nobody later reads a green tick as more than it is.

Run:  python -m pytest tests/unit/test_draw_is_invocation_independent.py
"""
import inspect

from apps.cli import commands as cmds


def test_the_site_spec_builder_cannot_be_told_about_the_art_layer():
    sig = inspect.signature(cmds._write_site_spec)
    assert "art_run" not in sig.parameters, (
        "the pool a mission draws from is a property of its BRIEF, not of the "
        "command that happens to be running -- see roadmap item 48")


def test_no_caller_still_passes_one():
    src = inspect.getsource(cmds)
    assert "art_run" not in src, (
        "a caller still threads an art-layer flag into the site spec builder")


def test_the_pool_is_not_decided_by_reading_the_planned_graph():
    """The specific shape that caused it: a binding computed from
    `plan.graph.jobs()` and then used as a POOL decision. Reading the graph
    for other reasons is fine, so this looks for that binding by name."""
    assert "_art_run" not in inspect.getsource(cmds)


def test_the_narrowing_still_happens():
    """The other half, and the one worth being nervous about. Removing the
    flag must not have removed the narrowing with it -- a greybox pass that
    draws from the WIDE pool is the original defect wearing the fix's
    clothes."""
    assert "require_themed_shells" in inspect.getsource(cmds._write_site_spec)


def test_it_is_reached_only_when_the_brief_asks_for_a_lot():
    """`lot_library` is the key that gates the art layer, and it is what the
    narrowing is now keyed on. A mission without it must not reach this at
    all, so existing single-shell missions keep their row byte-for-byte."""
    src = inspect.getsource(cmds._write_site_spec)
    head = src[:src.index("require_themed_shells")]
    assert 'library = getattr(model, "lot_library", None)' in head
    assert "if library and" in head
