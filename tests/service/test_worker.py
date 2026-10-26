"""The service worker's protocol v1 and its first operations (0.243.0, the factory's roadmap 310 and 311).

The Godot panel cannot call Python: it writes request.json into a run directory, runs `service-run`, and reads
events.jsonl and result.json. Every request that cannot run must still leave a result saying why -- an empty success
standing in for a failure is the defect the protocol exists to prevent -- and the result is written whole or not at
all. FAILS ON 0.242.0: no worker, no operations, no command.
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from packages.service import operations  # noqa: E402
from packages.service.worker import REQUEST_SCHEMA, RESULT_SCHEMA, RequestError, run_service  # noqa: E402


def _request(run_dir: Path, operation="discover_installation", arguments=None, **extra) -> None:
    req = {"schema": REQUEST_SCHEMA, "request_id": "r1", "operation": operation, "arguments": arguments or {}}
    req.update(extra)
    (run_dir / "request.json").write_text(json.dumps(req), encoding="utf-8")


def _result(run_dir: Path) -> dict:
    return json.loads((run_dir / "result.json").read_text(encoding="utf-8"))


def _events(run_dir: Path) -> list[dict]:
    p = run_dir / "events.jsonl"
    return [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines()] if p.exists() else []


@pytest.mark.parametrize("setup,code", [
    (lambda d: None, "request_missing"),
    (lambda d: (d / "request.json").write_text("{not json", encoding="utf-8"), "request_malformed"),
    (lambda d: (d / "request.json").write_text("[1, 2]", encoding="utf-8"), "request_malformed"),
    (lambda d: _request(d, schema="gabagool.service.request.v9"), "request_schema"),
    (lambda d: _request(d, extra_field=1), "request_unknown_keys"),
    (lambda d: _request(d, arguments=None, design_revision=True), "request_malformed"),
    (lambda d: _request(d, operation="make_me_a_sandwich"), "unknown_operation"),
    (lambda d: _request(d, arguments={"colour": "red"}), "unknown_arguments"),
])
def test_a_request_that_cannot_run_still_says_why(tmp_path, setup, code):
    setup(tmp_path)
    assert run_service(tmp_path) == 2
    r = _result(tmp_path)
    assert r["schema"] == RESULT_SCHEMA and r["status"] == "error" and r["data"] is None
    assert r["error"]["code"] == code and r["error"]["message"]


def test_an_operation_that_breaks_reports_it_and_leaves_no_half_file(tmp_path):
    def broken(arguments, events):
        events.emit("work", "running", "about to fail")
        raise ZeroDivisionError("nope")
    _request(tmp_path, operation="broken")
    assert run_service(tmp_path, {"broken": broken}) == 5
    r = _result(tmp_path)
    assert r["status"] == "error" and r["error"]["code"] == "internal_error"
    assert "ZeroDivisionError" in r["error"]["message"] and "traceback" in r["error"]
    assert not list(tmp_path.glob(".result.*.tmp"))
    assert [e["stage"] for e in _events(tmp_path)] == ["start", "work"]


def test_a_successful_operation_streams_events_and_returns_its_data(tmp_path):
    def echo(arguments, events):
        events.emit("half", "running", "halfway", progress=0.5)
        return {"echo": arguments, "dash": "—"}
    _request(tmp_path, operation="echo", arguments={"a": 1}, design_revision=3)
    assert run_service(tmp_path, {"echo": echo}) == 0
    r = _result(tmp_path)
    assert r["status"] == "ok" and r["error"] is None and r["design_revision"] == 3
    assert r["data"] == {"echo": {"a": 1}, "dash": "—"}          # UTF-8 through a file, not a console
    ev = _events(tmp_path)
    assert [e["stage"] for e in ev] == ["start", "half", "finish"] and [e["seq"] for e in ev] == [1, 2, 3]
    assert ev[1]["progress"] == 0.5 and all(e["request_id"] == "r1" for e in ev)


def test_discover_installation_answers_in_plain_language():
    events = type("E", (), {"emit": lambda self, *a, **k: None})()
    out = operations.discover_installation({}, events)
    assert Path(out["factory_root"]).joinpath("factory.manifest.json").is_file()
    names = {c["name"] for c in out["checks"]}
    assert {"python", "godot", "blender", "tool:deli_counter"} <= names
    for c in out["checks"]:
        assert c["label"] and c["readiness"] in ("ready", "warning", "missing", "problem")
        if c["readiness"] in ("missing", "problem"):
            assert c["fix"], c
    assert out["ready"] == (not out["blocking"])
    with pytest.raises(RequestError):
        operations.discover_installation({"blender": 3}, events)


def test_configure_installation_records_only_real_files(tmp_path, monkeypatch):
    from packages.tools import discovery
    monkeypatch.setattr(discovery, "factory_root", lambda start=None: tmp_path)
    events = type("E", (), {"emit": lambda self, *a, **k: None})()
    with pytest.raises(RequestError) as e:
        operations.configure_installation({"blender": str(tmp_path / "nope.exe")}, events)
    assert e.value.code == "not_a_file"
    exe = tmp_path / "blender.exe"
    exe.write_bytes(b"")
    operations.configure_installation({"blender": str(exe)}, events)
    rec = json.loads((tmp_path / discovery.LOCAL_FILE).read_text(encoding="utf-8"))
    assert rec["blender_executable"] == str(exe)


def test_service_run_is_a_command(tmp_path):
    _request(tmp_path)
    proc = subprocess.run([sys.executable, str(ROOT / "apps" / "cli" / "main.py"), "service-run", str(tmp_path)],
                          capture_output=True, timeout=300)
    r = _result(tmp_path)
    assert proc.returncode == 0 and r["status"] == "ok" and r["operation"] == "discover_installation"
    assert r["data"]["checks"]
