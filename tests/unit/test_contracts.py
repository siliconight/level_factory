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
    # DERIVED FROM THE TABLE, NOT COPIED OUT OF IT. These were literals
    # ("Deli Counter 0.75.0", "0.27.0"), so re-grounding broke a test that is
    # about `compare`'s arithmetic and has no opinion about which versions are
    # pinned -- 2026-09-21's re-grounding failed both of them for that reason.
    def _bump(adapter_id, major=0, minor=0):
        maj, mnr, pat = C.parse_semver(C.GROUNDED[adapter_id]["version"])
        return f"{maj + major}.{mnr + minor}.{pat}"

    installed = {
        "deli_counter": C.GROUNDED["deli_counter"]["version"],  # OK: equal
        "zoo": _bump("zoo", minor=1),             # DRIFT: same major
        "dispatch": _bump("dispatch", major=1),   # INCOMPATIBLE: major bump
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

    pinned = C.GROUNDED["laser_tag"]["version"]
    (tmp_path / "VERSION").write_text(f"Laser Tag {pinned}\n", encoding="utf-8")
    probe = LaserTagAdapter().probe({"repository": str(tmp_path)})
    assert probe.available
    assert C.parse_semver(probe.tool_version) == C.parse_semver(pinned)
    # And the grounded pin agrees, so verify-contracts reads OK rather than
    # UNKNOWN for a tool that is in fact perfectly identifiable.
    assert C.compare(pinned, probe.tool_version) == C.OK


def test_the_stub_repos_declare_the_grounded_versions():
    """`tests/fixtures/repos/*` impersonate the real tools for the integration
    and service suites, and `doctor` probes them like any other installation.
    When they declare a version GROUNDED no longer names, `doctor` reads
    DRIFT -- or INCOMPATIBLE once a major moves, which is what zoo 0.30.2 ->
    1.1.1 did -- and `tests/service/test_facade.py::test_doctor_passes` fails
    with `assert 'FAIL' in ('PASS', 'WARN')`, naming nothing. This says what
    to do instead.

    The real tools' versions are asserted by the real-tool smoke
    (`tests/real_tools/test_grounded_table.py`), which is where a claim about
    an actual tool belongs. This is only about the stand-ins.
    """
    from pathlib import Path as _P
    repos = _P(__file__).resolve().parents[1] / "fixtures" / "repos"
    wrong = []
    for adapter_id, entry in sorted(C.GROUNDED.items()):
        vf = repos / adapter_id / "VERSION"
        declared = vf.read_text(encoding="utf-8").strip() if vf.is_file() else None
        if C.compare(entry["version"], declared) != C.OK:
            wrong.append(f"  {adapter_id:<14} stub declares {declared!r}, "
                         f"GROUNDED says {entry['version']}")
    assert not wrong, (
        "the stub tool repos disagree with contracts.GROUNDED:\n"
        + "\n".join(wrong)
        + "\n\nRe-grounding moves the pins; the stand-ins have to follow or "
          "`doctor` reads drift against tools that do not exist. Update "
          "tests/fixtures/repos/<tool>/VERSION (and deli_counter's stub "
          "`contract` command, whose reported tool_version the adapter "
          "prefers over the file).")


def test_a_tool_without_a_version_file_still_degrades_to_unknown(tmp_path):
    """The point of the VERSION file is that it is READ, not that it is assumed.

    An empty repo must still come back UNKNOWN rather than inheriting the
    grounded pin -- a missing version has to look different from a matching one.
    """
    from adapters.laser_tag import LaserTagAdapter

    probe = LaserTagAdapter().probe({"repository": str(tmp_path)})
    assert probe.tool_version is None
    assert C.compare(C.GROUNDED["laser_tag"]["version"], probe.tool_version) == C.UNKNOWN
