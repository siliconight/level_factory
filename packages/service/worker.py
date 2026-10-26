"""The service worker: one operation per run directory, for a client that is not Python (the Godot panel).

PROTOCOL v1 (the factory's roadmap 310; `docs/AUTHORING_LOOP.md`). A client makes a fresh directory, writes
``request.json`` into it, and runs ``factory service-run <dir>``. The worker:

  * reads ``request.json`` -- ``{"schema": "gabagool.service.request.v1", "request_id": str, "operation": str,
    "arguments": {...}}`` and optionally ``"design_revision": int`` -- and refuses any other top-level key;
  * appends progress to ``events.jsonl``, one complete JSON object a line (``gabagool.service.event.v1``);
  * writes ``result.json`` (``gabagool.service.result.v1``) LAST and atomically: a temporary file in the same
    directory, then ``os.replace``. A client that sees ``result.json`` sees all of it.

Every file is UTF-8. Nothing is read from stdout: the doctor's JSON on stdout reached Windows' console encoding and
its em dashes arrived as U+FFFD, and a client parsing log text is the dependency this protocol removes.

A request that cannot run -- missing, unreadable, malformed, another schema, an unknown operation, arguments the
operation refuses -- still produces a result, with ``status: "error"`` and an ``error`` naming the reason. An empty
success is never a stand-in for a failure. The exit code mirrors the result (0 ok, 2 refused request, 5 internal
error) for a caller that only has the code; the result file is the answer.
"""
from __future__ import annotations

import json
import os
import time
import traceback
import uuid
from pathlib import Path

REQUEST_SCHEMA = "gabagool.service.request.v1"
RESULT_SCHEMA = "gabagool.service.result.v1"
EVENT_SCHEMA = "gabagool.service.event.v1"
REQUEST_KEYS = {"schema", "request_id", "operation", "arguments", "design_revision"}
#: A request is a few fields; anything near this is not one.
MAX_REQUEST_BYTES = 1 << 20

EXIT_OK, EXIT_REFUSED, EXIT_INTERNAL = 0, 2, 5


class RequestError(ValueError):
    """The request cannot run as written; ``code`` is the stable reason a client branches on."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime())


class EventSink:
    """Appends progress events to ``events.jsonl``. Each event is one ``write`` of one line, so a reader polling
    the file sees whole lines or none of the last one; a reader keeps a partial last line for its next poll."""

    def __init__(self, run_dir: Path, request_id: str, operation: str) -> None:
        #: ``events.jsonl``; its folder is the run directory an operation may write its own logs into
        self.path = run_dir / "events.jsonl"
        self.request_id = request_id
        self.operation = operation
        self.seq = 0

    def emit(self, stage: str, status: str, message: str = "", progress: float | None = None,
             **extra) -> None:
        self.seq += 1
        event = {"schema": EVENT_SCHEMA, "request_id": self.request_id, "operation": self.operation,
                 "seq": self.seq, "time": _now(), "stage": stage, "status": status, "message": message}
        if progress is not None:
            event["progress"] = max(0.0, min(1.0, float(progress)))
        event.update(extra)
        with open(self.path, "a", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")
            f.flush()


def write_result(run_dir: Path, result: dict) -> Path:
    """Write ``result.json`` atomically: the whole file or none of it."""
    path = run_dir / "result.json"
    tmp = run_dir / (".result.%s.tmp" % uuid.uuid4().hex)
    tmp.write_text(json.dumps(result, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    os.replace(tmp, path)
    return path


def read_request(run_dir: Path) -> dict:
    """The request, validated as protocol v1, or `RequestError`."""
    path = run_dir / "request.json"
    if not path.is_file():
        raise RequestError("request_missing", "no request.json in %s" % run_dir)
    raw = path.read_bytes()
    if len(raw) > MAX_REQUEST_BYTES:
        raise RequestError("request_too_large", "request.json is %d bytes; the limit is %d"
                           % (len(raw), MAX_REQUEST_BYTES))
    try:
        req = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RequestError("request_malformed", "request.json is not UTF-8 JSON: %s" % exc) from None
    if not isinstance(req, dict):
        raise RequestError("request_malformed", "request.json is not an object")
    if req.get("schema") != REQUEST_SCHEMA:
        raise RequestError("request_schema", "schema is %r; this worker reads %r"
                           % (req.get("schema"), REQUEST_SCHEMA))
    unknown = sorted(set(req) - REQUEST_KEYS)
    if unknown:
        raise RequestError("request_unknown_keys", "unknown keys: %s" % ", ".join(unknown))
    if not isinstance(req.get("request_id"), str) or not req["request_id"]:
        raise RequestError("request_malformed", "request_id must be a non-empty string")
    if not isinstance(req.get("operation"), str) or not req["operation"]:
        raise RequestError("request_malformed", "operation must be a non-empty string")
    args = req.get("arguments", {})
    if not isinstance(args, dict):
        raise RequestError("request_malformed", "arguments must be an object")
    rev = req.get("design_revision")
    if rev is not None and (isinstance(rev, bool) or not isinstance(rev, int) or rev < 0):
        raise RequestError("request_malformed", "design_revision must be a non-negative integer")
    req["arguments"] = args
    return req


def _version() -> str:
    try:
        return (Path(__file__).resolve().parents[2] / "VERSION").read_text(encoding="utf-8").strip()
    except OSError:
        return "unknown"


def run_service(run_dir: Path, operations: dict | None = None) -> int:
    """Run the request in ``run_dir`` and write its result. Returns the exit code the result mirrors."""
    from packages.service import operations as ops_module
    ops = operations if operations is not None else ops_module.OPERATIONS
    run_dir = Path(run_dir)
    started = _now()
    base = {"schema": RESULT_SCHEMA, "request_id": None, "operation": None, "design_revision": None,
            "started_at": started, "level_factory": _version()}
    if not run_dir.is_dir():
        # nowhere to write a result: the one failure only the exit code can carry
        return EXIT_REFUSED
    try:
        req = read_request(run_dir)
        base.update(request_id=req["request_id"], operation=req["operation"],
                    design_revision=req.get("design_revision"))
        fn = ops.get(req["operation"])
        if fn is None:
            raise RequestError("unknown_operation", "no operation %r; known: %s"
                               % (req["operation"], ", ".join(sorted(ops))))
        sink = EventSink(run_dir, req["request_id"], req["operation"])
        sink.emit("start", "running")
        data = fn(req["arguments"], sink)
        sink.emit("finish", "ok")
        write_result(run_dir, dict(base, status="ok", data=data, error=None, finished_at=_now()))
        return EXIT_OK
    except RequestError as exc:
        write_result(run_dir, dict(base, status="error", data=None, finished_at=_now(),
                                   error={"code": exc.code, "message": str(exc)}))
        return EXIT_REFUSED
    except Exception as exc:  # the result must say so, whatever broke
        write_result(run_dir, dict(base, status="error", data=None, finished_at=_now(),
                                   error={"code": "internal_error", "message": "%s: %s"
                                          % (type(exc).__name__, exc),
                                          "traceback": traceback.format_exc()}))
        return EXIT_INTERNAL
