"""0.157.0 -- the package says how responders arrive (roadmap 212).

The walker, 2026-10-08: "have responders show up after the job, on the way
back (and this would be on the gameplay layer, but we can make thee assets
and ensure there is clearance and routes for their arrival)". Lot 0.99.0
plans each arrival and reserves its lane and its stop; Level Factory 0.156.0
puts each stop in `gameplay_anchors.json` as an `ai_spawn` tagged
`responder`. A Dispatch anchor holds a position and tags, so the rest -- the
road end a vehicle appears at, the lane, the stop's room, which way it faces
-- is `responder_arrivals.json`, keyed by that anchor's id.

The site is cold run 9200's seed_9054 as Lot wrote it: the van's two
markers, the three arrivals' markers and records, verbatim. The instruments
are the test's own: positions are turned to the package's frame here (x, y
up, z = -site y) and compared with what the export wrote.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from packages.exporting.export import (  # noqa: E402
    RESPONDER_ARRIVALS_NAME, ExportProfile, export_mission,
)
from packages.staging.dispatch_inputs import stage_dispatch_inputs  # noqa: E402

#: Cold run 9200, seed_9054's `responder_plan.arrivals`, verbatim.
ARRIVALS = [
    {"road": 1, "travel": -1, "entry": [-29.9, 29.5], "stop": [-29.9, -1.0], "yaw": 0.0,
     "vehicle": [2.0, 5.4, 1.5], "stop_box": [-31.9, -3.7, -27.9, 1.7],
     "lane_box": [-31.4, 1.7, -28.4, 29.5], "toward": [-29.858, -0.923],
     "to_way_back": 0.088, "run": 30.5},
    {"road": 0, "travel": 1, "entry": [-86.5, -22.55], "stop": [-14.0, -22.55], "yaw": 90.0,
     "vehicle": [2.0, 5.4, 1.5], "stop_box": [-16.7, -24.55, -11.3, -20.55],
     "lane_box": [-86.5, -24.05, -16.7, -21.05], "toward": [-8.545, -12.552],
     "to_way_back": 11.389, "run": 72.5},
    {"road": 0, "travel": -1, "entry": [86.5, -19.75], "stop": [7.0, -19.75], "yaw": 270.0,
     "vehicle": [2.0, 5.4, 1.5], "stop_box": [4.3, -21.75, 9.7, -17.75],
     "lane_box": [9.7, -21.25, 86.5, -18.25], "toward": [-4.15, -14.95],
     "to_way_back": 12.139, "run": 79.5},
]
VAN = [-4.15, -14.95]


def _gameplay(tmp_path, plan=True):
    gp = {"up_axis": "z", "markers": [],
          "site_markers": [{"type": "crew_spawn", "at": VAN, "source": "getaway_van"},
                           {"type": "extraction", "at": VAN, "source": "getaway_van",
                            "getaway": "step_van"}]
          + [{"type": "responder_spawn", "at": a["stop"], "source": "responder_arrival",
              "arrival": a} for a in ARRIVALS]}
    if plan:
        gp["responder_plan"] = {"arrivals": ARRIVALS, "findings": []}
    path = tmp_path / "site.site.gameplay.json"
    path.write_text(json.dumps(gp), encoding="utf-8")
    return path


def _export(tmp_path, lot_gameplay):
    handoff = tmp_path / "handoff"
    handoff.mkdir()
    (handoff / "mission.tscn").write_text("[gd_scene]\n", encoding="utf-8")
    # Something for the entry to instance: `write_entry_scene` replaces
    # mission.tscn with its own stub, and an entry that instances nothing is
    # refused (test_closure_export.py says why).
    (handoff / "site.tscn").write_text("[gd_scene]\n", encoding="utf-8")
    return export_mission(mission_id="m1", handoff_dir=handoff, presentation_dir=None,
                          source_dir=None, profile=ExportProfile(), tool_versions={},
                          out_root=tmp_path / "exports", lot_gameplay=lot_gameplay)


def _godot(p):
    return [p[0], 0.0, -p[1]]


def test_the_package_says_how_each_responder_arrives(tmp_path):
    result = _export(tmp_path, _gameplay(tmp_path))
    doc = json.loads((result.export_dir / RESPONDER_ARRIVALS_NAME).read_text(encoding="utf-8"))
    assert doc["schema"] == "level_factory.responder_arrivals.v1"
    assert len(doc["arrivals"]) == len(ARRIVALS)
    for got, a in zip(doc["arrivals"], ARRIVALS):
        assert got["entry"] == _godot(a["entry"]) and got["stop"] == _godot(a["stop"])
        dx, dz = got["stop"][0] - got["entry"][0], got["stop"][2] - got["entry"][2]
        n = math.hypot(dx, dz)
        assert math.isclose(got["forward"][0], dx / n, abs_tol=1e-6)
        assert math.isclose(got["forward"][2], dz / n, abs_tol=1e-6)
        x0, y0, x1, y1 = a["stop_box"]
        assert got["stop_box"] == {"min": [x0, -y1], "max": [x1, -y0]}
        assert got["vehicle_m"] == a["vehicle"]


def test_the_manifest_lists_it(tmp_path):
    """Inside the resource manifest, not merely on disk: the export's own
    guard holds the sum, and this names the file."""
    result = _export(tmp_path, _gameplay(tmp_path))
    manifest = json.loads((result.export_dir / "portable_resource_manifest.json")
                          .read_text(encoding="utf-8"))
    assert RESPONDER_ARRIVALS_NAME in {r["path"] for r in manifest["resources"]}


def test_each_arrival_names_the_anchor_the_staging_wrote(tmp_path):
    """One counting for both: the sidecar's ids are the `responder` anchors
    `stage_dispatch_inputs` gives Dispatch from the same gameplay."""
    gp = _gameplay(tmp_path)
    result = _export(tmp_path, gp)
    doc = json.loads((result.export_dir / RESPONDER_ARRIVALS_NAME).read_text(encoding="utf-8"))
    deli = tmp_path / "deli.json"
    deli.write_text(json.dumps({"up_axis": "z", "markers": []}), encoding="utf-8")
    stage_dispatch_inputs(tmp_path / "stage", deli_gameplay=deli, shell_glb=tmp_path / "none.glb",
                          lot_gameplay=gp, mission_id="m1")
    staged = json.loads((tmp_path / "stage" / "lot" / "lot.gameplay.json").read_text(encoding="utf-8"))
    ids = [a["id"] for a in staged["anchors"] if "responder" in (a.get("tags") or [])]
    assert [a["anchor"] for a in doc["arrivals"]] == ids


def test_no_lot_output_no_file(tmp_path):
    result = _export(tmp_path, None)
    assert not (result.export_dir / RESPONDER_ARRIVALS_NAME).exists()


def test_lot_output_from_before_0_99_no_file(tmp_path):
    """Lot output with no `responder_plan` (before Lot 0.99.0): the package
    is exactly what it was."""
    result = _export(tmp_path, _gameplay(tmp_path, plan=False))
    assert not (result.export_dir / RESPONDER_ARRIVALS_NAME).exists()
