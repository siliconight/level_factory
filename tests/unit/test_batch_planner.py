"""Cross-mission batch planning (TDD 42, Phase 4)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from packages.core.models import MissionBrief
from packages.pipeline.batch_planner import plan_batch, shared_pixelcoat_id


def _briefs(n):
    return [MissionBrief(mission_id=f"m{i}", display_name=f"M{i}", archetype="bank",
                         candidate_count=3, time_of_day="afternoon")
            for i in range(1, n + 1)]


def test_shared_pixelcoat_is_deduplicated():
    briefs = _briefs(3)
    batch = {"batch_id": "b1", "seed_base": 1997, "theme_family": "delco"}
    sel = {b.mission_id: f"{b.mission_id}.candidate.seed_1997" for b in briefs}
    plan = plan_batch(briefs, batch=batch, selected_by_mission=sel, target="presentation")

    jobs = list(plan.graph.jobs())
    # Exactly one shared Pixelcoat node, no per-mission pixelcoat_build.
    assert shared_pixelcoat_id("b1") in [j.job_id for j in jobs]
    assert not any(j.stage_id == "pixelcoat_build" for j in jobs)
    # Every mission's Zoo kit depends on the shared node.
    kits = [j for j in jobs if j.stage_id == "zoo_kit_build"]
    assert len(kits) == 3
    assert all(shared_pixelcoat_id("b1") in k.depends_on for k in kits)


def test_missions_without_selection_are_skipped():
    briefs = _briefs(3)
    batch = {"batch_id": "b1", "seed_base": 1997}
    sel = {"m1": "m1.candidate.seed_1997", "m2": None, "m3": "m3.candidate.seed_1997"}
    plan = plan_batch(briefs, batch=batch, selected_by_mission=sel, target="presentation")
    assert set(plan.mission_ids) == {"m1", "m3"}
    assert plan.skipped_missions == ["m2"]


def test_graph_topologically_sorts():
    briefs = _briefs(2)
    batch = {"batch_id": "b1", "seed_base": 1997}
    sel = {b.mission_id: f"{b.mission_id}.candidate.seed_1997" for b in briefs}
    plan = plan_batch(briefs, batch=batch, selected_by_mission=sel, target="presentation")
    order = plan.graph.topological_order()  # raises on a cycle
    ids = [j.job_id for j in order]
    # Shared node comes before any zoo_kit that depends on it.
    shared_pos = ids.index(shared_pixelcoat_id("b1"))
    for j in order:
        if j.stage_id == "zoo_kit_build":
            assert shared_pos < ids.index(j.job_id)
