"""An urban street: the far side a continuous mid-rise wall (Level Factory 0.200.0, factory roadmap 241, steps 2-3).

The walker, 2026-10-11, chose a new urban level type: mid-rise blocks standing at the sidewalk line and touching,
block after block, a gap an event and not the default (`docs/reference/URBAN_MIDRISE_COMPS.md` in the factory
root). The brief asks for it with `streetscape: "urban"`; this first cut stands Deli Counter 0.213.0's mid-rise
Empties (`gs_midrise_*`) across the street as one continuous wall, where every other brief keeps the rowhome
terrace with an alley every few houses. Absent, the field changes nothing -- not the Empties, not the terrace,
not the functional signature.
"""
from packages.core.models import MissionBrief, STREETSCAPE_URBAN, streetscape_effective
from packages.pipeline import building_library, empties, site_variation

#: Literal extents (x0, x1, y0, y1) as `street_line.shell_extents` reads them: three rowhomes 5.5-6.5 m wide and
#: 12 m deep, and two mid-rises 15 and 24 m wide and 15 m deep.
EXT = {"gs_empty_rowhome_a": (-3.0, 3.0, -6.15, 6.15),
       "gs_empty_rowhome_b": (-2.75, 2.75, -6.15, 6.15),
       "gs_empty_rowhome_c": (-3.25, 3.25, -6.15, 6.15),
       "gs_midrise_a": (-7.5, 7.5, -7.5, 7.5),
       "gs_midrise_b": (-12.0, 12.0, -7.5, 7.5)}
THROUGH = {"a": [-90.0, -27.65], "b": [90.0, -27.65], "width": 10.0, "sidewalk": 3.0}


def _brief(**kw):
    base = dict(mission_id="m", display_name="m", archetype="corner_deli", building_count=3, lot_library="lib")
    base.update(kw)
    return MissionBrief(**{k: v for k, v in base.items() if k in MissionBrief.__dataclass_fields__})


def test_the_field_is_absent_by_default_and_changes_no_signature():
    plain = _brief()
    assert plain.streetscape == ""
    assert "streetscape" not in plain.functional_signature()
    assert streetscape_effective("", "across") == ""
    assert streetscape_effective("strip", "across") == ""


def test_urban_is_what_a_brief_gets_only_when_a_terrace_stands():
    assert streetscape_effective("urban", "across") == STREETSCAPE_URBAN
    assert streetscape_effective(" Urban ", "across") == STREETSCAPE_URBAN
    assert streetscape_effective("urban", "") == "", "no terrace stands: nothing to make urban"
    assert _brief(streetscape="urban").functional_signature()["streetscape"] == STREETSCAPE_URBAN
    one = _brief(streetscape="urban", building_count=1)
    assert "streetscape" not in one.functional_signature()


def test_an_urban_brief_draws_the_mid_rise_family(tmp_path):
    for aid in sorted(EXT):
        (tmp_path / (aid + ".glb")).write_bytes(b"glb")
        (tmp_path / (aid + ".gameplay.json")).write_text("{}")
        (tmp_path / (aid + ".slots.json")).write_text("{}")
        (tmp_path / (aid + ".validation.json")).write_text('{"facade": true}')
    strip = building_library.empties_for_brief(_brief(lot_library=str(tmp_path)))
    urban = building_library.empties_for_brief(_brief(lot_library=str(tmp_path), streetscape="urban"))
    assert [r["id"] for r in strip] == ["gs_empty_rowhome_a", "gs_empty_rowhome_b", "gs_empty_rowhome_c"]
    assert [r["id"] for r in urban] == ["gs_midrise_a", "gs_midrise_b"]


def test_the_urban_wall_is_continuous_and_on_the_line():
    rows = [{"id": "gs_midrise_a"}, {"id": "gs_midrise_b"}]
    placed, need = empties.terrace(rows, EXT, site_variation.stream(9104), [THROUGH], 180.0, continuous=True)
    assert len(placed) >= 6
    assert {p["front"] for p in placed} == {-37.65}
    for a, b in zip(placed, placed[1:]):
        gap = (b["at"][0] - b["size_x"] / 2) - (a["at"][0] + a["size_x"] / 2)
        assert abs(gap) < 1e-6, ("a gap in an urban wall", a["id"], b["id"], gap)
    assert all(a["archetype"] != b["archetype"] for a, b in zip(placed, placed[1:]))
    assert abs(need - (37.65 + 15.0)) < 1e-6


def test_the_strip_terrace_is_the_one_it_was():
    """`continuous` defaults off, and off the terrace draws as before: same houses, same alleys."""
    rows = [{"id": k} for k in ("gs_empty_rowhome_a", "gs_empty_rowhome_b", "gs_empty_rowhome_c")]
    before = empties.terrace(rows, EXT, site_variation.stream(9080), [THROUGH], 180.0)
    again = empties.terrace(rows, EXT, site_variation.stream(9080), [THROUGH], 180.0, continuous=False)
    assert before == again
    gaps = [(b["at"][0] - b["size_x"] / 2) - (a["at"][0] + a["size_x"] / 2) for a, b in zip(before[0], before[0][1:])]
    assert any(abs(g - empties.ALLEY) < 1e-6 for g in gaps), "the strip keeps its alleys"
