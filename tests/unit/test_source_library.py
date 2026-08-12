"""The pipeline must not read its own output as source — roadmap item 7.

`deli_counter/build/` is the source archetype library AND the directory Deli
Counter writes Level Factory's own missions into. The output lands beside the
input carrying the same three REQUIRED suffixes, so it indexes as a perfectly
good building: `lf_lot_demo_001_5017` was drawn into a lot and measured as an
archetype in the 2026-08-09 `module_extents.py --sweep`.

Eleven entries in that directory on 2026-08-09 were not source archetypes, and
this file names every one of them and says why. That matters more than the
count: a test that asserted "eleven are excluded" would pass just as happily on
the wrong eleven.

WHAT THIS COSTS, stated because `REQUIRED` warns about exactly it. Narrowing
the index reshuffles what `pick_lot` draws. Measured on the real library, all
eleven read `navigable: null` with `interior_checked: 0`, so `themed_fitness`
already refused them as UNJUDGED and the THEMED lot does not move — pinned by
`test_the_themed_pool_does_not_move`. The greybox draw does move, and it should:
that is the defect.
"""

import pytest

from packages.pipeline import building_library as bl


# --------------------------------------------------------------------------- #
# The eleven, each with the reason it is out
# --------------------------------------------------------------------------- #

#: Level Factory's own composed outputs. The id is built by this pipeline —
#: `apps/cli/commands/__init__.py` writes `f"lf_{mission_id}"` and
#: `DeliCounterAdapter._level_name` appends `_{seed}` — so the prefix is a
#: label the pipeline printed on its own output, not a word being read for a
#: kind.
COMPOSED_OUTPUTS = [
    "lf_art_probe_001_5017",
    "lf_category5_baie_dore_001_5017",
    "lf_category5_baie_dore_001_5118",
    "lf_category5_baie_dore_001_5219",
    "lf_category5_baie_dore_001_5320",
    "lf_category5_baie_dore_001_5421",
    "lf_lot_demo_001_5017",
    "lf_lot_demo_001_5118",
    "lf_lot_demo_001_5219",
]

#: Facades — a street wall, not a building. Deli Counter says so itself in
#: `<id>.validation.json` (`facade: true`), and both measure 0 markers, 0 rooms
#: and a six-polygon navmesh of three unjoined floor plates.
FACADES = ["gs_facade_rowhome", "gs_facade_storefront"]

THE_ELEVEN = COMPOSED_OUTPUTS + FACADES

SOURCE = ["deli_a01", "deli_a02", "pharmacy_a02", "depot_a01", "bank_branch_a04",
          "final_stand", "cr_deli"]


def _shell(root, aid, *, facade=None, navgate=None, coverage=None,
           validation=True):
    """One archetype on disk: the three REQUIRED files plus what it declares."""
    (root / (aid + ".glb")).write_text("{}")
    (root / (aid + ".gameplay.json")).write_text("{}")
    (root / (aid + ".slots.json")).write_text(
        '{"coverage": %s}' % ("{}" if coverage is None else coverage))
    if validation:
        body = "{}" if facade is None else '{"facade": %s}' % (
            "true" if facade else "false")
        (root / (aid + ".validation.json")).write_text(body)
    if navgate is not None:
        (root / (aid + ".navgate.json")).write_text(navgate)


#: A shell the nav gate judged and passed, post-2026-08-08 scope split.
JUDGED_OK = '{"markers": {"interior_checked": 1}, "navigable": true}'
#: A shell the nav gate measured NOTHING about — the state all eleven are in.
UNJUDGED = '{"markers": {"interior_checked": 0}, "navigable": null}'


def _library(tmp_path, source=SOURCE, non_source=THE_ELEVEN, navgate=JUDGED_OK):
    tmp_path.mkdir(parents=True, exist_ok=True)
    for aid in source:
        _shell(tmp_path, aid, facade=False, navgate=navgate, coverage='{"wall": 40}')
    for aid in non_source:
        _shell(tmp_path, aid, facade=aid in FACADES, navgate=UNJUDGED,
               coverage='{"wall": 40}')
    return tmp_path


# --------------------------------------------------------------------------- #
# What is excluded, and why
# --------------------------------------------------------------------------- #

def test_every_one_of_the_eleven_is_named_and_carries_its_reason(tmp_path):
    """THE POINT. Not "eleven were dropped" -- which eleven, and on what
    grounds. A count alone would pass on the wrong set."""
    _library(tmp_path)
    complete, _incomplete, non_source = bl.index(tmp_path)
    assert sorted(e["id"] for e in non_source) == sorted(THE_ELEVEN)
    assert sorted(e["id"] for e in complete) == sorted(SOURCE)
    for entry in non_source:
        assert entry["reason"], entry["id"]
    by_id = {e["id"]: e["reason"] for e in non_source}
    for aid in COMPOSED_OUTPUTS:
        assert "composed output" in by_id[aid]
    for aid in FACADES:
        assert "facade" in by_id[aid]


def test_a_composed_output_is_never_drawn_into_a_lot(tmp_path):
    """The defect itself: `lf_lot_demo_001_5017` was placed as a building and
    measured as an archetype in the 2026-08-09 sweep."""
    complete, _i, _n = bl.index(_library(tmp_path))
    for seed in (5017, 5118, 5219, 5320, 5421):
        lot = bl.pick_lot(complete, seed, 5)
        assert not [e for e in lot if e["id"].startswith("lf_")], lot


def test_the_facade_rule_reads_deli_counters_flag_not_the_name(tmp_path):
    """Put wrong on purpose, both directions. A name rule would agree with the
    flag on this library and disagree the moment somebody authors a building
    called `gs_facade_*` -- which is the `module_stem` defect, where a filename
    stood in for a dimension and one building's modules resolved against
    another's slots."""
    _shell(tmp_path, "gs_facade_but_a_real_building", facade=False)
    _shell(tmp_path, "quiet_row_a01", facade=True)
    complete, _i, non_source = bl.index(tmp_path)
    assert [e["id"] for e in complete] == ["gs_facade_but_a_real_building"]
    assert [e["id"] for e in non_source] == ["quiet_row_a01"]


def test_deli_counter_not_having_said_is_not_deli_counter_saying_yes(tmp_path):
    """Fails open, deliberately. Exactly one complete shell in the library has
    no validation manifest -- `cbp_town_finale_midbalanced_schemafixed` -- and
    it is a building. Reading absence as exclusion would drop it for never
    having been judged."""
    _shell(tmp_path, "cbp_town_finale_midbalanced_schemafixed", validation=False)
    complete, _i, non_source = bl.index(tmp_path)
    assert [e["id"] for e in complete] == \
        ["cbp_town_finale_midbalanced_schemafixed"]
    assert non_source == []


def test_an_unreadable_validation_manifest_is_not_a_facade_either(tmp_path):
    """Same rule as `_manifest` states: truncated, absent and not-an-object all
    answer the same thing, and none of them answers `facade`."""
    _shell(tmp_path, "torn_a01", validation=False)
    (tmp_path / "torn_a01.validation.json").write_text('{"facade": tr')
    complete, _i, non_source = bl.index(tmp_path)
    assert [e["id"] for e in complete] == ["torn_a01"]
    assert non_source == []


# --------------------------------------------------------------------------- #
# Reported, not swallowed
# --------------------------------------------------------------------------- #

def test_a_non_source_entry_is_not_reported_as_a_missing_manifest(tmp_path):
    """Two lists because they are two different things. A composed site with a
    hole in it is not an archetype with a hole in it, and saying so sends
    somebody to Deli Counter to rebuild a file that should never have been
    indexed at all."""
    _shell(tmp_path, "deli_a01", facade=False)
    (tmp_path / "lf_lot_demo_001_5017.glb").write_text("{}")     # nothing else
    complete, incomplete, non_source = bl.index(tmp_path)
    assert [e["id"] for e in complete] == ["deli_a01"]
    assert incomplete == []
    assert [e["id"] for e in non_source] == ["lf_lot_demo_001_5017"]


def test_the_index_reports_three_lists(tmp_path):
    """The arity change is the mechanism. A filter that just shortened
    `complete` would be the silent narrowing this module refuses everywhere
    else -- every caller is now obliged to say what it does with the third."""
    assert len(bl.index(tmp_path)) == 3
    assert bl.index(tmp_path / "nope") == ([], [], [])


# --------------------------------------------------------------------------- #
# What it costs
# --------------------------------------------------------------------------- #

def test_the_themed_pool_does_not_move(tmp_path):
    """MEASURED, not assumed, and it is the reason this can land without
    re-baselining the themed runs. All eleven read `navigable: null` with
    `interior_checked: 0` on the real library, so `themed_fitness` already
    refused every one as UNJUDGED -- `require_themed_shells` had removed
    exactly these eleven before `index` ever learned to. Pin it, because if a
    future re-bake makes one of them navigable this silently stops being true.
    """
    polluted = _library(tmp_path / "a")
    clean = _library(tmp_path / "b", non_source=[])
    lots = []
    for d in (polluted, clean):
        complete, _i, _n = bl.index(d)
        fit = bl.require_themed_shells(complete, 3)
        lots.append([e["id"] for e in bl.pick_lot(fit, 5421, 3)])
    assert lots[0] == lots[1]

    # And say WHY it does not move, so a failure here reads as a change in the
    # premise rather than a mystery: the eleven never reached the themed pool.
    complete, _i, _n = bl.index(polluted)
    _fit, unfit = bl.themed_report(complete)
    assert {e["id"] for e in unfit} == set()      # they are gone before this


def test_the_eleven_would_have_been_refused_by_themed_fitness_anyway(tmp_path):
    """The measurement the test above rests on, made directly. Handed the
    eleven as if they were candidates, `themed_fitness` refuses every one for
    being UNJUDGED -- which is why the themed lot does not move and the greybox
    lot does."""
    _library(tmp_path)
    rows = [{"id": aid, "family": aid,
             "slots": str(tmp_path / (aid + ".slots.json")),
             "navgate": str(tmp_path / (aid + ".navgate.json"))}
            for aid in THE_ELEVEN]
    fit, unfit = bl.themed_report(rows)
    assert fit == []
    assert len(unfit) == len(THE_ELEVEN)
    for row in unfit:
        assert any("unjudged" in str(r) for r in row["reasons"]), row


def test_the_greybox_draw_is_what_actually_narrows(tmp_path):
    """The other half of the same measurement, and the defect itself: nothing
    narrowed the greybox pool, which is how a composed site came to be placed
    as a building. The directory still holds all eleven; the index no longer
    offers them."""
    root = _library(tmp_path)
    raw = {p.name[: -len(".glb")] for p in root.glob("*.glb")}
    complete, _i, non_source = bl.index(root)
    offered = {e["id"] for e in complete}
    assert set(THE_ELEVEN) <= raw                  # still on disk
    assert not set(THE_ELEVEN) & offered           # not in the pool
    assert offered | {e["id"] for e in non_source} == raw


# --------------------------------------------------------------------------- #
# The rule itself, asked directly
# --------------------------------------------------------------------------- #

def test_source_exclusion_answers_empty_for_a_building(tmp_path):
    """`""` is "this IS a source archetype". A truthy return is always a
    sentence a reader can act on."""
    _shell(tmp_path, "pharmacy_a02", facade=False)
    assert bl.source_exclusion(tmp_path, "pharmacy_a02") == ""


@pytest.mark.parametrize("aid", THE_ELEVEN)
def test_source_exclusion_answers_a_sentence_for_each_of_the_eleven(tmp_path, aid):
    _library(tmp_path)
    why = bl.source_exclusion(tmp_path, aid)
    assert why and not why.endswith("."), why
