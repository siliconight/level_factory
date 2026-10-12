"""A job's independent commands run side by side, and job.log keeps every command (0.186.0).

Cold run 9251's art leg spent 64 s in the compose job's sixteen commands, one building after
another, and its `job.log` held only the last building's -- each command rewrote it.
"""
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from adapters.presentation import PresentationAdapter  # noqa: E402
from packages.adapters.sdk import PlannedCommand  # noqa: E402
from packages.jobs import scheduler as S  # noqa: E402


def _cmd(tmp_path, word, seconds=0.0, parallel=False, code=0):
    src = "import sys, time; time.sleep(%r); print(%r); sys.exit(%d)" % (seconds, word, code)
    return PlannedCommand(executable=Path(sys.executable), arguments=("-c", src),
                          working_directory=tmp_path, parallel=parallel)


def _run(tmp_path, planned, width):
    sch = S.Scheduler(index=None, cache=None, registry=None, jobs_dir=tmp_path, installation={})
    log = tmp_path / "job.log"
    return list(sch._run_commands(planned, tmp_path, log, None, width=width)), log


def test_a_command_is_not_parallel_unless_it_says_so(tmp_path):
    c = _cmd(tmp_path, "x")
    assert c.parallel is False and "parallel" not in c.as_dict()
    assert _cmd(tmp_path, "x", parallel=True).as_dict()["parallel"] is True


def test_parallel_commands_run_at_once_and_report_in_plan_order(tmp_path):
    planned = [_cmd(tmp_path, "c%d" % n, seconds=0.8, parallel=True) for n in range(3)]
    t0 = time.time()
    results, log = _run(tmp_path, planned, width=3)
    wall = time.time() - t0
    assert [r.exit_code for r in results] == [0, 0, 0]
    assert wall < 2.0, "three 0.8 s commands one after another take 2.4 s; side by side %.2f s" % wall
    text = log.read_text(encoding="utf-8")
    assert text.index("c0") < text.index("c1") < text.index("c2"), "job.log in plan order"
    assert text.count("(exit=0") == 3 and not list(tmp_path.glob("job.*.log"))


def test_job_log_keeps_every_command_of_a_job_run_in_turn(tmp_path):
    results, log = _run(tmp_path, [_cmd(tmp_path, "first"), _cmd(tmp_path, "second")], width=4)
    text = log.read_text(encoding="utf-8")
    assert "first" in text and "second" in text, "each command used to rewrite it"
    assert all(r.log_path == log for r in results)


def test_one_command_writes_job_log_as_before(tmp_path):
    results, log = _run(tmp_path, [_cmd(tmp_path, "only")], width=4)
    assert "only" in log.read_text(encoding="utf-8") and results[0].log_path == log


def test_a_width_of_one_runs_them_in_turn_and_a_failure_is_reported_in_place(tmp_path):
    planned = [_cmd(tmp_path, "a", parallel=True), _cmd(tmp_path, "b", parallel=True, code=3),
               _cmd(tmp_path, "c", parallel=True)]
    results, _ = _run(tmp_path, planned, width=1)
    assert [r.exit_code for r in results] == [0, 3, 0]


def test_a_caller_that_stops_at_a_failure_never_starts_what_follows_in_turn(tmp_path):
    sch = S.Scheduler(index=None, cache=None, registry=None, jobs_dir=tmp_path, installation={})
    marker = tmp_path / "ran.txt"
    third = PlannedCommand(executable=Path(sys.executable),
                           arguments=("-c", "open(%r, 'w').write('x')" % str(marker)),
                           working_directory=tmp_path)
    gen = sch._run_commands([_cmd(tmp_path, "a"), _cmd(tmp_path, "b", code=2), third],
                            tmp_path, tmp_path / "job.log", None, width=4)
    assert next(gen).exit_code == 0 and next(gen).exit_code == 2
    gen.close()
    assert not marker.exists()


def test_the_buildings_compose_side_by_side_and_the_shell_first_alone(tmp_path):
    spec = {"lot_archetypes": [{"id": "a", "glb": "a.glb", "slots": "a.slots.json"},
                               {"id": "b", "glb": "b.glb", "slots": "b.slots.json"}]}
    planned = PresentationAdapter().plan_commands(spec, {"work_dir": str(tmp_path / "work"),
                                                         "repository": ""})
    assert [c.parallel for c in planned] == [False, True, True]
