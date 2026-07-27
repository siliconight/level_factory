"""The numbers Laser Tag will actually play the map with (TDD 24.3, 29.4).

Lot places enemies so the crew's opening second is a fair one, and it sizes that
placement against ``enemy_sight_range = 35.0`` -- the field in
``default_laser_tag_scenario.tres``, the scenario Level Factory runs. The
reasoning is sound and the number is wrong, and the way it is wrong is worth
writing down because nothing in either repo could have caught it.

``time_to_first_contact`` is not stamped when an enemy acquires the crew. It is
stamped by ``LT_MetricsCollector.record_shot`` on the first shot fired in the
run *by either side*::

    if current["time_to_first_contact"] < 0.0:
        current["time_to_first_contact"] = _now()

and the side that fires first is the crew. ``LT_BotPlayerController`` carries
``@export var sight_range: float = 45.0``, ten metres further than the enemy it
is hunting, and nothing overrides it: ``LT_MapEvalHarness._configure_enemy``
assigns ``brain.sight_range = scenario.enemy_sight_range``, and the matching
line for the bot does not exist -- the scenario resource has no player sight
field at all. The bot's ``_fire_timer`` starts at zero, so the frame it can see
an enemy is the frame it shoots. An enemy 39 m from the crew spawn is outside
every number Lot was checking and inside the only one that decides the clock.

The second half is worse than a mis-stamped clock. ``_physics_process`` reads::

    var enemy := _find_visible_enemy()
    if enemy != null:
        _stop_horizontal()
        ...
    else:
        _advance_route(delta)

The route only advances in the ``else``. A crew that can see an enemy does not
walk -- not slower, not at all -- and ``LT_EnemyBrain._find_target`` has no
range gate whatsoever, so every enemy on the site seeks the crew from wherever
it starts and the sightline never clears. One enemy visible from the player
spawn is therefore not a pacing complaint. It is 0% route completion, by
construction, on every run. That is the whole of ``LT_MAP_TRAVERSAL`` at 0%
sitting next to ``LT_MAP_INSTANT_CONTACT`` at 0.1 s, and it is why the rule
below is a gate and not a nudge.

So this module is the one place that answers "what will the evaluator do",
by reading the evaluator's own files rather than by carrying a copy of its
constants. Everything here is pure text in, values and findings out: the same
functions back the adapter's pre-flight, tell Lot when its stated assumption has
drifted, and run in the tests. A tool that cannot reach the Laser Tag checkout
falls back to `MEASURED`, which is what these files said when they were last
read -- named as a measurement so it reads as a snapshot rather than a truth.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

#: ``[resource]``-section assignments in a Godot ``.tres``.
_TRES_FIELD = re.compile(r'^(\w+)\s*=\s*(.+?)\s*$', re.M)

#: ``@export var name: Type = literal``. The annotation may carry its own
#: arguments (``@export_range(0, 10) var ...``), and the type hint is optional.
_EXPORT = re.compile(
    r'^@export(?:_\w+)?(?:\([^)]*\))?\s+var\s+(\w+)\s*'
    r'(?::\s*[\w.\[\]]+\s*)?=\s*(.+?)\s*$', re.M)

#: ``brain.sight_range = scenario.enemy_sight_range`` and friends -- an
#: assignment in the harness that overrides a script default at setup.
_WIRED = re.compile(r'^\s*(\w+)\.(\w+)\s*=\s*scenario\.(\w+)\s*$', re.M)


# ---------------------------------------------------------------------------
# reading the evaluator's files
# ---------------------------------------------------------------------------
def _value(raw: str):
    """A GDScript literal as a Python value, or the raw string when it is not one."""
    raw = raw.split("#", 1)[0].strip()
    if raw in ("true", "false"):
        return raw == "true"
    if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in "\"'":
        return raw[1:-1]
    try:
        return int(raw)
    except ValueError:
        pass
    try:
        return float(raw)
    except ValueError:
        return raw


def parse_resource(text: str) -> dict:
    """Fields of a Godot ``.tres``'s ``[resource]`` section.

    Only that section: a ``load_steps`` in the header or a property on an
    ``[ext_resource]`` is not scenario configuration, and folding them in makes
    a lookup silently answer with the wrong file's business.
    """
    start = text.find("\n[resource]")
    if start == -1:
        return {}
    body = text[start + len("\n[resource]"):]
    nxt = re.search(r'^\[', body, re.M)
    if nxt:
        body = body[:nxt.start()]
    return {key: _value(raw) for key, raw in _TRES_FIELD.findall(body)}


def parse_exports(text: str) -> dict:
    """``@export`` defaults declared by a GDScript file.

    These are the values a node runs with unless something assigns over them,
    which is the distinction this whole module exists to make.
    """
    return {name: _value(raw) for name, raw in _EXPORT.findall(text)}


def scenario_wiring(harness_text: str) -> dict:
    """``{"<node>.<property>": "<scenario field>"}`` the harness assigns at setup.

    A property that appears here is configurable from the scenario resource. One
    that does not is a script default wearing a scenario's clothes: changing the
    resource moves nothing, and the person who changed it has no way to find
    that out from the resource.
    """
    return {f"{obj}.{prop}": field
            for obj, prop, field in _WIRED.findall(harness_text)}


# ---------------------------------------------------------------------------
# the contract
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Engagement:
    """What each side can do at the moment the run starts.

    ``opening_range`` is the one number a map has to be built against, and it is
    a maximum rather than the enemy's figure because first contact belongs to
    whoever shoots first and that is not always the enemy.
    """

    enemy_sight: float
    enemy_laser: float
    enemy_reaction_min: float
    player_sight: float
    player_laser: float
    player_sight_is_configurable: bool
    source: str

    @property
    def opening_range(self) -> float:
        return max(self.enemy_sight, self.player_sight)

    @property
    def opener(self) -> str:
        """Which side reaches the other first at ``opening_range``."""
        if self.player_sight > self.enemy_sight:
            return "the crew"
        if self.enemy_sight > self.player_sight:
            return "the enemy"
        return "either side"

    def as_dict(self) -> dict:
        return {
            "enemy_sight": self.enemy_sight,
            "enemy_laser": self.enemy_laser,
            "enemy_reaction_min": self.enemy_reaction_min,
            "player_sight": self.player_sight,
            "player_laser": self.player_laser,
            "opening_range": self.opening_range,
            "opener": self.opener,
            "player_sight_is_configurable": self.player_sight_is_configurable,
            "source": self.source,
        }


#: What the Laser Tag checkout said when it was last read, for a caller that
#: cannot reach it. A snapshot, not a definition -- `check_drift` exists so a
#: run against the real files says so when these have gone stale.
MEASURED = Engagement(
    enemy_sight=35.0,
    enemy_laser=35.0,
    enemy_reaction_min=0.25,
    player_sight=45.0,
    player_laser=60.0,
    player_sight_is_configurable=False,
    source="measured from the Laser Tag checkout; not read this run",
)


def read_engagement(scenario_text: str = "", bot_text: str = "",
                    brain_text: str = "", harness_text: str = "") -> Engagement:
    """Build the contract from whatever of the evaluator's files can be read.

    Each field falls back to `MEASURED` independently rather than the whole
    contract falling back together: a readable scenario and an unreadable bot
    script should still give the scenario's real numbers, and a caller that
    got half the truth is better served than one silently handed a snapshot.
    """
    scenario = parse_resource(scenario_text)
    bot = parse_exports(bot_text)
    brain = parse_exports(brain_text)
    wiring = scenario_wiring(harness_text)

    def num(value, fallback: float) -> float:
        return float(value) if isinstance(value, (int, float)) else fallback

    # The enemy's sight is the scenario's when the harness wires it across, and
    # the brain's own default when it does not -- reading the scenario field
    # unconditionally would report a number the brain never receives.
    enemy_sight_wired = "enemy_sight_range" in wiring.values() if wiring else True
    enemy_sight = num(scenario.get("enemy_sight_range"), MEASURED.enemy_sight) \
        if enemy_sight_wired else num(brain.get("sight_range"), MEASURED.enemy_sight)

    player_wired = any(field.startswith("player_sight")
                       for field in wiring.values())
    player_sight = num(scenario.get("player_sight_range"), 0.0) if player_wired \
        else num(bot.get("sight_range"), MEASURED.player_sight)

    read = [name for name, text in (("scenario", scenario_text),
                                    ("bot controller", bot_text),
                                    ("enemy brain", brain_text),
                                    ("harness", harness_text)) if text]
    return Engagement(
        enemy_sight=enemy_sight,
        enemy_laser=num(scenario.get("enemy_laser_range"), MEASURED.enemy_laser),
        enemy_reaction_min=num(scenario.get("enemy_reaction_delay_min"),
                               MEASURED.enemy_reaction_min),
        player_sight=player_sight,
        player_laser=num(scenario.get("player_laser_range"), MEASURED.player_laser),
        player_sight_is_configurable=player_wired,
        source=("read from " + ", ".join(read)) if read else MEASURED.source,
    )


#: Where each file lives under a Laser Tag checkout.
_FILES = {
    "scenario_text": "addons/laser_tag_tool/resources/default_laser_tag_scenario.tres",
    "bot_text": "addons/laser_tag_tool/scripts/player/LT_BotPlayerController.gd",
    "brain_text": "addons/laser_tag_tool/scripts/enemy/LT_EnemyBrain.gd",
    "harness_text": "addons/laser_tag_tool/scripts/core/LT_MapEvalHarness.gd",
}


def read_engagement_from(repository) -> Engagement:
    """`read_engagement` against a Laser Tag checkout on disk.

    A missing file is not an error: it becomes an unread field and the fallback
    covers it, which is the difference between a pre-flight that degrades and
    one that refuses to run because a tool moved a script.
    """
    if not repository:
        return MEASURED
    root = Path(repository)
    texts = {}
    for key, rel in _FILES.items():
        path = root / rel
        try:
            texts[key] = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            texts[key] = ""
    return read_engagement(**texts)


# ---------------------------------------------------------------------------
# what a tool that carries a copy of the number needs told
# ---------------------------------------------------------------------------
def check_drift(assumed: float, engagement: Engagement,
                *, who: str = "the producer") -> list[str]:
    """Findings for a tool that sized its placement against ``assumed`` metres.

    Lot cannot import this module -- it is a separate tool with its own
    dependencies -- so it carries `site_spawns.OPENING_RANGE` and states where
    the number came from. This is the check that the statement is still true,
    and it runs on the side that can see both repositories at once. Drift in the
    safe direction is still reported: a producer holding enemies further out
    than the evaluator requires is spending site area on nothing, and a reader
    deserves to know which of the two numbers moved.
    """
    problems: list[str] = []
    required = engagement.opening_range
    if abs(assumed - required) < 0.05:
        return problems
    if assumed < required:
        problems.append(
            f"{who} places enemies against a {assumed:g} m opening range, but "
            f"Laser Tag opens fire at {required:g} m ({engagement.opener} first: "
            f"enemy sight {engagement.enemy_sight:g} m, crew sight "
            f"{engagement.player_sight:g} m) — every enemy between {assumed:g} "
            f"and {required:g} m of the crew spawn was placed as fair and will "
            f"be shot at before the crew has moved, which stamps "
            f"time_to_first_contact at zero and stops the bot walking its route "
            f"({engagement.source})")
    else:
        problems.append(
            f"{who} places enemies against a {assumed:g} m opening range and "
            f"Laser Tag opens fire at {required:g} m ({engagement.source}) — the "
            f"placement is stricter than the evaluator requires, which costs "
            f"site area rather than runs, but the two numbers no longer agree")
    return problems


def check_configurability(engagement: Engagement) -> list[str]:
    """The crew's sight range is a script default that no scenario can move.

    ``LT_MapEvalHarness`` wires ``brain.sight_range`` from the scenario and has
    no matching line for the bot, so ``enemy_sight_range`` reads like the knob
    that sets engagement range and is only half of it. Anyone tuning a scenario
    to open the fight further out moves the enemy's number, watches first
    contact stay where it was, and has nowhere in the resource to look.
    """
    if engagement.player_sight_is_configurable:
        return []
    if engagement.player_sight <= engagement.enemy_sight:
        # Still worth stating, but it decides nothing while the crew sees no
        # further than the enemy does: the scenario's number is the binding one.
        return []
    return [
        f"the crew's sight range ({engagement.player_sight:g} m) is an @export "
        f"default on LT_BotPlayerController that the harness never assigns, so "
        f"it is not settable from the scenario resource — and it is larger than "
        f"the enemy_sight_range ({engagement.enemy_sight:g} m) the resource does "
        f"expose, which means the scenario field that looks like it sets "
        f"engagement range does not set it"
    ]
