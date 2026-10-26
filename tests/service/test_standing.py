"""A reopened level shows where it stands (0.251.0, the factory's roadmap 318: save and reopen).

`open_design` reads the records each step left beside the design -- the newest layouts, the choice, the last walk
and export -- and says of each whether it is of the design as it stands now. FAILS ON 0.250.0.
"""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from packages.service import layouts, operations, standing  # noqa: E402

_NOOP = type("E", (), {"emit": lambda self, *a, **k: None})()


@pytest.fixture
def level(tmp_path, monkeypatch):
    from packages.tools import discovery
    monkeypatch.setattr(discovery, "factory_root", lambda start=None: tmp_path)
    got = operations.create_design({"template": "restaurant_row", "name": "Back Again"}, _NOOP)
    return got, Path(got["path"]).parent


def _layouts(folder, revision, brief, chosen=None):
    rows = [{"candidate_id": "back_again_001.candidate.seed_%d" % s, "seed": s, "state": "valid", "plan": None}
            for s in (9003, 9205)]
    layouts._write_json(folder / "builds" / ("revision_%d.json" % revision),
                        {"design_revision": revision, "brief": brief, "candidates": rows,
                         "recommended": rows[1]["candidate_id"], "every_out": False,
                         "recommendation": "Ranked.", "plan_key": "key"})
    if chosen:
        marker = folder / "workspace" / ".level_factory" / "approvals" / "back_again_001.selected"
        marker.parent.mkdir(parents=True)
        marker.write_text(chosen + "\n", encoding="utf-8")


def test_a_new_level_stands_nowhere(level):
    got, folder = level
    opened = operations.open_design({"path": got["path"]}, _NOOP)
    assert opened["standing"] == {"layouts": None, "layouts_stale": [], "chosen": None, "walk": None,
                                  "export": None, "problems": []}


def test_reopened_after_walking_and_exporting_it_shows_each_as_current(level):
    got, folder = level
    _layouts(folder, 1, got["brief"], chosen="back_again_001.candidate.seed_9205")
    layouts._write_json(folder / "builds" / "revision_1.walk.json", {"label": "Back Again, revision 1, layout seed 9205"})
    layouts._write_json(folder / "builds" / "revision_1.export.json",
                        {"snapshot": "D:/x", "checklist": [], "design_revision": 1})
    s = operations.open_design({"path": got["path"]}, _NOOP)["standing"]
    assert [c["seed"] for c in s["layouts"]["candidates"]] == [9003, 9205]
    assert s["layouts"]["plan_key"] == "key" and s["layouts"]["design_revision"] == 1
    assert s["chosen"] == "back_again_001.candidate.seed_9205" and s["layouts_stale"] == []
    assert s["walk"]["current"] and s["walk"]["label"].endswith("seed 9205")
    assert s["export"]["current"] and s["export"]["snapshot"] == "D:/x" and s["export"]["snapshot_present"] is False
    (folder / "snap").mkdir()
    layouts._write_json(folder / "builds" / "revision_1.export.json", {"snapshot": str(folder / "snap")})
    assert operations.open_design({"path": got["path"]}, _NOOP)["standing"]["export"]["snapshot_present"] is True


def test_a_change_since_makes_the_walk_old_and_a_layout_change_makes_the_layouts_stale(level):
    got, folder = level
    _layouts(folder, 1, got["brief"])
    layouts._write_json(folder / "builds" / "revision_1.walk.json", {"label": "r1"})
    operations.update_design({"path": got["path"], "revision": 1, "choices": {"time_of_day": "midnight"}}, _NOOP)
    s = operations.open_design({"path": got["path"]}, _NOOP)["standing"]
    assert s["walk"]["current"] is False and s["layouts_stale"] == []        # lighting only: the layouts stand
    operations.update_design({"path": got["path"], "revision": 2, "choices": {"candidate_count": 5}}, _NOOP)
    s = operations.open_design({"path": got["path"]}, _NOOP)["standing"]
    assert s["layouts_stale"] and s["layouts"]["design_revision"] == 1


def test_the_newest_revision_wins_and_an_unreadable_record_is_reported(level):
    got, folder = level
    layouts._write_json(folder / "builds" / "revision_2.walk.json", {"label": "two"})
    layouts._write_json(folder / "builds" / "revision_10.walk.json", {"label": "ten"})
    (folder / "builds" / "revision_3.export.json").write_text("{not json", encoding="utf-8")
    s = standing.standing(folder, json.loads(Path(got["path"]).read_text(encoding="utf-8")))
    assert s["walk"]["label"] == "ten" and s["export"] is None
    assert len(s["problems"]) == 1 and "revision_3.export.json" in s["problems"][0]
