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


class ExportContentError(RuntimeError):
    """A package has nothing for its entry scene to instance.

    Raised rather than returned because there is no partial success
    here: an export that writes an entry adding no children produces a
    package that opens to an empty level and passes every check that
    starts from the entry.
    """


@dataclass
class LocalizeReport:
    rewritten_absolute: list[str] = field(default_factory=list)
    localized_scripts: list[str] = field(default_factory=list)
    stripped_scenes: list[str] = field(default_factory=list)
    sanitized_json: list[str] = field(default_factory=list)
    unresolved: list[str] = field(default_factory=list)
    repaired_bare_refs: list[str] = field(default_factory=list)
    rerooted_refs: list[str] = field(default_factory=list)
    entry_scene: str | None = None
    #: What the entry actually INSTANCES. Recorded because
    #: `entry_scene` only ever says `mission.tscn`, which is true of a
    #: package that opens to nothing.
    entry_instances: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "schema": "level_factory.export_closure.v0.1",
            "rewritten_absolute": sorted(self.rewritten_absolute),
            "localized_scripts": sorted(self.localized_scripts),
            "stripped_scenes": sorted(self.stripped_scenes),
            "sanitized_json": sorted(self.sanitized_json),
            "unresolved": sorted(self.unresolved),
            "repaired_bare_refs": sorted(self.repaired_bare_refs),
            "rerooted_refs": sorted(self.rerooted_refs),
            "entry_scene": self.entry_scene,
            "entry_instances": list(self.entry_instances),
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
    """Copy addons/<tool>/<rest> into runtime/<tool>/<rest>; return res-rel path.

    <rest> may be a DIRECTORY: lux_root.gd scans its preset library via
    ``res://addons/lux/presets`` (this crashed v0.10.0 exports with Errno 13
    on real hardware — copy2 on a directory). Directories are copytree'd:
    a localized LuxRoot needs its presets to travel with it. Any copy
    failure is recorded, never raised — closure problems belong in the
    report and the portability verdict, not in a dead export.
    """
    repo = addon_sources.get(tool)
    if repo is None:
        return None
    src = Path(repo) / "addons" / tool / rest
    if not src.exists():
        return None
    target = export_dir / _RUNTIME_DIR / tool / rest
    try:
        if src.is_dir():
            shutil.copytree(src, target, dirs_exist_ok=True)
            report.localized_scripts.append(f"addons/{tool}/{rest}/ (dir)")
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            if not target.exists():
                shutil.copy2(src, target)
                report.localized_scripts.append(f"addons/{tool}/{rest}")
    except OSError as exc:
        report.unresolved.append(f"addons/{tool}/{rest}: copy failed ({exc})")
        return None
    rel = (Path(_RUNTIME_DIR) / tool / rest).as_posix()
    # Preserve a trailing slash: lux_root.gd holds a preset-DIR path
    # ("res://addons/lux/presets/") and appends filenames (dir + f). Path()
    # normalizes the slash away, which produced "res://runtime/lux/presetsX.tres"
    # (no separator) on hardware. Keep it a directory ref if <rest> was one.
    return rel + "/" if rest.endswith("/") else rel


def _rewrite_text(path: Path, export_dir: Path, addon_sources: dict[str, Path],
                  report: LocalizeReport,
                  class_map: dict[str, tuple[str, str]] | None = None) -> bool:
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

    # Class-name closure (localized .gd only): pull scripts referenced by
    # global class name. The names need no rewriting — presence + the import
    # pass registers them — but a fresh copy must count as a change so the
    # fixpoint loop rescans it for ITS references.
    if class_map and path.suffix == ".gd":
        for cname, (tool, rest) in class_map.items():
            target = export_dir / _RUNTIME_DIR / tool / rest
            if target.exists():
                continue
            if re.search(r"\b" + re.escape(cname) + r"\b", new):
                if _localize_script(tool, rest, addon_sources, export_dir, report):
                    changed = True

    if changed:
        path.write_text(new, encoding="utf-8")
    return changed


_CLASS_NAME_DECL = re.compile(r"^class_name\s+([A-Za-z_]\w*)", re.MULTILINE)


def _build_class_map(addon_sources: dict[str, Path]) -> dict[str, tuple[str, str]]:
    """class_name -> (tool, path-under-addons/<tool>) across all tool repos.

    GDScript cross-references by GLOBAL CLASS NAME carry no res:// path for
    the ref rewriter to chase — the v0.10.1 hardware run localized lux_root.gd
    but none of the classes it names (30 parse errors in the clean project).
    The class map lets the .gd scan pull those scripts by name; once they are
    IN the project, the portability import pass registers them and the names
    resolve — no text rewrite needed for the names themselves.
    """
    out: dict[str, tuple[str, str]] = {}
    for tool, repo in addon_sources.items():
        base = Path(repo) / "addons" / tool
        if not base.is_dir():
            continue
        for gd in base.rglob("*.gd"):
            try:
                m = _CLASS_NAME_DECL.search(gd.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError):
                continue
            if m:
                out[m.group(1)] = (tool, gd.relative_to(base).as_posix())
    return out


#: Disposable QA harnesses that have no business in a deliverable.
#: `site_navqa.tscn` is Lot's nav-QA scene and `lot_navqa_setup.gd` is the
#: script that wires it to `res://addons/heist_nav_qa/nav_qa_director.gd` --
#: an addon a portable package cannot carry by contract. `mp_smoke*` is named
#: alongside them in ENGINE_GATES and is listed here for the same reason,
#: whether or not a given mission emits one.
_QA_HARNESS_FILES = ("site_navqa.tscn", "lot_navqa_setup.gd",
                     "mp_smoke.gd", "mp_smoke_node.gd")

#: Dev-only walk chrome. Kept apart from `_QA_HARNESS_FILES` on purpose: that
#: list goes unconditionally because nothing may ask for a QA harness, while
#: these two ARE asked for when a profile says include_walk -- `lot.py` emits
#: the walk scene naming both. So they go only alongside the walk scene, and
#: only when nothing else still references them.
#:
#: Measured on lot_demo_001 --mode pure-shell: both shipped, referenced by
#: nothing, in a package documented as functional geometry + collision +
#: anchors only. Closure scanning cannot catch this -- an unreferenced file
#: resolves fine, it simply has no business being in a deliverable.
_WALK_CHROME_FILES = ("lot_player.gd", "lot_site_walk.gd")


def _still_referenced(export_dir: Path, target: Path) -> bool:
    """Does any surviving text resource name this file?

    Matched by BASENAME and deliberately wide: a reference can arrive as
    ``res://lot_player.gd``, as a bare relative ``lot_player.gd``, or inside a
    preload in a .gd. Erring wide keeps a file that could have gone, which
    costs bytes; erring narrow deletes a script a scene still needs, which
    costs a package -- and with CLOSURE_ENFORCED True, an export.
    """
    for f in sorted(export_dir.rglob("*")):
        if not (f.is_file() and f.suffix in _TEXT_SUFFIXES) or f == target:
            continue
        try:
            if target.name in f.read_text(encoding="utf-8"):
                return True
        except (OSError, UnicodeDecodeError):
            continue
    return False


#: Any res:// reference in a text resource.
_RES_REF = re.compile(r'res://([^"\')\s]+)')


def _reroot_subpackages(export_dir: Path, report: LocalizeReport) -> None:
    """Reroot a package that was staged as its own res:// root.

    `res://x` is `<project root>/x` exactly. Deli Counter stages each themed
    building as its own res:// root, so `lot/<archetype>/site.tscn` names its
    modules `res://art/zoo/wall.glb` and its shell `res://site_base.glb`.
    Copying that package into a subdirectory of the export root does not move
    the references with it.

    Measured on lot_demo_001.portable-godot: five building scenes, 25 dangling
    art references each -- and a 26th, `res://site_base.glb`, which RESOLVES,
    to the site's 255 KB base mesh instead of the building's 108 KB one. Not
    missing, not misrooted, not detectable by any closure category: five
    buildings quietly standing the wrong geometry.

    So ask the disk which root the file was written against, rather than
    assuming `lot/<id>` is a package boundary: walk from the file's directory
    upward, take the DEEPEST ancestor under which strictly more of its
    references resolve than resolve at the export root, and rewrite only the
    references that actually resolve there. No ancestor wins -> no edit. A
    file already at the export root is already at its own root and is skipped.
    """
    for f in sorted(export_dir.rglob("*")):
        if not (f.is_file() and f.suffix in _TEXT_SUFFIXES):
            continue
        if f.parent == export_dir:
            continue
        try:
            text = f.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        refs = sorted(set(_RES_REF.findall(text)))
        if not refs:
            continue
        at_root = sum(1 for r in refs if (export_dir / r).exists())
        if at_root == len(refs):
            continue

        root_rel = None
        cand = f.parent.relative_to(export_dir)
        while cand != Path("."):
            if sum(1 for r in refs if (export_dir / cand / r).exists()) > at_root:
                root_rel = cand.as_posix()
                break
            cand = cand.parent
        if root_rel is None:
            continue

        new = text
        moved = 0
        for r in refs:
            if r.startswith(root_rel + "/"):
                continue
            if not (export_dir / root_rel / r).exists():
                continue
            # The lookahead is what keeps `.../wall_w30.glb` from matching
            # inside `.../wall_w300.glb`: a reference always ends at a quote,
            # whitespace or a closing paren.
            new = re.sub(r'res://' + re.escape(r) + r'(?=["\'\s)])',
                         f'res://{root_rel}/{r}', new)
            moved += 1
        if moved and new != text:
            f.write_text(new, encoding="utf-8")
            report.rerooted_refs.append(
                f"{f.relative_to(export_dir).as_posix()}: {moved} ref(s) -> "
                f"res://{root_rel}/")


def localize_export(export_dir: Path, *, addon_sources: dict[str, Path],
                    strip_walk: bool = True, max_passes: int = 10) -> LocalizeReport:
    """Repair the export's resource closure in place."""
    report = LocalizeReport()
    class_map = _build_class_map(addon_sources)

    if strip_walk:
        for walk in sorted(export_dir.rglob("*_walk.tscn")):
            report.stripped_scenes.append(walk.relative_to(export_dir).as_posix())
            walk.unlink()

    # THE NAV QA HARNESS IS THE SAME CLASS OF FILE and was never named, so it
    # shipped. `ENGINE_GATES.md`: "`nav_qa_director.gd` and `mp_smoke.gd` are
    # disposable QA harnesses, and neither may grow into a player controller."
    #
    # Measured on lot_demo_001's portable export: `lot_navqa_setup.gd` shipped
    # and referenced `res://addons/heist_nav_qa/nav_qa_director.gd`, which a
    # portable package cannot contain by contract -- one of 21 unresolved
    # references. An instrument in the deliverable, and a dangling one.
    #
    # Stripped unconditionally, not under `strip_walk`. That flag exists so a
    # profile can ASK for the walk scene; nothing asks for the QA harness, and
    # a parameter nobody passes is an unfinished thought. If a caller ever
    # wants it, it gets its own flag and its own reason.
    for name in _QA_HARNESS_FILES:
        for stray in sorted(export_dir.rglob(name)):
            report.stripped_scenes.append(
                stray.relative_to(export_dir).as_posix())
            stray.unlink()

    # The walk scene was the only thing naming its player and setup scripts,
    # so deleting the scene orphaned them and they shipped anyway. Runs AFTER
    # both strips above, so that anything already deleted cannot count as a
    # referrer and keep a file alive on the strength of a scene that is gone.
    if strip_walk:
        for name in _WALK_CHROME_FILES:
            for stray in sorted(export_dir.rglob(name)):
                if _still_referenced(export_dir, stray):
                    continue
                report.stripped_scenes.append(
                    stray.relative_to(export_dir).as_posix())
                stray.unlink()

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
                try:
                    changed |= _rewrite_text(f, export_dir, addon_sources, report,
                                             class_map)
                except OSError as exc:
                    report.unresolved.append(
                        f"{f.relative_to(export_dir).as_posix()}: rewrite failed ({exc})")
        if not changed:
            break

    # Reroot packages staged as their own res:// root (building packages under
    # lot/<archetype>/). BEFORE the bare-ref repair below, which would rewrite
    # a building's `res://site_base.glb` to `res://assets/site_base.glb` on a
    # basename match and point it at the SITE's base -- the same wrong mesh by
    # another route. Evidence-backed rewrite first; basename fallback after.
    _reroot_subpackages(export_dir, report)

    # Repair dangling bare res://<file> refs to their bundled assets/ copy.
    # A presentation scene generated in a DIFFERENT staging context (Lux apply
    # stages the building at res://<name>) can reference res://shell.glb while
    # the SAME asset was bundled to res://assets/shell.glb from the site scene's
    # absolute ref. The absolute-ref rewriter never sees a bare res:// path, so
    # reconcile every root-level res://<name> against what actually landed in
    # assets/. A ref that already points into assets/ can't match (it is not a
    # root-level "res://<name>"), so this is idempotent.
    assets_dir = export_dir / _ASSETS_DIR
    if assets_dir.is_dir():
        bundled = {a.name: f"{_ASSETS_DIR}/{a.name}"
                   for a in assets_dir.iterdir() if a.is_file()}
        for f in sorted(export_dir.rglob("*")):
            if not (f.is_file() and f.suffix in _TEXT_SUFFIXES):
                continue
            try:
                text = f.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            new = text
            for name, rel in bundled.items():
                new = re.sub(r'res://' + re.escape(name) + r'(?=["\'\s)])',
                             f'res://{rel}', new)
            if new != text:
                f.write_text(new, encoding="utf-8")
                report.repaired_bare_refs.append(
                    f.relative_to(export_dir).as_posix())
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
    """Synthesize mission.tscn instancing the level -- ONE of the two scenes.

    These are not peers, and instancing both put two copies of the same
    geometry at the same coordinates: the z-fighting this toolchain spent four
    commits removing. The presentation scene is the level once it has been
    themed and lit; site.tscn is what it is BUILT FROM, and after the themed
    site landed it is a dependency the presentation scene resolves by name
    rather than a second level standing beside it.

    So the presentation scene wins whenever it exists, and site.tscn is the
    entry when there is none. It still ships either way -- skipping it is
    what broke closure: `lux.applied.tscn: unresolved res://site.tscn`.

    "ONLY FOR A GRAYBOX EXPORT" WAS TOO NARROW, and this logic was already
    right for the case that sentence excluded. Since 0.36.0 an `art-unlit`
    export drops Lux's two files, so there is no presentation scene to
    prefer and the `elif` fires -- on a package that is neither graybox nor
    without an art pass. The entry it names is the THEMED site.tscn, which
    is correct and is the whole deliverable of that mode.

    The condition is deliberately about what EXISTS rather than about the
    mode. A mode test here would be a second place that decides what a
    package contains, and export.py already decided by not copying the
    file.
    """
    candidates: list[str] = []
    pres = export_dir / "presentation" / "lux.applied.tscn"
    site = export_dir / "site.tscn"
    if pres.exists():
        candidates.append("presentation/lux.applied.tscn")
    elif site.exists():
        candidates.append("site.tscn")
    # AN ENTRY THAT INSTANCES NOTHING IS NOT AN ENTRY.
    #
    # Measured 2026-08-15 on lot_demo_001. An art-unlit export held 180
    # files and 28.6 MB of themed geometry, no scene at the root that
    # placed any of it, and a mission.tscn whose _ready() only printed.
    # Everything agreed it was fine: export_closure_scan.json said
    # `ok: true` with `resource_count: 6`, because closure walks FROM
    # the entry and an entry that references nothing is trivially
    # closed. The emptier the package, the more certainly it passed.
    #
    # This knows nothing about export modes on purpose. A mode nobody
    # has written yet cannot ship hollow either.
    if not candidates:
        raise ExportContentError(
            f"{export_dir.name}: nothing for the entry scene to "
            f"instance -- no presentation/lux.applied.tscn and no "
            f"site.tscn. A package whose entry adds no children opens "
            f"to an empty level, and closure passes it because there "
            f"is nothing left to fail on.")
    lines = ""
    for i, rel in enumerate(candidates):
        lines += (f"\tvar packed_{i} := load('res://{rel}') as PackedScene\n"
                  f"\tif packed_{i} != null:\n"
                  f"\t\tadd_child(packed_{i}.instantiate())\n")
    (export_dir / "mission.tscn").write_text(
        _ENTRY_TEMPLATE.format(instances=lines), encoding="utf-8")
    report.entry_scene = "mission.tscn"
    report.entry_instances = list(candidates)
    return "mission.tscn"
