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
import re
import shutil
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from packages.core.canonical import pretty_dumps
from packages.core.hashing import hash_file
from packages.core.ids import (export_archive_name,
                               export_build_dir_name,
                               export_package_dir_name)

MODE_PORTABLE = "portable-godot"
MODE_PURE_SHELL = "pure-shell"
MODE_ART_UNLIT = "art-unlit"
MODE_SOURCE = "source-authoring"

#: Modes that ship no Lux RESULT. Not the same set as modes that ship no
#: art: `art-unlit` declines the render and keeps everything Pixelcoat,
#: Zoo and Patina built, which is the entire reason it exists.
UNLIT_MODES = frozenset({MODE_PURE_SHELL, MODE_ART_UNLIT})

#: Every mode this module can build. The CLI's `--mode` choices must
#: equal this set, and `test_export_modes_agree.py` asserts it by
#: parsing main.py rather than by anyone remembering.
#:
#: There used to be a fourth list: `cmd_export` kept a `mode_map` that
#: mapped each CLI string to the constant of the same value -- an
#: identity dict whose only effect was to raise KeyError on a mode it had
#: not been told about. It did exactly that the first time `art-unlit`
#: was typed at a real workspace.
MODES = frozenset({MODE_PORTABLE, MODE_ART_UNLIT, MODE_PURE_SHELL,
                   MODE_SOURCE})


def ships_lux(mode: str) -> bool:
    """Does a package built in this mode carry Lux's applied scene?

    A NAMED QUESTION because `profile.mode == MODE_PURE_SHELL` was
    answering three different ones, and only stayed correct while
    pure-shell was the only mode that declined anything. The third of
    those branches -- the composed themed root -- deliberately does NOT
    use this: an unlit art package is exactly the one that wants it.
    """
    return mode not in UNLIT_MODES

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
#: TRUE since 2026-08-12. It was False for the same reason
#: ``deli_counter.stairwell.CONTAINMENT_ENFORCED`` and ``WALKTEST_ENFORCED``
#: are: no export had ever been scanned at this point in the pipeline, the
#: first run that did found the current one broken, and promoting on day one
#: would have failed every export before anyone had looked at one. The stated
#: precondition was "wants the missing-art copy fixed first -- otherwise it
#: fails on a defect it did not cause."
#:
#: That precondition is met, and meeting it took three fixes, not one:
#:
#:   * THE MISSING ART. QA harnesses stripped, and the root `site.tscn` copy
#:     decided by the presentation scene instead of guessed. 21 unresolved -> 0.
#:   * THE SCANNER. It resolved `res://` by suffix -- which Godot has never
#:     done -- and certified the broken package at `ok: true, 0 missing`. With
#:     the suffix match renamed to what it actually finds: 132 misrooted.
#:   * THE PACKAGES. Each building is staged as its own `res://` root and was
#:     copied under another without rewriting. 137 references rerooted, 5 of
#:     which had been resolving to the site's base mesh instead of dangling.
#:
#: lot_demo_001 --mode portable-godot then passed with the engine agreeing:
#: `parser_error_count: 0`, `shader_error_count: 0`, `scene_instantiated: true`,
#: `status: PASS` in a clean Godot 4.7 project.
#:
#: The scan ALWAYS runs and ALWAYS writes its verdict to
#: export_closure_scan.json. This flag decides only whether the verdict stops
#: the build. Setting it back to False for a mode nobody has scanned yet is a
#: legitimate move -- but write down WHICH mode and WHY, because the comment
#: that used to sit here outlived its own reason without anyone noticing.
CLOSURE_ENFORCED = True


class ExportClosureError(RuntimeError):
    """A portable export references resources it does not contain."""


# Files that carry presentation only (dropped in pure-shell mode).
_PRESENTATION_FILES = {"lux.applied.tscn", "lux.quality.json"}

#: The first file inside the package, and named so a reader opens it.
#: Everything the folder name gave up lives here -- see
#: docs/EXPORT_NAMING.md.
EXPORT_MANIFEST_NAME = "LF_MANIFEST.json"
EXPORT_MANIFEST_SCHEMA = "level_factory.export_manifest.v1"


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
    #: Composed ONCE, at build time, and used by zip_export. The
    #: manifest inside the package states this string before the
    #: archive exists, so a second composition of it is a chance for
    #: the file inside to disagree with the file containing it.
    archive_name: str | None = None
    package_dir_name: str | None = None
    resource_manifest: dict = field(default_factory=dict)
    license_manifest: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "mission_id": self.mission_id, "mode": self.mode,
            "export_dir": str(self.export_dir),
            "zip_path": str(self.zip_path) if self.zip_path else None,
            "archive_name": self.archive_name,
            "package_dir_name": self.package_dir_name,
        }


def _copy_tree(src: Path, dst: Path, *, skip: set[str] = frozenset(),
               skip_dirs: set[str] = frozenset(),
               skip_rel: set[str] = frozenset()) -> None:
    dst.mkdir(parents=True, exist_ok=True)
    for item in src.rglob("*"):
        if item.is_dir():
            continue
        if item.name in skip or item.name.endswith(".provenance.json"):
            continue
        rel = item.relative_to(src)
        # `skip_rel` matches a RELATIVE PATH, which `skip` cannot: the note
        # below already says `skip` matches names, and a composed root holds
        # `site.tscn` at its root AND one per building under `lot/<id>/`.
        # Skipping by name took all six. Measured: five of them, and
        # `lux.applied.tscn: unresolved res://lot/<archetype>/site.tscn` x5,
        # with the review frame going from 88% void to 98% because every
        # building had left the package.
        if rel.as_posix() in skip_rel:
            continue
        # `skip` matches file NAMES. A directory cannot be excluded that way --
        # this walks files, so .godot/ would arrive one cache entry at a time.
        if skip_dirs and any(part in skip_dirs for part in rel.parts[:-1]):
            continue
        target = dst / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(item, target)


#: `res://site.tscn`, as an ext_resource line would carry it.
_ROOT_SITE_REF = re.compile(r'^\[ext_resource[^\]]*path="res://site\.tscn"',
                            re.M)


#: One `lot/<id>/site.tscn` reference in an assembly scene. The id is whatever
#: `_write_site_spec` put there -- a literal "shell" on the single-shell branch,
#: an archetype id on the varied one -- so this reads it rather than assuming.
_LOT_SITE_REF = re.compile(r'path="(lot/([^"/]+)/site\.tscn)"')


def _assembly_building_dir(themed_site_dir, composed_root) -> str:
    """``"lot/<id>"`` when the composed root belongs under it, else ``""``.

    ROADMAP 49. Returns non-empty only when ALL of these hold, and each one
    is a fact read off disk rather than a guess about the mission:

      * there is an assembly scene (`themed_site_assemble`'s `site.tscn`)
      * it names exactly ONE `lot/<id>/site.tscn` -- more than one is a varied
        lot, which the composed root already carries and which this must not
        touch
      * the composed root has no `lot/` of its own -- if it does, it is that
        varied lot and its buildings are already in the right place

    Returns a POSIX-style relative string because it is joined onto a Path by
    the caller and compared in tests; `Path` would make the test assertion
    platform-dependent for no benefit.

    Never raises. An unreadable assembly scene answers "" -- the previous
    behaviour -- because a copy destination is not the place to discover a
    corrupt scene, and the closure scan reports it a few lines later with the
    detail this function does not have.
    """
    if not themed_site_dir:
        return ""
    scene = Path(themed_site_dir) / "site.tscn"
    if not scene.is_file():
        return ""
    if composed_root and (Path(composed_root) / "lot").is_dir():
        return ""
    try:
        text = scene.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    hits = {m.group(1) for m in _LOT_SITE_REF.finditer(text)}
    if len(hits) != 1:
        return ""
    return str(next(iter(hits))).rsplit("/", 1)[0]


def _root_site_wanted(presentation_dir: Path | None) -> bool:
    """Does the presentation scene reference the composer's root ``site.tscn``?

    TRUE WHEN THERE IS NO PRESENTATION SCENE TO ASK. A graybox export has no
    art pass, its entry IS `site.tscn` (`write_entry_scene` says so), and
    withholding it on the strength of a question nobody answered would ship an
    empty package. Absence of evidence decides toward including, always.
    """
    if presentation_dir is None:
        return True
    scene = Path(presentation_dir) / "lux.applied.tscn"
    if not scene.is_file():
        return True
    try:
        return bool(_ROOT_SITE_REF.search(
            scene.read_text(encoding="utf-8", errors="replace")))
    except OSError:
        return True


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
    themed_site_dir: Path | None = None,
    source_dir: Path | None,
    profile: ExportProfile,
    tool_versions: dict[str, str | None],
    out_root: Path,
    graybox_dir: Path | None = None,
    layers=None,
    addon_sources: dict[str, Path] | None = None,
    composed_root: Path | None = None,
    # EVERY ONE OF THESE DEFAULTS TO None, and that is not laziness.
    # tests/unit/test_closure_export.py calls this with the old
    # argument set; a required parameter would fail the unit suite on a
    # patch about filenames. It also decides the behaviour for a caller
    # that has nothing to pass -- the part is written NA, not dropped.
    seed=None,
    candidate_id: str | None = None,
    factory_version: str | None = None,
    factory_tag: str | None = None,
    built_utc: str | None = None,
    # The CERTIFIED SET from factory.manifest.json, which is what
    # factory_tag recovers. Distinct from `tool_versions` above, which
    # is the ADAPTER versions -- the code that drives each tool, not the
    # tool. They differ by an order of magnitude (lot's adapter is
    # 0.4.0; lot is 0.41.0) and 0.27.0 shipped the wrong one of the two
    # under a key named `tools`.
    pinned_tools: dict | None = None,
) -> ExportResult:
    # ONE INSTANT, used by the archive name and the manifest both. Two
    # calls to the clock would put two different times on one build.
    built_utc = built_utc or _now()
    archive_name = export_archive_name(
        mission_id, profile_mode=profile.mode, seed=seed,
        built_utc=built_utc, factory_version=factory_version)
    package_dir_name = export_package_dir_name(mission_id)
    export_dir = out_root / export_build_dir_name(mission_id, profile.mode)
    if export_dir.exists():
        shutil.rmtree(export_dir)
    export_dir.mkdir(parents=True, exist_ok=True)
    layers = frozenset(layers or ())
    # THE MANIFEST DESCRIBES THE PACKAGE, NOT THE RUN. `cmd_export`
    # derives layers from what is on disk, so a lit mission reports the
    # light layer -- correctly, `lux_apply` ran. Exporting art-unlit from
    # that same mission would then declare a layer this package does not
    # contain, which is 0.34.0's failure with the sign reversed.
    if not ships_lux(profile.mode):
        from packages.pipeline.planner import LAYER_LIGHT
        layers = layers - {LAYER_LIGHT}

    # 1. Copy the functional base. With the Gameplay layer this is the Dispatch
    # handoff (functional + shell contract + advisory objective layer); without
    # it, the graybox Lot site IS the deliverable base.
    skip: set[str] = set()
    if not ships_lux(profile.mode):
        skip |= _PRESENTATION_FILES
    if not profile.include_validation:
        skip |= {"validation"}
    # DISPATCH'S MANIFEST IS NOT THIS PACKAGE'S MANIFEST. Roadmap 50.
    #
    # `resource_manifest.json` is `dispatch.resource_manifest.v0.2`, written
    # by the handoff stage to describe the handoff. The export then copies
    # that directory in, overwrites `mission.tscn` with its own portable
    # entry, adds the composed building and its art, and writes
    # `portable_resource_manifest.json` -- so by the time the package is
    # finished, Dispatch's file describes something that no longer exists.
    #
    # Measured on unlit_probe_001, 2026-08-16, art-unlit:
    #
    #     resource_manifest.json           17 entries, mission.tscn 16,246 B
    #     mission.tscn on disk                                          688 B
    #     portable_resource_manifest.json  58 resources, sha256 + size each,
    #                                      including lot/shell/site.tscn and
    #                                      all 31 art/zoo GLBs
    #
    # Two manifests, and the stale one has the better name. A recipient
    # checking what they received opens `resource_manifest.json` first.
    #
    # DROPPED RATHER THAN REGENERATED, and the precedent is twelve lines
    # below: the composed-root copy already skips
    # `portable_resource_manifest.json` for exactly this reason -- the
    # composer writes one, LF writes its own, and shipping both would be two
    # answers to one question. This is that rule applied to the other
    # manifest and the other producer.
    #
    # IF A RECIPIENT CONTRACT EVER REQUIRES THE NAME `resource_manifest.json`,
    # the fix is to REGENERATE it here rather than to un-skip it. The problem
    # was never the file; it was the file being stale.
    skip |= {"resource_manifest.json"}
    base_dir = handoff_dir if (handoff_dir and handoff_dir.exists()) else graybox_dir
    # THE GRAYBOX IS A BASE, NOT AN ALTERNATIVE. The line above is an
    # either/or, and the comment three lines above it already describes
    # the intent correctly: the Dispatch handoff is a LAYER, and a layer
    # goes on a base rather than replacing it. The moment a mission gained
    # a dispatch_handoff, Lot's site.tscn stopped shipping.
    #
    # Measured 2026-08-15, two exports of lot_demo_001: the one from
    # 2026-08-10 -- before this mission had a handoff -- carries a 25,378
    # byte site.tscn and a 688 byte entry; today's carries neither, and
    # its entry instances nothing. Closure passed it, because closure
    # walks FROM the entry.
    #
    # PURE-SHELL ONLY. Art modes take their assembly from
    # themed_site_assemble in 2.5 below, and laying the graybox under a
    # themed package would ship greybox geometry it has no use for -- the
    # same reasoning that keeps art-unlit out of the composed-root branch.
    if (profile.mode == MODE_PURE_SHELL and graybox_dir
            and graybox_dir.exists() and base_dir is not graybox_dir):
        _copy_tree(graybox_dir, export_dir, skip=skip)
    if base_dir and base_dir.exists():
        _copy_tree(base_dir, export_dir, skip=skip)

    # 2. Localize presentation (unless the mode ships no Lux).
    if ships_lux(profile.mode) and presentation_dir and presentation_dir.exists():
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
    # PURE-SHELL ALONE, and `art-unlit` is deliberately absent from this
    # one: the composed themed content IS what an unlit art package
    # ships. `ships_lux` asks a different question and using it here
    # would strip the art out of the art-without-light mode.
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
        # site.tscn: ASKED, not decided here for a third time.
        #
        # The comment above records this being skipped, then un-skipped when
        # closure broke with `lux.applied.tscn: unresolved res://site.tscn`.
        # Both positions were right for their own mission shape. A single-shell
        # compose INLINES its geometry and its presentation scene DOES name
        # `res://site.tscn`. A themed multi-building site instances five
        # packages and names `res://lot/<archetype>/site.tscn` instead --
        # measured on lot_demo_001: five such refs, no `res://site.tscn`.
        #
        # Shipping it anyway is not free. The composer's `art/dressing`,
        # `art/fixtures` and `art/zoo` are EMPTY for a themed mission, and
        # `_copy_tree` walks files, so three empty directories copy as nothing
        # and the scene arrives referencing twenty modules that exist nowhere
        # on disk. Measured: EXPORT_CLOSURE_BROKEN, 21 unresolved of 40
        # resources. The buildings' own modules are fine under
        # `lot/<archetype>/art/zoo/` and resolve.
        #
        # So the presentation scene decides. It is the artefact that knows.
        # BY RELATIVE PATH, not by name. `skip` matches basenames anywhere in
        # the tree and a composed root holds `site.tscn` at its root AND one
        # per building under `lot/<id>/`; a name skip took all six, and the
        # presentation scene came back with five unresolved buildings.
        wanted = _root_site_wanted(presentation_dir)
        # WHERE THE COMPOSED ROOT LANDS. Roadmap 49.
        #
        # It used to land at the package root, always. That is right for a
        # VARIED lot, whose composed root already holds `lot/<archetype>/`
        # per building and whose references therefore resolve. It is wrong
        # for a SINGLE-SHELL mission: there the composed root IS the one
        # building, flat -- `site.tscn`, `site_base.glb`, `art/` -- and step
        # 2.5 below then overwrites the root `site.tscn` with the ASSEMBLY
        # scene, whose only `ext_resource` is `lot/<id>/site.tscn`. Nothing
        # ever created that directory in the package, so every single-shell
        # themed export since 0.37.0 has shipped a level that cannot open,
        # in BOTH modes. Measured on unlit_probe_001: 56 files, entry
        # reaches 2.
        #
        # ASK THE ARTEFACT, do not infer the mission shape. The assembly
        # scene names the path it needs and `site_packages.py` has already
        # staged exactly that directory beside it; `_assembly_building_dir`
        # reads the name out of the scene rather than guessing from a flag.
        # `_root_site_wanted` is NOT that test and was briefly mistaken for
        # it: it returns True whenever there is no Lux scene to ask, which
        # on a mission that never ran Lux is every time.
        building_rel = _assembly_building_dir(themed_site_dir, composed_root)
        dest = (export_dir / building_rel) if building_rel else export_dir
        # AND THE COMPOSER'S OWN site.tscn IS WANTED when it is going under
        # `lot/<id>/`, because there it IS the building the assembly names.
        # Skipping it would recreate the same dangling reference one
        # directory down.
        _copy_tree(composed_root, dest,
                   skip={"project.godot", "HANDOFF.md",
                         "portable_resource_manifest.json",
                         "compose.summary.json",
                         "site_main.tscn"},
                   skip_rel=(set() if (wanted or building_rel)
                             else {"site.tscn"}),
                   skip_dirs={".godot", "addons"})

    # 2.5 THE ASSEMBLY SCENE.
    #
    # `themed_site_assemble` is the stage that makes a PLACE -- Lot re-run
    # over the composed buildings at the placements the graybox candidate
    # was judged on -- and its `site.tscn` was exported into nothing. The
    # lit package got away with that because
    # `presentation/lux.applied.tscn` is Lux's output OVER the assembly
    # and stands in for it. Drop Lux and the `lot/<archetype>/site.tscn`
    # packages are left with nothing that positions them: measured on
    # lot_demo_001, an art-unlit export of 180 files whose entry
    # instanced nothing at all.
    #
    # NOT the RETRACTED position in the comment above. That argument is
    # about the COMPOSER's root site.tscn, whose art/dressing,
    # art/fixtures and art/zoo are empty for a themed mission and which
    # arrives referencing twenty modules that exist nowhere -- measured,
    # 21 unresolved of 40. This is a different file from a different
    # stage, and it names the five lot/<archetype>/site.tscn the package
    # already carries.
    #
    # AFTER the composed copy, deliberately. `_root_site_wanted` may have
    # let the composer's own root site.tscn through, and for a
    # single-shell mission that file is the composed BUILDING while this
    # is the assembled SITE. Lux is run against the assembly, so a
    # reference to res://site.tscn has to resolve to the assembly.
    if profile.mode != MODE_PURE_SHELL and themed_site_dir:
        themed_scene = Path(themed_site_dir) / "site.tscn"
        if themed_scene.is_file():
            shutil.copy2(str(themed_scene), str(export_dir / "site.tscn"))

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
        # EVERY counter `ClosureResult.ok` reads, or the message lies. This
        # reported five of seven for as long as there were seven: an export
        # failing purely on misrooted or unresolved-relative references raised
        # with every number in its own summary reading zero. Tolerable while
        # the flag only printed; the moment it raises, this string IS the
        # diagnosis. A counter added to `ok` gets added here in the same edit.
        summary = (
            "EXPORT_CLOSURE_BROKEN: %d unresolved res:// reference(s), "
            "%d misrooted, %d unresolved relative, %d absolute path(s), "
            "%d external reference(s), %d required plugin(s), "
            "%d required autoload(s)"
            % (scan.missing_resource_count, scan.misrooted_resource_count,
               scan.unresolved_relative_count, scan.absolute_path_count,
               scan.external_reference_count, scan.required_plugin_count,
               scan.required_autoload_count))
        detail = "\n  ".join(scan.issues[:20])
        if len(scan.issues) > 20:
            detail += "\n  ... and %d more" % (len(scan.issues) - 20)
        if CLOSURE_ENFORCED:
            raise ExportClosureError(
                summary + "\n  " + detail + "\n  full verdict: "
                + str(export_dir / "export_closure_scan.json"))
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

    # 5. LF_MANIFEST.json -- everything the folder name gave up.
    #
    # WRITTEN LAST, after build_resource_manifest has already walked the
    # tree, so the package's resource manifest does not list a file that
    # describes it.
    #
    # `verified` carries the one check that ran INSIDE this build.
    # portability-test is a separate command that runs afterwards
    # against the build directory, so at this moment its answer does not
    # exist and claiming it would be inventing one. The note is there
    # because a block listing only passes invites a reader to assume the
    # rest -- and because the absence of walktest or nav-gate results
    # here is a limit of what export can see, not a claim they were
    # skipped.
    (export_dir / EXPORT_MANIFEST_NAME).write_text(pretty_dumps({
        "schema": EXPORT_MANIFEST_SCHEMA,
        "mission": mission_id,
        "candidate": candidate_id,
        "seed": seed,
        "profile": profile.mode,
        "built_utc": built_utc,
        "factory_version": factory_version,
        "factory_tag": factory_tag or (
            f"factory-v{factory_version}" if factory_version else None),
        "tools": (dict(sorted(pinned_tools.items()))
                  if pinned_tools else None),
        "tools_source": ("factory.manifest.json" if pinned_tools
                         else None),
        # NOT the same numbers, and no longer pretending to be.
        "adapters": {k: v for k, v in sorted(tool_versions.items())},
        "godot_version": profile.godot_version,
        "package_dir": package_dir_name,
        "archive_name": archive_name,
        "layers": sorted(layers),
        "verified": {
            "export_closure": "ok" if scan.ok else "BROKEN",
            "not_run": ["portability -- runs after the build, as a separate command"],
            "note": "This block records what THIS BUILD checked. Pipeline-stage results (walktest, nav gate, grades) are not visible from here; their absence is not a claim they did not run.",
        },
    }), encoding="utf-8")

    return ExportResult(
        mission_id=mission_id, mode=profile.mode, export_dir=export_dir,
        archive_name=archive_name, package_dir_name=package_dir_name,
        resource_manifest=resource_manifest, license_manifest=license_manifest,
    )


def zip_export(result: ExportResult) -> Path:
    """Deterministic ZIP (sorted entries, fixed timestamps)."""
    # APPEND, do not substitute. `with_suffix(".zip")` reads
    # `.portable-godot` as a file extension and replaces it, which is the
    # whole reason the archive was `lot_demo_001.zip` with no profile in
    # it. Nobody decided to drop it; a path helper ate it.
    # The build-time name if there is one. The fallback is 0.26.0's
    # behaviour, kept so a caller that built an ExportResult by hand --
    # the unit suite does -- still gets an archive rather than a crash.
    zip_path = result.export_dir.parent / (
        result.archive_name or (result.export_dir.name + ".zip"))
    # THE FOLDER INSIDE THE ARCHIVE IS NOT THE BUILD DIRECTORY. The
    # build dir carries the profile so two profiles can coexist in one
    # workspace; the folder a recipient drops in must NOT change between
    # exports, or every res:// path they integrated moves. Same bytes,
    # different name, and the archive is the only place that is true.
    top = result.package_dir_name or result.export_dir.name
    files = sorted(p for p in result.export_dir.rglob("*") if p.is_file())
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in files:
            arc = (Path(top) / f.relative_to(result.export_dir)).as_posix()
            info = zipfile.ZipInfo(arc, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            zf.writestr(info, f.read_bytes())
    result.zip_path = zip_path
    return zip_path
