"""The placement gate is a gate: a MISMATCH fails the compose job.

`run_presentation_compose.py` printed Deli Counter's placement verdict and
returned 0 either way from cold run 9001 to 9012 -- 9005: 400 of 430 modules
on their greybox slot, 9012's bank: 224 of 242 -- while the z-fight gate
beside it returned 3. The eighteen it named on the bank were wall remainders
standing across their walls, and the walker found one. These pin the gate's
line, its error, and that a clean verdict carries no error.
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


BANK_9012 = {
    "checked": 242, "matched": 224, "mismatched": 18, "ok": False,
    "mismatches": [
        {"slot": "ext_-1_E_seg10", "stem": "wallEnd_delco_1997_01",
         "fit_rot": 0, "greybox_extent": [0.3, 3.3, 1.7],
         "placed_extent": [1.7, 3.3, 0.3]},
        {"slot": "int_0_1_seg1", "stem": "wallEnd_delco_1997_02",
         "fit_rot": 0, "greybox_extent": [0.3, 3.3, 1.875],
         "placed_extent": [1.875, 3.3, 0.3]},
    ],
}


def test_a_mismatch_is_an_error_that_names_the_slots():
    line, err = _driver().placement_gate(BANK_9012)
    assert line == ("[compose] placement gate [MISMATCH]: 224/242 modules sit "
                    "on the greybox collision")
    assert err is not None and err.startswith("[compose] ERROR")
    assert "int_0_1_seg1 (wallEnd_delco_1997_02)" in err
    assert "placed [1.875, 3.3, 0.3] on greybox [0.3, 3.3, 1.875]" in err
    assert "and 16 more" in err


def test_a_clean_verdict_carries_no_error():
    line, err = _driver().placement_gate(
        {"checked": 242, "matched": 242, "mismatched": 0, "ok": True,
         "mismatches": []})
    assert line.startswith("[compose] placement gate [OK]: 242/242")
    assert err is None


def test_the_driver_returns_its_own_code_for_the_gate():
    """Distinct from the z-fight (3), ladder (4) and circulation (6) reds, so a
    job log says which gate closed."""
    src = _SCRIPT.read_text(encoding="utf-8")
    assert "if placement_error:" in src
    assert src.count("return 7") == 1
