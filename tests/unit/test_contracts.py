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
        "laser_tag": None,                        # UNKNOWN (nothing installed to read)
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


def test_laser_tag_reports_a_version_now(tmp_path):
    """Laser Tag reported UNKNOWN for one boring reason: no root VERSION file.

    `installed_factory_versions` reads `<factory_root>/<path>/VERSION` and
    nothing else, and `BaseAdapter._read_tool_version` looks there first too, so
    the addon's own `plugin.cfg` version was invisible to both layers. Adding
    the file was the whole fix -- no adapter code was needed, which is worth a
    test precisely because it means nothing in the adapter guards it.
    """
    from adapters.laser_tag import LaserTagAdapter

    (tmp_path / "VERSION").write_text("Laser Tag 0.8.0\n", encoding="utf-8")
    probe = LaserTagAdapter().probe({"repository": str(tmp_path)})
    assert probe.available
    assert C.parse_semver(probe.tool_version) == (0, 8, 0)
    # And the grounded pin agrees, so verify-contracts reads OK rather than
    # UNKNOWN for a tool that is in fact perfectly identifiable.
    assert C.compare(C.GROUNDED["laser_tag"]["version"], probe.tool_version) == C.OK


def test_a_tool_without_a_version_file_still_degrades_to_unknown(tmp_path):
    """The point of the VERSION file is that it is READ, not that it is assumed.

    An empty repo must still come back UNKNOWN rather than inheriting the
    grounded pin -- a missing version has to look different from a matching one.
    """
    from adapters.laser_tag import LaserTagAdapter

    probe = LaserTagAdapter().probe({"repository": str(tmp_path)})
    assert probe.tool_version is None
    assert C.compare(C.GROUNDED["laser_tag"]["version"], probe.tool_version) == C.UNKNOWN
