"""The draw by cluster template (0.176.0, roadmap 230): the walker's adjacency guide's eighteen
recipes as the families a lot prefers, and the draw that keeps its old answer when no brief asks."""
from packages.pipeline import building_library as bl
from packages.pipeline import cluster

ENTRIES = [{"id": f"{fam}_a01", "family": fam} for fam in
           ("deli", "pharmacy", "office", "strip_club", "arena", "marina", "apartment_walkup",
            "twin", "auto_shop", "gas_station", "warehouse", "clinic")]


def test_the_guides_eighteen_templates_each_name_an_anchor_and_its_uses():
    assert len(cluster.TEMPLATES) == 18
    for tid, (anchor, supporting, fabric) in cluster.TEMPLATES.items():
        assert tid[:3] in ("C01", "C02", "C03", "C04", "C05", "C06", "C07", "C08", "C09", "C10",
                           "C11", "C12", "C13", "C14", "C15", "C16", "C17", "C18")
        assert anchor and supporting and fabric


def test_the_catalog_maps_uses_onto_family_names():
    for use, fams in cluster.CATALOG_FAMILIES.items():
        assert isinstance(fams, tuple) and all(isinstance(f, str) and f for f in fams), use


def test_a_brief_that_names_nothing_keeps_the_draw_it_had():
    assert cluster.template_for("", "deli") is None
    assert cluster.resolved("", "deli") == {"asked": "", "got": "", "known": True, "preferred": []}
    assert bl.pick_lot(ENTRIES, 5421, 4) == bl.pick_lot(ENTRIES, 5421, 4, preferred=None)
    assert bl.pick_lot(ENTRIES, 5421, 4) == bl.pick_lot(ENTRIES, 5421, 4, preferred=[])


def test_auto_lets_the_archetypes_words_decide():
    for archetype, template in (("county_hospital", "C11_hospital_edge"),
                                ("gas_station", "C08_roadside_lodging"),
                                ("rail_station", "C03_station_neighborhood"),
                                ("industrial_warehouse", "C04_industrial_residential_edge"),
                                ("strip_club", "C10_evening_main_street"),
                                ("country_club", "C06_neighborhood_recreation"),
                                ("convenience_store", "C01_corner_services"),
                                ("urban_bank", "C02_borough_civic_center"),
                                ("something_nobody_named", "C01_corner_services")):
        assert cluster.template_for("auto", archetype) == template, archetype


def test_an_unknown_spelling_is_said_not_guessed():
    got = cluster.resolved("C99_nowhere", "deli")
    assert got["got"] == "" and got["known"] is False and got["preferred"] == []
    assert cluster.template_for("C99_nowhere", "deli") is None


def test_preferred_families_follow_the_guides_order():
    assert cluster.preferred_families("C03_station_neighborhood") == [
        "deli", "cr_deli", "night_deli", "pharmacy", "office", "office_stepped", "bank_tower",
        "apartment_walkup", "twin"]
    assert cluster.preferred_families("not_a_template") == []


def test_the_draw_takes_the_templates_families_first():
    preferred = cluster.preferred_families("C03_station_neighborhood")
    for seed in (1, 5421, 9104, 9205):
        lot = bl.pick_lot(ENTRIES, seed, 3, anchor="rail_station", preferred=preferred)
        assert {e["family"] for e in lot} == {"deli", "pharmacy", "office"}, (seed, lot)
    # the same seeds without the template reach past them
    others = {tuple(e["family"] for e in bl.pick_lot(ENTRIES, s, 3)) for s in (1, 5421, 9104, 9205)}
    assert any(set(fams) - {"deli", "pharmacy", "office"} for fams in others)


def test_a_preferred_family_the_library_lacks_is_skipped_and_the_lot_is_still_full():
    lot = bl.pick_lot(ENTRIES, 5421, 4, preferred=["tavern", "hardware", "deli"])
    assert len(lot) == 4 and lot[0]["family"] == "deli"
    assert len({e["family"] for e in lot}) == 4


def test_the_anchor_still_stands_first_and_is_not_drawn_twice():
    lot = bl.pick_lot(ENTRIES, 7, 3, anchor="deli", preferred=["deli", "pharmacy"])
    assert lot[0]["family"] == "deli" and lot[1]["family"] == "pharmacy"
    assert len({e["family"] for e in lot}) == 3
