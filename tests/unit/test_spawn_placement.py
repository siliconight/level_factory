"""Standing on a floor is not the same as standing somewhere reachable.

`check_ground_contact` passed the site that produced this module without a
word: every one of its six enemy spawns had a slab beneath it. Laser Tag then
refused the whole map with `UNREACHABLE_SPAWN` and completed zero runs, because
the producer had sampled the straight line from the crew spawn through the
objective to the extraction and dropped an enemy every few metres along it --
straight through the middle of two 44 m buildings.

These tests pin the two claims apart, and pin the direction of the model's
error: it is optimistic on purpose, so a wall it cannot see makes it quieter,
never louder.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from packages.validation.ground_contact import (  # noqa: E402
    Box, Reading, support_under)
from packages.validation.spawn_placement import (  # noqa: E402
    AGENT_CLIMB, CELL, MAX_SPAWN_LIFT, MIN_ENGAGEMENT_STANDOFF, Field,
    advise_spawn_placement, advise_spawn_placement_text, check_spawn_placement,
    check_spawn_placement_text, classify, heightfield, walk_distances)


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------
def slab(name: str, x: float, z: float, sx: float, sz: float,
         top: float = 0.0) -> Box:
    """A 0.5 m floor slab whose walking surface sits at ``top``."""
    return Box(name, (x, top - 0.25, z), (sx, 0.5, sz))


def wall(name: str, x: float, z: float, sx: float, sz: float,
         height: float = 4.0) -> Box:
    """A solid standing on the ground plane, tall enough to stop an agent."""
    return Box(name, (x, height / 2.0, z), (sx, height, sz))


#: A 40 x 20 m yard divided by a wall at x = 0 with no gap in it. The crew
#: starts at x = -15, the enemy at x = +15: eight metres apart as the crow
#: flies once you ignore the wall, and no walk between them at all.
def divided_yard():
    return [slab("yard", 0.0, 0.0, 40.0, 20.0),
            wall("partition", 0.0, 0.0, 1.0, 20.0)]


def scene_text(points) -> str:
    """A minimal staged level declaring the Laser Tag hooks at ``points``."""
    body = ['[gd_scene load_steps=1 format=3]', '',
            '[node name="site_walk" type="Node3D"]', '']

    def node(name, parent, p):
        body.extend([f'[node name="{name}" type="Node3D" parent="{parent}"]',
                     'transform = Transform3D(1, 0, 0, 0, 1, 0, 0, 0, 1, '
                     f'{p[0]:g}, {p[1]:g}, {p[2]:g})', ''])

    node("LT_PlayerSpawn", ".", points["player"])
    body.extend(['[node name="LT_EnemySpawnPoints" type="Node3D" parent="."]',
                 ''])
    for i, e in enumerate(points["enemies"]):
        node(f"Enemy_{i}", "LT_EnemySpawnPoints", e)
    node("LT_ObjectivePoint", ".", points.get(
        "objective", points["player"]))
    return "\n".join(body)


def reading(boxes) -> Reading:
    return Reading(tuple(boxes), ())


# ---------------------------------------------------------------------------
# the field itself
# ---------------------------------------------------------------------------
def test_a_flat_slab_is_standable_everywhere_on_it():
    field = heightfield([slab("g", 0.0, 0.0, 20.0, 20.0)], 0.0)
    assert field is not None
    assert field.standable(field.index(0.0, 0.0))
    assert field.standable(field.index(9.0, -9.0))
    assert field.index(40.0, 0.0) is None, "and nowhere off it"


def test_a_solid_standing_on_the_floor_is_not_standable():
    field = heightfield(divided_yard(), 0.0)
    assert not field.standable(field.index(0.0, 0.0)), (
        "the wall occupies the space the agent's own body would")
    assert field.standable(field.index(-15.0, 0.0))


def test_a_kerb_joins_and_a_wall_top_does_not():
    """The climb rule is the whole difference between a step and a storey."""
    boxes = [slab("street", -5.0, 0.0, 10.0, 10.0),
             slab("kerb", 5.0, 0.0, 10.0, 10.0, top=AGENT_CLIMB - 0.05),
             slab("roof", 20.0, 0.0, 10.0, 10.0, top=AGENT_CLIMB + 0.05)]
    field = heightfield(boxes, 0.0)
    reach = walk_distances(field, field.index(-5.0, 0.0))
    assert field.index(5.0, 0.0) in reach, "a kerb is a step up"
    assert field.index(20.0, 0.0) not in reach, "a ledge is not"


def test_distance_is_walked_not_flown():
    """Around the wall, not through it -- that is the point of the field."""
    boxes = [slab("yard", 0.0, 0.0, 40.0, 20.0),
             wall("partition", 0.0, -3.0, 1.0, 14.0)]   # gap at the south edge
    field = heightfield(boxes, 0.0)
    reach = walk_distances(field, field.index(-8.0, 0.0))
    walked = reach[field.index(8.0, 0.0)]
    assert walked > 16.0, (
        f"the straight line is 16 m; going around the wall is longer: {walked}")


def test_the_field_is_built_around_the_storey_the_mission_starts_on():
    """An upper floor is out of view, not underfoot.

    A single heightfield cannot describe a building's storeys. Taking the
    highest surface anywhere would put the whole field on the roof and call the
    ground floor unreachable, which is a lie in the loud direction.
    """
    boxes = [slab("ground", 0.0, 0.0, 20.0, 20.0),
             slab("second_floor", 0.0, 0.0, 20.0, 20.0, top=8.0)]
    field = heightfield(boxes, 0.0)
    assert field.floor[field.index(0.0, 0.0)] == 0.0


def test_a_big_site_is_coarsened_out_loud_rather_than_skipped():
    field = heightfield([slab("huge", 0.0, 0.0, 4000.0, 4000.0)], 0.0,
                        cell=CELL)
    assert field.coarsened, "the grid was widened"
    assert field.cell > CELL
    assert field.standable(field.index(0.0, 0.0)), "and it still answers"


def test_nothing_to_stand_on_is_no_field_rather_than_an_empty_one():
    assert heightfield([], 0.0) is None


# ---------------------------------------------------------------------------
# reading the hooks
# ---------------------------------------------------------------------------
def test_classify_separates_the_crew_the_enemies_and_the_route():
    player, enemies, destinations = classify({
        "LT_PlayerSpawn": (1.0, 0.0, 2.0),
        "LT_EnemySpawnPoints/Enemy_0": (3.0, 0.0, 4.0),
        "LT_ObjectivePoint": (5.0, 0.0, 6.0),
        "LT_PlayerRoutePoints/Route_0": (7.0, 0.0, 8.0),
        "LT_CoverTestPoints/Cover_0": (9.0, 0.0, 10.0),
    })
    assert player == (1.0, 0.0, 2.0)
    assert list(enemies) == ["Enemy_0"]
    assert sorted(destinations) == ["LT_ObjectivePoint", "Route_0"]
    assert "Cover_0" not in destinations, (
        "cover points are sampling positions, not somewhere a bot has to walk")


# ---------------------------------------------------------------------------
# the defect this module was written for
# ---------------------------------------------------------------------------
def test_an_enemy_sealed_behind_a_wall_refuses_the_map():
    text = scene_text({"player": (-15.0, 1.0, 0.0),
                       "enemies": [(15.0, 1.0, 0.0)],
                       "objective": (-15.0, 0.0, 0.0)})
    problems = check_spawn_placement_text(text, reading(divided_yard()))
    assert problems, "an enemy with no route to the crew is a blocker"
    assert "UNREACHABLE_SPAWN" in problems[0]
    assert "Enemy_0" in problems[0] and "sealed off" in problems[0]


def test_an_enemy_embedded_in_a_solid_is_named_as_such():
    text = scene_text({"player": (-15.0, 1.0, 0.0),
                       "enemies": [(0.0, 1.0, 0.0)],
                       "objective": (-15.0, 0.0, 0.0)})
    problems = check_spawn_placement_text(text, reading(divided_yard()))
    assert problems and "inside solid geometry" in problems[0], problems


def test_a_reachable_enemy_at_a_sensible_distance_says_nothing():
    text = scene_text({"player": (-15.0, 1.0, 0.0),
                       "enemies": [(15.0, 1.0, 0.0)],
                       "objective": (-15.0, 0.0, 0.0)})
    assert check_spawn_placement_text(
        text, reading([slab("yard", 0.0, 0.0, 40.0, 20.0)])) == []


def test_enemies_and_destinations_are_counted_separately():
    """One message that counts enemies and then lists route points reads as a
    miscount even when every word of it is true."""
    boxes = divided_yard()
    text = scene_text({"player": (-15.0, 1.0, 0.0),
                       "enemies": [(15.0, 1.0, 0.0)],
                       "objective": (15.0, 0.0, 0.0)})
    problems = check_spawn_placement_text(text, reading(boxes))
    assert len(problems) == 2, problems
    assert "1 of 1 enemy spawn(s)" in problems[0]
    assert "1 of 1 mission destination(s)" in problems[1]
    assert "TRAVERSAL" in problems[1], (
        "an unwalkable objective is a traversal failure, not a refused map")


def test_an_objective_on_a_counter_is_unreachable_rather_than_floored():
    """The real seed's objective sat on a 1.1 m surface with no ramp to it.

    `support_under` was perfectly happy: there was something underneath. It is
    the 0.5 m climb rule that decides whether the crew can ever get there.
    """
    boxes = [slab("street", 0.0, 0.0, 40.0, 20.0),
             slab("counter", 15.0, 0.0, 4.0, 4.0, top=1.1)]
    text = scene_text({"player": (-15.0, 1.0, 0.0),
                       "enemies": [(-10.0, 1.0, 0.0)],
                       "objective": (15.0, 1.1, 0.0)})
    problems = check_spawn_placement_text(text, reading(boxes))
    assert support_under((15.0, 1.1, 0.0), boxes) is not None, (
        "ground contact passes it")
    assert any("mission destination" in p for p in problems), problems


def test_a_spawn_hanging_in_the_air_is_reported_with_its_height():
    text = scene_text({"player": (-15.0, 1.0, 0.0),
                       "enemies": [(10.0, 1.0 + MAX_SPAWN_LIFT + 0.5, 0.0)],
                       "objective": (-15.0, 0.0, 0.0)})
    problems = advise_spawn_placement_text(
        text, reading([slab("yard", 0.0, 0.0, 40.0, 20.0)]))
    hanging = [p for p in problems if "hang" in p]
    assert hanging, problems
    assert "Enemy_0" in hanging[0]


def test_the_producers_one_metre_settling_lift_is_not_a_complaint():
    """Lot lifts its markers 1.0 m so a dropped capsule settles instead of
    clipping. That is deliberate and must stay silent, or the check cries on
    every scene the pipeline has ever produced."""
    text = scene_text({"player": (-15.0, 1.0, 0.0),
                       "enemies": [(10.0, 1.0, 0.0)],
                       "objective": (-15.0, 0.0, 0.0)})
    hanging = [p for p in advise_spawn_placement_text(
        text, reading([slab("yard", 0.0, 0.0, 40.0, 20.0)])) if "hang" in p]
    assert hanging == []


def test_an_enemy_in_the_crews_lap_is_instant_contact():
    text = scene_text({"player": (-15.0, 1.0, 0.0),
                       "enemies": [(-13.0, 1.0, 0.0)],
                       "objective": (-15.0, 0.0, 0.0)})
    problems = advise_spawn_placement_text(
        text, reading([slab("yard", 0.0, 0.0, 40.0, 20.0)]))
    assert any("INSTANT_CONTACT" in p for p in problems), problems


def test_an_unfair_opening_advises_and_never_refuses():
    """A firefight evaluator grades tactics; it does not condemn a build.

    The whole reason the two functions exist separately: this map is playable,
    Laser Tag will play it 25 times, and what it has to say afterwards is worth
    hearing without having stopped the level from being built (TDD 5.5).
    """
    text = scene_text({"player": (-15.0, 1.0, 0.0),
                       "enemies": [(-13.0, 1.0, 0.0)],
                       "objective": (-15.0, 0.0, 0.0)})
    read = reading([slab("yard", 0.0, 0.0, 40.0, 20.0)])
    assert check_spawn_placement_text(text, read) == []
    assert advise_spawn_placement_text(text, read) != []


def test_standoff_is_measured_around_the_wall_not_through_it():
    """Two metres away through a partition is not an ambush.

    The distance the crew has to walk is the distance that matters, and the
    partition makes it the length of the yard rather than the two metres a
    ruler laid on the plan would report.
    """
    boxes = [slab("yard", 0.0, 0.0, 400.0, 200.0),
             wall("partition", 0.0, -30.0, 1.0, 140.0)]
    # Both points sit on the sealed side of the partition, so the only way
    # across is the far end of the yard -- well past the opening range.
    text = scene_text({"player": (-1.0, 1.0, -50.0),
                       "enemies": [(1.0, 1.0, -50.0)],
                       "objective": (-1.0, 0.0, -50.0)})
    problems = advise_spawn_placement_text(text, reading(boxes))
    assert not any("INSTANT_CONTACT" in p for p in problems), problems


def test_the_standoff_is_sized_against_what_laser_tag_opens_fire_at():
    """The number was 8.0 m and it was chosen by eye.

    Laser Tag stamps `time_to_first_contact` on the first shot fired by either
    side, and the side that fires first is the crew: the bot's sight range is
    45 m against the enemy's 35 m. An enemy at 39 m cleared every check the
    pipeline had and opened the fight anyway.
    """
    from packages.validation import lasertag_contract
    assert MIN_ENGAGEMENT_STANDOFF == lasertag_contract.MEASURED.opening_range
    assert MIN_ENGAGEMENT_STANDOFF >= 45.0

    text = scene_text({"player": (-100.0, 1.0, 0.0),
                       "enemies": [(-61.0, 1.0, 0.0)],
                       "objective": (-100.0, 0.0, 0.0)})
    problems = advise_spawn_placement_text(
        text, reading([slab("yard", 0.0, 0.0, 400.0, 40.0)]))
    assert any("INSTANT_CONTACT" in p for p in problems), problems


# ---------------------------------------------------------------------------
# staying quiet where another check already speaks
# ---------------------------------------------------------------------------
def test_a_scene_with_no_hooks_is_not_this_modules_complaint():
    assert check_spawn_placement_text(
        '[node name="site_walk" type="Node3D"]',
        reading([slab("yard", 0.0, 0.0, 40.0, 20.0)])) == []


def test_a_scene_with_no_readable_collision_is_not_this_modules_complaint():
    """`check_ground_contact` owns that sentence. Saying it twice turns one
    defect into two bugs to chase."""
    text = scene_text({"player": (0.0, 1.0, 0.0), "enemies": [(10.0, 1.0, 0.0)]})
    assert check_spawn_placement_text(text, Reading((), ("shell.glb",))) == []


def test_a_spawn_over_a_hole_is_not_this_modules_complaint():
    text = scene_text({"player": (100.0, 1.0, 100.0),
                       "enemies": [(10.0, 1.0, 0.0)]})
    assert check_spawn_placement_text(
        text, reading([slab("yard", 0.0, 0.0, 40.0, 20.0)])) == []


def test_what_could_not_be_read_is_said_on_the_finding():
    text = scene_text({"player": (-15.0, 1.0, 0.0),
                       "enemies": [(15.0, 1.0, 0.0)],
                       "objective": (-15.0, 0.0, 0.0)})
    problems = check_spawn_placement_text(
        text, Reading(tuple(divided_yard()), ("shell.glb",)))
    assert "may be larger than this" in problems[0], problems
    assert "shell.glb" in problems[0]


def test_a_missing_scene_file_is_silent():
    assert check_spawn_placement(Path("/nonexistent/level.tscn")) == []


def test_the_objective_is_one_defect_even_though_lot_names_it_twice():
    """Lot builds its route as [spawn, objective, extraction], so Route_1 is
    the objective's own coordinate under a second name. Counting both turned
    one unreachable marker into "2 of 4 mission destinations" and made a single
    placement defect read as a map riddled with them."""
    _player, _enemies, destinations = classify({
        "LT_PlayerSpawn": (0.0, 0.0, 0.0),
        "LT_ObjectivePoint": (35.0, 0.9, 17.0),
        "LT_PlayerRoutePoints/Route_0": (0.0, 0.0, 0.0),
        "LT_PlayerRoutePoints/Route_1": (35.0, 0.9, 17.0),
        "LT_PlayerRoutePoints/Route_2": (117.0, 0.0, 16.0),
    })
    assert sorted(destinations) == [
        "LT_ObjectivePoint", "Route_0", "Route_2"]


def test_two_genuinely_distinct_waypoints_both_survive():
    _player, _enemies, destinations = classify({
        "LT_PlayerRoutePoints/Route_0": (0.0, 0.0, 0.0),
        "LT_PlayerRoutePoints/Route_1": (10.0, 0.0, 0.0),
    })
    assert len(destinations) == 2
