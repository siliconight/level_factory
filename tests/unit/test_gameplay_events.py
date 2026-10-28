"""The gameplay-events switch (0.265.0, the factory's roadmap 323).

The walker: "so we can flip the switch, turn gameplay events on, and then the gameplay layer could ingest if
warranted". Off -- the default -- a score's alarm markers stay out of Dispatch's inputs and the package is what it was;
on, each becomes a `trigger` anchor carrying its event for Dispatch 0.6.0's `event_block`. FAILS ON 0.264.0.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from packages.core.models import MissionBrief  # noqa: E402
from packages.service import design  # noqa: E402
from packages.staging.dispatch_inputs import markers_to_anchors  # noqa: E402

GAMEPLAY = {"markers": [
    {"name": "b0/ALARM_INT_-1_6_OPEN0", "type": "alarm", "id": "int_-1_6_open0", "x": -8.0, "y": -3.0, "z": -1.95,
     "room": "b0/vault", "building": "b0",
     "meta": {"event": "alarm.vault_door", "audible": True, "fixture": "vault_door"}},
    {"name": "b0/OBJECTIVE_A", "type": "objective", "id": "A", "x": -8.0, "y": 5.0, "z": -3.3, "building": "b0"},
]}


def test_off_the_package_carries_no_event():
    anchors = markers_to_anchors(GAMEPLAY, "lot")
    assert [a["type"] for a in anchors] == ["objective"]
    assert not any("event" in a for a in anchors)


def test_on_an_alarm_is_a_trigger_carrying_its_event():
    anchors = markers_to_anchors(GAMEPLAY, "lot", events=True)
    trig, = [a for a in anchors if a["type"] == "trigger"]
    assert trig["event"] == {"event": "alarm.vault_door", "audible": True, "fixture": "vault_door", "room": "b0/vault"}
    assert trig["building"] == "b0" and trig["pos"] == [-8.0, -3.0, -1.95]
    # every other anchor is what it was with the switch off
    assert [a for a in anchors if a["type"] != "trigger"] == markers_to_anchors(GAMEPLAY, "lot")


def test_the_switch_is_off_by_default_and_outside_the_lock():
    assert MissionBrief.__dataclass_fields__["gameplay_events"].default is False
    off = MissionBrief(mission_id="m_001", display_name="M")
    on = MissionBrief(mission_id="m_001", display_name="M", gameplay_events=True)
    assert off.functional_signature() == on.functional_signature()


def test_the_panel_offers_it_on_every_template():
    for tid in design.templates():
        c = {x["key"]: x for x in design.capabilities(tid)}["gameplay_events"]
        assert c["type"] == "boolean" and c["default"] is False and c["support"] == "supported"


def test_an_event_never_moves_another_anchors_id():
    """0.265.1: ids an existing anchor shares are suffixed by its index, and 0.265.0 counted the alarms in it -- six of
    the Bank Block template's anchors changed id with events OFF. Two buildings' markers sharing ids, an alarm between:
    every other anchor's id is the same with the alarm absent, events off, and events on."""
    def site(with_alarm):
        ms = [{"type": "objective", "id": "A", "x": 0, "y": 0, "z": 0, "building": "b0"}]
        if with_alarm:
            ms.append({"type": "alarm", "id": "teller", "x": 1, "y": 0, "z": 0, "building": "b0",
                       "meta": {"event": "alarm.panic_button", "audible": False}})
        ms.append({"type": "objective", "id": "A", "x": 5, "y": 0, "z": 0, "building": "b1"})
        return {"markers": ms}
    before = [a["id"] for a in markers_to_anchors(site(False), "lot")]
    off = [a["id"] for a in markers_to_anchors(site(True), "lot")]
    on = [a["id"] for a in markers_to_anchors(site(True), "lot", events=True) if a["type"] != "trigger"]
    assert before == off == on, (before, off, on)
