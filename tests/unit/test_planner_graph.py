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
