"""Pay the shader compile bill at load: ship the package's warm-up.

THE MEASUREMENT THIS EXISTS FOR. Cold run 9066's package, walked twice over
one six-leg route at 3 m/s (2026-09-21, Godot 4.7.stable, GL Compatibility,
NVIDIA RTX 2060), with BOTH shader caches cleared before the run:

    lap 1   mean 15.64 ms   2.43% over 16.7 ms   worst 8,564 ms
    lap 2   mean  7.16 ms   0.22% over 16.7 ms   worst    24 ms

Per leg, lap 1's worst frames were 8564, 4940, 2221, 226, 152, 178 ms. Draw
calls and object counts are the same on both laps, so nothing about what is
submitted changed -- only whether it had been drawn before.

WHY IT IS COMPILATION AND NOT SOMETHING ELSE. Four candidates were eliminated
by measurement rather than by argument:

  resource loading     the three renderer memory monitors and the resource
                       count are flat -- 0 KiB, 0 resources -- across EVERY
                       multi-second frame. The one frame in the run that does
                       move memory (+257 MiB of texture) costs 182 ms with the
                       caches warm, so that upload is real, bounded, and not
                       the stall.
  LOD / occluder /     built at import and at bake; the `.godot` cache and
  visibility build     `occluders.tscn` (301 nodes) were identical across
                       every run in the series.
  the probe's teleport the six legs sum to zero displacement, so the lap-end
                       teleport is a no-op, and it happens on both laps.
  draw submission      the cost the 9062 work found. Both laps submit the same
                       draw calls; lap 1 is 2.2x the mean and 360x the worst.

What DID move it was a directory the Godot project cannot see. The same
package, the same import cache, the same probe:

    both caches warm                         worst frame   172 ms
    Godot's user://shader_cache wiped                      376 ms
    that AND %LOCALAPPDATA%\\NVIDIA\\GLCache wiped        8,641 ms

`PIPELINE_COMPILATIONS_*` cannot settle this and did not: all five read 0 on
every frame of every run, which is what those monitors do under GL
Compatibility.

WHAT THIS SHIPS. `warmup.gd` at the package root and one `Node3D` in
`mission.tscn` carrying it. Ordinary scene data and one self-contained
script: no addon, no autoload, no editor plugin, so the package's standing
promise -- that it opens in somebody else's Godot project with none of our
tools present -- is unchanged. A recipient who does not want it deletes the
node, or sets `enabled` to false and keeps the stall to compare against.

WHERE THE COST GOES, and why. The warm-up turns a camera through six headings
at each of a set of stations before play starts, behind an opaque overlay,
with the 3D render scale at a tenth. The compile bill is conserved: it is paid
at load instead of in the first ninety seconds of play. That is the trade
shipped games make -- "compiling shaders 47%" -- and for a multiplayer client
a longer load beats one player's 8-second freeze taking the session's timing
with it.

WHY THE STATIONS. The obvious warm-up is to draw every material once, and it
is not enough. Measured on the same package, same cold conditions:

    every unique material, on a quad at spawn        8,564 -> 5,151 ms
    every unique mesh surface, on a speck at spawn   8,564 -> 5,151 ms
    one camera, six headings, at spawn               8,564 -> 4,395 ms
    six headings at each light cluster               8,564 -> 2,730 ms
    that plus a grid over the level's own extent     8,564 ->   155 ms

A GL Compatibility scene program is specialized on the LIGHTING CONTEXT of the
draw as well as on the material, and the renderable-light set is chosen by
distance to the CAMERA. So a prop warmed under the two lights that reach spawn
compiles a fresh program under the six that reach it where it stands, and the
warm-up has to stand where the player will stand. The residue the light
clusters left was the leg looking down the open street: a long-sightline
context no fixture makes, which is what the grid is for.

FOR SCALE, and because it is the number that decides whether consolidating
materials would have been the cheaper fix: that package holds 828 distinct
materials in the tree and they collapse to 17 distinct BaseMaterial3D feature
combinations. Godot generates one shader per combination, so the compile bill
is 17 programs, not 828, and there is no colour-only-variation defect here to
remove. The warm-up is the fix; consolidation would not have been.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

#: packages/exporting/warmup.py -> exporting -> packages -> <lf>
_LF_ROOT = Path(__file__).resolve().parents[2]

#: The script that runs. Source of truth lives in the repo and is checked by
#: `tools/gdcheck.py`; the package gets a byte copy.
WARMUP_SCRIPT = _LF_ROOT / "assets" / "godot" / "warmup.gd"

#: What lands in the package.
SCRIPT_NAME = "warmup.gd"
REPORT_NAME = "warmup.json"
SCHEMA = "lf.warmup.v1"

#: The node `mission.tscn` gains. Named, because the patch has to find it
#: again to know the scene is already wired and not wire it twice.
HOLDER_NODE = "Warmup"
_EXT_ID = "lf_warmup"

#: Guards the shipped script must carry. Checked by `audit` rather than
#: assumed, because each one is a way this can go wrong on somebody else's
#: machine and none of them is visible from the node in the scene.
REQUIRED_GUARDS = (
    # A headless run draws nothing, so the sweep would be pure cost. The QA
    # walkers run headless.
    'DisplayServer.get_name() == "headless"',
    # The editor instantiates scenes to show them.
    "Engine.is_editor_hint()",
    # A recipient's off switch.
    "enabled",
)


class WarmupError(RuntimeError):
    """The warm-up could not be shipped, or what shipped is not what this
    module writes. Never raised for a package with no geometry -- that is a
    legitimate package with nothing to warm."""


def script_text() -> str:
    """The script, read from the repo. Raises rather than shipping a stub."""
    if not WARMUP_SCRIPT.is_file():
        raise WarmupError(f"warm-up script missing: {WARMUP_SCRIPT}")
    text = WARMUP_SCRIPT.read_text(encoding="utf-8")
    missing = [g for g in REQUIRED_GUARDS if g not in text]
    if missing:
        raise WarmupError(
            "the warm-up script in this repo is missing guard(s) %s -- it "
            "would run in the editor, or headless, or with no way off"
            % ", ".join(repr(m) for m in missing))
    return text


#: `[gd_scene load_steps=N format=3]`, tolerant of spacing and of a scene
#: written without a `load_steps` at all (Godot omits it for a scene with no
#: resources, and `mission.tscn` has had one in every build since 0.36.0 --
#: but a reader that assumes it is a reader that breaks on the first one
#: that does not).
_HEADER = re.compile(r"^\[gd_scene(?P<attrs>[^\]]*)\]", re.M)
_LOAD_STEPS = re.compile(r"load_steps\s*=\s*(\d+)")


def _eol(path: Path) -> str:
    """The file's own line ending, derived rather than assumed.

    `write_text` translates `\\n` to `os.linesep`, so a rewrite on Windows
    silently converts an LF scene to CRLF and every line of the diff is the
    rewrite rather than the change. Read from bytes, because Python's text
    mode has already thrown the answer away by the time you can ask. A file
    with both endings is refused rather than guessed at -- that is the shape
    that put 81 bare LF lines into a CRLF CLAUDE.md.
    """
    raw = path.read_bytes()
    crlf = raw.count(b"\r\n")
    lf = raw.count(b"\n") - crlf
    if crlf and lf:
        raise WarmupError(
            f"{path.name} has {crlf} CRLF and {lf} LF line endings: a rewrite "
            "would have to pick one and neither is this file's")
    return "\r\n" if crlf else "\n"


def wire_into_scene(scene_path: Path) -> bool:
    """Put the warm-up node in the entry scene. True if it changed the file.

    Idempotent by the holder node's name: a package that already carries the
    node is left alone rather than given a second one, because the export is
    re-runnable and two warm-ups is two sweeps for one level.
    """
    scene_path = Path(scene_path)
    if not scene_path.is_file():
        raise WarmupError(f"no {scene_path.name} to wire the warm-up into")
    eol = _eol(scene_path)
    text = scene_path.read_text(encoding="utf-8")
    if f'[node name="{HOLDER_NODE}"' in text:
        return False

    header = _HEADER.search(text)
    if header is None:
        raise WarmupError(
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

    ext = (f'[ext_resource type="Script" path="res://{SCRIPT_NAME}" '
           f'id="{_EXT_ID}"]')
    lines = text.splitlines()
    # After the last ext_resource if there are any; otherwise straight after
    # the header, which is where Godot writes the first one. `mission.tscn`
    # carries its entry script as a sub_resource and has no ext_resource
    # block at all, so the second branch is the one that runs on every real
    # package -- it is not a fallback.
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
    lines.append(f'[node name="{HOLDER_NODE}" type="Node3D" parent="."]')
    lines.append(f'script = ExtResource("{_EXT_ID}")')
    scene_path.write_text(eol.join(lines) + eol, encoding="utf-8", newline="")
    return True


def audit(export_dir: Path) -> dict:
    """What the package ACTUALLY ships, read back off disk. Raises on a lie.

    Counts what a recipient will load, not what this module believes it
    wrote. The two have differed before in this repo -- that gap is where
    cold run 9065's occluders lived -- and a check written against the
    writer's own intentions is indistinguishable from one that passed.
    """
    export_dir = Path(export_dir)
    script = export_dir / SCRIPT_NAME
    entry = export_dir / "mission.tscn"
    if not entry.is_file():
        raise WarmupError(f"no mission.tscn in {export_dir}")
    text = entry.read_text(encoding="utf-8")

    nodes = text.count(f'[node name="{HOLDER_NODE}" type="Node3D"')
    refs = text.count(f'path="res://{SCRIPT_NAME}"')
    present = script.is_file()
    guards: list[str] = []
    if present:
        body = script.read_text(encoding="utf-8")
        guards = [g for g in REQUIRED_GUARDS if g in body]

    out = {"script_shipped": present, "warmup_nodes": nodes,
           "script_refs": refs, "guards_present": guards,
           "guards_required": list(REQUIRED_GUARDS)}

    if nodes == 0 and not present:
        # A package with no warm-up at all is consistent and is what every
        # build before 0.99.0 shipped. Reported, not raised.
        return out
    if nodes != 1:
        raise WarmupError(
            f"mission.tscn carries {nodes} `{HOLDER_NODE}` node(s), expected "
            "exactly 1 -- the package makes no single statement about warming")
    if not present:
        raise WarmupError(
            f"mission.tscn instances res://{SCRIPT_NAME} and the package does "
            "not ship it: the entry scene will fail to load")
    if refs != 1:
        raise WarmupError(
            f"mission.tscn names res://{SCRIPT_NAME} {refs} time(s), expected 1")
    if len(guards) != len(REQUIRED_GUARDS):
        missing = [g for g in REQUIRED_GUARDS if g not in guards]
        raise WarmupError(
            "the warm-up script that SHIPPED is missing guard(s) %s"
            % ", ".join(repr(m) for m in missing))
    return out


def emit(export_dir: Path, *, entry_scene: str = "mission.tscn") -> dict:
    """Copy the script in, wire the node, and write the report.

    Returns the report. Raises `WarmupError` when the warm-up cannot be
    shipped -- the caller decides whether that fails the export.
    """
    export_dir = Path(export_dir)
    # Validated as text, copied as BYTES. `write_text` translates endings to
    # the exporting machine's, so the same repo would ship two different
    # files from two machines and `audit` would be comparing a script with
    # itself under another spelling.
    script_text()
    (export_dir / SCRIPT_NAME).write_bytes(WARMUP_SCRIPT.read_bytes())
    wired = wire_into_scene(export_dir / entry_scene)
    report = {
        "schema": SCHEMA,
        "script": SCRIPT_NAME,
        "entry_scene": entry_scene,
        "node": HOLDER_NODE,
        "wired": wired,
        "guards": list(REQUIRED_GUARDS),
        # What the recipient can turn, and what each was measured at. A knob
        # with no recorded derivation is one nobody can turn and be believed.
        "knobs": {
            "station_spacing_m": {
                "default": 12.0,
                "measured": "12.0 took cold run 9066's package from an "
                            "8,564 ms worst frame to 155 ms; 24.0 (light "
                            "clusters only, no grid) left it at 2,730 ms",
            },
            "max_stations": {
                "default": 96,
                "measured": "9066's package needed 42. The cap bounds a load, "
                            "it is not a tuning",
            },
        },
    }
    report.update(audit(export_dir))
    (export_dir / REPORT_NAME).write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report
