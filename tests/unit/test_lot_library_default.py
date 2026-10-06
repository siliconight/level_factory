"""The lot library by default, wherever it can honour the brief (0.145.0).

The breadth sweep built three missions that named no `lot_library`: one
generated shell placed N times, and no Empties. A blanket default would have
cost county_hospital_001 its hospital -- today's library has no hospital
family -- so the default follows the anchor rule `pick_lot` draws with, and
`lot_for`'s own floor of two buildings.

Run:  python -m pytest tests/unit/test_lot_library_default.py -q
"""
from apps.cli.commands import LOT_LIBRARY_NONE, _brief_model, _default_lot_library


class _WS:
    def __init__(self, deli):
        self._deli = deli

    def load_tools_local(self):
        return {"repositories": {"deli_counter": str(self._deli)} if self._deli else {}}


def _library(tmp_path, ids=("deli_a01", "warehouse_a01", "clinic_a01", "bank_tower_a01")):
    build = tmp_path / "deli_counter" / "build"
    build.mkdir(parents=True)
    for aid in ids:
        for suf in (".glb", ".gameplay.json", ".validation.json"):
            (build / (aid + suf)).write_text("{}")
        (build / (aid + ".slots.json")).write_text('{"coverage": {"wall": 40}}')
    return tmp_path / "deli_counter", build


def _brief(**kw):
    return {"mission_id": "m", "building_count": 3, **kw}


def test_a_brief_whose_archetype_the_library_anchors_gets_the_library(tmp_path):
    """FAILS BEFORE 0.145.0: restaurant_row_001 (corner_deli, 3) and
    warehouse_yard_001 (industrial_warehouse, 2) placed generated copies."""
    deli, build = _library(tmp_path)
    for archetype, count in (("corner_deli", 3), ("industrial_warehouse", 2)):
        b = _brief(archetype=archetype, building_count=count)
        note = _default_lot_library(_WS(deli), b)
        assert b["lot_library"] == str(build), b
        assert "anchors on" in note


def test_an_archetype_with_no_family_keeps_its_generated_building(tmp_path):
    """county_hospital_001's case: a clinic is not a hospital."""
    deli, _ = _library(tmp_path)
    b = _brief(archetype="county_hospital")
    note = _default_lot_library(_WS(deli), b)
    assert "lot_library" not in b
    assert "no family for archetype 'county_hospital'" in note


def test_one_building_is_left_alone(tmp_path):
    """`lot_for` places no lot below two buildings, so a library there would
    change the signature and nothing else."""
    deli, _ = _library(tmp_path)
    b = _brief(archetype="corner_deli", building_count=1)
    assert _default_lot_library(_WS(deli), b) == "" and "lot_library" not in b


def test_a_brief_that_names_a_library_or_says_none_is_obeyed(tmp_path):
    deli, _ = _library(tmp_path)
    own = _brief(archetype="corner_deli", lot_library="D:/elsewhere/build")
    assert _default_lot_library(_WS(deli), own) == ""
    assert own["lot_library"] == "D:/elsewhere/build"
    none = _brief(archetype="corner_deli", lot_library="None")
    _default_lot_library(_WS(deli), none)
    assert none["lot_library"] == ""


def test_no_deli_counter_configured_changes_nothing(tmp_path):
    b = _brief(archetype="corner_deli")
    note = _default_lot_library(_WS(None), b)
    assert "lot_library" not in b and "no Deli Counter build" in note


def test_none_is_never_read_as_a_path():
    model = _brief_model(_brief(display_name="m", lot_library=LOT_LIBRARY_NONE))
    assert model.lot_library == ""
