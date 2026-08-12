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
#: An ext_resource's path, whatever scheme it uses -- including none.
_EXT_PATH = re.compile(r'^\[ext_resource[^\]]*path="([^"]+)"', re.M)
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
    "export_closure.json", "export_closure_scan.json", "output_layers.json",
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
    #: References that fail at the path they name while a file with that TAIL
    #: exists elsewhere in the package. Counted apart from `missing` because the
    #: two want different fixes: a missing resource was not copied, a misrooted
    #: one was copied and the scene that names it was moved without having its
    #: references rewritten.
    #:
    #: This category exists because the scan used to treat exactly this case as
    #: RESOLVED -- `any(pr.endswith(rel) for pr in present)` -- and Godot does
    #: not resolve `res://` by suffix. Measured on lot_demo_001: five building
    #: scenes staged under `lot/<archetype>/` with 33 unrewritten references
    #: each, and a report of `ok: true, 0 missing`.
    misrooted_resource_count: int = 0
    #: ext_resource paths carrying no scheme at all -- neither res:// nor
    #: uid://. `lot.write_godot_scene(portable=True)` emits these on purpose,
    #: relative to the scene file, so a scene and its siblings form a
    #: drop-anywhere folder. Reported as a COUNT because the scan used to have
    #: no opinion about them in either direction: the res:// regex never
    #: matched them, so five buildings named from the graybox site.tscn were
    #: neither resolved nor reported, in a verdict that said `ok: true`.
    relative_reference_count: int = 0
    #: Of those, the ones that resolve to nothing, or out of the package. A
    #: relative path is broken under EVERY reading of how the engine treats
    #: it, which is why this one counts against `ok` and the bare count above
    #: does not.
    unresolved_relative_count: int = 0
    required_plugin_count: int = 0
    required_autoload_count: int = 0
    issues: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return (self.absolute_path_count == 0
                and self.missing_resource_count == 0
                and self.misrooted_resource_count == 0
                and self.unresolved_relative_count == 0
                and self.external_reference_count == 0
                and self.required_plugin_count == 0
                and self.required_autoload_count == 0)

    def as_dict(self) -> dict:
        return {
            "resource_count": self.resource_count,
            "external_reference_count": self.external_reference_count,
            "absolute_path_count": self.absolute_path_count,
            "missing_resource_count": self.missing_resource_count,
            "misrooted_resource_count": self.misrooted_resource_count,
            "relative_reference_count": self.relative_reference_count,
            "unresolved_relative_count": self.unresolved_relative_count,
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
        # LF/Dispatch metadata files are not Godot resources; the closure
        # audit report in particular RECORDS the absolute paths it rewrote.
        if f.name in _METADATA_FILES:
            continue
        text = f.read_text(encoding="utf-8", errors="replace")
        # The label every issue below carries. NOT `f.name`: a composed export
        # holds six files called `site.tscn` and a basename names all of them.
        # `f.name` stays correct for the _METADATA_FILES tests, which match a
        # set of basenames.
        rel_f = f.relative_to(mission_root).as_posix()

        for m in _ABS_PATH.finditer(text):
            result.absolute_path_count += 1
            result.issues.append(f"{rel_f}: absolute path {m.group(0)[:60]}")

        if _USER_PATH.search(text):
            result.external_reference_count += 1
            result.issues.append(
                f"{rel_f}: user:// reference is not portable")

        for m in _RES_REF.finditer(text):
            rel = m.group(1)
            # res://.godot/ is the import cache, not an authored resource. Every
            # .import sidecar names its own cache target there, and those targets
            # are SUPPOSED to be absent from a package: a Godot project ships
            # sources plus .import, and the consumer's editor regenerates the
            # cache on first open. They are also platform-specific (.s3tc.ctex),
            # so shipping them would be shipping a build artifact.
            #
            # This mattered the moment the export started carrying art: 100 .glb
            # and .png sidecars arrived and the scan reported 104 unresolved
            # references, none of them real. A guardrail that fires on correct
            # output is one somebody switches off.
            if rel not in present and not rel.startswith(
                    (".godot/", "addons/godot/", "builtin/")):
                # Directory references (preset-library scans etc.) are
                # resolvable even though the present-set only lists files.
                if (mission_root / rel).exists():
                    continue
                # `res://x` IS `<root>/x`. No search path, no fallback,
                # no walking up -- Godot has never resolved a res:// path by
                # suffix and this scan used to, with
                # `any(pr.endswith(rel) for pr in present)`. That single line
                # certified lot_demo_001's portable export at `ok: true,
                # 0 missing` while five building scenes, staged under
                # `lot/<archetype>/` without their references rewritten, each
                # dangled 33 of them. The package opened as floors and a
                # staircase in an empty sky.
                #
                # The suffix search is kept and RENAMED to what it finds. A
                # reference that fails where it points while the file exists
                # elsewhere is not resolved and is not ordinarily missing
                # either: it is a scene that moved without being rewritten,
                # which is a specific defect with a specific fix, and saying
                # so beats a bare "unresolved".
                found_at = next((pr for pr in sorted(present)
                                 if pr.endswith("/" + rel) or pr == rel), None)
                if found_at is None:
                    result.missing_resource_count += 1
                    result.issues.append(
                        f"{rel_f}: unresolved res://{rel}")
                else:
                    result.misrooted_resource_count += 1
                    result.issues.append(
                        f"{rel_f}: MISROOTED res://{rel} -> present at "
                        f"{found_at}")

        # Scheme-less ext_resource paths. Godot's text loader is documented
        # to take a relative ext_resource path as relative to the scene file's
        # own directory, and that is the only reading under which these were
        # ever intended to work -- so resolve them that way and report what
        # comes back. A path that resolves to nothing, or climbs out of the
        # package, is broken under any reading; that is the only case this
        # calls a defect. The bare count is reported without judgement so the
        # number is visible instead of absent.
        if f.suffix in (".tscn", ".tres"):
            root_abs = mission_root.resolve()
            for m in _EXT_PATH.finditer(text):
                p = m.group(1)
                if "://" in p:
                    continue
                result.relative_reference_count += 1
                try:
                    target = (f.parent / p).resolve()
                    inside = target.is_relative_to(root_abs)
                except (OSError, ValueError):
                    target, inside = None, False
                here = f.parent.relative_to(mission_root).as_posix() or "."
                if target is None or not inside:
                    result.unresolved_relative_count += 1
                    result.issues.append(
                        f"{rel_f}: relative ext_resource leaves the package: "
                        f"{p} (from {here}/)")
                elif not target.exists():
                    result.unresolved_relative_count += 1
                    result.issues.append(
                        f"{rel_f}: relative ext_resource resolves to nothing: "
                        f"{p} (from {here}/)")

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
                            f"{rel_f}: authoring-repo path reference "
                            f"'{marker}'")
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
