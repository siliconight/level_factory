"""The draw by cluster template (0.176.0, roadmap 230): the walker's adjacency guide's eighteen
recipes as the families a lot prefers, and the draw that keeps its old answer when no brief asks."""
from packages.pipeline import building_library as bl
from packages.pipeline import cluster

ENTRIES = [{"id": f"{fam}_a01", "family": fam} for fam in
           ("deli", "pharmacy", "office", "strip_club", "arena", "marina", "apartment_walkup",
            "twin", "auto_shop", "gas_station", "warehouse", "clinic")]


def test_the_guides_eighteen_templates_each_name_an_anchor_and_its_uses():
    guide = {t: v for t, v in cluster.TEMPLATES.items() if t.startswith("C")}
    assert len(guide) == 18
    for tid, (anchor, supporting, fabric) in guide.items():
        assert tid[:3] in ("C01", "C02", "C03", "C04", "C05", "C06", "C07", "C08", "C09", "C10",
                           "C11", "C12", "C13", "C14", "C15", "C16", "C17", "C18")
        assert anchor and supporting and fabric
    # the factory's own (0.268.0) are `D`, and nothing else
    assert all(t.startswith(("C", "D")) for t in cluster.TEMPLATES)


def test_the_delco_avenue_puts_one_bank_beside_the_gas_station():
    """FAILS ON 0.267.0: no such template. The walker's vertical slice, 2026-10-29: "Delco Ave. Gas
    Station + Bank + some random buildings" -- the anchor, one branch bank, then the seeded draw."""
    assert cluster.preferred_families("D01_delco_avenue") == ["bank_branch"]
    entries = ENTRIES + [{"id": f"bank_branch_a0{i}", "family": "bank_branch"} for i in (2, 3)] + [
        {"id": "credit_union_a01", "family": "credit_union"}]
    pref = cluster.preferred_families("D01_delco_avenue")
    rest = set()
    for seed in (1, 5421, 9082, 9104, 9205):
        lot = bl.pick_lot(entries, seed, 4, anchor="gas_station", preferred=pref)
        fams = [e["family"] for e in lot]
        assert fams[0] == "gas_station" and fams[1] == "bank_branch", (seed, fams)
        assert "credit_union" not in fams[:2] and len(set(fams)) == 4
        rest.add(tuple(fams[2:]))
    assert len(rest) > 1                    # the rest is the seed's, not the template's


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



def test_preferred_for_brief_is_the_one_place_the_template_is_read():
    from types import SimpleNamespace
    assert bl.preferred_for_brief(SimpleNamespace(cluster="", archetype="deli")) is None
    got = bl.preferred_for_brief(SimpleNamespace(cluster="auto", archetype="rail_station"))
    assert got and got == cluster.preferred_families("C03_station_neighborhood")


def test_every_draw_outside_the_library_passes_the_template():
    """0.176.1, cold run 9231: `lot_for_brief` threaded the template and the site spec's own
    `pick_lot` call did not, so the art leg dressed a pharmacy the site never placed and the
    export's closure gate stopped the run. Every `pick_lot(` or `draw_lot(` in `apps/` and
    `packages/` outside the library must say `preferred=`, read with the brackets balanced --
    and a `draw_lot(` (0.221.0, the site spec's draw since) its `candidate=` too, the key the
    hole rule's answer is the same under for every caller."""
    import pathlib
    root = pathlib.Path(__file__).resolve().parents[2]
    found = 0
    for p in list((root / "apps").rglob("*.py")) + list((root / "packages").rglob("*.py")):
        if p.name == "building_library.py":
            continue
        text = p.read_text(encoding="utf-8")
        for name in ("pick_lot(", "draw_lot("):
            i = text.find(name)
            while i >= 0:
                j, depth = i + len(name), 1
                while depth and j < len(text):
                    depth += {"(": 1, ")": -1}.get(text[j], 0)
                    j += 1
                assert "preferred=" in text[i:j], f"{p.relative_to(root)}: a lot draw without the template"
                if name == "draw_lot(":
                    assert "candidate=" in text[i:j], f"{p.relative_to(root)}: a lot draw without its candidate"
                found += 1
                i = text.find(name, j)
    assert found >= 1, "the site spec's draw was not found"
