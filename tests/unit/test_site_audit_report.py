"""Lot's site audit reaches the validation report (0.163.0, roadmap 215).

Lot runs `site_audit` at the end of every assembly: exfil shape, responder
pressure, safe anchors, leg rhythm, street crossings. Until Lot 0.102.0 it
printed the findings to the job log and kept none, so this report -- and every
cold run's findings diff, which counts this report's codes -- never carried an
`S_` code. Measured on cold run 9209's seed_9181: the job log printed one MED
(`S_RESPONDER_ARC`) and three INFO (`S_GETAWAY_AT_SPAWN`, `S_STREET_CROSS`
twice), and `validation/club_block_014.json` carried no `S_` code.

Lot 0.102.0 keeps the audit as `site_audit` in `<stem>.site.gameplay.json`;
`adapters.lot.normalize_validation` reads it. No block, or one this adapter
cannot read, is LOT_SITE_AUDIT_UNREAD -- an absent audit and a clean one must
not look alike.
"""
from __future__ import annotations

import importlib
import json
import re
import sys

import pytest

import adapters.lot as lot_adapter
from adapters.lot import LotAdapter
from tests.siblings import not_found, sibling_repo

#: The file the tests below read and import from (`tests/siblings.py`).
_AUDIT = "site_audit.py"
LOT = sibling_repo("lot", marker=_AUDIT)


def _site_audit():
    assert LOT is not None, not_found("lot", marker=_AUDIT)
    if str(LOT) not in sys.path:
        sys.path.insert(0, str(LOT))
    return importlib.import_module("site_audit")


def _issues(tmp_path, doc):
    p = tmp_path / "site.site.gameplay.json"
    p.write_text(json.dumps(doc), encoding="utf-8")
    return [i for i in LotAdapter().normalize_validation([p])
            if str(i["code"]).startswith(("S_", "LOT_SITE_AUDIT"))]


#: A site shaped like cold run 9209's seed_9181 where it matters: the crew's
#: van at its spawn, three responder stops inside a few degrees of each other,
#: and both legs across a road.
SITE_9181_SHAPE = {
    "name": "site", "mode": "heist",
    "buildings": [{"id": "obj", "at": [0, 40]}],
    "spawn": "obj", "objective": "obj", "extraction": "obj",
    "site_markers": [
        {"type": "crew_spawn", "at": [0, -40]},
        {"type": "extraction", "at": [0, -40], "getaway": "step_van"},
        {"type": "objective", "at": [0, 40]},
        {"type": "responder_spawn", "at": [60, 50]},
        {"type": "responder_spawn", "at": [62, 46]},
        {"type": "responder_spawn", "at": [64, 42]},
    ],
    "cover": [{"at": [0, -36], "size": [4, 1.5, 1.8]}],
    "roads": [{"a": [-80, 0], "b": [80, 0]}],
    "blockers": [],
}


def test_every_finding_lot_keeps_reaches_the_report(tmp_path):
    """Lot's own audit and Lot's own record, read by this adapter: the four
    codes 9209's job log printed, at this model's severities, none blocking."""
    sa = _site_audit()
    block = sa.record(sa.audit(SITE_9181_SHAPE))
    kept = sorted((f["severity"], f["code"]) for f in block["findings"])
    assert kept == [("INFO", "S_GETAWAY_AT_SPAWN"), ("INFO", "S_STREET_CROSS"),
                    ("INFO", "S_STREET_CROSS"), ("MED", "S_RESPONDER_ARC")], kept
    got = _issues(tmp_path, {"site_audit": block})
    assert sorted((i["severity"], i["code"]) for i in got) == [
        ("info", "S_GETAWAY_AT_SPAWN"), ("info", "S_STREET_CROSS"),
        ("info", "S_STREET_CROSS"), ("moderate", "S_RESPONDER_ARC")], got
    assert not any(i["blocking"] for i in got)
    arc = next(i for i in got if i["code"] == "S_RESPONDER_ARC")
    assert "arc around the objective" in arc["message"], arc["message"]


def test_no_block_is_said_out_loud(tmp_path):
    """Lot before 0.102.0, or a manifest that lost the block: one
    LOT_SITE_AUDIT_UNREAD, never silence."""
    got = _issues(tmp_path, {"pacing": {"status": "within target"}})
    assert [i["code"] for i in got] == ["LOT_SITE_AUDIT_UNREAD"], got
    assert got[0]["blocking"] is False
    assert "0.102.0" in got[0]["message"]


def test_a_clean_audit_says_nothing(tmp_path):
    clean = {"mode": "heist", "counts": {"HIGH": 0, "MED": 0, "INFO": 0}, "findings": []}
    assert _issues(tmp_path, {"site_audit": clean}) == []


@pytest.mark.parametrize("block", [
    ["MED", "S_BARE_LEG", "positions, not fields"],
    {"counts": {"MED": 1}},
    {"findings": {"S_BARE_LEG": "MED"}},
    {"findings": [["MED", "S_BARE_LEG", "a tuple's positions"]]},
    {"findings": [{"severity": "LOW", "code": "S_BARE_LEG", "message": "m"}]},
    {"findings": [{"severity": ["MED"], "code": "S_BARE_LEG", "message": "m"}]},
    {"findings": [{"severity": "MED", "message": "no code"}]},
    {"findings": [{"severity": "MED", "code": "", "message": "empty code"}]},
], ids=["list", "no-findings", "findings-not-a-list", "finding-not-a-dict",
        "unknown-severity", "unhashable-severity", "no-code", "empty-code"])
def test_a_shape_this_cannot_read_is_not_a_pass(tmp_path, block):
    got = _issues(tmp_path, {"site_audit": block})
    assert [i["code"] for i in got] == ["LOT_SITE_AUDIT_UNREAD"], got
    assert got[0]["blocking"] is False


def test_nothing_the_audit_says_blocks(tmp_path):
    """Report-only, like Deli Counter's combat_audit: HIGH is a major, and
    still not a blocker."""
    block = {"findings": [{"severity": "HIGH", "code": "S_TEST", "message": "m"}]}
    (got,) = _issues(tmp_path, {"site_audit": block})
    assert (got["severity"], got["blocking"]) == ("major", False)


def test_the_adapter_knows_every_severity_lot_writes():
    """Read from Lot's source, so a severity Lot adds fails here rather than
    surfacing as LOT_SITE_AUDIT_UNREAD on every level."""
    assert LOT is not None, not_found("lot", marker=_AUDIT)
    src = (LOT / _AUDIT).read_text(encoding="utf-8")
    written = set(re.findall(r'F\(\("([A-Z]+)", "S_', src))
    assert written, "no `F((\"SEV\", \"S_...` in site_audit.py: this pattern is stale"
    counted = set(re.findall(r'"([A-Z]+)": 0', src))
    assert written <= counted, (written, counted)
    assert counted == set(lot_adapter.LOT_SITE_AUDIT_SEVERITY), counted
