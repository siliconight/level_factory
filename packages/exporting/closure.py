"""Portable resource closure scan (TDD 33.5, 44.11, 44.12).

A portable export must reference only files inside its own mission folder or
built-in Godot resources -- no absolute paths, no authoring-repo references, no
required editor add-on, no required autoload. This scans the exported Godot
text resources (.tscn/.tres/.gdshader/.import/.gd) and reports violations.

WHEN it runs is part of what it means. A verdict is about the folder as it
stood at the moment of the scan, and from 0.98.0 to 0.102.0 `export_mission`
called it in the middle of the build -- so the shipped verdict described an
intermediate package and every file written afterwards went out unjudged.
`verify_verdict_describes_package` is the backstop that makes the ordering
checkable instead of remembered.
"""
from __future__ import annotations

import hashlib
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
    # Added 0.103.0, when the verdict moved to the END of the export and saw
    # these four for the first time. Each is LF's own log of a build step; a
    # Godot loader reads none of them.
    #
    # `handoff_bindings.json` is the one that needed establishing rather than
    # assuming, because it names `deli_counter` and the marker test below
    # fires on it. Measured on cold 9066's and 9067's shipped packages: the
    # single issue a post-writer scan reports is
    #   handoff_bindings.json: authoring-repo path reference 'deli_counter'
    # from strings shaped
    #   Functional/GameplayAnchors/Triggers/deli_counter:01
    # -- a Godot NODE path, not a filesystem path and not a res:// path. It
    # trips only because `_PATH_MARKER_CHARS` reads `/` and `:` as evidence of
    # a path, and a NodePath spells itself with both.
    #
    # Three things make it benign, and they were checked rather than argued:
    #   1. `strip_dead_node_paths` writes this file, and its `paths` list is
    #      BY CONSTRUCTION the addresses whose leaf node name appears in no
    #      shipped scene. The file exists to say the package does not carry
    #      them; resolving one at runtime yields nothing whether or not the
    #      scan reads it, and that is a node-binding question owned by
    #      roadmap 101, not a portability one.
    #   2. The identical strings already ship inside `gameplay_anchors.json`
    #      and `runtime_ownership_requirements.json` -- under `node_dispatch`,
    #      55 of them on 9067 -- and both files have been in this set since it
    #      was written. Excluding the summary and scanning the source would be
    #      the inconsistency.
    #   3. Nothing consumes it. A grep across every repo in the factory finds
    #      LF's own unit test and two lines of prose; no GDScript, no Dispatch
    #      reader.
    "handoff_bindings.json", "occluders.json", "warmup.json",
    # Added 0.105.0 with the GLB reference gate that writes it. It is a scan
    # REPORT about the package's GLBs, and its `root` field carries the
    # absolute path of the directory the build wrote -- which is exactly what
    # `_ABS_PATH` is built to find. Same shape as every other entry here: LF's
    # own log of a build step, read by no Godot loader. It is not exempt from
    # the question it asks; `glb_refs.scan` re-derives that from the GLBs.
    "glb_reference_scan.json",
    # The export manifest records THIS verdict (`verified.export_closure`), so
    # it cannot be inside what the verdict describes -- the same reason
    # `export_closure_scan.json` itself is on this list.
    "LF_MANIFEST.json",
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
    #: WHAT THIS VERDICT WAS DERIVED FROM, recorded so a later step can ask
    #: whether the package still IS that. Not serialized -- `package_file_count`
    #: and `package_fingerprint` in `as_dict()` are the serializable summary.
    #:
    #: Two sets, because the verdict depends on two different things:
    #: `present_names` is every file in the package, since `res://x` resolves
    #: on PRESENCE alone and a .glb arriving late can turn a missing
    #: reference into a resolved one; `input_digest` is the CONTENT of the
    #: files actually read -- the scanned suffixes plus `project.godot`.
    #: Hashing every .glb as well would price the check in hundreds of
    #: megabytes to answer a question presence already answers.
    present_names: set[str] = field(default_factory=set)
    input_digest: dict[str, str] = field(default_factory=dict)

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
            # THE PACKAGE THIS VERDICT DESCRIBES. A reader who wants to know
            # whether a package is still the one that was judged can re-derive
            # these from the folder; `verify_verdict_describes_package` does.
            "package_file_count": len(self.present_names),
            "verdict_input_count": len(self.input_digest),
            "package_fingerprint": self.package_fingerprint,
        }

    @property
    def package_fingerprint(self) -> str:
        """One hash over everything `ok` could have depended on."""
        return _fingerprint(self.present_names, self.input_digest)


def _fingerprint(present_names, input_digest,
                 exclude: frozenset[str] = frozenset()) -> str:
    h = hashlib.sha256()
    for name in sorted(set(present_names) - set(exclude)):
        h.update(b"P\0" + name.encode("utf-8") + b"\0")
    for name, digest in sorted(input_digest.items()):
        if name in exclude:
            continue
        h.update(b"I\0" + name.encode("utf-8") + b"\0"
                 + digest.encode("ascii") + b"\0")
    return h.hexdigest()


def fingerprint_package(mission_root: Path, *,
                        exclude: frozenset[str] = frozenset()) -> str:
    """Re-derive a verdict's `package_fingerprint` from the folder.

    THE POINT OF THE NUMBER IS THAT SOMEBODY ELSE CAN CHECK IT. A verdict
    carries a fingerprint of the package it judged; a reader holding the
    shipped folder computes this and compares. It matches when the package is
    the one that was judged.

    `exclude` is the list the verdict names in `written_after_verdict` -- the
    manifests that describe the package and so were written after it was
    judged. Without it the re-derivation cannot match and the fingerprint
    would be a number describing most of a package, which is worse than no
    number: it looks checkable and is not.
    """
    present = {p.relative_to(mission_root).as_posix()
               for p in mission_root.rglob("*") if p.is_file()}
    return _fingerprint(present, _digest_inputs(mission_root), exclude)


def _scanned_files(mission_root: Path) -> list[Path]:
    """The files the text scan reads. ONE derivation, asked twice.

    `scan_closure` asks it to judge and
    `verify_verdict_describes_package` asks it again afterwards to find out
    whether anything moved under the verdict. Two spellings of this list is
    how the two would quietly stop describing the same set.
    """
    return sorted(p for p in mission_root.rglob("*")
                  if p.is_file() and p.suffix in _SCANNED_SUFFIXES)


def _verdict_inputs(mission_root: Path) -> list[Path]:
    """`_scanned_files` plus `project.godot`, which the autoload/plugin half
    reads and which carries no scanned suffix."""
    files = list(_scanned_files(mission_root))
    project = mission_root / "project.godot"
    if project.is_file():
        files.append(project)
    return sorted(files)


def _digest_inputs(mission_root: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for p in _verdict_inputs(mission_root):
        rel = p.relative_to(mission_root).as_posix()
        try:
            out[rel] = hashlib.sha256(p.read_bytes()).hexdigest()
        except OSError:
            # An input that cannot be read is recorded as such rather than
            # dropped: an absent entry would read as "this file was never
            # here", which is a different fact.
            out[rel] = "UNREADABLE"
    return out


def verify_verdict_describes_package(
        mission_root: Path, scan: ClosureResult,
        *, written_after: frozenset[str] = frozenset()) -> list[str]:
    """Say every way the package has changed since `scan` judged it.

    A PROBE. It reports and stops; whether a discrepancy should end the build
    is the caller's to decide and to explain.

    This exists because `export_mission` shipped a verdict about a package
    that did not exist yet. Measured on cold 9066's and 9067's shipped
    `LF_club_block_00{5,6}.portable-godot`: the verdict in the package said
    `ok: true, 0 issues, resource_count: 46`, and re-running the same scan on
    the same folder afterwards said `ok: false, 1 issue, resource_count: 48`
    -- `occluders.tscn` and `warmup.gd` were written after the judge looked,
    along with ~240 `.import` sidecars, `project.godot`, and two rewrites of
    `mission.tscn`. Moving the scan to the end fixes those packages. Only
    this check keeps the NEXT writer from doing it again, and a comment
    asking the next author to be careful is not a check.

    `written_after` names the relative paths that are ALLOWED to appear or
    change afterwards -- the manifests that describe the package and so
    cannot be inside it. Every one of them must also be a metadata file, or
    it would be judged in a later scan of the shipped folder and the two
    judges would disagree; the caller asserts that.
    """
    findings: list[str] = []
    now_present = {p.relative_to(mission_root).as_posix()
                   for p in mission_root.rglob("*") if p.is_file()}
    now_digest = _digest_inputs(mission_root)

    for rel in sorted(now_present - scan.present_names - written_after):
        findings.append(f"{rel}: written AFTER the closure verdict")
    for rel in sorted(scan.present_names - now_present - written_after):
        findings.append(f"{rel}: removed AFTER the closure verdict")
    for rel in sorted(set(now_digest) & set(scan.input_digest)):
        if rel in written_after:
            continue
        if now_digest[rel] != scan.input_digest[rel]:
            findings.append(f"{rel}: rewritten AFTER the closure verdict")
    return findings


def scan_closure(mission_root: Path) -> ClosureResult:
    result = ClosureResult(root=mission_root)
    files = _scanned_files(mission_root)
    result.resource_count = sum(
        1 for p in files if p.suffix in (".tscn", ".tres", ".gdshader", ".gd"))

    present = {p.relative_to(mission_root).as_posix() for p in mission_root.rglob("*")
               if p.is_file()}
    result.present_names = set(present)
    result.input_digest = _digest_inputs(mission_root)

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
