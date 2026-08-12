"""The per-building job axis: ids, and the field that saves anyone decoding them.

Step 1 of docs/PER_BUILDING_ART.md. Structural only -- nothing plans a
per-archetype job yet -- so these tests are the whole of the evidence that the
axis behaves, and they run in milliseconds with no Blender and no Godot.
"""
from __future__ import annotations

import json
import sys
from dataclasses import fields
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from packages.core.ids import candidate_id, job_id  # noqa: E402
from packages.core.models import Job  # noqa: E402


# ---------------------------------------------------------------------------
# the existing shapes must not move
# ---------------------------------------------------------------------------
def test_the_two_existing_id_shapes_are_unchanged():
    assert candidate_id("m1", 1997) == "m1.candidate.seed_1997"
    assert job_id("m1", "deli_generate") == "m1.deli_generate"
    assert (job_id("m1", "deli_generate", candidate=candidate_id("m1", 1997))
            == "m1.deli_generate.candidate.seed_1997")


# ---------------------------------------------------------------------------
# the new axis
# ---------------------------------------------------------------------------
def test_an_archetype_gives_one_job_id_per_building():
    ids = {job_id("lot_demo_001", "zoo_dressing_build", archetype=a)
           for a in ("final_stand", "supermarket_a01", "pharmacy_a02",
                     "depot_a01", "rail_station_a02")}
    assert len(ids) == 5, "five buildings must not collapse to one job"
    assert "lot_demo_001.zoo_dressing_build.final_stand" in ids


def test_both_axes_compose_and_stay_distinguishable():
    jid = job_id("m1", "zoo_dressing_build",
                 candidate=candidate_id("m1", 1997), archetype="depot_a01")
    assert jid == "m1.zoo_dressing_build.candidate.seed_1997.depot_a01"
    # the candidate tail is still literally `candidate.seed_<int>`, which is
    # what every existing reader keys on
    assert ".candidate.seed_1997" in jid


def test_an_archetype_job_is_distinct_from_its_mission_wide_stage():
    """`zoo_kit_build` stays one job per mission; dressing does not.

    If these ever collided, a fanned-out stage would overwrite the shared one's
    directory -- both are `jobs_dir / job_id / out`.
    """
    assert job_id("m1", "zoo_kit_build") != job_id(
        "m1", "zoo_kit_build", archetype="depot_a01")


# ---------------------------------------------------------------------------
# refusing, because job ids become directories
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("bad", [
    "lot/final_stand",      # separator: writes outside its own job dir
    "lot\\final_stand",
    "C:final_stand",
    "final stand",          # space: survives, but not legibly
    "final\tstand",
    "..",
    ".",
    "   ",
])
def test_an_unusable_archetype_id_is_refused_not_sanitised(bad):
    with pytest.raises(ValueError):
        job_id("m1", "zoo_dressing_build", archetype=bad)


def test_an_archetype_cannot_impersonate_the_candidate_segment():
    with pytest.raises(ValueError, match="candidate"):
        job_id("m1", "zoo_dressing_build", archetype="candidate")


def test_falsy_archetype_is_simply_absent_not_an_error():
    """A mission-wide stage passes nothing and must keep its old id."""
    assert job_id("m1", "zoo_kit_build", archetype=None) == "m1.zoo_kit_build"
    assert job_id("m1", "zoo_kit_build", archetype="") == "m1.zoo_kit_build"


# ---------------------------------------------------------------------------
# the Job field
# ---------------------------------------------------------------------------
def test_job_carries_the_building_so_nobody_has_to_decode_the_id():
    """The spec builder dispatches on `stage_id ==`.

    Five dressing jobs land in one branch; without this field the only way to
    tell them apart is taking the id back apart, and id parsing is already the
    fragile seam in this codebase.
    """
    assert "archetype_id" in {f.name for f in fields(Job)}
    j = Job(job_id="m1.zoo_dressing_build.depot_a01", mission_id="m1",
            stage_id="zoo_dressing_build", adapter_id="zoo",
            archetype_id="depot_a01")
    assert j.archetype_id == "depot_a01"


def test_a_mission_wide_job_has_no_building():
    j = Job(job_id="m1.zoo_kit_build", mission_id="m1",
            stage_id="zoo_kit_build", adapter_id="zoo")
    assert j.archetype_id is None


def test_an_old_payload_still_loads():
    """`Index.get_job` does `Job(**json.loads(payload))`.

    Every job record already in index.sqlite was written before this field
    existed. If the default were missing, opening an existing workspace would
    raise -- so this is the test that the change is safe to land on a live
    workspace rather than only on a fresh one.
    """
    old = {"job_id": "m1.zoo_kit_build", "mission_id": "m1",
           "stage_id": "zoo_kit_build", "adapter_id": "zoo",
           "candidate_id": "m1.candidate.seed_1997", "status": "planned",
           "attempt": 0, "priority": 0, "resource_class": "blender",
           "depends_on": [], "command": [], "working_directory": "",
           "environment_fingerprint": "", "input_fingerprint": "",
           "build_fingerprint": "", "started_at": None, "finished_at": None,
           "exit_code": None, "log_path": None, "artifact_ids": [],
           "expected_outputs": [], "failure": None}
    j = Job(**json.loads(json.dumps(old)))
    assert j.archetype_id is None


def test_a_new_payload_round_trips_through_as_dict():
    j = Job(job_id="m1.zoo_dressing_build.depot_a01", mission_id="m1",
            stage_id="zoo_dressing_build", adapter_id="zoo",
            archetype_id="depot_a01")
    back = Job(**json.loads(json.dumps(j.as_dict())))
    assert back.archetype_id == "depot_a01"
    assert back == j
