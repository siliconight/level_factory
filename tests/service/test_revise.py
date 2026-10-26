"""Change a level's settings and see the change in the next walk (0.248.0, the factory's roadmap 316).

A change is a new revision, never an overwrite: the revision the change was made to must still be the saved one, an
unchanged save is refused, and the answer says what the change rebuilds. The walk builds the CURRENT revision -- its
brief re-written and re-imported before the art leg -- and refuses when a change made the chosen layout stale.
FAILS ON 0.247.0: no update_design.
"""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from packages.service import design, layouts, operations, walking  # noqa: E402
from packages.service.worker import EventSink, RequestError  # noqa: E402

_NOOP = type("E", (), {"emit": lambda self, *a, **k: None})()


@pytest.fixture
def level(tmp_path, monkeypatch):
    from packages.tools import discovery
    monkeypatch.setattr(discovery, "factory_root", lambda start=None: tmp_path)
    got = operations.create_design({"template": "restaurant_row", "name": "Late Shift"}, _NOOP)
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    return got, run_dir


def _save(got, **kw):
    return operations.update_design(dict({"path": got["path"]}, **kw), _NOOP)


def test_a_change_is_the_next_revision_and_says_what_it_rebuilds(level):
    got, _ = level
    out = _save(got, revision=1, choices={"time_of_day": "midnight"})
    assert out["design"]["revision"] == 2 and out["rebuilds"] == ["lighting"]
    assert json.loads(Path(out["path"]).read_text(encoding="utf-8"))["choices"]["time_of_day"] == "midnight"
    assert out["brief"]["time_of_day"] == "midnight"
    out = _save(got, revision=2, choices={"road_grammar": "block"})
    assert out["rebuilds"] == ["layout"]
    out = _save(got, revision=3, intent={"notes": "after closing"})
    assert out["rebuilds"] == [] and out["design"]["revision"] == 4


def test_a_stale_revision_and_an_unchanged_save_are_refused(level):
    got, _ = level
    _save(got, revision=1, choices={"time_of_day": "morning"})
    with pytest.raises(RequestError) as e:
        _save(got, revision=1, choices={"time_of_day": "noon"})
    assert e.value.code == "conflict"
    with pytest.raises(RequestError) as e:
        _save(got, revision=2, choices={"time_of_day": "morning"})
    assert e.value.code == "nothing_changed"
    with pytest.raises(RequestError) as e:
        _save(got, revision=2, choices={"time_of_day": "dusk"})
    assert e.value.code == "bad_choice"


def _workspace_with_layouts(got, run_dir, brief):
    folder = Path(got["path"]).parent
    ws = folder / "workspace"
    (ws / ".level_factory" / "approvals").mkdir(parents=True)
    (ws / "factory.project.json").write_text("{}", encoding="utf-8")
    (ws / ".level_factory" / "approvals" / "late_shift_001.selected").write_text(
        "late_shift_001.candidate.seed_9003", encoding="utf-8")
    layouts._write_json(folder / "builds" / "revision_1.json", {"brief": brief, "candidates": []})
    return ws


def _fake(calls):
    def leg(argv, log, *, cancel_file, on_poll=None):
        calls.append(argv)
        if argv[2:3] == ["walk"]:
            prev = Path(argv[1]) / ".level_factory" / "preview" / "late_shift_001_walk"
            prev.mkdir(parents=True)
            (prev / "project.godot").write_text("", encoding="utf-8")
        return 0
    return leg


def test_the_walk_builds_the_current_revision(level):
    got, run_dir = level
    _workspace_with_layouts(got, run_dir, got["brief"])
    _save(got, revision=1, choices={"time_of_day": "midnight"})
    calls = []
    out = walking.walk(got["path"], EventSink(run_dir, "r", "w"), run_dir, leg=_fake(calls))
    assert calls[0][2:4] == ["batch", "create"] and [a[2] for a in calls[1:]] == ["approve", "approve", "run", "walk"]
    imported = json.loads((Path(calls[0][4]).parent / "briefs" / "late_shift_001.json").read_text(encoding="utf-8"))
    assert imported["time_of_day"] == "midnight"
    assert out["design_revision"] == 2 and "revision 2" in out["label"]


def test_a_layout_change_makes_the_walk_ask_for_new_layouts(level):
    got, run_dir = level
    _workspace_with_layouts(got, run_dir, got["brief"])
    _save(got, revision=1, choices={"road_grammar": "cross"})
    calls = []
    with pytest.raises(layouts.LayoutError) as e:
        walking.walk(got["path"], EventSink(run_dir, "r", "w"), run_dir, leg=_fake(calls))
    assert e.value.code == "needs_new_layouts" and "Streets" in str(e.value) and calls == []
