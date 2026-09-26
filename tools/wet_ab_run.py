"""Price a wet `next_pass` on the scene a package actually runs.

THE HARNESS FOR `tools/wet_ab.gd`, modelled on `occlusion_ab_run.py` so a wet
figure this repo publishes is produced the same way an occlusion figure was.
Roadmap 157 slice 2; `docs/proposals/RAIN_WETNESS.md` item 2.

THE ARMS, and each answers something the others cannot.

    dry         the package as exported. No extra pass.
    wet_ground  the pass on what a player looks DOWN at -- road, sidewalk,
                kerb, asphalt, ground slabs, road paint. The cheap version of
                the look, and the one the cost model says should be cheap:
                the pass bills per SUBMISSION at ~3.5 us each, flat, so
                dropping walls and roofs should cut it in proportion. This arm
                is here to measure that rather than extrapolate it.
    wet       a wet `next_pass` on surfaces whose MATERIAL NAME says the
              weather reaches them -- ground, road, sidewalk, kerb, roof,
              exterior wall families. The shipping shape.
    wet_all   the same pass on EVERY material in the scene. Not a candidate
              for shipping: it is the upper bound, and it exists because a
              selective arm can only flatter the answer if the naming is
              incomplete. A cost you would not pay is still a cost you should
              know.

WHAT PROVES THE INSTRUMENT. A `next_pass` rasterises the SAME triangles a
second time, so DRAW CALLS MUST RISE from `dry` to `wet`. That is not a
sanity check bolted on; it is the control CLAUDE.md requires, and it is free.
The CRT measurement earned that rule: its first render probe reported
"pixel-identical" from frames that were 99.7% black, and a known geometry
change measured zero through the same probe. This refuses to tabulate a `wet`
arm whose draw calls did not move, because such a row is a frame-time number
with nothing behind it.

WHAT IT REFUSES BESIDES. Arms that do not name the same `main_scene`; a run
whose report is not `ok`; and a `wet` arm that wet zero materials.

WHY A WINDOW. Headless draws nothing: every `RENDERING_INFO_*` counter reads 0
and there is no frame to time. Each run quits itself.

THE RULE THIS SERVES. The walker, standing: performance over look when the two
compete, because the game is multiplayer and a look costs its milliseconds on
every client, every frame, on hardware nobody here has seen. This does not
decide whether wetness ships. It produces the number that decision needs, at
the renderer packages ship on, so the tradeoff can be put in front of a person
rather than guessed at.

    python tools/wet_ab_run.py <package_dir> <work_dir> [--godot EXE]
                               [--rounds 3] [--wetness 0.85]
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import statistics as st
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPT = HERE / "wet_ab.gd"
ARMS = ("dry", "wet_ground", "wet", "wet_all")


def _godot(explicit=None):
    if explicit:
        return explicit
    for env in ("LF_GODOT", "DC_GODOT", "LOT_GODOT"):
        p = os.environ.get(env)
        if p and Path(p).is_file():
            return p
    usual = Path("C:/Godot/4.7/Godot_v4.7-stable_win64_console.exe")
    return str(usual) if usual.is_file() else shutil.which("godot")


def stage(pkg: Path, work: Path, arm: str) -> Path:
    """A copy per arm. THE PACKAGE IS NEVER TOUCHED -- it is evidence, and a
    measurement that edits its subject has changed what it measured."""
    dest = work / arm
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(pkg, dest)
    shutil.copyfile(SCRIPT, dest / SCRIPT.name)
    return dest


def run_arm(godot: str, dest: Path, arm: str, wetness: float) -> dict:
    out = dest / "wet_ab.json"
    if out.exists():
        out.unlink()
    # imported once so the project can load(); the copy is throwaway, so the
    # cache it leaves is nobody's problem -- unlike in an export, where cold
    # run 9071 died on exactly that.
    subprocess.run([godot, "--headless", "--path", str(dest), "--import"],
                   capture_output=True, text=True, timeout=1800)
    proc = subprocess.run(
        [godot, "--path", str(dest), "--script", f"res://{SCRIPT.name}", "--",
         f"res://wet_ab.json", arm, str(wetness)],
        capture_output=True, text=True, timeout=3600)
    if not out.exists():
        for stream, label in ((proc.stdout, "stdout"), (proc.stderr, "stderr")):
            for line in (stream or "").strip().splitlines()[-20:]:
                print(f"    [godot {label}] {line}")
        raise SystemExit(f"wet_ab: arm {arm} wrote no report "
                         f"(godot exit {proc.returncode}); output above")
    rep = json.loads(out.read_text(encoding="utf-8"))
    if rep.get("schema") != "lf.wet_ab.v1":
        raise SystemExit(f"wet_ab: arm {arm} reported schema "
                         f"{rep.get('schema')!r}, not the one this knows")
    if not rep.get("ok"):
        raise SystemExit(f"wet_ab: arm {arm} refused: {rep.get('error')}")
    return rep


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("package", type=Path)
    ap.add_argument("work", type=Path)
    ap.add_argument("--godot")
    ap.add_argument("--rounds", type=int, default=3)
    ap.add_argument("--wetness", type=float, default=0.85)
    ap.add_argument("--json", type=Path)
    args = ap.parse_args(argv)

    godot = _godot(args.godot)
    if godot is None:
        print("wet_ab: no Godot binary (set LF_GODOT)")
        return 2
    if not args.package.is_dir():
        print(f"wet_ab: {args.package} is not a directory")
        return 2
    args.work.mkdir(parents=True, exist_ok=True)

    print(f"wet_ab: {args.package}")
    print(f"  renderer: the package's own (GL Compatibility is what ships)")
    print(f"  wetness : {args.wetness}   rounds: {args.rounds}\n")

    rounds = {a: [] for a in ARMS}
    for arm in ARMS:
        dest = stage(args.package, args.work, arm)
        for r in range(args.rounds):
            rep = run_arm(godot, dest, arm, args.wetness)
            rounds[arm].append(rep)
            print(f"  {arm:<8} round {r + 1}/{args.rounds}: "
                  f"{rep['materials_wet']} material(s) wet")

    scenes = {r["main_scene"] for a in ARMS for r in rounds[a]}
    if len(scenes) != 1:
        print(f"\nREFUSED: the arms ran different scenes: {scenes}")
        return 1
    if rounds["wet"][0]["materials_wet"] == 0:
        print("\nREFUSED: the `wet` arm wet zero materials -- the name test "
              "found nothing, so every figure below would be the dry arm "
              "measured twice.")
        return 1

    def rows(arm):
        out = {}
        for rep in rounds[arm]:
            for s in rep["stations"]:
                out.setdefault(s["station"], []).append(s)
        return out

    dry, grnd = rows("dry"), rows("wet_ground")
    wet, allw = rows("wet"), rows("wet_all")

    # THE CONTROL, and it is not optional. A next_pass draws the same triangles
    # again; if the counter did not move, nothing was added and no ms below is
    # evidence.
    moved = [s for s in dry
             if st.median([x["draw_calls"] for x in wet[s]])
             > st.median([x["draw_calls"] for x in dry[s]])]
    if not moved:
        print("\nREFUSED: draw calls did not rise at ANY station between dry "
              "and wet. The pass did not reach the frame, so the frame times "
              "are the same scene measured twice.")
        return 1

    # THE SECOND CONTROL, and the first run of this probe needed it. A
    # station whose cpu_ms and gpu_ms both read 0.00 was measured with
    # `viewport_set_measure_render_time` off, so the wall-clock figure
    # beside it is whatever the display did -- three stations came back
    # pinned at 6.07 ms, which is a refresh interval and not a frame
    # time. Without the split the run also cannot say whether an extra
    # pass costs submission or fill, which is the question that decides
    # whether narrowing the surface set would help at all.
    blind = [s for s in dry
             if max(x["cpu_ms"] + x["gpu_ms"]
                    for x in dry[s] + wet[s]) <= 0.0]
    if len(blind) == len(dry):
        print("\nREFUSED: every station reported cpu_ms and gpu_ms of "
              "0.00. Render-time measurement is off, so the frame times "
              "are display-limited wall clock and the "
              "submission-vs-fill question cannot be answered from "
              "them.")
        return 1

    # THE CONTROL THAT WAS MISSING, and its absence voided this probe's first
    # result. Draw calls rising proves a SUBMISSION. It does not prove a
    # shaded pixel, and a `next_pass` with `depth_draw_never` and no vertex
    # offset is rejected by GL Compatibility's depth test -- measured in
    # `assets/godot/zoo_worldskin.gd` before this file existed, and true of
    # this probe's own first shader. Its 2026-09-24 figures therefore priced
    # submission with a fragment that never ran, and the conclusion drawn from
    # them -- "the pass bills per submission, not per pixel" -- is withdrawn.
    #
    # A frame's own mean luminance can tell the two apart.
    if any("frame_luma" in x for s in dry for x in dry[s]):
        drew = [s for s in dry
                if abs(st.median([x.get("frame_luma", 0.0) for x in wet[s]])
                       - st.median([x.get("frame_luma", 0.0) for x in dry[s]]))
                > 1e-4]
        if not drew:
            print("\nREFUSED: the frame is identical at every station with "
                  "the pass on and off. Draw calls rose, so the geometry was "
                  "submitted -- and nothing was shaded. That is exactly what "
                  "this probe measured the first time.")
            return 1
        print("  the frame CHANGED at %d of %d station(s) -- the pass is "
              "visible, not merely submitted" % (len(drew), len(dry)))

    print(f"\n  materials wet: {rounds['wet'][0]['materials_wet']} selective, "
          f"{rounds['wet_all'][0]['materials_wet']} all")
    print(f"  draw calls rose at {len(moved)} of {len(dry)} station(s) "
          f"-- the instrument can see the pass\n")
    print("  %-14s %14s %14s %14s %14s"
          % ("station", "dry", "wet_ground", "wet (named)",
             "wet_all (bound)"))
    print("  %-14s %7s %6s %7s %6s %7s %6s %7s %6s"
          % ("", "draws", "ms", "draws", "ms", "draws", "ms", "draws", "ms"))
    for s in dry:
        def med(tbl, key):
            return st.median([x[key] for x in tbl[s]])
        print("  %-14s %7d %6.2f %7d %6.2f %7d %6.2f %7d %6.2f"
              % (s, med(dry, "draw_calls"), med(dry, "ms_median"),
                 med(grnd, "draw_calls"), med(grnd, "ms_median"),
                 med(wet, "draw_calls"), med(wet, "ms_median"),
                 med(allw, "draw_calls"), med(allw, "ms_median")))

    # THE COST MODEL, stated as a number rather than a word. If the marginal
    # us-per-added-draw-call is flat across stations whose wet-surface SCREEN
    # COVERAGE differs wildly, the pass bills per submission and narrowing the
    # material set cuts it proportionally. If it tracks coverage instead, it
    # bills per pixel and narrowing to the ground -- which is most of a street
    # frame -- buys nothing. This prints the spread and lets the reader decide,
    # rather than closing with a sentence naming a cause.
    print("\n  marginal cost of the pass, per added draw call:")
    for label, tbl in (("wet_ground", grnd), ("wet", wet), ("wet_all", allw)):
        per = []
        for s in dry:
            dd = (st.median([x["draw_calls"] for x in tbl[s]])
                  - st.median([x["draw_calls"] for x in dry[s]]))
            dm = (st.median([x["ms_median"] for x in tbl[s]])
                  - st.median([x["ms_median"] for x in dry[s]]))
            if dd > 0:
                per.append(1000.0 * dm / dd)
        if per:
            print("    %-11s %5.2f - %5.2f us  (median %.2f, over %d station"
                  "(s))" % (label, min(per), max(per), st.median(per),
                            len(per)))

    def delta(tbl):
        return [st.median([x["ms_median"] for x in tbl[s]])
                - st.median([x["ms_median"] for x in dry[s]]) for s in dry]

    print("")
    for label, tbl in (("wet_ground", grnd), ("wet", wet), ("wet_all", allw)):
        dl = delta(tbl)
        print("  %-11s - dry : median %+.2f ms, worst %+.2f ms"
              % (label, st.median(dl), max(dl)))
    print("  The median is over ALL stations including near-empty views; the "
          "worst is\n  the one to hold a budget against.")
    print("\n  This prices ONE EXTRA RASTER of the same triangles with a cheap "
          "fragment.\n  It is not the look: what a wet Delco street should "
          "look like is Pixelcoat's\n  grammar and the walker's call. It is "
          "also not the expensive reference --\n  the screen-space puddle pass "
          "reads depth and is unmeasured on GL\n  Compatibility "
          "(RAIN_WETNESS.md item 1), and must be priced separately.")

    if args.json:
        args.json.write_text(json.dumps(
            {"schema": "lf.wet_ab_run.v1", "package": str(args.package),
             "wetness": args.wetness, "rounds": args.rounds,
             "arms": {a: rounds[a] for a in ARMS}}, indent=1), encoding="utf-8")
        print(f"\n  wrote {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
