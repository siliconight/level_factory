"""Stub walktest.py (0.25.0 CLI shape).

    python walktest.py <project_dir> <scene> [--all] [--require] [--report-dir D]

Stands in for Lot's nav QA runner in the fixture pipeline. Real walktest.py
launches headless Godot, bakes a navmesh and drives physical walkers; none of
that is what the end-to-end tests are exercising, so this writes the report the
director would have written and returns the exit code the verdict implies.

Two behaviours are copied deliberately because the adapter depends on them:
`--report-dir` is where the report goes, and the report is the ONLY evidence the
check ran -- a run that writes nothing must not return 0. The real runner's skip
path (no Godot, no --require, exit 0, no report) is not reproduced here; the
adapter always passes --require, and the skip itself is covered in Lot's own
tests/test_walktest_runner.py.
"""
import json
import os
import sys


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    report_dir = None
    if "--report-dir" in argv:
        i = argv.index("--report-dir")
        report_dir = argv[i + 1]
        del argv[i:i + 2]
    flags = {a for a in argv if a.startswith("--")}
    pos = [a for a in argv if not a.startswith("--")]
    project = pos[0] if pos else "."
    scene = pos[1] if len(pos) > 1 else "site_navqa.tscn"

    # A pass: the spine is pathable and both walkers reach their targets. The
    # failing shapes are covered directly in tests/unit/test_walktest_adapter.py,
    # which reads reports rather than producing them.
    report = {
        "ok": True,
        "path_proofs": [
            {"leg": "spawn->objective", "ok": True, "length_m": 38.4},
            {"leg": "objective->extraction", "ok": True, "length_m": 41.9},
        ],
        "walkers": [
            {"name": "bot_0", "status": "ok", "targets_reached": 1,
             "targets_total": 1, "travelled_m": 40.2},
            {"name": "bot_1", "status": "ok", "targets_reached": 1,
             "targets_total": 1, "travelled_m": 44.8},
        ],
        "proxies": 1, "bot_spawns": 2, "map_iteration": 3,
        "sim_seconds": 21.5,
    }

    name = os.path.splitext(os.path.basename(scene))[0] + ".walktest.json"
    beside = os.path.join(project, name)
    os.makedirs(project, exist_ok=True)
    with open(beside, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, sort_keys=True)
    if report_dir:
        os.makedirs(report_dir, exist_ok=True)
        with open(os.path.join(report_dir, name), "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, sort_keys=True)

    print(f"[walktest] {name}: {'PASS' if report['ok'] else 'FAIL'} "
          f"(require={'--require' in flags})")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
