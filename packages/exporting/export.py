"""Export assembly (TDD 33).

Assembles the Dispatch shell-handoff plus localized presentation into a
self-contained, portable Godot 4.7 mission folder. Three modes (33.1-33.3):

  * portable-godot   -- runnable in a clean project, no authoring tools/add-ons
  * pure-shell       -- functional geometry + collision + anchors only
  * source-authoring -- includes source recipes/specs for re-authoring

Lux portability policy (33.6): a portable export either LOCALIZES the minimal
Lux runtime scripts into the mission folder, or BAKES presentation to
vertex/lightmap data so no Lux runtime is required. The default is 'localized'.
"""
from __future__ import annotations

import datetime as _dt
import shutil
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from packages.core.canonical import pretty_dumps
from packages.core.hashing import hash_file

MODE_PORTABLE = "portable-godot"
MODE_PURE_SHELL = "pure-shell"
MODE_SOURCE = "source-authoring"

LUX_LOCALIZED = "localized"
LUX_BAKED = "baked"

HANDOFF_LANGUAGE = (
    "This package contains a self-contained Godot 4.7 mission shell, presentation "
    "resources, gameplay anchors, proposed mission beats, and runtime integration "
    "requirements.\n\n"
    "Level Factory and its authoring tools are not required to consume this package.\n\n"
    "The production game runtime remains authoritative for mission progression, "
    "gameplay behavior, enemy AI, replication, persistence, late joining, "
    "reconnection, and online correctness.\n"
)

#: Whether a broken resource closure fails the export outright.
#:
#: False for the same reason ``deli_counter.stairwell.CONTAINMENT_ENFORCED`` and
#: ``WALKTEST_ENFORCED`` are: no export has ever been scanned at this point in
#: the pipeline, the first run that did found the current one broken, and
#: promoting on day one would fail every export before anyone has looked at one.
#:
#: The scan ALWAYS runs and ALWAYS writes its verdict to
#: export_closure_scan.json. This flag decides only whether the verdict stops
#: the build. Flipping it is its own pass, and wants the missing-art copy fixed
#: first -- otherwise it fails on a defect it did not cause.
CLOSURE_ENFORCED = False


class ExportClosureError(RuntimeError):
    """A portable export references resources it does not contain."""


# Files that carry presentation only (dropped in pure-shell mode).
_PRESENTATION_FILES = {"lux.applied.tscn", "lux.quality.json"}


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat()


@dataclass
class ExportProfile:
    mode: str = MODE_PORTABLE
    godot_version: str = "4.7"
    entry_scene: str = "mission.tscn"
    include_walk: bool = False
    lux_strategy: str = LUX_LOCALIZED
    include_source_authoring: bool = False
    include_validation: bool = True
    include_provenance: bool = True
    require_no_addons: bool = True
    require_no_autoloads: bool = True
    require_resource_closure: bool = True

    def as_dict(self) -> dict:
        return self.__dict__.copy()


@dataclass
class ExportResult:
    mission_id: str
    mode: str
    export_dir: Path
    zip_path: Path | None = None
    resource_manifest: dict = field(default_factory=dict)
    license_manifest: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "mission_id": self.mission_id, "mode": self.mode,
            "export_dir": str(self.export_dir),
            "zip_path": str(self.zip_path) if self.zip_path else None,
        }


def _copy_tree(src: Path, dst: Path, *, skip: set[str] = frozenset(),
               skip_dirs: set[str] = frozenset()) -> None:
    dst.mkdir(parents=True, exist_ok=True)
    for item in src.rglob("*"):
        if item.is_dir():
            continue
        if item.name in skip or item.name.endswith(".provenance.json"):
            continue
        rel = item.relative_to(src)
        # `skip` matches file NAMES. A directory cannot be excluded that way --
        # this walks files, so .godot/ would arrive one cache entry at a time.
        if skip_dirs and any(part in skip_dirs for part in rel.parts[:-1]):
            continue
        target = dst / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(item, target)


def _write_project_godot(export_dir: Path, entry_scene: str, mission_id: str) -> None:
    """A minimal, autoload-free, plugin-free project so the shell is portable."""
    (export_dir / "project.godot").write_text(
        "; Portable Level Factory mission shell (autoload-free, no editor plugins)\n"
        "config_version=5\n\n"
        "[application]\n"
        f'config/name="{mission_id} (shell)"\n'
        f'run/main_scene="res://{entry_scene}"\n\n'
        "[rendering]\n"
        'renderer/rendering_method="gl_compatibility"\n\n'
        "[debug]\n"
        "; Localized tool scripts are strict-clean under their home projects'\n"
        "; warning config; engine DEFAULTS escalate inference-on-Variant to a\n"
        "; load-killing error (proven on hardware: lux_root.gd:218 took two\n"
        "; dependents down as compile knock-ons). Warn, don't refuse to load.\n"
        "gdscript/warnings/inference_on_variant=1\n",
        encoding="utf-8",
    )


def build_resource_manifest(export_dir: Path) -> dict:
    files = sorted(p for p in export_dir.rglob("*") if p.is_file())
    return {
        "schema": "level_factory.portable_manifest.v0.1",
        "created_at": _now(),
        "resources": [
            {"path": p.relative_to(export_dir).as_posix(),
             "hash": hash_file(p), "size": p.stat().st_size}
            for p in files
        ],
    }


def build_license_manifest(tool_versions: dict[str, str | None]) -> dict:
    return {
        "schema": "level_factory.license_manifest.v0.1",
        "created_at": _now(),
        "note": "Attribution for tools that produced shell content.",
        "tools": [{"tool": t, "version": v} for t, v in sorted(tool_versions.items())],
    }


def export_mission(
    *,
    mission_id: str,
    handoff_dir: Path | None,
    presentation_dir: Path | None,
    source_dir: Path | None,
    profile: ExportProfile,
    tool_versions: dict[str, str | None],
    out_root: Path,
    graybox_dir: Path | None = None,
    layers=None,
    addon_sources: dict[str, Path] | None = None,
    composed_root: Path | None = None,
) -> ExportResult:
    export_dir = out_root / f"{mission_id}.{profile.mode}"
    if export_dir.exists():
        shutil.rmtree(export_dir)
    export_dir.mkdir(parents=True, exist_ok=True)
    layers = frozenset(layers or ())

    # 1. Copy the functional base. With the Gameplay layer this is the Dispatch
    # handoff (functional + shell contract + advisory objective layer); without
    # it, the graybox Lot site IS the deliverable base.
    skip: set[str] = set()
    if profile.mode == MODE_PURE_SHELL:
        skip |= _PRESENTATION_FILES
    if not profile.include_validation:
        skip |= {"validation"}
    base_dir = handoff_dir if (handoff_dir and handoff_dir.exists()) else graybox_dir
    if base_dir and base_dir.exists():
        _copy_tree(base_dir, export_dir, skip=skip)

    # 2. Localize presentation (unless pure-shell).
    if profile.mode != MODE_PURE_SHELL and presentation_dir and presentation_dir.exists():
        pres_target = export_dir / "presentation"
        _copy_tree(presentation_dir, pres_target)
        if profile.lux_strategy == LUX_LOCALIZED:
            # Copy only the minimal runtime scripts (no editor plugin needed).
            (export_dir / "presentation" / "LUX_RUNTIME.md").write_text(
                "Localized Lux runtime: presentation scripts are copied into this "
                "folder; enabling the Lux editor plugin is NOT required.\n",
                encoding="utf-8",
            )

    # 2.5 The composed res:// root -- the assets the presentation scene names.
    #
    # presentation_dir is the lux_apply job's out/, and that job emits exactly
    # three files: lux.applied.tscn and two json sidecars. The scene's
    # ext_resources are res://site_base.glb and res://art/zoo/*.glb, which live
    # one job upstream in <mission>.presentation_compose/out/presentation/.
    # That directory IS the res:// root Lux was run against -- stage_godot_project
    # copies a scene's sibling FILES flat and its sibling SUBDIRECTORIES with
    # their structure intact, which is precisely why site_base.glb resolves at
    # the root and the modules resolve under art/zoo/ and nowhere else. The
    # export has to reproduce that same root or the scene arrives with every
    # module reference dangling.
    #
    # It did. Measured 2026-08-01 on category5_baie_dore_001 --mode
    # portable-godot: 211 of the scene's 243 nodes instanced one of ten glb
    # files the package did not contain. The shell opened, applied Blue Hour
    # correctly, and rendered nothing but sky. Roadmap item 27.
    #
    # Skipped on the way in, and each for its own reason: project.godot,
    # HANDOFF.md and portable_resource_manifest.json because section 4 below
    # writes this export's own and the composer's describe a different root;
    # compose.summary.json because it is the composer's job log, not content;
    # .godot/ because an import cache is machine-specific and large; addons/
    # because a portable shell carries none by contract.
    if (profile.mode != MODE_PURE_SHELL
            and composed_root and composed_root.exists()):
        # RETRACTED, kept above what replaced it. This skipped site.tscn as
        # well, on this reasoning: "The composer emits its themed building AS
        # site.tscn ... Lot ALSO emits a site.tscn, meaning the assembled site
        # ... copying the composer's over it silently replaced the site with
        # one building. It also made write_entry_scene instance the same
        # building twice -- once unlit as site.tscn, once lit as
        # presentation/lux.applied.tscn, exactly coincident."
        #
        # Both halves were true when the presentation scene INLINED its
        # geometry. Once themed_site_assemble landed they stopped being: Lot
        # assembles the site by INSTANCING the composed building, so
        # lux.applied.tscn now carries `res://site.tscn` as a reference and
        # deleting the file broke the package --
        # "EXPORT_CLOSURE_BROKEN: lux.applied.tscn: unresolved res://site.tscn".
        #
        # The double-instancing was never this copy's fault either. It came
        # from write_entry_scene instancing site.tscn AND the presentation
        # scene as if they were peers, and that is fixed where it happens: the
        # entry now instances the presentation scene when there is one, and
        # site.tscn only for a graybox export with no presentation pass.
        #
        # site_main.tscn stays skipped. It is Deli Counter's own entry stub for
        # opening the composed building on its own, nothing shipped references
        # it, and an export carries one entry -- the one section 4 writes.
        _copy_tree(composed_root, export_dir,
                   skip={"project.godot", "HANDOFF.md",
                         "portable_resource_manifest.json",
                         "compose.summary.json",
                         "site_main.tscn"},
                   skip_dirs={".godot", "addons"})

    # 3. Source authoring (only in source mode).
    if profile.mode == MODE_SOURCE and source_dir and source_dir.exists():
        _copy_tree(source_dir, export_dir / "source")

    # 3.5 Resource-closure repair (TDD 33.5): bundle absolutely-referenced
    # assets, localize addon scripts (LUX_LOCALIZED made real), strip or
    # localize walk scenes, then synthesize the mission.tscn entry the
    # portability test instantiates. Runs for every mode; pure-shell has
    # already skipped presentation files so there is simply less to do.
    from packages.exporting.localize import localize_export, write_entry_scene
    closure_report = localize_export(
        export_dir,
        addon_sources=dict(addon_sources or {}),
        strip_walk=not profile.include_walk)
    write_entry_scene(export_dir, closure_report)
    (export_dir / "export_closure.json").write_text(
        pretty_dumps(closure_report.as_dict()), encoding="utf-8")

    # 3.6 Resource-closure VERDICT.
    #
    # localize_export above is the FIXER; closure.py's scan_closure is the
    # JUDGE, and localize.py's own docstring says exactly that. The fixer's
    # `unresolved` list fills only when a repair was ATTEMPTED and failed --
    # an absolute ref whose source is gone, an addon copy that raised. A scene
    # referencing res://art/zoo/wall.glb that was simply never copied in is not
    # something the fixer tries to repair, so it leaves no trace there at all.
    #
    # Until now the judge was reachable only from run_portability_test, a
    # separate command, off the path that produces the deliverable. Measured
    # 2026-08-01 on category5_baie_dore_001 --mode portable-godot:
    # export_closure.json reported "unresolved": [] while 211 of the
    # presentation scene's 243 nodes instanced ten .glb files the package did
    # not contain. The shell opened, lit itself correctly from its pinned
    # preset, and rendered nothing but sky.
    #
    # Note the two files are deliberately named apart. export_closure.json is
    # the fixer's log; export_closure_scan.json is the verdict. One name
    # answering two questions is how the empty export read as clean.
    from packages.exporting.closure import scan_closure
    scan = scan_closure(export_dir)
    (export_dir / "export_closure_scan.json").write_text(
        pretty_dumps(scan.as_dict()), encoding="utf-8")
    if not scan.ok:
        summary = (
            "EXPORT_CLOSURE_BROKEN: %d unresolved res:// reference(s), "
            "%d absolute path(s), %d external reference(s), "
            "%d required plugin(s), %d required autoload(s)"
            % (scan.missing_resource_count, scan.absolute_path_count,
               scan.external_reference_count, scan.required_plugin_count,
               scan.required_autoload_count))
        detail = "\n  ".join(scan.issues[:20])
        if len(scan.issues) > 20:
            detail += "\n  ... and %d more" % (len(scan.issues) - 20)
        if CLOSURE_ENFORCED:
            raise ExportClosureError(summary + "\n  " + detail)
        print("[export] WARNING " + summary)
        for issue in scan.issues[:20]:
            print("[export]   " + issue)
        if len(scan.issues) > 20:
            print("[export]   ... and %d more" % (len(scan.issues) - 20))

    # 4. project.godot, HANDOFF.md, manifests.
    _write_project_godot(export_dir, profile.entry_scene, mission_id)
    (export_dir / "HANDOFF.md").write_text(HANDOFF_LANGUAGE, encoding="utf-8")

    resource_manifest = build_resource_manifest(export_dir)
    (export_dir / "portable_resource_manifest.json").write_text(
        pretty_dumps(resource_manifest), encoding="utf-8")
    license_manifest = build_license_manifest(tool_versions)
    (export_dir / "LICENSES.json").write_text(
        pretty_dumps(license_manifest), encoding="utf-8")
    (export_dir / "export_profile.json").write_text(
        pretty_dumps(profile.as_dict()), encoding="utf-8")
    parts = ["graybox"] + [x for x in ("art", "gameplay") if x in layers]
    (export_dir / "output_layers.json").write_text(pretty_dumps({
        "schema": "level_factory.output_layers.v0.1",
        "layers": sorted(layers), "label": "+".join(parts),
    }), encoding="utf-8")

    return ExportResult(
        mission_id=mission_id, mode=profile.mode, export_dir=export_dir,
        resource_manifest=resource_manifest, license_manifest=license_manifest,
    )


def zip_export(result: ExportResult) -> Path:
    """Deterministic ZIP (sorted entries, fixed timestamps)."""
    zip_path = result.export_dir.with_suffix(".zip")
    files = sorted(p for p in result.export_dir.rglob("*") if p.is_file())
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in files:
            arc = f.relative_to(result.export_dir.parent).as_posix()
            info = zipfile.ZipInfo(arc, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            zf.writestr(info, f.read_bytes())
    result.zip_path = zip_path
    return zip_path
