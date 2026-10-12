"""The scheduler's caps can be overridden for one invocation (0.184.0, factory roadmap 239).

A wider width is measured before it becomes a default: `LF_CONCURRENCY` sets it for the command
line's scheduler, says so, and refuses what it does not understand rather than ignoring it.
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from packages.jobs import scheduler as S  # noqa: E402


def _scheduler(**kw):
    return S.Scheduler(index=None, cache=None, registry=None, jobs_dir=Path("."),
                       installation={}, **kw)


def test_a_width_per_class():
    assert S.concurrency_overrides("blender=3, python_cpu = 6") == {"blender": 3, "python_cpu": 6}
    assert S.concurrency_overrides("") == {} and S.concurrency_overrides(None) == {}


@pytest.mark.parametrize("text", ["blender", "blendr=3", "blender=three", "blender=0", "gpu=2"])
def test_what_it_cannot_read_refuses_the_run(text):
    with pytest.raises(ValueError) as exc:
        S.concurrency_overrides(text)
    assert S.CONCURRENCY_ENV in str(exc.value)


def test_the_command_lines_scheduler_takes_it_and_says_so(monkeypatch, capsys):
    monkeypatch.setenv(S.CONCURRENCY_ENV, "blender=3")
    sch = _scheduler()
    assert sch.concurrency["blender"] == 3
    assert sch.concurrency["python_cpu"] == S.DEFAULT_CONCURRENCY["python_cpu"]
    assert "blender 1 -> 3" in capsys.readouterr().out


def test_caps_given_to_the_constructor_are_the_callers(monkeypatch):
    monkeypatch.setenv(S.CONCURRENCY_ENV, "blender=3")
    assert _scheduler(concurrency={"blender": 1}).concurrency == {"blender": 1}


def test_without_it_the_defaults_stand(monkeypatch):
    monkeypatch.delenv(S.CONCURRENCY_ENV, raising=False)
    assert _scheduler().concurrency == S.DEFAULT_CONCURRENCY
