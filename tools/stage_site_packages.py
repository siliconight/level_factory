"""Stage a site job's building packages into its own out dir. One planned step.

Run by the Lot adapter as the FIRST of two planned commands, before ``lot.py``
touches the spec:

    python tools/stage_site_packages.py <manifest.json> <out_dir>

It is a separate command rather than a side effect inside ``plan_commands``
because ``plan_commands`` is called to build the build FINGERPRINT as well as
to run the job -- including on the cache-hit path, where nothing is meant to
execute. A step that copies eleven megabytes of geometry while a fingerprint is
being computed is a step that runs at times nobody chose. As a planned command
it is logged, re-runnable on its own, and its arguments are folded into the
fingerprint like every other command's.

Exits 1 with the reason on any missing source. That is the point: the manifest
is built at PLAN time, before the compose jobs that produce these packages have
run, so it is a list of what the site is supposed to contain rather than a
survey of what exists. A varied lot has already shipped once with five correct
composes beside a site that placed the mission shell five times, because an
absence was read as "nothing to stage" instead of "this is wrong".
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from packages.staging.site_packages import StagingError, stage_all  # noqa: E402


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: python tools/stage_site_packages.py "
              "<manifest.json> <out_dir>")
        return 2
    manifest_path, out_dir = Path(argv[0]), Path(argv[1])
    if not manifest_path.is_file():
        print(f"[stage] manifest missing: {manifest_path}")
        return 1
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    try:
        report = stage_all(manifest, out_dir)
    except StagingError as exc:
        print(f"[stage] REFUSED: {exc}")
        return 1

    for pid, ref in sorted(report["packages"].items()):
        print(f"[stage] package {pid} -> {ref}")
    for bid, ref in sorted(report["glbs"].items()):
        print(f"[stage] glb     {bid} -> {ref}")
    if report["addons"]:
        print(f"[stage] addon scripts -> {', '.join(report['addons'])}")

    total = len(report["packages"]) + len(report["glbs"])
    if not total:
        # Not an error -- a site can legitimately have nothing to stage -- but
        # say so, because "staged 0" and "did not run" look identical in a log
        # and only one of them is fine.
        print("[stage] nothing to stage (no packages or glbs in the manifest)")
    else:
        print(f"[stage] {total} building source(s) staged under {out_dir}")

    # What the site scene should now contain, so the run's log carries the
    # claim the acceptance test checks rather than leaving it to be re-derived.
    print("[stage] every building ref is now relative to the site out dir")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
