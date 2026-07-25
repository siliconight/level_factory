"""The traversal/visual gate's decision layer, tested without a game engine.

The bots themselves are GDScript and need Godot; what is tested here is the
part that decides -- does this verdict fail the build, and does a human reading
the log learn what to go fix. That logic is where a gate goes wrong in the way
that matters: not by computing the wrong number, but by turning a real defect
into a line nobody reads, or by turning engine trouble into a level failure and
teaching everyone to pass --no-bot.

The fake engine is a shell script that writes a canned verdict, so these tests
cover the real subprocess path (argv, timeout, missing-file handling) at
millisecond cost.
"""
import json
import os
import stat
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from packages.preview import walk_bot  # noqa: E402


def _fake_godot(tmp_path: Path, verdict, *, exit_code=0, write=True) -> Path:
    """A stand-in engine: writes ``verdict`` to the out-json it is handed.

    The runner launches whatever path it is given as an executable, so the fake
    has to be one. A ``#!``-line script is not that on Windows (CreateProcess
    rejects it with WinError 193), so the body stays Python and the thing
    handed to the runner is a platform-native launcher: a ``.cmd`` shim under
    Windows, a shebang+exec-bit script everywhere else. Both forward argv and
    propagate the exit code, which is the whole point of the fixture.
    """
    body = tmp_path / "fake_godot_body.py"
    body.write_text(
        "import json, sys\n"
        f"write = {write!r}\n"
        # the out path is the argument right after the bare '--'
        "out = sys.argv[sys.argv.index('--') + 1]\n"
        "if write:\n"
        f"    open(out, 'w').write({json.dumps(verdict)!r})\n"
        "sys.stderr.write('fake engine noise\\n')\n"
        f"sys.exit({exit_code})\n",
        encoding="utf-8")

    if os.name == "nt":
        exe = tmp_path / "fake_godot.cmd"
        exe.write_text(
            "@echo off\r\n"
            f'"{sys.executable}" "{body}" %*\r\n'
            "exit /b %ERRORLEVEL%\r\n",
            encoding="utf-8")
        return exe

    exe = tmp_path / "fake_godot"
    exe.write_text(
        "#!/bin/sh\n"
        f'exec "{sys.executable}" "{body}" "$@"\n',
        encoding="utf-8")
    exe.chmod(exe.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return exe


PASS = {"ok": True, "error": "", "ladders": [
    {"ladder": "Ladder_0", "ok": True, "ground": True, "approach": True,
     "latch": True, "climb": True, "top_exit": True, "no_fall": True,
     "final_rel_y": 4.0}]}

STALL = {"ok": False, "error": "", "ladders": [
    {"ladder": "Ladder_0", "ok": False, "ground": True, "approach": True,
     "latch": True, "climb": False, "top_exit": False, "no_fall": True,
     "climb_height_reached": 1.9,
     "stall": {"blocker": "slab_col_1", "aperture_admits_capsule": False,
               "reason": "slab cut does not cover the climb column"}}]}


def test_verdict_is_read_from_the_file_not_the_exit_code(tmp_path: Path):
    # Godot exits non-zero for its own reasons (no audio device, no driver).
    # Trusting the exit code would report engine noise as a broken level.
    exe = _fake_godot(tmp_path, PASS, exit_code=1)
    got = walk_bot.run_walk_bot(exe, tmp_path)
    assert got["ok"] is True


def test_missing_verdict_is_engine_trouble_not_a_level_failure(tmp_path: Path):
    exe = _fake_godot(tmp_path, PASS, write=False)
    with pytest.raises(walk_bot.BotUnavailable) as err:
        walk_bot.run_walk_bot(exe, tmp_path)
    # the engine's own words must survive, or nobody can debug this
    assert "fake engine noise" in str(err.value)


def test_a_clean_traversal_passes(tmp_path: Path):
    ok, lines = walk_bot.summarize(PASS, None)
    assert ok
    assert any("[OK]" in ln and "Ladder_0" in ln for ln in lines)


def test_a_stalled_climb_fails_and_says_why(tmp_path: Path):
    ok, lines = walk_bot.summarize(STALL, None)
    assert not ok
    blob = "\n".join(lines)
    assert "climb" in blob and "top_exit" in blob
    # the diagnosis, not just the verdict -- otherwise it is back to Blender
    # to guess
    assert "slab cut does not cover the climb column" in blob


def test_ladderless_package_passes_but_says_it_proved_nothing():
    ok, lines = walk_bot.summarize(
        {"ok": True, "error": "", "ladders": [],
         "note": "no ladder_area3d in scene; traversal vacuous"}, None)
    assert ok
    assert any("vacuous" in ln for ln in lines)


def test_zfighting_station_fails_the_visual_pass():
    shot = {"ok": False, "error": "", "stations": [
        {"station": "roof", "ok": False, "jitter_pct": 30.67, "void_pct": 0.01,
         "reason": "30.67% of pixels flip when the camera moves 1 mm"},
        {"station": "exterior", "ok": True, "jitter_pct": 0.01,
         "void_pct": 89.2}]}
    ok, lines = walk_bot.summarize(PASS, shot)
    assert not ok
    assert any("30.67" in ln for ln in lines)


def test_a_skipped_visual_pass_is_not_a_pass_and_not_a_failure():
    shot = {"skipped": True, "ok": None, "reason": "no display and no xvfb-run"}
    ok, lines = walk_bot.summarize(PASS, shot)
    assert ok, "no renderer is not the level's fault"
    assert any("SKIPPED" in ln for ln in lines), (
        "a level that shipped unlooked-at must say so in the log")


def _as_x11_host(monkeypatch):
    """Pin the platform so the X-server tests below mean the same thing on a
    Windows dev machine as they do in Linux CI."""
    monkeypatch.setattr(walk_bot, "_needs_x_display", lambda: True)


def test_headless_host_without_xvfb_reports_a_skip(tmp_path, monkeypatch):
    _as_x11_host(monkeypatch)
    monkeypatch.delenv("DISPLAY", raising=False)
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    monkeypatch.setattr(walk_bot.shutil, "which", lambda _n: None)
    got = walk_bot.run_shot_bot(_fake_godot(tmp_path, {}), tmp_path)
    assert got["skipped"] is True and got["ok"] is None


def test_an_existing_display_is_used_directly(monkeypatch):
    _as_x11_host(monkeypatch)
    monkeypatch.setenv("DISPLAY", ":0")
    assert walk_bot.display_wrapper() == []


def test_xvfb_is_allocated_a_free_server(tmp_path, monkeypatch):
    _as_x11_host(monkeypatch)
    monkeypatch.delenv("DISPLAY", raising=False)
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    monkeypatch.setattr(walk_bot.shutil, "which", lambda _n: "/usr/bin/xvfb-run")
    # -a matters: two missions checked at once must not fight over :99
    assert walk_bot.display_wrapper() == ["/usr/bin/xvfb-run", "-a"]


@pytest.mark.parametrize("plat", ["win32", "darwin", "cygwin"])
def test_a_desktop_os_without_DISPLAY_still_renders(monkeypatch, plat):
    """DISPLAY is an X11 variable. A Windows or macOS session has a window
    server and never sets it, so probing for it skipped the visual pass on
    every Windows dev machine while reporting it as a host limitation.
    """
    monkeypatch.setattr(walk_bot.sys, "platform", plat)
    monkeypatch.delenv("DISPLAY", raising=False)
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    monkeypatch.setattr(walk_bot.shutil, "which", lambda _n: None)
    assert walk_bot.display_wrapper() == [], (
        "a desktop OS must not be mistaken for a headless host")


def test_linux_is_still_probed(monkeypatch):
    # the other half of the contract: real headless Linux must keep skipping
    # rather than launching a renderer that cannot open a window
    monkeypatch.setattr(walk_bot.sys, "platform", "linux")
    monkeypatch.delenv("DISPLAY", raising=False)
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    monkeypatch.setattr(walk_bot.shutil, "which", lambda _n: None)
    assert walk_bot.display_wrapper() is None
