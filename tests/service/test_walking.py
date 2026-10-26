"""Walk a level's chosen layout (0.247.0, the factory's roadmap 315).

Driven with a fake leg runner that leaves what the real legs leave -- the selection marker, a preview project -- so
the test checks what the panel is told: the legs in order, the gates recorded as the panel's automatic steps and not
reviews, the self-check's verdict, the design revision and layout named, and the walk recorded beside the design;
and the refusals before anything runs (no layouts, no choice). FAILS ON 0.246.0.
"""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from packages.service import layouts, operations, walking  # noqa: E402
from packages.service.worker import EventSink, RequestError  # noqa: E402


@pytest.fixture
def level(tmp_path, monkeypatch):
    from packages.tools import discovery
    monkeypatch.setattr(discovery, "factory_root", lambda start=None: tmp_path)
    noop = type("E", (), {"emit": lambda self, *a, **k: None})()
    got = operations.create_design({"template": "restaurant_row", "name": "Walker"}, noop)
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    return got, run_dir, Path(got["path"]).parent / "workspace"


def _fake(calls, walk_code=0, choose=True):
    def leg(argv, log, *, cancel_file, on_poll=None):
        calls.append(argv)
        if argv[0] == "init":
            ws = Path(argv[1])
            ws.mkdir(parents=True, exist_ok=True)
            (ws / "factory.project.json").write_text("{}", encoding="utf-8")
            (ws / "tools.local.json").write_text(json.dumps({"godot_executable": "G:/godot.exe"}), encoding="utf-8")
            if choose:
                ap = ws / ".level_factory" / "approvals"
                ap.mkdir(parents=True)
                (ap / "walker_001.selected").write_text("walker_001.candidate.seed_9205", encoding="utf-8")
        elif argv[2:3] == ["walk"]:
            prev = Path(argv[1]) / ".level_factory" / "preview" / "walker_001_walk"
            prev.mkdir(parents=True)
            (prev / "project.godot").write_text("", encoding="utf-8")
            return walk_code
        return 0
    return leg


def _workspace(level, calls, **kw):
    got, run_dir, ws = level
    _fake(calls, **kw)(["init", str(ws)], run_dir / "legs.log", cancel_file=run_dir / "cancel")
    calls.clear()


def test_the_walk_runs_its_legs_names_what_it_shows_and_records_it(level):
    got, run_dir, ws = level
    calls = []
    _workspace(level, calls)
    out = walking.walk(got["path"], EventSink(run_dir, "r", "walk_level"), run_dir, leg=_fake(calls))
    assert [a[2] for a in calls] == ["approve", "approve", "run", "walk"]
    assert calls[0][3:5] == ["walker_001", "brief_approved"] and calls[1][4] == "functional_shell_locked"
    for gate in calls[:2]:
        assert gate[gate.index("--by") + 1] == "panel" and "not a review" in gate[gate.index("--note") + 1]
    assert calls[2][-2:] == ["--art", "--gameplay"] and "--play" not in calls[3]
    assert out["self_check"] == "passed" and out["godot"] == "G:/godot.exe"
    assert out["candidate_id"].endswith("seed_9205") and out["design_revision"] == 1
    assert "revision 1" in out["label"] and "9205" in out["label"]
    record = json.loads((Path(got["path"]).parent / "builds" / "revision_1.walk.json").read_text(encoding="utf-8"))
    assert record["preview"] == out["preview"] and record["design_id"] == got["design"]["design_id"]


def test_a_self_check_with_findings_still_hands_the_preview_over(level):
    got, run_dir, ws = level
    calls = []
    _workspace(level, calls)
    out = walking.walk(got["path"], EventSink(run_dir, "r", "w"), run_dir, leg=_fake(calls, walk_code=1))
    assert out["self_check"] == "findings" and Path(out["preview"]).name == "walker_001_walk"


def test_no_layouts_and_no_choice_are_refused_before_anything_runs(level):
    got, run_dir, ws = level
    calls = []
    with pytest.raises(layouts.LayoutError) as e:
        walking.walk(got["path"], EventSink(run_dir, "r", "w"), run_dir, leg=_fake(calls))
    assert e.value.code == "no_layouts" and calls == []
    _workspace(level, calls, choose=False)
    with pytest.raises(layouts.LayoutError) as e:
        walking.walk(got["path"], EventSink(run_dir, "r", "w"), run_dir, leg=_fake(calls, choose=False))
    assert e.value.code == "no_choice" and calls == []


def test_a_failed_art_leg_is_a_refusal_naming_it(level):
    got, run_dir, ws = level
    calls = []
    _workspace(level, calls)

    def leg(argv, log, *, cancel_file, on_poll=None):
        return 4 if argv[2:3] == ["run"] else _fake(calls)(argv, log, cancel_file=cancel_file)
    with pytest.raises(layouts.LayoutError) as e:
        walking.walk(got["path"], EventSink(run_dir, "r", "w"), run_dir, leg=leg)
    assert e.value.code == "leg_failed" and "art exited 4" in str(e.value)


def test_the_operation_carries_refusals(level):
    got, run_dir, ws = level
    with pytest.raises(RequestError) as e:
        operations.walk_level({"path": got["path"]}, EventSink(run_dir, "r", "w"))
    assert e.value.code == "no_layouts"
    with pytest.raises(RequestError):
        operations.walk_level({"path": got["path"], "play": True}, EventSink(run_dir, "r", "w"))
