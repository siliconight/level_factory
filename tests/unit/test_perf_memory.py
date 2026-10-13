"""The price reports what the package holds in memory (0.199.0, factory roadmap 238).

A package's texture memory was 314.6 MiB on cold run 9273 and 65.6 MiB on 9274, once the reflection atlas
was sized to the package (0.198.0), and no price said either. The fixed-station harness reported draws and
frame time; the memory was read by a separate probe on a separate copy (the factory's
`docs/findings/texture_memory/`). So the probe reads the engine's texture, buffer and video memory once
every station has been warmed -- what a station shows is resident by then -- and the runner prints them
beside the passes, in MiB.

The probe's half is read as source -- it runs only inside Godot -- and the runner's half is driven through
`test_perf_stations_run.py`'s stub Godot, which writes the report rather than pre-seeding it.
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tests.unit.test_perf_stations_run import (  # noqa: E402
    EXIT_OK, ROW, RUNNER, _pkg, _run, _stub_godot)

PROBE = RUNNER.with_name("perf_stations.gd")
MONITORS = (("texture_mem_bytes", "RENDER_TEXTURE_MEM_USED"),
            ("buffer_mem_bytes", "RENDER_BUFFER_MEM_USED"),
            ("video_mem_bytes", "RENDER_VIDEO_MEM_USED"))


def _src():
    return PROBE.read_text(encoding="utf-8")


def test_the_probe_reads_the_engine_s_memory_once_every_station_is_warm():
    """FAILS ON 0.198.0: the report carries no memory."""
    s = _src()
    warmed = s.index('_geometry["cold_worst_ms"] = cold_worst')
    measured = s.index("for _pass in range(PASSES):")
    for key, monitor in MONITORS:
        m = re.search(r'_geometry\["%s"\] = int\(Performance\.get_monitor\(\s*Performance\.%s\)\)'
                      % (key, monitor), s)
        assert m, key
        # after the warm-up, so what a station shows is resident, and before the measured passes
        assert warmed < m.start() < measured, key


def _report(tmp_path, geometry):
    pkg = _pkg(tmp_path)
    doc = {"schema": "level_factory.perf_stations.v1", "complete": True,
           "geometry": geometry, "rows": [ROW]}
    return _run(pkg, "--godot", str(_stub_godot(tmp_path, pkg, doc)), "--draws", "2000", "--ms", "11")


def test_the_runner_prints_the_memory_in_mib(tmp_path):
    """FAILS ON 0.198.0. The bytes are cold run 9274's texture figure and its buffers', as MiB."""
    out = _report(tmp_path, {"texture_mem_bytes": 68786586, "buffer_mem_bytes": 50331648,
                             "video_mem_bytes": 119118234})
    assert out.returncode == EXIT_OK, out.stdout
    assert "memory after the warm-up: textures 65.6 MiB, buffers 48.0 MiB, video 113.6 MiB" in out.stdout, \
        out.stdout


def test_a_report_without_memory_says_so_rather_than_printing_a_zero(tmp_path):
    """FAILS ON 0.198.0, which says nothing."""
    out = _report(tmp_path, {})
    assert out.returncode == EXIT_OK, out.stdout
    assert "memory: none in this report (a probe from before 0.199.0)" in out.stdout, out.stdout


def test_a_report_with_part_of_the_memory_prints_none_of_it(tmp_path):
    """The probe writes the three together; a report with some is not one this knows, and a missing field
    is never read as a zero."""
    out = _report(tmp_path, {"texture_mem_bytes": 68786586})
    assert out.returncode == EXIT_OK, out.stdout
    assert "memory after the warm-up" not in out.stdout, out.stdout
    assert "memory: only texture_mem_bytes in this report -- not printed" in out.stdout, out.stdout
