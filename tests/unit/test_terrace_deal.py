"""The terrace deals its houses (Level Factory 0.142.0).

Cold run 9160 doubled the rowhome Empties to twelve, expecting a row to show
each about twice. Its three candidates' rows showed 10, 12 and 10 of them,
one design up to 6 times: a uniform draw's spread. Dealt from a shuffled bag,
a row of n houses from k designs shows each floor(n/k) or one more times.
"""
from packages.pipeline import empties, site_variation

#: twelve rowhome-sized designs, 5.5 to 6.5 m wide and 12.3 m deep, as
#: `street_line.shell_extents` reads them. Literals.
EXT = {"gs_empty_rowhome_%s" % c: (-w / 2.0, w / 2.0, -6.15, 6.15)
       for c, w in zip("abcdefghijkl", (6.0, 5.5, 6.5, 6.0, 5.5, 6.0, 5.8, 6.3, 6.1, 6.2, 5.6, 6.4))}
ROWS = [{"id": k} for k in sorted(EXT)]
THROUGH = {"a": [-90.0, -27.65], "b": [90.0, -27.65], "width": 10.0, "sidewalk": 3.0}


def _kinds(seed, roads=(THROUGH,)):
    placed, _ = empties.terrace(ROWS, EXT, site_variation.stream(seed), list(roads), 180.0)
    return [p["archetype"] for p in placed]


def _dealt_whole(kinds):
    k = len(ROWS)
    return all(sorted(kinds[i:i + k]) == sorted(EXT) for i in range(0, len(kinds) - k + 1, k))


def test_every_design_is_dealt_before_any_is_dealt_again():
    """FAILS ON 0.141.0: drawn uniformly, a design came round again first."""
    for seed in (9080, 9181, 9282, 5, 6):
        kinds = _kinds(seed)
        assert len(kinds) > len(ROWS), (seed, len(kinds))
        assert _dealt_whole(kinds), (seed, kinds)


def test_a_row_shows_each_design_as_evenly_as_its_length_allows():
    for seed in (9080, 9181, 9282):
        kinds = _kinds(seed)
        counts = [kinds.count(d) for d in EXT]
        assert max(counts) - min(counts) <= 1, (seed, counts)


def test_neighbours_differ_across_a_deal_too():
    for seed in range(40):
        kinds = _kinds(seed)
        assert all(a != b for a, b in zip(kinds, kinds[1:])), seed


def test_a_house_turned_away_by_a_road_is_placed_past_it():
    """A pick that a southward road blocks stays on the bag, so the row past
    the road still deals every design once before repeating one."""
    south = {"a": [10.0, -27.65], "b": [10.0, -80.0], "width": 8.0, "sidewalk": 2.0}
    kinds = _kinds(9080, roads=(THROUGH, south))
    assert len(kinds) > len(ROWS) and _dealt_whole(kinds)
