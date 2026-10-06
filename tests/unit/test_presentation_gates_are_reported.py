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


# ---- every placed building, not the first manifest (0.149.0) ----------------
#
# A varied lot composes one package per building, under `presentation/lot/`.
# `normalize_validation` read `next(...)` of the sorted manifests, which is
# the first building's. In cold run 9187 three of fifteen failed z-fight --
# deli_a01 203 pairs, office 121, rail_station_a02 117 -- and the one finding
# recorded was deli_a01's (`docs/findings/presentation_gates/` at the factory
# root).

def _lot(tmp_path, buildings, root=None):
    """A varied lot's outputs: one package a building, and the mission's own
    shell at the root when ``root`` is given."""
    base = tmp_path / "presentation"
    paths = []
    for bid, blocks in buildings.items():
        d = base / "lot" / bid
        d.mkdir(parents=True)
        man = {"schema": "portable.v1", "walkable": True, "closure": {"portable": True}}
        man.update(blocks)
        (d / "portable_resource_manifest.json").write_text(json.dumps(man), encoding="utf-8")
        paths.append(d / "portable_resource_manifest.json")
    if root is not None:
        base.mkdir(parents=True, exist_ok=True)
        man = {"schema": "portable.v1", "walkable": True, "closure": {"portable": True}}
        man.update(root)
        (base / "portable_resource_manifest.json").write_text(json.dumps(man), encoding="utf-8")
        paths.append(base / "portable_resource_manifest.json")
    return sorted(paths)


def test_every_placed_building_is_read(tmp_path):
    outs = _lot(tmp_path, {
        "deli_a01": {"zfight_check": dict(COLD_9005, pairs=203, solids=761)},
        "gs_empty_rowhome_a": {},
        "office": {"zfight_check": dict(COLD_9005, pairs=121, solids=422)},
        "rail_station_a02": {"zfight_check": dict(COLD_9005, pairs=117, solids=397)}})
    z = [i for i in PresentationAdapter().normalize_validation(outs)
         if i["code"] == "PRESENTATION_ZFIGHT"]
    assert sorted(i["location"] for i in z) == ["deli_a01", "office", "rail_station_a02"]
    assert all(i["message"].startswith(i["location"] + ": ") for i in z)


def test_an_unplaced_mission_shell_is_not_read_in_a_lot(tmp_path):
    """A varied lot composes the mission's own shell for the job's output
    contract and places each building instead (`_LOT_SUBDIR`). 9187's root
    package lists dangling refs; read, it would block a level that does not
    contain it."""
    outs = _lot(tmp_path, {"deli_a01": {}}, root={
        "closure": {"portable": False, "dangling_refs": ["site.tscn -> res://x.glb"]}})
    assert "PRESENTATION_UNRESOLVED_REF" not in _codes(
        PresentationAdapter().normalize_validation(outs))


def test_a_single_shell_mission_reads_its_root(tmp_path):
    outs = _lot(tmp_path, {}, root={
        "closure": {"portable": False, "dangling_refs": ["site.tscn -> res://x.glb"]}})
    assert "PRESENTATION_UNRESOLVED_REF" in _codes(
        PresentationAdapter().normalize_validation(outs))


#: cold run 9187's deli_a01, as Deli Counter 0.191.0's gate reads it: the
#: dressing arm clean, the shell arm naming a counter over the stairwell.
DELI_9187 = {"ok": False,
             "shell": {"ok": False, "source": "shell", "volumes": 14, "props": 154,
                       "declared_props": 154, "excused": [],
                       "conflicts": [{"prop": "counter_island_upper_hall_2",
                                      "volume": "stair:deli_stair_up",
                                      "penetration": 0.8}]},
             "dressing": {"ok": True, "source": "dressing", "volumes": 14,
                          "nodes": 8, "props": 249, "conflicts": []}}


def test_a_failing_circulation_arm_becomes_a_finding(tmp_path):
    """No branch read `circulation_check` at all: every cold run from 9164
    to 9187 failed it and none reached a finding."""
    issues = PresentationAdapter().normalize_validation(
        _lot(tmp_path, {"deli_a01": {"circulation_check": DELI_9187}}))
    circ = [i for i in issues if i["code"] == "PRESENTATION_CIRCULATION"]
    assert len(circ) == 1
    assert circ[0]["location"] == "deli_a01"
    assert "counter_island_upper_hall_2 0.8 m into stair:deli_stair_up" in circ[0]["message"]
    assert "(shell)" in circ[0]["message"]
    assert circ[0]["blocking"] is False and circ[0]["severity"] == "moderate"


def test_a_passing_circulation_check_says_nothing(tmp_path):
    clean = {"ok": True, "shell": dict(DELI_9187["shell"], ok=True, conflicts=[]),
             "dressing": DELI_9187["dressing"]}
    issues = PresentationAdapter().normalize_validation(
        _lot(tmp_path, {"deli_a01": {"circulation_check": clean}}))
    assert "PRESENTATION_CIRCULATION" not in _codes(issues)


def test_a_circulation_gate_that_did_not_run_is_said(tmp_path):
    broken = {"ok": False, "source": "dressing", "error": "gate failed to run: boom"}
    issues = PresentationAdapter().normalize_validation(
        _lot(tmp_path, {"office": {"circulation_check": broken}}))
    assert "gate failed to run: boom" in _one(issues, "PRESENTATION_CIRCULATION")["message"]


def test_an_unreadable_manifest_is_said(tmp_path):
    """It used to return quietly: a broken manifest silencing every finding
    about its package is "I cannot see it" reported as "it is not there"."""
    outs = _lot(tmp_path, {"office": {}})
    outs[0].write_text("{not json", encoding="utf-8")
    msg = _one(PresentationAdapter().normalize_validation(outs),
               "PRESENTATION_MANIFEST_UNREADABLE")["message"]
    assert msg.startswith("office: ")
