"""Phase-2 end-to-end: locked shell -> presentation -> export -> portability.

Proves the Phase-2 exit criteria (TDD 42):
  * one mission runs from a locked shell through the full PS2 presentation
    (Pixelcoat/Zoo/Patina/Lux) and the Dispatch handoff
  * the mission exports in portable-godot and pure-shell modes
  * the clean-project portability test passes
  * a functional regression after the art pass blocks export
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests" / "fixtures"
sys.path.insert(0, str(ROOT))

from packages.project_store.workspace import init_workspace  # noqa: E402

_PRES_REPOS = ("deli_counter", "lot", "laser_tag",
               "pixelcoat", "zoo", "patina", "lux", "dispatch")


def _installation() -> dict:
    return {
        "python_executable": sys.executable,
        "godot_executable": str(FIXTURES / "bin" / "godot"),
        "blender_executable": str(FIXTURES / "bin" / "godot"),
        "repositories": {r: str(FIXTURES / "repos" / r) for r in _PRES_REPOS},
    }


@pytest.fixture()
def workspace(tmp_path):
    ws = init_workspace(tmp_path / "ws", project_id="test", name="P2 Factory")
    ws.write_json(ws.tools_local, _installation())
    # Shared Pixelcoat recipes (batch-level asset).
    (ws.shared_dir / "pixelcoat" / "recipes").mkdir(parents=True)
    (ws.shared_dir / "pixelcoat" / "recipes" / "brick.json").write_text('{"recipe":"brick"}')

    batch = {
        "schema": "level_factory.batch.v0.1", "batch_id": "batch_001",
        "name": "P2 Batch", "seed_base": 1997, "theme_family": "delco_1997",
        "missions": ["bank_block_001"],
    }
    src = tmp_path / "batch_src"
    (src / "briefs").mkdir(parents=True)
    (src / "batch.json").write_text(json.dumps(batch))
    (src / "briefs" / "bank_block_001.json").write_text(json.dumps({
        "schema": "level_factory.mission_brief.v0.1",
        "mission_id": "bank_block_001", "display_name": "Bank Block",
        "archetype": "urban_bank", "building_count": 1,
        "site_shape": "street_block", "route_shape": "push_then_backtrack",
        "candidate_count": 3, "target_minutes": [25, 35],
        "theme": "delco_1997", "time_of_day": "afternoon",
    }))
    return ws, src


def _cli(ws_root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(ROOT / "apps" / "cli" / "main.py"), "-C", str(ws_root), *args],
        capture_output=True, text=True,
    )


def test_presentation_export_and_portability(workspace):
    ws, src = workspace
    root = ws.root

    assert _cli(root, "batch", "create", str(src / "batch.json")).returncode == 0
    assert _cli(root, "run", "bank_block_001", "--target", "functional-lock").returncode in (0, 1)

    _cli(root, "approve", "bank_block_001", "brief_approved")
    cand = "bank_block_001.candidate.seed_1997"
    assert _cli(root, "approve", "bank_block_001", "candidate_selected",
                "--candidate", cand).returncode == 0
    assert _cli(root, "approve", "bank_block_001", "functional_shell_locked").returncode == 0

    # Presentation run: all four presentation tools + Lux + Dispatch.
    r = _cli(root, "run", "bank_block_001", "--target", "presentation")
    assert r.returncode in (0, 1), r.stderr + r.stdout
    for stage in ("pixelcoat_build", "zoo_kit_build", "patina_apply",
                  "patina_dressing", "zoo_dressing_build", "lux_apply",
                  "dispatch_handoff"):
        assert stage in r.stdout, f"missing stage {stage}"

    # Lux applied a presentation-only scene.
    lux_out = root / ".level_factory" / "jobs" / "bank_block_001.lux_apply" / "out"
    assert (lux_out / "lux.applied.tscn").exists()
    assert (lux_out / "lux.quality.json").exists()

    # Export portable-godot (folder) + pure-shell (zip).
    r = _cli(root, "export", "bank_block_001", "--mode", "portable-godot", "--format", "folder")
    assert r.returncode == 0, r.stderr + r.stdout
    r = _cli(root, "export", "bank_block_001", "--mode", "pure-shell", "--format", "zip")
    assert r.returncode == 0, r.stderr + r.stdout
    exports = root / ".level_factory" / "exports"
    assert (exports / "bank_block_001.portable-godot" / "HANDOFF.md").exists()
    assert (exports / "bank_block_001.zip").exists()

    # Clean-project portability test passes.
    r = _cli(root, "portability-test", "bank_block_001", "--mode", "portable-godot")
    assert r.returncode == 0, r.stderr + r.stdout
    report = json.loads(r.stdout)
    assert report["status"] == "PASS"
    assert report["absolute_path_count"] == 0
    assert report["scene_instantiated"] is True


def test_functional_regression_blocks_export(workspace):
    ws, src = workspace
    root = ws.root

    assert _cli(root, "batch", "create", str(src / "batch.json")).returncode == 0
    assert _cli(root, "run", "bank_block_001", "--target", "functional-lock").returncode in (0, 1)
    _cli(root, "approve", "bank_block_001", "brief_approved")
    cand = "bank_block_001.candidate.seed_1997"
    _cli(root, "approve", "bank_block_001", "candidate_selected", "--candidate", cand)
    _cli(root, "approve", "bank_block_001", "functional_shell_locked")
    _cli(root, "run", "bank_block_001", "--target", "presentation")

    # Illegally move collision AFTER the art pass.
    site = (root / ".level_factory" / "jobs"
            / "bank_block_001.lot_assemble.candidate.seed_1997" / "out" / "site.site.gameplay.json")
    data = json.loads(site.read_text())
    data["stair_systems"] = [{"id": "INJECTED", "role": "primary"}]
    site.write_text(json.dumps(data))

    r = _cli(root, "export", "bank_block_001", "--mode", "portable-godot", "--format", "folder")
    assert r.returncode == 2, "expected export blocked by functional regression"
    assert "regression" in (r.stderr + r.stdout).lower()
