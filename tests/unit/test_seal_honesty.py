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


# ---------------------------------------------------------------------------
# an upstairs room whose only floor is inferred (cold run 9058)
# ---------------------------------------------------------------------------
def _spans(name, x, y, z, *, approximate):
    """A box from its ``(low, high)`` spans, the form the probe printed."""
    spans = (x, y, z)
    return Box(name, tuple((lo + hi) / 2.0 for lo, hi in spans),
               tuple(hi - lo for lo, hi in spans), approximate=approximate)


#: Godot metres. The objective is cold run 9058's, `b1/OBJECTIVE_UPSTAIRS` in
#: Deli Counter's `twin_a01`; the spawn is moved in from (53, 1, -8) to keep
#: the field small, onto the same street.
TWIN_SPAWN = (20.0, 1.0, -10.0)
TWIN_OBJECTIVE = (-4.0, 2.9, -13.0)


def _twin(*, approximate=True, stairs=True):
    """`twin_a01` as `ground_contact` reads it out of the `.glb` on 9058.

    Spans are the scene-root ones the reader produced for b1 (placed at x 0,
    z -10, turned 180 degrees), trimmed to the two storeys that matter: slabs
    0 and 1, both storeys' exterior walls and cross walls with their openings
    closed (a bounding box has none), and the two storey-0 flights of the
    switchbacks with their discharge landings at 2.9. On 9058 every one of
    them is a collision MESH's bounding box, so every one is approximate.
    """
    def box(name, x, y, z):
        return _spans(name, x, y, z, approximate=approximate)

    boxes = [
        Box("street", (0.0, -0.25, -10.0), (60.0, 0.5, 40.0)),
        box("slab_col_0", (-8.0, 8.0), (-0.25, 0.0), (-16.5, -3.5)),
        box("slab_col_1", (-8.0, 8.0), (2.65, 2.9), (-16.5, -3.5)),
    ]
    for storey, rise in enumerate(((0.0, 2.65), (2.9, 5.55))):
        boxes += [
            box(f"ext_{storey}_N", (-8.15, 8.15), rise, (-3.65, -3.35)),
            box(f"ext_{storey}_S", (-8.15, 8.15), rise, (-16.65, -16.35)),
            box(f"ext_{storey}_E", (-8.15, -7.85), rise, (-16.35, -3.65)),
            box(f"ext_{storey}_W", (7.85, 8.15), rise, (-16.35, -3.65)),
            box(f"int_{storey}_cross", (-8.0, 8.0), rise, (-11.65, -11.35)),
        ]
    if stairs:
        boxes += [
            box("stair0ramp_0", (4.0, 4.9), (-0.26, 3.1), (-8.68, -4.38)),
            box("stair0col_discharge_0", (2.7, 5.3), (2.69, 2.9), (-9.4, -8.6)),
            box("stair1ramp_0", (-4.0, -3.1), (-0.26, 3.1), (-8.68, -4.38)),
            box("stair1col_discharge_0", (-5.3, -2.7), (2.69, 2.9), (-9.4, -8.6)),
        ]
    return boxes


def _twin_findings(boxes):
    """``(refusals, coded advisories)`` for the crew, one enemy on the street,
    and the upstairs objective."""
    def node(name, parent, p):
        return [f'[node name="{name}" type="Node3D" parent="{parent}"]',
                "transform = Transform3D(1, 0, 0, 0, 1, 0, 0, 0, 1, "
                f"{p[0]:g}, {p[1]:g}, {p[2]:g})", ""]

    text = "\n".join(
        ["[gd_scene load_steps=1 format=3]", "",
         '[node name="site_walk" type="Node3D"]', ""]
        + node("LT_PlayerSpawn", ".", TWIN_SPAWN)
        + ['[node name="LT_EnemySpawnPoints" type="Node3D" parent="."]', ""]
        + node("Enemy_0", "LT_EnemySpawnPoints", (-20.0, 1.0, -25.0))
        + node("LT_ObjectivePoint", ".", TWIN_OBJECTIVE))
    reading = Reading(tuple(boxes), ())
    return (sp.check_spawn_placement_text(text, reading),
            sp.advise_spawn_placement_coded(text, reading))


def test_the_one_storey_field_cannot_see_a_switchback_under_an_inferred_slab():
    """What 9058's field held, pinned so the fix below has something to explain.

    Slab 1's bounding box spans the whole footprint, stairwells included, and
    its top (2.9) is inside `FIELD_BAND` of the street, so it is the highest
    in-band surface over every cell of the building: the ground floor and both
    flights are not in the field at all. The flood fill stops at the
    building's edge, where the surface jumps 2.9 m.
    """
    boxes = _twin()
    field = sp.heightfield(boxes, support_under(TWIN_SPAWN, boxes).top)
    for x, z in ((-3.55, -6.5), (4.45, -6.5), (-4.0, -13.0), (0.0, -15.0)):
        assert abs(field.floor[field.index(x, z)] - 2.9) < 1e-9, (x, z)
    reach = sp.walk_distances(field, field.index(TWIN_SPAWN[0], TWIN_SPAWN[2]))
    assert field.index(TWIN_OBJECTIVE[0], TWIN_OBJECTIVE[2]) not in reach


def test_an_upstairs_objective_in_an_inferred_shell_is_reported_not_refused():
    """Cold run 9058, refused at export: "LT_ObjectivePoint is sealed off from
    the crew spawn".

    The seal was never measured. The strict field has no stair to find (see
    above), and the counterfactual that is meant to confirm a seal sets slab 1
    aside with every other inferred box taller than a step -- so it holds no
    surface at 2.9 and answers "on a storey this field does not see".
    `_split_seals` counted any answer but "reachable" as confirmation. On the
    9058 scene Lot's contract bake paths 81.0 m from the crew spawn up stair1
    to the objective, and a 0.35 x 1.8 capsule walks it to within 0.31 m.
    """
    problems, advice = _twin_findings(_twin())
    assert not any("mission destination" in p for p in problems), problems
    unseen = [m for code, m in advice if code == sp.CODE_UNSEEN_STOREY]
    assert len(unseen) == 1 and "LT_ObjectivePoint" in unseen[0], advice
    # not the doorway advisory: that one says the point IS reachable once the
    # inferred walls are gone, and here nothing is known to reach it
    assert not any(code == sp.CODE_UNVERIFIED_SEAL for code, _m in advice), advice


def test_the_verdict_does_not_depend_on_stairs_this_reader_cannot_see():
    """The cost, said out loud: with the flights removed the answer is the same.

    The field never held them, so removing them cannot change what it says.
    This reader cannot tell a building with stairs from one without, and that
    is the argument for reporting rather than refusing -- the walktest, which
    bakes every storey, can.
    """
    assert _twin_findings(_twin()) == _twin_findings(_twin(stairs=False))


def test_an_upstairs_room_built_of_measured_boxes_still_refuses():
    """Only inferred collision is excused.

    The same shell out of `BoxShape3D`s has nothing inferred, so there is no
    counterfactual to consult and the seal the field measured stands.
    """
    problems, _advice = _twin_findings(_twin(approximate=False, stairs=False))
    assert any("LT_ObjectivePoint is sealed off" in p for p in problems), problems


def test_a_counterfactual_that_keeps_the_storey_and_still_cannot_reach_it_refuses():
    """"Unseen" is about the storey leaving the field, and nothing else.

    An inferred shell on the crew's own storey, with a MEASURED ring standing
    inside it: the counterfactual keeps the floor, keeps the ring, and still
    says sealed. That is confirmation, as it always was.
    """
    ring = [_wall("mn", 0.0, -4.0, 8.0, 0.4, approximate=False),
            _wall("ms", 0.0, 4.0, 8.0, 0.4, approximate=False),
            _wall("mw", -4.0, 0.0, 0.4, 8.0, approximate=False),
            _wall("me", 4.0, 0.0, 0.4, 8.0, approximate=False)]
    gates, advises = _verdict(_room(approximate=True) + ring)
    assert gates == ["Route_2"]
    assert advises == []
