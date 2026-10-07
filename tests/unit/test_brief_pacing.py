"""The brief's pacing reaches Lot, and Lot's verdict reaches the operator
(0.153.0, roadmap 200).

Three disconnections on one dial, each measured 2026-10-07:

- `target_minutes` was written at the site spec's top level. Lot's
  `site_pacing._cfg` reads `pacing.target_minutes`, so every level was judged
  against Lot's default 7-15 min: 144 of 144 candidate specs on disk, while
  177 of 181 cold-run briefs ask for 25-35.
- The site spec carried no `mode`, and `site_pacing._critical_legs` builds
  travel legs only for heist, assault or survival, so the estimate counted no
  travel at all (cold run 9193: `"mode": null`).
- `adapters.lot.normalize_validation` raised LOT_PACING_OUTSIDE_TARGET only
  for a status containing "outside target". Lot writes four statuses
  (`site_pacing.estimate_pacing`); "likely TOO SHORT vs target" and "likely
  TOO LONG vs target" never matched, so the two verdicts that mean most were
  the two that never surfaced.

Setting the mode turns on Lot's heist gate (`site_tactical.gate`), which
raises -- the build fails -- unless spawn, objective and extraction are
joined. Measured before it was set: it passes on all 144 candidate specs on
disk (`docs/findings/brief_pacing_mode/heist_gate_census.py`).
"""
from __future__ import annotations

import importlib
import inspect
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

import apps.cli.commands as cmds
from adapters.lot import LotAdapter
from packages.core.models import MissionBrief
from tests.siblings import not_found, sibling_repo

#: The file the Lot tests below import from. It is the marker, not the
#: directory name (`tests/siblings.py`).
_PACING = "site_pacing.py"
LOT = sibling_repo("lot", marker=_PACING)


class _Workspace(SimpleNamespace):
    def load_tools_local(self) -> dict:
        return {"repositories": {}}


def _spec(tmp_path, **brief):
    out = tmp_path / "deli" / "out"
    out.mkdir(parents=True)
    (out / "shell.glb").write_bytes(b"glb")
    (out / "shell.gameplay.json").write_text("{}", encoding="utf-8")
    model = MissionBrief(mission_id="m", display_name="m", archetype="bank",
                         building_count=3, theme="delco", candidate_count=1,
                         lot_library=None, **brief)
    ws = _Workspace(jobs_dir=tmp_path / "jobs", internal_dir=tmp_path / "internal")
    p = cmds._write_site_spec(ws, model, tmp_path / "deli", seed=9021)
    return model, json.loads(Path(p).read_text(encoding="utf-8"))


def _lot(module):
    assert LOT is not None, not_found("lot", marker=_PACING)
    if str(LOT) not in sys.path:
        sys.path.insert(0, str(LOT))
    return importlib.import_module(module)


def test_the_window_is_written_where_lot_reads_it(tmp_path):
    _, spec = _spec(tmp_path, target_minutes=(20, 30))
    assert spec["pacing"]["target_minutes"] == [20, 30]


def test_the_site_spec_names_the_mode_deli_counter_builds(tmp_path):
    model, spec = _spec(tmp_path)
    assert spec["mode"] == "heist"
    assert cmds.mission_mode(model) == spec["mode"]


def test_lots_own_estimate_reads_the_window_and_counts_travel(tmp_path):
    _, spec = _spec(tmp_path, target_minutes=(20, 30))
    pacing = _lot("site_pacing").estimate_pacing(spec, {"markers": []})
    assert pacing["mode"] == "heist"
    assert pacing["target_min"] == "20-30 min", pacing["target_min"]
    travel = [b for b in pacing["breakdown"] if b["phase"].startswith("travel")]
    assert travel, pacing["breakdown"]


def test_lots_heist_gate_passes_on_a_written_spec(tmp_path):
    """A guard, not a regression proof: with no mode the gate returns without
    checking anything, so this passes on 0.152.0 too. With the mode it raises
    on a site whose spawn, objective and extraction are not joined."""
    _, spec = _spec(tmp_path)
    _lot("site_tactical").gate(spec)


def _issues(tmp_path, pacing):
    p = tmp_path / "site.site.gameplay.json"
    doc = {} if pacing is None else {"pacing": pacing}
    p.write_text(json.dumps(doc), encoding="utf-8")
    return [i for i in LotAdapter().normalize_validation([p])
            if str(i["code"]).startswith("LOT_PACING")]


@pytest.mark.parametrize("status", [
    "likely TOO SHORT vs target",
    "likely TOO LONG vs target",
    "partly outside target (range straddles the window)",
])
def test_every_verdict_outside_the_window_surfaces(tmp_path, status):
    got = _issues(tmp_path, {"status": status, "estimate_expected_min": 2.8,
                             "range_min": "1.8-3.8 min", "target_min": "25-35 min",
                             "breakdown": [{"phase": "travel b1->b0", "secs": 16.0},
                                           {"phase": "setup/positioning", "secs": 30}]})
    assert [i["code"] for i in got] == ["LOT_PACING_OUTSIDE_TARGET"], got
    assert got[0]["blocking"] is False
    assert status in got[0]["message"]


def test_the_adapter_knows_every_status_lot_writes():
    """Read from Lot's source, so a status Lot renames or adds fails here
    rather than surfacing as LOT_PACING_UNREAD on every level."""
    import re

    import adapters.lot as lot_adapter
    assert LOT is not None, not_found("lot", marker=_PACING)
    src = (LOT / _PACING).read_text(encoding="utf-8")
    written = set(re.findall(r'status = "([^"]+)"', src))
    assert written, "no `status = \"...\"` in site_pacing.py: this pattern is stale"
    assert written == set(lot_adapter.LOT_PACING_STATUSES), written


def test_within_the_window_says_nothing(tmp_path):
    assert _issues(tmp_path, {"status": "within target"}) == []


def test_a_status_nobody_wrote_down_is_not_read_as_a_pass(tmp_path):
    got = _issues(tmp_path, {"status": "ahead of schedule"})
    assert [i["code"] for i in got] == ["LOT_PACING_UNREAD"], got
    assert got[0]["blocking"] is False


def test_no_pacing_block_is_said_out_loud(tmp_path):
    got = _issues(tmp_path, None)
    assert [i["code"] for i in got] == ["LOT_PACING_UNREAD"], got


def test_the_brief_fields_nothing_builds_from_are_named():
    brief = {"route_shape": "push_then_backtrack", "objective_hypotheses": ["enter_bank"],
             "extraction_relationship": "crew_start_backtrack", "verticality": "medium",
             "landmark": "bank_clock", "archetype": "bank", "target_minutes": [25, 35]}
    assert cmds.unbuilt_brief_fields(brief) == [
        "route_shape", "objective_hypotheses", "extraction_relationship",
        "verticality", "landmark"]
    assert cmds.unbuilt_brief_fields({"archetype": "bank", "objective_hypotheses": []}) == []
    assert set(cmds.UNBUILT_BRIEF_FIELDS) <= set(MissionBrief.__dataclass_fields__)


def test_batch_create_says_them_out_loud():
    assert "unbuilt_brief_fields(" in inspect.getsource(cmds.cmd_batch_create)
