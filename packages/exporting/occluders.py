"""Stop submitting what a wall is hiding: emit the package's occluders.

THE MEASUREMENT THIS EXISTS FOR. On cold run 9062's package, after Zoo
1.1.0's merge, standing inside the card shop at `interior_c` cost 4,635 draw
calls and 14.36 ms. Attributing that by hiding one top-level branch at a
time and reading the draw count back:

    b0  (the shop you are standing in)     266
    b1  (the country club across the road) 1,599  of 1,602 it owns
    b2  (the market hall)                  1,481  of 1,487 it owns
    street props                             719
    site surface                             566

Two buildings were being submitted essentially whole -- their interiors
included, every shelf and wall of a room no ray from that camera can reach.
Frustum culling cannot reject them, because they are in front of the camera.
Only the wall between can, and nothing in the package was telling the engine
there was a wall.

WHAT THIS SHIPS. `occluders.tscn`, a scene of nothing but
`OccluderInstance3D`, instanced by `mission.tscn` -- the scene
`run/main_scene` names, which is the only scene whose contents a recipient
ever loads. Ordinary scene data: no addon, no import script, no autoload, so
the package's standing promise -- that it opens in somebody else's Godot
project with none of our tools present -- is unchanged. A recipient whose
project has occlusion culling switched off gets inert nodes that cost
nothing rather than a broken level.

WHY THE ENTRY SCENE AND NOT `site.tscn`, WHICH IS WHERE 0.98.0 PUT IT.
Measured on cold run 9066's shipped `LF_club_block_005.portable-godot`,
2026-09-21, Godot 4.7.stable and 4.8-dev6 alike: 301 `OccluderInstance3D` in
the package, 0 in the tree `mission.tscn` builds. `site.tscn` is a Lux-less
sibling that nothing in that package references; the entry instances
`presentation/lux.applied.tscn` and the dressing layer, and the relit scene
pulls the three `lot/<archetype>/site.tscn` buildings directly rather than
through the root one. So every occluder shipped and none was ever loaded,
and every occlusion figure this repo published before 0.102.0 was measured
on `site.tscn` -- a scene the mission does not run.

`mission.tscn` and not `presentation/lux.applied.tscn`, for three reasons
and in this order:

  * It is the scene named by `run/main_scene`. Wiring anywhere else is a
    claim that the entry reaches that scene, and this feature has now been
    wrong about exactly that claim twice.
  * LF synthesizes it itself, on every export, in `localize.write_entry_scene`
    -- so it is the one scene in the package no upstream job regenerates
    under us. `lux.applied.tscn` is the `lux_apply` job's output, copied in.
  * It is the only wiring point that is correct in EVERY export mode. The
    entry instances the presentation scene when there is one and `site.tscn`
    when there is not (`art-unlit`, graybox), so a holder inside
    `lux.applied.tscn` would be reachable in one mode and absent in another
    -- which is this defect again, wearing a different mode's clothes.

The frames coincide and that was checked rather than assumed: the same bake
run against `res://site.tscn` and `res://mission.tscn` on that package
produced byte-identical `modules` lists, 301 occluders each. The geometry
the 0.98.0 scene carried was right; nothing loaded it.

THE DIVISION OF LABOUR. `assets/godot/bake_occluders.gd` measures, because
Godot is the only thing that has imported these GLBs and a module's filename
carries its width but not its height or thickness. This writes the scene,
because two things Godot's own packer did were wrong for a generated
package, both measured rather than assumed:

  * `ResourceSaver` names sub-resources non-deterministically -- two runs
    over one unchanged package produced two different files.
  * It wrote one `BoxOccluder3D` per occluder: 395 resources for 17 distinct
    sizes. Sharing them is the same rule as never expressing variation as a
    new material.

WHAT IS NOT OCCLUDED, and why each one is deliberate. Glass, because a
storefront shows the street and an occluder across it would cull what is
visibly through it. Doorways, windows and breaches, because the opening is
the module. Props of every kind -- lampposts, rails, bins, signs -- because
they are thin or porous and an occluder is a promise that nothing is
visible past it. The counts are in `occluders.json` so a skip is priced
rather than assumed.
"""
from __future__ import annotations

import json
import posixpath
import re
import shutil
import subprocess
from pathlib import Path

from packages.core.godot_project import OCCLUSION_KEY

#: The Godot script that measures the modules.
#:   packages/exporting/occluders.py -> exporting -> packages -> <lf>
_LF_ROOT = Path(__file__).resolve().parents[2]
BAKE_SCRIPT = _LF_ROOT / "assets" / "godot" / "bake_occluders.gd"

#: The Godot script that counts what the entry scene can REACH. The arbiter
#: for the question `reachable_occluders` below answers by parsing.
COUNT_SCRIPT = _LF_ROOT / "assets" / "godot" / "count_occluders.gd"
RUNTIME_SCHEMA = "lf.occluders.runtime.v1"

#: What lands in the package.
OCCLUDER_SCENE = "occluders.tscn"
REPORT_NAME = "occluders.json"
SCHEMA = "lf.occluders.v1"

#: The scene `run/main_scene` names, and the one the holder goes into. See
#: the module docstring: this is the only scene a recipient loads, and the
#: only one that is right in every export mode.
ENTRY_SCENE = "mission.tscn"

#: The node `mission.tscn` gains. Named, because the patch has to find it
#: again to know the scene has already been wired and not wire it twice.
HOLDER_NODE = "Occluders"
_EXT_ID = "lf_occluders"


class OccluderError(RuntimeError):
    """The bake could not be trusted. Never raised for 'no occluders' --
    that is a legitimate answer for a package with no buildings in it."""


#: Godot's import cache. Its PRESENCE is the precondition this module's bake
#: has, and its ABSENCE is what the shipped package must have.
CACHE_DIR = ".godot"


def ensure_imported(export_dir: Path, godot_executable, *,
                    timeout: int = 1200) -> bool:
    """Import the project if Godot has never imported it. True if it ran.

    THIS IS THE DEFECT COLD RUN 9065 SHIPPED. A Godot project cannot `load()`
    anything until its `.godot` cache exists -- sidecars are the import
    SETTINGS, not the imported resources -- and the export ran this bake
    straight after the sidecar pass, which deletes that cache one line before
    the bake needs it. Reproduced on the shipped
    `LF_club_block_004.portable-godot`, 2026-09-21, Godot 4.7.stable, by
    running the bake script against two clean copies of it:

        cache absent   `[occluders] FAILED: cannot load res://site.tscn`,
                       preceded by `Failed loading resource` on every GLB
                       and `referenced non-existent resource` on every PNG
        cache present  `measured=414 solid=414 porous=41 glass=35
                       filler=85 other=483`, exit 0

    Same package, same script, same engine; the only difference is whether
    `--import` had run. The 0.96.0 measurements passed because they were taken
    against packages a person had already imported by hand.

    Costs one import (18.3 s on that package) and nothing at all on the export
    path, where the sidecar pass has already left the cache in place -- this
    is then an `is_dir()` call. The caller is responsible for removing the
    cache before the package ships; `drop_cache` below is that.
    """
    export_dir = Path(export_dir)
    if (export_dir / CACHE_DIR).is_dir():
        return False
    if not godot_executable:
        raise OccluderError("no Godot executable: occluders cannot be measured")
    try:
        subprocess.run(
            [str(godot_executable), "--headless", "--path", str(export_dir),
             "--import"],
            capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError) as exc:
        raise OccluderError(f"import pass did not run: {exc}") from exc
    if not (export_dir / CACHE_DIR).is_dir():
        raise OccluderError(
            "import pass left no %s cache: the bake cannot load anything"
            % CACHE_DIR)
    return True


def drop_cache(export_dir: Path) -> bool:
    """Remove the import cache. True if there was one.

    The package ships sidecars and not the cache, deliberately: the cache is
    machine-specific and large (75.2 MB against 1.4 MB of sidecars on cold run
    9065's package). Kept here rather than in the sidecar pass so that the one
    step between them that NEEDS the cache can have it.
    """
    cache = Path(export_dir) / CACHE_DIR
    if not cache.is_dir():
        return False
    shutil.rmtree(cache, ignore_errors=True)
    return True


def measure(export_dir: Path, godot_executable, *,
            scene: str = f"res://{ENTRY_SCENE}",
            script: Path = BAKE_SCRIPT,
            timeout: int = 900) -> dict:
    """Run the bake and return its report.

    The report is the evidence. An exit code is not: the script writes
    ``ok: false`` with a reason for every failure it can name, and a report
    that does not parse, or whose schema is not the one this module knows,
    raises rather than reading as a package with no occluders in it.

    BAKED AGAINST THE ENTRY SCENE since 0.102.0, not against `site.tscn`.
    The bake reports every transform relative to the root of the scene it was
    handed, so baking one scene and wiring the result into another is a
    silent assertion that their frames coincide. They did on cold run 9066's
    package -- identical `modules` lists, checked -- and an assertion nothing
    checks is how this feature shipped broken twice. Measuring the scene the
    holder goes into makes the question unaskable.
    """
    export_dir = Path(export_dir)
    report_path = export_dir / REPORT_NAME
    if not godot_executable:
        raise OccluderError("no Godot executable: occluders cannot be measured")
    if not Path(script).is_file():
        raise OccluderError(f"bake script missing: {script}")
    ensure_imported(export_dir, godot_executable)
    bundled = export_dir / Path(script).name
    bundled.write_bytes(Path(script).read_bytes())
    try:
        subprocess.run(
            [str(godot_executable), "--headless", "--path", str(export_dir),
             "--script", f"res://{Path(script).name}", "--",
             scene, str(report_path)],
            capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError) as exc:
        raise OccluderError(f"bake did not run: {exc}") from exc
    finally:
        bundled.unlink(missing_ok=True)

    if not report_path.is_file():
        raise OccluderError("bake wrote no report")
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise OccluderError(f"report unreadable: {exc}") from exc
    if not isinstance(report, dict) or report.get("schema") != SCHEMA:
        raise OccluderError(
            f"report schema is {report.get('schema')!r}, not {SCHEMA!r}")
    if not report.get("ok"):
        raise OccluderError(f"bake failed: {report.get('error')}")
    if not isinstance(report.get("modules"), list):
        raise OccluderError("report carries no `modules` list")
    assert_no_capped_openings(report)
    return report


#: Mirrors `bake_occluders.HOLE_MIN_M2`. Derived there, and the derivation is
#: worth repeating because it is the whole reason this gate exists: the
#: smallest opening this pipeline cuts is a 1.10 x 1.30 m ladder hole
#: (1.43 m2), and the measured uncovered area of every module WITHOUT an
#: opening was 0.000000 m2 across 381 of them on cold run 9072's package.
HOLE_MIN_M2 = 0.25


def assert_no_capped_openings(report: dict) -> int:
    """Raise `OccluderError` if any emitted occluder covers an opening.

    WHAT THIS CAUGHT. Cold run 9072 shipped 17 floor and 17 ceiling occluders
    as full-room horizontal boxes -- `floor_main_floor` was 36 x 13 m, 2 cm
    thick, spanning a stair opening. Standing on that floor and looking down
    the stair, the basement was culled. The walker found it by turning the
    flag off; five gates had passed the package.

    An UNRECOGNISED SHAPE FAILS. A report whose rows carry no `uncovered_m2`
    came from a bake that cannot have taken this measurement, and reading its
    absence as "nothing over the limit" is the `or []` mistake CLAUDE.md
    records -- a checker that cannot find its field has learned nothing.
    """
    rows = report.get("modules")
    if not isinstance(rows, list):
        raise OccluderError("report carries no `modules` list to check")
    missing = [r for r in rows if "uncovered_m2" not in r]
    if missing:
        raise OccluderError(
            "%d of %d occluder row(s) carry no `uncovered_m2`: this bake did "
            "not measure whether its boxes cap an opening, and an unmeasured "
            "occluder must not ship as a measured one"
            % (len(missing), len(rows)))
    bad = [r for r in rows if float(r["uncovered_m2"]) > HOLE_MIN_M2]
    if bad:
        worst = sorted(bad, key=lambda r: -float(r["uncovered_m2"]))[:6]
        lines = ["OCCLUDER_CAPS_AN_OPENING: %d occluder(s) cover more hole "
                 "than %.2f m2" % (len(bad), HOLE_MIN_M2)]
        for r in worst:
            lines.append("    %-34s %-22s %8.2f m2 uncovered"
                         % (str(r.get("module"))[:34], str(r.get("node"))[:22],
                            float(r["uncovered_m2"])))
        lines.append("  an occluder over an opening hides whatever is visible "
                     "through it -- a stair, a mezzanine, a basement")
        raise OccluderError("\n".join(lines))
    return len(rows)


def _fmt(v) -> str:
    """A float as Godot writes one, and the same way every run.

    `repr` would emit `1.9600000381469727` for a float32 that came back
    through JSON, and a scene diff between two identical runs is a defect
    report nobody can read.
    """
    f = float(v)
    if f == int(f) and abs(f) < 1e15:
        return str(int(f))
    return f"{f:.4f}".rstrip("0").rstrip(".")


def scene_text(report: dict) -> str:
    """`occluders.tscn` for a bake report -- deterministic, shapes shared.

    Sub-resource ids are `BoxOccluder3D_<n>` over the sizes in first-seen
    order, so the file is a function of the report and of nothing else.
    """
    modules = report.get("modules") or []
    shapes: dict[tuple, int] = {}
    for m in modules:
        key = tuple(_fmt(x) for x in m["size"])
        if key not in shapes:
            shapes[key] = len(shapes)

    out = [f"[gd_scene load_steps={len(shapes) + 1} format=3]", ""]
    for key, idx in shapes.items():
        out.append(f'[sub_resource type="BoxOccluder3D" id="BoxOccluder3D_{idx}"]')
        out.append(f"size = Vector3({key[0]}, {key[1]}, {key[2]})")
        out.append("")
    out.append(f'[node name="{HOLDER_NODE}" type="Node3D"]')
    out.append("")
    for i, m in enumerate(modules):
        key = tuple(_fmt(x) for x in m["size"])
        b = [_fmt(x) for x in m["basis"]]
        o = [_fmt(x) for x in m["origin"]]
        out.append(f'[node name="occ_{i:04d}" type="OccluderInstance3D" '
                   f'parent="."]')
        out.append("transform = Transform3D("
                   + ", ".join(b + o) + ")")
        out.append(f'occluder = SubResource("BoxOccluder3D_{shapes[key]}")')
        out.append("")
    return "\n".join(out)


#: `[gd_scene load_steps=N format=3]`, tolerant of spacing and of a scene
#: written with no `load_steps` at all -- Godot omits it for a scene with no
#: resources, and `mission.tscn` is written with one only because it carries
#: its entry script as a sub_resource.
_HEADER = re.compile(r"^\[gd_scene(?P<attrs>[^\]]*)\]", re.M)
_LOAD_STEPS = re.compile(r"load_steps\s*=\s*(\d+)")


def _eol(path: Path) -> str:
    """The file's own line ending, derived rather than assumed.

    `write_text` translates `\\n` to `os.linesep`, so a rewrite on Windows
    silently converts an LF scene to CRLF and every line of the diff is the
    rewrite rather than the change. Read from bytes, because Python's text
    mode has already thrown the answer away by the time you can ask. A file
    with both endings is refused rather than guessed at. Same helper, same
    reasoning, as `warmup._eol`.
    """
    raw = path.read_bytes()
    crlf = raw.count(b"\r\n")
    lf = raw.count(b"\n") - crlf
    if crlf and lf:
        raise OccluderError(
            f"{path.name} has {crlf} CRLF and {lf} LF line endings: a rewrite "
            "would have to pick one and neither is this file's")
    return "\r\n" if crlf else "\n"


def wire_into_scene(scene_path: Path) -> bool:
    """Instance `occluders.tscn` from the ENTRY scene. True if it changed it.

    Idempotent by the holder node's name: a package that already carries the
    branch is left alone rather than given a second one, because the export
    is re-runnable and two sets of occluders is twice the raster cost for
    nothing.

    THIS USED TO REFUSE A SCENE WITH NO `ext_resource` BLOCK, on the reasoning
    that a scene with none "is not one of ours". `mission.tscn` has none --
    it carries its entry script as a `sub_resource` and instances its content
    by `load()` from `_ready()` -- so that refusal was aimed squarely at the
    one scene this now has to wire. It is the same shape `warmup.wire_into_scene`
    already handles, and for the same file, so the handling is the same:
    after the last `ext_resource` when there are any, otherwise straight after
    the `[gd_scene]` header, which is where Godot writes the first one. A file
    with no header at all is still refused; that really is not a scene.
    """
    scene_path = Path(scene_path)
    if not scene_path.is_file():
        raise OccluderError(f"no {scene_path.name} to wire the occluders into")
    eol = _eol(scene_path)
    text = scene_path.read_text(encoding="utf-8")
    if f'[node name="{HOLDER_NODE}" parent="."' in text:
        return False

    header = _HEADER.search(text)
    if header is None:
        raise OccluderError(
            f"{scene_path.name} has no [gd_scene] header: it is not a scene "
            "this can wire safely")

    # load_steps counts the resources the loader must build, and an
    # ext_resource is one. Godot recovers from a low count, but a scene that
    # lies about its own size is a defect somebody else will have to read.
    attrs = header.group("attrs")
    steps = _LOAD_STEPS.search(attrs)
    if steps is None:
        new_attrs = attrs.rstrip() + " load_steps=2"
    else:
        new_attrs = attrs[:steps.start()] + (
            "load_steps=%d" % (int(steps.group(1)) + 1)) + attrs[steps.end():]
    text = text[:header.start()] + "[gd_scene" + new_attrs + "]" \
        + text[header.end():]

    ext = (f'[ext_resource type="PackedScene" path="res://{OCCLUDER_SCENE}" '
           f'id="{_EXT_ID}"]')
    lines = text.splitlines()
    last_ext = max((i for i, ln in enumerate(lines)
                    if ln.startswith("[ext_resource ")), default=-1)
    if last_ext < 0:
        head = max((i for i, ln in enumerate(lines)
                    if ln.startswith("[gd_scene")), default=-1)
        lines.insert(head + 1, "")
        lines.insert(head + 2, ext)
    else:
        lines.insert(last_ext + 1, ext)

    lines.append("")
    lines.append(f'[node name="{HOLDER_NODE}" parent="." '
                 f'instance=ExtResource("{_EXT_ID}")]')
    scene_path.write_text(eol.join(lines) + eol, encoding="utf-8", newline="")
    return True


#: `occlusion_culling/use_occlusion_culling=true`, tolerant of spacing.
_OCC_SETTING = re.compile(
    r"^\s*" + re.escape(OCCLUSION_KEY) + r"\s*=\s*(\S+)\s*$", re.M)


class OccluderDisagreement(RuntimeError):
    """The culling flag, the occluders in the package and the occluders the
    entry scene can reach do not all agree."""


#: `run/main_scene="res://x.tscn"`. The one setting that says which scene a
#: recipient loads; everything below is measured from it.
_MAIN_SCENE = re.compile(r'^\s*run/main_scene\s*=\s*"([^"]+)"\s*$', re.M)

#: An `[ext_resource ...]` line, and then its attributes. Matched in two
#: steps rather than one because attribute ORDER is Godot's business and a
#: single pattern that pins it is a checker that stops working on a version
#: nobody has shipped yet.
_EXT_LINE = re.compile(r"^\[ext_resource\b([^\]]*)\]", re.M)
_ATTR = re.compile(r'(\w+)="([^"]*)"')

#: `instance=ExtResource("id")` -- a DECLARED PackedScene is not a loaded one.
#: The distinction is the whole point: `occluders.tscn` was declared in
#: `site.tscn` and `site.tscn` was never instanced by anything.
_INSTANCED = re.compile(r'\binstance=ExtResource\("([^"]+)"\)')

#: `load('res://x')` / `preload("res://x")`, which is how `mission.tscn`
#: instances its content -- its entry script is a `sub_resource` GDScript and
#: the scenes it adds appear nowhere in the scene's own resource block. Read
#: off the real file: cold run 9066's `mission.tscn` names
#: `res://presentation/lux.applied.tscn` and `res://club_block_005_dressing.tscn`
#: this way and no other.
_LOADED = re.compile(r"\b(?:pre)?load\(\s*['\"]([^'\"]+)['\"]\s*\)")


def _resolve(base_dir: str, path: str):
    """A scene reference as a package-relative path, or None if unplaceable.

    Godot resolves a `.tscn` reference without a `res://` prefix relative to
    the scene that carries it, and cold run 9066's `site.tscn` carries both
    spellings -- `lot/strip_club_a02/site.tscn` beside
    `res://occluders.tscn`. A `uid://` cannot be placed from text at all and
    says so rather than being dropped.
    """
    if path.startswith("uid://"):
        return None
    if path.startswith("res://"):
        rel = path[len("res://"):]
    elif base_dir:
        rel = posixpath.join(base_dir, path)
    else:
        rel = path
    rel = posixpath.normpath(rel.replace("\\", "/"))
    if rel.startswith("..") or rel.startswith("/") or ":" in rel.split("/")[0]:
        return None
    return rel


def reachable_occluders(export_dir: Path) -> dict:
    """Walk from `run/main_scene` DOWN, the way the runtime does, and count.

    THE RULE THIS ENFORCES, and it is not the rule 0.98.0's audit enforced.
    That one asked whether `OccluderInstance3D` nodes exist ANYWHERE in the
    package -- `rglob("*.tscn")` -- and cold run 9066's package satisfied it
    with 301 of them in `occluders.tscn`, instanced from a `site.tscn` that
    `mission.tscn` never names. The question a recipient's frame time asks is
    whether the scene the engine LOADS can reach them, so that is the
    question here: follow the references, from the entry, transitively.

    Two kinds of edge, because the package uses two:

      * `[ext_resource type="PackedScene"]` that some node actually
        INSTANCES. A declared-but-uninstanced PackedScene is exactly the
        thing being ruled out, so declaring is not reaching.
      * `load()`/`preload()` of a `res://` path from an embedded script,
        which is the ONLY way `mission.tscn` reaches its content.

    Only `.tscn` is followed. A `.glb` cannot carry an `OccluderInstance3D`
    -- glTF has no such node -- and this module never writes occluders into
    anything but a `.tscn`. A reference to a script is not followed either;
    if a future package ever hides occluders behind a `.gd`, the RUNTIME
    count (`assets/godot/count_occluders.gd`) will disagree with this one and
    the export will fail rather than guess, which is the point of running
    both.

    A reference this cannot place, and one that names a file the package does
    not contain, is RECORDED rather than raised on: unresolved resources are
    `closure.scan_closure`'s verdict to give, and two gates shouting about
    one defect is how a fix looks like it did not work.
    """
    export_dir = Path(export_dir)
    proj = export_dir / "project.godot"
    if not proj.is_file():
        raise OccluderDisagreement(f"no project.godot in {export_dir}")
    hits = _MAIN_SCENE.findall(proj.read_text(encoding="utf-8"))
    if len(hits) != 1:
        raise OccluderDisagreement(
            f"project.godot carries {len(hits)} `run/main_scene` lines, "
            "expected exactly 1 -- the package does not say which scene it "
            "runs, so nothing can be said about what that scene reaches")
    main = _resolve("", hits[0])
    if main is None:
        raise OccluderDisagreement(
            f"run/main_scene is {hits[0]!r}, which this cannot place in the "
            "package -- the reachable set cannot be walked from it")
    if not (export_dir / main).is_file():
        raise OccluderDisagreement(
            f"run/main_scene names res://{main} and the package does not "
            "contain it: the recipient opens to a load error")

    order: list[str] = []
    seen: set[str] = set()
    by_scene: dict[str, int] = {}
    unresolved: list[str] = []
    unplaceable: list[str] = []
    followed_non_tscn = 0
    queue = [main]
    while queue:
        rel = queue.pop(0)
        if rel in seen:
            continue
        seen.add(rel)
        order.append(rel)
        try:
            text = (export_dir / rel).read_text(encoding="utf-8",
                                                errors="replace")
        except OSError as exc:
            raise OccluderDisagreement(
                f"res://{rel} is reachable from the entry scene and could not "
                f"be read: {exc}") from exc
        n = text.count('type="OccluderInstance3D"')
        if n:
            by_scene[rel] = n
        base = posixpath.dirname(rel)

        packed: dict[str, str] = {}
        for body in _EXT_LINE.findall(text):
            attrs = dict(_ATTR.findall(body))
            if (attrs.get("type") == "PackedScene"
                    and "id" in attrs and "path" in attrs):
                packed[attrs["id"]] = attrs["path"]
        refs = [packed[i] for i in _INSTANCED.findall(text) if i in packed]
        refs += _LOADED.findall(text)

        for raw in refs:
            target = _resolve(base, raw)
            if target is None:
                unplaceable.append(f"{rel} -> {raw}")
                continue
            if not target.endswith(".tscn"):
                followed_non_tscn += 1
                continue
            if not (export_dir / target).is_file():
                unresolved.append(f"{rel} -> res://{target}")
                continue
            queue.append(target)

    # WHAT SHIPS AND IS NEVER LOADED. Reported, not acted on. On cold run
    # 9066's package this is `site.tscn` -- 312 KB of themed assembly that
    # the entry does not name, because `lux.applied.tscn` instances the three
    # `lot/<archetype>/site.tscn` buildings directly. LF 0.94.0 dropped an
    # orphan `site_base.glb` on exactly this reasoning, and it would be wrong
    # to drop this one by the same reflex: a SINGLE-SHELL mission's
    # presentation scene DOES name `res://site.tscn`, measured, and deleting
    # it broke closure with `lux.applied.tscn: unresolved res://site.tscn`.
    # So the walk says which scenes are orphans in THIS package and the
    # decision stays with whoever reads it.
    shipped_scenes = sorted(
        p.relative_to(export_dir).as_posix()
        for p in export_dir.rglob("*.tscn") if CACHE_DIR not in p.parts)
    unreachable = [s for s in shipped_scenes if s not in seen]

    return {
        "main_scene": main,
        "scenes_walked": order,
        "unreachable_scenes": unreachable,
        "occluder_nodes": sum(by_scene.values()),
        "occluder_nodes_by_scene": by_scene,
        "unresolved_scene_refs": sorted(set(unresolved)),
        "unplaceable_refs": sorted(set(unplaceable)),
        "non_scene_refs_skipped": followed_non_tscn,
    }


def _runtime_verdict(export_dir: Path):
    """The Godot count `emit` recorded, or None if this package has none.

    Read out of `occluders.json` under a key this module writes, and an
    unrecognised shape reads as ABSENT rather than as zero. A missing key
    that becomes a zero is how a `--verify` once printed "closure verdict
    clean" over a broken export.
    """
    report = export_dir / REPORT_NAME
    if not report.is_file():
        return None
    try:
        data = json.loads(report.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    rt = data.get("runtime")
    if not isinstance(rt, dict) or rt.get("schema") != RUNTIME_SCHEMA:
        return None
    if not rt.get("ok") or not isinstance(rt.get("occluder_nodes"), int):
        return None
    return rt


def audit(export_dir: Path) -> dict:
    """What the package ACTUALLY ships, read back off disk. Raises on a lie.

    THE STATE 0.98.0 EXISTED TO MAKE IMPOSSIBLE is the one cold run 9065
    shipped: `use_occlusion_culling=true` and zero `OccluderInstance3D`
    anywhere in the package. The export printed a warning, exited 0, and the
    package went out with the culler's per-frame cost and nothing for it to
    reject -- the flag on, the culling absent, which is worse than neither.

    THE STATE 0.98.0 STILL PASSED, and this is why the rule changed. Cold run
    9066's package: flag on, 301 nodes in `occluders.tscn`, and the scene
    `run/main_scene` names reaching NONE of them. Counting nodes in the
    shipped scenes answered "are they in the box" when the question was "will
    the engine load them", and a check that cannot fail on the defect it was
    written for is indistinguishable from one that passed. So the count that
    decides is now the REACHABLE one, walked from the entry scene down.

    The other direction is a defect too and is checked with the same breath:
    occluders in the package with the culler off is a scene of software
    rasteriser input that the engine will never consult. And a node that
    ships but is unreachable is its own finding, reported separately, because
    the residue after a fix should be diagnostic rather than a surprise.

    `occluders.json` is read for two things only: whether the bake said it
    succeeded, and the RUNTIME count if one was taken. The runtime count
    never decides on its own either -- when the two instruments disagree one
    of them is wrong, and that is a build failure rather than a choice.
    """
    export_dir = Path(export_dir)
    proj = export_dir / "project.godot"
    if not proj.is_file():
        raise OccluderDisagreement(f"no project.godot in {export_dir}")
    hits = _OCC_SETTING.findall(proj.read_text(encoding="utf-8"))
    if len(hits) != 1:
        raise OccluderDisagreement(
            f"project.godot carries {len(hits)} `{OCCLUSION_KEY}` lines, "
            "expected exactly 1 -- the package makes no single statement "
            "about occlusion culling")
    flag = hits[0].strip().lower() == "true"

    shipped = 0
    scenes = 0
    for tscn in sorted(export_dir.rglob("*.tscn")):
        if CACHE_DIR in tscn.parts:
            continue
        try:
            text = tscn.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        n = text.count('type="OccluderInstance3D"')
        if n:
            scenes += 1
        shipped += n

    walk = reachable_occluders(export_dir)
    reachable = walk["occluder_nodes"]

    report_ok = None
    report = export_dir / REPORT_NAME
    if report.is_file():
        try:
            report_ok = bool(json.loads(
                report.read_text(encoding="utf-8")).get("ok"))
        except (OSError, ValueError):
            report_ok = None
    runtime = _runtime_verdict(export_dir)

    out = {"use_occlusion_culling": flag,
           # `occluder_nodes` means REACHABLE from 0.102.0 on. The name is
           # kept because it is what every caller prints, and what it used to
           # mean is the defect; `occluder_nodes_in_package` is the old sense,
           # reported beside it so the gap is visible rather than implied.
           "occluder_nodes": reachable,
           "occluder_nodes_in_package": shipped,
           "scenes_with_occluders": scenes,
           "main_scene": walk["main_scene"],
           "scenes_walked": len(walk["scenes_walked"]),
           "occluder_scenes_reached": sorted(walk["occluder_nodes_by_scene"]),
           "unreachable_scenes": walk["unreachable_scenes"],
           "runtime_occluder_nodes": (None if runtime is None
                                      else runtime["occluder_nodes"]),
           "bake_reported_ok": report_ok}

    if runtime is not None and runtime["occluder_nodes"] != reachable:
        raise OccluderDisagreement(
            "two instruments disagree about what res://%s reaches: Godot "
            "counted %d OccluderInstance3D in the instantiated tree, this "
            "walk of the scene text found %d. One of them is wrong and "
            "neither is evidence until that is settled."
            % (walk["main_scene"], runtime["occluder_nodes"], reachable))
    if flag and reachable == 0:
        if shipped:
            raise OccluderDisagreement(
                "use_occlusion_culling=true, %d OccluderInstance3D node(s) in "
                "the package, and 0 reachable from res://%s. They ship and "
                "nothing loads them: the culler is switched on with nothing "
                "to cull. Walked %d scene(s) from the entry. This is cold run "
                "9066's state -- occluders wired into a scene the mission "
                "does not run."
                % (shipped, walk["main_scene"], len(walk["scenes_walked"])))
        raise OccluderDisagreement(
            "use_occlusion_culling=true and 0 OccluderInstance3D nodes in the "
            "package: the culler is switched on with nothing to cull. "
            f"occluders.json ok={report_ok}. This is cold run 9065's state.")
    if shipped and not flag:
        raise OccluderDisagreement(
            f"{shipped} OccluderInstance3D node(s) in the package and "
            "use_occlusion_culling is not true: they will never be consulted.")
    if shipped != reachable:
        raise OccluderDisagreement(
            "%d OccluderInstance3D node(s) ship and %d are reachable from "
            "res://%s: %d node(s) are in the package and in no scene the "
            "engine loads. An occluder nothing loads is bytes on a recipient's "
            "disk; an occluder loaded twice is twice the raster cost."
            % (shipped, reachable, walk["main_scene"], abs(shipped - reachable)))
    return out


def count_at_runtime(export_dir: Path, godot_executable, *,
                     script: Path = COUNT_SCRIPT,
                     timeout: int = 900) -> dict:
    """Ask Godot what the entry scene's tree actually contains.

    The arbiter for `reachable_occluders`. That one parses scene text, needs
    no Godot, and runs on every export; this one loads `run/main_scene` the
    way a recipient does and counts the nodes in the tree. Run while the
    import cache the bake needed is still in place -- see `emit` -- so it
    costs one headless launch and no second import.

    Same contract as `measure`: the REPORT is the evidence, an exit code is
    not, and a schema this does not recognise raises rather than reading as
    an entry scene with no occluders under it.
    """
    export_dir = Path(export_dir)
    if not godot_executable:
        raise OccluderError("no Godot executable: the runtime count cannot "
                            "be taken")
    if not Path(script).is_file():
        raise OccluderError(f"count script missing: {script}")
    ensure_imported(export_dir, godot_executable)
    bundled = export_dir / Path(script).name
    # Written into the package because Godot needs a res:// path for the
    # script, and removed in `finally` because neither it nor its report is
    # part of the deliverable.
    out_path = export_dir / "occluders_runtime.json"
    bundled.write_bytes(Path(script).read_bytes())
    try:
        subprocess.run(
            [str(godot_executable), "--headless", "--path", str(export_dir),
             "--script", f"res://{Path(script).name}", "--", str(out_path)],
            capture_output=True, text=True, timeout=timeout)
        if not out_path.is_file():
            raise OccluderError("the runtime count wrote no report")
        try:
            rt = json.loads(out_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise OccluderError(f"runtime report unreadable: {exc}") from exc
    except (OSError, subprocess.SubprocessError) as exc:
        raise OccluderError(f"the runtime count did not run: {exc}") from exc
    finally:
        bundled.unlink(missing_ok=True)
        out_path.unlink(missing_ok=True)
        (export_dir / (Path(script).name + ".uid")).unlink(missing_ok=True)

    if not isinstance(rt, dict) or rt.get("schema") != RUNTIME_SCHEMA:
        raise OccluderError(
            f"runtime report schema is {rt.get('schema')!r}, "
            f"not {RUNTIME_SCHEMA!r}")
    if not rt.get("ok"):
        raise OccluderError(f"the runtime count failed: {rt.get('error')}")
    if not isinstance(rt.get("occluder_nodes"), int):
        raise OccluderError("runtime report carries no `occluder_nodes` count")
    return rt


def emit(export_dir: Path, godot_executable, *,
         entry_scene: str = ENTRY_SCENE) -> dict:
    """Measure, write `occluders.tscn`, wire it into the ENTRY scene, and
    confirm with Godot that the entry scene's tree really holds them.

    Returns the report with `occluder_scene`, `wired` and `runtime` added.
    Raises `OccluderError` when the bake cannot be trusted -- the caller
    decides whether that fails the export or is reported and survived.

    `scene_name` was the old keyword and it meant `site.tscn`. It is gone
    rather than kept as an alias: a caller that still passes it is a caller
    that believes the occluders go somewhere they no longer go, and failing
    loudly is cheaper than wiring a package's occluders into a scene nothing
    runs for a third time.
    """
    export_dir = Path(export_dir)
    entry = export_dir / entry_scene
    if not entry.is_file():
        raise OccluderError(
            f"no {entry_scene} in {export_dir}: the entry scene is written by "
            "localize.write_entry_scene and has to exist before the occluders "
            "can be wired into anything")
    report = measure(export_dir, godot_executable,
                     scene=f"res://{entry_scene}")
    report["entry_scene"] = entry_scene
    if int(report.get("occluders") or 0) == 0:
        # NOTHING TO HIDE IS NOT A FAILURE, and it is not a reason to ship an
        # empty branch either. A package with no solid modules in it gets no
        # `occluders.tscn` and no holder node: an instanced scene of nothing
        # is one more node for the tree to carry and one more file in the
        # resource manifest, and the export then writes the culling flag off
        # to match. The bake SUCCEEDED and the report says so.
        report["occluder_scene"] = None
        report["wired"] = False
        report["runtime"] = None
    else:
        (export_dir / OCCLUDER_SCENE).write_text(
            scene_text(report), encoding="utf-8")
        report["occluder_scene"] = OCCLUDER_SCENE
        report["wired"] = wire_into_scene(entry)
        # THE CONFIRMATION, and it is the whole point of 0.102.0. Taken here
        # rather than in `audit` for one reason: the import cache the bake
        # needed is still in place, so this is one headless launch instead of
        # one launch plus an 18 s re-import. The export drops the cache a few
        # lines later and `audit` then runs the text walk against the files
        # that are about to be zipped.
        runtime = count_at_runtime(export_dir, godot_executable)
        report["runtime"] = runtime
        if runtime["occluder_nodes"] == 0:
            raise OccluderError(
                "%d occluder(s) were written to %s and wired into %s, and "
                "Godot loading res://%s found %d in the tree. The package "
                "would ship the culler switched on with nothing to cull -- "
                "cold run 9066's defect, caught this time."
                % (report["occluders"], OCCLUDER_SCENE, entry_scene,
                   entry_scene, runtime["occluder_nodes"]))
    (export_dir / REPORT_NAME).write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report
