"""Run the fixed-station performance harness against an exported package.

    python level_factory/tools/perf_stations_run.py <package dir> [options]

Copies `perf_stations.gd` into the package, runs Godot windowed (headless
draws nothing, so it cannot measure a frame), reads the JSON back, prints a
table, and applies the budget.

WHY IT IS A SEPARATE PYTHON HALF. The probe's job is to measure and stop --
`CLAUDE.md`: "a probe prints what it measured and stops; it never closes with
a fixed sentence naming a cause". Budget arithmetic and the pass/fail call
live here, where they can be argued with and where a caller can change the
budget without editing a GDScript file.

It also keeps pixel-and-number work out of GDScript. A previous probe diffed
1280x720 with `get_pixel` and hung a window on the walker's desktop until a
timeout killed it; Godot captures, Python computes.

EXIT CODES, matching `tools/check_all.py`:

    0   measured, and every station inside budget
    1   measured, and at least one station over budget (findings)
    2   COULD NOT MEASURE -- no stations, no frames drawn, Godot missing,
        the run timed out, or the report came back in a shape this does not
        recognise. Never reported as a pass: a checker that cannot find the
        field it wants has learned nothing and must say so.

THE BUDGET IS PROVISIONAL AND SAYS SO. `docs/DRAW_CALL_BUDGET.md` derives
2,000 draw calls in the worst sightline from two measured runs, at about half
the 16.7 ms crossing, with the remainder held back for the gameplay, netcode
and other players that were absent from the measurement -- and on hardware
that is not the low-end GL Compatibility target. Override it rather than
quietly trusting it.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

EXIT_OK = 0
EXIT_FINDINGS = 1
EXIT_CANNOT = 2

#: `docs/DRAW_CALL_BUDGET.md`. Provisional, derived, and meant to be replaced
#: by an exported-build measurement on a low-end GL Compatibility machine.
DEFAULT_DRAWS = 2000
#: 60 FPS is 16.7 ms for the WHOLE frame including the gameplay this harness
#: does not run, so the rendering share has to come in well under it.
DEFAULT_MS = 11.0

PROBE = Path(__file__).with_name("perf_stations.gd")


def _find_godot(explicit: str | None) -> str | None:
    if explicit:
        return explicit if Path(explicit).exists() else None
    env = os.environ.get("GODOT") or os.environ.get("GODOT_BIN")
    if env and Path(env).exists():
        return env
    for c in (
        r"C:/Godot/4.7/Godot_v4.7-stable_win64_console.exe",
        r"C:/Godot/Godot_v4.7-stable_win64_console.exe",
    ):
        if Path(c).exists():
            return c
    return shutil.which("godot")


def _table(rows, draw_budget, ms_budget):
    over = []
    print()
    print("  %-24s %6s %8s %8s %8s %7s %7s %10s"
          % ("station", "yaw", "p95 ms", "worst", "gpu ms", "rcpu", "draws",
             "primitives"))
    for r in sorted(rows, key=lambda x: -float(x["worst_heading"]["ms_p95"])):
        w = r["worst_heading"]
        flags = []
        if int(w["draws"]) > draw_budget:
            flags.append("DRAWS")
        if float(w["ms_p95"]) > ms_budget:
            flags.append("MS")
        if flags:
            over.append((r["station"], flags, w))
        print("  %-24s %6.0f %8.2f %8.2f %8.2f %7.2f %7d %10d  %s"
              % (str(r["station"])[:24], float(w["yaw"]), float(w["ms_p95"]),
                 float(w["ms_worst"]), float(w["gpu_ms"]),
                 float(w["render_cpu_ms"]), int(w["draws"]),
                 int(w["primitives"]), " ".join(flags)))
    return over


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("package", type=Path,
                    help="an exported portable-godot package, or a walk copy")
    ap.add_argument("--godot", default=None)
    ap.add_argument("--draws", type=int, default=DEFAULT_DRAWS,
                    help="worst-sightline draw-call budget (default %d)"
                         % DEFAULT_DRAWS)
    ap.add_argument("--ms", type=float, default=DEFAULT_MS,
                    help="p95 frame-time budget in ms (default %.1f)"
                         % DEFAULT_MS)
    ap.add_argument("--json", type=Path, default=None,
                    help="where to copy the report (default: beside the package)")
    ap.add_argument("--timeout", type=int, default=900)
    args = ap.parse_args(argv)

    pkg: Path = args.package.resolve()
    if not (pkg / "project.godot").exists():
        print("CANNOT MEASURE: %s has no project.godot" % pkg)
        return EXIT_CANNOT
    if not (pkg / "gameplay_anchors.json").exists():
        print("CANNOT MEASURE: %s has no gameplay_anchors.json, so there are"
              % pkg)
        print("  no stations. The harness derives them from the package on")
        print("  purpose; a station typed into a probe goes stale the first")
        print("  time the generator moves something.")
        return EXIT_CANNOT

    godot = _find_godot(args.godot)
    if godot is None:
        print("CANNOT MEASURE: no Godot binary (pass --godot or set $GODOT)")
        return EXIT_CANNOT

    # IMPORT ONCE IF IT HAS NOT BEEN. The package ships sidecars, not a
    # `.godot` cache -- its own export message says to do this -- and
    # without it every GLB fails to load silently. The first run of this
    # harness measured a level containing nothing but its dressing
    # MultiMeshes: 4 draw calls at all 29 stations.
    if not (pkg / ".godot").exists():
        print("importing %s (ships sidecars, no cache)" % pkg.name)
        try:
            subprocess.run([godot, "--headless", "--path", str(pkg),
                            "--import"], timeout=args.timeout,
                           capture_output=True, text=True)
        except subprocess.TimeoutExpired:
            print("CANNOT MEASURE: import did not finish in %ds"
                  % args.timeout)
            return EXIT_CANNOT
        if not (pkg / ".godot").exists():
            print("CANNOT MEASURE: import produced no .godot cache")
            return EXIT_CANNOT

    shutil.copy(PROBE, pkg / PROBE.name)
    out = pkg / "perf_stations.json"
    if out.exists():
        out.unlink()
    cmd = [godot, "--path", str(pkg), "--script", "res://" + PROBE.name,
           "--", "--out", "res://perf_stations.json"]
    print("$ " + " ".join(cmd))
    try:
        proc = subprocess.run(cmd, timeout=args.timeout,
                              capture_output=True, text=True)
    except subprocess.TimeoutExpired:
        print("CANNOT MEASURE: Godot did not finish in %ds" % args.timeout)
        return EXIT_CANNOT
    for line in (proc.stdout or "").splitlines():
        if line.startswith("[perf]") or line.startswith("  "):
            print(line)

    if not out.exists():
        print("CANNOT MEASURE: the probe wrote no report (exit %d)"
              % proc.returncode)
        tail = (proc.stderr or "").strip().splitlines()[-5:]
        for t in tail:
            print("  godot: %s" % t)
        return EXIT_CANNOT

    doc = json.loads(out.read_text(encoding="utf-8"))
    # AN UNRECOGNISED SHAPE FAILS. This repo has shipped a --verify that read
    # keys a file never wrote, turned the absence into an empty problem list
    # with `or []`, and printed "clean" three lines under the exporter
    # shouting that 21 resources were unresolved.
    if doc.get("schema") != "level_factory.perf_stations.v1":
        print("CANNOT MEASURE: report schema is %r, not the one this reads"
              % doc.get("schema"))
        return EXIT_CANNOT
    # A TRUNCATED RUN IS NOT A PASS. The watchdog writes what it has so
    # the partial numbers are not lost; `complete` is how it says so, and
    # the first version of this runner printed "every station inside
    # budget" over exactly such a report.
    if not doc.get("complete", False):
        print("CANNOT MEASURE: the probe did not finish (watchdog or a")
        print("  refusal). The partial report is still at %s" % out)
        geo = doc.get("geometry") or {}
        if geo:
            print("  geometry seen: %s" % geo)
        return EXIT_CANNOT

    rows = doc.get("rows")
    if not isinstance(rows, list) or not rows:
        print("CANNOT MEASURE: report carried no station rows")
        return EXIT_CANNOT

    over = _table(rows, args.draws, args.ms)

    census = rows[0].get("light_census") or {}
    if census:
        print()
        print("  lights per object: cap %s, %s of %s mesh(es) over it, "
              "worst %s (%s)"
              % (census.get("cap"), census.get("over_cap"),
                 census.get("meshes"), census.get("worst"),
                 census.get("worst_mesh")))
        print("  (merging and instancing buy draw calls with lighting "
              "fidelity; a change that")
        print("   improves the draw column can darken interiors, so the two "
              "are reported together)")

    dest = args.json or (pkg.parent / (pkg.name + ".perf_stations.json"))
    shutil.copy(out, dest)
    print()
    print("  report -> %s" % dest)
    print("  budget: %d draws, %.1f ms p95 (provisional -- "
          "docs/DRAW_CALL_BUDGET.md)" % (args.draws, args.ms))
    print("  gpu/rcpu come from a SEPARATE short pass with the render")
    print("  timers on, and are not comparable with p95 ms, which is")
    print("  measured with them off -- the timers cost real frame time.")

    worst = max(rows, key=lambda r: float(r["worst_heading"]["ms_p95"]))
    wh = worst["worst_heading"]
    print("  worst station: %s at yaw %.0f -- %.2f ms p95, %d draws"
          % (worst["station"], float(wh["yaw"]), float(wh["ms_p95"]),
             int(wh["draws"])))

    if over:
        print()
        print("PERF_STATION_OVER_BUDGET: %d of %d station(s)"
              % (len(over), len(rows)))
        for name, flags, w in over:
            print("  %-24s %s (%.2f ms p95, %d draws)"
                  % (name, "+".join(flags), float(w["ms_p95"]),
                     int(w["draws"])))
        return EXIT_FINDINGS
    print()
    print("every station inside budget")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
