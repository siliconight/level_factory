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

WHY THE EXAMPLES FIRST AND THE DEFAULT SECOND. Raising `crew_size`'s default
changes every historical comparison in one line -- the objection that kept
`advance_while_engaging` opt-in -- so 0.62.0 fixed the corpus a newcomer
copies and left the default at 1. On 2026-09-11 the default was raised to 4
as well (0.69.0), decided rather than drifted into: the 23 briefs still
without a crew were all workspace copies and cold-run records, and the
scenario values are in the Laser Tag fingerprint, so their next evaluation
re-runs at 4 instead of replaying a grade taken at 1. The examples still
declare the field, because a brief that says how many people arrive is
better than one that inherits it.

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


def test_the_default_crew_is_four():
    """The decision of 2026-09-11 (roadmap 129), pinned in the one place the
    brief model reads it and in the two CLI fallbacks that repeat it."""
    from packages.core.models import MissionBrief
    m = MissionBrief(mission_id="m", display_name="M", archetype="urban_bank")
    assert m.crew_size == 4
    src = (_ROOT / "apps" / "cli" / "commands" / "__init__.py").read_text(encoding="utf-8")
    assert 'getattr(model, "crew_size", 1)' not in src, "a CLI fallback still says 1"


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
