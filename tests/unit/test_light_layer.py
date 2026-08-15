"""LAYER_LIGHT: Lux's apply pass, and only that, is declinable.

Roadmap item 47 stage 1. Six of these are about one line --

    dispatch_dep = lux_jid if LAYER_LIGHT in layers else themed_jid

-- because getting it wrong builds the Dispatch handoff on the wrong scene
and reports success, which is a failure nobody would see.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from packages.core.models import MissionBrief  # noqa: E402
from packages.pipeline.planner import (  # noqa: E402
    ALL_LAYERS, LAYER_ART, LAYER_GAMEPLAY, LAYER_LIGHT, TARGET_PRESENTATION,
    label_for_layers, layers_for_target, normalize_layers, plan_mission,
)

CAND = "m1.candidate.seed_1997"


def _brief():
    return MissionBrief(mission_id="m1", display_name="M1",
                        archetype="urban_bank", candidate_count=1)


def _plan(layers):
    return plan_mission(_brief(), seed_base=1997, layers=layers,
                        selected_candidate=CAND)


def _stages(plan):
    return {j.stage_id for j in plan.graph.jobs()}


def _job(plan, stage_id):
    matches = [j for j in plan.graph.jobs() if j.stage_id == stage_id]
    assert len(matches) == 1, f"{stage_id}: {[j.job_id for j in matches]}"
    return matches[0]


# --------------------------------------------------------------- the vocabulary

def test_light_is_a_layer():
    assert LAYER_LIGHT in ALL_LAYERS


def test_presentation_still_means_the_full_lit_stack():
    """--target presentation has always produced a LIT level."""
    assert layers_for_target(TARGET_PRESENTATION) == frozenset(
        {LAYER_ART, LAYER_LIGHT, LAYER_GAMEPLAY})


def test_the_label_names_the_light_layer():
    assert label_for_layers({LAYER_ART}) == "graybox+art"
    assert label_for_layers({LAYER_ART, LAYER_LIGHT}) == "graybox+art+light"
    assert label_for_layers(
        {LAYER_ART, LAYER_LIGHT, LAYER_GAMEPLAY}) == "graybox+art+light+gameplay"


def test_light_without_art_is_refused_not_repaired():
    """It would otherwise plan NOTHING and succeed.

    `lux_apply` is reached only from inside `if LAYER_ART in layers`, so a
    light-only request produces a graybox plan that runs and reports success.
    Adding art silently would be worse: a caller who asked for light would be
    billed for four tools it never requested.
    """
    with pytest.raises(ValueError) as exc:
        normalize_layers({LAYER_LIGHT})
    assert "requires" in str(exc.value)


def test_an_unknown_layer_is_refused():
    with pytest.raises(ValueError):
        normalize_layers({"lighting"})


def test_plan_mission_validates_too():
    """Not just the helper -- the door everything comes through."""
    with pytest.raises(ValueError):
        plan_mission(_brief(), seed_base=1997, layers={LAYER_LIGHT},
                     selected_candidate=CAND)


# ------------------------------------------------------------- what is planned

def test_light_on_plans_lux_apply():
    assert "lux_apply" in _stages(_plan({LAYER_ART, LAYER_LIGHT}))


def test_light_off_does_not():
    assert "lux_apply" not in _stages(_plan({LAYER_ART}))


def test_the_fixture_pass_stays_in_the_art_layer():
    """THE PART THAT MUST NOT MOVE.

    Where the light hardware physically is, and whether it is co-located with
    its lamp, is a question about the LEVEL. An unlit package still ships
    validated fixtures and their LuxEmit markers for another lighting system.
    """
    unlit = _stages(_plan({LAYER_ART}))
    assert "zoo_fixtures_build" in unlit
    assert "lux_fixture_gate" in unlit


def test_the_themed_site_stays_in_the_art_layer():
    assert "themed_site_assemble" in _stages(_plan({LAYER_ART}))


# ------------------------------------------------- the one line that carries it

def test_dispatch_depends_on_lux_when_lit():
    plan = _plan({LAYER_ART, LAYER_LIGHT, LAYER_GAMEPLAY})
    assert _job(plan, "dispatch_handoff").depends_on == [
        _job(plan, "lux_apply").job_id]


def test_dispatch_depends_on_the_themed_site_when_unlit():
    """NOT the greybox, which is where a fallthrough would land it.

    `themed_site_assemble` is the last stage that makes a place. Handing
    Dispatch the graybox instead would build the handoff on a site with no art
    pass on it and report success.
    """
    plan = _plan({LAYER_ART, LAYER_GAMEPLAY})
    assert _job(plan, "dispatch_handoff").depends_on == [
        _job(plan, "themed_site_assemble").job_id]


def test_the_unlit_handoff_does_not_depend_on_the_graybox():
    plan = _plan({LAYER_ART, LAYER_GAMEPLAY})
    dep = _job(plan, "dispatch_handoff").depends_on[0]
    assert "lot_assemble" not in dep


def test_a_graybox_gameplay_plan_is_unchanged():
    """No art at all still means Dispatch rides the Lot site."""
    plan = _plan({LAYER_GAMEPLAY})
    dep = _job(plan, "dispatch_handoff").depends_on[0]
    assert "lot_assemble" in dep


def test_no_dangling_dependencies_either_way():
    """A dependency on a job that was never planned is exactly what the
    conditional could produce, and a DAG will happily hold one."""
    for layers in ({LAYER_ART, LAYER_GAMEPLAY},
                   {LAYER_ART, LAYER_LIGHT, LAYER_GAMEPLAY}):
        plan = _plan(layers)
        planned = {j.job_id for j in plan.graph.jobs()}
        for j in plan.graph.jobs():
            missing = [d for d in j.depends_on if d not in planned]
            assert not missing, f"{layers} -> {j.job_id} needs {missing}"


def test_the_unlit_plan_is_the_lit_plan_minus_exactly_one_stage():
    lit = _stages(_plan({LAYER_ART, LAYER_LIGHT, LAYER_GAMEPLAY}))
    unlit = _stages(_plan({LAYER_ART, LAYER_GAMEPLAY}))
    assert lit - unlit == {"lux_apply"}
    assert not unlit - lit
