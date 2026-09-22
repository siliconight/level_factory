"""Price the warm-up's station set: stations, load time, and lap 1's worst frame.

WHAT THIS ANSWERS. `warmup.gd` trades load time for first-sight stalls, and
0.100.0 shipped one point on that trade (`station_spacing_m` 12.0) without the
curve either side of it. This drives the curve: for each configuration it
records the station count, the seconds spent before play on a machine whose
driver cache has never seen the content AND on one where it has, and what the
first lap's worst frame then costs.

THE TWO CACHES, AND WHY NEITHER IS THE MACHINE'S. `tools/first_sight_probe.gd`'s
header carries the procedure; this automates it and adds the control it asks
for.

  * Godot's own cache lives at `%APPDATA%/Godot/app_userdata/<config/name>/
    shader_cache` and is keyed on the project NAME. Every configuration here
    runs under that same name, so it is wiped before EVERY run -- warm and cold
    alike. A player loading a level they have never loaded has an empty one,
    which is the case being priced.
  * The NVIDIA driver's is machine-global. It is never deleted and never moved:
    `__GL_SHADER_DISK_CACHE_PATH` points the process at a private directory
    instead, so `%LOCALAPPDATA%\\NVIDIA\\GLCache` (558 MB on this machine) is
    left exactly as it was found. COLD gets an empty private directory; WARM
    re-runs the same configuration against the directory the cold run filled.
  * A cold run that wrote NO cache was not cold -- it reused one somewhere else
    -- so the private directory's byte count is taken before and after, and a
    run that did not grow it is reported as `cache+0 B` and is not evidence.

WHAT IT REPORTS, AND WHAT IT DOES NOT. Load and frame time are separate columns
on purpose: they are being traded against each other and one figure hides the
trade. `load_s` is wall time from process launch to the warm-up's own
`warmup_finished`, so it covers Godot's startup, the scene load and the sweep;
`sweep_ms` is the warm-up's own figure for the sweep alone. `scene_s` is the
entry scene's `scene instantiated ok`, which is the only comparable moment a
package with the warm-up switched OFF prints, so the control lands on the same
axis as the rows it is a control for.

It prints what it measured. The reading belongs in the reply.

Usage:
    python tools/warmup_spacing_sweep.py --work <dir> --configs <json> --out <json>
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

_LF_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_LF_ROOT))

from packages.exporting import warmup as warmup_mod  # noqa: E402

PROBE = _LF_ROOT / "tools" / "first_sight_probe.gd"
PROBE_NAME = "first_sight_probe.gd"

#: Godot's per-project shader cache lives under here.
_APPDATA = Path(os.environ.get("APPDATA", ""))

#: Eye height for the walk camera, above the spawn anchor. The anchor is a
#: FLOOR position; the camera is an eye.
_EYE_M = 1.6

_WARMUP_DONE = re.compile(r"\[warmup\] (\d+) frame\(s\) in ([0-9.]+) ms")
_WARMUP_PLAN = re.compile(
    r"\[warmup\] (\d+) station\(s\), (\d+) on a ([0-9.]+) m grid")
_WARMUP_PLAN_0100 = re.compile(r"\[warmup\] (\d+) station\(s\) at ([0-9.]+) m")
_LAP = re.compile(
    r"\[fs\] LAP (\d+): (\d+) frames, mean ([0-9.]+) ms, "
    r"([0-9.]+)% over 16\.7 ms, worst ([0-9.]+) ms")


#: Every Godot the machine is running, by PID. A frame-time MAXIMUM is the
#: most contention-sensitive number there is, and this machine had a second
#: agent driving its own Godot through the middle of this sweep. A row
#: measured against a busy GPU is not comparable with one measured against an
#: idle one, so the count is recorded per run and a non-zero `foreign_godot`
#: means the row is contended -- reported, not silently averaged away.
_GODOT_IMAGES = ("Godot_v4.7-stable_win64.exe", "Godot_v4.8-stable_win64.exe",
                 "Godot_v4.7-stable_win64_console.exe",
                 "Godot_v4.8-stable_win64_console.exe")


def _godot_pids() -> set[int]:
    pids: set[int] = set()
    for image in _GODOT_IMAGES:
        try:
            out = subprocess.run(
                ["tasklist", "/FI", f"IMAGENAME eq {image}", "/FO", "CSV",
                 "/NH"], capture_output=True, text=True, timeout=20).stdout
        except Exception:
            continue
        for line in out.splitlines():
            parts = [c.strip('"') for c in line.split('","')]
            if len(parts) > 1 and parts[1].isdigit():
                pids.add(int(parts[1]))
    return pids


class _Contention:
    """Polls for Godot processes that are not the one this run launched."""

    def __init__(self, mine: set[int], *, foreign_at_start: int = 0) -> None:
        self._mine = mine
        self._stop = threading.Event()
        self.samples = 0
        self.contended = 0
        self.peak = foreign_at_start
        self.at_start = foreign_at_start
        self._th = threading.Thread(target=self._loop, daemon=True)
        self._th.start()

    def _loop(self) -> None:
        while not self._stop.wait(3.0):
            other = _godot_pids() - self._mine
            self.samples += 1
            if other:
                self.contended += 1
                self.peak = max(self.peak, len(other))

    def stop(self) -> dict:
        self._stop.set()
        self._th.join(timeout=25)
        return {"samples": self.samples, "contended_samples": self.contended,
                "peak_foreign_godot": self.peak,
                "foreign_at_start": self.at_start}


def _dir_bytes(p: Path) -> int:
    if not p.is_dir():
        return 0
    return sum(f.stat().st_size for f in p.rglob("*") if f.is_file())


def _project_name(pkg: Path) -> str:
    for line in (pkg / "project.godot").read_text(encoding="utf-8").splitlines():
        if line.startswith("config/name="):
            return line.split("=", 1)[1].strip().strip('"')
    raise SystemExit("no config/name in project.godot -- cannot find the cache")


def _add_camera(pkg: Path) -> str:
    """Give the walk copy a current `Camera3D`, at the level's own spawn.

    The probe refuses a scene with no current camera, and a level package
    ships no player. The position comes from the `crew_spawn` anchor the
    package declares rather than from an invented origin, so every row in the
    table stands where the level says a body starts.
    """
    scene = pkg / "mission.tscn"
    text = scene.read_text(encoding="utf-8")
    if '[node name="WalkCam"' in text:
        return "already present"
    anchors = json.loads(
        (pkg / "gameplay_anchors.json").read_text(encoding="utf-8"))["anchors"]
    spawn = [a for a in anchors if a["anchor_type"] == "crew_spawn"]
    if not spawn:
        raise SystemExit("no crew_spawn anchor -- refusing to invent one")
    x, y, z = spawn[0]["transform"]["pos"]
    y += _EYE_M
    lines = text.splitlines()
    at = next(i for i, ln in enumerate(lines)
              if ln.startswith(f'[node name="{warmup_mod.HOLDER_NODE}"'))
    cam = ['[node name="WalkCam" type="Camera3D" parent="."]',
           f"transform = Transform3D(1, 0, 0, 0, 1, 0, 0, 0, 1, {x}, {y}, {z})",
           "current = true", "far = 4000.0", ""]
    lines = lines[:at] + cam + lines[at:]
    scene.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return f"crew_spawn {x}, {y}, {z}"


def _set_node_props(pkg: Path, props: dict) -> None:
    """Rewrite the `Warmup` node's property lines, and nothing else.

    Replaces exactly that node's block rather than everything from it to the
    end of the file. The walk copy carries the camera node too, and a rewrite
    that truncated the tail would delete it and turn every row into NO CAMERA
    -- silently, because the file would still parse.

    A row with an empty override set IS the script's own defaults, which is
    what makes it the control.
    """
    scene = pkg / "mission.tscn"
    lines = scene.read_text(encoding="utf-8").splitlines()
    head = f'[node name="{warmup_mod.HOLDER_NODE}" type="Node3D" parent="."]'
    start = lines.index(head)
    end = start + 1
    while end < len(lines) and not lines[end].startswith("["):
        end += 1
    block = [head]
    block += [ln for ln in lines[start + 1:end] if ln.startswith("script = ")]
    for k, v in props.items():
        block.append(f"{k} = {str(v).lower()}" if isinstance(v, bool)
                     else f"{k} = {v}")
    out = lines[:start] + block + [""] + lines[end:]
    while out and out[-1] == "":
        out.pop()
    scene.write_text("\n".join(out) + "\n", encoding="utf-8", newline="\n")


def prepare(package: Path, work: Path, godot: str) -> Path:
    """Build the walk copy once: package + shipped warm-up + camera + probe.

    The warm-up is put in by `packages.exporting.warmup.emit`, the same call
    the exporter makes, so what is measured is what a package ships and not a
    hand-wired approximation of it.
    """
    pkg = work / "pkg"
    if pkg.exists():
        print(f"[prep] reusing walk copy at {pkg}")
        return pkg
    print(f"[prep] copying {package} -> {pkg}")
    shutil.copytree(package, pkg)
    report = warmup_mod.emit(pkg)
    print("[prep] warm-up emitted: " + json.dumps(
        {k: report[k] for k in ("wired", "script_shipped", "warmup_nodes")}))
    shutil.copy2(PROBE, pkg / PROBE_NAME)
    print("[prep] walk camera: " + _add_camera(pkg))

    gd = (pkg / "project.godot").read_text(encoding="utf-8")
    if "[autoload]" in gd:
        raise SystemExit("the package already has an [autoload] block")
    # The probe times the gap between `_process` calls. With vsync on, every
    # frame under the refresh interval reads as the refresh interval, which
    # would floor every mean in the table and make the fast configurations
    # indistinguishable from each other.
    gd += ("\n[autoload]\n"
           f'FirstSight="*res://{PROBE_NAME}"\n'
           "\n[display]\n"
           "window/vsync/vsync_mode=0\n")
    (pkg / "project.godot").write_text(gd, encoding="utf-8")

    print("[prep] importing (headless)")
    t0 = time.time()
    subprocess.run([godot, "--headless", "--path", str(pkg), "--import"],
                   capture_output=True, text=True, timeout=1800)
    print(f"[prep] import took {time.time() - t0:.0f} s; "
          f".godot exists={(pkg / '.godot').is_dir()}")
    return pkg


def run_once(pkg: Path, godot: str, cache_dir: Path, *, label: str,
             timeout: int) -> dict:
    """One launch. Returns what the run printed about itself, plus the clock."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    before = _dir_bytes(cache_dir)

    shader_cache = (_APPDATA / "Godot" / "app_userdata" / _project_name(pkg)
                    / "shader_cache")
    if shader_cache.is_dir():
        shutil.rmtree(shader_cache, ignore_errors=True)

    env = dict(os.environ)
    env["__GL_SHADER_DISK_CACHE"] = "1"
    env["__GL_SHADER_DISK_CACHE_PATH"] = str(cache_dir)
    env["__GL_SHADER_DISK_CACHE_SKIP_CLEANUP"] = "1"

    before_pids = _godot_pids()
    t0 = time.time()
    proc = subprocess.Popen(
        [godot, "--path", str(pkg), "--resolution", "1280x720"],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        env=env, bufsize=1)
    # Godot on Windows launches a console companion, so "mine" is every PID
    # that was not there a moment ago, not just `proc.pid`.
    # REFUTED FIRST VERSION, kept because it read as a clean result: `mine`
    # was `before_pids | {proc.pid} | new`, which is every Godot on the
    # machine, so a Godot another agent had ALREADY started counted as this
    # run's own and every row reported "no contention". A zero an instrument
    # cannot avoid printing is not a measurement. Mine is this process and
    # whatever appeared with it; anything that was already there is foreign.
    watch = _Contention({proc.pid} | (_godot_pids() - before_pids),
                        foreign_at_start=len(before_pids))
    lines: list[str] = []
    load_s = None
    scene_s = None
    try:
        for line in proc.stdout:
            line = line.rstrip()
            lines.append(line)
            if load_s is None and _WARMUP_DONE.search(line):
                load_s = time.time() - t0
            if scene_s is None and "scene instantiated ok" in line:
                scene_s = time.time() - t0
            if time.time() - t0 > timeout:
                proc.kill()
                lines.append("[sweep] TIMEOUT")
                break
        proc.wait(timeout=60)
    finally:
        if proc.poll() is None:
            proc.kill()
    rc = proc.returncode
    total_s = time.time() - t0
    contention = watch.stop()
    grew = _dir_bytes(cache_dir) - before

    text = "\n".join(lines)
    plan = _WARMUP_PLAN.search(text)
    plan0 = _WARMUP_PLAN_0100.search(text)
    done = _WARMUP_DONE.search(text)
    laps = {int(m.group(1)): {
        "frames": int(m.group(2)), "mean_ms": float(m.group(3)),
        "over_pct": float(m.group(4)), "worst_ms": float(m.group(5))}
        for m in _LAP.finditer(text)}
    return {
        "label": label,
        "stations": int(plan.group(1)) if plan else (
            int(plan0.group(1)) if plan0 else 0),
        "grid_stations": int(plan.group(2)) if plan else None,
        "grid_stride_m": float(plan.group(3)) if plan else None,
        "sweep_frames": int(done.group(1)) if done else 0,
        "sweep_ms": float(done.group(2)) if done else None,
        "load_s": load_s,
        "scene_s": scene_s,
        "total_s": total_s,
        "cache_grew_bytes": grew,
        "returncode": rc,
        "started_at": t0,
        "ended_at": t0 + total_s,
        "contention": contention,
        "laps": laps,
        "log": lines,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--package", default=str(
        Path("C:/Projects/gabagool_studios/gabagool_factory/workspaces/"
             "cold-9066-ws/.level_factory/exports/"
             "LF_club_block_005.portable-godot")))
    ap.add_argument("--work", required=True)
    ap.add_argument("--godot", default=os.environ.get(
        "DC_GODOT", r"C:\Godot\4.7\Godot_v4.7-stable_win64.exe"))
    ap.add_argument("--configs", required=True,
                    help="path to a JSON list of {name, props, script?}")
    ap.add_argument("--timeout", type=int, default=600)
    ap.add_argument("--out", required=True)
    ap.add_argument("--prepare-only", action="store_true")
    args = ap.parse_args()

    work = Path(args.work)
    work.mkdir(parents=True, exist_ok=True)
    pkg = prepare(Path(args.package), work, args.godot)
    if args.prepare_only:
        return 0

    configs = json.loads(Path(args.configs).read_text(encoding="utf-8"))
    out_path = Path(args.out)
    rows: list[dict] = []
    if out_path.is_file():
        rows = json.loads(out_path.read_text(encoding="utf-8"))
    # Both halves, or the configuration is not done: a run interrupted after
    # its cold row would otherwise be skipped forever with no warm row, and
    # the table would be missing a cell nobody looked for.
    seen: dict[str, set] = {}
    for r in rows:
        name, _, state = r["label"].rpartition(":")
        seen.setdefault(name, set()).add(state)
    done_names = {n for n, states in seen.items()
                  if {"cold", "warm"} <= states}

    for cfg in configs:
        name = cfg["name"]
        if name in done_names:
            print(f"[sweep] {name}: already measured, skipping")
            continue
        # A row may name its own copy of the script, so the version this
        # branch replaced runs through the identical harness as the control.
        # Without that, every number here would be comparable only with the
        # other numbers here.
        src = Path(cfg.get("script", warmup_mod.WARMUP_SCRIPT))
        (pkg / warmup_mod.SCRIPT_NAME).write_bytes(src.read_bytes())
        _set_node_props(pkg, cfg.get("props", {}))
        cache = work / "glcache" / name
        shutil.rmtree(cache, ignore_errors=True)
        for state in ("cold", "warm"):
            label = f"{name}:{state}"
            # A run that printed no LAP line measured nothing. It has
            # happened three times on this machine, silently: no crash
            # backtrace, no error, the process simply gone mid-sweep while a
            # second agent was tidying up stray Godots. A retry is cheap; a
            # missing row that looks like a fast configuration is not. A COLD
            # retry has to start from an empty cache or it is a warm run
            # wearing a cold label.
            attempts = 0
            while True:
                attempts += 1
                if state == "cold":
                    shutil.rmtree(cache, ignore_errors=True)
                print(f"[sweep] {label} (attempt {attempts}) ...", flush=True)
                row = run_once(pkg, args.godot, cache, label=label,
                               timeout=args.timeout)
                if row["laps"] or attempts >= 3:
                    break
                print("[sweep] %s: no lap report after %.0f s (rc=%s) -- "
                      "retrying" % (label, row["total_s"], row["returncode"]),
                      flush=True)
            row["attempts"] = attempts
            row["props"] = cfg.get("props", {})
            lap1 = row["laps"].get(1, {})
            print("[sweep] %-22s stations=%3d load=%s sweep=%s ms "
                  "lap1 worst=%s mean=%s  cache+%d B"
                  % (label, row["stations"],
                     "%.1f s" % row["load_s"] if row["load_s"] else "-",
                     "%.0f" % row["sweep_ms"] if row["sweep_ms"] else "-",
                     lap1.get("worst_ms", "?"), lap1.get("mean_ms", "?"),
                     row["cache_grew_bytes"]), flush=True)
            if (row["contention"]["contended_samples"]
                    or row["contention"]["foreign_at_start"]):
                print("[sweep] %-22s CONTENDED: another Godot was running for "
                      "%d of %d samples (peak %d, %d already running at "
                      "launch)"
                      % (label, row["contention"]["contended_samples"],
                         row["contention"]["samples"],
                         row["contention"]["peak_foreign_godot"],
                         row["contention"]["foreign_at_start"]), flush=True)
            rows.append(row)
            out_path.write_text(json.dumps(rows, indent=1), encoding="utf-8")
    print(f"[sweep] {len(rows)} row(s) -> {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
