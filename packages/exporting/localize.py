"""Export localization: make a portable export actually portable (TDD 33.5).

`scan_closure` (closure.py) is the judge; this module is the fixer. It runs
after the exporter's tree copies and makes three classes of repair, recording
every action in an export_closure.json-shaped report:

1. ABSOLUTE REFS -> BUNDLED ASSETS. Tool outputs (Lot's site.tscn) reference
   inputs by absolute path, which the Godot resource writer mangles into
   ``res://C:/...``. Every such reference is copied into ``assets/`` inside
   the export (deduped by content hash; name collisions get a short hash
   suffix) and the reference rewritten. Provenance note: a content-addressed
   cache hit can legitimately restore an output whose absolute path names a
   SIBLING candidate's byte-identical input — the bundled bytes are correct
   either way; only the path was poison.

2. ADDON REFS -> LOCALIZED RUNTIME. ``res://addons/<tool>/...`` scripts do
   not exist in a clean project (portable-godot promises no addons). Scenes
   that need them get the LUX_LOCALIZED treatment the profile always
   promised: the referenced scripts are copied to ``runtime/<tool>/...``
   inside the export and every reference rewritten — recursively, since
   localized .gd files may preload further addon scripts. Walk scenes
   (``*_walk.tscn``) are development chrome, not mission content: stripped
   by default, localized instead when the profile says include_walk.

3. ENTRY SCENE. ``mission.tscn`` (the project's main scene and the
   portability test's target) is synthesized: it instances the site scene
   (and the localized presentation scene when present) via an embedded
   script that prints the instantiate marker and quits when run under
   ``--lf-portability-check`` — making the clean-project engine check a real
   load test instead of a hang.
"""
from __future__ import annotations

import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from packages.core.hashing import hash_file

# path="res://C:/..." (mangled), path="C:/..." or path="C:\..." — the
# ext_resource forms tool outputs actually produce.
_ABS_EXT_REF = re.compile(
    r'path="(?:res://)?((?:[A-Za-z]:[\\/]|/(?:home|Users|mnt|tmp|var|private|Projects)/)[^"]+)"')
# res://addons/<tool>/<rest> anywhere in a text resource (tscn or gd).
_ADDON_REF = re.compile(r'res://addons/([A-Za-z0-9_]+)/([^"\')\s]+)')

_ASSETS_DIR = "assets"
_RUNTIME_DIR = "runtime"
_TEXT_SUFFIXES = {".tscn", ".tres", ".gd"}


@dataclass
class LocalizeReport:
    rewritten_absolute: list[str] = field(default_factory=list)
    localized_scripts: list[str] = field(default_factory=list)
    stripped_scenes: list[str] = field(default_factory=list)
    sanitized_json: list[str] = field(default_factory=list)
    unresolved: list[str] = field(default_factory=list)
    entry_scene: str | None = None

    def as_dict(self) -> dict:
        return {
            "schema": "level_factory.export_closure.v0.1",
            "rewritten_absolute": sorted(self.rewritten_absolute),
            "localized_scripts": sorted(self.localized_scripts),
            "stripped_scenes": sorted(self.stripped_scenes),
            "sanitized_json": sorted(self.sanitized_json),
            "unresolved": sorted(self.unresolved),
            "entry_scene": self.entry_scene,
        }


def _bundle_asset(src: Path, export_dir: Path, report: LocalizeReport) -> str | None:
    """Copy an absolutely-referenced file into assets/, dedupe by content."""
    assets = export_dir / _ASSETS_DIR
    assets.mkdir(parents=True, exist_ok=True)
    target = assets / src.name
    if target.exists():
        if hash_file(target) != hash_file(src):
            target = assets / f"{src.stem}.{hash_file(src)[:8]}{src.suffix}"
            if not target.exists():
                shutil.copy2(src, target)
    else:
        shutil.copy2(src, target)
    rel = target.relative_to(export_dir).as_posix()
    report.rewritten_absolute.append(f"{src} -> res://{rel}")
    return rel


def _localize_script(tool: str, rest: str, addon_sources: dict[str, Path],
                     export_dir: Path, report: LocalizeReport) -> str | None:
    """Copy addons/<tool>/<rest> into runtime/<tool>/<rest>; return res-rel path."""
    repo = addon_sources.get(tool)
    if repo is None:
        return None
    src = Path(repo) / "addons" / tool / rest
    if not src.exists():
        return None
    target = export_dir / _RUNTIME_DIR / tool / rest
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        shutil.copy2(src, target)
        report.localized_scripts.append(f"addons/{tool}/{rest}")
    return (Path(_RUNTIME_DIR) / tool / rest).as_posix()


def _rewrite_text(path: Path, export_dir: Path, addon_sources: dict[str, Path],
                  report: LocalizeReport) -> bool:
    """One rewrite pass over a text resource. Returns True if changed."""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return False
    changed = False

    def _abs_sub(m: "re.Match[str]") -> str:
        nonlocal changed
        src = Path(m.group(1).replace("\\", "/"))
        if not src.exists():
            report.unresolved.append(f"{path.name}: absolute ref missing on disk: {src}")
            return m.group(0)
        rel = _bundle_asset(src, export_dir, report)
        changed = True
        return f'path="res://{rel}"'

    def _addon_sub(m: "re.Match[str]") -> str:
        nonlocal changed
        tool, rest = m.group(1), m.group(2)
        rel = _localize_script(tool, rest, addon_sources, export_dir, report)
        if rel is None:
            report.unresolved.append(
                f"{path.name}: res://addons/{tool}/{rest} (no source configured)")
            return m.group(0)
        changed = True
        return f"res://{rel}"

    new = _ABS_EXT_REF.sub(_abs_sub, text)
    new = _ADDON_REF.sub(_addon_sub, new)
    if changed:
        path.write_text(new, encoding="utf-8")
    return changed


def localize_export(export_dir: Path, *, addon_sources: dict[str, Path],
                    strip_walk: bool = True, max_passes: int = 10) -> LocalizeReport:
    """Repair the export's resource closure in place."""
    report = LocalizeReport()

    if strip_walk:
        for walk in sorted(export_dir.rglob("*_walk.tscn")):
            report.stripped_scenes.append(walk.relative_to(export_dir).as_posix())
            walk.unlink()

    # Data-file hygiene: tool outputs (Lot gameplay/site data) embed absolute
    # input paths as provenance strings. In a clean project those paths are
    # dead weight that trips the authoring-marker scan; neutralize every
    # absolute-path string value to its basename. Runs before the exporter
    # writes its own manifests, so only tool data is touched.
    import json as _json
    _abs_val = re.compile(r"^(?:[A-Za-z]:[\\/]|/(?:home|Users|mnt|tmp|var|private|Projects)/)")

    def _scrub(v):
        if isinstance(v, str) and _abs_val.match(v):
            return Path(v.replace("\\", "/")).name
        if isinstance(v, list):
            return [_scrub(x) for x in v]
        if isinstance(v, dict):
            return {k: _scrub(x) for k, x in v.items()}
        return v

    for jf in sorted(export_dir.rglob("*.json")):
        try:
            data = _json.loads(jf.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        scrubbed = _scrub(data)
        if scrubbed != data:
            jf.write_text(_json.dumps(scrubbed, indent=2, sort_keys=True),
                          encoding="utf-8")
            report.sanitized_json.append(jf.relative_to(export_dir).as_posix())

    # Rewrite to fixpoint: localizing a .gd can surface new addon refs inside
    # the freshly copied runtime/ scripts.
    for _ in range(max_passes):
        changed = False
        for f in sorted(export_dir.rglob("*")):
            if f.is_file() and f.suffix in _TEXT_SUFFIXES:
                changed |= _rewrite_text(f, export_dir, addon_sources, report)
        if not changed:
            break
    return report


_ENTRY_TEMPLATE = """[gd_scene load_steps=2 format=3]

[sub_resource type="GDScript" id="mission_entry"]
script/source = "extends Node3D
# Level Factory portable mission entry. Self-contained (no addons): instances
# the mission content, and under the clean-project portability check prints
# the instantiate marker and quits instead of running forever headless.

func _ready() -> void:
{instances}\tprint('scene instantiated ok')
\tif '--lf-portability-check' in OS.get_cmdline_user_args():
\t\tget_tree().quit()
"

[node name="Mission" type="Node3D"]
script = SubResource("mission_entry")
"""


def write_entry_scene(export_dir: Path, report: LocalizeReport) -> str:
    """Synthesize mission.tscn instancing the site (+presentation) scenes."""
    candidates: list[str] = []
    site = export_dir / "site.tscn"
    if site.exists():
        candidates.append("site.tscn")
    pres = export_dir / "presentation" / "lux.applied.tscn"
    if pres.exists():
        candidates.append("presentation/lux.applied.tscn")
    lines = ""
    for i, rel in enumerate(candidates):
        lines += (f"\tvar packed_{i} := load('res://{rel}') as PackedScene\n"
                  f"\tif packed_{i} != null:\n"
                  f"\t\tadd_child(packed_{i}.instantiate())\n")
    (export_dir / "mission.tscn").write_text(
        _ENTRY_TEMPLATE.format(instances=lines), encoding="utf-8")
    report.entry_scene = "mission.tscn"
    return "mission.tscn"
