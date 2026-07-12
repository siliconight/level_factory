"""Offscreen PySide6 smoke test (TDD 27, Phase 3).

Qt is exercised in a SUBPROCESS via `python -m apps.desktop --self-check`, so the
real Qt runtime never loads into the pytest process (which avoids a Qt teardown
crash at interpreter exit when threads from the parallel scheduler are present).
The child builds the real main window under the offscreen platform, drives every
screen, and prints a summary the test asserts on. Skips cleanly when PySide6
isn't installed (the desktop is an optional extra; the core never imports Qt).
"""
import io
import json
import subprocess
import sys
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests" / "fixtures"
sys.path.insert(0, str(ROOT))

pytest.importorskip("PySide6", reason="desktop is an optional Phase 3 dependency")

from packages.project_store.workspace import init_workspace  # noqa: E402
from packages.service.facade import FactoryService  # noqa: E402

_REPOS = ("deli_counter", "lot", "laser_tag", "pixelcoat", "zoo", "patina", "lux", "dispatch")


@pytest.fixture(scope="module")
def prepared_ws(tmp_path_factory):
    root = tmp_path_factory.mktemp("desk") / "ws"
    ws = init_workspace(root, project_id="t", name="Desk")
    ws.write_json(ws.tools_local, {
        "python_executable": sys.executable,
        "godot_executable": str(FIXTURES / "bin" / "godot"),
        "blender_executable": str(FIXTURES / "bin" / "godot"),
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
    svc = FactoryService(ws)
    svc.run("m1", "functional-lock")
    svc.approve("m1", "brief_approved")
    svc.select_candidate("m1", "m1.candidate.seed_1997")
    svc.approve("m1", "functional_shell_locked")
    svc.run("m1", "presentation")
    return ws


def test_desktop_self_check_subprocess(prepared_ws):
    """Build the real window offscreen in a child process and drive all screens."""
    proc = subprocess.run(
        [sys.executable, "-m", "apps.desktop", "--self-check", str(prepared_ws.root)],
        capture_output=True, text=True, cwd=str(ROOT),
        env={**__import__("os").environ, "QT_QPA_PLATFORM": "offscreen"},
    )
    out = proc.stdout + proc.stderr
    assert proc.returncode == 0, out
    assert "SELFCHECK OK" in out, out
    # Every screen populated from the service.
    assert "dashboard=1" in out
    assert "pipeline=16" in out
    assert "candidates=3" in out
    assert "handoff=11" in out
    assert "console=16" in out
