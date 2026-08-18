"""The applied preset must be READ OFF LuxRoot, never the argument echoed back.

`lux.quality.json["preset"]` has always been the `--preset` argument written
straight back out, so comparing it against Level Factory's `_preset_for` -- the
comparison roadmap item 53 ranked first -- compares a string with itself. The
item said the file "already echoes the applied preset back". It echoed the
REQUEST. `preset_applied` is read from `LuxRoot.get_current_preset()`, whose
`_current` is assigned only by `_apply_immediate`, from the library resource.

THIS IS A SOURCE-SHAPE TEST AND IT IS ONE ON PURPOSE. Applying a preset needs a
Godot process and unit CI has no headless-Godot harness, so nothing here can
prove the driver works -- the hardware evidence is a run, not a test. What it
can prove is that nobody quietly re-points `preset_applied` back at
`preset_name`, which is the one regression that would restore the tautology
without changing a single output key or failing anything else.

Run:  python -m pytest tests/unit/test_lux_preset_readback.py
"""
import re
from pathlib import Path

import pytest

DRIVER = (Path(__file__).resolve().parents[2]
          / "assets" / "godot" / "run_lux_apply.gd")

# `preset_name` as a WHOLE word, not reached through a member access and not
# inside quotes -- so `cur.get("preset_name")`, which is the correct source,
# does not read as the argument.
_ARG = re.compile(r'(?<![.\w"])preset_name\b')
_ASSIGN = re.compile(r"^(?:var\s+)?reported\s*:?=[^=]")


@pytest.fixture(scope="module")
def src() -> str:
    assert DRIVER.is_file(), f"driver missing at {DRIVER}"
    return DRIVER.read_text(encoding="utf-8")


def test_the_applied_preset_comes_from_lux(src):
    assert "get_current_preset" in src


def test_the_applied_preset_is_never_assigned_from_the_argument(src):
    """An assignment is the bug. A comparison is the entire point of the fix,
    so `reported != String(preset_name)` must not trip this."""
    bad = []
    for line in src.splitlines():
        s = line.strip()
        if s.startswith("#") or "reported" not in s:
            continue
        if not _ASSIGN.match(s):
            continue
        if _ARG.search(s):
            bad.append(s)
    assert bad == [], bad


def test_the_comparison_this_test_protects_is_actually_present(src):
    """Without this, the test above passes trivially on a file that dropped
    the comparison altogether."""
    assert _ARG.search(src) is not None
    assert any("reported" in l and "!=" in l for l in src.splitlines())


def test_quality_json_reports_the_request_and_the_result_separately(src):
    assert '"preset": preset_name' in src
    assert '"preset_applied": reported' in src


def test_a_preset_that_did_not_apply_is_a_finding(src):
    assert "LUX_PRESET_NOT_APPLIED" in src


def test_a_failed_save_is_not_reported_as_applied(src):
    saves = [l for l in src.splitlines() if "ResourceSaver.save(" in l]
    assert saves, "driver no longer saves the applied scene"
    for line in saves:
        assert "!= OK" in line or "== OK" in line, line.strip()
