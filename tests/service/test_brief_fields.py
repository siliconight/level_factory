"""The Level Standard's designer brief on the Level tab (0.253.0; the walker's section 16, docs/LEVEL_STANDARD.md).

PLAYERS is a real control: the brief's ``crew_size``, which Lot reads to place one spawn per crew member and Laser
Tag reads as the crew it plays, so changing it rebuilds the layouts. The standard's FANTASY, SCALE, DENSITY, TONE and
PLAYSTYLE have no reader yet: they are intent, saved and reopened with the design and kept out of the pipeline's
brief. A design saved before this release, without Players, builds exactly as it did. FAILS ON 0.252.0.
"""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from apps.cli.commands import _brief_model  # noqa: E402
from packages.service import design, operations, schemas  # noqa: E402

T = "restaurant_row"
STANDARD = ("fantasy", "scale", "density", "tone", "playstyle")
_NOOP = type("E", (), {"emit": lambda self, *a, **k: None})()


def _controls():
    return {c["key"]: c for c in design.capabilities(T)}


def test_players_is_the_crew_lot_and_laser_tag_read():
    c = _controls()["crew_size"]
    assert (c["label"], c["support"], c["min"], c["max"], c["default"], c["rebuilds"]) == (
        "Players", "supported", 1, 4, 4, "layout")
    brief = design.brief_from_design(design.new_design(T, "t", {"crew_size": 2}))
    assert brief["crew_size"] == 2 and _brief_model(brief).crew_size == 2
    for bad in (0, 5, True, "4"):
        with pytest.raises(design.DesignError):
            design.new_design(T, "t", {"crew_size": bad})


def test_changing_players_rebuilds_the_layouts():
    old = design.new_design(T, "t")
    new = design.update_design(old, 1, choices={"crew_size": 3})
    assert design.rebuilds_between(old, new) == ["layout"]


def test_the_standards_brief_is_intent_kept_out_of_the_pipeline():
    c = _controls()
    for key in STANDARD:
        assert c[key]["support"] == "intent" and "nothing builds from it" in c[key]["note"]
    words = {"fantasy": "Rob the deli's office safe after close and leave by the alley.", "scale": "small",
             "density": "medium-high", "tone": "familiar, worn, warm", "playstyle": "stealth, then loud"}
    brief = design.brief_from_design(design.new_design(T, "t", intent=words))
    assert not set(STANDARD) & set(brief)
    assert brief == design.brief_from_design(design.new_design(T, "t"))     # it changes nothing built


def test_the_brief_is_saved_and_reopened(tmp_path, monkeypatch):
    from packages.tools import discovery
    monkeypatch.setattr(discovery, "factory_root", lambda start=None: tmp_path)
    got = operations.create_design({"template": T, "name": "Brief", "choices": {"crew_size": 2},
                                    "intent": {"fantasy": "Crack the safe", "tone": "worn"}}, _NOOP)
    opened = operations.open_design({"path": got["path"]}, _NOOP)
    assert opened["problems"] == [] and opened["unknown_fields"] == []
    d = opened["design"]
    assert d["choices"]["crew_size"] == 2 and d["intent"]["fantasy"] == "Crack the safe" and d["intent"]["tone"] == "worn"
    assert schemas.check(d, "gabagool.design.v1") == []


def test_a_design_saved_before_players_builds_as_it_did():
    old = json.loads((Path(__file__).resolve().parent / "fixtures" / "authoring" / "design.json").read_text(
        encoding="utf-8"))
    assert "crew_size" not in old["choices"]
    assert design.validate(old) == ([], [])
    brief = design.brief_from_design(old)
    assert "crew_size" not in brief and _brief_model(brief).crew_size == 4
