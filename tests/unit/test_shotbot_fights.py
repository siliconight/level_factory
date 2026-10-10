"""The walk's visual check fails a fight, not a sparkle (0.172.0, roadmap 225).

A z-fight swaps a pixel between two surfaces' colours; texture sparkle shifts it by a sub-pixel
blend of one texture. Measured on the shot bot's sampled grid: a control of two quads, red and
blue, 0.01 mm apart, flips every sample it flips by 255 of 255; cold run 9222's five stations flip
by a median of 16 to 19, with at most 7.6% of flips over 64. The verdict counts flips over 64.

`shot_bot.gd` needs a display, which this suite does not have, so its change is held here by
reading the script; the runs that proved it are in the changelog. The summary line is Python.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from packages.preview import walk_bot  # noqa: E402

_SHOT_BOT = (ROOT / "assets" / "godot" / "shot_bot.gd").read_text(encoding="utf-8")


def _const(name):
    m = re.search(r"^const %s := ([0-9.]+)" % name, _SHOT_BOT, re.M)
    assert m, name
    return float(m.group(1))


def test_a_fight_is_a_flip_over_64_and_fails_past_half_a_percent():
    assert _const("FIGHT_DELTA") == 64
    assert _const("FIGHT_FAIL_PCT") == 0.5
    assert "JITTER_FAIL_PCT" not in _SHOT_BOT          # the old count is not a verdict


def test_the_verdict_reads_fights_and_not_every_change():
    shoot = _SHOT_BOT[_SHOT_BOT.find("func _shoot"):_SHOT_BOT.find("func _frame")]
    assert re.search(r'st\["ok"\] = float\(jd\["fight_pct"\]\) \* 100\.0 <= FIGHT_FAIL_PCT',
                     shoot)
    diff = _SHOT_BOT[_SHOT_BOT.find("func _jitter_diff"):]
    assert "if d > FIGHT_DELTA:" in diff and '"fight_pct"' in diff


def test_the_calibration_is_between_the_control_and_the_sparkle():
    # the measured control and worst sparkle, as the constants' comment states them
    control, sparkle = 2.02, 0.12
    assert sparkle < _const("FIGHT_FAIL_PCT") < control
    assert "2.02% on the control" in _SHOT_BOT and "0.12% on 9222" in _SHOT_BOT


def test_the_summary_names_fighting_and_notes_sparkle():
    ok, lines = walk_bot.summarize(None, {"stations": [
        {"station": "base", "ok": True, "jitter_pct": 3.64, "fight_pct": 0.12,
         "void_pct": 0.0, "sparkle": True},
        {"station": "wall", "ok": False, "jitter_pct": 2.02, "fight_pct": 2.02,
         "void_pct": 88.8, "reason": "2.02% of pixels swap colour"}]})
    assert not ok
    assert "fighting 0.12%" in lines[0] and "sparkle" in lines[0]
    assert "[FAIL] wall" in lines[1] and "fighting 2.02%" in lines[1]


def test_a_verdict_from_before_still_reads():
    ok, lines = walk_bot.summarize(None, {"stations": [
        {"station": "old", "ok": True, "jitter_pct": 0.5, "void_pct": 1.0}]})
    assert ok and lines[0] == "  shot bot [OK] old: jitter 0.5%, void 1.0%"
