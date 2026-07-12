"""Headless application-service tests (TDD 9.1, 27).

These exercise the full FactoryService without Qt: query methods return correct
view-models, and action methods drive the same orchestration the CLI does,
including the export regression block.
"""
import io
import json
import sys
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests" / "fixtures"
sys.path.insert(0, str(ROOT))

from packages.project_store.workspace import init_workspace  # noqa: E402
from packages.service.facade import FactoryService  # noqa: E402

_REPOS = ("deli_counter", "lot", "laser_tag", "pixelcoat", "zoo", "patina", "lux", "dispatch")


def _make_ws(root: Path):
    ws = init_workspace(root, project_id="t", name="Svc")
    ws.write_json(ws.tools_local, {
        "python_executable": sys.executable,
        "godot_executable": str(FIXTURES / "bin" / ("godot.cmd" if sys.platform.startswith("win") else "godot")),
        "blender_executable": str(FIXTURES / "bin" / ("godot.cmd" if sys.platform.startswith("win") else "godot")),
        "repositories": {r: str(FIXTURES / "repos" / r) for r in _REPOS},
    })
    (ws.shared_dir / "pixelcoat" / "recipes").mkdir(parents=True)
    (ws.shared_dir / "pixelcoat" / "recipes" / "b.json").write_text('{"recipe":"b"}')
    src = root.parent / "src"
    (src / "briefs").mkdir(parents=True)
    (src / "batch.json").write_text(json.dumps({
        "schema": "level_factory.batch.v0.1", "batch_id": "b1", "name": "B",
        "seed_base": 1997, "theme_family": "delco_1997", "missions": ["m1"]}))
    (src / "briefs" / "m1.json").write_text(json.dumps({
        "schema": "level_factory.mission_brief.v0.1", "mission_id": "m1",
        "display_name": "M1", "archetype": "urban_bank", "building_count": 1,
        "site_shape": "street_block", "route_shape": "push_then_backtrack",
        "candidate_count": 3, "target_minutes": [25, 35], "theme": "delco_1997",
        "time_of_day": "afternoon"}))
    from apps.cli.commands import cmd_batch_create
    with redirect_stdout(io.StringIO()):
        cmd_batch_create(SimpleNamespace(chdir=str(ws.root), batch_json=str(src / "batch.json")))
    return ws, src


@pytest.fixture(scope="module")
def prepared(tmp_path_factory):
    root = tmp_path_factory.mktemp("svc") / "ws"
    ws, _ = _make_ws(root)
    svc = FactoryService(ws)
    svc.run("m1", "functional-lock")
    svc.approve("m1", "brief_approved")
    svc.select_candidate("m1", "m1.candidate.seed_1997")
    svc.approve("m1", "functional_shell_locked")
    svc.run("m1", "presentation")
    return svc


def test_doctor_passes(prepared):
    report = prepared.doctor()
    assert report["worst"] in ("PASS", "WARN")


def test_dashboard_reflects_state(prepared):
    rows = prepared.dashboard()
    assert len(rows) == 1
    row = rows[0]
    assert row.mission_id == "m1"
    assert row.selected_candidate == "m1.candidate.seed_1997"
    assert row.presentation_status == "ready"
    assert row.handoff_status == "ready"
    assert "functional_shell_locked" in row.approved_gates


def test_pipeline_has_presentation_nodes(prepared):
    nodes = prepared.pipeline("m1", "presentation")
    stages = {n.stage_id for n in nodes}
    assert {"pixelcoat_build", "zoo_kit_build", "lux_apply", "dispatch_handoff"} <= stages
    assert all(n.state in ("SUCCEEDED", "SKIPPED_CACHE_HIT", "PLANNED") for n in nodes)


def test_candidates_have_metrics(prepared):
    cards = prepared.candidates("m1")
    assert len(cards) == 3
    assert all(c.candidate_id.startswith("m1.candidate.seed_") for c in cards)


def test_art_pass_sections_done(prepared):
    sections = prepared.art_pass("m1")
    names = {s.name for s in sections}
    assert "Lux profiles" in names
    assert all(s.status == "done" for s in sections)


def test_handoff_table_matches_spec(prepared):
    status = prepared.handoff("m1")
    labels = [r.label for r in status.rows]
    assert "Gameplay Anchors" in labels
    assert "Gameplay Runtime" in labels  # by-design row present
    assert status.export_ready
    assert "Export folder" in status.available_actions


def test_job_console_reads_a_job(prepared):
    jc = prepared.job_console("m1.lux_apply")
    assert jc is not None
    assert jc.state == "SUCCEEDED"
    assert jc.resource_class == "godot_headless"


def test_node_detail_lists_outputs(prepared):
    detail = prepared.node_detail("m1", "m1.lux_apply", "presentation")
    assert detail.state == "SUCCEEDED"
    assert "lux.applied.tscn" in detail.outputs


def test_seed_preview_is_deterministic(prepared):
    assert prepared.seed_preview("m1", 1997, 3) == [1997, 2098, 2199]


def test_validate_brief_flags_missing_fields(prepared):
    problems = prepared.validate_brief({"archetype": "bank"})
    assert any("mission_id" in p for p in problems)


def test_export_and_portability_via_service(prepared):
    exp = prepared.export("m1", "portable-godot", "folder")
    assert exp.exit_code == 0
    port = prepared.portability_test("m1", "portable-godot")
    assert port.exit_code == 0


def test_regression_blocks_export_via_service(tmp_path):
    ws, _ = _make_ws(tmp_path / "ws")
    svc = FactoryService(ws)
    svc.run("m1", "functional-lock")
    svc.approve("m1", "brief_approved")
    svc.select_candidate("m1", "m1.candidate.seed_1997")
    svc.approve("m1", "functional_shell_locked")
    svc.run("m1", "presentation")
    # Inject functional drift after the art pass.
    site = (ws.jobs_dir / "m1.lot_assemble.candidate.seed_1997" / "out" / "site.site.gameplay.json")
    data = json.loads(site.read_text())
    data["stair_systems"] = [{"id": "INJECTED"}]
    site.write_text(json.dumps(data))
    result = svc.export("m1", "portable-godot", "folder")
    assert result.blocked
    assert result.exit_code == 2


def test_batch_run_and_report_via_service(tmp_path):
    ws, _ = _make_ws(tmp_path / "ws")
    svc = FactoryService(ws)
    svc.run("m1", "functional-lock")
    svc.approve("m1", "brief_approved")
    svc.select_candidate("m1", "m1.candidate.seed_1997")
    svc.approve("m1", "functional_shell_locked")
    r = svc.run_batch("b1", "presentation")
    assert r.exit_code == 0, r.output
    assert "1 shared job(s)" in r.output
    rep = svc.batch_report("b1")
    assert rep.exit_code == 0
    assert "theme.pack.json" in rep.output
