"""Read the body dimensions out of Deli Counter's agent contract.

`deli_counter/agent_contract.json` calls itself "THE single source of truth for
character/agent dimensions and every clearance derived from them". Deli Counter
reads it -- `nav_gate`, `navigability`, `stairwell`, the headroom tests all
derive from it. Laser Tag does not, and until Laser Tag 0.11.0 its evaluation
pill was hardcoded in a `.tscn` at 0.40 m wide and 4.5 m/s against the
contract's 0.35 and 4.0 (roadmap 123).

0.11.0 moved those onto `LT_TestScenario`'s Body group, which made them
settable. This is the other half: LEVEL FACTORY IS THE SEAM. It already writes
`mission_scenario.tres` and stages it into the evaluation project beside the
map and the vendored addon, so it is the one place that touches both repos --
and it can copy the contract's numbers in without either tool importing the
other or reading the other's files at run time.

WHY THAT MATTERS TO SOMEBODY WHO IS NOT US. Nobody ships a floating capsule.
The pill exists to prove that a body of a STATED size fits the doors, stairs
and headroom this factory generates, and a studio using these tools has
characters of its own size. The promise of the contract is that they state that
size ONCE. Without this, stating it moves every Deli Counter clearance and
leaves the body that tests them at whatever Laser Tag was authored with.

THE ENEMY'S EYE CROSSES HERE TOO (0.231.0, the factory's roadmap 292). Until
then this seam wrote the player's body and nothing of the enemy's, so a studio
stating a 2.05 m character got a crew sighting from 1.85 m and enemies from
Laser Tag's stock 1.6 -- while Laser Tag has built every enemy's capsule, mesh
and agent from the crew's body in the scenario since its 0.26.0, and the
contract says its NPCs share the player's metrics until a distinct class ships.
The enemy's eye is `characters.npc_standard`'s, and the player's while that
block states none of its own.

A MISSING OR MALFORMED CONTRACT IS NOT AN ERROR, for the same reason
`lasertag_contract.read_engagement_from` treats a missing file as an unread
field: a pre-flight that refuses to run because a tool moved a file is worse
than one that degrades and says which numbers it used. The caller gets None and
falls back to the stock scenario, which carries the same values.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Mapping

#: `LT_TestScenario` field  <-  `characters.player` key.
#:
#: `radius_m` IS THE BODY'S, NOT THE BAKE'S, and that distinction is the whole
#: bug this closes. `nav_bake.agent_radius_m` is 0.40 and its own note says
#: "fattest navigating character + 0.05 safety" -- a bake parameter with a
#: margin folded in. The pill had been built at 0.40, so every door-width test
#: ran against a proxy 14% fatter than the character it stood for, and the
#: margin was being spent twice.
#: `aim_height_m` IS A BODY DIMENSION and was the last one not to cross this
#: seam (roadmap 131). Laser Tag aims every shot at a flat height above the
#: target's feet, and until the contract carried `chest_height_m` that height
#: followed nothing: a studio stating a 2.05 m character got an eye that moved
#: and an aim point that stayed at ours. It is not cosmetic -- LOS is granted
#: only when the ray cast AT that height hits the target body first, so an aim
#: point outside the target's capsule misses, nothing ever sees anything, and
#: the report fills with zeroes that read like a map problem.
_FIELDS = {
    "player_radius_m": "radius_m",
    "player_height_m": "height_m",
    "player_eye_height_m": "eye_height_m",
    "player_walk_speed_mps": "walk_speed_mps",
    # the step the player's controller lifts itself over (0.154.0, roadmap
    # 203): Laser Tag 0.24.0's crew steps up to it
    "player_max_step_up_m": "max_step_up_m",
    "aim_height_m": "chest_height_m",
}

#: `LT_TestScenario` field  <-  the enemy's body: `characters.npc_standard`'s
#: key, or `characters.player`'s where the NPC states none, because the
#: contract's NPCs share the player's metrics until a distinct class ships
#: (0.231.0, the factory's roadmap 292). The eye alone: Laser Tag builds an
#: enemy's capsule, mesh and agent from the crew's `player_radius_m` and
#: `player_height_m`, and has no enemy radius or height to write.
_NPC_FIELDS = {
    "enemy_eye_height_m": "eye_height_m",
}

CONTRACT_REL = "agent_contract.json"


def _metres(value) -> float | None:
    """A positive number of metres, or None: 0 is not a body, a string is not
    metres, and `True` is not 1 m."""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if float(value) > 0.0:
            return float(value)
    return None


def read_player_body(repository) -> dict | None:
    """`{scenario field: metres}` from a Deli Counter checkout, or None.

    Both sides' bodies, though the name is the player's: the crew's from
    `characters.player`, and the enemy's eye from `characters.npc_standard`
    over it (0.231.0) -- the player's being the body an NPC states nothing
    against.

    None means "nothing to say" -- no repository, no file, unreadable JSON, or
    no `characters.player` block -- and the caller keeps its own defaults.
    """
    if not repository:
        return None
    path = Path(repository) / CONTRACT_REL
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(raw, Mapping):
        return None
    player = (raw.get("characters") or {}).get("player")
    if not isinstance(player, Mapping):
        return None
    out: dict = {}
    for field, key in _FIELDS.items():
        value = _metres(player.get(key))
        if value is not None:
            out[field] = value
    npc = (raw.get("characters") or {}).get("npc_standard")
    npc = npc if isinstance(npc, Mapping) else {}
    for field, key in _NPC_FIELDS.items():
        # a value the NPC states is its own, nonsense included, which is
        # dropped rather than quietly replaced with the player's
        value = _metres(npc[key] if key in npc else player.get(key))
        if value is not None:
            out[field] = value
    return out or None


def body_drift(body: Mapping | None, stock: Mapping) -> list[str]:
    """Findings where the contract and the stock scenario disagree.

    Reported rather than silently resolved. The contract wins -- it says it is
    the source of truth -- but a stock value that has drifted from it is a
    number somebody typed twice, and the second copy is the one that rots.
    """
    if not body:
        return []
    out = []
    for field, value in body.items():
        if field not in stock:
            continue
        if abs(float(stock[field]) - value) > 1e-6:
            out.append(
                f"{field}: agent_contract.json says {value:g}, the stock "
                f"scenario says {stock[field]:g} -- using the contract")
    return out
