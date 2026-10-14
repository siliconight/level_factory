"""A spent bag is not a full street: the near side deals afresh where a design fits and the bag's
remainder does not (Level Factory 0.203.0, factory roadmap 241).

`empties.infill` deals the near side's blocks as the far side deals them -- every design once, then a new
bag -- and 0.201.0 left a room open whenever what was left in the bag was too wide for it. Cold run 9289's
seed_9104 kept a 6.70 m room between two of the mission's buildings that its 6.6 m block fits, because that
block had been dealt already. Over the three rooms of this file's street and forty seeds, 0.202.0 left 58 of
the 120 rooms with a design's width or more standing empty.
"""
from packages.pipeline import empties, site_variation

#: Three mid-rises as `street_line.shell_extents` reads them (x0, x1, y0, y1): 15, 24 and 6.6 m wide.
EXT = {"gs_midrise_a": (-7.5, 7.5, -7.5, 7.5), "gs_midrise_b": (-12.0, 12.0, -7.5, 7.5),
       "gs_midrise_i": (-3.3, 3.3, -7.5, 7.5)}
ROWS = [{"id": k} for k in EXT]
NARROWEST = 6.6
THROUGH = {"a": [-90.0, -27.65], "b": [90.0, -27.65], "width": 10.0, "sidewalk": 3.0}
LINE = -17.65
BUILDINGS = [(-40.0, -10.0, LINE, LINE + 40.0), (20.0, 50.0, LINE, LINE + 40.0)]
#: The rooms the plate's ends and the buildings' passages leave on the near line: 42, 22 and 32 m.
ROOMS = [(-90.0 + empties.CLEARANCE, -40.0 - empties.NEAR_PASSAGE),
         (-10.0 + empties.NEAR_PASSAGE, 20.0 - empties.NEAR_PASSAGE),
         (50.0 + empties.NEAR_PASSAGE, 90.0 - empties.CLEARANCE)]


def _spans(placed):
    return sorted((p["at"][0] + EXT[p["archetype"]][0], p["at"][0] + EXT[p["archetype"]][1]) for p in placed)


def test_no_room_a_design_fits_is_left_open():
    """In every room the blocks stand end to end from its start, and what is left at its end is narrower
    than the narrowest design."""
    for seed in range(1, 41):
        placed, _ = empties.infill(ROWS, EXT, site_variation.stream(seed), [THROUGH], 180.0, BUILDINGS)
        spans = _spans(placed)
        for lo, hi in ROOMS:
            inside = [s for s in spans if lo - 1e-9 <= s[0] and s[1] <= hi + 1e-9]
            end = lo
            for s0, s1 in inside:
                assert abs(s0 - end) < 1e-6, (seed, lo, hi, inside)       # end to end, from the start
                end = s1
            assert hi - end < NARROWEST - 1e-9, (seed, lo, hi, inside)


class _Counting:
    """A stream that counts what is drawn from it."""

    def __init__(self, stream):
        self.stream, self.drawn = stream, 0

    def __iter__(self):
        return self

    def __next__(self):
        self.drawn += 1
        return next(self.stream)


def test_a_remainder_no_design_fits_asks_nothing_of_the_stream():
    """A fresh deal is asked for only when some design fits what is left, so the bag never grows by a deal
    that could not help. One 42 m room before a building that runs to the plate's end, two designs of 15 and
    24 m: one deal fills it with both; the empty bag is dealt again as it always was, and the 3 m left asks
    for nothing more. A deal of two designs is one draw."""
    two = {k: EXT[k] for k in ("gs_midrise_a", "gs_midrise_b")}
    rows = [{"id": k} for k in two]
    s = _Counting(site_variation.stream(5))
    placed, _ = empties.infill(rows, two, s, [THROUGH], 180.0, [(-40.0, 90.0, LINE, LINE + 40.0)])
    assert sorted(p["archetype"] for p in placed) == ["gs_midrise_a", "gs_midrise_b"]
    assert s.drawn == 2
