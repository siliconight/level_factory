"""Make node names in a staged .tscn legal, and keep parent paths pointing at
them (TDD 24.7).

Godot cannot represent ``.``, ``:``, ``@``, ``/``, ``"`` or ``%`` in a node
name: ``Node::set_name`` rewrites each of them to ``_`` when the scene is
instantiated. A generator that writes ``[node name="b0/LADDER_0_climb"]`` and
then ``[node ... parent="b0/LADDER_0_climb"]`` therefore ships a scene that
silently loses children -- the node is renamed to ``b0_LADDER_0_climb``, the
parent string is parsed as the *path* ``b0`` -> ``LADDER_0_climb``, no such node
exists, and the child is dropped with a message nobody reads. Lot's walkable
scene did exactly this for every ladder, so every ladder volume arrived with no
CollisionShape3D and nothing could climb it.

Applying Godot's own rule at staging time -- to the names *and* to every path
that referenced them -- keeps the staged scene identical to what the author
meant. Pure text in, text out: no bpy, no Godot, so the builder, the linter and
the tests all run the same function.
"""
from __future__ import annotations

import re

# Godot 4: String::invalid_node_name_characters
INVALID_NAME_CHARS = '.:@/"%'

_NODE_LINE = re.compile(r'^\[node\s+[^\]\n]*\]', re.M)
_PATH_LINE = re.compile(r'^\[(?:connection|editable)\s+[^\]\n]*\]', re.M)
_ATTR = re.compile(r'(\w+)="([^"]*)"')


def validate_node_name(name: str) -> str:
    """Godot's own sanitization: every invalid character becomes ``_``."""
    return "".join("_" if c in INVALID_NAME_CHARS else c for c in name)


def _attr(header: str, key: str) -> str | None:
    for k, v in _ATTR.findall(header):
        if k == key:
            return v
    return None


def _set_attr(header: str, key: str, value: str) -> str:
    def _sub(m: "re.Match[str]") -> str:
        return f'{key}="{value}"' if m.group(1) == key else m.group(0)

    return _ATTR.sub(_sub, header)


def _split_prefix(path: str) -> tuple[str, str]:
    """Separate a leading ``./`` so it can be put back verbatim."""
    if path.startswith("./"):
        return "./", path[2:]
    return "", path


def sanitize_node_names(text: str) -> tuple[str, list[tuple[str, str]]]:
    """Return (rewritten_text, renames) for one .tscn document.

    ``renames`` lists ``(original_path, sanitized_path)`` for every node whose
    name had to change, so callers can report what they repaired rather than
    fixing it invisibly.
    """
    renames: list[tuple[str, str]] = []
    # original full path -> sanitized full path, in document order. Node headers
    # always declare their parent before the child, so a single forward pass is
    # enough to resolve nested renames.
    path_map: dict[str, str] = {}

    def _safe_parent(raw_parent: str) -> str:
        prefix, body = _split_prefix(raw_parent)
        if body == "" or body == ".":
            return raw_parent
        return prefix + path_map.get(body, body)

    def _node(m: "re.Match[str]") -> str:
        header = m.group(0)
        raw_name = _attr(header, "name")
        if raw_name is None:
            return header
        safe_name = validate_node_name(raw_name)
        raw_parent = _attr(header, "parent")
        if raw_parent is None:  # the root node has no parent attribute
            if safe_name != raw_name:
                renames.append((raw_name, safe_name))
                header = _set_attr(header, "name", safe_name)
            return header
        safe_parent = _safe_parent(raw_parent)
        _, parent_body = _split_prefix(raw_parent)
        _, safe_body = _split_prefix(safe_parent)
        raw_full = raw_name if parent_body in ("", ".") else f"{parent_body}/{raw_name}"
        safe_full = safe_name if safe_body in ("", ".") else f"{safe_body}/{safe_name}"
        if raw_full != safe_full:
            path_map[raw_full] = safe_full
            if safe_name != raw_name:
                renames.append((raw_full, safe_full))
        if safe_name != raw_name:
            header = _set_attr(header, "name", safe_name)
        if safe_parent != raw_parent:
            header = _set_attr(header, "parent", safe_parent)
        return header

    out = _NODE_LINE.sub(_node, text)

    # Signal/editable sections carry node paths too, and they are written after
    # every node, so the map is complete by the time we reach them.
    def _paths(m: "re.Match[str]") -> str:
        header = m.group(0)
        for key in ("from", "to", "path"):
            raw = _attr(header, key)
            if raw is None:
                continue
            prefix, body = _split_prefix(raw)
            if body in path_map:
                header = _set_attr(header, key, prefix + path_map[body])
        return header

    return _PATH_LINE.sub(_paths, out), renames
