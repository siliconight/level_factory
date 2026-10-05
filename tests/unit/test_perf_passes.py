"""The fixed-station harness measures every heading twice and keeps the pass
with the lower p95 (0.141.0).

Four price runs on 2026-10-05 each had a heading jump 1-4 ms in ONE of three
runs with no draw changed, and each was argued away by hand. A hitch only
ever adds time, so the fastest of repeated measurements is the estimate.

The probe's half is read as source -- it runs only inside Godot -- and the
runner's half is driven through the stub Godot `test_perf_stations_run.py`
built, which writes the report rather than pre-seeding it.
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tests.unit.test_perf_stations_run import (  # noqa: E402
    EXIT_OK, ROW, RUNNER, _pkg, _run, _stub_godot)

PROBE = RUNNER.with_name("perf_stations.gd")


def _src():
    return PROBE.read_text(encoding="utf-8")


def test_the_probe_measures_every_heading_more_than_once():
    """FAILS ON 0.140.0: one pass."""
    m = re.search(r"^const PASSES := (\d+)", _src(), re.M)
    assert m and int(m.group(1)) >= 2
    assert "for _pass in range(PASSES):" in _src()


def test_the_lower_p95_pass_is_kept_whole_and_the_others_beside_it():
    """p95 is what a station's worst heading is chosen by and what the budget
    judges; a spike of three frames moves it and barely moves the median."""
    s = _src()
    assert 'passes.sort_custom(func(a, b): return float(a["ms_p95"]) < float(b["ms_p95"]))' in s
    assert "(passes[0] as Dictionary).duplicate()" in s
    assert 'best["passes"] = kept' in s
    assert 'best["pass_spread_ms"] = float(slowest["ms_p95"]) - float(best["ms_p95"])' in s


def test_the_watchdog_fires_before_the_runner_kills():
    """The watchdog writes what it has; the runner's timeout kills the tree
    and keeps nothing. A watchdog at or past the timeout never gets to write.
    Two passes took this patch's first draft to a 1200 s watchdog against a
    900 s timeout, and one pass measures 52 s, so it stayed at 600."""
    wd = re.search(r"^const WATCHDOG_SEC := ([\d.]+)", _src(), re.M)
    to = re.search(r'"--timeout", type=int, default=(\d+)',
                   RUNNER.read_text(encoding="utf-8"))
    assert wd and to, "the watchdog or the runner's timeout is no longer where this reads it"
    assert float(wd.group(1)) < float(to.group(1))


def _heading(yaw, spread=None, draws=(100, 100)):
    h = dict(ROW["worst_heading"], yaw=yaw, ms_median=3.0)
    if spread is not None:
        h["pass_spread_ms"] = spread
        h["passes"] = [{"ms_median": 3.0, "ms_p95": 4.0, "draws": draws[0]},
                       {"ms_median": 3.5, "ms_p95": 4.0 + spread, "draws": draws[1]}]
    return h


def _report(tmp_path, headings, passes=None):
    pkg = _pkg(tmp_path)
    row = dict(ROW, worst_heading=headings[0], headings=headings)
    doc = {"schema": "level_factory.perf_stations.v1", "complete": True,
           "geometry": {"passes": passes} if passes else {}, "rows": [row]}
    return _run(pkg, "--godot", str(_stub_godot(tmp_path, pkg, doc)), "--draws", "2000", "--ms", "11")


def test_the_runner_says_how_many_headings_hitched_in_a_pass(tmp_path):
    out = _report(tmp_path, [_heading(0.0, 2.4), _heading(90.0, 0.1, draws=(100, 104))], passes=2)
    assert out.returncode == EXIT_OK, out.stdout
    assert "passes: 2 per heading" in out.stdout, out.stdout
    assert "1 of 2 heading(s) differed by more than 1.0 ms p95 (largest 2.40 ms)" in out.stdout
    assert "1 drew a different count" in out.stdout


def test_a_report_from_before_passes_is_said_to_be_one(tmp_path):
    out = _report(tmp_path, [_heading(0.0)])
    assert out.returncode == EXIT_OK, out.stdout
    assert "passes: one per heading" in out.stdout, out.stdout
