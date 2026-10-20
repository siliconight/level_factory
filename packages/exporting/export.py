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
import json
import re
import shutil
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from packages.core.canonical import pretty_dumps
from packages.core.godot_project import (count_package_probes,
                                          package_light_budget,
                                          rendering_block,
                                          set_occlusion_culling, shader_globals_block)
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


def output_layers_record(layers) -> dict:
    """`output_layers.json`: the layers this package carries, and its label in
    ONE spelling, the planner's (0.213.0, the factory's roadmap 257). This file
    spelled the label from `("art", "gameplay")` alone while
    `planner.label_for_layers` spelled the whole set, so a package carrying
    the light said `graybox+art+gameplay` of itself."""
    from packages.pipeline.planner import label_for_layers
    layers = sorted(layers or ())
    return {"schema": "level_factory.output_layers.v0.1", "layers": layers,
            "label": label_for_layers(layers)}


def handoff_layers_text(layers, mode: str) -> str:
    """HANDOFF.md's last paragraph (0.213.0, the factory's roadmap 257): what
    this package is made of, layer by layer, and that the light is Lux's
    result, a layer apart from the art it lights. `output_layers.json` and
    `LF_MANIFEST.json` carry the same names."""
    from packages.pipeline.planner import LAYER_ART, LAYER_GAMEPLAY, LAYER_LIGHT
    layers = frozenset(layers or ())
    parts = ["the graybox base (Deli Counter's shells with their collision, "
             "assembled by Lot, with navigation)"]
    if LAYER_ART in layers:
        parts.append("the ART layer (Zoo's themed modules, props and dressing, "
                     "Pixelcoat's skins, Patina's cohesion -- and the light "
                     "FIXTURES, which are geometry whoever lights them, with "
                     "their `LuxEmit` markers)")
    if LAYER_LIGHT in layers:
        parts.append("the LIGHT layer (Lux's applied scene and its baked "
                     "lightmap: the render decisions)")
    if LAYER_GAMEPLAY in layers:
        parts.append("the GAMEPLAY layer (Dispatch's advisory objectives, "
                     "spawns and navigation hints)")
    text = "WHAT THIS PACKAGE IS MADE OF: " + "; ".join(parts) + ". "
    text += "THE LIGHT IS A LAYER OF ITS OWN, APART FROM THE ART. "
    if LAYER_LIGHT in layers:
        text += ("This package carries it. The same build exports without it as "
                 "`--mode art-unlit` -- the art and its fixtures unchanged -- for "
                 "a runtime that brings its own lighting.")
    elif mode == MODE_ART_UNLIT:
        text += ("This package was exported `art-unlit`: the art and its fixtures "
                 "with no Lux result. Light it yourself, or export the same build "
                 "`portable-godot` for Lux's.")
    else:
        text += "This package carries no light layer."
    return text + " `output_layers.json` and `LF_MANIFEST.json` name the layers.\n"


def handoff_text(layers, mode: str) -> str:
    """HANDOFF.md whole (0.215.1): `HANDOFF_LANGUAGE`, a blank line, the layers
    paragraph. 0.213.0 appended the paragraph straight after the language,
    whose last line ends with one newline, so it landed inside the paragraph
    before it (cold run 9314's package)."""
    return HANDOFF_LANGUAGE.rstrip("\n") + "\n\n" + handoff_layers_text(layers, mode)

LUX_LOCALIZED = "localized"
LUX_BAKED = "baked"

HANDOFF_LANGUAGE = (
    "This package contains a self-contained Godot 4.7 mission shell, presentation "
    "resources, gameplay anchors, proposed mission beats, and runtime integration "
    "requirements.\n\n"
    "IMPORT BEFORE YOU RUN IT. Godot cannot load a .glb until it has imported it. This "
    "package ships the .import sidecars, so your import uses the settings this level was "
    "built and checked with rather than the engine defaults -- but not the .godot/ cache, "
    "which is machine-specific. Open the project once in the editor, or run "
    "`godot --headless --path <this folder> --import`, BEFORE running the scene. "
    "Skipping that step gives `No loader found for resource` on every mesh, then "
    "`Parse Error: [ext_resource] referenced non-existent resource`, and an empty "
    "level -- which looks like a broken package and is not one. Measured on this "
    "package: 1141 load errors without the import pass, 0 with it.\n\n"
    "THERE IS NO PLAYER IN THIS PACKAGE, BY CONTRACT. `mission.tscn` loads the "
    "content and stops; running it shows the level on a static default camera, "
    "which on most builds is a grey window. Your runtime brings its own character. "
    "TO WALK IT YOURSELF, do not add one here: from the factory that made it run "
    "`level-factory -C <workspace> walk <mission_id> --play` (in an unpacked "
    "factory, `.\\factory` on Windows or `sh factory.sh` on Linux in place of "
    "`level-factory`), which copies this package unchanged, adds a player at the "
    "package's own player_start, imports the copy and opens it. Two paths, one "
    "deliverable: the walk is a copy, this folder is what ships.\n\n"
    "TO VERIFY WHAT YOU RECEIVED, read `portable_resource_manifest.json`. It "
    "carries a sha256 and a size for every file in this package except two, and "
    "it names those two and why in its own `unlisted` block: itself (a file "
    "cannot contain the hash of its own finished bytes) and `LF_MANIFEST.json` "
    "(written after the manifest, so the manifest does not list a file that "
    "describes it). Its `accounting` block states the check:\n\n"
    "    listed + declared_unlisted == files in the package\n\n"
    "If that does not hold on the folder you received, the package is not the "
    "package that was built -- a truncated transfer or an edit in flight. "
    "Nothing else in this folder is expected to be absent from the manifest; up "
    "to level_factory 0.103.0 four files were, which is the defect this block "
    "exists to have made impossible.\n\n"
    "WHERE THE MISSION STARTS AND ENDS, AND WHERE RESPONDERS ARRIVE. "
    "`gameplay_anchors.json` tags the mission's start `mission_start` and its exit "
    "`extraction` -- on a heist, both at the crew's getaway van -- and tags each "
    "place responders can arrive `responder`. `responder_arrivals.json`, when "
    "present, says how each arrives: the road end a vehicle appears at, the lane it "
    "drives in by and the stop it pulls up at, both kept clear by the factory, and "
    "which way it faces. Spawning and timing responders is your runtime's.\n\n"
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


#: Whether a failed occluder bake fails the build. Same shape as
#: CLOSURE_ENFORCED above and for the same reason: cold run 9065 shipped a
#: package with `use_occlusion_culling=true` and zero occluders because this
#: step printed a warning and exited 0. Only consulted when the build HAD a
#: Godot to bake with -- a missing Godot is a setup problem and the package
#: that comes out of it is consistent, with the culler off.
OCCLUDERS_ENFORCED = True


#: How many times the export runs Godot's `--import` before it calls the
#: import failed (0.163.1). CHOSEN, not derived: one short pass was seen in
#: eight on cold run 9214's package, a pass costs about 40 s there, and 3
#: bounds a bad export at about two minutes before it says so.
IMPORT_PASSES = 3


class ExportClosureError(RuntimeError):
    """A portable export references resources it does not contain."""


class ExportOccluderError(RuntimeError):
    """The package's occluders could not be measured, or the culling flag and
    the occluders that shipped do not agree."""


class ExportImportError(RuntimeError):
    """Godot's `--import` was run `IMPORT_PASSES` times with a Godot present
    and left models the package carries unimported (0.163.1, cold run 9214):
    every step after it loads them."""


class ExportMergeError(RuntimeError):
    """The Empties' merge ran and its report could not be believed (0.143.0,
    roadmap 182): `packages/exporting/merge_empties.check` says which. The
    buildings' merge raises it too (0.223.0, roadmap 266;
    `packages/exporting/merge_buildings.check`)."""


class ExportManifestError(RuntimeError):
    """`portable_resource_manifest.json` does not account for the package it
    ships in -- a file present and neither listed nor declared unlisted, a
    listed file that is not there, or its own counts disagreeing with its own
    lists."""


class ExportGlbReferenceError(RuntimeError):
    """A shipped GLB names a file the package does not contain.

    The closure scan next door asks the same question of `res://` references
    and cannot see this one: a glTF `images[].uri` is a string inside a binary
    that no text scan reads. Zoo 1.2.0 moved every module texture onto that
    string and three packages went out as greybox behind three green gates --
    see `packages.exporting.glb_refs`, which owns the check."""


class ExportGreyboxSkinError(RuntimeError):
    """A themed package still draws greybox where theming claims to reach.

    Every other gate here measures traversal correctness or resource closure.
    This one measures whether the result reads as DESIGNED, which is the gap
    CLAUDE.md names: of the three problems found by actually playing a
    generated level, one was caught by an instrument and two by a person
    looking at the screen. The defect it was built from -- a bare `gb_floor`
    collar lining every ladder shaft and stairwell, 10.44 m2 over 8 openings
    on cold run 9070's package -- was found on a ladder, by the walker.

    Refuses on any greybox surface in a themed package since 0.218.0
    (`ExportProfile.require_no_greybox`; on slabs only before it, and with it
    off); see `packages.exporting.greybox_skin` for the census that set each
    threshold."""


class ExportDropEdgesError(RuntimeError):
    """A body can walk off an edge, indoors, that nothing guards and nothing
    declares -- or the census that asks could not be taken.

    Factory roadmap 173: every drop a body reaches is either GUARDED, or
    DECLARED, or a defect. The first two findings that were not the
    instrument's own were an office stair's landing open 6.67 m over its well
    and a flight's inner side open over the flight beside it, 12 edges no gate
    had seen; Deli Counter 0.225.0 fixed them at the source. See
    `packages.exporting.drop_edges` for what is refused and what is reported,
    and `assets/godot/walkable_edge.gd` for the measurement."""


class ExportWarmupError(RuntimeError):
    """The package's shader warm-up could not be shipped, or what shipped is
    not what `packages.exporting.warmup` writes.

    Fatal rather than a warning, on the same reasoning that made the occluder
    bake fatal in 0.98.0: a warning nobody reads is how a package ships with a
    runtime defect in it. This one is worth 8,564 ms in a single frame on cold
    run 9066's package, measured with both shader caches cleared."""


# Files that carry presentation only (dropped in pure-shell mode).
_PRESENTATION_FILES = {"lux.applied.tscn", "lux.quality.json"}

#: The first file inside the package, and named so a reader opens it.
#: Everything the folder name gave up lives here -- see
#: docs/EXPORT_NAMING.md.
EXPORT_MANIFEST_NAME = "LF_MANIFEST.json"
EXPORT_MANIFEST_SCHEMA = "level_factory.export_manifest.v1"


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat()


#: Whether `export` bakes the lights unless told otherwise (0.178.0, roadmap
#: 231): the command line's default since 0.144.0, now ONE constant read by
#: the parser (`apps/cli/main.py`) and by the site spec writer, which tells
#: Lot the package will bake (`render.lights_baked`) so Lot can cut its
#: plates for a lightmapped package (Lot 0.115.0's MESH_TILE_BAKED; the
#: culler pairs no baked light with a lightmapped mesh). `ExportProfile`
#: itself stays off, as its comment below says.
BAKE_LIGHTS_CLI_DEFAULT = True


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
    #: Refuse a package in which a body can walk off an undeclared edge
    #: indoors (0.216.0, factory roadmap 173; `packages/exporting/drop_edges`).
    #: On by default for the same reason the closure verdict is: a warning
    #: nobody reads is how a package ships with a fall in it. Off, the census
    #: still runs and its count is in the export log and `drop_edges_scan.json`.
    require_declared_drops: bool = True
    #: Refuse a THEMED package that draws any greybox surface (0.218.0, factory
    #: roadmap 168; `packages/exporting/greybox_skin`). Every kind of base
    #: geometry the census has met has an owner now, so a greybox surface is a
    #: pass that failed or a new kind without one. Off, the census reports and
    #: refuses slabs only, as it did before -- for a build that knowingly ships
    #: a new kind before its pass exists.
    require_no_greybox: bool = True
    #: The brief's weather word (0.130.0): what the shipped project's wind is
    #: written from. "clear" when the caller has no brief in hand.
    weather: str = "clear"
    #: Bake the steady lights into a lightmap (0.131.0, roadmap item 31,
    #: `packages/exporting/light_bake.py`). It needs a GPU and a display,
    #: and opens the Godot editor for about a minute. OFF HERE and ON at the
    #: command line since 0.144.0 (`apps/cli/main.py`): code that builds a
    #: profile, the tests among it, says what it wants, and a person running
    #: `export` gets the bake unless they pass --no-bake-lights.
    bake_lights: bool = False
    #: Merge the enterable buildings' static modules per room cell and material
    #: (0.223.0, the factory's roadmap 266; `packages/exporting/merge_buildings`).
    #: ON by default, a call meant to be changed: priced before it shipped (the
    #: factory's `docs/findings/interior_merge_266/`) at 11 % fewer draws and the
    #: worst heading 10.05 -> 9.14 ms p95, for a larger lightmap. It runs only with a
    #: Godot and Lot's site record in hand; without either the package keeps its
    #: per-module buildings, as it did before, and says so.
    merge_buildings: bool = True

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
               skip_rel: set[str] = frozenset(),
               skip_lot: set[str] = frozenset()) -> None:
    dst.mkdir(parents=True, exist_ok=True)
    for item in src.rglob("*"):
        if item.is_dir():
            continue
        if item.name in skip or item.name.endswith(".provenance.json"):
            continue
        rel = item.relative_to(src)
        # `skip_lot` (0.207.0) names `lot/<id>/` packages no scene stands
        # (`_standing_lot_ids`): by a relative path's first two parts, never
        # by a name, which would match anywhere in the tree
        if skip_lot and len(rel.parts) > 2 and rel.parts[0] == "lot" and rel.parts[1] in skip_lot:
            continue
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


def _standing_lot_ids(themed_site_dir):
    """The `lot/<id>/` packages the ASSEMBLY scene stands (0.207.0): every
    `lot/<id>/site.tscn` it names (`_LOT_SITE_REF`), as a set -- or None where
    there is no assembly scene to ask, or it names none, and then every
    composed package ships, as before. Absence of evidence decides toward
    including.

    WHY. The compose stage themes every Empty the brief was given, and an
    urban brief is given every corner block and mid-rise; a candidate stands
    some. Cold run 9297's package carried sixteen `lot/` packages and its
    assembly named thirteen: `gs_cornershop_a`, `_b` and `gs_midrise_g` --
    12.2 MB, and 95 of the 711 model imports `light_bake.mark_imports` sets
    to Static Lightmaps, each unwrapped for a lightmap at import -- shipped
    and imported for scenes nothing instanced."""
    if not themed_site_dir:
        return None
    scene = Path(themed_site_dir) / "site.tscn"
    try:
        text = scene.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    ids = {m.group(2) for m in _LOT_SITE_REF.finditer(text)}
    return ids or None


#: THE COMPOSER'S ROOT PAIR, kept or dropped TOGETHER (see the `skip_rel` at
#: the composed-root copy). `site.tscn` is the scene Deli Counter's composer
#: writes at the root of a composed package; `site_base.glb` is the greybox
#: base that scene alone names, as `res://site_base.glb` with
#: `id="0_greybox_base"`. Nothing else in a package can reach it: each
#: building names `res://lot/<id>/site_base.glb` instead.
#:
#: NOT `zoo_worldskin.gd`, which sits beside them at the composed root and
#: always ships. `project.godot` sets it as the `[importer_defaults] scene`
#: import script, so EVERY `.import` in the package -- all three buildings'
#: bases, the cover props, the kit modules -- names `res://zoo_worldskin.gd`
#: at the root. The copies under `lot/<id>/` are named by nothing.
_COMPOSED_ROOT_PAIR = frozenset({"site.tscn", "site_base.glb"})


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


#: The folder Zoo writes a module's shared textures into, beside its GLB.
#: Spelled here as well as in `zoo_keeper.core.gltf_textures.TEX_DIR` because
#: Level Factory does not import Zoo -- it consumes a directory Zoo wrote. Two
#: spellings of one contract drift, so `test_shared_texture_imports` asserts
#: they agree whenever Zoo is present beside this repo, and says so when it is
#: not rather than passing quietly.
SHARED_TEX_DIR = "_tex"

#: Import parameters pinned on every `.png.import` under `SHARED_TEX_DIR`.
#: The measurement behind each is in `_write_import_sidecars`'s docstring.
#:
#: COMPRESSED, AS EVERY EDITOR LEAVES THEM (0.190.0, the walker's call of
#: 2026-10-12). These were pinned lossless (`compress/mode=0`, the measurement
#: in `_write_import_sidecars`' docstring) with Godot's 3D detection left on,
#: and every editor that opened the package -- the light bake's, the walk copy
#: opened to be walked, a recipient's -- re-encoded each one it saw in use as
#: VRAM compressed (the factory's docs/findings/grader_speed/
#: editor_texture_probe.py: the bake's editor changed 426 texture sidecars of
#: cold run 9255's package). The lossless pin held only in a headless import,
#: and a package's textures depended on whether anyone had opened it. Offered
#: lossless everywhere or VRAM everywhere, the walker chose VRAM: what every
#: editor had shown, and less texture memory. So these are the editor's own
#: decisions, read off its sidecars, pinned before any import, the detection
#: off because nothing is left for it to decide.
SHARED_TEX_PINS = {
    "compress/mode": "2",
    "process/fix_alpha_border": "false",
    "mipmaps/generate": "true",
    "detect_3d/compress_to": "0",
}

#: And on the ones the models' glTF names as a NORMAL map (0.190.0): what the
#: editor writes when it finds one in use -- red-green compression, and the
#: roughness limiter Godot 4.7 sets on a normal map, pointed at that map
#: itself (`roughness/src_normal`, written per file by `_shared_pins_for`).
#: Read off the editor's sidecars for all 22 of cold run 9255's normal maps,
#: which are exactly the 22 its models' glTF names as `normalTexture`.
NORMAL_TEX_PINS = {"compress/normal_map": "1", "roughness/mode": "1"}
#: On the site's skins and the businesses' signs (0.190.0): what the editor
#: does to each one it finds in use -- VRAM compression and a mip chain, the
#: detection then off. `process/fix_alpha_border` stays as Godot writes it,
#: as the editor leaves it.
SURFACE_TEX_PINS = {
    "compress/mode": "2",
    "mipmaps/generate": "true",
    "detect_3d/compress_to": "0",
}
#: REPLACED (0.190.0): `FILTERED_TEX_PINS` pinned VRAM compression only on a
#: shared texture every sampler FILTERED (0.128.0, `_filtered_shared_textures`
#: reading the models' samplers off their glTF), the rest lossless for pixel
#: art shown at its own size: 7,304,813 B lossless against 1,374,528 B
#: compressed, for three props. Every shared texture is compressed now, and
#: no sampler decides.


def _glb_json(path: Path):
    """The JSON chunk of a binary glTF, or None when the file is not one."""
    import json as _json
    import struct as _struct
    try:
        with open(path, "rb") as fh:
            head = fh.read(20)
            if len(head) < 20 or head[:4] != b"glTF" or head[16:20] != b"JSON":
                return None
            return _json.loads(fh.read(_struct.unpack("<I", head[12:16])[0]))
    except (OSError, ValueError):
        return None


def _normal_map_shared_textures(export_dir: Path) -> set:
    """Every shared texture a model's glTF names as a material's
    `normalTexture` (0.190.0): the textures an editor detects as normal maps,
    22 of 22 on cold run 9255's package.

    Read off the GLBs, as the samplers were before it; a GLB this cannot read
    names none. The sidecar step reads it before it holds the models, for the
    reason it had to read the samplers so (0.189.0).
    """
    out = set()
    for glb in export_dir.rglob("*.glb"):
        doc = _glb_json(glb)
        if not isinstance(doc, dict):
            continue
        images = doc.get("images") or []
        textures = doc.get("textures") or []
        for mat in doc.get("materials") or []:
            if not isinstance(mat, dict):
                continue
            ti = (mat.get("normalTexture") or {}).get("index")
            if not isinstance(ti, int) or not 0 <= ti < len(textures):
                continue
            src = textures[ti].get("source")
            if not isinstance(src, int) or not 0 <= src < len(images):
                continue
            uri = images[src].get("uri")
            if not uri:
                continue
            png = (glb.parent / uri).resolve()
            if png.parent.name == SHARED_TEX_DIR:
                out.add(png)
    return out


def _apply_pins(sidecar: Path, pins: dict) -> bool:
    """Write `pins` on a sidecar's own lines; True when anything changed
    (0.190.0, the rule the pin functions shared, now one function).

    A sidecar missing a key is not written to. The key set is Godot's, read
    off what Godot wrote on the first pass; a file that does not carry one is
    a file these were not shown, and adding the line would be guessing at a
    schema."""
    try:
        lines = sidecar.read_text(encoding="utf-8").splitlines()
    except OSError:
        return False
    out, hit = [], False
    for ln in lines:
        key = ln.split("=", 1)[0]
        want = pins.get(key)
        if want is not None and ln != f"{key}={want}":
            out.append(f"{key}={want}")
            hit = True
        else:
            out.append(ln)
    if hit:
        sidecar.write_text("\n".join(out) + "\n", encoding="utf-8")
    return hit


def _shared_pins_for(sidecar: Path, export_dir: Path, normals) -> dict:
    """The pins a shared texture's sidecar takes: `SHARED_TEX_PINS`, and on a
    normal map `NORMAL_TEX_PINS` with its own path as `roughness/src_normal`,
    as the editor writes it (0.190.0)."""
    pins = dict(SHARED_TEX_PINS)
    png = sidecar.with_name(sidecar.name[:-len(".import")])
    if png.resolve() in normals:
        pins.update(NORMAL_TEX_PINS)
        pins["roughness/src_normal"] = '"res://%s"' % png.relative_to(export_dir).as_posix()
    return pins


def _pin_shared_texture_imports(export_dir: Path, normals=None) -> int:
    """Pin the shared textures' sidecars (`_shared_pins_for`, `_apply_pins`).

    Returns how many files were changed, so the caller's next import pass
    runs when this alone had something to do.

    The normal maps are read off the models (`_normal_map_shared_textures`);
    the sidecar step reads them before it holds the models (0.189.0).
    """
    changed = 0
    if normals is None:
        normals = _normal_map_shared_textures(export_dir)
    for sidecar in export_dir.rglob("*.png.import"):
        if sidecar.parent.name != SHARED_TEX_DIR:
            continue
        if _apply_pins(sidecar, _shared_pins_for(sidecar, export_dir, normals)):
            changed += 1
    return changed


def _shared_texture_pins_missing(export_dir: Path) -> list:
    """Every `SHARED_TEX_DIR` sidecar not carrying its pins, as ``(path, key,
    value found)`` with the first key that is off or absent -- what the
    package would ship wrong. The cache is not the package and is skipped."""
    normals = _normal_map_shared_textures(export_dir)
    out = []
    for sidecar in sorted(export_dir.rglob("*.png.import")):
        if sidecar.parent.name != SHARED_TEX_DIR or ".godot" in sidecar.parts:
            continue
        pins = _shared_pins_for(sidecar, export_dir, normals)
        have = {}
        for ln in sidecar.read_text(encoding="utf-8").splitlines():
            key, eq, value = ln.partition("=")
            if eq:
                have.setdefault(key, value)
        for key, want in pins.items():
            if have.get(key) != want:
                out.append((sidecar.relative_to(export_dir).as_posix(), key, have.get(key)))
                break
    return out


def _repin_after_imports(export_dir: Path) -> dict:
    """THE PINS AGAIN, AFTER THE LAST IMPORT, AND READ BACK (0.182.0).

    The pins are written once, between the sidecar step's two passes, and
    every import after that runs over them. One of those undoes some:
    measured (factory `docs/findings/texture_pins/`), the light bake's first
    `--import` -- re-importing every model `mark_imports` moved to static
    lightmaps -- imported the shared textures 1,843 times for 476 models, the
    same file again and again with several in flight, and 62 to 86 of 415
    sidecars came out with Godot's DEFAULTS, which ones varying between runs;
    nothing before it moved one, nothing after it put one back. Cold run
    9248 shipped 65 of them so. Pinning `detect_3d/compress_to=0` changed
    nothing (62, and the same 1,843), so the cause is the engine's import of
    a scene's textures and not a setting this owns. This is the backstop:
    the shared and the sign pins applied again over the files that ship,
    then every shared sidecar read back, and a package that still carries
    a wrong or a missing pin REFUSED -- a key a sidecar does not carry is
    not one this writes (`_pin_shared_texture_imports`' rule), so it fails
    here rather than shipping on the engine's default.

    The cache, gone by the time this runs, was built with the pins the race
    left; the light bake read those few textures without their mip chain or
    with the alpha border filled, and nothing it bakes depends on either.
    ``{"shared_repinned", "sign_repinned", "skin_repinned",
    "shared_sidecars"}`` -- the skins since 0.190.0."""
    shared = _pin_shared_texture_imports(export_dir)
    sign = _pin_sign_texture_imports(export_dir)
    skin = _pin_skin_texture_imports(export_dir)   # 0.190.0
    missing = _shared_texture_pins_missing(export_dir)
    if missing:
        raise ExportImportError(
            "%d shared-texture sidecar(s) do not carry their import pins after "
            "they were applied again; first: %s (%s=%s)"
            % (len(missing), missing[0][0], missing[0][1], missing[0][2]))
    total = sum(1 for s in export_dir.rglob("*.png.import")
                if s.parent.name == SHARED_TEX_DIR and ".godot" not in s.parts)
    return {"shared_repinned": shared, "sign_repinned": sign,
            "skin_repinned": skin, "shared_sidecars": total}


#: The folder Lot copies a dealt business's sign maps into, beside its scene
#: (Lot 0.69.0) -- and, since Lot 0.105.0, the pack's manifest with them.
SIGNS_DIR = "signs"
#: The folder the export copies the site's skins into, beside the site scene
#: (`skins/<map>`): Pixelcoat's maps for the ground, the kerbs and the paint
#: (0.190.0).
SKINS_DIR = "skins"


#: REPLACED (0.190.0): `_sign_pins` read a pack's `import_hints` (0.166.0) and
#: compressed and mipped a smooth pack's maps -- `linear` sampling and a mip
#: chain asked for -- and left a pixel pack's as Godot wrote them, the 3D
#: detection on in both. Every editor that opened the package compressed and
#: mipped every sign it saw in use, pixel or smooth. Since the walker's call,
#: compressed everywhere, every sign map takes `SURFACE_TEX_PINS`, whatever
#: its pack asks.


def _pin_skin_texture_imports(export_dir: Path) -> int:
    """Pin the site's skins (`SKINS_DIR`) as an editor leaves them (0.190.0):
    `SURFACE_TEX_PINS`. Unpinned before, they kept Godot's defaults --
    lossless, no mip chain, the 3D detection on -- and the editor compressed
    and mipped all eight of cold run 9255's. Returns how many sidecars changed
    (`_apply_pins`' rule: a key a sidecar does not carry is not given one)."""
    changed = 0
    for sidecar in sorted(export_dir.rglob("*.png.import")):
        if sidecar.parent.name != SKINS_DIR or ".godot" in sidecar.parts:
            continue
        if _apply_pins(sidecar, SURFACE_TEX_PINS):
            changed += 1
    return changed


def _pin_sign_texture_imports(export_dir: Path) -> int:
    """Pin each sign map a pack's manifest names (0.166.0) as an editor leaves it,
    whatever the pack asks (0.190.0, `SURFACE_TEX_PINS`).

    Measured before this, on `LF_gas_block_001`'s package: a sign map
    imported `compress/mode=0` and `mipmaps/generate=false`, whatever the pack
    was. Each `signs/*.pack.json` names its maps; a map's sidecar takes the
    keys `_sign_pins` gives and no others, and a sidecar missing a key is not
    given one -- `_pin_shared_texture_imports`'s rule. A manifest that cannot
    be read pins nothing. Returns how many sidecars changed."""
    import json as _json
    changed = 0
    for man in sorted(p for p in export_dir.rglob("*.pack.json") if p.parent.name == SIGNS_DIR):
        try:
            doc = _json.loads(man.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        pins = dict(SURFACE_TEX_PINS)   # whatever its import_hints ask (0.190.0)
        for fname in (doc.get("maps") or {}).values():
            sidecar = man.parent / (str(fname) + ".import")
            if not sidecar.is_file():
                continue
            lines = sidecar.read_text(encoding="utf-8").splitlines()
            out, hit = [], False
            for ln in lines:
                key = ln.split("=", 1)[0]
                want = pins.get(key)
                if want is not None and ln != f"{key}={want}":
                    out.append(f"{key}={want}")
                    hit = True
                else:
                    out.append(ln)
            if hit:
                sidecar.write_text("\n".join(out) + "\n", encoding="utf-8")
                changed += 1
    return changed


#: Where a model waits while an import pass runs without it (0.189.0): an
#: extension Godot does not import, beside the model it holds.
HELD_SUFFIX = ".held"
#: The worldskin's bases (`zoo_worldskin.gd`'s `BASE_PREFIX`): a base skins
#: its slabs, stairs and ladders from sibling modules it `load()`s, so it is
#: imported after every other model (0.189.0).
WORLDSKIN_BASE_PREFIX = "site_base"
#: `meshes/light_baking` Static: what a model whose own second UV set is
#: shader data has always shipped with, written for it now that the models'
#: defaults are Static Lightmaps when the export bakes (0.189.0).
MODEL_STATIC = 1
_SCENE_SIDECAR_HEAD = ('[remap]\n\nimporter="scene"\nimporter_version=1\n'
                       'type="PackedScene"\n\n')


def _model_import_defaults(text: str, lightmaps: bool) -> str:
    """`project.godot`'s text with the models' final settings as its
    `[importer_defaults] scene` (0.189.0): images embedded uncompressed, and
    Static Lightmaps when the export bakes. Merged into the block the
    worldskin's declaration starts, or a new one."""
    from packages.exporting.light_bake import STATIC_LIGHTMAPS
    keys = {"gltf/embedded_image_handling": 3}
    if lightmaps:
        keys["meshes/light_baking"] = STATIC_LIGHTMAPS
    lines = ",\n".join('"%s": %s' % (k, v) for k, v in keys.items())
    section, head = "[importer_defaults]\n", "scene={\n"
    if section in text and head in text[text.index(section):]:
        i = text.index(head, text.index(section)) + len(head)
        j = text.index("}", i)
        body = text[i:j].rstrip("\n")
        return (text[:i] + (body + ",\n" if body.strip() else "") + lines + "\n"
                + text[j:])
    if section in text:
        k = text.index(section) + len(section)
        return text[:k] + "\n" + head + lines + "\n}\n" + text[k:]
    return text.rstrip("\n") + "\n\n" + section + "\n" + head + lines + "\n}\n"


def _own_light_baking_sidecars(models, late, own) -> int:
    """Write the light baking of every model whose light baking is its own
    (0.189.0). One held to the last pass gets a WHOLE sidecar -- every
    `[params]` line of a model the second pass imported, its light baking
    set -- because a sidecar written by hand is not a new import: the
    project's defaults reach only a file with no sidecar, and a key the
    sidecar lacks takes the value an import from before the key existed would
    have had (`gltf/texture_map_mode=0`, measured, where every new import
    reads 1). One the second pass imported, there being no other model to
    copy, has its own sidecar's line set and is imported again. Returns how
    many it wrote."""
    donor = next((p for p in models if p not in late and p not in own), None)
    params = None
    if donor is not None:
        text = Path(str(donor) + ".import").read_text(encoding="utf-8")
        if "[params]" in text and "meshes/light_baking=" in text:
            params = text[text.index("[params]"):]
    written = 0
    for p, value in own.items():
        side = Path(str(p) + ".import")
        line = "meshes/light_baking=%d" % value
        if p in late:
            if params is None:
                raise ExportImportError(
                    "no imported model's sidecar to copy for %s, whose light "
                    "baking is its own" % p.name)
            text = _SCENE_SIDECAR_HEAD + re.sub(
                r"^meshes/light_baking=\d+$", line, params, flags=re.M)
        elif side.is_file():
            text = re.sub(r"^meshes/light_baking=\d+$", line,
                          side.read_text(encoding="utf-8"), flags=re.M)
        else:
            continue
        side.write_text(text, encoding="utf-8", newline="\n")
        written += 1
    return written


def _write_import_sidecars(export_dir: Path, godot_executable, *,
                           bake_spawned=None) -> int:
    """Run one import pass and keep the `.import` sidecars, not the cache.

    ROADMAP 25, the half it never covered. Godot cannot load a `.glb` as a
    PackedScene until it has imported it, and this package ships neither
    sidecars nor a cache -- so a recipient who runs the project before opening
    the editor gets `No loader found for resource` on every mesh and an empty
    level. Measured on `LF_precinct_yard_001.portable-godot`: 111 GLBs, 0
    sidecars, and the first walk of it produced exactly that.

    The portability check has ALWAYS known: it runs `--import` on its clean
    copy first, saying so in its own comment -- "the bundled GLB needs import
    artifacts and localized scripts need the global class cache before
    anything can load". So the export certified `portability PASS` on a state
    it produced for itself and did not ship.

    SIDECARS, NOT THE CACHE. `.godot/` stays excluded for the reason already
    written twenty lines above -- machine-specific and large; measured at 13 MB
    against 1.4 MB of sidecars on a 19 MB package. What the sidecar buys is not
    speed but SETTINGS: it pins the import parameters this level was built and
    photographed under, so the recipient does not silently import with engine
    defaults. That is not hypothetical -- roadmap 89 is a mipmap setting
    changing the look of a shipped build.

    Safe to re-import: the shipped scenes carry ZERO `uid://` references (118
    of 118 are `path="res://..."`), so regenerated ids bind to nothing.

    TWO PASSES, AND THE SECOND ONE IS THE POINT. Godot's default GLTF setting
    is `gltf/embedded_image_handling=1` -- EXTRACT -- which writes every
    embedded texture out as a loose .png beside the GLB, so the package carries
    each one twice. Measured on this package, all three modes, clean copies:

        variant                     ship MB   PNGs   sidecars
        no import (as shipped)         19.3      0          0
        embedded_image_handling=1      29.2    244        361   (+63%)
        embedded_image_handling=3      19.5      0        117   (+1%)
        embedded_image_handling=2      19.5      0        117   (+1%)

    So pass one produces the sidecars, this rewrites them to mode 3 (Embed as
    Uncompressed), drops what extract wrote, and pass two re-imports. Mode 3
    over mode 2 (Basis Universal) because the ship size is identical and
    uncompressed keeps the texture exactly as Pixelcoat authored it -- roadmap
    89 is a compression setting silently changing a shipped build's look.

    The cost of NOT doing this, measured on the same package: 1141 load errors.

    AND THE SHARED TEXTURES BESIDE THE GLBs (`_tex/`, Zoo 1.2.0). The reasoning
    above is about images that are still INSIDE the GLB. Zoo now writes a
    module's images to files beside it, named by a hash of their pixels, so
    sixty modules that use one pack texture reference one file -- and Godot
    imports that file once, where it imported sixty copies of the embedded
    form. Measured on cold run 9066's package, Godot 4.7, GL Compatibility,
    counted by distinct texture RID in the loaded tree:

        embedded, as shipped      1,841 textures   332,867,236 B texture mem
        shared beside the GLBs      157 textures    47,090,266 B

    Three keys are pinned on those `.png.import` sidecars, and each one is
    here for a measured reason, all three on the same 512x512 source compared
    against the embedded mode-3 decode:

        compress/mode=0            Lossless. Mode 2 is the default and is VRAM
                                   compression -- 100% of pixels differ. Same
                                   call as mode 3 above: roadmap 89.
        process/fix_alpha_border=false
                                   The default is true and rewrites RGB under
                                   transparent texels -- 7.755% of pixels
                                   differ, max channel delta 255. With it off
                                   the decode is byte-identical to the
                                   embedded one: 0.000%, max delta 0.
        mipmaps/generate=true      The chain a shipped package had been getting
                                   only from `zoo_worldskin.gd`'s import-time
                                   pass, which rebuilds each texture as its own
                                   ImageTexture and would undo the sharing this
                                   is for. With the chain already present that
                                   pass is a no-op and the textures stay shared.
                                   Free here: a 512x512 RGBA8 texture reads
                                   1,398,100 B of texture memory with mipmaps
                                   and 1,398,100 B without, measured on a
                                   twenty-GLB control against an empty-scene
                                   baseline -- the renderer allocates the chain
                                   either way.

    AND ONE EXCEPTION TO THE FIRST PIN (0.128.0): a shared texture that every
    sampler reaching it FILTERS is pinned to `compress/mode=2`. Zoo 1.46.0
    paints its machines' atlases at three times the density and samples them
    Linear; the lossless pin's reason is pixels shown at their own size, and a
    filtered texture's are not. Measured in a scratch project on Zoo 1.46.0's
    ATM, video poker and cash register together, Godot 4.7, GL Compatibility,
    the renderer's texture-memory figure with the three loaded less the
    figure before them:

        compress/mode=0, mip chain     7,304,813 B
        compress/mode=2, mip chain     1,374,528 B

    Mean difference between the two in a frame, 8-bit codes: 5.6 at arm's
    length on the ATM's head, 2.6 at nine metres. NOT MEASURED: any target
    other than desktop -- mode 2 imports S3TC here, and a platform without it
    needs its own import flag before this pin means anything there.

    BOTH SUPERSEDED (0.190.0, the walker's call of 2026-10-12): every shared
    texture is pinned VRAM compressed, Godot's 3D detection off. The lossless
    pin held only in a headless import -- every editor that opened the
    package re-encoded the textures it saw in use as VRAM compressed -- so
    what anyone looked at in an editor was compressed all along, and the
    package's textures depended on whether it had been opened.
    `SHARED_TEX_PINS` says how it was found.

    Best-effort only where Godot is missing: that is a setup problem, not an
    export failure, and HANDOFF.md tells the recipient what to do either way.

    NOT BEST-EFFORT WHERE GODOT IS THERE (0.163.1), and cold run 9214 is why.
    Its first pass left sidecars on 140 of the package's 975 importable files
    -- SkyMint's, which arrive with Lux's runtime -- and on none of its 425
    models. This threw the pass's exit code and output away and returned;
    `ensure_imported` took the `.godot` folder for an import; the occluder
    bake loaded a scene whose every module was missing and reported `ok`
    with 0 modules; and the Empties' merge was the first step to refuse. The
    same package imported 425 of 425 in seven fresh reruns, two of them from
    the export's exact starting state, so the pass is a transient and the
    cure is to look: every pass is checked by `occluders.unimported_models`
    and repeated up to `IMPORT_PASSES` times, every pass's exit code and
    output go to `<package>.import.log` beside the package -- not in it,
    where the resource manifest would have to account for it -- and a pass
    that never completes raises `ExportImportError`.

    THREE PASSES OVER THREE SETS, EVERY MODEL IMPORTED ONCE (0.189.0). What
    the two passes above did by rewriting sidecars and importing again, a
    model's first import now does with its final settings: the textures go
    first (a model imported before them embeds a copy of each), the worldskin
    bases last (they `load()` a sibling module), and a model whose light
    baking is its own goes last from a whole sidecar. The comment at the
    passes says what each of those cost when it was got wrong. Mode 3 and
    the shared textures' pins above still say why those settings are these.
    """
    if not godot_executable:
        return 0
    import shutil as _shutil
    import subprocess as _subprocess

    from packages.exporting.occluders import (package_models,
                                              unimported_models)
    log_path = export_dir.parent / (export_dir.name + ".import.log")
    log_path.unlink(missing_ok=True)  # this export's passes, not the last one's
    passes: list = []

    def _import_pass() -> None:
        """One `--import`, its exit code and output appended to the log."""
        try:
            done = _subprocess.run(
                [str(godot_executable), "--headless", "--path",
                 str(export_dir), "--import"],
                capture_output=True, timeout=1200)
            code = getattr(done, "returncode", None)
            out = ((getattr(done, "stdout", None) or b"")
                   + (getattr(done, "stderr", None) or b""))
        except (OSError, _subprocess.SubprocessError) as exc:
            code, out = None, ("did not run: %s\n" % exc).encode("utf-8", "replace")
        passes.append(code)
        with open(log_path, "ab") as fh:
            fh.write(("==== import pass %d: exit %s\n" % (len(passes), code))
                     .encode("utf-8"))
            fh.write(out if isinstance(out, bytes)
                     else str(out).encode("utf-8", "replace"))

    def _import_pass_verified() -> None:
        """Import until every model is, at most `IMPORT_PASSES` times."""
        for n in range(1, IMPORT_PASSES + 1):
            _import_pass()
            left = unimported_models(export_dir)
            if not left:
                if n > 1:
                    print("[export] import: every model imported on attempt %d "
                          "(%s)" % (n, log_path))
                return
            print("[export] import pass %d left %d model(s) unimported, first "
                  "%s" % (len(passes), len(left), left[0]))
        raise ExportImportError(
            "the import pass left %d of %d model(s) unimported after %d "
            "attempt(s) and this build had a Godot to run it with; first: "
            "%s\n  Godot's output: %s"
            % (len(left), len(package_models(export_dir)), IMPORT_PASSES,
               left[0], log_path))

    # THREE PASSES OVER THREE SETS, EVERY MODEL IMPORTED ONCE (0.189.0).
    # The step imported the package twice: a first pass with Godot's
    # defaults, then -- embedded images, the pins and the bake's marks
    # (0.187.0) written into the sidecars, what extract wrote deleted, the
    # cache wiped -- every file again: 86 s of a 238 s re-export of cold run
    # 9254. With its final settings asked for up front, a model's first
    # import is its only one, and a first import has hazards, each measured
    # by re-exporting 9254 against itself and digesting every model as Godot
    # loads it (the factory's docs/findings/grader_speed/sidecar_once_probe.py
    # and import_digest.gd):
    #
    #   * a model imported before the shared textures it names embeds a copy
    #     of each instead of naming the file -- 1,463 surfaces in 461 models,
    #     and every gate passed -- so the textures go first, every model held;
    #   * a worldskin base skins its slabs from a sibling module it `load()`s
    #     (`WORLDSKIN_BASE_PREFIX`), which a first import cannot promise is
    #     there -- 105 slab meshes greybox -- so the bases go last;
    #   * a model imported twice, its textures already imported, is the race
    #     0.182.0 backstops -- re-importing six models to set their light
    #     baking back reset two textures' pins and embedded a copy in three --
    #     so a model whose light baking is its own is held with the bases and
    #     imported once, from a whole sidecar (`_own_light_baking_sidecars`);
    #   * the filtered-texture set is read off the models' glTF, and read
    #     while they were held it was empty: 26 textures went lossless until
    #     the read-back after the last import. It is read before -- and
    #     since 0.190.0 the set read so is the normal maps.
    #
    # Measured against the export as it was: the sidecar step 86.1 -> 62.2 s,
    # the export 238.1 -> 214.8 s; every model loading the same (501 of 501),
    # every gate the same, no pin lost, and the two packages differing only
    # where two exports of the same code always do.
    from packages.exporting.light_bake import DYNAMIC, glb_has_uv2, mark_imports
    lightmaps = bake_spawned is not None
    models = [p for p in sorted(export_dir.rglob("*.glb")) if ".godot" not in p.parts]
    own = {}
    if lightmaps:
        spawned = set(bake_spawned)
        for p in models:
            if p.relative_to(export_dir).as_posix() in spawned:
                own[p] = DYNAMIC
            elif glb_has_uv2(p):
                own[p] = MODEL_STATIC
    late = {p for p in models if p.name.startswith(WORLDSKIN_BASE_PREFIX)}
    if any(p not in late and p not in own for p in models):
        late |= set(own)   # a model the second pass imports, to copy a whole sidecar from
    normals = _normal_map_shared_textures(export_dir)   # off the models, while they are here
    proj = export_dir / "project.godot"
    kept_project = proj.read_bytes() if proj.is_file() else None
    held = {}
    try:
        project_text = (kept_project or b"").decode("utf-8")
        p_eol = "\r\n" if "\r\n" in project_text else "\n"
        proj.write_bytes(_model_import_defaults(
            project_text.replace("\r\n", "\n"), lightmaps
        ).replace("\n", p_eol).encode("utf-8"))
        for p in models:
            q = p.with_name(p.name + HELD_SUFFIX)
            p.rename(q)
            held[p] = q
        _import_pass_verified()      # 1: the textures, and everything not a model
        _pin_shared_texture_imports(export_dir, normals)
        _pin_sign_texture_imports(export_dir)
        _pin_skin_texture_imports(export_dir)
        for p in models:
            if p not in late:
                held.pop(p).rename(p)
        _import_pass_verified()      # 2: every model but the late ones
        for p in models:
            if p in held:
                held.pop(p).rename(p)
        _own_light_baking_sidecars(models, late, own)
        if lightmaps:
            # the paint's meshes: every model already carries its light baking
            mark_imports(export_dir, bake_spawned)
        _import_pass_verified()      # 3: the bases, and the models with a light baking of their own
    finally:
        for p, q in held.items():
            if q.exists():
                q.rename(p)
        if kept_project is None:
            proj.unlink(missing_ok=True)
        else:
            proj.write_bytes(kept_project)

    # THE CACHE IS LEFT IN PLACE, and this is the fix for cold run 9065.
    # It used to be removed here -- one line before the occluder bake, which
    # is the only step in the export that has to `load()` a scene and
    # therefore the only one that needs it. The bake failed with `cannot load
    # res://site.tscn` on every real export, the export printed a warning and
    # exited 0, and the package shipped `use_occlusion_culling=true` with zero
    # occluders in it.
    #
    # `occluders.drop_cache` removes it after that step and before
    # `build_resource_manifest` walks the tree, so the shipped package is
    # cache-free exactly as before. Nothing here got slower: the import pass
    # this function already ran is the one the bake now uses.
    return len(list(export_dir.rglob("*.import")))


#: Installed into the composed package by `run_presentation_compose.py`, which
#: is where the reasoning for it lives. Named here so the export can declare
#: it; one constant, so the two cannot drift apart silently.
_WORLDSKIN = "zoo_worldskin.gd"


def _worldskin_in_package(export_dir: Path) -> Path | None:
    """Where the package actually carries `zoo_worldskin.gd`, relative to
    its root, or None.

    THE ROOT WAS THE WRONG PLACE TO LOOK, and every package since 0.5x has
    paid for it. `run_presentation_compose` installs the script at the root
    of the COMPOSED package, and the export copies that package in as
    `lot/shell/` -- so the script ships at `lot/shell/zoo_worldskin.gd`,
    the old `export_dir / _WORLDSKIN` test found nothing, no
    `[importer_defaults]` was written, and `_write_import_sidecars` baked
    an empty `import_script/path` into every kit sidecar. Measured on cold
    run 9005's `LF_county_hospital_001.portable-godot` (2026-09-11, roadmap
    141): the script at `lot/shell/`, 0 of 48 kit sidecars bound,
    `tools/texel_density.gd` reporting a 66.0x world-density mismatch on
    the concrete skin (0.152 to 10.0 texels/m over 278 surfaces) -- the
    texel-scale jumps at remainders and doorways a person walked that
    morning. The same package with the script declared where it sits and
    the sidecars regenerated: 1.0x on all four skins, world-triplanar.

    Root first, so a package that does put it there keeps its declaration;
    then the first copy anywhere below. One script, one declaration.
    """
    if (export_dir / _WORLDSKIN).is_file():
        return Path(_WORLDSKIN)
    hits = sorted(p for p in export_dir.rglob(_WORLDSKIN)
                  if p.is_file() and ".godot" not in p.parts)
    if not hits:
        return None
    return hits[0].relative_to(export_dir)


def _importer_defaults_block(export_dir: Path) -> str:
    """Declare the kit's post-import script, if the package actually ships it.

    `zoo_worldskin.gd` scopes itself by asset name (`wall_`, `wallEnd_`,
    `window_`, `doorway_`, `breach_`) and leaves everything else alone, so
    declaring it project-wide is safe: props and dressing import unchanged.
    Declared at the path the package carries it (`_worldskin_in_package`).
    """
    rel = _worldskin_in_package(export_dir)
    if rel is None:
        return ""
    return ("[importer_defaults]\n\n"
            "scene={\n"
            f'"import_script/path": "res://{rel.as_posix()}"\n'
            "}\n\n")


def _write_project_godot(export_dir: Path, entry_scene: str, mission_id: str,
                         godot_version: str, weather: str = "clear") -> None:
    """A minimal, autoload-free, plugin-free project so the shell is portable.

    `config/features` IS the version declaration, and omitting it is not
    cosmetic: without it Godot treats the folder as an unversioned project and
    drops to the PROJECT MANAGER instead of opening the level -- the same
    failure `presentation_compose` already patches around, and the plainest
    possible violation of the standalone contract for a package whose whole
    job is to open in somebody else's editor.

    Measured on four shipped exports before this landed: 0 of 4 declared it,
    while every one of their manifests recorded `godot_version: 4.7`. The
    package asserted a version it did not tell the engine.

    `[importer_defaults]` IS WHAT MAKES WORLD-SPACE UVs SHIP, and leaving it
    out is why they never did. `presentation_compose` installs
    `zoo_worldskin.gd` and declares it in ITS project.godot, but the export
    writes this file from scratch and dropped the declaration -- so the
    package carried the script and ran it on nothing. Measured on
    `LF_precinct_yard_001.portable-godot`: the script present, no
    `[importer_defaults]`, and an empty `import_script/path` on all 111 GLB
    sidecars, because `_write_import_sidecars` runs after this and bakes the
    engine default into every one. Every recipient got box-projected UVs --
    roadmap 88's defect, shipped, with its own fix sitting unused beside it.

    Declared ONLY when the script is actually in the package. Naming a script
    that is not there fails every scene import, which is a worse package than
    one with the old look.
    """
    (export_dir / "project.godot").write_text(
        "; Portable Level Factory mission shell (autoload-free, no editor plugins)\n"
        "config_version=5\n\n"
        "[application]\n"
        f'config/name="{mission_id} (shell)"\n'
        f'config/features=PackedStringArray("{godot_version}")\n'
        f'run/main_scene="res://{entry_scene}"\n\n'
        # The culler goes out OFF here and is settled by the occluder step
        # once the bake has answered -- see `set_occlusion_culling`. A build
        # that dies between the two then ships no flag and no occluders,
        # which is a consistent package; the other ordering ships 9065's.
        # the reflection atlas from the probes in this folder (0.198.0)
        + rendering_block(package_light_budget(export_dir), 0,
                          count_package_probes(export_dir))
        # the wind (0.130.0): one global the sway shaders read
        + shader_globals_block(weather)
        + _importer_defaults_block(export_dir) +
        "[debug]\n"
        "; Localized tool scripts are strict-clean under their home projects'\n"
        "; warning config; engine DEFAULTS escalate inference-on-Variant to a\n"
        "; load-killing error (proven on hardware: lux_root.gd:218 took two\n"
        "; dependents down as compile knock-ons). Warn, don't refuse to load.\n"
        "gdscript/warnings/inference_on_variant=1\n",
        encoding="utf-8",
    )


#: Dispatch's handoff files that address anchors by NODE PATH into the
#: `mission.tscn` tree the export replaces (roadmap 101). Listed by name, not
#: by pattern, because a pattern that matched a file LF itself writes would
#: strip bindings that are true.
_DISPATCH_NODE_PATH_FILES = ("gameplay_anchors.json",
                             "runtime_ownership_requirements.json")

_TSCN_NODE_NAME = re.compile(r'\[node name="([^"]+)"')

#: The only files allowed to land after the closure verdict, by relative path
#: inside the package. Every one of them describes the BUILD rather than being
#: content the judge could sensibly scan. Anything else appearing after the
#: judge is the defect this list exists to catch.
#:
#: THIS LIST SAYS NOTHING ABOUT THE RESOURCE MANIFEST, and until 0.104.0 its
#: own comment quietly implied it did. That comment read "Every one of them
#: DESCRIBES the package ... so it cannot be inside what it describes", which
#: is true of the closure verdict and of `LF_MANIFEST.json` and is NOT true of
#: `LICENSES.json`, `export_profile.json` or `output_layers.json` -- they were
#: below the manifest walk by accident, shipped unlisted for it, and this
#: sentence made the accident read as a decision. Four unlisted files on cold
#: 9067, 562 against 567. Being after the VERDICT and being outside the
#: MANIFEST are two different facts about a file, and the three above are now
#: the first without being the second.
#:
#: What a file cannot be inside the manifest is decided by
#: `_UNLISTED_BY_CONSTRUCTION`, which is a subset of this set and says why for
#: each member.
#:
#: Relative paths, not basenames. `_copy_tree`'s `skip` is a basename match
#: and it once excluded five `lot/<archetype>/site.tscn` along with the one
#: root `site.tscn` it was aimed at, exporting every building unresolved.
_WRITTEN_AFTER_VERDICT = frozenset({
    "export_closure_scan.json",
    "portable_resource_manifest.json",
    "LICENSES.json",
    "export_profile.json",
    "output_layers.json",
    EXPORT_MANIFEST_NAME,
})


def _closure_verdict(export_dir: Path):
    """The resource-closure VERDICT. Writes `export_closure_scan.json`.

    `localize_export` at step 3.5 is the FIXER; `closure.scan_closure` is the
    JUDGE, and localize.py's own docstring says exactly that. The fixer's
    `unresolved` list fills only when a repair was ATTEMPTED and failed -- an
    absolute ref whose source is gone, an addon copy that raised. A scene
    referencing res://art/zoo/wall.glb that was simply never copied in is not
    something the fixer tries to repair, so it leaves no trace there at all.

    The judge was once reachable only from `run_portability_test`, a separate
    command, off the path that produces the deliverable. Measured 2026-08-01
    on category5_baie_dore_001 --mode portable-godot: export_closure.json
    reported "unresolved": [] while 211 of the presentation scene's 243 nodes
    instanced ten .glb files the package did not contain. The shell opened,
    lit itself correctly from its pinned preset, and rendered nothing but sky.

    The two files are deliberately named apart. export_closure.json is the
    fixer's log; export_closure_scan.json is the verdict. One name answering
    two questions is how the empty export read as clean.

    IT RUNS LAST, and that is the 0.103.0 change. From 0.98.0 it ran at step
    3.6, in the middle of the build, and certified a package that did not
    exist yet. Measured 2026-09-22 on cold 9066's and 9067's shipped
    `LF_club_block_00{5,6}.portable-godot`, which are the packages that went
    out:

        the verdict IN the package : ok=true,  0 issues, resource_count 46
        the same scan, run after   : ok=false, 1 issue,  resource_count 48

    274 files landed between the old position and this one on 9067, and 243
    of them carry a suffix this scan reads: 229 `.import` sidecars, 10
    `.json`, `occluders.tscn`, a rewritten `mission.tscn`, `warmup.gd`, and
    `project.godot`. `occluders.tscn` and `warmup.gd` are the two the count
    was short by; the rewritten `mission.tscn` means the entry scene the
    verdict read was not the entry scene that shipped; and `project.godot`
    did not exist AT ALL when the judge looked, which made
    `required_autoload_count` and `required_plugin_count` structurally
    incapable of being anything but zero on this path for five versions. A
    check that cannot fail is indistinguishable from one that passed.

    THE COST OF MOVING IT, said out loud rather than discovered: a package
    with broken closure now pays for the occluder bake and the warm-up before
    it is told. That is minutes on a build that is going to be thrown away.
    The alternative -- a cheap early scan plus a real one at the end -- is two
    instruments answering one question, and this repo has the scar: the empty
    export read as clean because the fixer's log and the judge's verdict were
    one file. One judge, at the end, where the package is what ships.
    """
    from packages.exporting.closure import scan_closure
    scan = scan_closure(export_dir)
    verdict = scan.as_dict()
    # WHAT THE FINGERPRINT DOES NOT COVER, named in the verdict itself, so a
    # reader with the folder can re-derive it (`closure.fingerprint_package`)
    # instead of having to know this module's ordering.
    verdict["written_after_verdict"] = sorted(_WRITTEN_AFTER_VERDICT)
    (export_dir / "export_closure_scan.json").write_text(
        pretty_dumps(verdict), encoding="utf-8")
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
    return scan


def _guard_verdict_is_about_the_package(export_dir: Path, scan) -> None:
    """The backstop, read back off the files that are about to be zipped.

    Same shape as the occluder and warm-up audits, and for the same reason:
    moving the scan fixes the packages shipped today, and only a check keeps
    the next writer added to `export_mission` from reopening the hole. A
    comment asking the next author to put their step above this line is not a
    check.

    RAISES rather than warns. `occluders.py` records what a warning nobody
    reads is worth: 0.98.0 shipped a package with the culling flag on and
    nothing to cull, behind one.
    """
    from packages.exporting.closure import (_METADATA_FILES,
                                            verify_verdict_describes_package)
    # The two lists cannot drift: a file allowed to land after the verdict
    # must also be one the verdict would decline to scan, or the next scan of
    # the shipped folder -- `run_portability_test` runs exactly that -- would
    # judge it and the two judges would disagree about the same package.
    unscanned = {n for n in _WRITTEN_AFTER_VERDICT if n not in _METADATA_FILES}
    if unscanned:
        raise ExportClosureError(
            "these are allowed to land after the closure verdict but are not "
            "closure metadata, so a later scan of the shipped package would "
            "judge them: " + ", ".join(sorted(unscanned)))
    drift = verify_verdict_describes_package(
        export_dir, scan, written_after=_WRITTEN_AFTER_VERDICT)
    if drift:
        raise ExportClosureError(
            "EXPORT_CLOSURE_VERDICT_IS_STALE: %d file(s) changed after "
            "export_closure_scan.json was written, so the verdict in this "
            "package does not describe this package.\n  %s\n  Either move "
            "the step that writes them above the verdict, or -- if the file "
            "describes the package and so cannot be inside it -- add it to "
            "_WRITTEN_AFTER_VERDICT and to closure._METADATA_FILES."
            % (len(drift), "\n  ".join(drift[:20])
               + ("" if len(drift) <= 20
                  else "\n  ... and %d more" % (len(drift) - 20))))


def _guard_manifest_accounts_for_the_package(export_dir: Path) -> None:
    """Every file in the package is listed in the manifest or declared unlisted.

    Same shape as `_guard_verdict_is_about_the_package`, and there for the
    same reason: what makes the manifest's numbers true is the ORDER of the
    writers in `export_mission`, and a comment asking the next author to put
    their writer above the walk is not a check. Cold run 9067 shipped 562
    listed against 567 on disk because three writers sat four lines too low.

    READ BACK OFF DISK, not off the dict `build_resource_manifest` returned.
    The two differ by exactly the files written between the walk and now,
    which is the entire subject -- so checking the dict would be a check
    written against what the code believes it wrote.

    RAISES rather than warns, on the standing reasoning in `occluders.py`: a
    package whose manifest does not describe it is one an integrator cannot
    verify, and a warning nobody reads is how that ships.
    """
    path = export_dir / "portable_resource_manifest.json"
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ExportManifestError(
            "the package's resource manifest could not be read back: %s (%s)"
            % (path, exc)) from exc

    # AN UNRECOGNISED SHAPE FAILS. `or []` here would turn a renamed key into
    # an empty problem list and print a clean verdict -- which is precisely
    # how a `--verify` once reported "closure verdict clean" three lines
    # under the exporter shouting EXPORT_CLOSURE_BROKEN.
    missing_keys = [k for k in ("resources", "unlisted", "accounting")
                    if k not in manifest]
    if missing_keys:
        raise ExportManifestError(
            "portable_resource_manifest.json is missing %s, so its own "
            "accounting cannot be checked. Schema on disk: %r; this build "
            "writes level_factory.portable_manifest.v0.2."
            % (", ".join("`%s`" % k for k in missing_keys),
               manifest.get("schema")))

    listed = {r["path"] for r in manifest["resources"]}
    declared = {u["path"] for u in manifest["unlisted"]}
    on_disk = {p.relative_to(export_dir).as_posix()
               for p in export_dir.rglob("*") if p.is_file()}

    problems: list[str] = []
    # The two lists cannot drift, the same way `_WRITTEN_AFTER_VERDICT` and
    # `closure._METADATA_FILES` cannot: a file this manifest declines to list
    # is by definition one written after the walk, and the walk is after the
    # verdict, so it must already be allowed to land there.
    for name in sorted(declared - _WRITTEN_AFTER_VERDICT):
        problems.append(
            "%s: declared unlisted but is not in _WRITTEN_AFTER_VERDICT, so "
            "nothing says it is allowed to land after the walk at all" % name)
    for name in sorted(listed & declared):
        problems.append("%s: both listed and declared unlisted" % name)
    for name in sorted(on_disk - listed - declared):
        problems.append(
            "%s: ships in the package, neither listed nor declared" % name)
    for name in sorted((listed | declared) - on_disk):
        problems.append("%s: named by the manifest, not in the package" % name)

    # The manifest's OWN arithmetic, asked of the same values once. A count
    # that disagrees with the list beside it is worse than no count.
    acc = manifest["accounting"]
    for key, want in (("listed", len(listed)),
                      ("declared_unlisted", len(declared)),
                      ("files_in_package", len(on_disk))):
        if acc.get(key) != want:
            problems.append(
                "accounting.%s says %r; the package says %d"
                % (key, acc.get(key), want))

    if problems:
        raise ExportManifestError(
            "PORTABLE_MANIFEST_DOES_NOT_ACCOUNT_FOR_THE_PACKAGE: %d listed + "
            "%d declared unlisted against %d file(s) on disk.\n  %s\n  A file "
            "written after `build_resource_manifest` walks the tree must "
            "either move above that walk, or be named in "
            "_UNLISTED_BY_CONSTRUCTION with the reason it cannot be listed."
            % (len(listed), len(declared), len(on_disk),
               "\n  ".join(problems[:20])
               + ("" if len(problems) <= 20
                  else "\n  ... and %d more" % (len(problems) - 20))))


#: The package's account of how responders arrive (0.157.0, roadmap 212).
RESPONDER_ARRIVALS_NAME = "responder_arrivals.json"


def _package_xz(x, y) -> list:
    """A site plan point in the package's frame: x, then z = -(site y).
    `+ 0.0` so a point on the axis writes 0.0, not -0.0."""
    return [x + 0.0, -y + 0.0]


def responder_vehicle_scenes(themed_site_dir) -> list:
    """The package-relative paths of the cars the themed site names in
    `responders.json` (Lot 0.101.0): models the gameplay layer spawns, which
    the light bake sets dynamic rather than baking (0.162.1). Empty without
    one."""
    if not themed_site_dir:
        return []
    named = Path(themed_site_dir) / "responders.json"
    if not named.is_file():
        return []
    doc = json.loads(named.read_text(encoding="utf-8"))
    return sorted({v["scene"] for v in doc.get("vehicles") or []})


def write_responder_arrivals(export_dir: Path, lot_gameplay,
                             themed_site_dir: Path | None = None) -> dict | None:
    """How each responder arrives, in the package's frame -- or None, and no
    file, when Lot's gameplay carries no `responder_plan`.

    The walker, 2026-10-08: "have responders show up after the job, on the
    way back (and this would be on the gameplay layer, but we can make thee
    assets and ensure there is clearance and routes for their arrival)".
    Lot 0.99.0 plans each arrival and reserves its lane and its stop from
    everything it stands in the street. 0.156.0 put each stop in
    `gameplay_anchors.json` as an `ai_spawn` tagged `responder`. A Dispatch
    anchor holds a position and tags, so the rest is here, keyed by that
    anchor's id: the road end a vehicle appears at, the stop, which way it
    faces arriving, the lane and stop boxes nothing else stands in, and the
    point of the crew's way back the stop was chosen for.

    THE LANE IS BOXES (0.161.0, schema v2). Lot 0.100.0 steers a lane round
    what stands in it -- toward and across the centre line, tapered, back in
    its own half by the stop -- and writes it as `lane_boxes`, one box a run
    of slices at one shift, with `lane_shift` the largest. One box could not
    say that: drawn round a steered lane it covers the van the lane goes
    round. A lane from Lot 0.99 is its one `lane_box`, shipped as the only
    box, at shift 0.

    THE CAR EACH BRINGS (0.162.0, schema v3). Lot 0.101.0's themed assembly
    copies the cruiser Zoo's site kit built beside its scene -- into
    `cover/`, a sibling this package carries -- stands it nowhere, and names
    it in `responders.json`. Each arrival here gets `vehicle_scene`, the
    car's `res://` path, matched by its stop. It is null when the themed
    site names no car for that stop, or names a file the package does not
    hold, and `vehicle_findings` says which. This file is one of
    `closure._METADATA_FILES`, so the closure gate does not read the path:
    the file's presence is checked here. Lot from before 0.101.0 writes no
    `responders.json`, and every arrival's car is null with that said once.

    Frame: Godot -- x, y up, z = -(site y) -- metres, the frame of every
    position in `gameplay_anchors.json`; the ground at y 0. A box is the
    x/z extent of a plan rect. Lot's output from before 0.99.0 carries no
    `responder_plan`, and its package is exactly what it was."""
    import math
    if not lot_gameplay or not Path(lot_gameplay).is_file():
        return None
    gp = json.loads(Path(lot_gameplay).read_text(encoding="utf-8"))
    if "responder_plan" not in gp:
        return None
    from packages.staging.dispatch_inputs import site_marker_anchor_pairs

    def stop_key(p):
        return (round(float(p[0]), 3), round(float(p[1]), 3))

    cars, said = {}, []
    named = Path(themed_site_dir) / "responders.json" if themed_site_dir else None
    if named is not None and named.is_file():
        rv = json.loads(named.read_text(encoding="utf-8"))
        for v in rv.get("vehicles") or []:
            cars[stop_key(v["stop"])] = v["scene"]
        if rv.get("missing"):
            said.append("the themed site built no car for arrival(s) %s" % rv["missing"])
    else:
        said.append("the themed site names no responder car (no responders.json: "
                    "Lot before 0.101.0, or no themed site)")
    arrivals = []
    for marker, anchor in site_marker_anchor_pairs(gp, "lot"):
        a = marker.get("arrival")
        if marker.get("type") != "responder_spawn" or not isinstance(a, dict):
            continue
        (ex, ez), (sx, sz) = _package_xz(*a["entry"][:2]), _package_xz(*a["stop"][:2])
        dx, dz = sx - ex, sz - ez
        n = math.hypot(dx, dz) or 1.0
        tx, tz = _package_xz(*a["toward"][:2])
        def box(rect):
            x0, y0, x1, y1 = rect
            return {"min": _package_xz(x0, y1), "max": _package_xz(x1, y0)}

        lane = a["lane_boxes"] if "lane_boxes" in a else [a["lane_box"]]
        scene = cars.get(stop_key(a["stop"]))
        if scene is not None and not (export_dir / scene).is_file():
            said.append("%s is named for the stop at %s and is not in the package"
                        % (scene, list(a["stop"][:2])))
            scene = None
        elif scene is None and cars:
            said.append("the themed site names no car for the stop at %s" % list(a["stop"][:2]))
        arrivals.append({
            "anchor": anchor["id"],
            "entry": [ex, 0.0, ez], "stop": [sx, 0.0, sz],
            "forward": [dx / n, 0.0, dz / n],
            "vehicle_m": list(a.get("vehicle") or []),
            "stop_box": box(a["stop_box"]),
            "lane_boxes": [box(r) for r in lane],
            "lane_shift_m": a.get("lane_shift", 0.0),
            "vehicle_scene": ("res://" + scene) if scene else None,
            "toward": [tx, 0.0, tz],
            "to_way_back_m": a.get("to_way_back"), "run_m": a.get("run"),
        })
    doc = {"schema": "level_factory.responder_arrivals.v3",
           "frame": "Godot: x, y up, z = -(site y); metres; the ground at y 0",
           "what": ("Where responders can arrive. The factory reserves each "
                    "lane and stop; spawning and timing responders is the "
                    "runtime's. Each `anchor` is an `ai_spawn` tagged "
                    "`responder` in gameplay_anchors.json."),
           "arrivals": arrivals, "vehicle_findings": said}
    (export_dir / RESPONDER_ARRIVALS_NAME).write_text(pretty_dumps(doc), encoding="utf-8")
    return doc


def strip_dead_node_paths(export_dir: Path) -> dict:
    """Move every `node` field that names nothing in the package aside.

    Roadmap 101. The export overwrites Dispatch's `mission.tscn` with its own
    portable entry -- correctly; a package that needs an addon is not
    portable -- and Dispatch's `gameplay_anchors.json` and
    `runtime_ownership_requirements.json` go on addressing anchors into the
    tree that was replaced: `Functional/GameplayAnchors/Triggers/...`,
    `Presentation/...`. Measured on `LF_precinct_yard_001`: 17 such paths,
    and ZERO of the node names they use exist in any scene the package ships.
    These are the first files an integrating team opens, and every address in
    them is dead on arrival.

    The DATA survives -- every anchor still carries its position and its
    stable id, which is the pattern `interactives.json` uses and the reason it
    was unaffected. So the fix is the item's third shape, done reversibly: a
    `node` that resolves to nothing is renamed `node_dispatch`, the package
    stops asserting a binding it does not carry, and the original address is
    still there for the day LF's entry grows the tree that would make it true
    (the item's first shape). Nothing is deleted.

    Resolution is by NODE NAME anywhere in any shipped scene, not by full
    path, because a re-parent is exactly the failure being handled -- a path
    whose leaf exists somewhere is a binding a reader could recover; one whose
    leaf exists nowhere is not.

    Returns a summary and writes it beside the files as
    `handoff_bindings.json`, so the count is in the package rather than only
    in a log line.
    """
    names: set[str] = set()
    for tscn in export_dir.rglob("*.tscn"):
        try:
            names.update(_TSCN_NODE_NAME.findall(
                tscn.read_text(encoding="utf-8", errors="replace")))
        except OSError:
            continue

    def leaf(path: str) -> str:
        return path.rstrip("/").split("/")[-1]

    def walk(obj, moved: list) -> object:
        if isinstance(obj, dict):
            out = {}
            for k, v in obj.items():
                if k == "node" and isinstance(v, str) and v:
                    if leaf(v) in names or v in names:
                        out[k] = v
                    else:
                        out["node_dispatch"] = v
                        moved.append(v)
                else:
                    out[k] = walk(v, moved)
            return out
        if isinstance(obj, list):
            return [walk(x, moved) for x in obj]
        return obj

    summary: dict = {"schema": "level_factory.handoff_bindings.v1",
                     "reason": ("node paths that name nothing in the shipped "
                                "scenes are moved to node_dispatch; the anchor "
                                "keeps its position and id (roadmap 101)"),
                     "files": {}}
    total = 0
    for name in _DISPATCH_NODE_PATH_FILES:
        p = export_dir / name
        if not p.is_file():
            continue
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        moved: list = []
        rewritten = walk(data, moved)
        if moved:
            p.write_text(pretty_dumps(rewritten), encoding="utf-8")
        summary["files"][name] = {"moved": len(moved), "paths": moved}
        total += len(moved)
    summary["moved_total"] = total
    if summary["files"]:
        (export_dir / "handoff_bindings.json").write_text(
            pretty_dumps(summary), encoding="utf-8")
    return summary


#: The files a package ships that this manifest cannot list, each with the
#: reason it cannot. Both are written AFTER `build_resource_manifest` walks the
#: tree, so no walk could have seen them and no hash of them would be true.
#:
#: DECLARED RATHER THAN OMITTED, and that is the whole change. Measured
#: 2026-09-22 on cold run 9067's shipped `LF_club_block_006.portable-godot`:
#: 562 files listed against 567 on disk, with `LF_MANIFEST.json`,
#: `LICENSES.json`, `export_profile.json`, `output_layers.json` and this
#: manifest arriving unannounced. Only the last had a reason recorded
#: anywhere. Three of the five were an ordering accident -- their writers sat
#: below the walk in `export_mission` for no reason anybody had stated -- and
#: they are now above it and listed like any other shipped file. These two
#: are real, so they are named and counted instead of left silent. Four files
#: arriving unlisted read to an integrator as tampering or a truncated
#: download, and were neither.
#:
#: THE TWO REASONS ARE NOT THE SAME KIND and the text says so. The manifest
#: cannot contain its own hash under any ordering; `LF_MANIFEST.json` could be
#: listed if its writer moved above the walk, and is deliberately not. Calling
#: both "impossible" would be tidier and would be a claim this repo cannot
#: support.
#:
#: The point of naming them is the equation, which is falsifiable:
#:
#:     len(resources) + len(unlisted) == files in the package
#:
#: `_guard_manifest_accounts_for_the_package` reads it back off the finished
#: folder. An unlisted set nobody counts is the same silence with more words
#: in it.
_UNLISTED_BY_CONSTRUCTION: tuple[tuple[str, str], ...] = (
    ("portable_resource_manifest.json",
     "STRUCTURAL: this manifest. A file cannot carry the hash and size of "
     "its own finished bytes."),
    (EXPORT_MANIFEST_NAME,
     "DELIBERATE: written last, after this walk, so the package's resource "
     "manifest does not list a file that describes it (export.py, section "
     "5). It could be listed if that writer moved above the walk; it is not, "
     "and this row says so rather than leaving it unexplained."),
)


def build_resource_manifest(export_dir: Path) -> dict:
    files = sorted(p for p in export_dir.rglob("*") if p.is_file())
    resources = [
        {"path": p.relative_to(export_dir).as_posix(),
         "hash": hash_file(p), "size": p.stat().st_size}
        for p in files
    ]
    unlisted = [{"path": name, "reason": why}
                for name, why in _UNLISTED_BY_CONSTRUCTION]
    return {
        # v0.2, because the shape grew two keys. Nothing in this repo or any
        # sibling reads this string -- grepped 2026-09-22 across every repo in
        # the factory -- so the bump is a statement to a reader rather than a
        # switch anything flips on.
        "schema": "level_factory.portable_manifest.v0.2",
        "created_at": _now(),
        # THE CLAIM AN INTEGRATOR CHECKS, written as an equation rather than
        # left to be inferred from two list lengths. `files_in_package` is a
        # PREDICTION at the moment this runs -- the two unlisted files do not
        # exist yet -- which is exactly why a guard reads it back off the
        # finished folder before the package is zipped.
        "accounting": {
            "listed": len(resources),
            "declared_unlisted": len(unlisted),
            "files_in_package": len(resources) + len(unlisted),
            "check": "listed + declared_unlisted == files in the package",
        },
        "resources": resources,
        "unlisted": unlisted,
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
    #: Used for ONE import pass so the package ships `.import` sidecars
    #: (roadmap 25). Defaults to None so every existing caller -- including
    #: the unit suite, which has no Godot -- keeps working; the package is
    #: then exactly what it was before, and HANDOFF.md still says what to do.
    godot_executable: str | None = None,
    #: Layer 3 surface dressing (roadmap 110): Patina's
    #: `<site>.surface_dressing.json` and the Zoo clutter build's out dir.
    #: Both default to None so a mission that never planned the layer
    #: exports exactly as before; a mission that did ships
    #: `<site>_dressing.tscn` and `dressing/<asset>.res`.
    dressing_manifest: Path | None = None,
    clutter_dir: Path | None = None,
    #: The backdrop beyond the plate's edge (0.174.0, roadmap 228): the themed
    #: site's drawn spec, read for its `backdrop` list and the kit it names.
    #: None for a caller with nothing to pass, and then the package is exactly
    #: what it was.
    backdrop_spec: Path | None = None,
    #: Where responders arrive (0.157.0, roadmap 212): the selected Lot
    #: candidate's `site.site.gameplay.json`, read for its
    #: `responder_plan`. None for a caller with nothing to pass, and then
    #: the package is exactly what it was.
    lot_gameplay: Path | None = None,
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
    # A cache kept beside the last package was that package's import, not
    # this one's (0.188.0, `occluders.keep_cache`): it goes with it, so an
    # export that stops early leaves no walk copy a stranger's cache.
    from packages.exporting.occluders import kept_cache_dir
    shutil.rmtree(kept_cache_dir(export_dir), ignore_errors=True)
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
        #
        # AND ITS BASE GOES WITH IT -- `_COMPOSED_ROOT_PAIR`, not just the
        # scene. A varied lot refused the composer's root `site.tscn` here
        # and shipped the `site_base.glb` that scene alone names, so the
        # package carried a mesh nothing could reach. Measured on cold run
        # 9061's card_block_001: 371,260 bytes at the package root, 525
        # nodes, 279 meshes, 18 `stair0_*` flight meshes, named by no
        # `.tscn` in the package -- the three buildings name
        # `res://lot/<id>/site_base.glb` (388,568 / 187,884 / 150,668) --
        # and listed in `portable_resource_manifest.json`, so it ships AND
        # imports rather than merely sitting on disk. Cold run 9057's
        # LF_club_block_001 carries the same orphan at 400,444 bytes.
        #
        # WHAT WROTE IT, since the size says it is not the first building's:
        # `adapters/presentation.plan_commands` composes the mission's OWN
        # shell to `presentation/site.tscn` for every mission, varied or
        # not, to satisfy that job's output contract -- its own note by
        # `_LOT_SUBDIR` says a varied lot does not place it. On a varied lot
        # that compose gets no kit (`modules_dir` is keyed per archetype and
        # carries no "" entry), so it emits a scene with 63 dangling
        # `res://art/zoo/*` refs and `portable: false` beside this base. The
        # scene was already refused here. The base is its other half.
        #
        # NOT FREE, either: the base has no `art/` beside it, so 0.93.0's
        # `_skin_stairs` guard push_errors `[worldskin] res://site_base.glb;
        # NO art/zoo BESIDE THE BASE -- 18 flight mesh(es) left in the
        # greybox material` on every import of a package of this shape, and
        # `--import` still exits 0. An error about a file nobody loads is
        # how a real one stops being read.
        #
        # BOTH OTHER PATHS KEEP IT, and by construction rather than by a
        # second rule: `wanted` means the root scene ships as the entry, and
        # `building_rel` means the whole composed root moves under
        # `lot/<id>/` where the assembly names it. The base's fate is the
        # scene's fate in all three.
        # ONLY THE PACKAGES A SCENE STANDS (0.207.0, `_standing_lot_ids`): a
        # varied lot's composed root holds a `lot/<id>/` for every building
        # the brief was given, and the assembly names the ones this candidate
        # stands. A single-shell mission moves the root itself under
        # `lot/<id>/` and has no packages of its own to leave out.
        standing = None if building_rel else _standing_lot_ids(themed_site_dir)
        lot_root = Path(composed_root) / "lot"
        idle = (sorted({d.name for d in lot_root.iterdir() if d.is_dir()} - standing)
                if standing is not None and lot_root.is_dir() else [])
        if idle:
            print("[export] %d composed building(s) no scene stands, left out: %s"
                  % (len(idle), ", ".join(idle)))
        _copy_tree(composed_root, dest,
                   skip={"project.godot", "HANDOFF.md",
                         "portable_resource_manifest.json",
                         "compose.summary.json",
                         "site_main.tscn"},
                   skip_rel=(set() if (wanted or building_rel)
                             else set(_COMPOSED_ROOT_PAIR)),
                   skip_dirs={".godot", "addons"},
                   skip_lot=set(idle))

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
        # The ground's skins (roadmap 152): Lot 0.58.0 copies the Pixelcoat
        # maps to `skins/` beside its scene and references them as siblings,
        # the way the staged buildings are referenced -- `skins/<map>` from
        # the assembly, `res://skins/<map>` from Lux's applied scene, both
        # of which resolve to this one directory at the package root.
        # ... and the cover modules Lot 0.59.2 copies to `cover/` (roadmap
        # 22), and the shop signs Lot 0.69.0 copies to `signs/` (roadmap
        # 153), for the same reason and by the same rule. THE LIST IS THE
        # CONTRACT: cold run 9039 shipped a street whose every sign was
        # named by the scene and whose maps were in none of these, and the
        # closure gate refused the package with six unresolved references
        # -- which is the gate working, and the reason a new sibling
        # directory in Lot means a line here.
        for sib in ("skins", "cover", "signs"):
            src = Path(themed_site_dir) / sib
            if src.is_dir():
                shutil.copytree(str(src), str(export_dir / sib),
                                dirs_exist_ok=True)
        # ... and the road paint Lot 0.114.0 writes as one `site_marks_<colour>.obj`
        # a paint colour beside its scene (roadmap 231), named "from ./" by the
        # assembly and `res://site_marks_*.obj` by Lux's applied scene: sibling
        # FILES, which the directory list above cannot carry. Cold run 9235
        # shipped the scene without them -- 2 unresolved res://, 2 unresolved
        # relative, and the bake's scene would not open -- one stage after 9234
        # had shipped it without them for the adapter's reason (0.177.2). Same
        # rule as the directories: a new sibling in Lot means a line here.
        for obj in sorted(Path(themed_site_dir).glob("*.obj")):
            shutil.copy2(str(obj), str(export_dir / obj.name))

    # 2.7 LAYER 3 SURFACE DRESSING (roadmap 110). Before 3.5 on purpose:
    # the entry scene written there instances `<site>_dressing.tscn` beside
    # the level, and the closure verdict at 3.6 walks from that entry, so
    # the scene and the `.res` meshes it names have to be in the package
    # first. Needs Godot for the mesh extraction; without one the report
    # says so and the package ships undressed and says that too.
    dressing_report = None
    if profile.mode != MODE_PURE_SHELL and dressing_manifest:
        from packages.exporting.dressing_layer import ship_dressing
        dressing_report = ship_dressing(
            export_dir, dressing_manifest, clutter_dir, godot_executable,
            scratch_root=out_root)
        if dressing_report.get("shipped"):
            print("[export] surface dressing: %s -- %d instances of %d "
                  "meshes, %d draw calls"
                  % (dressing_report["scene"], dressing_report["instances"],
                     dressing_report["meshes"], dressing_report["draw_calls"]))
        else:
            print("[export] surface dressing NOT shipped: "
                  + "; ".join(dressing_report.get("reasons") or ["?"]))

    # 2.8 THE BACKDROP BEYOND THE PLATE'S EDGE (0.174.0, roadmap 228 step E):
    # the themed site's `backdrop` list and the site kit's modules, as
    # `<site>_backdrop.tscn` with one MultiMesh a module a side, which the
    # entry scene at 3.5 instances beside the level. Needs Godot for the
    # mesh extraction, as the dressing does; without one the report says so.
    backdrop_report = None
    if profile.mode != MODE_PURE_SHELL and backdrop_spec:
        from packages.exporting.backdrop_layer import ship_backdrop
        backdrop_report = ship_backdrop(
            export_dir, backdrop_spec, godot_executable, scratch_root=out_root)
        if backdrop_report.get("shipped"):
            print("[export] backdrop: %s -- %d instances of %d module(s) on their "
                  "sides, %d draw calls (%s; %d tower)"
                  % (backdrop_report["scene"], backdrop_report["instances"],
                     len(backdrop_report["modules"]), backdrop_report["draw_calls"],
                     ", ".join("%s %d" % kv for kv in backdrop_report["by_side"].items()),
                     backdrop_report["towers"]))
        else:
            print("[export] backdrop NOT shipped: "
                  + "; ".join(backdrop_report.get("reasons") or ["?"]))

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

    # THE RESOURCE-CLOSURE VERDICT USED TO RUN HERE, at step 3.6, and it is
    # now step 4.9 -- the last thing before the manifests. Nothing else moved.
    # See `_closure_verdict` below for what the middle of the build was
    # certifying and what it was not.

    # 4. project.godot, HANDOFF.md, manifests.
    _write_project_godot(export_dir, profile.entry_scene, mission_id,
                         profile.godot_version, profile.weather)
    (export_dir / "HANDOFF.md").write_text(handoff_text(layers, profile.mode), encoding="utf-8")
    # The light bake's marks go on before the second import pass, so the bake
    # does not import every model a third time (0.187.0).
    _write_import_sidecars(
        export_dir, godot_executable,
        bake_spawned=(responder_vehicle_scenes(themed_site_dir)
                      if profile.bake_lights else None))

    # Occluders. AFTER the sidecar pass, because the bake measures the GLBs'
    # real extents and cannot until Godot has imported them AND left the
    # `.godot` cache in place for it; BEFORE the resource manifest, so
    # `occluders.tscn` is in it like any other scene.
    #
    # NO LONGER BEST-EFFORT WHEN GODOT IS THERE, and cold run 9065 is why.
    # This step used to print a warning and exit 0, and a warning nobody reads
    # is how a package shipped with the culling flag on and nothing to cull.
    # The two cases are not the same defect and are no longer treated as one:
    #
    #   no Godot     nothing could be measured; a setup problem, not an export
    #                failure. The package ships with the culler OFF, which is
    #                a consistent and honest package.
    #   bake failed  Godot was there, the measurement was asked for, and it
    #                broke. That is this build failing, and it says so.
    #
    # Either way the flag is settled from the count that actually shipped, so
    # the flag and the occluders cannot disagree.
    #
    # THE HOLDER GOES INTO `mission.tscn` SINCE 0.102.0, not into `site.tscn`.
    # Cold run 9066's package shipped 301 occluder nodes and loaded none of
    # them: `occluders.tscn` was instanced from `site.tscn`, which the entry
    # scene does not name -- it instances `presentation/lux.applied.tscn` and
    # the dressing layer. The bake now runs against the entry scene too, so
    # the frame the occluders are measured in is the frame they are placed
    # in, and `count_at_runtime` inside `emit` asks Godot to load
    # `run/main_scene` and count what is really in the tree.
    from packages.exporting.occluders import (OccluderDisagreement,
                                              OccluderError, audit,
                                              drop_cache, emit,
                                              keep_cache)
    occluder_count = 0
    try:
        occ = emit(export_dir, godot_executable)
        occluder_count = int(occ["occluders"])
        print("[export] %d occluder(s) from %d solid module(s); "
              "%d glass, %d porous and %d filler left open"
              % (occ["occluders"], occ["classified"]["solid"],
                 occ["classified"]["glass"], occ["classified"]["porous"],
                 occ["classified"]["filler"]))
        rt = occ.get("runtime")
        if rt:
            print("[export]   %s loaded by Godot holds %d occluder node(s) "
                  "in a tree of %d"
                  % (rt["main_scene"], rt["occluder_nodes"],
                     rt["nodes_in_tree"]))
    except OccluderError as exc:
        if godot_executable and OCCLUDERS_ENFORCED:
            drop_cache(export_dir)
            raise ExportOccluderError(
                "the occluder bake failed and this build had a Godot to run "
                "it with: %s\n  report: %s\n  a package that cannot be "
                "measured must not be shipped claiming it was"
                % (exc, export_dir / "occluders.json"))
        print("[export] WARNING no occluders in this package: %s" % exc)
        print("[export]   occlusion culling stays OFF in project.godot; "
              "the package is consistent and buys nothing from the culler")

    # THE EMPTIES, MERGED ONE MESH A SIDE PER MATERIAL (0.143.0, roadmap 182).
    # After the occluder bake, whose boxes were measured on the modules and are
    # world-space, so they stay true of the merged geometry; before the light
    # bake, whose users are node paths -- the merged meshes are the users, and
    # arrive unwrapped. Needs the import cache, as both do. Without a Godot the
    # package keeps its per-module Empties: consistent, and merely slower.
    # With one, a merge whose report cannot be believed fails the build, as
    # the occluder bake does.
    from packages.exporting.merge_empties import MergeError
    from packages.exporting.merge_empties import merge as _merge_empties
    if godot_executable:
        try:
            mreport = _merge_empties(export_dir, godot_executable)
        except MergeError as exc:
            drop_cache(export_dir)
            raise ExportMergeError(
                "the Empties' merge failed and this build had a Godot to run "
                "it with: %s\n  report: %s" % (exc, export_dir / "merge_empties.json"))
        rows = mreport.get("scenes") or []
        if rows:
            print("[export] Empties merged: %d scene(s), %d mesh(es) of %d surface(s) "
                  "-> %d merged mesh(es), %d collider(s) kept"
                  % (len(rows), sum(r["meshes_in"] for r in rows),
                     sum(r["surfaces_in"] for r in rows),
                     sum(r["merged"] for r in rows), sum(r["colliders"] for r in rows)))
            # THE MODULES ONLY MERGED SLOTS INSTANCED (0.210.0, roadmap 249) go
            # before the light bake, which imports every model it finds for a
            # lightmap; the closure verdict and the resource manifest, written
            # after both, see the folder as it ships.
            from packages.exporting.merge_empties import drop_merged_modules
            dropped = drop_merged_modules(export_dir, mreport)
            print("[export] merged Empties' modules no file names: %d removed (%.1f MB), "
                  "%d named and kept" % (len(dropped["dropped"]), dropped["bytes"] / 1e6,
                                         dropped["kept"]))

    # THE ENTERABLE BUILDINGS, MERGED PER ROOM CELL AND MATERIAL (0.223.0, roadmap
    # 266). Where the Empties' merge runs and for its reasons; its rooms come from
    # Lot's record of the site, the one the responders are read from. A merge
    # whose report cannot be believed fails the build, as the Empties' does.
    if profile.merge_buildings and godot_executable and lot_gameplay is not None:
        from packages.exporting.merge_buildings import merge as _merge_buildings
        from packages.exporting.merge_empties import MergeError as _BMergeError
        try:
            breport = _merge_buildings(export_dir, godot_executable, lot_gameplay)
        except _BMergeError as exc:
            drop_cache(export_dir)
            raise ExportMergeError(
                "the buildings' merge failed and this build had a Godot to run "
                "it with: %s\n  report: %s" % (exc, export_dir / "merge_buildings.json"))
        brows = breport.get("scenes") or []
        if brows:
            print("[export] buildings merged: %d scene(s), %d slot(s), %d surface(s) "
                  "-> %d merged mesh(es), %d collider(s) kept"
                  % (len(brows), sum(r["slots_merged"] for r in brows),
                     sum(r["surfaces_in"] for r in brows),
                     sum(r["merged"] for r in brows), sum(r["colliders"] for r in brows)))
            from packages.exporting.merge_empties import drop_merged_modules
            bdropped = drop_merged_modules(export_dir, breport)
            print("[export] merged buildings' modules no file names: %d removed (%.1f MB), "
                  "%d named and kept" % (len(bdropped["dropped"]), bdropped["bytes"] / 1e6,
                                         bdropped["kept"]))
    elif profile.merge_buildings:
        print("[export] buildings NOT merged: %s -- the package keeps one module a slot"
              % ("no Godot" if not godot_executable else "no Lot site record"))

    # THE LIGHT BAKE (0.131.0), opt-in. After the occluder bake, which leaves
    # the import cache this needs, and before the cache is dropped; it points
    # the entry at `bake.tscn` and ships the lightmap, or restores what it
    # touched and ships the package unbaked, saying which in light_bake.json.
    if profile.bake_lights:
        from packages.exporting.light_bake import bake as _bake_lights
        # the responders' car (0.162.1): spawned by the gameplay layer, so
        # its import is set dynamic and it takes the lightmap's probes
        _bake_lights(export_dir, godot_executable,
                     spawned=responder_vehicle_scenes(themed_site_dir))

    # Settle the flag against what shipped. The cache the bake needed stays
    # until the greybox census has read it, below (0.181.0).
    proj = export_dir / "project.godot"
    proj.write_text(
        set_occlusion_culling(proj.read_text(encoding="utf-8"),
                              occluder_count), encoding="utf-8")

    # The backstop, read back off the files that are about to be zipped rather
    # than off the counts above. A check written against what the code
    # believes it wrote is indistinguishable from one that passed.
    try:
        verdict = audit(export_dir)
    except OccluderDisagreement as exc:
        raise ExportOccluderError(str(exc)) from exc
    print("[export] occlusion: use_occlusion_culling=%s with %d occluder "
          "node(s) reachable from res://%s (%d in the package, %d scene(s) "
          "walked)"
          % (str(verdict["use_occlusion_culling"]).lower(),
             verdict["occluder_nodes"], verdict["main_scene"],
             verdict["occluder_nodes_in_package"], verdict["scenes_walked"]))
    # A MEASUREMENT, NOT A CAUSE. A scene the entry never reaches is bytes on
    # a recipient's disk, and it is also how the occluders went missing -- so
    # the walk says which ones they are and stops. Whether one should be
    # dropped is a per-mission question: `lux.applied.tscn` names
    # `res://site.tscn` for a single-shell mission and does not for a themed
    # multi-building one, and deleting it broke closure once already.
    if verdict["unreachable_scenes"]:
        print("[export] %d scene(s) ship and res://%s reaches none of them: %s"
              % (len(verdict["unreachable_scenes"]), verdict["main_scene"],
                 ", ".join(verdict["unreachable_scenes"][:6])
                 + ("" if len(verdict["unreachable_scenes"]) <= 6
                    else ", ...")))

    # The warm-up. AFTER the occluder step, which also rewrites
    # `mission.tscn` -- the two add their holders in a fixed order and each
    # bumps the scene's `load_steps`, so running them the other way round
    # would work and would make the entry scene's diff depend on the order.
    # BEFORE the resource manifest, so `warmup.gd` is in it like any other
    # file.
    #
    # Needs no Godot, deliberately: the thing it fixes is a RUNTIME cost, and
    # a build step that cannot run without a Godot on the box is a step that
    # silently does not run -- which is exactly how 0.98.0's occluder defect
    # shipped. A package whose warm-up failed to wire is a package that
    # stalls on first sight, so this fails the build rather than warning.
    from packages.exporting.warmup import WarmupError
    from packages.exporting.warmup import audit as warmup_audit
    from packages.exporting.warmup import emit as warmup_emit
    try:
        warm = warmup_emit(export_dir)
        print("[export] warm-up: res://%s wired into %s as `%s`, %d guard(s)"
              % (warm["script"], warm["entry_scene"], warm["node"],
                 len(warm["guards_present"])))
        # The stride is what decides the load this package will charge, so it
        # is said out loud rather than left in warmup.json for whoever thinks
        # to open it.
        print("[export] warm-up knobs: %s"
              % ", ".join("%s=%s" % (n, k["default"])
                          for n, k in sorted(warm["knobs"].items())))
    except WarmupError as exc:
        raise ExportWarmupError(
            "the warm-up could not be shipped: %s\n  a package without one "
            "stalls on first sight -- 8,564 ms in one frame, measured on cold "
            "run 9066's package with both shader caches cleared" % exc) from exc

    # The backstop, read back off the files that are about to be zipped rather
    # than off the report above.
    try:
        warm_verdict = warmup_audit(export_dir)
    except WarmupError as exc:
        raise ExportWarmupError(str(exc)) from exc
    print("[export] warm-up verdict: %d node, script shipped=%s"
          % (warm_verdict["warmup_nodes"],
             str(warm_verdict["script_shipped"]).lower()))

    # Dispatch's node addresses, checked against what actually shipped, now
    # that every scene is in place (roadmap 101).
    bindings = strip_dead_node_paths(export_dir)
    if bindings.get("moved_total"):
        print("[export] %d handoff node path(s) named nothing in the package "
              "and were moved to node_dispatch -- see handoff_bindings.json"
              % bindings["moved_total"])

    # 4.81 HOW RESPONDERS ARRIVE (0.157.0, roadmap 212). Above the glb
    # scan, the closure verdict and the manifest walk, so the file is inside
    # the package each of them describes and the manifest lists it.
    # `closure._METADATA_FILES` names it: its anchor ids are shaped like the
    # NodePath strings the authoring-path test reads as paths, the reasoning
    # that put `handoff_bindings.json` there.
    arrivals_doc = write_responder_arrivals(export_dir, lot_gameplay, themed_site_dir)
    if arrivals_doc is not None:
        print("[export] responder arrivals: %d, in %s"
              % (len(arrivals_doc["arrivals"]), RESPONDER_ARRIVALS_NAME))

    # 4.85 DOES EVERY GLB IN THIS PACKAGE GET WHAT IT ASKS FOR? See
    # `packages.exporting.glb_refs` for what was shipped without this and why
    # nothing caught it. Three gates were closed over what the package
    # CONTAINS -- closure over `res://` references, the manifest over files
    # present, the cold-run verdict over hands needed -- and none over what it
    # REFERS TO.
    #
    # ABOVE THE CLOSURE VERDICT, so `glb_reference_scan.json` is inside the
    # package the verdict describes and inside the manifest that lists it. It
    # is therefore NOT in `_WRITTEN_AFTER_VERDICT`, and must not be added
    # there: being after the verdict and being outside the manifest are two
    # different facts about a file and this one is neither.
    #
    # AFTER every step that writes a GLB -- the composed-root copy, the
    # sibling directories, the dressing layer. The occluder bake writes no
    # geometry, so its position relative to this does not matter; it is below
    # it anyway because the bake wants the import cache this does not.
    from packages.exporting import glb_refs
    glb_report = glb_refs.scan(export_dir)
    (export_dir / "glb_reference_scan.json").write_text(
        pretty_dumps(glb_report), encoding="utf-8")
    print("[export] glb references: " + glb_refs.summary(glb_report))
    if glb_report["nothing_to_check"]:
        # SAID, not refused. The reasoning and the measurement that reversed
        # the refusal are in `glb_refs`'s docstring; the short version is that
        # `pure-shell` legitimately produces a package with no `.glb` in it,
        # and whether the entry reaches any geometry is the closure verdict's
        # question three steps below this one.
        print("[export]   this package contains no .glb, so the reference "
              "gate has certified nothing about it")
    try:
        glb_refs.assert_closed(export_dir, glb_report)
    except glb_refs.GlbReferenceError as exc:
        raise ExportGlbReferenceError(
            str(exc) + "\n  full report: "
            + str(export_dir / "glb_reference_scan.json")
            + "\n  a package whose GLBs name files it does not carry renders "
              "as greybox and passes every other gate in this exporter") from exc

    # 4.87 DOES THIS THEMED PACKAGE STILL DRAW GREYBOX? See
    # `packages.exporting.greybox_skin`, which owns the verdict, and
    # `assets/godot/greybox_census.gd`, which owns the measurement.
    #
    # IN THE ENGINE, not over the GLBs: `zoo_worldskin.gd` is an import
    # post-processor, so a shipped GLB keeps its `gb_*` materials by design
    # and a glTF-level check would refuse every package ever built.
    #
    # ABOVE THE CLOSURE VERDICT, so `greybox_skin_scan.json` is inside the
    # package the verdict describes and inside the manifest that lists it --
    # the same reasoning as the GLB reference gate above, and the same
    # consequence: it must NOT be added to `_WRITTEN_AFTER_VERDICT`.
    #
    # ENFORCED ONLY WITH A GODOT TO RUN IT, matching the occluder bake. A
    # build with no engine cannot take this census, and a census not taken
    # must say so rather than read as a clean package.
    from packages.exporting import greybox_skin
    if godot_executable:
        try:
            gb_report = greybox_skin.measure(export_dir, godot_executable)
            print("[export] greybox skin: " + greybox_skin.summary(
                gb_report, any_role=profile.require_no_greybox))
            greybox_skin.assert_skinned(export_dir, gb_report,
                                        any_role=profile.require_no_greybox)
        except greybox_skin.GreyboxCensusError as exc:
            raise ExportGreyboxSkinError(
                "the greybox census failed and this build had a Godot to run "
                "it with: %s\n  a package that cannot be measured must not "
                "be shipped claiming it was" % exc) from exc
        except greybox_skin.GreyboxSkinError as exc:
            raise ExportGreyboxSkinError(str(exc)) from exc
    else:
        print("[export] greybox skin: no Godot in this build, so the census "
              "was not taken and nothing is certified about it")

    # 4.88 CAN A BODY WALK OFF AN EDGE THE LEVEL DID NOT DECLARE? (0.216.0,
    # factory roadmap 173.) See `packages.exporting.drop_edges`, which owns the
    # verdict, and `assets/godot/walkable_edge.gd`, which owns the measurement.
    #
    # IN THE ENGINE, because the question is where a BODY stands and falls:
    # the body's own capsule over every surface, a flood from the package's
    # player_start across steps, falls and its ladders, and every reached edge
    # with a fall beyond a step and nothing in the way. The declared set is
    # the package's own: its drop links, its ladders' shafts, a flight's own
    # open side. Refuses on an UNDECLARED drop INDOORS; a roof's rim, a dock
    # and a thing's top are reported.
    #
    # ABOVE THE CLOSURE VERDICT, like the greybox census: `drop_edges.json`
    # and `drop_edges_scan.json` are inside the package the verdict describes
    # and inside the manifest that lists it. NOT in `_WRITTEN_AFTER_VERDICT`.
    #
    # ENFORCED ONLY WITH A GODOT TO RUN IT, and OPTED OUT by the profile
    # (`require_declared_drops`): a build with no engine cannot take the
    # census, and a census not taken must say so rather than read as clean.
    # A package with no `player_start` (a single shell exported on its own,
    # as this exporter's tests do) seeds no flood: the census is NOT TAKEN,
    # the scan says so, and the export goes on -- not refused over a thing
    # it could not measure, not certified either.
    from packages.exporting import drop_edges
    if godot_executable:
        try:
            de_report = drop_edges.measure(export_dir, godot_executable)
            de_scan = drop_edges.classify(de_report, export_dir)
            drop_edges.write_scan(export_dir, de_scan)
            print("[export] drop edges: " + drop_edges.summary(de_scan))
            if profile.require_declared_drops:
                drop_edges.assert_declared(export_dir, de_scan)
            else:
                print("[export] drop edges: the profile does not require "
                      "declared drops, so the count above is reported, not "
                      "refused on")
        except drop_edges.NoSeedError as exc:
            de_scan = drop_edges.not_taken(str(exc))
            drop_edges.write_scan(export_dir, de_scan)
            print("[export] drop edges: " + drop_edges.summary(de_scan))
        except drop_edges.DropCensusError as exc:
            raise ExportDropEdgesError(
                "the drop-edge census failed and this build had a Godot to "
                "run it with: %s\n  a package that cannot be measured must "
                "not be shipped claiming it was" % exc) from exc
        except drop_edges.UndeclaredDropError as exc:
            raise ExportDropEdgesError(str(exc)) from exc
    else:
        print("[export] drop edges: no Godot in this build, so the census "
              "was not taken and nothing is certified about it")

    # THE CACHE GOES HERE, AFTER THE CENSUS (0.181.0, factory roadmap 239), and
    # before the closure verdict and `build_resource_manifest` walk the tree,
    # so neither can meet a cache entry and the package stays cache-free. It
    # was dropped straight after the bake, and the census then imported the
    # whole package again to read it: 100.4 of a 430.7 s export, profiled on
    # cold run 9248's -- the fifth import of the same files in one export.
    # Nothing between the bake and this line reads the cache's file types
    # (`.scn`, `.mesh`, `.md5`, `.cfg`): the occlusion audit and the handoff
    # walk read `*.tscn`, the GLB scan `*.glb`, the rest JSON.
    #
    # KEPT BESIDE THE PACKAGE, NOT DELETED (0.188.0): the walk copy starts
    # from it instead of importing every file again -- 9.6 s against 86 s,
    # `occluders.keep_cache` says how that was measured. The package leaves
    # this line as cache-free as it did.
    kept = keep_cache(export_dir)
    if kept is not None:
        print("[export] import cache moved beside the package (%s); the "
              "package ships sidecars, not %s" % (kept.name, ".godot"))

    # THE IMPORT PINS, READ BACK OFF THE FILES THAT SHIP (0.182.0): after the
    # last import and the cache, before the verdict and the manifest describe
    # the package. `_repin_after_imports` says why it has to be here.
    pins = _repin_after_imports(export_dir)
    print("[export] import pins: %d of %d shared-texture sidecar(s) carry their "
          "pins; %d re-pinned after an import reset them, %d sign sidecar(s) "
          "re-pinned, %d skin sidecar(s) re-pinned"
          % (pins["shared_sidecars"], pins["shared_sidecars"],
             pins["shared_repinned"], pins["sign_repinned"], pins["skin_repinned"]))

    # 4.9 Resource-closure VERDICT -- see `_closure_verdict`. LAST, after
    # every step that writes into the package and before the manifests, which
    # describe it and so cannot be in it.
    scan = _closure_verdict(export_dir)
    print("[export] closure verdict: ok=%s, %d issue(s) over %d resource(s) "
          "in a package of %d file(s)"
          % (str(scan.ok).lower(), len(scan.issues), scan.resource_count,
             len(scan.present_names)))

    # 4.95 THE BLOCKS THAT DESCRIBE THE BUILD BUT ARE NOT ABOUT THE PACKAGE'S
    # CONTENTS -- licences, profile, layers.
    #
    # ABOVE THE MANIFEST WALK, and that is the fix in 0.104.0. These three sat
    # below it for no stated reason and were therefore shipped unlisted:
    # measured on cold run 9067's `LF_club_block_006.portable-godot`, 562
    # files listed against 567 on disk. Nothing about a licence block or a
    # profile dump makes it unlistable -- unlike the resource manifest, which
    # cannot hash itself. They were simply written four lines too low, and an
    # integrator checking the package against its manifest met three files
    # nobody had announced.
    #
    # They still land AFTER the closure verdict, which is where 0.103.0 put
    # it, and all three are already in `_WRITTEN_AFTER_VERDICT` and in
    # `closure._METADATA_FILES` -- so `_guard_verdict_is_about_the_package`
    # is satisfied by construction and nothing about the verdict moves.
    license_manifest = build_license_manifest(tool_versions)
    (export_dir / "LICENSES.json").write_text(
        pretty_dumps(license_manifest), encoding="utf-8")
    (export_dir / "export_profile.json").write_text(
        pretty_dumps(profile.as_dict()), encoding="utf-8")
    record = output_layers_record(layers)
    (export_dir / "output_layers.json").write_text(pretty_dumps(record), encoding="utf-8")
    # `LAYER_LIGHT` is "light" (pinned by test_layers_shown); the record carries strings
    print("[export] layers: %s (%s); the light is Lux's result, a layer apart from the art%s"
          % (", ".join(record["layers"]) or "none, the graybox alone", record["label"],
             "" if "light" in record["layers"] else " -- this package carries none"))

    # 4.96 THE RESOURCE MANIFEST. Everything written above this line is in it;
    # the two files written below are named in its `unlisted` block with the
    # reason each cannot be, and `_guard_manifest_accounts_for_the_package`
    # checks the sum against the finished folder.
    resource_manifest = build_resource_manifest(export_dir)
    (export_dir / "portable_resource_manifest.json").write_text(
        pretty_dumps(resource_manifest), encoding="utf-8")

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
            # WHICH package that verdict is about. Until 0.103.0 the honest
            # answer was "an earlier one": the judge ran at step 3.6 and 274
            # files landed after it on cold 9067, three of them Godot
            # resources. The fingerprint is re-derivable from the folder with
            # `closure.fingerprint_package` and the `written_after_verdict`
            # list the verdict carries, so the claim is checkable by somebody
            # who did not run the build.
            "export_closure_package_fingerprint": scan.package_fingerprint,
            "not_run": ["portability -- runs after the build, as a separate command"],
            "note": "This block records what THIS BUILD checked. Pipeline-stage results (walktest, nav gate, grades) are not visible from here; their absence is not a claim they did not run.",
        },
    }), encoding="utf-8")

    # Nothing may be written into the package below this line. The guards are
    # what make that a fact rather than a request. They ask two different
    # questions of the same folder and both are read back off disk: the first,
    # whether the verdict in the package is about this package; the second,
    # whether the manifest in the package accounts for this package.
    _guard_verdict_is_about_the_package(export_dir, scan)
    _guard_manifest_accounts_for_the_package(export_dir)
    acc = resource_manifest["accounting"]
    print("[export] manifest: %d file(s) listed + %d declared unlisted = %d "
          "in the package (%s)"
          % (acc["listed"], acc["declared_unlisted"], acc["files_in_package"],
             ", ".join(u["path"] for u in resource_manifest["unlisted"])))

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
