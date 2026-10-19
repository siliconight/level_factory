"""The greybox census's verdict, on synthetic reports (0.218.0, factory roadmap 168).

`packages.exporting.greybox_skin.assert_skinned` refused on slabs only and reported the rest; since 0.218.0 it
refuses any greybox surface in a themed package, behind `ExportProfile.require_no_greybox` (default on). The
measurement half is `assets/godot/greybox_census.gd`; these pin what the verdict does with a report. The verdict
had no unit test before this file.

Run: python -m pytest -q tests/unit/test_greybox_skin_verdict.py
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from packages.exporting import greybox_skin as G  # noqa: E402
from packages.exporting.export import ExportProfile  # noqa: E402


def _report(by_role, slabs=0, themed=True, worst=()):
    n = sum(int(r["surfaces"]) for r in by_role.values())
    return {"schema": G.SCHEMA, "themed": themed, "greybox_surfaces": n, "slab_surfaces": slabs,
            "by_role": by_role, "worst": list(worst), "nothing_to_check": not themed}


#: cold run 9321's package, as its census read it: the three vault ledges, nothing else
LEDGES = _report({"gb_floor": {"area_m2": 49.73, "surfaces": 3}},
                 worst=[{"node": "Bake/Site/b0/GreyboxBase/VAULTLEDGE_1", "material": "gb_floor", "area_m2": 20.16}])


def test_a_greybox_slab_is_refused_as_it_was(tmp_path):
    rep = _report({"gb_floor": {"area_m2": 10.4, "surfaces": 8}}, slabs=8,
                  worst=[{"node": "Bake/Site/b0/GreyboxBase/slab_1_t0_0", "material": "gb_floor"}])
    for any_role in (True, False):
        with pytest.raises(G.GreyboxSkinError) as err:
            G.assert_skinned(tmp_path, rep, any_role=any_role)
        assert "GREYBOX_SLAB_IN_A_THEMED_PACKAGE: 8" in str(err.value)


def test_a_greybox_vault_ledge_is_refused(tmp_path):
    with pytest.raises(G.GreyboxSkinError) as err:
        G.assert_skinned(tmp_path, LEDGES)
    msg = str(err.value)
    assert "GREYBOX_IN_A_THEMED_PACKAGE: 3 surface(s)" in msg and "gb_floor 3" in msg
    assert "VAULTLEDGE_1" in msg and "require_no_greybox = False" in msg


def test_the_switch_off_reports_without_refusing(tmp_path):
    assert G.assert_skinned(tmp_path, LEDGES, any_role=False) is LEDGES
    assert "the class this gate refuses on" in G.summary(LEDGES, any_role=False)


def test_a_clean_themed_package_passes(tmp_path):
    clean = _report({})
    assert G.assert_skinned(tmp_path, clean) is clean
    assert "0 surface(s) on a greybox material (none), 0 of them slabs" in G.summary(clean)


def test_an_unthemed_package_is_never_refused(tmp_path):
    grey = _report({"gb_floor": {"area_m2": 900.0, "surfaces": 400}}, slabs=346, themed=False)
    assert G.assert_skinned(tmp_path, grey) is grey
    assert "no theming was applied" in G.summary(grey)


def test_the_summary_says_any_one_is_refused():
    assert "any one is refused (require_no_greybox)" in G.summary(LEDGES)


def test_the_profile_refuses_by_default():
    assert ExportProfile.__dataclass_fields__["require_no_greybox"].default is True
