"""Export a level as a snapshot (0.249.0, the factory's roadmap 317).

The snapshot is the package the designer walked, copied whole into a new folder they chose, with a checklist read from
the files that know each answer and a manifest naming the design revision and layout. Refused: a revision that was
not walked, a folder that already holds something. A missing record is "unknown", never a pass. FAILS ON 0.248.0.
"""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from packages.service import exporting, layouts, operations  # noqa: E402
from packages.service.worker import EventSink, RequestError  # noqa: E402

_NOOP = type("E", (), {"emit": lambda self, *a, **k: None})()


@pytest.fixture
def walked(tmp_path, monkeypatch):
    """A design whose revision 1 was walked: the export folder, the walk record and the layouts as the real legs
    leave them."""
    from packages.tools import discovery
    monkeypatch.setattr(discovery, "factory_root", lambda start=None: tmp_path / "factory")
    got = operations.create_design({"template": "restaurant_row", "name": "Ship It"}, _NOOP)
    folder = Path(got["path"]).parent
    internal = folder / "workspace" / ".level_factory"
    export_dir = internal / "exports" / "LF_ship_it_001.portable-godot"
    export_dir.mkdir(parents=True)
    (export_dir / "mission.tscn").write_text("[gd_scene]\n", encoding="utf-8")
    (export_dir / "project.godot").write_text('renderer/rendering_method="gl_compatibility"\n', encoding="utf-8")
    (export_dir / "export_closure_scan.json").write_text(json.dumps({"ok": True, "package_file_count": 2,
                                                                      "missing_resource_count": 0,
                                                                      "external_reference_count": 0,
                                                                      "package_fingerprint": "abc"}), encoding="utf-8")
    (export_dir / "light_bake.json").write_text(json.dumps({"ok": True, "attempts": [{"result": {"users": 9}}]}),
                                                encoding="utf-8")
    for seed in (9003, 9205):
        (internal / "jobs" / ("ship_it_001.lot_assemble.candidate.seed_%d" % seed)).mkdir(parents=True)
        w = internal / "jobs" / ("ship_it_001.walktest_navqa.candidate.seed_%d" % seed) / "1" / "out"
        w.mkdir(parents=True)
        (w / "a.walktest.json").write_text(json.dumps({"ok": True, "walkers": []}), encoding="utf-8")
    (internal / "validation").mkdir()
    (internal / "validation" / "ship_it_001.json").write_text(json.dumps({"issues": [
        {"candidate_id": "ship_it_001.candidate.seed_9205", "severity": "major", "code": "SOMETHING"}]}),
        encoding="utf-8")
    layouts._write_json(folder / "builds" / "revision_1.walk.json",
                        {"candidate_id": "ship_it_001.candidate.seed_9205", "design_revision": 1})
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    return got, run_dir, export_dir


def _leg(status="PASS"):
    def leg(argv, log, *, cancel_file, on_poll=None):
        exports = Path(argv[1]) / ".level_factory" / "exports"
        (exports / "LF_ship_it_001.portable-godot.portability.json").write_text(
            json.dumps({"status": status, "engine_check": "passed"}), encoding="utf-8")
        return 0 if status == "PASS" else 2
    return leg


def test_the_snapshot_is_the_walked_package_with_its_checklist(walked, tmp_path):
    got, run_dir, export_dir = walked
    dest = tmp_path / "out" / "ship_it_v1"
    dest.parent.mkdir()
    out = exporting.export(got["path"], str(dest), EventSink(run_dir, "r", "e"), run_dir, leg=_leg())
    assert Path(out["snapshot"]) == dest and (dest / "mission.tscn").read_text(encoding="utf-8") == "[gd_scene]\n"
    states = {c["item"]: c["state"] for c in out["checklist"]}
    assert states == {"Package complete": "ok", "Opens without the factory": "ok", "Lights baked": "ok",
                      "Renderer": "ok", "Findings left": "problem"}
    m = json.loads((dest / exporting.SNAPSHOT_FILE).read_text(encoding="utf-8"))
    assert m["design_revision"] == 1 and m["layout"].endswith("seed_9205") and m["package_fingerprint"] == "abc"
    assert not list(dest.parent.glob(".*partial"))
    assert (Path(got["path"]).parent / "builds" / "revision_1.export.json").is_file()


def test_a_missing_record_is_unknown_and_a_failed_check_a_problem(walked, tmp_path):
    got, run_dir, export_dir = walked
    (export_dir / "light_bake.json").unlink()
    dest = tmp_path / "unbaked"
    out = exporting.export(got["path"], str(dest), EventSink(run_dir, "r", "e"), run_dir, leg=_leg("FAIL"))
    states = {c["item"]: c["state"] for c in out["checklist"]}
    assert states["Lights baked"] == "unknown" and states["Opens without the factory"] == "problem"


def test_a_folder_with_something_in_it_is_refused(walked, tmp_path):
    got, run_dir, export_dir = walked
    dest = tmp_path / "busy"
    dest.mkdir()
    (dest / "keep.txt").write_text("mine", encoding="utf-8")
    with pytest.raises(layouts.LayoutError) as e:
        exporting.export(got["path"], str(dest), EventSink(run_dir, "r", "e"), run_dir, leg=_leg())
    assert e.value.code == "destination_not_empty" and (dest / "keep.txt").read_text(encoding="utf-8") == "mine"


def test_an_unwalked_revision_is_refused(walked, tmp_path):
    got, run_dir, export_dir = walked
    operations.update_design({"path": got["path"], "revision": 1, "choices": {"time_of_day": "midnight"}}, _NOOP)
    with pytest.raises(layouts.LayoutError) as e:
        exporting.export(got["path"], str(tmp_path / "x"), EventSink(run_dir, "r", "e"), run_dir, leg=_leg())
    assert e.value.code == "walk_first" and "revision 2" in str(e.value)


def test_the_operation_carries_refusals(walked, tmp_path):
    got, run_dir, export_dir = walked
    with pytest.raises(RequestError) as e:
        operations.export_level({"path": got["path"], "destination": "relative/folder"}, EventSink(run_dir, "r", "e"))
    assert e.value.code == "bad_destination"
