"""Price occlusion culling on the scene a package actually runs.

THE HARNESS FOR `tools/occlusion_ab.gd`. That script measures one package;
this builds the arms, runs the rounds, and prints the table -- so a figure
this repo publishes about occlusion can be reproduced by somebody who has
the package and this file, rather than by somebody who has the same four
commands in their scrollback.

THE ARMS, and each one exists to answer a question the others cannot.

    on        the package as exported: 301 occluders reachable from
              `run/main_scene`, `use_occlusion_culling=true`
    off       byte-identical except the flag. The occluder NODES are still
              there and the engine is told not to consult them, so the only
              variable is the culler.
    nocc_on   the holder removed from `mission.tscn` -- nothing to cull --
              with the flag ON. Cold run 9065's state.
    nocc_off  the same, flag off.

`on` against `off` is the saving. `nocc_on` against `nocc_off` is the COST,
and it needs its own pair because no station isolates it: the most open view
in the set still saves 76 draw calls, so its frame-time difference is a net
of a cost and a saving and neither can be read off it. The two `nocc` arms
must report IDENTICAL draw calls at every station, and this refuses to
tabulate them if they do not -- a cost arm whose frames differ is not
measuring a cost.

WHAT IT REFUSES. Rows that do not all name the same `main_scene`; a run
whose `warmup_finished` is false (the warm-up turns the culler off and drops
the viewport to a tenth scale while it sweeps, so such a run is not the
configuration that shipped); and any station whose `viewport_occlusion`
disagrees with what its package asked for.

A window is opened on purpose: headless draws nothing and cannot answer a
frame-time question. Every run quits itself.

    python tools/occlusion_ab_run.py <package_dir> <work_dir> [--godot EXE]
                                     [--rounds 3] [--occluders N]
"""
from __future__ import annotations

import argparse
import json
import shutil
import statistics as st
import subprocess
import sys
from pathlib import Path

_LF_ROOT = Path(__file__).resolve().parents[1]
if str(_LF_ROOT) not in sys.path:
    sys.path.insert(0, str(_LF_ROOT))

from packages.core.godot_project import (OCCLUSION_KEY,  # noqa: E402
                                         set_occlusion_culling)
from packages.exporting.occluders import (CACHE_DIR,  # noqa: E402
                                          OCCLUDER_SCENE)

PROBE = _LF_ROOT / "tools" / "occlusion_ab.gd"
COUNT = _LF_ROOT / "assets" / "godot" / "count_occluders.gd"

#: The four arms, as (name, flag, strip_holder).
ARMS = (("on", True, False), ("off", False, False),
        ("nocc_on", True, True), ("nocc_off", False, True))
COST_PAIR = ("nocc_on", "nocc_off")
SAVING_PAIR = ("on", "off")


def _run(argv, timeout: int, echo=("STATION", "SETTING", "MAIN_SCENE",
                                   "OCCLUDER_NODES", "BOUNDS", "WARMUP",
                                   "[occ-runtime]", "[warmup]")):
    p = subprocess.run([str(a) for a in argv], capture_output=True, text=True,
                       timeout=timeout)
    for line in (p.stdout or "").splitlines():
        if line.startswith(tuple(echo)):
            print("   ", line, flush=True)
    if p.returncode != 0:
        print("    rc=%d" % p.returncode, flush=True)
        for line in (p.stderr or "").strip().splitlines()[-6:]:
            print("    !", line, flush=True)
    return p


def _strip_holder(pkg: Path) -> None:
    """Take the occluder branch out of the entry scene, leaving the frame.

    The `.tscn` stays on disk and is simply not instanced, so the two `nocc`
    arms differ from the two measured arms in the tree and in nothing on
    disk. Refuses unless it removed exactly the two lines
    `occluders.wire_into_scene` adds.
    """
    p = pkg / "mission.tscn"
    raw = p.read_bytes()
    eol = b"\r\n" if raw.count(b"\r\n") else b"\n"
    keep, dropped, eat_blank = [], 0, False
    for ln in raw.split(eol):
        s = ln.decode("utf-8", "replace")
        if s.startswith("[ext_resource ") and OCCLUDER_SCENE in s:
            dropped += 1
            continue
        if s.startswith('[node name="Occluders"'):
            dropped += 1
            eat_blank = True
            continue
        if eat_blank and not s.strip():
            eat_blank = False
            continue
        eat_blank = False
        keep.append(ln)
    if dropped != 2:
        raise SystemExit("%s: removed %d line(s) naming %s, expected 2"
                         % (pkg.name, dropped, OCCLUDER_SCENE))
    text = eol.join(keep).decode("utf-8")
    if OCCLUDER_SCENE in text:
        raise SystemExit("%s: mission.tscn still names %s"
                         % (pkg.name, OCCLUDER_SCENE))
    p.write_bytes(eol.join(keep))


def _make_arm(src: Path, work: Path, name: str, flag: bool, strip: bool,
              godot: Path, occluders: int) -> Path:
    dst = work / f"pkg_{name}"
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)
    if strip:
        _strip_holder(dst)
    proj = dst / "project.godot"
    # The repo's own writer, which spells the key without the `rendering/`
    # half -- that is the ini section -- and refuses a file with anything but
    # exactly one line to rewrite. It takes a COUNT, because the flag is a
    # function of how many occluders shipped.
    proj.write_text(
        set_occlusion_culling(proj.read_text(encoding="utf-8"),
                              occluders if flag else 0),
        encoding="utf-8", newline="")
    print("%-9s %s" % (name, [ln.strip() for ln in
                              proj.read_text(encoding="utf-8").splitlines()
                              if OCCLUSION_KEY in ln]), flush=True)
    # The package ships sidecars and no import cache; nothing loads until
    # Godot has imported once.
    _run([godot, "--headless", "--path", dst, "--import"], 1800)
    if not (dst / CACHE_DIR).is_dir():
        raise SystemExit(f"{name}: --import left no {CACHE_DIR}")
    shutil.copyfile(PROBE, dst / PROBE.name)
    return dst


def _load(out: Path, arms, rounds):
    runs = {}
    for arm in arms:
        for r in range(1, rounds + 1):
            f = out / f"{arm}_r{r}.json"
            if not f.is_file():
                raise SystemExit(f"missing {f}")
            runs[(arm, r)] = json.loads(f.read_text(encoding="utf-8"))
    scenes = {d["main_scene"] for d in runs.values()}
    if len(scenes) != 1:
        raise SystemExit(f"rows describe {len(scenes)} scenes: {scenes}")
    for k, d in runs.items():
        if not d.get("warmup_finished"):
            raise SystemExit(
                f"{k}: the warm-up had not finished -- the culler was off and "
                "the viewport at a tenth scale for part of this run")
        for row in d["stations"]:
            if bool(row["viewport_occlusion"]) != bool(d["occlusion_setting"]):
                raise SystemExit(
                    "%s %s: the viewport had occlusion=%s while the package "
                    "asked for %s" % (k, row["station"],
                                      row["viewport_occlusion"],
                                      d["occlusion_setting"]))
    return runs, scenes.pop()


def _series(runs, arm, station, col, rounds):
    return [row[col] for r in range(1, rounds + 1)
            for row in runs[(arm, r)]["stations"] if row["station"] == station]


def _table(runs, pair, rounds, title) -> None:
    a, b = pair
    stations = [r["station"] for r in runs[(a, 1)]["stations"]]
    print()
    print(title)
    print("%-14s %8s %8s %7s %7s %10s %10s %8s %8s %8s %8s"
          % ("station", f"draws {a}", f"draws {b}", f"obj {a}", f"obj {b}",
             f"prims {a}", f"prims {b}", f"ms {a}", f"ms {b}",
             f"cpu {a}", f"cpu {b}"))
    for s in stations:
        d_a = _series(runs, a, s, "draw_calls", rounds)
        d_b = _series(runs, b, s, "draw_calls", rounds)
        print("%-14s %8d %8d %7d %7d %10d %10d %8.2f %8.2f %8.2f %8.2f"
              % (s, st.median(d_a), st.median(d_b),
                 st.median(_series(runs, a, s, "objects", rounds)),
                 st.median(_series(runs, b, s, "objects", rounds)),
                 st.median(_series(runs, a, s, "primitives", rounds)),
                 st.median(_series(runs, b, s, "primitives", rounds)),
                 st.median(_series(runs, a, s, "median_ms", rounds)),
                 st.median(_series(runs, b, s, "median_ms", rounds)),
                 st.median(_series(runs, a, s, "render_cpu_ms", rounds)),
                 st.median(_series(runs, b, s, "render_cpu_ms", rounds))))
    print("per-round median_ms, so a difference smaller than the spread of "
          "either arm can be seen to be one")
    for s in stations:
        print("%-14s %-26s %s"
              % (s,
                 " ".join("%6.2f" % x
                          for x in _series(runs, a, s, "median_ms", rounds)),
                 " ".join("%6.2f" % x
                          for x in _series(runs, b, s, "median_ms", rounds))))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("package", type=Path,
                    help="an exported package directory (read only)")
    ap.add_argument("work", type=Path, help="where the arms are built")
    ap.add_argument("--godot", type=Path,
                    default=Path(r"C:\Godot\4.7"
                                 r"\Godot_v4.7-stable_win64_console.exe"))
    ap.add_argument("--rounds", type=int, default=3)
    ap.add_argument("--occluders", type=int, default=301,
                    help="the count the `on` arms write into project.godot")
    args = ap.parse_args(argv)

    src, work = args.package.resolve(), args.work.resolve()
    if not (src / "project.godot").is_file():
        raise SystemExit(f"no project.godot in {src}")
    if work == src or src in work.parents:
        raise SystemExit("the work directory must be outside the package")
    out = work / "results"
    out.mkdir(parents=True, exist_ok=True)

    arms = {}
    for name, flag, strip in ARMS:
        arms[name] = _make_arm(src, work, name, flag, strip, args.godot,
                               args.occluders)

    # The arbiter, on the arm that ships: Godot loads `run/main_scene` and
    # counts the tree, against the text walk the export already ran.
    shutil.copyfile(COUNT, arms["on"] / COUNT.name)
    rep = work / "count_on.json"
    _run([args.godot, "--headless", "--path", arms["on"], "--script",
          f"res://{COUNT.name}", "--", rep], 900)
    (arms["on"] / COUNT.name).unlink(missing_ok=True)
    (arms["on"] / (COUNT.name + ".uid")).unlink(missing_ok=True)

    for rnd in range(1, args.rounds + 1):
        for name, pkg in arms.items():
            tag = f"{name}_r{rnd}"
            dest = out / f"{tag}.json"
            if dest.is_file():
                continue
            print("--- %s ---" % tag, flush=True)
            _run([args.godot, "--path", pkg, "--script",
                  f"res://{PROBE.name}", "--", dest, tag], 1800)
            if not dest.is_file():
                raise SystemExit(f"no report for {tag}")

    for pkg in arms.values():
        (pkg / PROBE.name).unlink(missing_ok=True)
        (pkg / (PROBE.name + ".uid")).unlink(missing_ok=True)

    runs, scene = _load(out, [a for a, _, _ in ARMS], args.rounds)
    print()
    print("scene", scene)
    for name, _, _ in ARMS:
        d = runs[(name, 1)]
        print("  arm %-9s flag=%-5s occluders in tree=%d"
              % (name, str(d["occlusion_setting"]).lower(),
                 d["occluder_nodes"]))
    if runs[(COST_PAIR[0], 1)]["occluder_nodes"] != 0:
        raise SystemExit("the cost arms still hold occluders")

    _table(runs, SAVING_PAIR, args.rounds,
           "WHAT THE CULLER SAVES -- same package, the flag the only variable")
    stations = [r["station"] for r in runs[(COST_PAIR[0], 1)]["stations"]]
    for s in stations:
        a = set(_series(runs, COST_PAIR[0], s, "draw_calls", args.rounds))
        b = set(_series(runs, COST_PAIR[1], s, "draw_calls", args.rounds))
        if a != b:
            raise SystemExit(
                "%s: the cost arms submit different frames (%s vs %s), so the "
                "difference between them is not a cost" % (s, sorted(a),
                                                           sorted(b)))
    _table(runs, COST_PAIR, args.rounds,
           "WHAT THE CULLER COSTS -- nothing to cull, draw calls identical")
    return 0


if __name__ == "__main__":
    sys.exit(main())
