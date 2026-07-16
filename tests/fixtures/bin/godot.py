#!/usr/bin/env python3
"""Stub 'godot': --version, laser_tag runner, lux driver, and portability check.

Mimics the REAL headless invocations:
  godot --headless --path <proj> -s res://addons/laser_tag_tool/runners/run_map_eval.gd -- \
        --map res://level.tscn --scenario <.tres> --runs N --seed S --output <path>.json
  godot --headless --path <proj> -s res://run_lux_apply.gd -- \
        --scene res://level.tscn --preset <name> --out <dir>
"""
import json, sys
from pathlib import Path


def _uargs(argv):
    """User args after the `--` separator (Godot passes these through)."""
    return argv[argv.index("--") + 1:] if "--" in argv else argv


def _opt(uargs, name, default=None):
    return uargs[uargs.index(name) + 1] if name in uargs and uargs.index(name) + 1 < len(uargs) else default


def main():
    argv = sys.argv[1:]
    if "--version" in argv:
        print("4.7.stable.official"); return 0

    # Blender-style invocation: `--background --python <script> -- <args>`.
    # Real Zoo geometry builds run this way; execute the target script with the
    # post-`--` args so the zoo stub writes its real building-id-named index.
    if "--python" in argv and argv.index("--python") + 1 < len(argv):
        target = argv[argv.index("--python") + 1]
        zoo_args = argv[argv.index("--") + 1:] if "--" in argv else []
        import subprocess
        return subprocess.run([sys.executable, target, *zoo_args]).returncode

    script = argv[argv.index("-s") + 1] if "-s" in argv else ""
    uargs = _uargs(argv)

    if script.endswith("run_map_eval.gd"):
        out = _opt(uargs, "--output", "user://reports/eval.json")
        seed = int(_opt(uargs, "--seed", "0"))
        runs = int(_opt(uargs, "--runs", "25"))
        jp = Path(out); jp.parent.mkdir(parents=True, exist_ok=True)
        jp.write_text(json.dumps({"score": 70 + (seed % 20), "grade": "B",
                                  "runs": runs, "overexposed_zones": [],
                                  "blind_zones": []}, sort_keys=True))
        csv = Path(str(jp)[:-5] + ".csv" if str(jp).endswith(".json") else str(jp) + ".csv")
        csv.write_text("run,score\n0,70\n")
        print(f"[LT] JSON report: {jp}")
        return 0

    if script.endswith("run_lux_apply.gd"):
        out = Path(_opt(uargs, "--out", "user://lux")); out.mkdir(parents=True, exist_ok=True)
        preset = _opt(uargs, "--preset", "")
        # Presentation roots only; gameplay nodes stay outside them.
        (out / "lux.applied.tscn").write_text(
            '[gd_scene format=3]\n[node name="Mission" type="Node3D"]\n'
            '[node name="LuxRoot" type="Node3D" parent="."]\n'
            '[node name="Functional" type="Node3D" parent="."]\n')
        (out / "lux.quality.json").write_text(json.dumps(
            {"preset": preset, "applied": True, "driver": "run_lux_apply"}, sort_keys=True))
        (out / "lux.validation.json").write_text(json.dumps({"issues": []}, sort_keys=True))
        print(f"[lux] applied preset '{preset}' -> {out}")
        return 0

    if script.endswith("run_fixture_gate.gd"):
        out = Path(_opt(uargs, "--out", "user://fixture_gate"))
        out.mkdir(parents=True, exist_ok=True)
        # Mirror the real driver's report shape; stub fixtures GLB carries no
        # real markers, so derive counts from the staged glb name marker.
        (out / "fixture_gate.report.json").write_text(json.dumps(
            {"driver": "run_fixture_gate", "markers": 4, "spawnable": 4,
             "spawned": 4, "colocation_errors": [],
             "powered": {"kill": True, "restore": True},
             "tolerance": 0.1}, sort_keys=True))
        print("[fixture_gate] markers=4 spawned=4 colocation_errors=0")
        return 0

    # Bare import pass on a staged project: nothing to do headlessly.
    if "--import" in argv:
        return 0

    if "--lf-portability-check" in argv:
        proj = Path(argv[argv.index("--path") + 1]) if "--path" in argv else Path(".")
        if (proj / "mission.tscn").exists():
            print("scene instantiated ok"); return 0
        print("Parse Error: mission.tscn missing"); return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
