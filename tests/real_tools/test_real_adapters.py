"""Drive the REAL Siliconight tools through the rebound Level Factory adapters.

Each test resolves the real repo, builds the adapter's planned command, runs it
against the tool's own bundled example, and asserts the adapter's expected
outputs are produced. This is the TDD 37.5 real-tool smoke — it proves the
adapters invoke the real CLIs correctly (not just the stubs).

Run with:  LF_TOOLS_DIR=/path/to/tools pytest tests/real_tools -q
"""
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def _run_adapter(adapter, job_spec, repo, work):
    ctx = {"repository": str(repo), "work_dir": str(work),
           "python_executable": sys.executable}
    problems = adapter.validate_configuration(job_spec, ctx)
    assert not problems, problems
    cmd = adapter.plan_commands(job_spec, ctx)[0]
    env = {**os.environ, "PYTHONPATH": str(repo)}
    proc = subprocess.run(cmd.argv(), cwd=str(cmd.working_directory), env=env,
                          capture_output=True, text=True, timeout=300)
    outs = list(adapter.collect_outputs(job_spec, ctx))
    names = {p.name for p in outs}
    return proc, cmd, outs, names


def test_real_dispatch(tool_root):
    from adapters.dispatch import DispatchAdapter
    repo = tool_root("dispatch/__main__.py")
    # dispatch package lives at <root>/dispatch; the mission example is bundled.
    example = repo / "examples" / "gas_station_robbery_001" / "dispatch.mission.json"
    if not example.exists():
        pytest.skip("dispatch example mission not present")
    adapter = DispatchAdapter()
    # Probe the real contract command.
    probe = adapter.probe({"repository": str(repo), "python_executable": sys.executable})
    assert probe.available, probe.problems
    assert probe.tool_version  # real version string from `dispatch contract`

    work = repo / "_lf_smoke_out"
    job = {"mission_spec_path": str(example), "mode": "shell-handoff", "inputs": {}}
    proc, cmd, outs, names = _run_adapter(adapter, job, repo, work)
    assert proc.returncode == 0, (proc.stdout + proc.stderr)[-800:]
    assert set(cmd.expected_outputs) <= names, set(cmd.expected_outputs) - names
    # The adapter's real validation normalization runs on real outputs.
    issues = adapter.normalize_validation(outs)
    assert all("code" in i for i in issues)


def test_real_lot(tool_root, tmp_path):
    from adapters.lot import LotAdapter
    repo = tool_root("lot.py")
    spec = repo / "specs" / "gs_heist.json"
    if not spec.exists():
        pytest.skip("lot example spec not present")
    adapter = LotAdapter()
    job = {"site_spec_path": str(spec), "walkable": True}
    proc, cmd, outs, names = _run_adapter(adapter, job, repo, tmp_path / "out")
    assert proc.returncode == 0, (proc.stdout + proc.stderr)[-800:]
    assert set(cmd.expected_outputs) <= names, set(cmd.expected_outputs) - names
    # Pacing is surfaced as a non-blocking estimate.
    issues = adapter.normalize_validation(outs)
    assert all(not i["blocking"] or i["severity"] == "blocker" for i in issues)


def test_real_patina(tool_root, tmp_path):
    from adapters.patina import PatinaAdapter
    repo = tool_root("patina/cli.py")
    glb = repo / "examples" / "shell.glb"
    if not glb.exists():
        pytest.skip("patina example shell.glb not present")
    adapter = PatinaAdapter()
    job = {"input_glb": str(glb), "art_mode": "vertex-color", "theme": "default"}
    work = tmp_path / "out"; work.mkdir()
    proc, cmd, outs, names = _run_adapter(adapter, job, repo, work)
    assert proc.returncode == 0, (proc.stdout + proc.stderr)[-800:]
    assert set(cmd.expected_outputs) <= names, set(cmd.expected_outputs) - names
    # Patina must preserve collision (prints "collision N tris (untouched)").
    assert "untouched" in (proc.stdout + proc.stderr)
