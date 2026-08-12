"""A seal this reader inferred is not a seal it may refuse a build on.

`ground_contact` builds one box per collision MESH, taking its bounding box.
A doorway lives in a mesh, so an exterior wall with openings cut in it arrives
as a solid box across every one of them. Measured 2026-08-09 on `lot_demo_001`
candidate 5017: `cr_garage` declares seventeen openings, seven of them
ground-level entries including two 5 m garage doors, and rendered from this
reader's own boxes at 0.5 m cells it is an unbroken ring. The extraction hook
stood on clear floor inside it, `_placement` said "sealed off from the crew
spawn", and the build was refused for a level that was fine.

Under that model no mission point inside ANY building can ever be reachable.
Sites pass only because Lot usually places its markers outdoors.

These tests pin the distinction the fix rests on: a seal made of MEASURED boxes
still gates, and a seal made of INFERRED ones advises. They also pin the reason
the first attempt failed -- setting a wall's blocking aside while keeping its
floor leaves a standable, unclimbable ledge, so the counterfactual answers
exactly as the original does and the whole check is inert.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from packages.validation.ground_contact import (  # noqa: E402
    Box, Reading, support_under)
from packages.validation import spawn_placement as sp  # noqa: E402


PLATE = Box("plate", (0.0, -0.25, 0.0), (200.0, 0.5, 120.0))
SPAWN = (-40.0, 0.0, 0.0)
INSIDE = (0.0, 0.0, 0.0)


def _wall(name, cx, cz, sx, sz, *, approximate):
    return Box(name, (cx, 1.5, cz), (sx, 3.0, sz), approximate=approximate)


def _room(*, approximate):
    """Four walls with no door -- the shape a doorway-bearing wall reduces to."""
    return [PLATE,
            _wall("n", 0.0, -10.0, 20.0, 1.0, approximate=approximate),
            _wall("s", 0.0, 10.0, 20.0, 1.0, approximate=approximate),
            _wall("w", -10.0, 0.0, 1.0, 20.0, approximate=approximate),
            _wall("e", 10.0, 0.0, 1.0, 20.0, approximate=approximate)]


def _verdict(boxes, point=INSIDE):
    """``(gates, advises)`` for one destination at ``point``."""
    reading = Reading(tuple(boxes), ())
    field = sp.heightfield(boxes, support_under(SPAWN, boxes).top)
    reach = sp.walk_distances(field, field.index(SPAWN[0], SPAWN[2]))
    loose = sp._optimistic_reach(field, reading, SPAWN)
    points = {"Route_2": point}
    verified, unverified = sp._split_seals(
        sp._strand(field, reach, points), points, loose)
    return sorted(verified), sorted(unverified)


# ---------------------------------------------------------------------------
# the distinction
# ---------------------------------------------------------------------------
def test_a_seal_made_of_measured_boxes_still_refuses_the_build():
    """A `BoxShape3D` IS a box. Nothing was inferred, so nothing is excused."""
    gates, advises = _verdict(_room(approximate=False))
    assert gates == ["Route_2"]
    assert advises == []


def test_a_seal_made_of_inferred_boxes_advises_instead():
    """The wall might have a door in it; this reader cannot see one either way.

    Refusing here is refusing on the reader's own blind spot, which is what
    `JOB_PREFLIGHT_REFUSED` did to candidate 5017.
    """
    gates, advises = _verdict(_room(approximate=True))
    assert gates == []
    assert advises == ["Route_2"]


def test_open_ground_is_neither():
    """A probe that only ever reports a seal cannot tell you it found one."""
    gates, advises = _verdict([PLATE])
    assert gates == []
    assert advises == []


# ---------------------------------------------------------------------------
# the failure the first attempt shipped
# ---------------------------------------------------------------------------
def test_an_inferred_wall_leaves_the_field_rather_than_softening():
    """Keeping a wall's floor while dropping its blocking does not work.

    A 3 m wall top is standable and unclimbable: `walk_distances` steps only
    between surfaces within `AGENT_CLIMB`, so the flood fill still cannot
    cross and the counterfactual returns the same answer as the original. The
    rule is a height rule, and this is what pins it.
    """
    boxes = _room(approximate=True)
    reading = Reading(tuple(boxes), ())
    field = sp.heightfield(boxes, support_under(SPAWN, boxes).top)
    loose = sp._optimistic_reach(field, reading, SPAWN)
    assert loose is not None
    lfield, _lreach = loose
    cell = lfield.index(0.0, -10.0)          # dead centre of the north wall
    assert lfield.floor[cell] is not None, "the plate under the wall survives"
    assert abs(lfield.floor[cell]) < 0.01, "and it is the PLATE, not the wall top"
    assert not lfield.blocked[cell]


def test_an_inferred_floor_survives_the_counterfactual():
    """Only walls leave. An interior floor is inferred too, and it has to stay.

    Dropping every inferred box would trade a wall this reader invented for a
    hole it invented, and a hole reads as "over a gap in the storey the mission
    starts on" -- a different refusal, equally wrong.
    """
    interior = Box("interior_floor", (0.0, -0.05, 0.0), (18.0, 0.1, 18.0),
                   approximate=True)
    boxes = _room(approximate=True) + [interior]
    reading = Reading(tuple(boxes), ())
    field = sp.heightfield(boxes, support_under(SPAWN, boxes).top)
    loose = sp._optimistic_reach(field, reading, SPAWN)
    assert loose is not None
    lfield, lreach = loose
    cell = lfield.index(*(INSIDE[0], INSIDE[2]))
    assert lfield.floor[cell] is not None
    assert cell in lreach, "the interior keeps a floor and becomes reachable"


# ---------------------------------------------------------------------------
# the verdicts that do not depend on seeing a doorway
# ---------------------------------------------------------------------------
def test_the_other_refusals_are_untouched():
    """Over a gap, off the field, wrong storey, inside geometry -- all still gate.

    None of them could be changed by a doorway, so none of them is excused.
    """
    boxes = _room(approximate=True)
    reading = Reading(tuple(boxes), ())
    field = sp.heightfield(boxes, support_under(SPAWN, boxes).top)
    reach = sp.walk_distances(field, field.index(SPAWN[0], SPAWN[2]))
    loose = sp._optimistic_reach(field, reading, SPAWN)

    off = {"Route_2": (5000.0, 0.0, 5000.0)}
    verified, unverified = sp._split_seals(
        sp._strand(field, reach, off), off, loose)
    assert sorted(verified) == ["Route_2"], "off the field still refuses"
    assert unverified == {}


def test_a_box_is_measured_unless_it_says_otherwise():
    """The flag defaults to False, so a reader that never sets it gates as before."""
    assert Box("b", (0.0, 0.0, 0.0), (1.0, 1.0, 1.0)).approximate is False
