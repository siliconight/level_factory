"""An open blocker blocks the export.

Cold run 9015 (2026-09-12): the Lux stage exited 2 on a site scene it could
not parse, the scheduler filed `JOB_TOOL_EXIT` as a blocking finding in the
mission's validation file, and `export` shipped the mission anyway -- a
package with no lighting, walked black. The finding existed; nothing that
ships read it. `_open_blockers` is the read, and `cmd_export` refuses on it.
"""
import inspect
import json
from types import SimpleNamespace

import apps.cli.commands as cmds


def _ws(tmp_path):
    return SimpleNamespace(internal_dir=tmp_path / "internal")


def _write(tmp_path, issues):
    v = tmp_path / "internal" / "validation"
    v.mkdir(parents=True, exist_ok=True)
    (v / "m.json").write_text(json.dumps({"mission_id": "m", "issues": issues}),
                              encoding="utf-8")


def test_a_blocking_finding_is_listed_with_code_stage_and_message(tmp_path):
    _write(tmp_path, [
        {"code": "JOB_TOOL_EXIT", "blocking": True, "location": "m.lux_apply",
         "message": "tool exited 2"},
        {"code": "LT_MAP_OVEREXPOSED_ZONE", "blocking": False, "message": "advisory"},
    ])
    out = cmds._open_blockers(_ws(tmp_path), "m")
    assert out == ["JOB_TOOL_EXIT at m.lux_apply: tool exited 2"]


def test_a_layer_the_package_reports_absent_does_not_block(tmp_path):
    """The Layer 3 chain says its own absence in `dressing_layer.json`; a
    blocker there is a finding about a layer the export already declares
    missing. Lux is not that: a package without its lighting says nothing."""
    _write(tmp_path, [
        {"code": "JOB_TOOL_EXIT", "blocking": True,
         "location": "m.lot_site_surfaces", "message": "tool exited 1"},
        {"code": "ZOO_HABITAT_REFUSED", "blocking": True,
         "stage_id": "zoo_clutter_build", "message": "needs habitat"},
        {"code": "JOB_TOOL_EXIT", "blocking": True,
         "location": "m.patina_surface_dressing", "message": "tool exited 1"},
        {"code": "JOB_TOOL_EXIT", "blocking": True, "location": "m.lux_apply",
         "message": "tool exited 2"},
    ])
    assert cmds._open_blockers(_ws(tmp_path), "m") == [
        "JOB_TOOL_EXIT at m.lux_apply: tool exited 2"]
    assert cmds.EXPORT_SELF_REPORTING_STAGES == {
        "lot_site_surfaces", "zoo_clutter_build", "patina_surface_dressing"}


def test_no_blockers_means_an_empty_list(tmp_path):
    _write(tmp_path, [{"code": "X", "blocking": False}])
    assert cmds._open_blockers(_ws(tmp_path), "m") == []
    assert cmds._open_blockers(_ws(tmp_path), "never_ran") == []


def test_the_export_command_reads_it_before_anything_ships():
    src = inspect.getsource(cmds.cmd_export)
    assert "_open_blockers(ws, mission_id)" in src
    # the refusal comes before the functional-lock check, which is the next
    # gate; a refusal after the package is written would be a package
    assert src.index("_open_blockers(") < src.index("_lock_path(ws, mission_id)")
    assert "return EXIT_BLOCKED" in src[src.index("_open_blockers("):
                                        src.index("_lock_path(ws, mission_id)")]
