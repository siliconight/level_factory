"""Open ground is the defect; distance was only the symptom.

The site that produced this module had its nearest enemy 39 m from the crew
spawn -- outside the 35 m the producer was checking against, and inside the
45 m at which the crew's bot opens fire. The reflex fix is to push the enemy
further out, and it trades `INSTANT_CONTACT` for `BLIND_MAP` without making the
site any better: what was wrong was that two points could see each other across
tens of metres of nothing.

These tests pin the measurement (a solid only blocks a line if it stands *in*
it, not under it or beside it) and pin the output as a placement instruction
rather than a complaint. The sharpest one here is `break_interval` returning
`None`: chest-high cover does not break a standing sightline on flat ground,
and a module that cheerfully proposed a crate anyway would be handing Lot work
that could not help.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from packages.validation.ground_contact import Box  # noqa: E402
from packages.validation.sightlines import (  # noqa: E402
    MIN_COVER_HEIGHT, break_interval, describe, open_sightlines, propose_cover,
    sightline)


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------
def block(name: str, x: float, z: float, sx: float, sz: float,
          height: float, base: float = 0.0) -> Box:
    """A solid standing on ``base``, ``height`` tall."""
    return Box(name, (x, base + height / 2.0, z), (sx, height, sz))


def slab(name: str, x: float, z: float, sx: float, sz: float,
         top: float = 0.0) -> Box:
    return Box(name, (x, top - 0.25, z), (sx, 0.5, sz))


CREW = (-50.0, 0.0, 0.0)
FAR = (50.0, 0.0, 0.0)


# ---------------------------------------------------------------------------
# measuring
# ---------------------------------------------------------------------------
def test_an_empty_yard_leaves_the_whole_line_open():
    line = sightline("crew", CREW, "enemy", FAR, [slab("yard", 0, 0, 200, 200)])
    assert line.length == 100.0
    assert line.is_open
    assert line.blocked_by == ()


def test_a_building_across_the_middle_closes_the_line():
    line = sightline("crew", CREW, "enemy", FAR,
                     [slab("yard", 0, 0, 200, 200),
                      block("shed", 0.0, 0.0, 10.0, 10.0, 4.0)])
    assert not line.is_open
    assert line.blocked_by == ("shed",)
    assert line.open_length == 90.0


def test_a_kerb_is_in_the_way_on_a_plan_view_and_a_rifle_shoots_over_it():
    """The reason the crossing test is not enough on its own.

    A 0.4 m solid spans the line in two dimensions and occludes nothing: the
    sightline runs from an eye at 1.4 m to a chest at 1.0 m and passes a metre
    above it the whole way.
    """
    line = sightline("crew", CREW, "enemy", FAR,
                     [slab("yard", 0, 0, 200, 200),
                      block("kerb", 0.0, 0.0, 10.0, 10.0, 0.4)])
    assert line.is_open


def test_a_first_floor_slab_overhead_is_not_cover_for_the_fight_beneath_it():
    line = sightline("crew", CREW, "enemy", FAR,
                     [slab("yard", 0, 0, 200, 200),
                      slab("mezzanine", 0.0, 0.0, 20.0, 20.0, top=4.0)])
    assert line.is_open


def test_the_building_you_are_standing_in_is_not_cover_from_itself():
    """A spawn that landed indoors would otherwise pass every sightline test.

    Same rule Lot applies for the same reason: an occluder containing an
    endpoint tells you nothing about what that endpoint can see out of.
    """
    inside = (0.0, 0.0, 0.0)
    line = sightline("crew", inside, "enemy", FAR,
                     [block("hall", 0.0, 0.0, 30.0, 30.0, 6.0)])
    assert line.is_open


def test_two_overlapping_blockers_are_not_counted_twice():
    """Otherwise a row of touching props reads as blocking more than the line is long."""
    line = sightline("crew", CREW, "enemy", FAR,
                     [block("a", 0.0, 0.0, 20.0, 10.0, 4.0),
                      block("b", 5.0, 0.0, 20.0, 10.0, 4.0)])
    assert 0.0 <= line.open_length <= line.length
    assert round(line.open_length, 3) == 75.0


def test_pairs_are_reported_longest_first_and_only_past_the_opening_range():
    """The longest line is usually the one whose fix shortens three others."""
    points = {"crew": CREW, "near": (-20.0, 0.0, 0.0), "far": FAR}
    lines = open_sightlines(points, [slab("yard", 0, 0, 300, 300)], limit=45.0)
    assert [(l.a_name, l.b_name) for l in lines] == [("crew", "far"), ("far", "near")]
    assert lines[0].length > lines[1].length


def test_a_blocked_pair_is_not_an_open_sightline_however_long_it_is():
    points = {"crew": CREW, "far": FAR}
    boxes = [slab("yard", 0, 0, 300, 300), block("tower", 0.0, 0.0, 12.0, 12.0, 8.0)]
    assert open_sightlines(points, boxes, limit=45.0) == []


# ---------------------------------------------------------------------------
# what to do about it
# ---------------------------------------------------------------------------
def test_cover_has_to_stop_both_sides_or_it_stops_nothing():
    """Two lines run between the same two points, not one.

    The crew sights from its eye at the enemy's chest and the enemy does the
    same back, so a solid tall enough for one of them can sit under the other.
    That is not half a fix: Laser Tag stamps first contact on the first shot
    fired by *either* side, so cover that leaves one side a free shot leaves
    the clock exactly where it was.

    A 1.1 m block clears the crew's outgoing line over most of its length --
    that line descends from 1.4 m to 1.0 m -- and never touches the incoming
    one, which is climbing while the other falls.
    """
    boxes = [slab("yard", 0, 0, 300, 300)]
    line = sightline("crew", CREW, "enemy", FAR, boxes)
    assert break_interval(line, 1.1) is None
    assert propose_cover([line], height=1.1, min_height=1.0) == []


def test_on_flat_ground_the_shortest_workable_cover_works_at_one_spot_only():
    """`MIN_COVER_HEIGHT` is derived, not chosen.

    The two lines cross at the midpoint at the mean of eye and chest height, so
    a solid exactly that tall occludes both at that one position and nowhere
    else. It is the floor under every cover proposal on a flat site, and the
    reason the interval is worth returning rather than a point.
    """
    boxes = [slab("yard", 0, 0, 300, 300)]
    line = sightline("crew", CREW, "enemy", FAR, boxes)
    assert MIN_COVER_HEIGHT == 1.2
    interval = break_interval(line, MIN_COVER_HEIGHT)
    assert interval is not None
    lo, hi = interval
    assert abs(lo - 0.5) < 0.05 and abs(hi - 0.5) < 0.05, interval
    # And a taller solid earns room to move along the line.
    wide = break_interval(line, 1.8)
    assert wide[1] - wide[0] > 0.5


def test_a_solid_taller_than_both_ends_breaks_the_line_anywhere_along_it():
    line = sightline("crew", CREW, "enemy", FAR, [slab("yard", 0, 0, 300, 300)])
    interval = break_interval(line, 1.8)
    assert interval is not None
    lo, hi = interval
    assert lo >= 0.1 and hi <= 0.9, "never propose a solid on somebody's head"


def test_a_solid_shorter_than_the_minimum_is_a_decoration_not_cover():
    line = sightline("crew", CREW, "enemy", FAR, [slab("yard", 0, 0, 300, 300)])
    assert break_interval(line, 0.6) is None


def test_an_enemy_on_a_roof_is_measured_from_the_yard_the_cover_stands_on():
    """The rooftop case, and why the floor is read from the boxes.

    A crew on the ground and an enemy on a 3 m roof are not looking along a
    ramp. The line climbs away from the yard, so a 2 m block works near the
    crew and is useless further out -- treating the ground between them as a
    straight interpolation would report the opposite and propose a solid
    hovering halfway up.
    """
    boxes = [slab("yard", 0, 0, 300, 300), block("roof", 50.0, 0.0, 16.0, 16.0, 3.0)]
    high = (50.0, 3.0, 0.0)
    line = sightline("crew", CREW, "enemy", high, boxes)
    interval = break_interval(line, 2.0, boxes=boxes)
    assert interval is not None
    assert interval[0] < 0.15, "usable from the crew's end"
    assert interval[1] < 0.6, "and not out where the line has climbed away"


def test_cover_is_proposed_towards_the_crews_approach_rather_than_the_midpoint():
    """A line broken at its midpoint is fair to both ends, which is the problem.

    The crew walks and the enemy holds. Cover a third of the way along gives the
    crew something to move between; the same reasoning that puts a ladder's
    slab-hole on the approach side.
    """
    line = sightline("crew", CREW, "enemy", FAR, [slab("yard", 0, 0, 300, 300)])
    proposal = propose_cover([line], height=1.8)[0]
    assert proposal.x < 0.0, "nearer the crew than the enemy"
    assert -50.0 < proposal.x < 0.0
    assert proposal.as_dict()["breaks"] == "crew->enemy"


def test_a_proposal_placed_where_it_was_asked_for_actually_breaks_the_line():
    """The loop that matters: propose, place, re-measure, and it is closed.

    Without this the module is a plausible-looking coordinate generator.
    """
    boxes = [slab("yard", 0, 0, 300, 300)]
    line = sightline("crew", CREW, "enemy", FAR, boxes)
    assert line.is_open
    p = propose_cover([line], height=1.8)[0]
    placed = boxes + [block("cover", p.x, p.z, 3.0, 3.0, p.height)]
    assert not sightline("crew", CREW, "enemy", FAR, placed).is_open


def test_the_finding_says_what_to_do_and_keeps_the_fact_it_was_drawn_from():
    line = sightline("crew", CREW, "enemy", FAR, [slab("yard", 0, 0, 300, 300)])
    text = describe([line], limit=45.0)[0]
    assert "100.0 m of open ground" in text
    assert "45 m" in text
    assert "cover near" in text


def test_a_line_no_cover_can_break_says_it_needs_a_building():
    """Silence here would read as "nothing to do" for the worst case there is.

    A sniper ten metres up on a tower sees over anything short enough to call
    cover, from every position along the line. The finding has to say that the
    answer is a building rather than quietly proposing nothing.
    """
    boxes = [slab("yard", 0, 0, 300, 300), block("tower", 50.0, 0.0, 8.0, 8.0, 10.0)]
    line = sightline("crew", CREW, "sniper", (50.0, 10.0, 0.0), boxes)
    assert line.is_open
    assert break_interval(line, 1.8, boxes=boxes) is None
    text = describe([line], limit=45.0, boxes=boxes)[0]
    assert "needs a building" in text
    assert "cover near" not in text


def test_a_long_list_is_summarised_rather_than_dumped():
    boxes = [slab("yard", 0, 0, 600, 600)]
    points = {f"p{i}": (float(i * 60 - 300), 0.0, float(i * 7)) for i in range(6)}
    lines = open_sightlines(points, boxes, limit=45.0)
    assert len(lines) > 6
    out = describe(lines, limit=45.0)
    assert len(out) == 7
    assert out[-1].startswith("and ")
    assert "more open sightline" in out[-1]


def test_nothing_open_is_nothing_said():
    assert describe([], limit=45.0) == []
    assert open_sightlines({}, [], limit=45.0) == []
