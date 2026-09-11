"""The capability-gap signal reaches a run summary (roadmap 62).

Zoo says what it cannot build -- a kit module whose species is not in the
genome library, a light anchor whose type has no fixture species -- in its
index. Nothing in Level Factory read either until 2026-09-11, so a gap
surfaced as a greybox box or a dark room in a walk rather than as a line in
the run. These pin that both become a `ZOO_CAPABILITY_GAP` finding, non-
blocking, naming the species and the owner.

The third test is the one that matters most: `ZOO_PARTIAL_BUILD` read `n_fail`
off the index and Zoo never wrote it there, so the check was dead from the day
it shipped -- 98 failed modules across 37 indexes, zero findings. The
per-module `status` was always in the file; the count is now derived from it.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from adapters.zoo import ZooAdapter  # noqa: E402


def _index(tmp_path, name, **fields) -> Path:
    p = tmp_path / name
    p.write_text(json.dumps(fields), encoding="utf-8")
    return p


def _gaps(issues):
    return [i for i in issues if i["code"] == "ZOO_CAPABILITY_GAP"]


def test_a_missing_kit_species_is_a_gap_finding(tmp_path):
    idx = _index(tmp_path, "shop_kit.built.json", building_id="shop",
                 modules=[], n_fail=0,
                 missing_modules=[{"species": "gazebo", "stem": "gazebo_delco_01",
                                   "type": "gazebo", "count": 2,
                                   "nearest": ["gable"], "owner": "zoo"}])
    gaps = _gaps(ZooAdapter().normalize_validation([idx]))
    assert len(gaps) == 1
    g = gaps[0]
    assert g["blocking"] is False
    assert g["category"] == "art_coverage"
    assert "gazebo" in g["message"]
    assert "gable" in g["message"]
    assert "owner=zoo" in g["suggested_fix"]


def test_a_clean_kit_index_has_no_gap(tmp_path):
    idx = _index(tmp_path, "shop_kit.built.json", building_id="shop",
                 modules=[{"status": "pass"}], n_fail=0, missing_modules=[])
    assert _gaps(ZooAdapter().normalize_validation([idx])) == []


def test_partial_build_is_derived_from_module_status_when_n_fail_is_absent(tmp_path):
    # Every index Zoo wrote before 0.58.0 looks like this: no n_fail, and a
    # status on every module.
    idx = _index(tmp_path, "shop_kit.built.json", building_id="shop",
                 modules=[{"status": "pass"}, {"status": "fail"},
                          {"status": "warn"}, {"status": "fail"}])
    issues = ZooAdapter().normalize_validation([idx])
    pb = [i for i in issues if i["code"] == "ZOO_PARTIAL_BUILD"]
    assert len(pb) == 1
    assert pb[0]["message"].startswith("2 module(s) failed")
    assert pb[0]["blocking"] is False


def test_partial_build_stays_quiet_when_every_module_built(tmp_path):
    idx = _index(tmp_path, "shop_kit.built.json", building_id="shop",
                 modules=[{"status": "pass"}, {"status": "warn"}])
    issues = ZooAdapter().normalize_validation([idx])
    assert all(i["code"] != "ZOO_PARTIAL_BUILD" for i in issues)


def test_an_unserved_light_anchor_is_a_gap_finding(tmp_path):
    idx = _index(tmp_path, "site_fixtures.built.json", scope_id="site",
                 fixtures_built=3, emitter_markers=3,
                 skipped=[{"id": "w1", "type": "window",
                           "reason": "daylight/preset -- no hardware"},
                          {"id": "p1", "type": "pendant",
                           "reason": "no fixture species for this type"},
                          {"id": "p2", "type": "pendant",
                           "reason": "no fixture species for this type"}])
    gaps = _gaps(ZooAdapter().normalize_validation([idx]))
    assert len(gaps) == 1
    assert "2 light anchor(s)" in gaps[0]["message"]
    assert "pendant" in gaps[0]["message"]
    assert "window" not in gaps[0]["message"]
    assert gaps[0]["blocking"] is False


def test_daylight_skips_are_not_gaps(tmp_path):
    idx = _index(tmp_path, "site_fixtures.built.json", scope_id="site",
                 fixtures_built=3, emitter_markers=3,
                 skipped=[{"id": "w1", "type": "window",
                           "reason": "daylight/preset -- no hardware"},
                          {"id": "f1", "type": "fluorescent",
                           "reason": "filtered out by --fixture-types"}])
    assert _gaps(ZooAdapter().normalize_validation([idx])) == []
