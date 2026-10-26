"""A level is a saved design, and its form tells the truth (0.245.0, the factory's roadmap 312 and 313).

Two promises, each held from both sides. THE CATALOG: every option a control offers is one its consumer knows, read
off the owning code; every field nothing builds from is labelled intent; and a supported control's value reaches
what the pipeline plans or builds. THE DESIGN: created, saved, reopened with every choice intact; a name used twice
never overwrites; unknown fields are reported, not dropped; the brief derived from the Restaurant Row template at its
defaults is the brief cold run 9222 built with nobody touching anything. FAILS ON 0.244.0: no design module.
"""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from apps.cli.commands import UNBUILT_BRIEF_FIELDS, _brief_model, _preset_for  # noqa: E402
from packages.pipeline import road_grammar, site_variation  # noqa: E402
from packages.pipeline.planner import derive_seeds  # noqa: E402
from packages.service import design, operations  # noqa: E402
from packages.service.worker import RequestError  # noqa: E402

T = "restaurant_row"
_NOOP = type("E", (), {"emit": lambda self, *a, **k: None})()


def _controls():
    return {c["key"]: c for c in design.capabilities(T)}


# ---- the catalog ------------------------------------------------------------------------------------------------

def test_every_unbuilt_field_is_labelled_intent_and_nothing_else_is():
    c = _controls()
    intent = {k for k, v in c.items() if v["support"] == "intent"}
    assert intent == set(UNBUILT_BRIEF_FIELDS) | {"notes"}
    for k in intent:
        assert c[k]["note"], k


def test_the_options_are_the_consumers_own():
    c = _controls()
    assert [o["value"] for o in c["road_grammar"]["options"]] == list(road_grammar.GRAMMARS)
    assert [o["value"] for o in c["surroundings"]["options"]] == [""] + list(site_variation.SURROUNDINGS)
    assert (c["candidate_count"]["min"], c["candidate_count"]["max"]) == design.CANDIDATES


def test_each_time_of_day_lights_the_level_differently():
    presets = set()
    for o in _controls()["time_of_day"]["options"]:
        doc = design.new_design(T, "t", {"time_of_day": o["value"]})
        presets.add(_preset_for(_brief_model(design.brief_from_design(doc))))
    assert len(presets) == 5 and "Gas Station Fluorescent" not in presets      # none falls through to the default


def test_rain_is_conditional_and_says_what_it_replaces():
    w = _controls()["weather"]
    assert w["support"] == "conditional" and "replaces" in w["note"]
    doc = design.new_design(T, "t", {"weather": "rain", "time_of_day": "midnight"})
    assert _preset_for(_brief_model(design.brief_from_design(doc))) == "Heavy Rain"


def test_streets_and_layout_count_reach_the_pipeline():
    doc = design.new_design(T, "t", {"road_grammar": "block", "candidate_count": 5})
    brief = design.brief_from_design(doc)
    assert road_grammar.grammar_of(brief["road_grammar"]) == "block"
    assert len(derive_seeds(9003, _brief_model(brief).candidate_count)) == 5


def test_a_bad_value_or_an_unknown_control_is_refused():
    with pytest.raises(design.DesignError):
        design.new_design(T, "t", {"time_of_day": "dawn"})
    with pytest.raises(design.DesignError):
        design.new_design(T, "t", {"candidate_count": 99})
    with pytest.raises(design.DesignError):
        design.new_design(T, "t", {"verticality": "high"})          # intent is not a choice
    with pytest.raises(design.DesignError):
        design.new_design(T, "t", intent={"time_of_day": "noon"})   # nor a choice intent
    with pytest.raises(design.DesignError):
        design.new_design(T, "  ")


def test_the_template_at_its_defaults_is_the_first_level_brief():
    from packages.tools import discovery
    factory = discovery.factory_root()
    if factory is None:
        pytest.skip("this Level Factory stands outside a factory: no first-level brief to compare with")
    first = json.loads((factory / "docs" / "first_level" / "briefs" / "restaurant_row_001.json").read_text(
        encoding="utf-8"))
    brief = design.brief_from_design(design.new_design(T, "Restaurant Row"))
    for key, value in first.items():
        if key in ("mission_id", "notes"):
            continue
        assert brief[key] == value, key


# ---- the design -------------------------------------------------------------------------------------------------

@pytest.fixture
def factory(tmp_path, monkeypatch):
    from packages.tools import discovery
    monkeypatch.setattr(discovery, "factory_root", lambda start=None: tmp_path)
    return tmp_path


def test_create_save_reopen_keeps_every_choice(factory):
    made = operations.create_design({"template": T, "name": "Night Shift",
                                     "choices": {"time_of_day": "midnight", "road_grammar": "cross"},
                                     "intent": {"notes": "a tired strip after closing"}}, _NOOP)
    path = Path(made["path"])
    assert path == factory / "levels" / "night_shift" / "design.json"
    got = operations.open_design({"path": str(path.parent)}, _NOOP)
    assert got["problems"] == [] and got["unknown_fields"] == []
    assert got["design"] == made["design"]
    assert got["design"]["choices"]["time_of_day"] == "midnight"
    assert got["brief"]["notes"] == "a tired strip after closing"
    assert got["brief"]["mission_id"] == "night_shift_001"


def test_a_name_used_twice_gets_its_own_folder(factory):
    a = operations.create_design({"template": T, "name": "Twice"}, _NOOP)
    b = operations.create_design({"template": T, "name": "Twice"}, _NOOP)
    assert Path(a["path"]).parent.name == "twice" and Path(b["path"]).parent.name == "twice_2"
    assert b["design"]["slug"] == "twice_2" and b["brief"]["mission_id"] == "twice_2_001"
    listed = operations.list_designs({}, _NOOP)["designs"]
    assert {Path(r["path"]).parent.name for r in listed} == {"twice", "twice_2"}


def test_unknown_fields_are_reported_and_a_wrong_schema_is_a_problem(factory):
    made = operations.create_design({"template": T, "name": "Odd"}, _NOOP)
    path = Path(made["path"])
    doc = json.loads(path.read_text(encoding="utf-8"))
    doc["colour_grade"] = "teal"
    doc["choices"]["fog"] = 0.3
    path.write_text(json.dumps(doc), encoding="utf-8")
    got = operations.open_design({"path": str(path)}, _NOOP)
    assert sorted(got["unknown_fields"]) == ["choices.fog", "colour_grade"]
    assert got["design"]["colour_grade"] == "teal"                     # kept, not dropped
    doc["schema"] = "gabagool.design.v0"
    path.write_text(json.dumps(doc), encoding="utf-8")
    got = operations.open_design({"path": str(path)}, _NOOP)
    assert got["problems"] and got["brief"] is None


def test_operations_refuse_with_reasons(factory):
    with pytest.raises(RequestError) as e:
        operations.create_design({"template": "space_station", "name": "x"}, _NOOP)
    assert e.value.code == "unknown_template"
    with pytest.raises(RequestError) as e:
        operations.open_design({"path": str(factory / "nowhere")}, _NOOP)
    assert e.value.code == "no_design"
    assert [t["template_id"] for t in operations.list_templates({}, _NOOP)["templates"]] == [T]
    assert operations.describe_template({"template": T}, _NOOP)["controls"]
