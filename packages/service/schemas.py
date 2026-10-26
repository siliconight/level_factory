"""The authoring loop's records as data schemas, and the check every reader and writer of them runs.

THE SCHEMAS are JSON Schema (draft 2020-12) files in ``schemas/authoring/``, one per record, named by the record's
own ``schema`` field: the service protocol's request, event and result; the design and its template; the layouts'
build record, the walk record and the exported snapshot. They are the contract a client in another language (the
Godot panel) can read; the code that writes each record is held to its file.

THE CHECK IS BUILT IN, because the tools run on interpreters that may not have the ``jsonschema`` package (Blender's
own Python among them). It implements the keywords these files use and REFUSES A SCHEMA THAT USES ANY OTHER: a
validator that skipped a keyword it did not know would pass what the file forbids. Where ``jsonschema`` is
installed, `tests/service/test_schemas.py` checks each file with it and requires both to agree.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

SCHEMA_DIR = Path(__file__).resolve().parents[2] / "schemas" / "authoring"
#: Keywords that only describe; they never decide.
ANNOTATIONS = {"$schema", "$id", "$comment", "title", "description", "$defs"}
#: Keywords this check decides with. Anything else in a schema is refused when it is loaded.
KEYWORDS = {"type", "properties", "required", "additionalProperties", "items", "minItems", "enum", "const",
            "minimum", "maximum", "minLength", "pattern", "anyOf", "$ref"}
_TYPES = {"object": dict, "array": list, "string": str, "boolean": bool, "null": type(None)}


class SchemaError(ValueError):
    """A record that does not match its schema; ``problems`` lists each mismatch with its path."""

    def __init__(self, schema_id: str, problems: list[str]) -> None:
        super().__init__("not a valid %s: %s" % (schema_id, "; ".join(problems)))
        self.schema_id = schema_id
        self.problems = problems


def _keywords_known(node, where: str) -> None:
    if isinstance(node, dict):
        for k, v in node.items():
            if k in ("properties", "$defs"):
                for name, sub in v.items():
                    _keywords_known(sub, "%s/%s/%s" % (where, k, name))
                continue
            if k not in KEYWORDS and k not in ANNOTATIONS:
                raise ValueError("%s uses %r, which this check does not implement" % (where or "/", k))
            if k in ("items", "additionalProperties") and isinstance(v, dict):
                _keywords_known(v, "%s/%s" % (where, k))
            elif k == "anyOf":
                for i, sub in enumerate(v):
                    _keywords_known(sub, "%s/anyOf/%d" % (where, i))


@lru_cache(maxsize=None)
def load(schema_id: str) -> dict:
    """The schema named ``schema_id``, refused when its file is missing, misnamed or uses a keyword not implemented."""
    path = SCHEMA_DIR / ("%s.schema.json" % schema_id)
    try:
        schema = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ValueError("no schema %s at %s" % (schema_id, path)) from None
    if schema.get("$id") != schema_id:
        raise ValueError("%s says $id %r" % (path.name, schema.get("$id")))
    _keywords_known(schema, "")
    return schema


def known() -> list[str]:
    """Every schema id shipped."""
    return sorted(p.name[:-len(".schema.json")] for p in SCHEMA_DIR.glob("*.schema.json"))


def _is(value, kind: str) -> bool:
    if kind == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if kind == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    return isinstance(value, _TYPES[kind])


def _check(value, node: dict, root: dict, path: str, out: list) -> None:
    if "$ref" in node:
        ref = node["$ref"]
        if not ref.startswith("#/$defs/"):
            raise ValueError("only local $defs references are implemented, not %r" % ref)
        _check(value, root["$defs"][ref[len("#/$defs/"):]], root, path, out)
    if "type" in node:
        kinds = node["type"] if isinstance(node["type"], list) else [node["type"]]
        if not any(_is(value, k) for k in kinds):
            out.append("%s: is %s, not %s" % (path, type(value).__name__, " or ".join(kinds)))
            return
    if "const" in node and value != node["const"]:
        out.append("%s: is %r, not %r" % (path, value, node["const"]))
    if "enum" in node and value not in node["enum"]:
        out.append("%s: is %r, not one of %s" % (path, value, ", ".join(repr(e) for e in node["enum"])))
    if _is(value, "number"):
        if "minimum" in node and value < node["minimum"]:
            out.append("%s: %r is below %r" % (path, value, node["minimum"]))
        if "maximum" in node and value > node["maximum"]:
            out.append("%s: %r is above %r" % (path, value, node["maximum"]))
    if isinstance(value, str):
        if "minLength" in node and len(value) < node["minLength"]:
            out.append("%s: is shorter than %d" % (path, node["minLength"]))
        if "pattern" in node and not re.search(node["pattern"], value):
            out.append("%s: %r does not match %s" % (path, value, node["pattern"]))
    if isinstance(value, list):
        if "minItems" in node and len(value) < node["minItems"]:
            out.append("%s: has %d items, fewer than %d" % (path, len(value), node["minItems"]))
        if isinstance(node.get("items"), dict):
            for i, item in enumerate(value):
                _check(item, node["items"], root, "%s/%d" % (path, i), out)
    if isinstance(value, dict):
        for key in node.get("required", []):
            if key not in value:
                out.append("%s: %s is missing" % (path, key))
        props = node.get("properties", {})
        extra = node.get("additionalProperties", True)
        for key, item in value.items():
            if key in props:
                _check(item, props[key], root, "%s/%s" % (path, key), out)
            elif extra is False:
                out.append("%s: %s is not a field of this record" % (path, key))
            elif isinstance(extra, dict):
                _check(item, extra, root, "%s/%s" % (path, key), out)
    if "anyOf" in node:
        branches = []
        for sub in node["anyOf"]:
            got: list = []
            _check(value, sub, root, path, got)
            if not got:
                break
            branches.append(got)
        else:
            out.append("%s: matches none of its allowed shapes (%s)" % (
                path, " | ".join("; ".join(b) for b in branches)))


def check(instance, schema_id: str) -> list[str]:
    """Every way ``instance`` differs from schema ``schema_id``; empty when it matches. Paths are JSON pointers."""
    root = load(schema_id)
    out: list[str] = []
    _check(instance, root, root, "", out)
    return ["/" + p if p.startswith(":") else p for p in out]      # the record itself is "/"


def require(instance, schema_id: str):
    """``instance``, or `SchemaError` listing every mismatch. Writers call it before a record reaches disk."""
    problems = check(instance, schema_id)
    if problems:
        raise SchemaError(schema_id, problems)
    return instance
