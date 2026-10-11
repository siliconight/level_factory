"""Laser Tag's evaluation runs on a clock that does not wait (factory roadmap 239, 0.180.0).

Cold runs 9245 and 9247 measured every Laser Tag evaluation simulating 3.91 to 3.97 times its
job's wall time: Godot paced the run to Laser Tag's 4x clock in real seconds, so most of a
ten-minute job waited. `--fixed-fps 60` -- an ENGINE argument, so before the `--` that starts
Laser Tag's own -- makes each frame one physics step, computed as fast as the processor allows,
and with Laser Tag 0.27.0's navigation on the evaluation's thread the report reads the same in
every field (cold run 9247's seed_9104: 593 s -> 21 s; the factory's
`docs/findings/grader_speed/`). The engine hides the flag from Laser Tag's scripts, so this
command is the only place the clock is chosen -- and the only place a regression would show.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from adapters.laser_tag import LaserTagAdapter  # noqa: E402


def _arguments(tmp_path, adapter=None):
    planned = (adapter or LaserTagAdapter()).plan_commands(
        {"seed": 1}, {"work_dir": str(tmp_path), "godot_executable": "godot"})
    return list(planned[0].arguments)


def test_the_engine_runs_the_fixed_clock(tmp_path):
    args = _arguments(tmp_path)
    assert "--fixed-fps" in args, args
    i = args.index("--fixed-fps")
    assert args[i + 1] == "60", args
    assert i < args.index("--"), "the clock is the engine's: it goes before `--`"


def test_one_frame_is_one_physics_step():
    """60 is the staged project's physics tick rate, which staging leaves at Godot's default, so a
    frame is one step -- the configuration every measured report ran under."""
    assert LaserTagAdapter.fixed_fps == 60


def test_the_physics_step_is_left_alone(tmp_path):
    """The fixed clock changes how fast the steps are computed, never how long a step is: that is
    `--time-scale`'s, and Laser Tag's default 4 is what every measured report used."""
    assert "--time-scale" not in _arguments(tmp_path)


def test_zero_restores_the_synchronised_clock(tmp_path):
    adapter = LaserTagAdapter()
    adapter.fixed_fps = 0
    assert "--fixed-fps" not in _arguments(tmp_path, adapter)
