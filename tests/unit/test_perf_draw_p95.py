"""A heading's draws are its window's p95, not its maximum; the maximum is kept beside it (0.269.0).

Two harness runs over one package read 616 and 703 draws at one heading. Recorded frame by frame (the factory's
docs/findings/price_draw_flicker/, `trace_run1.json`), the scene there alternates 540 and 616 every frame and now and
then submits ONE frame higher -- 703 at frame 51 of a window, 987 and 1008 at frames 4 and 3 of another heading's --
and the window's maximum took whichever stray frame it held. Over that run's 53 headings, the p95 of each window
agreed between the two passes at every heading and equalled the earlier report at every heading.

The probe runs only inside Godot, so its half is read as source, as `test_perf_passes.py` reads it.
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tests.unit.test_perf_stations_run import RUNNER  # noqa: E402

PROBE = RUNNER.with_name("perf_stations.gd")


def _sample_src():
    s = PROBE.read_text(encoding="utf-8")
    start = s.index("func _sample(")
    return s[start:s.index("\nfunc ", start + 1)]


def test_the_counts_are_not_a_running_maximum():
    """FAILS ON 0.268.0: `draws = maxi(draws, ...)` -- one stray frame in the window became the heading's count."""
    s = _sample_src()
    assert not re.search(r"\bdraws = maxi\(", s)
    assert not re.search(r"\bprims = maxi\(", s) and not re.search(r"\bobjs = maxi\(", s)


def test_the_counts_are_each_windows_p95_and_the_maximum_is_kept():
    s = _sample_src()
    assert "var draws: int = int(_pct(draw_frames, 0.95))" in s
    assert "var prims: int = int(_pct(prim_frames, 0.95))" in s
    assert "var objs: int = int(_pct(obj_frames, 0.95))" in s
    # sorted before the percentile is read, as `ms` is
    assert s.index("draw_frames.sort()") < s.index("int(_pct(draw_frames, 0.95))")
    assert '"draws_max": int(draw_frames[draw_frames.size() - 1])' in s
    # and every pass's record carries it, so a spike still shows in the report
    assert '"draws": pd["draws"], "draws_max": pd["draws_max"]' in PROBE.read_text(encoding="utf-8")


def test_one_stray_frame_cannot_move_the_count():
    """The window is long enough that its p95 index sits below the top three frames."""
    src = PROBE.read_text(encoding="utf-8")
    window = int(re.search(r"^const WINDOW := (\d+)", src, re.M).group(1))
    assert int(float(window - 1) * 0.95) <= window - 2
