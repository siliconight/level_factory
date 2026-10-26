"""Generate a level's layouts and choose one (0.246.0, the factory's roadmap 314).

The legs are `make`'s, so these tests drive `layouts.generate` with a fake leg runner that leaves what a real shell
leg leaves -- candidate job folders, the validation file, walk tests -- and check that what the panel is told is read
from those, not from printed text: each layout's state, the recommendation (never a recommendation when every layout
failed), the request and build record written beside the design, the stop, and the choice. FAILS ON 0.245.0.
"""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from packages.service import design, layouts, operations  # noqa: E402
from packages.service.worker import EventSink, RequestError  # noqa: E402

SEEDS = (9003, 9104, 9205)


@pytest.fixture
def made(tmp_path, monkeypatch):
    from packages.tools import discovery
    monkeypatch.setattr(discovery, "factory_root", lambda start=None: tmp_path)
    noop = type("E", (), {"emit": lambda self, *a, **k: None})()
    got = operations.create_design({"template": "restaurant_row", "name": "Strip"}, noop)
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    return got, run_dir


def _fake(outcomes, calls):
    """A leg runner that does what each leg leaves on disk. ``outcomes``: seed -> (majors, walk_ok)."""
    def leg(argv, log, *, cancel_file, on_poll=None):
        calls.append(argv)
        if argv[0] == "init":
            ws = Path(argv[1])
            ws.mkdir(parents=True, exist_ok=True)
            (ws / "factory.project.json").write_text("{}", encoding="utf-8")
        elif argv[2:3] == ["run"]:
            ws, mission = Path(argv[1]), argv[3]
            internal = ws / ".level_factory"
            issues = []
            for seed, (majors, walk_ok) in outcomes.items():
                cid = "%s.candidate.seed_%d" % (mission, seed)
                (internal / "jobs" / ("%s.lot_assemble.candidate.seed_%d" % (mission, seed))).mkdir(parents=True)
                if walk_ok is not None:
                    w = internal / "jobs" / ("%s.walktest_navqa.candidate.seed_%d" % (mission, seed)) / "1" / "out"
                    w.mkdir(parents=True)
                    (w / "site.walktest.json").write_text(json.dumps({"ok": walk_ok, "walkers": []}),
                                                         encoding="utf-8")
                issues += [{"candidate_id": cid, "severity": "major", "code": c} for c in majors]
            (internal / "validation").mkdir(parents=True)
            (internal / "validation" / ("%s.json" % mission)).write_text(json.dumps({"issues": issues}),
                                                                       encoding="utf-8")
            return 1 if issues else 0
        return 0
    return leg


def test_generate_reads_each_layout_from_the_build_and_records_the_request(made):
    got, run_dir = made
    calls = []
    sink = EventSink(run_dir, "r", "generate_layouts")
    out = layouts.generate(got["path"], sink, run_dir,
                           leg=_fake({9003: ([], True), 9104: (["LOT_SOMETHING_MAJOR"], True), 9205: ([], None)},
                                     calls))
    states = {c["seed"]: c["state"] for c in out["candidates"]}
    assert states == {9003: "valid", 9104: "needs attention", 9205: "not checked"}
    assert out["recommended"].endswith("seed_9003") and not out["every_out"]
    assert [a[0] if a[0] != "-C" else a[2] for a in calls] == ["init", "batch", "plan", "run"]
    folder = Path(got["path"]).parent
    brief = json.loads((folder / "request" / "briefs" / "strip_001.json").read_text(encoding="utf-8"))
    assert brief == got["brief"]
    record = json.loads((folder / "builds" / "revision_1.json").read_text(encoding="utf-8"))
    assert record["design_revision"] == 1 and record["brief"] == brief and len(record["candidates"]) == 3
    stages = [json.loads(x)["stage"] for x in sink.path.read_text(encoding="utf-8").splitlines()]
    assert stages[:4] == ["init", "import", "plan", "layouts"]


def test_when_every_layout_fails_nothing_is_recommended(made):
    got, run_dir = made
    out = layouts.generate(got["path"], EventSink(run_dir, "r", "g"), run_dir,
                           leg=_fake({9003: ([], False), 9104: ([], False)}, []))
    assert out["every_out"] and {c["state"] for c in out["candidates"]} == {"failed"}
    assert "not a recommendation" in out["recommendation"]


def test_stop_ends_the_build_and_says_what_finished(made):
    got, run_dir = made
    (run_dir / "cancel").write_text("", encoding="utf-8")

    def leg(argv, log, *, cancel_file, on_poll=None):
        if argv[2:3] == ["plan"] and cancel_file.exists():
            raise layouts.LayoutError("cancelled", "stopped")
        return _fake({9003: ([], True)}, [])(argv, log, cancel_file=cancel_file)
    with pytest.raises(layouts.LayoutError) as e:
        layouts.generate(got["path"], EventSink(run_dir, "r", "g"), run_dir, leg=leg)
    assert e.value.code == "cancelled" and "init, import" in str(e.value)


def test_a_failed_leg_is_a_refusal_naming_it(made):
    got, run_dir = made

    def leg(argv, log, *, cancel_file, on_poll=None):
        return 4 if argv[2:3] == ["plan"] else _fake({}, [])(argv, log, cancel_file=cancel_file)
    with pytest.raises(layouts.LayoutError) as e:
        layouts.generate(got["path"], EventSink(run_dir, "r", "g"), run_dir, leg=leg)
    assert e.value.code == "leg_failed" and "plan exited 4" in str(e.value)


def test_choosing_records_the_gate_and_refuses_a_stranger(made):
    got, run_dir = made
    calls = []
    leg = _fake({9003: ([], True), 9104: ([], True)}, calls)
    layouts.generate(got["path"], EventSink(run_dir, "r", "g"), run_dir, leg=leg)
    out = layouts.choose(got["path"], "strip_001.candidate.seed_9104", EventSink(run_dir, "r", "c"), run_dir, leg=leg)
    assert out["chosen"]["seed"] == 9104
    approve = calls[-1]
    assert approve[2:5] == ["approve", "strip_001", "candidate_selected"]
    assert approve[approve.index("--by") + 1] == "panel" and "not a review" in approve[approve.index("--note") + 1]
    with pytest.raises(layouts.LayoutError) as e:
        layouts.choose(got["path"], "strip_001.candidate.seed_1", EventSink(run_dir, "r", "c"), run_dir, leg=leg)
    assert e.value.code == "unknown_candidate"


def test_the_operations_carry_refusals(made, tmp_path):
    got, run_dir = made
    sink = EventSink(run_dir, "r", "g")
    with pytest.raises(RequestError) as e:
        operations.choose_layout({"path": got["path"], "candidate": "x"}, sink)
    assert e.value.code == "no_layouts"
    with pytest.raises(RequestError):
        operations.generate_layouts({"path": got["path"], "seed": 1}, sink)
