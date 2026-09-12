"""A gate that fires into a log nobody reads has not fired (roadmap 133).

`presentation_compose` computes a z-fight check, writes it into
`portable_resource_manifest.json`, prints

    ERROR: coplanar surfaces detected -- the package would flicker

and exits 3. Its exit code is advisory by design -- a readiness signal is not
a build failure -- so the job records SUCCEEDED, and `normalize_validation`
had no branch for `zfight_check`. The finding therefore reached no status
line, no `validate` output and no report.

THREE COLD RUNS SHIPPED A PACKAGE THE COMPOSER SAID WOULD FLICKER, and each
was recorded as clean:

    cold 9003   33 coplanar pair(s) / 636 solids
    cold 9004   15 coplanar pair(s) / 249 solids
    cold 9005   30 coplanar pair(s) / 697 solids

It was found while ATTRIBUTING cold run 9005's output rather than while
measuring anything, which is the whole argument for attributing every item in
a gate's output before drawing a conclusion from it.
"""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from adapters.presentation import PresentationAdapter  # noqa: E402


def _manifest(tmp_path, **blocks):
    man = {"schema": "portable.v1", "walkable": True,
           "closure": {"portable": True}}
    man.update(blocks)
    path = tmp_path / "portable_resource_manifest.json"
    path.write_text(json.dumps(man), encoding="utf-8")
    return [path]


def _codes(issues):
    return [i["code"] for i in issues]


def _one(issues, code):
    return next(i for i in issues if i["code"] == code)


#: cold run 9005's real figures, as they stand in the shipped manifest.
COLD_9005 = {
    "ok": False, "scene": "site.tscn", "solids": 697, "pairs": 30,
    "buried_pairs": 8, "greybox_internal_pairs": 14,
    "findings": [
        {"a": "base:stair0_0_0", "b": "floor_ground_west_ward", "area": 0.311},
        {"a": "base:stair0_1_0", "b": "floor_ward_west_1", "area": 0.311},
        {"a": "base:stair1_0_0", "b": "floor_lobby", "area": 0.267},
    ],
}


def test_a_failing_zfight_gate_becomes_a_finding(tmp_path):
    """THE POINT OF THE ITEM."""
    issues = PresentationAdapter().normalize_validation(
        _manifest(tmp_path, zfight_check=COLD_9005))
    assert "PRESENTATION_ZFIGHT" in _codes(issues)


def test_a_clean_gate_says_nothing(tmp_path):
    """A finding on every run is a finding nobody reads, which is the defect
    this fixes wearing different clothes."""
    clean = dict(COLD_9005, ok=True)
    issues = PresentationAdapter().normalize_validation(
        _manifest(tmp_path, zfight_check=clean))
    assert "PRESENTATION_ZFIGHT" not in _codes(issues)


def test_a_manifest_without_the_block_is_not_a_finding(tmp_path):
    """An older manifest predates the check. Absent is not failing -- and
    `or {}` on a missing key would have turned absent into `ok is None`,
    which is not False."""
    issues = PresentationAdapter().normalize_validation(_manifest(tmp_path))
    assert "PRESENTATION_ZFIGHT" not in _codes(issues)


def test_the_visible_count_is_separated_from_the_total(tmp_path):
    """30 pairs, 8 of them visible. Reporting the total alone sends somebody
    hunting for 30 seams in a scene that has 8: a pair with one face buried
    inside a solid cannot flicker, and a pair between two greybox faces is
    under the art rather than in it."""
    issues = PresentationAdapter().normalize_validation(
        _manifest(tmp_path, zfight_check=COLD_9005))
    msg = _one(issues, "PRESENTATION_ZFIGHT")["message"]
    assert "30 coplanar face pair(s)" in msg
    assert "8 buried" in msg
    assert "14 greybox-internal" in msg
    assert "so 8 can be seen" in msg


def test_it_names_the_worst_offenders_rather_than_only_counting(tmp_path):
    """A count is not actionable. These are all stair bases coplanar with
    floors, which is a specific defect somebody can go and look at."""
    issues = PresentationAdapter().normalize_validation(
        _manifest(tmp_path, zfight_check=COLD_9005))
    msg = _one(issues, "PRESENTATION_ZFIGHT")["message"]
    assert "base:stair0_0_0 / floor_ground_west_ward" in msg


def test_it_does_not_block(tmp_path):
    """Advisory -- unlike the placement gate beside it, a blocker since
    0.74.0. Coplanar faces are an art
    defect, and refusing to build the level over one stops it existing long
    enough to be looked at -- the rule `Scheduler._advise` enforces."""
    issues = PresentationAdapter().normalize_validation(
        _manifest(tmp_path, zfight_check=COLD_9005))
    assert _one(issues, "PRESENTATION_ZFIGHT")["blocking"] is False
    assert _one(issues, "PRESENTATION_ZFIGHT")["severity"] == "moderate"


def test_findings_may_be_absent_without_raising(tmp_path):
    """The composer writes `findings` today. A manifest that reports a count
    and no list is still a real failure and must not take the reader down
    with it."""
    thin = {"ok": False, "scene": "site.tscn", "solids": 249, "pairs": 15}
    issues = PresentationAdapter().normalize_validation(
        _manifest(tmp_path, zfight_check=thin))
    msg = _one(issues, "PRESENTATION_ZFIGHT")["message"]
    assert "15 coplanar face pair(s)" in msg
    assert "not reported" in msg


def test_the_placement_gate_still_reports(tmp_path):
    """It always did, and the first draft of roadmap 133 said otherwise.
    Pinned so the correction cannot quietly reverse."""
    issues = PresentationAdapter().normalize_validation(
        _manifest(tmp_path, placement_check={"checked": 430, "matched": 400,
                                             "mismatched": 30}))
    assert "PRESENTATION_PLACEMENT_MISMATCH" in _codes(issues)
    # a blocker since 0.74.0: every cold run from 9001 to 9012 carried it as
    # a moderate advisory while the packages shipped wall remainders
    # standing across their walls
    pm = _one(issues, "PRESENTATION_PLACEMENT_MISMATCH")
    assert pm["blocking"] is True and pm["severity"] == "blocker"


def test_the_cold_run_manifest_on_disk_produces_both(tmp_path):
    """Against the artefact itself rather than a fixture, when it is there.
    A reader built from a guessed schema is the defect this repo has written
    down twice; this is the check that the shape is the real one."""
    man = (ROOT.parent / "workspaces" / "cold-9005-ws" / ".level_factory"
           / "jobs" / "county_hospital_001.presentation_compose" / "out"
           / "presentation" / "portable_resource_manifest.json")
    if not man.is_file():
        pytest.skip("cold run 9005 workspace not present")
    codes = _codes(PresentationAdapter().normalize_validation([man]))
    assert "PRESENTATION_ZFIGHT" in codes
    assert "PRESENTATION_PLACEMENT_MISMATCH" in codes
