"""The doctor's long-path row reads the flag and weighs the workspace's depth (0.173.0, roadmap 227).

Until 0.173.0 it WARNed on every Windows machine without reading `LongPathsEnabled`, so it could
not pass where long paths were on, and where they were off it could not say whether a workspace
was deep enough to matter. Measured on cold runs 9222 and 9223 (`docs/findings/long_paths/` at the
factory root): a level writes files 217 characters below its workspace, and those workspaces, 69
characters deep, held 725 and 440 files past Windows' 260.
"""
import sys

from packages.adapters.registry import AdapterRegistry
from packages.tools import doctor

#: cold run 9223's workspace, where the 217 was measured
DEEP = "C:\\Projects\\gabagool_studios\\gabagool_factory\\workspaces\\cold-9223-ws"
SHORT = "C:\\gabagool\\levels"


def _row(report):
    rows = [c for c in report.checks if c.name == "windows_long_paths"]
    assert len(rows) == 1, [c.name for c in report.checks]
    return rows[0]


def test_the_measured_workspace_is_69_characters_and_its_deepest_file_287():
    assert len(DEEP) == 69
    assert len(DEEP) + 1 + doctor.LEVEL_DEPTH == 287


def test_long_paths_on_passes_at_any_depth():
    status, detail = doctor.long_paths_check(1, DEEP)
    assert status == doctor.PASS and "is 1" in detail


def test_long_paths_off_passes_a_short_workspace_and_says_how_far_it_reaches():
    status, detail = doctor.long_paths_check(0, SHORT)
    assert status == doctor.PASS, detail
    assert str(len(SHORT) + 1 + doctor.LEVEL_DEPTH) in detail and SHORT in detail


def test_long_paths_off_warns_a_deep_workspace_with_its_reach_the_budget_and_the_remedies():
    status, detail = doctor.long_paths_check(0, DEEP)
    assert status == doctor.WARN
    assert "287" in detail and "42" in detail
    assert "shorter folder" in detail and "administrator" in detail


def test_the_budget_is_exact_at_its_edge():
    edge = "C:\\" + "a" * (doctor.WINDOWS_MAX_PATH - 1 - doctor.LEVEL_DEPTH - 3)
    assert len(edge) == 42
    assert doctor.long_paths_check(0, edge)[0] == doctor.PASS
    assert doctor.long_paths_check(0, edge + "b")[0] == doctor.WARN


def test_an_unread_flag_passes_only_a_workspace_within_the_budget():
    assert doctor.long_paths_check(None, SHORT)[0] == doctor.PASS
    status, detail = doctor.long_paths_check(None, DEEP)
    assert status == doctor.WARN and "could not be read" in detail


def test_no_workspace_and_the_flag_off_warns_with_the_budget():
    status, detail = doctor.long_paths_check(0, None)
    assert status == doctor.WARN and "42" in detail


def test_run_doctor_reads_the_flag_and_weighs_the_workspace_it_is_given(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(doctor, "long_paths_enabled", lambda: 1)
    report = doctor.run_doctor({}, {}, registry=AdapterRegistry({}), workspace_root=DEEP)
    assert _row(report).status == doctor.PASS
    monkeypatch.setattr(doctor, "long_paths_enabled", lambda: 0)
    report = doctor.run_doctor({}, {}, registry=AdapterRegistry({}), workspace_root=DEEP)
    assert _row(report).status == doctor.WARN and "287" in _row(report).detail
    report = doctor.run_doctor({}, {}, registry=AdapterRegistry({}), workspace_root=SHORT)
    assert _row(report).status == doctor.PASS


def test_the_flag_reader_answers_1_0_or_none():
    assert doctor.long_paths_enabled() in (0, 1, None)
