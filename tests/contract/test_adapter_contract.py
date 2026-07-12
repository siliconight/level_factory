"""Shared adapter contract suite (TDD 37.2).

Every adapter must satisfy these invariants regardless of the tool it wraps.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from packages.adapters.registry import build_default_registry
from packages.adapters.sdk import PlannedCommand, ToolAdapter

ADAPTERS = build_default_registry()


@pytest.mark.parametrize("adapter_id", sorted(ADAPTERS))
def test_adapter_implements_protocol(adapter_id):
    adapter = ADAPTERS[adapter_id]
    assert isinstance(adapter, ToolAdapter)
    assert adapter.adapter_id == adapter_id
    assert adapter.adapter_version
    assert adapter.capabilities


@pytest.mark.parametrize("adapter_id", sorted(ADAPTERS))
def test_probe_missing_tool_reports_unavailable(adapter_id):
    probe = ADAPTERS[adapter_id].probe({"repository": "/nonexistent/path/xyz"})
    assert probe.available is False
    assert probe.problems


@pytest.mark.parametrize("adapter_id", sorted(ADAPTERS))
def test_invalid_configuration_is_reported_not_fixed(adapter_id):
    # Empty job spec + empty context should surface problems, never silently pass.
    problems = ADAPTERS[adapter_id].validate_configuration({}, {})
    assert isinstance(problems, (list, tuple))
    assert len(problems) >= 1


@pytest.mark.parametrize("adapter_id", sorted(ADAPTERS))
def test_commands_are_argument_arrays(adapter_id, tmp_path):
    adapter = ADAPTERS[adapter_id]
    repo = tmp_path / "repo"; repo.mkdir()
    work = tmp_path / "work"; work.mkdir()
    ctx = {
        "repository": str(repo), "work_dir": str(work),
        "blender_executable": str(tmp_path / "blender"),
        "godot_executable": str(tmp_path / "godot"),
        "python_executable": "python3",
        "godot_project": str(work),
    }
    spec = {
        "seed": 1997, "archetype": "bank", "theme": "delco",
        "building_glbs": [str(work / "b.glb")], "lights_jsons": [],
        "evaluation_scene": str(work / "s.tscn"),
        "mission_spec_path": str(work / "m.json"), "mode": "shell-handoff",
        "site_shape": "block", "route_shape": "push", "target_minutes": [25, 35],
    }
    for p in ("b.glb", "s.tscn", "m.json"):
        (work / p).write_text("x")
    commands = adapter.plan_commands(spec, ctx)
    assert commands
    for cmd in commands:
        assert isinstance(cmd, PlannedCommand)
        assert isinstance(cmd.arguments, tuple)
        assert all(isinstance(a, str) for a in cmd.argv())
        assert cmd.resource_class


@pytest.mark.parametrize("adapter_id", sorted(ADAPTERS))
def test_fingerprint_is_stable(adapter_id, tmp_path):
    adapter = ADAPTERS[adapter_id]
    work = tmp_path / "w"; work.mkdir()
    for p in ("b.glb", "s.tscn", "m.json"):
        (work / p).write_text("x")
    spec = {"seed": 1, "building_glbs": [str(work / "b.glb")],
            "evaluation_scene": str(work / "s.tscn"),
            "mission_spec_path": str(work / "m.json")}
    ctx = {"work_dir": str(work)}
    a = adapter.fingerprint_inputs(spec, ctx)
    b = adapter.fingerprint_inputs(spec, ctx)
    assert dict(a) == dict(b)
