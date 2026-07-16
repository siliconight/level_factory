"""Unit tests: tool-contract verification (integration-drift guard)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from packages.tools import contracts as C


def test_parse_semver_tolerates_name_prefixes():
    assert C.parse_semver("Deli Counter 0.74.2") == (0, 74, 2)
    assert C.parse_semver("0.27.0") == (0, 27, 0)
    assert C.parse_semver("Lux 0.13.0") == (0, 13, 0)
    assert C.parse_semver(None) is None
    assert C.parse_semver("no version here") is None


def test_compare_statuses():
    assert C.compare("0.74.2", "0.74.2") == C.OK
    assert C.compare("0.74.2", "0.74.5") == C.DRIFT       # patch diff, same major
    assert C.compare("0.18.0", "0.20.0") == C.DRIFT       # minor diff, same major
    assert C.compare("0.3.0", "1.0.0") == C.INCOMPATIBLE  # major bump
    assert C.compare("0.2.0", None) == C.UNKNOWN          # unreadable installed
    assert C.compare(None, "0.2.0") == C.UNKNOWN          # unpinned tool


def test_lock_overrides_grounded():
    lock_tools = {"zoo": {"certified_version": "0.30.0"}}
    ver, src = C.certified_version("zoo", lock_tools)
    assert (ver, src) == ("0.30.0", "lock")
    # Falls back to grounded when the lock has no entry.
    ver, src = C.certified_version("lot", lock_tools)
    assert src == "grounded" and ver == C.GROUNDED["lot"]["version"]


def test_verify_flags_drift_and_incompat():
    installed = {
        "deli_counter": "Deli Counter 0.75.0",  # OK (re-grounded v0.9.0)
        "zoo": "0.27.0",                          # DRIFT vs grounded 0.30.1
        "dispatch": "1.0.0",                      # INCOMPATIBLE vs 0.3.0
        "laser_tag": None,                        # UNKNOWN (unpinned)
    }
    results = {r.adapter_id: r.status for r in C.verify(installed)}
    assert results["deli_counter"] == C.OK
    assert results["zoo"] == C.DRIFT
    assert results["dispatch"] == C.INCOMPATIBLE
    assert results["laser_tag"] == C.UNKNOWN
    # worst_status escalates to the most severe present.
    assert C.worst_status(C.verify(installed)) == C.INCOMPATIBLE


def test_certify_records_versions_preserving_other_fields():
    full = {"schema": C.LOCK_SCHEMA, "godot": "4.7",
            "tools": {"dispatch": {"required_contract": "dispatch.mission.v0.2"}}}
    installed = {"dispatch": "0.3.0", "zoo": "0.27.0"}
    updated = C.certify(full, installed)
    # Engine key + existing tool fields preserved; certified_version added.
    assert updated["godot"] == "4.7"
    assert updated["tools"]["dispatch"]["required_contract"] == "dispatch.mission.v0.2"
    assert updated["tools"]["dispatch"]["certified_version"] == "0.3.0"
    assert updated["tools"]["zoo"]["certified_version"] == "0.27.0"


def test_every_grounded_tool_is_an_adapter():
    from packages.adapters.registry import AdapterRegistry
    ids = set(AdapterRegistry().ids())
    assert set(C.GROUNDED) <= ids, set(C.GROUNDED) - ids
