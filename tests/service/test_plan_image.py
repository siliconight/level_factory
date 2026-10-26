"""Each layout's top-down plan, drawn from the build that made it (0.250.0, the factory's roadmap 314).

The plan reads the candidate's own ``site.site.drawn.json`` -- the newest attempt's -- names it and its hash, and is
not drawn when the build left none; `generate` keeps the plans with the revision's record. FAILS ON 0.249.0.
"""
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from packages.service import layouts, plan_image  # noqa: E402
from packages.service.worker import EventSink  # noqa: E402

SITE = {"site_id": "m", "ground": {"size_x": 100, "size_y": 60}, "objective": "b0",
        "roads": [{"a": [-50, -20], "b": [50, -20], "width": 10, "sidewalk": 3}],
        "buildings": [{"id": "b0", "archetype": "deli_a01", "at": [-20, 5], "rot": 0, "_footprint": [30, 20]},
                      {"id": "b1", "archetype": "deli_a03", "at": [25, 5], "rot": 90, "_footprint": [30, 20]}],
        "blockers": [{"id": "e0", "at": [0, -40], "rot": 180, "size_x": 6, "size_y": 12}],
        "cover": [{"at": [1, 2]}], "site_markers": [{"type": "crew_spawn", "at": [0, -15]}]}


def _site(internal, mission, seed, attempt, site):
    out = internal / "jobs" / ("%s.lot_assemble.candidate.seed_%d" % (mission, seed)) / str(attempt) / "out"
    out.mkdir(parents=True)
    (out / "site.site.drawn.json").write_text(json.dumps(site), encoding="utf-8")
    return out / "site.site.drawn.json"


def _rects(text):
    return [tuple(float(v) for v in m) for m in
            re.findall(r'<rect x="([\d.]+)" y="([\d.]+)" width="([\d.]+)" height="([\d.]+)" fill="#c9b48f"', text)]


def test_the_plan_is_the_newest_attempts_site_named_by_its_hash(tmp_path):
    internal = tmp_path / ".level_factory"
    _site(internal, "m", 1, 1, dict(SITE, buildings=[]))
    newest = _site(internal, "m", 1, 2, SITE)
    rows = [{"seed": 1}]
    plan_image.write_plans(internal, "m", rows, tmp_path / "plans")
    text = Path(rows[0]["plan"]).read_text(encoding="utf-8")
    assert hashlib.sha256(newest.read_bytes()).hexdigest() in text and str(newest) in text
    assert "<text" not in text                    # Godot's SVG loader draws no text
    # north up, PX per metre, MARGIN round the ground: b0 spans x -35..-5, y -5..15; b1 is turned 90 degrees
    px, m = plan_image.PX, plan_image.MARGIN
    x0, y1 = -50 - m, 30 + m
    assert _rects(text) == [((-35 - x0) * px, (y1 - 15) * px, 30 * px, 20 * px),
                            ((15 - x0) * px, (y1 - 20) * px, 20 * px, 30 * px)]
    assert 'stroke="#e0533d"' in text             # the objective is outlined


def test_no_drawn_site_means_no_plan_and_says_why(tmp_path):
    internal = tmp_path / ".level_factory"
    (internal / "jobs" / "m.lot_assemble.candidate.seed_2").mkdir(parents=True)
    _site(internal, "m", 3, 1, {"site_id": "m"})          # no ground: unreadable as a plan
    rows = [{"seed": 2}, {"seed": 3}]
    plan_image.write_plans(internal, "m", rows, tmp_path / "plans")
    assert rows[0]["plan"] is None and "no drawn site" in rows[0]["plan_problem"]
    assert rows[1]["plan"] is None and "cannot be read" in rows[1]["plan_problem"]
    assert not (tmp_path / "plans").exists()


def test_generate_keeps_each_layouts_plan_with_the_revision(tmp_path, monkeypatch):
    from packages.service import operations
    from packages.tools import discovery
    monkeypatch.setattr(discovery, "factory_root", lambda start=None: tmp_path)
    noop = type("E", (), {"emit": lambda self, *a, **k: None})()
    got = operations.create_design({"template": "restaurant_row", "name": "Plans"}, noop)
    run_dir = tmp_path / "run"
    run_dir.mkdir()

    def leg(argv, log, *, cancel_file, on_poll=None):
        if argv[0] == "init":
            Path(argv[1]).mkdir(parents=True, exist_ok=True)
            (Path(argv[1]) / "factory.project.json").write_text("{}", encoding="utf-8")
        elif argv[2:3] == ["run"]:
            internal, mission = Path(argv[1]) / ".level_factory", argv[3]
            _site(internal, mission, 9003, 1, SITE)
            (internal / "jobs" / ("%s.lot_assemble.candidate.seed_9104" % mission)).mkdir(parents=True)
            (internal / "validation").mkdir(parents=True)
            (internal / "validation" / ("%s.json" % mission)).write_text('{"issues": []}', encoding="utf-8")
        return 0

    out = layouts.generate(got["path"], EventSink(run_dir, "r", "e"), run_dir, leg=leg)
    plans = {c["seed"]: c["plan"] for c in out["candidates"]}
    folder = Path(got["path"]).parent
    assert plans == {9003: str(folder / "builds" / "plans" / "revision_1" / "seed_9003.svg"), 9104: None}
    assert out["plan_key"] == plan_image.KEY and "10 m" in out["plan_key"]
    record = json.loads((folder / "builds" / "revision_1.json").read_text(encoding="utf-8"))
    assert [c["plan"] for c in record["candidates"]] == [plans[9003], None]
