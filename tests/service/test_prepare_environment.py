"""The panel prepares the tools' Python itself (0.244.0, the factory's roadmap 311, increment 2).

Increment 1's dock named the blocker a new user meets first on this machine -- the launcher runs the factory on
Blender's own Python, which cannot import PIL, pygltflib or jsonschema -- and its fix was `factory setup --venv`, a
terminal step. `prepare_environment` is that step as a service operation. These tests drive it with a fake `run`
so nothing is downloaded; FAILS ON 0.243.0.
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from packages.service import operations  # noqa: E402
from packages.service.worker import EventSink, RequestError  # noqa: E402


def _factory(tmp_path, monkeypatch, made="ok"):
    from packages.tools import discovery, interpreter
    monkeypatch.setattr(discovery, "factory_root", lambda start=None: tmp_path)
    (tmp_path / discovery.LOCAL_FILE).write_text(json.dumps({
        "schema": discovery.LOCAL_SCHEMA, "blender_executable": "B", "godot_executable": "G",
        "python_executable": ""}), encoding="utf-8")
    calls = []

    def fake_make_venv(root, base, *, run=None, timeout=1800):
        calls.append((root, base))
        # what make_venv's pip step does with the run it is given: a command whose output streams
        run([sys.executable, "-c", "print('Collecting pillow'); print('Successfully installed pillow')"])
        if made != "ok":
            return "", made
        return str(tmp_path / ".venv" / "Scripts" / "python.exe"), ""
    monkeypatch.setattr(interpreter, "make_venv", fake_make_venv)
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    return EventSink(run_dir, "r", "prepare_environment"), calls


def test_it_makes_the_environment_records_it_and_streams_pip(tmp_path, monkeypatch):
    from packages.tools import discovery
    sink, calls = _factory(tmp_path, monkeypatch)
    out = operations.prepare_environment({}, sink)
    assert calls == [(tmp_path, sys.executable)]
    rec = json.loads((tmp_path / discovery.LOCAL_FILE).read_text(encoding="utf-8"))
    assert rec["python_executable"].endswith("python.exe")
    assert (rec["blender_executable"], rec["godot_executable"]) == ("B", "G")       # kept
    events = [json.loads(x) for x in sink.path.read_text(encoding="utf-8").splitlines()]
    said = [e["message"] for e in events if e["stage"] == "install"]
    assert "Collecting pillow" in said and "Successfully installed pillow" in said
    assert "Successfully installed pillow" in (sink.path.parent / "pip.log").read_text(encoding="utf-8")
    assert "checks" in out


def test_a_failed_install_is_a_refusal_that_says_which_step(tmp_path, monkeypatch):
    from packages.tools import discovery
    sink, _calls = _factory(tmp_path, monkeypatch, made="pip install pillow==12.3.0 exited 1")
    with pytest.raises(RequestError) as e:
        operations.prepare_environment({}, sink)
    assert e.value.code == "environment_failed" and "pip install" in str(e.value)
    rec = json.loads((tmp_path / discovery.LOCAL_FILE).read_text(encoding="utf-8"))
    assert rec["python_executable"] == ""                                      # nothing recorded


def test_it_takes_no_arguments(tmp_path, monkeypatch):
    sink, _calls = _factory(tmp_path, monkeypatch)
    with pytest.raises(RequestError):
        operations.prepare_environment({"force": True}, sink)


def test_the_tools_python_fix_names_the_button():
    assert "Prepare environment" in operations.FIXES["tools_python"]
