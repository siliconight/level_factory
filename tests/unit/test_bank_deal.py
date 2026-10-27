"""A bank's band is dealt the name Zoo gives its other faces (0.262.0).

Zoo 1.138.0 names a bank on its teller line, its time-and-temperature sign, its drive-up canopy and its door, every
one by `storefront_names`' rule, and the deal now starts there. FAILS ON 0.261.0: bank_branch_a02 was dealt MATTRESS
MONEY TRUST under a line saying YOUSE CREDIT CO-OP (the bank level, seed 9082).
"""
import importlib
import sys

import apps.cli.commands as cmds
from tests.siblings import sibling_repo
from tests.unit.test_signs_in_site_spec import _Workspace

ZOO = sibling_repo("zoo", marker="zoo_keeper/core/storefront_names.py")


def _slug_text(ws, slug):
    return next(s["text"] for s in cmds._sign_profile(ws, "delco_1997") if s["slug"] == slug)


def test_a_library_bank_is_dealt_zoos_name():
    ws = _Workspace()
    for shell in ("bank_branch_a02", "bank_branch_a03", "bank_branch_a04", "bank_job", "bank_tower_a01",
                  "credit_union_a01"):
        deal = cmds.deal_signs(ws, [{"id": "b0", "archetype": shell}], "delco_1997")
        assert _slug_text(ws, deal[shell]) == cmds.zoo_bank_name(shell), shell
    # the bank level's bank, by name
    deal = cmds.deal_signs(ws, [{"id": "b0", "archetype": "bank_branch_a02"}], "delco_1997")
    assert _slug_text(ws, deal["bank_branch_a02"]) == "YOUSE CREDIT CO-OP"


def test_two_banks_with_one_name_on_a_street_still_get_two():
    ws = _Workspace()
    # find two library shells Zoo names alike
    shells = ["bank_branch_a0%d" % i for i in range(1, 10)] + ["bank_job", "bank_tower_a01", "bank_tower_a02",
                                                               "bank_tower_a03", "credit_union_a01"]
    by_name = {}
    for s in shells:
        by_name.setdefault(cmds.zoo_bank_name(s), []).append(s)
    pair = next(v[:2] for v in by_name.values() if len(v) >= 2)
    deal = cmds.deal_signs(ws, [{"id": "b0", "archetype": pair[0]}, {"id": "b1", "archetype": pair[1]}], "delco_1997")
    assert deal[pair[0]] != deal[pair[1]]
    assert _slug_text(ws, deal[pair[0]]) == cmds.zoo_bank_name(pair[0])


def test_the_mirror_is_zoos_and_the_profiles():
    ws = _Workspace()
    banks = [s["text"] for s in cmds._sign_profile(ws, "delco_1997") if "bank" in (s.get("families") or [])]
    assert sorted(banks) == sorted(cmds.ZOO_BANK_NAMES)
    if ZOO is None:
        import pytest
        pytest.skip("no zoo checkout beside this repo")
    if str(ZOO) not in sys.path:
        sys.path.insert(0, str(ZOO))
    SN = importlib.import_module("zoo_keeper.core.storefront_names")
    names = next(n for kind, _m, n in SN.KINDS if kind == "bank")
    assert tuple(names) == cmds.ZOO_BANK_NAMES
    for shell in ("bank_branch_a02", "credit_union_a01", "bank_job"):
        assert SN.sign_for(shell)["text"] == cmds.zoo_bank_name(shell), shell
