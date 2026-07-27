"""A firefight evaluator grades a map. It does not get to refuse one.

Every finding in this file describes a level that loads, bakes, plays and comes
back with a mediocre score. The pipeline's first instinct was to stop the build
on each of them, which trades a level someone can put cover into for no level at
all -- and the finding that mattered most, "these two markers can shoot the
length of ninety metres of empty street", is not a complaint about the map at
all. It is a coordinate. Somebody just has to be handed it.

So these tests pin three things: what the advisories say, that they carry the
instruction and not only the diagnosis, and that nothing on this path can ever
be the reason a level does not exist.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from packages.validation import lasertag_contract, tactical  # noqa: E402
from packages.validation.ground_contact import Box, Reading  # noqa: E402
from packages.validation.model import BLOCKER, severity_rank  # noqa: E402
from packages.validation.spawn_placement import (  # noqa: E402
    CODE_FLOATING, CODE_STANDOFF)


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------
def slab(name: str, x: float, z: float, sx: float, sz: float,
         top: float = 0.0) -> Box:
    return Box(name, (x, top - 0.25, z), (sx, 0.5, sz))


def wall(name: str, x: float, z: float, sx: float, sz: float,
         height: float = 6.0) -> Box:
    return Box(name, (x, height / 2.0, z), (sx, height, sz))


def scene_text(player, enemies, objective=None) -> str:
    body = ['[gd_scene load_steps=1 format=3]', '',
            '[node name="site_walk" type="Node3D"]', '']

    def node(name, parent, p):
        body.extend([f'[node name="{name}" type="Node3D" parent="{parent}"]',
                     'transform = Transform3D(1, 0, 0, 0, 1, 0, 0, 0, 1, '
                     f'{p[0]:g}, {p[1]:g}, {p[2]:g})', ''])

    node("LT_PlayerSpawn", ".", player)
    body.extend(['[node name="LT_EnemySpawnPoints" type="Node3D" parent="."]',
                 ''])
    for i, e in enumerate(enemies):
        node(f"Enemy_{i}", "LT_EnemySpawnPoints", e)
    node("LT_ObjectivePoint", ".", objective or player)
    return "\n".join(body)


def reading(boxes) -> Reading:
    return Reading(tuple(boxes), ())


#: 240 x 60 m of open street, nothing on it. The crew at one end, one enemy
#: 92 m away at the other: too far to be an ambush, close enough that Laser Tag
#: opens fire on the first frame, and with nothing whatsoever in between.
EMPTY_STREET = [slab("street", 0.0, 0.0, 240.0, 60.0)]


def empty_street_scene() -> str:
    return scene_text((-46.0, 1.0, 0.0), [(46.0, 1.0, 0.0)])


def engagement(**over) -> lasertag_contract.Engagement:
    base = dict(enemy_sight=35.0, enemy_laser=35.0, enemy_reaction_min=0.25,
                player_sight=45.0, player_laser=60.0,
                player_sight_is_configurable=False, source="a test")
    base.update(over)
    return lasertag_contract.Engagement(**base)


def codes(findings) -> list[str]:
    return [f["code"] for f in findings]


# ---------------------------------------------------------------------------
# the sightline is the finding worth having
# ---------------------------------------------------------------------------
def test_an_open_street_comes_back_as_a_place_to_put_something():
    """The whole reason this path exists rather than a refusal.

    "The map is too open" needs a person to translate it before anyone can act.
    A coordinate does not.
    """
    findings = tactical.scene_findings(empty_street_scene(),
                                       reading(EMPTY_STREET),
                                       opening_range=45.0)
    line = [f for f in findings if f["code"] == tactical.CODE_SIGHTLINE]
    assert len(line) == 1, codes(findings)
    assert "92.0 m of open ground" in line[0]["message"]
    assert line[0]["suggested_fix"].startswith("cover near ("), line[0]
    assert "would break it" in line[0]["suggested_fix"]


def test_one_street_is_one_finding_even_under_two_names():
    """An objective standing on the crew spawn used to double every sightline.

    Same endpoints, same length, same cover proposal, reported twice -- which
    reads as a site twice as open as it is.
    """
    text = scene_text((-46.0, 1.0, 0.0), [(46.0, 1.0, 0.0)],
                      objective=(-46.0, 1.0, 0.0))
    findings = tactical.scene_findings(text, reading(EMPTY_STREET),
                                       opening_range=45.0)
    lines = [f for f in findings if f["code"] == tactical.CODE_SIGHTLINE]
    assert len(lines) == 1, [f["message"] for f in lines]
    assert "LT_PlayerSpawn" in lines[0]["message"], (
        "and the spawn is the name worth keeping: 'LT_ObjectivePoint sees "
        "Enemy_0' sends the reader looking at the objective")


def test_a_street_with_a_building_across_it_says_nothing():
    """Silence is the correct output for a site that already solved this."""
    blocked = EMPTY_STREET + [wall("block", 0.0, 0.0, 30.0, 30.0)]
    findings = tactical.scene_findings(empty_street_scene(), reading(blocked),
                                       opening_range=45.0)
    assert tactical.CODE_SIGHTLINE not in codes(findings)


def test_the_range_is_the_callers_and_not_this_modules():
    """A caller that read the real scenario reports against it.

    92 m is open ground under any engagement contract; whether it is *reportable*
    open ground depends on the range somebody opens fire at, and that number
    lives in the Laser Tag checkout rather than in here.
    """
    assert tactical.CODE_SIGHTLINE in codes(
        tactical.scene_findings(empty_street_scene(), reading(EMPTY_STREET),
                                opening_range=45.0))
    assert tactical.CODE_SIGHTLINE not in codes(
        tactical.scene_findings(empty_street_scene(), reading(EMPTY_STREET),
                                opening_range=120.0))


def test_a_scene_with_no_crew_spawn_draws_no_sightlines():
    """Missing hooks belong to `check_scene_hooks`, said once."""
    text = '\n'.join(['[gd_scene load_steps=1 format=3]', '',
                      '[node name="site_walk" type="Node3D"]', ''])
    assert tactical.scene_findings(text, reading(EMPTY_STREET),
                                   opening_range=45.0) == []


# ---------------------------------------------------------------------------
# the placement advisories come through with their own codes
# ---------------------------------------------------------------------------
def test_an_enemy_in_the_crews_lap_is_filed_as_a_standoff():
    text = scene_text((-4.0, 1.0, 0.0), [(4.0, 1.0, 0.0)])
    findings = tactical.scene_findings(text, reading(EMPTY_STREET),
                                       opening_range=45.0)
    assert CODE_STANDOFF in codes(findings)


def test_a_marker_hanging_over_its_floor_is_filed_separately():
    """Two defects, two codes, fixed in two different places.

    A caller that had to tell these apart by matching on the prose would be
    coupled to a sentence, which lasts exactly until somebody improves it.
    """
    text = scene_text((-46.0, 1.0, 0.0), [(46.0, 4.0, 0.0)])
    findings = tactical.scene_findings(text, reading(EMPTY_STREET),
                                       opening_range=45.0)
    assert CODE_FLOATING in codes(findings)
    assert CODE_STANDOFF not in codes(findings), (
        "92 m apart is not an ambush; only the height is wrong here")


# ---------------------------------------------------------------------------
# the two checkouts, checked against each other
# ---------------------------------------------------------------------------
def test_the_producers_stated_range_is_read_from_its_source(tmp_path):
    (tmp_path / "site_spawns.py").write_text(
        "MIN_STANDOFF = 8.0\nOPENING_RANGE = 45.0\n", encoding="utf-8")
    assert tactical.lot_opening_range(tmp_path) == 45.0


def test_no_checkout_is_not_a_finding(tmp_path):
    """Nothing to check is silence, not an accusation.

    A drift check against a remembered default would be checking this module's
    memory rather than the pipeline, and it would fire on every run of a
    workspace that has no Lot configured.
    """
    assert tactical.lot_opening_range(None) is None
    assert tactical.lot_opening_range(tmp_path) is None
    assert tactical.CODE_DRIFT not in codes(
        tactical.engagement_findings(engagement(), None))


def test_drift_is_reported_when_the_producer_falls_behind():
    """The 35 m that wiped the crew.

    Lot sized its placement against `enemy_sight_range`, which is the number in
    the scenario resource and not the number that decides who shoots first.
    """
    findings = tactical.engagement_findings(engagement(), 35.0)
    drift = [f for f in findings if f["code"] == tactical.CODE_DRIFT]
    assert len(drift) == 1
    assert "45 m" in drift[0]["message"] and "Lot" in drift[0]["message"]
    assert "OPENING_RANGE to 45" in drift[0]["suggested_fix"]


def test_agreement_is_silent():
    assert tactical.CODE_DRIFT not in codes(
        tactical.engagement_findings(engagement(), 45.0))


def test_the_knob_that_looks_like_the_engagement_range_is_reported():
    """`enemy_sight_range` is half of it, and the resource says nothing.

    Anyone tuning the scenario to open the fight further out moves the enemy's
    number, watches first contact stay where it was, and has nowhere in the
    resource to look.
    """
    findings = tactical.engagement_findings(engagement(), 45.0)
    assert tactical.CODE_NOT_CONFIGURABLE in codes(findings)
    assert tactical.CODE_NOT_CONFIGURABLE not in codes(
        tactical.engagement_findings(
            engagement(player_sight_is_configurable=True), 45.0))


# ---------------------------------------------------------------------------
# and none of it blocks
# ---------------------------------------------------------------------------
def test_nothing_this_module_produces_is_a_blocker():
    """The rule the whole module exists to keep.

    Every finding here describes a level that Laser Tag will load, bake, play
    and score. Blocking on one stops the level existing long enough to be
    improved.
    """
    text = scene_text((-4.0, 1.0, 0.0), [(4.0, 4.0, 0.0), (46.0, 1.0, 0.0)])
    findings = (tactical.scene_findings(text, reading(EMPTY_STREET),
                                        opening_range=45.0)
                + tactical.engagement_findings(engagement(), 35.0))
    assert len(findings) >= 4, codes(findings)
    for finding in findings:
        assert finding["blocking"] is False, finding
        assert severity_rank(finding["severity"]) > severity_rank(BLOCKER), finding


def test_a_scene_that_is_not_there_yet_still_checks_the_contract(tmp_path):
    """The pre-flight owns "there is no scene"; saying it twice reads as two bugs."""
    findings = tactical.advise_scene(tmp_path / "absent.tscn",
                                     engagement=engagement())
    assert codes(findings) == [tactical.CODE_NOT_CONFIGURABLE]
    assert tactical.advise_scene(None, engagement=engagement()) == findings


def test_the_whole_pass_runs_off_one_scene_on_disk(tmp_path):
    (tmp_path / "level.tscn").write_text(empty_street_scene(), encoding="utf-8")
    (tmp_path / "site_spawns.py").write_text("OPENING_RANGE = 35.0\n",
                                             encoding="utf-8")
    # No collision in the .tscn itself, so the sightline half stays quiet and
    # the contract half does not: they read different things and fail apart.
    findings = tactical.advise_scene(tmp_path / "level.tscn",
                                     engagement=engagement(),
                                     lot_repository=tmp_path)
    assert tactical.CODE_DRIFT in codes(findings)
