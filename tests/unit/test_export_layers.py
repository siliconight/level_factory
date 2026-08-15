"""The art layer is reported from what the art layer produces.

Written for level_factory 0.34.0. `cmd_export` inferred the art layer from
`lux_apply`'s output directory, so a mission whose art pass succeeded and
whose Lux stage failed exported a manifest declaring no art layer. These
cover the mapping itself -- which artifact stands for which layer -- not the
spelling of any job path.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from apps.cli.commands import _layers_produced  # noqa: E402
from packages.pipeline.planner import LAYER_ART, LAYER_GAMEPLAY  # noqa: E402


def _dirs(tmp_path, *, compose=False, lux=False, handoff=False, tag="0"):
    """Three job directories, under a root belonging to THIS call.

    HERMETIC BY CONSTRUCTION. Two calls in one test shared `tmp_path`
    and the second `mkdir(parents=True)` raised FileExistsError. The
    small fix is `exist_ok=True`; the correct one is that a call must
    not see what an earlier call created, or a test asking for 'no
    layers' after asking for 'gameplay' is handed gameplay and passes
    or fails for a reason it does not state.
    """
    base = tmp_path / f"case{tag}"
    c = base / "compose" / "out" / "presentation"
    l = base / "lux" / "out"
    h = base / "handoff" / "out"
    for wanted, d in ((compose, c), (lux, l), (handoff, h)):
        if wanted:
            d.mkdir(parents=True, exist_ok=True)
    return {"compose_root": c, "lux_dir": l, "handoff_dir": h}


def test_the_art_pass_alone_reports_the_art_layer(tmp_path):
    """THE BUG. Art built, Lux absent -- this returned an empty set."""
    assert _layers_produced(**_dirs(tmp_path, compose=True)) == {LAYER_ART}


def test_lux_alone_still_reports_the_art_layer(tmp_path):
    """The union, not a replacement. An existing workspace must not start
    describing itself differently after the upgrade."""
    assert _layers_produced(**_dirs(tmp_path, lux=True)) == {LAYER_ART}


def test_both_report_it_once(tmp_path):
    assert _layers_produced(**_dirs(tmp_path, compose=True, lux=True)) == {LAYER_ART}


def test_a_graybox_mission_reports_no_layers(tmp_path):
    assert _layers_produced(**_dirs(tmp_path)) == set()


def test_the_gameplay_layer_is_independent(tmp_path):
    # Distinct tags: the second call must not inherit the first's dirs.
    assert _layers_produced(
        **_dirs(tmp_path, handoff=True, tag="gameplay-only")
    ) == {LAYER_GAMEPLAY}
    assert _layers_produced(
        **_dirs(tmp_path, compose=True, handoff=True, tag="both")
    ) == {LAYER_ART, LAYER_GAMEPLAY}


def test_two_calls_in_one_test_do_not_contaminate_each_other(tmp_path):
    """THE BUG, as an assertion rather than a crash.

    Ask for gameplay, then ask for nothing. The second answer must be
    empty. Under a shared root the second call inherits the first
    call's directory and reports gameplay, with no exception to make
    anyone look."""
    assert _layers_produced(
        **_dirs(tmp_path, handoff=True, tag="a")) == {LAYER_GAMEPLAY}
    assert _layers_produced(**_dirs(tmp_path, tag="b")) == set()


def test_it_is_never_narrower_than_the_code_it_replaced(tmp_path):
    """The old rule, exhaustively, as the floor.

    Old: art iff lux_dir.exists(); gameplay iff handoff_dir.exists(). Every
    combination the old lines reported must still be reported.
    """
    for lux in (False, True):
        for handoff in (False, True):
            for compose in (False, True):
                old = set()
                if lux:
                    old.add(LAYER_ART)
                if handoff:
                    old.add(LAYER_GAMEPLAY)
                new = _layers_produced(
                    **_dirs(tmp_path / f"c{compose}l{lux}h{handoff}",
                            compose=compose, lux=lux, handoff=handoff))
                assert old <= new, (compose, lux, handoff, old, new)
