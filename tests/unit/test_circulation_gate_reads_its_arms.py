"""The circulation gate's line reads each arm it was given (0.149.0).

Deli Counter writes `circulation_check` as two arms and a verdict when a
building has a greybox and a dressing layer: `{"ok", "shell", "dressing"}`.
The driver printed `len(circ["conflicts"])` and `circ.get("volumes", "?")`
from the top of that, so every cold run from 9164 to 9187 logged

    [compose] circulation gate [FAIL]: 0 prop conflict(s) across ? circulation volume(s)

-- a FAIL with nothing in it, on every building, which is a line nobody reads.
"""
import importlib.util
import sys
from pathlib import Path

_SCRIPT = (Path(__file__).resolve().parents[2] / "assets" / "scripts"
           / "run_presentation_compose.py")


def _driver():
    spec = importlib.util.spec_from_file_location("run_presentation_compose",
                                                  _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


TWO_ARMS = {"ok": False,
            "shell": {"ok": False, "volumes": 14, "props": 154,
                      "excused": [{"prop": "stair_guard_back_15",
                                   "volume": "stair:s0", "penetration": 0.34}],
                      "conflicts": [{"prop": "counter_island_upper_hall_2",
                                     "volume": "stair:deli_stair_up",
                                     "penetration": 0.8}]},
            "dressing": {"ok": True, "volumes": 14, "nodes": 8, "props": 249,
                         "conflicts": []}}


def test_the_line_reads_each_arm():
    line, details = _driver().circulation_gate(TWO_ARMS)
    assert line.startswith("[compose] circulation gate [FAIL]: ")
    assert "shell 1 conflict(s) across 14 volume(s), 1 excused" in line
    assert "dressing 0 conflict(s) across 14 volume(s)" in line
    assert details == ["[compose]   shell: counter_island_upper_hall_2 intrudes "
                       "0.8m into stair:deli_stair_up"]


def test_one_arm_reads_its_own_counts():
    line, details = _driver().circulation_gate(
        {"ok": True, "source": "shell", "volumes": 9, "props": 3, "conflicts": []})
    assert line == ("[compose] circulation gate [OK]: shell 0 conflict(s) "
                    "across 9 volume(s)")
    assert details == []


def test_an_arm_that_did_not_run_says_why():
    line, _ = _driver().circulation_gate(
        {"ok": False, "source": "dressing", "error": "gate failed to run: boom"})
    assert "dressing 0 conflict(s) across ? volume(s) (gate failed to run: boom)" in line
