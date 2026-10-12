"""Blender jobs run three at a time where the machine allows (0.185.0, factory roadmap 239).

Cold run 9251 measured three: its Blender window 45.7 s against 114.0 one at a time, the drive
10.8 minutes against 12.1, and no model changed in a way two runs one at a time do not already
change it (`docs/findings/grader_speed/blender_width_compare.py` in the factory).
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from packages.jobs import scheduler as S  # noqa: E402


def test_three_on_the_machine_it_was_measured_on():
    assert S.blender_cap(16) == 3          # 8 cores, 16 logical CPUs: cold run 9251's


def test_never_wider_than_proven_however_big_the_machine():
    assert S.blender_cap(64) == S.BLENDER_PROVEN_WIDTH == 3


def test_a_small_machine_runs_fewer_and_never_none():
    assert S.blender_cap(4) == 2
    assert S.blender_cap(2) == 1 and S.blender_cap(1) == 1
    assert S.blender_cap(None) == 1 and S.blender_cap("x") == 1


def test_the_default_reads_it():
    import os
    assert S.DEFAULT_CONCURRENCY["blender"] == S.blender_cap(os.cpu_count())
