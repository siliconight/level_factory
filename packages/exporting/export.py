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

# Files that carry presentation only (dropped in pure-shell mode).
_PRESENTATION_FILES = {"lux.applied.tscn", "lux.quality.json"}


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat()


@dataclass
class ExportProfile:
    mode: str = MODE_PORTABLE
    godot_version: str = "4.7"
    entry_scene: str = "mission.tscn"
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


def _copy_tree(src: Path, dst: Path, *, skip: set[str] = frozenset()) -> None:
    dst.mkdir(parents=True, exist_ok=True)
    for item in src.rglob("*"):
        if item.is_dir():
            continue
        if item.name in skip or item.name.endswith(".provenance.json"):
            continue
        rel = item.relative_to(src)
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
        'renderer/rendering_method="gl_compatibility"\n',
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

    # 3. Source authoring (only in source mode).
    if profile.mode == MODE_SOURCE and source_dir and source_dir.exists():
        _copy_tree(source_dir, export_dir / "source")

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
