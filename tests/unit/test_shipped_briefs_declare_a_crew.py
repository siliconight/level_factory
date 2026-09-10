"""The shipped example briefs say how many people arrive (roadmap 129).

`_STOCK_SCENARIO` ships `enemy_count` 6 and `player_count` 1, and
`player_count` is wired from the brief's `crew_size`, which defaults to 1. Of
the 27 briefs on disk exactly one declared a crew size. So every evaluation
this project had ever run was ONE crew member against SIX guards, and no brief
asked for that -- it was two defaults disagreeing.

MEASURED ON THE MAP THAT PROVOKED IT, `warehouse_yard_001`, whose cold run
9004 wiped 75 runs out of 75:

    seed 9004   crew 1: 25 wipes, progress 0.00  ->  crew 4: 0 wipes, 0.33
    seed 9105   crew 1: 25 wipes, progress 0.00  ->  crew 4: 2 wipes, 0.65
    seed 9206   crew 1: 25 wipes, progress 0.00  ->  crew 4: 19 wipes, 0.47

WHY THE EXAMPLES AND NOT THE DEFAULT. Raising `crew_size`'s default would
change every historical comparison in one line -- the objection that kept
`advance_while_engaging` opt-in. Fixing the corpus a newcomer copies is
narrower and leaves the default honest. It is the same remedy roadmap 118
reached for the `lot_library` laggards, and for the same reason: examples are
what people copy.

`crew_size` was also missing from `mission.brief.schema.json`, which is
probably why nobody set it -- the model and the CLI both read a field the
schema never mentioned.
"""
import json
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
_EXAMPLES = _ROOT / "examples"
_SCHEMA = _ROOT / "schemas" / "mission.brief.schema.json"


def _shipped_briefs():
    return sorted(p for p in _EXAMPLES.rglob("*.json") if p.parent.name == "briefs")


def test_the_schema_documents_crew_size():
    """The field the model and the CLI already read. A schema that omits it
    is why 26 of 27 briefs never set it."""
    fields = json.loads(_SCHEMA.read_text(encoding="utf-8"))["fields"]
    assert fields.get("crew_size") == "int", fields.get("crew_size")


def test_there_are_shipped_briefs_to_check():
    """A sweep over zero files passes and proves nothing (CLAUDE.md)."""
    assert len(_shipped_briefs()) >= 4, [str(p) for p in _shipped_briefs()]


@pytest.mark.parametrize("path", _shipped_briefs(), ids=lambda p: p.name)
def test_every_shipped_brief_declares_a_crew(path):
    d = json.loads(path.read_text(encoding="utf-8"))
    assert "crew_size" in d, (
        f"{path.name} does not say how many people arrive, so it evaluates as "
        "1 against enemy_count's 6")
    assert isinstance(d["crew_size"], int) and d["crew_size"] >= 1, d["crew_size"]


def test_the_crew_is_not_outnumbered_six_to_one():
    """NOT a rule about the right crew size -- a rule against the pairing that
    made every level read as unplayable. 6 versus 1 is the shipped enemy count
    against the shipped crew default, and it wiped three maps in a row."""
    from adapters import laser_tag
    enemies = laser_tag._STOCK_SCENARIO["enemy_count"]
    for path in _shipped_briefs():
        crew = json.loads(path.read_text(encoding="utf-8")).get("crew_size", 1)
        assert crew * 2 >= enemies, (
            f"{path.name}: {crew} crew against {enemies} enemies. Measured at "
            "1-vs-6 every run ended in a team wipe on three separate maps.")
