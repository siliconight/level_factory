"""The authoring loop's records as data schemas (0.252.0, the factory's `docs/AUTHORING_LOOP.md`).

Each record the loop reads or writes has a JSON Schema in schemas/authoring/, checked by a built-in validator that
refuses any keyword it does not implement. Real records -- copied from the factory's trial levels and runs into
fixtures/authoring/ -- pass; each is then broken one field at a time and must fail. Where ``jsonschema`` is
installed both validators judge every case and must agree, so the built-in check cannot quietly be looser than the
standard. The worker, the design and the record writers are held to the schemas. FAILS ON 0.251.0.
"""
import copy
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from packages.service import design, operations, schemas  # noqa: E402
from packages.service.worker import EventSink, run_service  # noqa: E402

try:
    import jsonschema
except ImportError:                       # Blender's Python: the built-in check stands alone
    jsonschema = None

FIX = Path(__file__).resolve().parent / "fixtures" / "authoring"
REAL = [("gabagool.design.v1", "design.json"), ("gabagool.build_record.v1", "build_record.json"),
        ("gabagool.walk_record.v1", "walk_record.json"), ("gabagool.snapshot.v1", "export_record.json"),
        ("gabagool.snapshot.v1", "snapshot.json"), ("gabagool.service.request.v1", "request.json"),
        ("gabagool.service.result.v1", "result_ok.json")]
_NOOP = type("E", (), {"emit": lambda self, *a, **k: None})()


def _real():
    out = [(sid, json.loads((FIX / name).read_text(encoding="utf-8")), name) for sid, name in REAL]
    out += [("gabagool.service.event.v1", json.loads(line), "events.jsonl:%d" % i)
            for i, line in enumerate((FIX / "events.jsonl").read_text(encoding="utf-8").splitlines(), 1)]
    out.append(("gabagool.template.v1", design.template("restaurant_row"), "restaurant_row.json"))
    return out


def _standard(instance, sid):
    """``None`` when jsonschema is not installed, else whether the standard validator accepts ``instance``."""
    if jsonschema is None:
        return None
    return not list(jsonschema.Draft202012Validator(schemas.load(sid)).iter_errors(instance))


def _breakages(instance, sid):
    """``(what, broken copy)`` -- each required field removed, each field given a value of the wrong type, and a
    field the record does not have where the schema forbids one."""
    root = schemas.load(sid)
    for key in root["required"]:
        bad = copy.deepcopy(instance)
        del bad[key]
        yield "without %s" % key, bad
    for key, prop in root["properties"].items():
        if key in instance:
            bad = copy.deepcopy(instance)
            bad[key] = "text" if prop.get("type") == "array" else []
            yield "%s of the wrong type" % key, bad
    if root.get("additionalProperties") is False:
        yield "with a field it does not have", dict(instance, zz_not_a_field=1)


def test_every_schema_is_named_by_its_record_and_is_standard_json_schema():
    ids = schemas.known()
    assert len(ids) == 8
    for sid in ids:
        s = schemas.load(sid)
        assert s["$id"] == sid and s["properties"]["schema"] == {"const": sid}
        if jsonschema is not None:
            jsonschema.Draft202012Validator.check_schema(s)


@pytest.mark.parametrize("sid,instance,name", _real(), ids=lambda v: v if isinstance(v, str) else "")
def test_real_records_pass_and_every_breakage_fails(sid, instance, name):
    assert schemas.check(instance, sid) == [], name
    assert _standard(instance, sid) in (None, True)
    broken = list(_breakages(instance, sid))
    assert broken
    for what, bad in broken:
        problems = schemas.check(bad, sid)
        assert problems, "%s %s passed" % (name, what)
        assert _standard(bad, sid) in (None, False), "%s %s: the two validators disagree" % (name, what)


def test_a_result_is_ok_with_data_or_an_error_never_both():
    ok = json.loads((FIX / "result_ok.json").read_text(encoding="utf-8"))
    both = dict(ok, error={"code": "x", "message": "y"})
    neither = dict(ok, status="error", error=None)
    for bad in (both, neither):
        assert schemas.check(bad, "gabagool.service.result.v1")
        assert _standard(bad, "gabagool.service.result.v1") in (None, False)


def test_a_schema_using_a_keyword_the_check_does_not_implement_is_refused(tmp_path, monkeypatch):
    (tmp_path / "x.v1.schema.json").write_text(json.dumps({"$id": "x.v1", "type": "object",
                                                           "properties": {"a": {"oneOf": []}}}), encoding="utf-8")
    monkeypatch.setattr(schemas, "SCHEMA_DIR", tmp_path)
    schemas.load.cache_clear()
    try:
        with pytest.raises(ValueError, match="oneOf"):
            schemas.load("x.v1")
    finally:
        schemas.load.cache_clear()


def _request(run_dir, **fields):
    req = {"schema": "gabagool.service.request.v1", "request_id": "r1", "operation": "echo", "arguments": {}}
    req.update(fields)
    (run_dir / "request.json").write_text(json.dumps(req), encoding="utf-8")


def _result(run_dir):
    r = json.loads((run_dir / "result.json").read_text(encoding="utf-8"))
    assert schemas.check(r, "gabagool.service.result.v1") == []        # every result the worker writes
    return r


def test_the_worker_refuses_a_request_its_schema_refuses_and_says_where(tmp_path):
    _request(tmp_path, request_id=5)
    assert run_service(tmp_path, {"echo": lambda a, e: {}}) == 2
    r = _result(tmp_path)
    assert r["error"]["code"] == "request_malformed" and "/request_id" in r["error"]["message"]


def test_an_answer_or_event_the_schema_refuses_is_an_internal_error_not_a_bad_file(tmp_path):
    (tmp_path / "a").mkdir()
    _request(tmp_path / "a")
    assert run_service(tmp_path / "a", {"echo": lambda a, e: ["not", "an", "object"]}) == 5
    assert "/data" in _result(tmp_path / "a")["error"]["message"]

    def says_failed(arguments, events):
        events.emit("work", "failed", "a failure is the result's error, never an event")
        return {}
    (tmp_path / "b").mkdir()
    _request(tmp_path / "b")
    assert run_service(tmp_path / "b", {"echo": says_failed}) == 5
    assert "/status" in _result(tmp_path / "b")["error"]["message"]
    for line in (tmp_path / "b" / "events.jsonl").read_text(encoding="utf-8").splitlines():
        assert schemas.check(json.loads(line), "gabagool.service.event.v1") == []


def test_a_design_is_checked_when_read_and_when_written(tmp_path, monkeypatch):
    from packages.tools import discovery
    monkeypatch.setattr(discovery, "factory_root", lambda start=None: tmp_path)
    got = operations.create_design({"template": "restaurant_row", "name": "Checked"}, _NOOP)
    path = Path(got["path"])
    doc = json.loads(path.read_text(encoding="utf-8"))
    assert schemas.check(doc, "gabagool.design.v1") == []
    del doc["updated_at"]
    path.write_text(json.dumps(doc), encoding="utf-8")
    assert any("updated_at is missing" in p for p in design.read_design(path)["problems"])
    with pytest.raises(schemas.SchemaError):
        design.write_design(path.parent, dict(doc, slug="Not A Slug", updated_at=doc["created_at"]))
    assert "updated_at" not in json.loads(path.read_text(encoding="utf-8"))      # nothing written


def test_a_template_is_checked_when_loaded(tmp_path, monkeypatch):
    t = design.template("restaurant_row")
    (tmp_path / "restaurant_row.json").write_text(json.dumps(dict(t, batch={"seed_base": "9003"})), encoding="utf-8")
    monkeypatch.setattr(design, "TEMPLATES_DIR", tmp_path)
    with pytest.raises(design.DesignError) as e:
        design.templates()
    assert e.value.code == "template_unreadable" and "/batch/seed_base" in str(e.value)
