"""Unit tests: planner + DAG (TDD 15, 16)."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from packages.core.models import Job, MissionBrief
from packages.pipeline.graph import GraphError, JobGraph
from packages.pipeline.planner import (
    TARGET_FUNCTIONAL_LOCK, TARGET_SHELL_HANDOFF, derive_seeds, plan_mission,
)


def _brief(n=3):
    return MissionBrief(mission_id="m1", display_name="M1", archetype="urban_bank",
                        candidate_count=n)


def test_derive_seeds_deterministic():
    assert derive_seeds(1997, 3) == [1997, 2098, 2199]


def test_functional_plan_has_no_dispatch():
    plan = plan_mission(_brief(), seed_base=1997, target=TARGET_FUNCTIONAL_LOCK)
    adapters = {j.adapter_id for j in plan.graph.jobs()}
    assert "dispatch" not in adapters
    assert len(plan.candidate_ids) == 3
    # 3 candidates x (deli + lot + laser) = 9 jobs.
    assert len(plan.graph.jobs()) == 9


def test_handoff_plan_requires_selected_candidate():
    no_sel = plan_mission(_brief(), seed_base=1997, target=TARGET_SHELL_HANDOFF)
    assert not any(j.adapter_id == "dispatch" for j in no_sel.graph.jobs())

    sel = plan_mission(_brief(), seed_base=1997, target=TARGET_SHELL_HANDOFF,
                       selected_candidate="m1.candidate.seed_1997")
    dispatch_jobs = [j for j in sel.graph.jobs() if j.adapter_id == "dispatch"]
    assert len(dispatch_jobs) == 1
    # Dispatch depends on the Lot site of exactly the selected candidate.
    assert "seed_1997" in dispatch_jobs[0].depends_on[0]


def test_topological_order_respects_dependencies():
    plan = plan_mission(_brief(1), seed_base=1997, target=TARGET_FUNCTIONAL_LOCK)
    order = [j.job_id for j in plan.graph.topological_order()]
    deli = next(i for i, j in enumerate(order) if "deli" in j)
    lot = next(i for i, j in enumerate(order) if "lot" in j)
    laser = next(i for i, j in enumerate(order) if "laser" in j)
    assert deli < lot < laser


def test_graph_detects_cycle():
    g = JobGraph()
    g.add(Job(job_id="a", mission_id="m", stage_id="s", adapter_id="x", depends_on=["b"]))
    g.add(Job(job_id="b", mission_id="m", stage_id="s", adapter_id="x", depends_on=["a"]))
    with pytest.raises(GraphError):
        g.topological_order()


# --- Composable output layers (graybox base + optional art/gameplay) ---

from packages.pipeline.planner import (  # noqa: E402
    LAYER_ART, LAYER_GAMEPLAY, layers_for_target, label_for_layers,
    TARGET_PRESENTATION,
)

_SEL = "m1.candidate.seed_1997"


def _stages(layers):
    plan = plan_mission(_brief(), seed_base=1997, layers=layers, selected_candidate=_SEL)
    return {j.stage_id for j in plan.graph.jobs()}


def test_graybox_base_is_just_deli_lot_laser():
    st = _stages(frozenset())
    assert st == {"deli_generate", "lot_assemble", "laser_tag_evaluate"}


def test_art_layer_has_full_art_pass_but_no_dispatch():
    st = _stages(frozenset({LAYER_ART}))
    assert {"pixelcoat_build", "zoo_kit_build", "patina_apply", "patina_dressing",
            "zoo_dressing_build", "lux_apply"} <= st
    assert "dispatch_handoff" not in st  # art alone never runs the gameplay layer


def test_gameplay_layer_alone_puts_dispatch_on_graybox():
    plan = plan_mission(_brief(), seed_base=1997, layers=frozenset({LAYER_GAMEPLAY}),
                        selected_candidate=_SEL)
    disp = next(j for j in plan.graph.jobs() if j.stage_id == "dispatch_handoff")
    # No art stages, and dispatch depends on the Lot site (graybox), not Lux.
    assert "lux_apply" not in {j.stage_id for j in plan.graph.jobs()}
    assert "lot_assemble" in disp.depends_on[0]


def test_both_layers_dispatch_builds_on_art_scene():
    plan = plan_mission(_brief(), seed_base=1997,
                        layers=frozenset({LAYER_ART, LAYER_GAMEPLAY}), selected_candidate=_SEL)
    disp = next(j for j in plan.graph.jobs() if j.stage_id == "dispatch_handoff")
    assert disp.depends_on[0].endswith("lux_apply")


def test_layers_require_a_locked_candidate():
    # Optional layers with no selection -> only the graybox candidate shells.
    plan = plan_mission(_brief(), seed_base=1997, layers=frozenset({LAYER_ART}),
                        selected_candidate=None)
    assert "lux_apply" not in {j.stage_id for j in plan.graph.jobs()}


def test_legacy_target_maps_to_layers():
    assert layers_for_target(TARGET_FUNCTIONAL_LOCK) == frozenset()
    assert layers_for_target(TARGET_SHELL_HANDOFF) == frozenset({LAYER_GAMEPLAY})
    assert layers_for_target(TARGET_PRESENTATION) == frozenset({LAYER_ART, LAYER_GAMEPLAY})


def test_output_labels():
    assert label_for_layers(frozenset()) == "graybox"
    assert label_for_layers({LAYER_ART}) == "graybox+art"
    assert label_for_layers({LAYER_GAMEPLAY}) == "graybox+gameplay"
    assert label_for_layers({LAYER_ART, LAYER_GAMEPLAY}) == "graybox+art+gameplay"


def test_plan_records_layers():
    plan = plan_mission(_brief(), seed_base=1997, layers=frozenset({LAYER_ART}),
                        selected_candidate=_SEL)
    d = plan.as_dict()
    assert d["layers"] == ["art"]
    assert d["output_label"] == "graybox+art"
