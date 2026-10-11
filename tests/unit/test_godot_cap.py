"""The Godot cap follows the machine and the width the graders' verdicts were
proven at (Level Factory 0.179.1).

`DEFAULT_CONCURRENCY["godot_headless"]` was 2 on any machine. Cold run 9245's
graders -- three candidates' Laser Tag evaluations and walk tests, 88 % of the
run's job time -- queued two at a time on 8 cores and 16 logical CPUs, and its
shell leg spanned 15.7 minutes. Rerun from copies of cold run 9246's staged
projects, the graders' verdicts were identical at one, two, three and six at a
time; from three up, a few recorded event positions moved by a rounding step
in some reports, which the walker accepted on 2026-10-11 (`docs/findings/
grader_speed/` in the factory). So the cap is the smaller of one Godot job per
physical core (half the logical CPUs, never below the old 2) and that proven
width, 3.

FAILS ON 0.179.0: there is no `godot_cap`.
"""
from __future__ import annotations

import os

from packages.jobs import scheduler


def test_the_cap_is_the_machine_s_bounded_by_the_proven_width():
    assert scheduler.GODOT_PROVEN_WIDTH == 3
    assert scheduler.godot_cap(16) == 3     # this machine: 8 cores, held to 3
    assert scheduler.godot_cap(12) == 3
    assert scheduler.godot_cap(6) == 3
    assert scheduler.godot_cap(5) == 2      # 2 cores' worth: the machine's bound
    assert scheduler.godot_cap(4) == 2
    assert scheduler.godot_cap(1) == 2      # never below the 2 every machine had
    assert scheduler.godot_cap(None) == 2   # os.cpu_count() may not know


def test_the_default_reads_this_machine():
    assert scheduler.DEFAULT_CONCURRENCY["godot_headless"] == scheduler.godot_cap(os.cpu_count())


def test_three_candidates_evaluations_run_at_once_where_the_machine_allows():
    """A run's three candidates each have a Laser Tag evaluation; at 2 the
    third waited for one of the first two to finish."""
    assert scheduler.godot_cap(8) >= 3


def test_the_other_classes_did_not_move():
    caps = scheduler.DEFAULT_CONCURRENCY
    assert (caps["python_cpu"], caps["blender"], caps["godot_interactive"],
            caps["io_heavy"], caps["lightweight"]) == (4, 1, 1, 2, 8)
