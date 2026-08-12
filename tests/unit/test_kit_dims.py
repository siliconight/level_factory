"""The kit is measured against its own index, by the job that built it.

Zoo's `<building_id>_kit.built.json` states, per module, the `dims` the planner
asked for. The `.glb` beside it is what was built. Nothing compared the two
until 2026-08-09, when one kit shared across a lot was found to have put
3.300 m walls in eight buildings whose slots asked 3.1 to 5.2 -- a 0.95 m gap
under every wall in `depot_a01`, past every gate in the pipeline.

THE ASSERTION THAT MATTERS is `test_a_kit_built_to_its_index_is_clean`. A check
that flags a bad kit tells you nothing on its own: the first version of
`module_extents.py --kit` read a wall's THICKNESS as its height and flagged
everything, correct kits included, and its fixture was authored in the same
wrong axis so the two agreed and passed together. Only the clean report has
any value, so it is asserted first and separately.
"""
from __future__ import annotations

import json
import struct
from pathlib import Path

from adapters.zoo import ZooAdapter
from packages.validation.kit_dims import kit_dimension_findings, module_extent


def _glb(w: float, d: float, h: float) -> bytes:
    """A .glb of a w x d x h box, authored Y-UP as a real export is.

    (x=w, y=h, z=d). Written out deliberately: a fixture in Zoo's authoring
    space would agree with a reader that had the axes wrong, which is how the
    bug this file guards got through a green test once already.
    """
    doc = {
        "asset": {"version": "2.0"},
        "scene": 0, "scenes": [{"nodes": [0]}],
        "nodes": [{"mesh": 0}],
        "meshes": [{"primitives": [{"attributes": {"POSITION": 0}}]}],
        "accessors": [{"componentType": 5126, "count": 2, "type": "VEC3",
                       "min": [-w / 2, -h / 2, -d / 2],
                       "max": [w / 2, h / 2, d / 2]}],
    }
    body = json.dumps(doc).encode("utf-8")
    body += b" " * ((4 - len(body) % 4) % 4)
    return (b"glTF" + struct.pack("<II", 2, 12 + 8 + len(body))
            + struct.pack("<II", len(body), 0x4E4F534A) + body)


def _kit(tmp_path: Path, wall=(2.0, 0.3, 5.2), *, status="ok") -> Path:
    """A kit dir whose index asks for a 2.0 x 0.3 x 5.2 wall and a unit end."""
    out = tmp_path / "kit"
    out.mkdir(exist_ok=True)
    (out / "wall_rockay_01_w200.glb").write_bytes(_glb(*wall))
    (out / "wallEnd_rockay_01.glb").write_bytes(_glb(1.0, 1.0, 1.0))
    index = {
        "building_id": "depot_a01", "theme": "rockay", "style": 1,
        "modules": [
            {"stem": "wall_rockay_01_w200", "fit": "exact",
             "dims": [2.0, 0.3, 5.2], "status": status},
            {"stem": "wallEnd_rockay_01", "fit": "unit",
             "dims": [1.0, 1.0, 1.0], "status": "ok"},
        ],
    }
    p = out / "depot_a01_kit.built.json"
    p.write_text(json.dumps(index), encoding="utf-8")
    return p


# --- the assertion that matters -------------------------------------------

def test_a_kit_built_to_its_index_is_clean(tmp_path):
    """A correct kit must produce NO findings. Everything else is worthless
    without this: a check that flags the good ones too is not a check."""
    assert kit_dimension_findings(_kit(tmp_path)) == []


def test_the_axis_is_read_as_the_exporter_writes_it(tmp_path):
    """Height is the .glb's Y extent, thickness its Z. Named, because reading
    z gave `wanted 5.2, built 0.3` for a kit that was right."""
    _kit(tmp_path)
    got = module_extent(tmp_path / "kit" / "wall_rockay_01_w200.glb")
    assert got == (2.0, 0.3, 5.2), got


# --- and then the defect ---------------------------------------------------

def test_a_short_wall_is_flagged(tmp_path):
    """The measured defect: built 3.3 where the slot asked 5.2."""
    found = kit_dimension_findings(_kit(tmp_path, wall=(2.0, 0.3, 3.3)))
    assert len(found) == 1, found
    assert found[0]["code"] == "ZOO_KIT_DIMS_MISMATCH"
    assert found[0]["blocking"] is True
    assert "height 5.200 -> 3.300" in found[0]["message"]


def test_a_wrong_depth_is_flagged_too(tmp_path):
    """The plate collision was a DEPTH -- "a slab eight metres too deep". A
    check that only looks at the axis of the last bug finds the last bug."""
    found = kit_dimension_findings(_kit(tmp_path, wall=(2.0, 8.0, 5.2)))
    assert len(found) == 1
    assert "depth 0.300 -> 8.000" in found[0]["message"]


def test_a_unit_module_is_judged_against_the_unit_box(tmp_path):
    """A wallEnd is 1x1x1 and Deli Counter scales it at placement. Measuring
    one against its slot's 5.2 m reports the only correct module as broken --
    which is how the 2026-08-08 `wallEnd` finding happened, from the far end."""
    index_path = _kit(tmp_path)
    index = json.loads(index_path.read_text())
    index["modules"][1]["dims"] = [0.45, 0.3, 5.2]   # its slot, not its box
    index_path.write_text(json.dumps(index), encoding="utf-8")
    assert kit_dimension_findings(index_path) == []


def test_a_module_that_failed_to_build_is_not_flagged_twice(tmp_path):
    """Zoo already reports those as ZOO_PARTIAL_BUILD."""
    found = kit_dimension_findings(
        _kit(tmp_path, wall=(2.0, 0.3, 3.3), status="fail"))
    assert found == []


def test_an_unmeasurable_module_is_not_silence(tmp_path):
    """An unknown that prints nothing is indistinguishable from a pass."""
    index_path = _kit(tmp_path)
    (tmp_path / "kit" / "wall_rockay_01_w200.glb").write_bytes(b"not a glb")
    found = kit_dimension_findings(index_path)
    assert [f["code"] for f in found] == ["ZOO_KIT_DIMS_UNREADABLE"]
    assert found[0]["blocking"] is False


# --- and that the adapter actually asks ------------------------------------

def test_the_zoo_adapter_reports_it(tmp_path):
    """Wired, not merely written. The check has to be reached by the job."""
    index_path = _kit(tmp_path, wall=(2.0, 0.3, 3.3))
    issues = ZooAdapter().normalize_validation([index_path])
    assert any(i["code"] == "ZOO_KIT_DIMS_MISMATCH" for i in issues), issues


def test_the_zoo_adapter_stays_quiet_on_a_good_kit(tmp_path):
    issues = ZooAdapter().normalize_validation([_kit(tmp_path)])
    assert [i for i in issues if i["code"].startswith("ZOO_KIT_DIMS")] == []
