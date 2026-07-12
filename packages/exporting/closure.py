"""Portable resource closure scan (TDD 33.5, 44.11, 44.12).

A portable export must reference only files inside its own mission folder or
built-in Godot resources -- no absolute paths, no authoring-repo references, no
required editor add-on, no required autoload. This scans the exported Godot
text resources (.tscn/.tres/.gdshader/.import/.gd) and reports violations.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

_RES_REF = re.compile(r'res://([^"\')\s]+)')
_ABS_PATH = re.compile(
    r'["\']((?:[A-Za-z]:[\\/])|(?:/(?:home|Users|mnt|Projects)/))[^"\']*["\']')
_USER_PATH = re.compile(r'user://')

_SCANNED_SUFFIXES = {".tscn", ".tres", ".gd", ".gdshader", ".import", ".cfg", ".json"}
_AUTHORING_MARKERS = ("deli-counter", "deli_counter", "lasertag", "pixelcoat",
                      "level-factory", "level_factory")
# LF/Dispatch metadata files legitimately name tools/schemas; they are not Godot
# resources and never break portability, so exclude them from marker scanning.
_METADATA_FILES = {
    "portable_resource_manifest.json", "LICENSES.json", "export_profile.json",
    "build.lock.json", "mission_manifest.json", "runtime_ownership_requirements.json",
    "proposed_beat_graph.json", "gameplay_anchors.json", "navigation_hints.json",
    "lux.quality.json", "lux.validation.json",
}
# A marker only breaks portability when it appears as a PATH reference.
_PATH_MARKER_CHARS = ("/", "\\", ":")


@dataclass
class ClosureResult:
    root: Path
    resource_count: int = 0
    external_reference_count: int = 0
    absolute_path_count: int = 0
    missing_resource_count: int = 0
    required_plugin_count: int = 0
    required_autoload_count: int = 0
    issues: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return (self.absolute_path_count == 0
                and self.missing_resource_count == 0
                and self.external_reference_count == 0
                and self.required_plugin_count == 0
                and self.required_autoload_count == 0)

    def as_dict(self) -> dict:
        return {
            "resource_count": self.resource_count,
            "external_reference_count": self.external_reference_count,
            "absolute_path_count": self.absolute_path_count,
            "missing_resource_count": self.missing_resource_count,
            "required_plugin_count": self.required_plugin_count,
            "required_autoload_count": self.required_autoload_count,
            "ok": self.ok,
            "issues": self.issues,
        }


def scan_closure(mission_root: Path) -> ClosureResult:
    result = ClosureResult(root=mission_root)
    files = [p for p in mission_root.rglob("*")
             if p.is_file() and p.suffix in _SCANNED_SUFFIXES]
    result.resource_count = sum(
        1 for p in files if p.suffix in (".tscn", ".tres", ".gdshader", ".gd"))

    present = {p.relative_to(mission_root).as_posix() for p in mission_root.rglob("*")
               if p.is_file()}

    for f in files:
        text = f.read_text(encoding="utf-8", errors="replace")

        for m in _ABS_PATH.finditer(text):
            result.absolute_path_count += 1
            result.issues.append(f"{f.name}: absolute path {m.group(0)[:60]}")

        if _USER_PATH.search(text):
            result.external_reference_count += 1
            result.issues.append(f"{f.name}: user:// reference is not portable")

        for m in _RES_REF.finditer(text):
            rel = m.group(1)
            if rel not in present and not rel.startswith(("addons/godot/", "builtin/")):
                if not any(pr.endswith(rel) for pr in present):
                    result.missing_resource_count += 1
                    result.issues.append(f"{f.name}: unresolved res://{rel}")

        low = text.lower()
        if f.name not in _METADATA_FILES:
            for marker in _AUTHORING_MARKERS:
                idx = low.find(marker)
                # Only a violation when the marker is used as a path (adjacent
                # to a path separator), not a bare tool name in metadata.
                if idx != -1:
                    window = low[max(0, idx - 1): idx + len(marker) + 1]
                    if any(ch in window for ch in _PATH_MARKER_CHARS):
                        result.external_reference_count += 1
                        result.issues.append(
                            f"{f.name}: authoring-repo path reference '{marker}'")
                        break

    project = mission_root / "project.godot"
    if project.exists():
        ptext = project.read_text(encoding="utf-8", errors="replace")
        if "[autoload]" in ptext:
            section = ptext.split("[autoload]", 1)[1].split("[", 1)[0]
            entries = [ln for ln in section.splitlines() if "=" in ln and ln.strip()]
            result.required_autoload_count += len(entries)
            if entries:
                result.issues.append(f"project.godot declares {len(entries)} autoload(s)")
        if "enabled=PackedStringArray(" in ptext and 'res://addons' in ptext:
            result.required_plugin_count += 1
            result.issues.append("project.godot enables an editor plugin")

    return result
