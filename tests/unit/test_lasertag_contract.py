"""The evaluator's numbers, read from the evaluator rather than remembered.

Every constant in this repo that describes Laser Tag is a copy, and a copy is
a claim that goes stale silently. The bug that produced this module is exactly
that: Lot held `SIGHT_RANGE = 35.0`, correctly sourced from the scenario
resource, and the fight actually opens at 45 m because the crew's bot sees ten
metres further than the enemy and nothing in the scenario resource says so.

So these tests pin two things. That the parsers read GDScript and `.tres` the
way those files are actually written -- annotations with arguments, typed
exports, trailing comments, `[resource]` sections that are not the whole file.
And that the contract's conclusions are drawn from the wiring rather than from
the field names: a scenario field only sets something if the harness assigns it
across, and the whole defect is a field that looks like a knob and is not one.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from packages.validation import lasertag_contract as lt  # noqa: E402


# ---------------------------------------------------------------------------
# fixtures: trimmed but structurally faithful copies of the real files
# ---------------------------------------------------------------------------
SCENARIO = """[gd_resource type="Resource" script_class="LT_TestScenario" load_steps=2 format=3]

[ext_resource type="Script" path="res://addons/laser_tag_tool/resources/LT_TestScenario.gd" id="1"]

[resource]
script = ExtResource("1")
enemy_count = 6
enemy_sight_range = 35.0
enemy_laser_range = 35.0
enemy_fire_cooldown = 1.1
enemy_reaction_delay_min = 0.25
enemy_reaction_delay_max = 0.9
player_laser_range = 60.0
run_time_limit = 180.0
"""

BOT = """extends Node
class_name LT_BotPlayerController

@export var body: NodePath
@export var sight_range: float = 45.0
@export var fire_cooldown: float = 0.7
@export_range(0.0, 15.0) var aim_error_degrees: float = 2.5
@export var use_navigation: bool = true  # nav agent when the map has a mesh
"""

BRAIN = """extends Node
class_name LT_EnemyBrain

@export var sight_range: float = 35.0
@export var preferred_distance: float = 14.0
"""

HARNESS = """func _configure_enemy(enemy: Node, scenario: LT_TestScenario) -> void:
	var brain := enemy.get_node("Brain")
	brain.fire_cooldown = scenario.enemy_fire_cooldown
	brain.sight_range = scenario.enemy_sight_range

func _configure_player(player: Node, scenario: LT_TestScenario) -> void:
	var shooter := player.get_node("Shooter")
	shooter.laser_range = scenario.player_laser_range
	bot_controller.use_navigation = true
"""


def engagement(**over) -> lt.Engagement:
    texts = {"scenario_text": SCENARIO, "bot_text": BOT,
             "brain_text": BRAIN, "harness_text": HARNESS}
    texts.update(over)
    return lt.read_engagement(**texts)


# ---------------------------------------------------------------------------
# parsing
# ---------------------------------------------------------------------------
def test_only_the_resource_section_counts_as_scenario_configuration():
    """A `.tres` header carries assignments that are not the scenario's business.

    `load_steps=2` and the `[ext_resource]` block both parse as `key = value`,
    and folding them in gives a lookup that answers confidently with the wrong
    file's fields.
    """
    fields = lt.parse_resource(SCENARIO)
    assert fields["enemy_sight_range"] == 35.0
    assert fields["enemy_count"] == 6
    assert "load_steps" not in fields
    assert "path" not in fields


def test_a_tres_with_no_resource_section_reads_as_nothing_rather_than_guessing():
    assert lt.parse_resource("[gd_scene format=3]\nfoo = 1\n") == {}


def test_exports_are_read_through_annotations_types_and_trailing_comments():
    """The four shapes the real scripts use, all in one file.

    `@export_range(0.0, 15.0) var x: float = 2.5` is the one that breaks a naive
    pattern, and it is in the shipped bot controller.
    """
    exports = lt.parse_exports(BOT)
    assert exports["sight_range"] == 45.0
    assert exports["aim_error_degrees"] == 2.5
    assert exports["use_navigation"] is True
    # `@export var body: NodePath` declares no default, so it has none to
    # report. An export with no initialiser is a value the scene file supplies,
    # and inventing an empty one here would let a lookup answer for it.
    assert "body" not in exports


def test_wiring_names_the_scenario_field_each_property_is_assigned_from():
    wiring = lt.scenario_wiring(HARNESS)
    assert wiring["brain.sight_range"] == "enemy_sight_range"
    assert wiring["shooter.laser_range"] == "player_laser_range"
    # Assigned, but not from the scenario -- so not configurable.
    assert "bot_controller.use_navigation" not in wiring


# ---------------------------------------------------------------------------
# the contract
# ---------------------------------------------------------------------------
def test_the_opening_range_is_the_crews_sight_not_the_scenarios_number():
    """The finding this module was written for.

    Both numbers are true. The scenario says 35 and the site has to be built
    against 45, because first contact belongs to whoever shoots first and the
    bot's `_fire_timer` starts at zero.
    """
    eng = engagement()
    assert eng.enemy_sight == 35.0
    assert eng.player_sight == 45.0
    assert eng.opening_range == 45.0
    assert eng.opener == "the crew"


def test_a_scenario_field_the_harness_never_assigns_is_not_configuration():
    """Adding `player_sight_range` to the resource changes nothing on its own.

    This is the trap in the shape the next person will hit it: the obvious fix
    for "the crew sees too far" is a scenario field, and a scenario field with
    no wiring behind it is a value that reads back correctly and moves nothing.
    """
    scenario = SCENARIO + "player_sight_range = 20.0\n"
    eng = engagement(scenario_text=scenario)
    assert eng.player_sight_is_configurable is False
    assert eng.player_sight == 45.0, "the bot's export still decides the fight"


def test_wiring_the_bot_makes_the_scenario_field_the_real_number():
    harness = HARNESS + "\tbot_controller.sight_range = scenario.player_sight_range\n"
    eng = engagement(scenario_text=SCENARIO + "player_sight_range = 20.0\n",
                     harness_text=harness)
    assert eng.player_sight_is_configurable is True
    assert eng.player_sight == 20.0
    assert eng.opening_range == 35.0
    assert eng.opener == "the enemy"


def test_an_unwired_enemy_sight_falls_back_to_the_brains_own_default():
    """Symmetry check: the enemy is only scenario-driven because a line says so.

    Delete that line and the scenario's 35.0 becomes as decorative as the crew's
    would be, and the contract has to report the brain's export instead.
    """
    harness = HARNESS.replace(
        "\tbrain.sight_range = scenario.enemy_sight_range\n", "")
    eng = engagement(scenario_text=SCENARIO.replace(
        "enemy_sight_range = 35.0", "enemy_sight_range = 90.0"),
        harness_text=harness)
    assert eng.enemy_sight == 35.0, "the brain's export, not the resource's 90"


def test_each_field_falls_back_on_its_own_rather_than_the_whole_contract():
    """Half the truth beats a snapshot presented as the truth.

    A tool that can read the scenario but not the scripts should still get the
    scenario's real numbers; only the fields it could not reach come from
    `MEASURED`.
    """
    eng = lt.read_engagement(scenario_text=SCENARIO.replace(
        "enemy_laser_range = 35.0", "enemy_laser_range = 50.0"))
    assert eng.enemy_laser == 50.0
    assert eng.player_sight == lt.MEASURED.player_sight
    assert "scenario" in eng.source


def test_the_source_says_whether_anything_was_actually_read():
    assert lt.read_engagement().source == lt.MEASURED.source
    assert "read from" in engagement().source


def test_reading_a_checkout_that_is_not_there_degrades_instead_of_raising(tmp_path):
    """A moved script is not a reason for a pre-flight to refuse to run."""
    eng = lt.read_engagement_from(tmp_path / "no-such-checkout")
    assert eng.opening_range == lt.MEASURED.opening_range
    assert lt.read_engagement_from(None) is lt.MEASURED


def test_reading_a_real_checkout_layout_finds_the_files(tmp_path):
    for key, rel in lt._FILES.items():
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text({"scenario_text": SCENARIO, "bot_text": BOT,
                         "brain_text": BRAIN, "harness_text": HARNESS}[key],
                        encoding="utf-8")
    eng = lt.read_engagement_from(tmp_path)
    assert eng.opening_range == 45.0
    assert eng.player_sight_is_configurable is False


# ---------------------------------------------------------------------------
# drift
# ---------------------------------------------------------------------------
def test_the_producers_thirty_five_metres_is_reported_against_the_real_forty_five():
    """The exact miss that shipped, worded so the consequence is in the finding.

    "35 != 45" is a fact nobody acts on. The finding has to say that the enemies
    between the two numbers were placed as fair, will be shot at first, and cost
    the run its route completion -- because that is the part that reads as a
    placement bug rather than a level review.
    """
    problems = lt.check_drift(35.0, engagement(), who="Lot")
    assert len(problems) == 1
    text = problems[0]
    assert "35 m" in text and "45 m" in text
    assert "the crew first" in text
    assert "route" in text


def test_agreement_within_a_rounding_hair_is_not_a_finding():
    assert lt.check_drift(45.0, engagement()) == []
    assert lt.check_drift(45.02, engagement()) == []


def test_drift_in_the_safe_direction_is_still_said_out_loud():
    """A stricter producer is not a bug, and silence about it is.

    If the numbers disagree, the reader needs to know which one moved -- the
    evaluator may have been retuned, in which case the producer's extra caution
    is the stale half.
    """
    problems = lt.check_drift(80.0, engagement())
    assert len(problems) == 1
    assert "stricter" in problems[0]
    assert "site area" in problems[0]


def test_the_unsettable_crew_sight_is_a_finding_against_laser_tag_itself():
    problems = lt.check_configurability(engagement())
    assert len(problems) == 1
    assert "not settable from the scenario resource" in problems[0]
    assert "enemy_sight_range" in problems[0]


def test_it_is_not_a_finding_once_the_crew_sees_no_further_than_the_enemy():
    """Still unsettable, no longer misleading.

    While the enemy's number is the binding one, `enemy_sight_range` does set
    the engagement range, and a finding that fires anyway trains its reader to
    skip it.
    """
    eng = engagement(bot_text=BOT.replace("sight_range: float = 45.0",
                                          "sight_range: float = 30.0"))
    assert eng.opening_range == 35.0
    assert lt.check_configurability(eng) == []
