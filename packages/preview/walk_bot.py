"""Run the headless traversal + visual bots over a built walk preview and turn
their JSON verdicts into a pass/fail a pipeline can gate on.

Why this lives here and not in the GDScript: the bots must run inside Godot (they
need the physics server and the renderer), but *deciding what to do about the
answer* is orchestration, and orchestration belongs in Python where it is
testable without a game engine. This module never imports Godot; it shells out
and reads a file, so its own tests run in milliseconds against a fake engine.

The two bots answer different questions and neither subsumes the other:

  walk_bot.gd   Can a player capsule actually get where the level says it can?
                Colliders, climb areas, slab cuts. A physics proof.
  shot_bot.gd   Does it look like a building when you stand in it? Coplanar
                surfaces fighting for the depth test, and how much of the frame
                is nothing at all. A render proof -- invisible to physics,
                because a z-fighting wall collides perfectly.

The visual bot needs a display. That is a real constraint, not a bug to code
around: an offscreen renderer that lies about what a player sees would be worse
than no check. Where there is no display the visual pass is SKIPPED and says so
-- a skip is reported honestly and never silently counted as a pass.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

# The walk bot writes its verdict to a file and also exits non-zero on failure.
# We read the FILE, not the exit code: Godot exits non-zero for its own reasons
# (a missing driver, an audio device it could not open), and mistaking engine
# noise for a level defect would make the gate untrustworthy in exactly the way
# that gets gates disabled.
WALK_SCRIPT = "res://walk_bot.gd"
SHOT_SCRIPT = "res://shot_bot.gd"


class BotUnavailable(RuntimeError):
    """The engine could not be run at all -- distinct from a level failing."""


def _run(argv, timeout):
    try:
        return subprocess.run(argv, capture_output=True, text=True,
                              timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        raise BotUnavailable(
            f"bot did not finish within {timeout}s: {' '.join(argv)}") from exc
    except OSError as exc:
        raise BotUnavailable(f"could not launch {argv[0]}: {exc}") from exc


def _read_verdict(path: Path, proc, what: str) -> dict:
    if not path.exists():
        tail = (proc.stderr or proc.stdout or "").strip().splitlines()[-8:]
        raise BotUnavailable(
            f"{what} produced no verdict at {path}"
            + (("; engine said:\n  " + "\n  ".join(tail)) if tail else ""))
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BotUnavailable(f"{what} verdict at {path} is unreadable: {exc}")


def run_walk_bot(godot_exe, project_dir, *, out_json=None, timeout=600) -> dict:
    """Physics traversal proof. Returns the parsed verdict dict."""
    project_dir = Path(project_dir)
    out = Path(out_json) if out_json else project_dir / "walkbot.json"
    proc = _run([str(godot_exe), "--headless", "--path", str(project_dir),
                 "--script", WALK_SCRIPT, "--", str(out)], timeout)
    return _read_verdict(out, proc, "walk bot")


def display_wrapper() -> list[str]:
    """Command prefix that gives the visual bot a display, or [] if it already
    has one, or None if there is no way to get one here."""
    if os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"):
        return []
    xvfb = shutil.which("xvfb-run")
    # -a picks a free server number, so parallel missions don't collide.
    return [xvfb, "-a"] if xvfb else None


def run_shot_bot(godot_exe, project_dir, *, shots_dir=None, out_json=None,
                 timeout=900) -> dict:
    """Visual proof. Returns the parsed verdict dict, or a ``skipped`` record
    when this machine has no display to render into."""
    project_dir = Path(project_dir)
    out = Path(out_json) if out_json else project_dir / "shotbot.json"
    shots = Path(shots_dir) if shots_dir else project_dir / "shots"
    prefix = display_wrapper()
    if prefix is None:
        return {"skipped": True, "ok": None,
                "reason": "no display and no xvfb-run; the visual pass needs a "
                          "renderer (install xvfb, or run it on a desktop)"}
    proc = _run([*prefix, str(godot_exe), "--rendering-driver", "opengl3",
                 "--path", str(project_dir), "--script", SHOT_SCRIPT,
                 "--", str(out), str(shots)], timeout)
    return _read_verdict(out, proc, "shot bot")


def summarize(walk: dict | None, shot: dict | None) -> tuple[bool, list[str]]:
    """Fold both verdicts into (ok, human lines).

    A skipped visual pass does not fail the gate but is never silently dropped
    from the summary -- if a level ships unlooked-at, that should be visible in
    the log rather than inferred from an absence.
    """
    lines: list[str] = []
    ok = True

    if walk is not None:
        if walk.get("error"):
            lines.append(f"  walk bot: ERROR {walk['error']}")
            ok = False
        elif walk.get("note"):
            lines.append(f"  walk bot: {walk['note']}")
        for lad in walk.get("ladders") or []:
            name = lad.get("ladder", "?")
            if lad.get("ok"):
                lines.append(f"  walk bot [OK]   {name}: climbed to "
                             f"{lad.get('final_rel_y')} m and stood up")
                continue
            ok = False
            failed = [k for k in ("ground", "approach", "latch", "climb",
                                  "top_exit")
                      if not lad.get(k)] or (["fell"] if not
                                             lad.get("no_fall", True) else [])
            lines.append(f"  walk bot [FAIL] {name}: {', '.join(failed)}")
            stall = lad.get("stall") or {}
            if stall.get("reason"):
                lines.append(f"      {stall['reason']}")
            if lad.get("blocked_at"):
                lines.append(f"      stopped at {lad['blocked_at']}")

    if shot is not None:
        if shot.get("skipped"):
            lines.append(f"  shot bot: SKIPPED -- {shot.get('reason', '')}")
        elif shot.get("error"):
            lines.append(f"  shot bot: ERROR {shot['error']}")
            ok = False
        else:
            for st in shot.get("stations") or []:
                name = st.get("station", "?")
                tag = "OK" if st.get("ok") else "FAIL"
                lines.append(
                    f"  shot bot [{tag}] {name}: jitter {st.get('jitter_pct')}%"
                    f", void {st.get('void_pct')}%")
                if not st.get("ok"):
                    ok = False
                    if st.get("reason"):
                        lines.append(f"      {st['reason']}")
            if shot.get("stations"):
                lines.append(f"  frames written for review "
                             f"({len(shot['stations'])} stations)")
    return ok, lines
