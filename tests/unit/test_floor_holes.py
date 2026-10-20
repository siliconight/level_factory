"""A hole in a floor is rare: a level carries one at the brief's rate (0.221.0; the factory's roadmap 269).

The walker, 2026-10-20: "stairs and ladders should be the primary way to get between floors in this game...with the
holes in floors being somewhat rare...but still at our disposal to use if needed/desired to add some more ways to
navigate levels". Measured before it (the factory's `docs/findings/hole_frequency/`): every corner-deli level carried
the deli's cut drop, and every single-building deli and county-hospital level its preset's.

`building_library.holes_wanted` decides per candidate, at `floor_hole_rate` (the brief's `floor_holes`, else
FLOOR_HOLE_RATE 0.25); `apply_hole_rule` swaps a drawn building's VARIANT within its family to match, never the
family; `draw_lot` is the one place the draw and the rule meet, for `lot_for` and the site spec's own draw alike; and
the mission's own building is built without its holes (`--holes off`, Deli Counter 0.237.0) on a level left without.

FAIL ON 0.220.0: none of these names exists, the brief has no `floor_holes`, and the adapter passes no `--holes`.

Run:  python -m pytest tests/unit/test_floor_holes.py
"""
import json
from types import SimpleNamespace

from packages.core.models import MissionBrief
from packages.pipeline import building_library as bl


def _entry(tmp_path, eid, family, hole=False, stair=False, roof=False):
    """A library row whose gameplay record carries the links Deli Counter writes: a drop with a `cause`, a hatch into
    a stair's own well (cause `stair`), a roof hatch (no cause)."""
    links = [{"kind": "stair", "from_story": 0, "to_story": 1}]
    if hole:
        links.append({"kind": "floor_hole", "story": 1, "x": 0.0, "y": 0.0, "cause": "cut"})
    if stair:
        links.append({"kind": "hatch", "story": 1, "x": 3.0, "y": 3.0, "cause": "stair"})
    if roof:
        links.append({"kind": "hatch", "story": 2, "x": 0.0, "y": 0.0})
    p = tmp_path / (eid + ".gameplay.json")
    p.write_text(json.dumps({"vertical_links": links}), encoding="utf-8")
    return {"id": eid, "family": family, "gameplay": str(p)}


def test_the_rate_is_the_rate():
    keys = ["m.candidate.seed_%d" % s for s in range(9000, 13000)]
    share = sum(bl.holes_wanted(k, 0.25) for k in keys) / len(keys)
    assert 0.23 < share < 0.27, share
    assert not any(bl.holes_wanted(k, 0.0) for k in keys[:300])
    assert all(bl.holes_wanted(k, 1.0) for k in keys[:300])
    assert [bl.holes_wanted(k, 0.25) for k in keys[:60]] == [bl.holes_wanted(k, 0.25) for k in keys[:60]]
    # keyed on the candidate, not the seed alone: two missions sharing a seed do not share the answer
    a = [bl.holes_wanted("restaurant_row_001.candidate.seed_%d" % s, 0.5) for s in range(9000, 9200)]
    b = [bl.holes_wanted("urban_row_001.candidate.seed_%d" % s, 0.5) for s in range(9000, 9200)]
    assert a != b


def test_a_hole_is_a_drop_a_player_sees(tmp_path):
    assert bl.carries_hole(_entry(tmp_path, "a", "f", hole=True))
    assert not bl.carries_hole(_entry(tmp_path, "b", "f", stair=True))       # into a stair's own well
    assert not bl.carries_hole(_entry(tmp_path, "c", "f", roof=True))        # a roof hatch
    assert not bl.carries_hole({"id": "d", "family": "f", "gameplay": str(tmp_path / "absent.json")})


def _library(tmp_path):
    return {"deli1": _entry(tmp_path, "deli_a01", "deli"),
            "deli3": _entry(tmp_path, "deli_a03", "deli", hole=True),
            "wh1": _entry(tmp_path, "warehouse_a01", "warehouse"),
            "wh2": _entry(tmp_path, "warehouse_a02", "warehouse", hole=True),
            "bank": _entry(tmp_path, "bank_a01", "bank")}


def test_a_level_without_one_swaps_the_variant_never_the_family(tmp_path):
    L = _library(tmp_path)
    entries = list(L.values())
    lot, wanted, swaps = bl.apply_hole_rule([L["deli3"], L["wh2"], L["bank"]], entries, "k", 0.0)
    assert not wanted
    assert [e["id"] for e in lot] == ["deli_a01", "warehouse_a01", "bank_a01"]
    assert swaps == [("deli_a03", "deli_a01"), ("warehouse_a02", "warehouse_a01")]
    # a family with no variant without one keeps its building, and the swap says so
    lot, wanted, swaps = bl.apply_hole_rule([L["deli3"]], [L["deli3"]], "k", 0.0)
    assert [e["id"] for e in lot] == ["deli_a03"] and swaps == [("deli_a03", None)]


def test_a_level_with_one_keeps_it_or_takes_one(tmp_path):
    L = _library(tmp_path)
    entries = list(L.values())
    lot, wanted, swaps = bl.apply_hole_rule([L["deli1"], L["bank"]], entries, "k", 1.0)
    assert wanted and [e["id"] for e in lot] == ["deli_a03", "bank_a01"] and swaps == [("deli_a01", "deli_a03")]
    # one is enough: a lot that already holds one stands as drawn
    lot, _w, swaps = bl.apply_hole_rule([L["deli3"], L["wh1"]], entries, "k", 1.0)
    assert [e["id"] for e in lot] == ["deli_a03", "warehouse_a01"] and swaps == []
    # and one only: the first family that can hold one takes it
    lot, _w, swaps = bl.apply_hole_rule([L["deli1"], L["wh1"]], entries, "k", 1.0)
    assert [e["id"] for e in lot] == ["deli_a03", "warehouse_a01"] and swaps == [("deli_a01", "deli_a03")]
    # a lot whose families have no variant with one stands
    lot, _w, swaps = bl.apply_hole_rule([L["bank"]], entries, "k", 1.0)
    assert [e["id"] for e in lot] == ["bank_a01"] and swaps == []


def _build_dir(tmp_path):
    """A Deli Counter build dir: the three files `index` requires, the gameplay record carrying the drop."""
    lib = tmp_path / "build"
    lib.mkdir()
    for aid, hole in (("deli_a01", False), ("deli_a03", True), ("bank_a01", False)):
        for suf in bl.REQUIRED:
            (lib / (aid + suf)).write_text("{}")
        links = [{"kind": "floor_hole", "story": 1, "x": 0.0, "y": 0.0, "cause": "cut"}] if hole else []
        (lib / (aid + ".gameplay.json")).write_text(json.dumps({"vertical_links": links}))
    return str(lib)


def test_lot_for_and_the_site_draw_apply_it_alike(tmp_path):
    lib = _build_dir(tmp_path)
    complete = bl.index(lib)[0]
    for s in range(9000, 9040):
        cid = "deli_001.candidate.seed_%d" % s
        for rate in (0.0, 1.0):
            lot, _inc = bl.lot_for(lib, 2, cid, anchor="deli", hole_rate=rate)
            deli = [e["id"] for e in lot if e["family"] == "deli"]
            assert deli == (["deli_a03"] if rate else ["deli_a01"]), (cid, rate, lot)
            # the site spec's own draw, through the one meeting place
            site = bl.draw_lot(complete, s, 2, anchor="deli", candidate=cid, hole_rate=rate)
            assert [e["id"] for e in site] == [e["id"] for e in lot]
    # at the default rate, one level in about four keeps the drop
    kept = sum("deli_a03" in [e["id"] for e in bl.lot_for(lib, 2, "deli_001.candidate.seed_%d" % s,
                                                           anchor="deli")[0]]
               for s in range(9000, 9400))
    assert 70 < kept < 130, kept


def test_the_brief_names_its_rate():
    m = MissionBrief(mission_id="m", display_name="m", archetype="deli")
    assert m.floor_holes is None and "floor_holes" not in m.functional_signature()
    assert bl.floor_hole_rate(m) == bl.FLOOR_HOLE_RATE == 0.25
    m = MissionBrief(mission_id="m", display_name="m", archetype="deli", floor_holes=1.0)
    assert m.functional_signature()["floor_holes"] == 1.0 and bl.floor_hole_rate(m) == 1.0
    assert bl.floor_hole_rate(SimpleNamespace(floor_holes=3)) == 1.0
    assert bl.floor_hole_rate(SimpleNamespace(floor_holes=-1)) == 0.0


def test_the_deli_counter_job_passes_holes_off_and_nothing_else(tmp_path):
    from adapters.deli_counter import DeliCounterAdapter
    ad = DeliCounterAdapter()
    ctx = {"repository": str(tmp_path), "work_dir": str(tmp_path / "w"), "python_executable": "python",
           "blender_executable": "blender"}

    def args(spec):
        return list(ad.plan_commands(spec, ctx)[0].arguments)
    base = {"archetype": "deli", "seed": 9003, "level_name": "lf_m"}
    assert "--holes" not in args(base)
    assert "--holes" not in args(dict(base, holes="on"))
    a = args(dict(base, holes="off"))
    assert a[a.index("--holes") + 1] == "off"
    # fingerprinted when named, and only then
    assert "holes" not in ad.fingerprint_inputs(base, ctx)
    assert ad.fingerprint_inputs(dict(base, holes="off"), ctx)["holes"] == "off"
