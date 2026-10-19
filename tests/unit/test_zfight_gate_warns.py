"""The z-fight gate says WARN, which is what the pipeline does with it (0.218.1, factory roadmap 177).

`run_presentation_compose.py` printed `z-fight gate [FAIL]` and `ERROR: coplanar surfaces detected` over a job the
scheduler records SUCCEEDED (the compose job is `exit_advisory`) and a finding the presentation adapter files as
moderate and not blocking. The decision 177 owed -- block, warn or delete -- was made 2026-10-19, meant to be
changed: warn now, block once the library counts zero.

Run: python -m pytest -q tests/unit/test_zfight_gate_warns.py
"""
import importlib.util
import sys
from pathlib import Path

_SCRIPT = (Path(__file__).resolve().parents[2] / "assets" / "scripts"
           / "run_presentation_compose.py")


def _driver():
    spec = importlib.util.spec_from_file_location("run_presentation_compose", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


#: cold run 9322's office, as its compose summary read it
OFFICE_9322 = {"ok": False, "pairs": 2, "solids": 425, "scene": "site.tscn", "buried_pairs": 129,
               "greybox_internal_pairs": 0,
               "findings": [{"a": "base:VAULTLEDGE_0", "b": "reception_desk", "axis": 0, "plane": 2.5,
                             "side": "max", "area": 0.2},
                            {"a": "base:VAULTLEDGE_0", "b": "reception_desk", "axis": 0, "plane": -2.5,
                             "side": "min", "area": 0.2}]}


def test_pairs_are_a_warning_line():
    line, warn = _driver().zfight_gate(OFFICE_9322)
    assert line == "[compose] z-fight gate [WARN]: 2 coplanar pair(s) across 425 solids", line
    assert "[FAIL]" not in line


def test_the_warning_names_the_pairs_and_where_the_verdict_lives():
    _line, warn = _driver().zfight_gate(OFFICE_9322)
    assert warn.startswith("[compose] WARNING: 2 coplanar pair(s)"), warn
    assert "base:VAULTLEDGE_0 / reception_desk" in warn
    assert "PRESENTATION_ZFIGHT, moderate and not blocking" in warn
    assert "ERROR" not in warn


def test_a_clean_check_carries_no_warning():
    line, warn = _driver().zfight_gate({"ok": True, "pairs": 0, "solids": 233})
    assert line == "[compose] z-fight gate [OK]: 0 coplanar pair(s) across 233 solids"
    assert warn is None


def test_the_runner_prints_no_zfight_error_and_keeps_its_advisory_exit():
    src = _SCRIPT.read_text(encoding="utf-8")
    assert "coplanar surfaces detected -- the package would flicker" not in src
    assert '"OK" if z.get("ok") else "FAIL"' not in src
    assert "if zwarn:" in src and src.count("return 3") == 1


def test_the_call_is_recorded_as_one_that_can_change():
    src = _SCRIPT.read_text(encoding="utf-8")
    assert "block once the library counts zero" in src and "meant to be changed" in src
