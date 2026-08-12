"""Stage composed building packages into a site job's own directory.

A themed site places N buildings, and each one arrives as a SELF-CONTAINED
Godot project: ``site.tscn`` beside ``site_base.glb`` and ``art/``, with every
internal reference written ``res://<something>`` rooted at THAT package. Five
of those merged into one directory collide on every name they have.

So each package is staged under ``lot/<id>/`` and its scenes are rewritten to
reference their siblings RELATIVELY, with no ``res://`` prefix at all. Godot
resolves a non-``res://`` ext_resource path against the referencing scene's own
directory -- measured, not assumed: a probe project whose root scene instanced
``lot/a/inner.tscn``, which in turn referenced a bare ``leaf.tscn`` that exists
only beside it, loaded clean under 4.7.stable and printed its marker. Had the
engine resolved against the project root instead it would have looked for
``<project>/leaf.tscn`` and missed.

That choice is what makes the result drop-in ANYWHERE. Rewriting to
``res://lot/<id>/X`` would also load, but only for a consumer who puts ``lot/``
at their own project root -- which is not "drop this folder in", it is "drop
this folder in at one specific place and nowhere else".

WHY THIS CANNOT BE LEFT TO THE READER. Lot's own resolvers
(``site_ground._resolve_res``, ``site_collision._resolve_res``) look up
``res://X`` by walking the scene's directory and then its ancestors, so they
resolve an unrewritten staged package perfectly well and report the site fully
read and fully floored. Godot does not. Measured against the real ``final_stand``
and ``pharmacy_a02`` scenes staged at ``out/lot/<id>/``:

    res://site_base.glb                    ground HIT  collision HIT  godot MISS
    lot/final_stand/site_base.glb          ground HIT  collision HIT  godot HIT

Both of Lot's gates pass on the artifact the engine cannot load. The rewrite is
therefore not something a downstream check would have caught, and the second
row is also the evidence that rewriting does not regress those gates.
"""
from __future__ import annotations

import os
import re
import shutil
from pathlib import Path
from typing import Mapping

#: Harness and metadata a package carries for its own standalone self-check.
#: None of it survives contact with being one building among five:
#: ``project.godot`` would be a second, nested project (Godot loads one), and
#: ``site_main.tscn`` is the portable entry that instances the building sitting
#: beside it -- the site scene does that instancing now.
SKIP_NAMES = frozenset({
    "project.godot",
    "compose.summary.json",
    "HANDOFF.md",
    "portable_resource_manifest.json",
})

#: ``[ext_resource ... path="res://X" ...]``. Deliberately anchored on the
#: ext_resource header rather than on ``res://`` anywhere in the file: a scene
#: can carry an embedded GDScript block, and a ``preload('res://...')`` inside
#: one is resolved by the ENGINE AT RUNTIME from the project root. Rewriting
#: that string would break it in a way no file-level check would see.
_EXT_RESOURCE = re.compile(r'(\[ext_resource\b[^\]]*?\bpath=")res://([^"]*)(")')

#: The runtime form of the same reference, which this module must never rewrite
#: and must never silently leave dangling. See `_runtime_res_refs`.
_RUNTIME_RES = re.compile(r"""(?:preload|load)\s*\(\s*['"]res://([^'"]+)['"]""")


class StagingError(RuntimeError):
    """A package could not be staged. Never downgraded to a warning.

    A varied lot has already shipped once with every stage reporting success
    and the mission shell standing in five times, because a probe for a missing
    archetype scene ran before the scene existed and its absence was read as
    "nothing to do". A site that is quietly not the site that was asked for is
    the failure this refuses to repeat.
    """


def _runtime_res_refs(text: str) -> list[str]:
    """``res://`` paths a scene resolves at RUNTIME, which staging cannot fix.

    An ext_resource path is data this module rewrites. A ``preload('res://x')``
    inside an embedded script is code, and it will be resolved against the
    consumer's project root wherever this pack lands. There is no rewrite that
    makes that correct for an unknown root, so a package carrying one is
    reported rather than shipped looking fine.
    """
    return sorted(set(_RUNTIME_RES.findall(text)))


def portable_refs(text: str, *, scene_rel_dir: str = "") -> str:
    """Rewrite a scene's ``res://`` ext_resource paths to scene-relative ones.

    ``scene_rel_dir`` is the scene's own directory RELATIVE TO ITS PACKAGE
    ROOT, because ``res://X`` inside a package means "X from the package root"
    and a relative path means "X from this scene". They are the same string
    only for a scene sitting at the root, which is where ``site.tscn`` sits --
    so passing this is currently always a no-op and is still computed properly.
    A parameter the caller has to supply and the body ignores is how a formula
    ends up wrong by exactly the term nobody used.
    """
    if not scene_rel_dir or scene_rel_dir in (".", ""):
        return _EXT_RESOURCE.sub(lambda m: f"{m.group(1)}{m.group(2)}{m.group(3)}",
                                 text)

    def _rel(match: re.Match) -> str:
        target = match.group(2)
        rel = os.path.relpath(
            os.path.join("_root_", target),
            os.path.join("_root_", scene_rel_dir),
        ).replace("\\", "/")
        return f"{match.group(1)}{rel}{match.group(3)}"

    return _EXT_RESOURCE.sub(_rel, text)


def absolute_refs(text: str) -> list[str]:
    """Every ext_resource path in a scene that names an absolute location.

    The defect this module exists to prevent, stated as an observation rather
    than a rule: ``res://`` is rooted at the Godot project directory, so
    ``res://C:/Projects/...`` asks for a folder literally named ``C:`` inside
    the project and can resolve nowhere. A drive letter, a leading slash and a
    UNC prefix are all the same mistake wearing different punctuation.
    """
    out = []
    for match in re.finditer(r'\[ext_resource\b[^\]]*?\bpath="([^"]*)"', text):
        path = match.group(1)
        bare = path[len("res://"):] if path.startswith("res://") else path
        if re.match(r"^(?:[A-Za-z]:[\\/]|[\\/])", bare):
            out.append(path)
    return out


def stage_package(source: Path, dest_root: Path, package_id: str,
                  *, subdir: str = "lot") -> str:
    """Copy ONE composed package under ``<dest_root>/<subdir>/<id>/``.

    Returns the site-relative path of the package's content scene, which is
    what the site spec should name and what Lot will write into the site
    scene's ext_resource line.
    """
    source = Path(source)
    dest_root = Path(dest_root)
    if not source.is_dir():
        raise StagingError(
            f"package '{package_id}' is not a directory: {source}")
    scene = source / "site.tscn"
    if not scene.is_file():
        raise StagingError(
            f"package '{package_id}' has no site.tscn at {source} -- a varied "
            f"lot that silently drops a building is a different level wearing "
            f"the same brief")

    dest = dest_root / subdir / package_id
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)

    for item in sorted(source.iterdir()):
        if item.name in SKIP_NAMES or item.name.endswith("_main.tscn"):
            continue
        if item.is_dir():
            shutil.copytree(item, dest / item.name)
        else:
            shutil.copy2(item, dest / item.name)

    # Rewrite every scene we kept, each against its OWN directory.
    for tscn in sorted(dest.rglob("*.tscn")):
        text = tscn.read_text(encoding="utf-8")
        runtime = _runtime_res_refs(text)
        if runtime:
            raise StagingError(
                f"package '{package_id}' scene {tscn.name} resolves "
                f"{', '.join(runtime)} at runtime via preload/load. Staging "
                f"rewrites ext_resource data, not code, so that reference "
                f"would be resolved against the consumer's project root and "
                f"dangle wherever this pack lands")
        rel_dir = tscn.parent.relative_to(dest).as_posix()
        tscn.write_text(portable_refs(text, scene_rel_dir=rel_dir),
                        encoding="utf-8")

    return f"{subdir}/{package_id}/site.tscn"


def stage_glb(source: Path, dest_root: Path, building_id: str,
              *, subdir: str = "buildings") -> str:
    """Copy ONE baked ``.glb`` in, for the greybox path.

    Same defect, smaller shape: the greybox site spec names its shell by
    absolute path too, so ``lot_assemble`` has always emitted ``res://C:/``
    exactly like the themed path. A ``.glb`` carries no ext_resource lines, so
    there is nothing to rewrite -- only somewhere coherent to put it.
    """
    source = Path(source)
    if not source.is_file():
        raise StagingError(
            f"building '{building_id}' has no geometry at {source}")
    dest = Path(dest_root) / subdir
    dest.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, dest / f"{building_id}{source.suffix}")
    return f"{subdir}/{building_id}{source.suffix}"


def stage_addon_scripts(addon_dir: Path, dest_root: Path) -> list[str]:
    """Copy Lot's runtime scripts to the site root, for the walk scene.

    ``write_walk_scene(portable=True)`` names them bare (``lot_player.gd``, not
    ``addons/lot/lot_player.gd``) precisely so the pack does not have to claim
    an ``addons/`` directory in somebody else's project, where it would merge
    with theirs. This puts them where that scene looks.
    """
    addon_dir = Path(addon_dir)
    dest_root = Path(dest_root)
    dest_root.mkdir(parents=True, exist_ok=True)
    copied = []
    for name in ("lot_player.gd", "lot_site_walk.gd", "lot_navqa_setup.gd"):
        src = addon_dir / name
        if src.is_file():
            shutil.copy2(src, dest_root / name)
            copied.append(name)
    return copied


def stage_all(manifest: Mapping[str, object], dest_root: Path) -> dict:
    """Stage everything one site job needs, from a manifest built at spec time.

    The manifest is CONSTRUCTED, not probed. It is written while the plan is
    being built, before the compose jobs that produce these packages have run,
    so nothing here may ask whether a source exists in order to decide what to
    do -- it may only refuse when a source it was told about is missing at
    staging time, which is exactly what `StagingError` is for.
    """
    dest_root = Path(dest_root)
    report: dict = {"packages": {}, "glbs": {}, "addons": []}

    for package_id, source in sorted(
            (manifest.get("packages") or {}).items()):
        report["packages"][package_id] = stage_package(
            Path(str(source)), dest_root, package_id)

    for building_id, source in sorted((manifest.get("glbs") or {}).items()):
        report["glbs"][building_id] = stage_glb(
            Path(str(source)), dest_root, building_id)

    addon_dir = manifest.get("addon_dir")
    if addon_dir:
        report["addons"] = stage_addon_scripts(Path(str(addon_dir)), dest_root)

    return report
