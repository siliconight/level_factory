"""The cluster templates: which buildings stand beside the objective, and why (0.176.0, roadmap 230).

The walker's guide (`docs/reference/PA_1990S_ADJACENCY_AND_LAYOUT_GUIDE.md` at the factory root)
names eighteen neighbourhood recipes, each an anchor with the uses that support it and the
ordinary fabric that repeats around it. `building_library.pick_lot` drew the buildings beside the
archetype from the whole library by seed alone -- a marina beside a strip club as readily as a
pharmacy -- which is why a new building family changed every seed's level. A brief that names a
`cluster` (a template's id, or `auto` for the archetype to decide) draws the template's families
first, in the order the guide lists them, and the library's remainder after; a brief that names
none keeps the draw it always had, byte for byte.

The templates carry the guide's ids; `CATALOG_FAMILIES` maps each id onto the library families
that are that use. A use the library has no family for is skipped, not invented, and the site spec
records what was asked, what was got and which families were preferred (`resolved`).
"""
from __future__ import annotations

#: The guide's templates: (anchor, the supporting uses in the guide's order, the ordinary fabric).
TEMPLATES = {
    "C01_corner_services": ("corner_store", ("pizzeria", "laundromat"), ("rowhouse", "shop_house")),
    "C02_borough_civic_center": ("municipal_hall", ("library", "bank", "diner", "post_office"),
                                 ("office", "shop_house")),
    "C03_station_neighborhood": ("rail_station", ("deli", "pharmacy", "office"),
                                 ("apartment", "twin_house", "shop_house")),
    "C04_industrial_residential_edge": ("factory", ("warehouse", "tavern", "union_hall"),
                                        ("rowhouse", "workshop")),
    "C05_repair_and_trade_strip": ("repair_garage", ("hardware", "building_supply", "diner"),
                                   ("workshop", "office")),
    "C06_neighborhood_recreation": ("community_center", ("public_pool", "sports_field", "playground"),
                                    ("detached_house", "twin_house")),
    "C07_parish_block": ("church", ("school", "community_center"), ("rowhouse", "twin_house")),
    "C08_roadside_lodging": ("motel", ("diner", "fuel_station", "hotel_pool"),
                             ("office", "repair_garage")),
    "C09_small_shopping_center": ("strip_center", ("grocery", "video_store", "pharmacy", "pizzeria"),
                                  ("barber_salon", "office")),
    "C10_evening_main_street": ("cinema", ("restaurant", "tavern", "arcade"),
                                ("shop_house", "apartment", "office")),
    "C11_hospital_edge": ("hospital", ("clinic", "pharmacy", "office", "deli"), ("apartment", "office")),
    "C12_creek_mill_conversion": ("factory", ("workshop", "print_shop", "office"),
                                  ("rowhouse", "warehouse")),
    "C13_rural_crossroads": ("feed_store", ("hardware", "diner", "repair_garage", "fire_station"),
                             ("detached_house", "workshop")),
    "C14_working_farm": ("barn", ("farmhouse", "machine_shed", "greenhouse"), ("machine_shed",)),
    "C15_marina_restaurant": ("marina", ("restaurant", "boat_storage", "repair_garage"),
                              ("office", "workshop")),
    "C16_airport_landside_edge": ("airport_terminal", ("hotel", "hotel_pool", "rental_car_lot", "parking_garage"),
                                  ("office", "warehouse")),
    "C17_administrative_lunch_district": ("courthouse", ("office", "bank", "diner", "print_shop"),
                                          ("shop_house", "apartment")),
    "C18_large_cultural_campus_edge": ("museum", ("park", "restaurant", "college"), ("office",)),
}

#: The guide's building ids onto the library's families (`building_library.family`), the ones
#: that ARE that use. A use the library has no family for maps to nothing: a rowhouse is the
#: Empties' terrace, not a lot building; a tavern, a diner or a hardware store is a building the
#: library has not drawn yet, and the template's slot falls to the ordinary draw. A pizzeria is
#: the guide's own neighbourhood restaurant, so it stands in for one.
CATALOG_FAMILIES = {
    "corner_store": ("stop_n_go", "convenience_store", "gs_corner_station"),
    "pizzeria": ("primos_pizza",),
    "restaurant": ("primos_pizza",),
    "deli": ("deli", "cr_deli", "night_deli"),
    "pharmacy": ("pharmacy",),
    "grocery": ("supermarket",),
    "strip_center": ("strip_retail",),
    "video_store": ("video_store",),
    "bank": ("bank_branch", "credit_union", "bank"),
    "office": ("office", "office_stepped", "bank_tower"),
    "clinic": ("clinic",),
    "courthouse": ("courthouse",),
    "police_station": ("07_police_station",),
    "funeral_home": ("funeral_home",),
    "municipal_hall": ("landmark_hall",),
    "union_hall": ("landmark_hall",),
    "museum": ("museum",),
    "country_club": ("country_club",),
    "marina": ("marina",),
    "adult_venue": ("strip_club",),
    "repair_garage": ("auto_shop", "gs_auto_shop", "cr_garage", "night_auto"),
    "warehouse": ("warehouse", "large_warehouse"),
    "storage_facility": ("self_storage",),
    "brewery": ("brewery",),
    "truck_depot": ("depot", "freight_terminal"),
    "rail_station": ("rail_station",),
    "airport_terminal": ("airport_terminal",),
    "parking_garage": ("parking_garage",),
    "fuel_station": ("gas_station", "cr_gas", "gas_street", "fuel_stop_heist"),
    "produce_market": ("market_hall",),
    "apartment": ("apartment_walkup",),
    "twin_house": ("twin",),
    "detached_house": ("mansion",),
}

#: The template an archetype implies when the brief says `auto`: the first row whose word the
#: archetype's name carries wins, so the order is load-bearing -- `gas_station` carries
#: `station`, and the fuel row stands before the station row; `country_club` carries `club`,
#: and the recreation row stands before the evening row.
TEMPLATE_BY_WORD = (
    (("hospital", "clinic"), "C11_hospital_edge"),
    (("gas", "fuel", "motel"), "C08_roadside_lodging"),
    (("station", "deli", "pharmacy", "apartment", "twin"), "C03_station_neighborhood"),
    (("auto", "garage"), "C05_repair_and_trade_strip"),
    (("warehouse", "depot", "freight", "brewery", "storage", "train", "yard"), "C04_industrial_residential_edge"),
    (("supermarket", "strip_retail", "video", "card"), "C09_small_shopping_center"),
    (("country_club",), "C06_neighborhood_recreation"),
    (("club", "casino", "pizza"), "C10_evening_main_street"),
    (("courthouse", "police", "bank_tower", "landmark"), "C17_administrative_lunch_district"),
    (("bank", "credit"), "C02_borough_civic_center"),
    (("museum", "stadium", "arena"), "C18_large_cultural_campus_edge"),
    (("marina", "harbor"), "C15_marina_restaurant"),
    (("airport", "parking"), "C16_airport_landside_edge"),
    (("funeral", "mansion", "rowhouse"), "C07_parish_block"),
    (("store", "corner", "convenience", "stop"), "C01_corner_services"),
)
AUTO = "auto"
DEFAULT_AUTO = "C01_corner_services"


def known(asked) -> bool:
    """Is this a spelling the draw understands: empty (no template), `auto`, or a template id."""
    a = str(asked or "").strip()
    return a == "" or a == AUTO or a in TEMPLATES


def by_archetype(archetype) -> str:
    """The template an archetype's words imply; the corner services when none do."""
    key = str(archetype or "").strip().lower()
    for words, template in TEMPLATE_BY_WORD:
        if any(w in key for w in words):
            return template
    return DEFAULT_AUTO


def template_for(asked, archetype):
    """The template the lot is drawn by: the one asked for, the archetype's under `auto`, and
    None when nothing was asked or the spelling is unknown (the draw as it always was)."""
    a = str(asked or "").strip()
    if a in TEMPLATES:
        return a
    if a == AUTO:
        return by_archetype(archetype)
    return None


def preferred_families(template_id) -> list:
    """The library families a template prefers, in the guide's order: the supporting uses, then
    the ordinary fabric, each use's families in turn, no family twice."""
    if template_id not in TEMPLATES:
        return []
    _anchor, supporting, fabric = TEMPLATES[template_id]
    out = []
    for use in tuple(supporting) + tuple(fabric):
        for fam in CATALOG_FAMILIES.get(use, ()):
            if fam not in out:
                out.append(fam)
    return out


def resolved(asked, archetype) -> dict:
    """What the site spec records: what was asked, what template was got (or none), whether the
    spelling was known, and the families preferred, in order."""
    template = template_for(asked, archetype)
    return {"asked": str(asked or ""), "got": template or "", "known": known(asked),
            "preferred": preferred_families(template) if template else []}
