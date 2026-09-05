"""A brief that asks for N buildings and gets one, N times, must say so.

Roadmap 37's varied lot is BUILT -- `building_library` selects a lot, the
planner fans art jobs out per archetype, and `_write_site_spec` places a mixed
row. It is opt-in on `lot_library`, and the opting-in is the part nobody does:
of the eight briefs on disk when this was written, two demos set the key and
all three COLD-RUN briefs -- the runs that exist to measure
interventions-per-level -- did not. Every cold run measured to date placed one
building three or four times, and no line of output said so.

That is the shape roadmap 62 names: a tool that cannot make what was asked
should say what it made instead. Here it can make it and was not asked.

The silence is the defect under test, so these assert on stdout.
"""

from pathlib import Path
from types import SimpleNamespace

import apps.cli.commands as cmds
from packages.core.models import MissionBrief


class _Workspace(SimpleNamespace):
    """Enough Workspace for the spec builder."""

    def load_tools_local(self) -> dict:
        return {"repositories": {}}


def _deli_out(tmp_path: Path) -> Path:
    """A published Deli Counter job dir: `_write_site_spec` measures the GLB."""
    out = tmp_path / "deli" / "out"
    out.mkdir(parents=True)
    (out / "shell.glb").write_bytes(b"glb")
    (out / "shell.gameplay.json").write_text("{}", encoding="utf-8")
    return tmp_path / "deli"


def _write(tmp_path: Path, count: int) -> None:
    brief = MissionBrief(mission_id="m", display_name="m", archetype="bank",
                         building_count=count, theme="delco",
                         candidate_count=1, lot_library=None)
    ws = _Workspace(jobs_dir=tmp_path / "jobs",
                    internal_dir=tmp_path / "internal")
    cmds._write_site_spec(ws, brief, _deli_out(tmp_path), seed=5017)


def test_a_multi_building_brief_without_a_library_says_what_it_built(
        tmp_path, capsys):
    _write(tmp_path, count=3)
    out = capsys.readouterr().out
    assert "ONE archetype" in out
    # The count and the key are both in the line, because a warning that does
    # not name the fix is a warning somebody learns to scroll past.
    assert "3 buildings" in out
    assert "lot_library" in out


def test_one_building_is_not_a_repetition_and_stays_quiet(tmp_path, capsys):
    """A single-building brief has nothing to vary. Warning here would train
    the reader to ignore the line that matters."""
    _write(tmp_path, count=1)
    assert "ONE archetype" not in capsys.readouterr().out
