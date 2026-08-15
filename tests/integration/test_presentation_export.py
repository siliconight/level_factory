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
        "godot_executable": str(FIXTURES / "bin" / ("godot.cmd" if sys.platform.startswith("win") else "godot")),
        "blender_executable": str(FIXTURES / "bin" / ("godot.cmd" if sys.platform.startswith("win") else "godot")),
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


def _stage_status(stdout: str, mission_id: str) -> dict:
    """Map `<stage>[.<suffix>]` -> the status word the run printed for it.

    A run prints one indented line per job, `<mission>.<stage>  <status>`,
    where status is `succeeded`, `cache` or `failed`. Lines that do not
    begin with the mission id -- the candidate summary, the structural
    check total -- are not jobs and are skipped.
    """
    out: dict[str, str] = {}
    for line in stdout.splitlines():
        parts = line.split()
        if len(parts) < 2 or not parts[0].startswith(mission_id + "."):
            continue
        out[parts[0][len(mission_id) + 1:]] = parts[-1]
    return out


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
    # A stage NAME proves nothing. The run prints a status word at the end
    # of each job line, so `bank_block_001.presentation_compose  failed`
    # CONTAINS "presentation_compose" and satisfied `stage in r.stdout`.
    # Measured 2026-08-15: compose failed, six of these eight assertions
    # passed anyway, and the two that caught it did so only because their
    # stages never ran at all. Read the STATUS the line carries.
    status = _stage_status(r.stdout, "bank_block_001")
    for stage in ("pixelcoat_build", "zoo_kit_build", "patina_apply",
                  "patina_dressing", "zoo_dressing_build", "presentation_compose",
                  "lux_apply", "dispatch_handoff"):
        got = [s for jid, s in sorted(status.items())
               if jid == stage or jid.startswith(stage + ".")]
        assert got, f"missing stage {stage}\n{r.stdout}"
        assert all(s in ("succeeded", "cache") for s in got), \
            f"stage {stage} reported {got}\n{r.stdout}"

    # The compose stage produced the themed scene DC's composer emits, and Lux
    # lit THAT (not the greybox site) — the --art wiring under test.
    compose_out = (root / ".level_factory" / "jobs"
                   / "bank_block_001.presentation_compose" / "out")
    assert (compose_out / "presentation" / "site.tscn").exists()

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
    # 0.26.0/0.27.0 renamed both of these on purpose -- see
    # docs/EXPORT_NAMING.md for why there are three names and not one.
    # The build directory KEEPS the profile so two modes can coexist in
    # one workspace; it is spelled out literally here rather than
    # imported from `export_build_dir_name`, because a test that asks
    # the code for the name it expects passes whatever the code does.
    build_dir = exports / "LF_bank_block_001.portable-godot"
    assert build_dir.is_dir(), (
        f"no build dir; exports/ holds "
        f"{sorted(p.name for p in exports.glob('*'))}")
    # Loose ON PURPOSE, and tight enough to fail: the archive rewrites
    # its members under an interior `LF_<mission>/` and it has not been
    # observed whether a FOLDER export nests one too. Search, and print
    # the real tree when it is not there.
    handoffs = sorted(p.relative_to(build_dir).as_posix()
                      for p in build_dir.rglob("HANDOFF.md"))
    assert handoffs, (
        f"no HANDOFF.md in {build_dir.name}; it holds "
        f"{sorted(p.relative_to(build_dir).as_posix() for p in build_dir.rglob('*'))}")
    # The archive is fully qualified -- seed, UTC instant, factory
    # version -- so it cannot be spelled literally. Match the shape, and
    # require exactly one: two would mean an export did not replace its
    # predecessor, which is the failure the old single name hid.
    zips = sorted(p.name for p in exports.glob(
        "LF_bank_block_001_s*_f*_pure-shell.zip"))
    assert len(zips) == 1, (
        f"expected exactly one pure-shell archive, got {zips}; "
        f"exports/ holds {sorted(p.name for p in exports.glob('*'))}")

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
