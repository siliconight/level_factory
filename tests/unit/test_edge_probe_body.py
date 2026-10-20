"""The drop-edge probe models the body, not the lattice (0.222.0; the factory's roadmap 173, What is left item 7).

The factory's lattice phase sweep (`docs/findings/drop_edges_173/phase_sweep/`) moved the gate's 0.5 m lattice a
quarter cell at a time over three packages, and at one phase restaurant_row_001 -- which the shipped phase passes --
was refused, and its flood reached a quarter less of the level. Both were the standing probe's model of a body:

  * A KERB A BODY STEPS OVER OCCUPIED THE CELL BESIDE IT. The standing capsule, 0.20 m wide and 1.80 m tall stood on a
    hit, met the 8 cm face of a kerb 0.038 m from the cell, so every cell along that kerb read occupied -- a moat the
    flood could not cross to the office and the east ground. The capsule now stands `STEP_M` up, the contract's
    `clearances.unassisted_step_max_m` (0.1025): what a body walks over with no step-up does not occupy a cell.
  * A GAP NARROWER THAN A BODY READ AS A FALL. A 0.4 by 0.36 m slot between deli_a03's flight and its hole's unrailed
    edge was refused as an undeclared 3.3 m drop; the contract's body is 0.70 m across. Before a drop counts, a sphere
    of the body's radius is now sampled along the step, at the rim's level, `FIT_FROM` to `FIT_TO` past the cell: a
    drop no sample fits in is `too_narrow`, not a fall. Any hole 0.85 m or wider holds a sample, at every phase.

These run the real instrument through a real Godot over small scenes of boxes, the way `test_edge_seam.py` does, and
are skipped where no Godot is installed (`LF_GODOT`, then `DC_GODOT`, then `LOT_GODOT`, then the usual Windows path).

FAIL ON 0.221.0: the cell beside the kerb is occupied, the sidewalk and the ground past it are unreached, every slot
cell reads an unguarded drop, and there is no `STEP_M`.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from packages.exporting import drop_edges as D  # noqa: E402

EDGE = D.EDGE_SCRIPT  # the very file the export's gate runs
NEAR = D.CELL_M / 2 + 0.01


def _godot() -> str | None:
    for env in ("LF_GODOT", "DC_GODOT", "LOT_GODOT"):
        p = os.environ.get(env)
        if p and Path(p).is_file():
            return p
    usual = Path("C:/Godot/4.7/Godot_v4.7-stable_win64_console.exe")
    if usual.is_file():
        return str(usual)
    return shutil.which("godot")


godot_required = pytest.mark.skipif(_godot() is None, reason="no Godot binary; this runs the real instrument")

PROJECT = """config_version=5

[application]
config/name="edge_probe_body"
run/main_scene="res://main.tscn"
config/features=PackedStringArray("4.7")
"""


def _scene(boxes) -> str:
    """A scene of static boxes: ``[(name, (cx, cy, cz), (sx, sy, sz))]``, each a BoxShape3D with a BoxMesh beside it
    so the instrument's grid (the drawn geometry's extent) covers it."""
    subs, nodes = [], ['[node name="Main" type="Node3D"]', ""]
    for i, (name, c, s) in enumerate(boxes):
        size = "Vector3(%r, %r, %r)" % tuple(float(v) for v in s)
        subs.append('[sub_resource type="BoxShape3D" id="s%d"]\nsize = %s\n' % (i, size))
        subs.append('[sub_resource type="BoxMesh" id="m%d"]\nsize = %s\n' % (i, size))
        nodes += ['[node name="%s" type="StaticBody3D" parent="."]' % name,
                  "transform = Transform3D(1, 0, 0, 0, 1, 0, 0, 0, 1, %r, %r, %r)" % tuple(float(v) for v in c), "",
                  '[node name="col" type="CollisionShape3D" parent="%s"]' % name, 'shape = SubResource("s%d")' % i, "",
                  '[node name="mesh" type="MeshInstance3D" parent="%s"]' % name, 'mesh = SubResource("m%d")' % i, ""]
    return "[gd_scene load_steps=%d format=3]\n\n" % (len(subs) + 1) + "\n".join(subs) + "\n" + "\n".join(nodes)


def _box(name, x0, x1, y0, y1, z0, z1):
    return (name, ((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2), (x1 - x0, y1 - y0, z1 - z0))


def _run(tmp_path, boxes, seed):
    proj = tmp_path / "pkg"
    proj.mkdir()
    (proj / "project.godot").write_text(PROJECT, encoding="utf-8")
    (proj / "main.tscn").write_text(_scene(boxes), encoding="utf-8")
    (proj / "walkable_edge.gd").write_text(EDGE.read_text(encoding="utf-8"), encoding="utf-8")
    out = tmp_path / "edges.json"
    run = subprocess.run([_godot(), "--headless", "--path", str(proj), "--script", "res://walkable_edge.gd", "--",
                          str(out), str(D.CELL_M), "%r,%r,%r" % tuple(seed)],
                         capture_output=True, text=True, timeout=300)
    assert out.is_file(), run.stdout + run.stderr
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["ok"], report["error"]
    return report


def _reached(report, name):
    """Cells the flood reached on the body named `name` (its collider's node path ends in it)."""
    idx = [i for i, p in enumerate(report["owners"]) if p.rstrip("/").endswith("/" + name)]
    return sum(int(report["reachable_by_owner"].get(str(i), report["reachable_by_owner"].get(i, 0))) for i in idx)


# ---------------------------------------------------------------------------
# a kerb a body steps over
# ---------------------------------------------------------------------------
#: Lot's kerb (SIDEWALK_H), 0.95 of the contract's unassisted step.
KERB_H = 0.0974
#: The grid starts at the drawn extent's west edge (x -10) laid SEAM_NUDGE_X (0.0031) off it, so a column of cells
#: stands at x 0.0031; the kerb's face is put 0.038 m east of it -- the distance the phase sweep measured at the main
#: road's south sidewalk, where the shipped phase stood 0.163 m off and the refusing one 0.038.
KERB_X = 0.0031 + 0.038


@godot_required
def test_a_kerb_a_body_steps_over_does_not_occupy_the_cell_beside_it(tmp_path):
    boxes = [_box("GroundW", -10.0, KERB_X, -0.2, 0.0, -6.0, 6.0),
             _box("Sidewalk", KERB_X, KERB_X + 3.0, -0.2, KERB_H, -6.0, 6.0),
             _box("GroundE", KERB_X + 3.0, 10.0, -0.2, 0.0, -6.0, 6.0)]
    report = _run(tmp_path, boxes, (-5.0, 0.0, 0.1))
    # the sidewalk is across the kerb from the seed, and the ground past it across the sidewalk
    assert _reached(report, "Sidewalk") > 0, (report["reachable_by_owner"], report["owners"])
    assert _reached(report, "GroundE") > 0, (report["reachable_by_owner"], report["owners"])
    assert report.get("stand_lift_m") == pytest.approx(0.1025)


# ---------------------------------------------------------------------------
# a gap narrower than a body, beside a hole a body falls through
# ---------------------------------------------------------------------------
SLAB_TOP, SLAB_T, ROOF = 3.3, 0.3, 6.6


def _storey(dx):
    """A storey slab 3.3 m up under a roof, holding two holes: a 2.4 m hole with a 2.0 m block standing in it to the
    slab's top -- deli_a03's flight beside its hole, leaving a 0.4 m slot -- and a 2.2 m hole with nothing in it, the
    drop the deli's cut is. The storey shifted `dx` east over a ground that stays put: the grid starts at the drawn
    extent's west edge, the ground's, so this moves the lattice's phase across the storey -- shifting the ground with
    it moved nothing (measured, writing this). At dx 0.13 and 0.26 a column of cells stands in the slot 0.37 and
    0.24 m off the block, where the body's probe fits on the floor below and 0.221.0 read a 3.3 m drop -- the phase
    sweep's refusal; at 0.0 and 0.39 the slot's column is 3 mm and 0.11 m off it and reads occupied, as the shipped
    phase did."""
    def b(name, x0, x1, y0, y1, z0, z1):
        return _box(name, x0 + dx, x1 + dx, y0, y1, z0, z1)
    y0, y1 = SLAB_TOP - SLAB_T, SLAB_TOP
    return [_box("Ground", -10.0, 10.0, -0.2, 0.0, -8.0, 8.0),
            b("SlabS", -6.0, 6.0, y0, y1, -4.0, -2.0),
            b("SlabN", -6.0, 6.0, y0, y1, 2.0, 4.0),
            b("SlabW", -6.0, -2.0, y0, y1, -2.0, 2.0),
            b("SlabM", 0.4, 2.0, y0, y1, -2.0, 2.0),
            b("SlabE", 4.2, 6.0, y0, y1, -2.0, 2.0),
            b("SlabHs", 2.0, 4.2, y0, y1, -2.0, -1.1),
            b("SlabHn", 2.0, 4.2, y0, y1, 1.1, 2.0),
            b("Flight", -2.0, 0.0, 0.0, y1, -2.0, 2.0),
            b("Roof", -6.0, 6.0, ROOF, ROOF + 0.3, -4.0, 4.0)]


@pytest.mark.parametrize("dx", [0.0, 0.13, 0.26, 0.39])
@godot_required
def test_a_gap_narrower_than_a_body_is_not_a_fall_and_a_hole_still_is(tmp_path, dx):
    report = _run(tmp_path, _storey(dx), (1.2 + dx, SLAB_TOP, 3.0))
    upper = [e for e in report["edges"] if abs(e["y"] - SLAB_TOP) < 0.2]
    # the slot, x 0.0..0.4: no edge across it -- from the slab east of it, or the flight's top west of it
    slot = [(e["x"], e["z"]) for e in upper if -0.25 + dx <= e["x"] <= 0.65 + dx and abs(e["z"]) < 1.8]
    assert slot == [], slot[:20]
    assert report.get("too_narrow", 0) > 0
    # the 2.2 m hole, x 2.0..4.2 by z -1.1..1.1: an edge on each of its four sides
    def side(cond):
        return [e for e in upper if cond(e["x"] - dx, e["z"]) and e["indoors"]]
    assert side(lambda x, z: abs(x - 2.0) <= NEAR and abs(z) < 0.9), "west"
    assert side(lambda x, z: abs(x - 4.2) <= NEAR and abs(z) < 0.9), "east"
    assert side(lambda x, z: abs(z + 1.1) <= NEAR and 2.2 < x < 4.0), "south"
    assert side(lambda x, z: abs(z - 1.1) <= NEAR and 2.2 < x < 4.0), "north"


# ---------------------------------------------------------------------------
# the numbers are the contract's
# ---------------------------------------------------------------------------
def test_the_step_and_the_body_are_the_contracts():
    src = EDGE.read_text(encoding="utf-8")
    step = re.search(r"^const STEP_M := ([0-9.]+)", src, re.M)
    body = re.search(r"^const BODY_R := ([0-9.]+)", src, re.M)
    assert step and body, "walkable_edge.gd names no STEP_M or BODY_R"
    from tests.siblings import not_found, sibling_repo
    dc = sibling_repo("deli_counter", marker="agent_contract.json")
    if dc is None:
        pytest.skip(not_found("deli_counter", marker="agent_contract.json"))
    contract = json.loads((dc / "agent_contract.json").read_text(encoding="utf-8"))
    assert float(step.group(1)) == contract["clearances"]["unassisted_step_max_m"]
    assert float(body.group(1)) == contract["characters"]["player"]["radius_m"]
