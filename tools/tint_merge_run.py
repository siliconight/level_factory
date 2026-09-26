"""Run `tint_merge_ab.gd` on a package and report what collapsing the tint
variants would buy.

WHY A RUNNER AND NOT A COMMAND. The same reasons `wet_ab_run.py` has one: the
package is staged per arm so a probe never touches a deliverable, each arm runs
several rounds because one round of a frame time is an anecdote, and the
CONTROLS are enforced here rather than left for a reader to notice. This one
refuses a result where the triangle count moved between arms -- a merge that
drops geometry gets faster for the wrong reason -- and refuses a `merged` arm
that merged nothing, which would otherwise tabulate the same arm twice and
report the fix as free.
"""
from __future__ import annotations

import argparse
import json
import shutil
import statistics as st
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

ARMS = ("as_is", "merged")
SCRIPT = Path(__file__).resolve().parent / "tint_merge_ab.gd"


def find_godot(explicit: str | None) -> str:
    import os
    for cand in (explicit, os.environ.get("DC_GODOT"), os.environ.get("GODOT")):
        if cand and Path(cand).exists():
            return cand
    found = shutil.which("godot")
    if found:
        return found
    raise SystemExit("no Godot binary: pass --godot or set DC_GODOT")


def stage(pkg: Path, work: Path, arm: str) -> Path:
    """A throwaway copy per arm. The export is never opened by the probe."""
    dest = work / f"tint_{arm}"
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(pkg, dest)
    shutil.copy2(SCRIPT, dest / SCRIPT.name)
    return dest


def run_arm(godot: str, dest: Path, arm: str) -> dict:
    out = dest / "tint_merge_ab.json"
    if out.exists():
        out.unlink()
    subprocess.run([godot, "--headless", "--path", str(dest), "--import"],
                   capture_output=True, text=True, timeout=1800)
    proc = subprocess.run(
        [godot, "--path", str(dest), "--script", f"res://{SCRIPT.name}", "--",
         "res://tint_merge_ab.json", arm],
        capture_output=True, text=True, timeout=3600)
    if not out.exists():
        for stream, label in ((proc.stdout, "stdout"), (proc.stderr, "stderr")):
            for line in (stream or "").strip().splitlines()[-20:]:
                print(f"    [godot {label}] {line}")
        raise SystemExit(f"tint_merge: arm {arm} wrote no report "
                         f"(godot exit {proc.returncode}); output above")
    return json.loads(out.read_text(encoding="utf-8"))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="what collapsing Zoo's tint variants buys, in draw calls")
    ap.add_argument("package", type=Path)
    ap.add_argument("work", type=Path)
    ap.add_argument("--godot", default=None)
    ap.add_argument("--rounds", type=int, default=3)
    ap.add_argument("--json", type=Path, default=None)
    args = ap.parse_args(argv)

    godot = find_godot(args.godot)
    args.work.mkdir(parents=True, exist_ok=True)

    rounds: dict[str, list] = {a: [] for a in ARMS}
    for arm in ARMS:
        dest = stage(args.package, args.work, arm)
        for r in range(args.rounds):
            print(f"  {arm} round {r + 1}/{args.rounds} ...")
            rep = run_arm(godot, dest, arm)
            if not rep.get("ok"):
                raise SystemExit(f"tint_merge: arm {arm} failed: "
                                 f"{rep.get('error')}")
            rounds[arm].append(rep)

    merge = rounds["merged"][0].get("merge") or {}
    print("\n  what the merge did")
    for k in ("considered", "skipped_multi_surface", "groups_merged",
              "surfaces_before", "surfaces_after", "surfaces_removed"):
        print(f"    {k:24s} {merge.get(k, 0)}")

    # REFUSAL 1: a merged arm that merged nothing is the as_is arm measured
    # twice, and every delta below would read as "the fix is free".
    if int(merge.get("groups_merged", 0)) == 0:
        print("\nREFUSED: the merged arm merged 0 groups. Either this package "
              "has no tint families or the key did not match them -- and a "
              "zero here is indistinguishable from a fix that costs nothing.")
        return 1

    def rows(arm: str) -> dict:
        tbl = defaultdict(list)
        for rep in rounds[arm]:
            for s in rep["stations"]:
                tbl[s["station"]].append(s)
        return tbl

    a, b = rows("as_is"), rows("merged")

    # REFUSAL 2: THE CONTROL, and it is not the one this runner shipped with.
    #
    # WITHDRAWN 2026-09-26, kept above the check that replaced it. The first
    # version required `primitives` to be IDENTICAL in frame between the arms,
    # modelled on the merge this probe follows ("118 meshes to 4, triangles
    # identical"). It refused its own first run:
    #
    #     street_down       886,110 ->   886,852    (+742)
    #     street_along    1,152,456 -> 1,193,404 (+40,948)
    #     exterior_high   1,129,824 -> 1,194,252 (+64,428)
    #     interior_b      1,170,592 -> 1,221,216 (+50,624)
    #
    # Those rises are not lost geometry, they are the merge WORKING. Zoo's
    # merge held triangles because every part of one pack wall enters view
    # together; a tint family spans a whole placed file, so merging it makes
    # one object out of things the culler used to reject separately. That is
    # the cost CLAUDE.md already names -- "a whole street merged into one mesh
    # would be faster to submit and slower to play" -- and a control that
    # forbids that cost cannot measure it.
    #
    # The conservation check moved to where the answer does not depend on
    # where a camera stands: the probe counts triangles INTO the merge and
    # OUT of it.
    tin = int(merge.get("triangles_in", -1))
    tout = int(merge.get("triangles_out", -2))
    if tin != tout:
        print(f"\nREFUSED: the merge took in {tin:,} triangles and emitted "
              f"{tout:,}. Geometry was lost or duplicated, so every figure "
              f"below describes a different scene from the one that ships.")
        return 1
    print(f"\n  control: {tin:,} triangles in, {tout:,} out -- the merge "
          f"conserved geometry")
    print(f"  widest merged group: "
          f"{float(merge.get('widest_group_span_m', 0.0)):.2f} m across")

    print("\n  triangles submitted in frame (the culling cost of merging)")
    for s in a:
        pa = st.median([x["primitives"] for x in a[s]])
        pb = st.median([x["primitives"] for x in b[s]])
        pct = 100.0 * (pb - pa) / max(pa, 1.0)
        print(f"    {s:16s} {pa:>12,.0f} -> {pb:>12,.0f}"
              f"   ({pb - pa:+,.0f}, {pct:+.1f}%)")

    print("\n  %-16s %8s %7s   %8s %7s   %8s %8s"
          % ("station", "draws", "ms", "draws", "ms", "d draws", "d ms"))
    print("  %-16s %8s %7s   %8s %7s" % ("", "as_is", "", "merged", ""))
    saved_draws, saved_ms = [], []
    for s in a:
        da = st.median([x["draw_calls"] for x in a[s]])
        db = st.median([x["draw_calls"] for x in b[s]])
        ma = st.median([x["ms_median"] for x in a[s]])
        mb = st.median([x["ms_median"] for x in b[s]])
        saved_draws.append(da - db)
        saved_ms.append(ma - mb)
        print("  %-16s %8d %7.2f   %8d %7.2f   %+8d %+8.2f"
              % (s, da, ma, db, mb, db - da, mb - ma))

    print("\n  draw calls removed : median %d, best %d"
          % (st.median(saved_draws), max(saved_draws)))
    print("  frame time saved   : median %+.2f ms, best %+.2f ms"
          % (st.median(saved_ms), max(saved_ms)))

    # The luminance is reported, not gated. The merge SHOULD look identical --
    # the tint moves from the albedo factor into the vertex colour channel,
    # which glTF multiplies anyway -- but "identical" is a claim about a look
    # and belongs in a reply where it can be argued with, not in a refusal.
    print("\n  frame luminance (the merge should be invisible, not merely cheap)")
    for s in a:
        la = st.median([x.get("frame_luma", 0.0) for x in a[s]])
        lb = st.median([x.get("frame_luma", 0.0) for x in b[s]])
        print("    %-16s %.4f -> %.4f   (%+.4f)" % (s, la, lb, lb - la))

    if args.json:
        args.json.write_text(json.dumps(
            {"schema": "lf.tint_merge_run.v1", "rounds": args.rounds,
             "merge": merge, "arms": {x: rounds[x] for x in ARMS}}, indent=1),
            encoding="utf-8")
        print(f"\n  wrote {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
