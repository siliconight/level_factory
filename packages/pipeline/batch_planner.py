"""Cross-mission batch planning (TDD 42 Phase 4).

Composes each mission's presentation plan into ONE combined DAG so the whole
batch runs as a single scheduler pass. Shared work is deduplicated into a single
batch-level node rather than rebuilt per mission: the shared Pixelcoat surface
packs are built once (a batch asset) and every mission's Zoo kit depends on that
one node.

Job ids are mission-namespaced and the shared node is batch-namespaced, so the
merged graph has no id collisions. The content-addressed cache still covers any
incidental cross-mission dedup beyond the explicit shared node.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path

from packages.core.models import Job, MissionBrief
from packages.pipeline.graph import JobGraph
from packages.pipeline.planner import (
    TARGET_FUNCTIONAL_LOCK, TARGET_PRESENTATION, TARGET_SHELL_HANDOFF, plan_mission,
)

SHARED_PIXELCOAT_STAGE = "pixelcoat_shared"


def shared_pixelcoat_id(batch_id: str) -> str:
    return f"batch.{batch_id}.{SHARED_PIXELCOAT_STAGE}"


@dataclass
class BatchPlan:
    batch_id: str
    target: str
    graph: JobGraph
    mission_ids: list[str] = field(default_factory=list)
    skipped_missions: list[str] = field(default_factory=list)
    shared_job_ids: list[str] = field(default_factory=list)
    layers: frozenset = field(default_factory=frozenset)

    def as_dict(self) -> dict:
        return {
            "batch_id": self.batch_id,
            "target": self.target,
            "layers": sorted(self.layers),
            "missions": self.mission_ids,
            "skipped_missions": self.skipped_missions,
            "shared_jobs": self.shared_job_ids,
            "job_count": len(list(self.graph.jobs())),
        }


def plan_batch(
    briefs: list[MissionBrief],
    *,
    batch: dict,
    selected_by_mission: dict[str, str | None],
    target: str = TARGET_PRESENTATION,
    layers=None,
) -> BatchPlan:
    from packages.pipeline.planner import LAYER_ART, layers_for_target
    layers = frozenset(layers) if layers is not None else layers_for_target(target)
    batch_id = str(batch.get("batch_id", "batch"))
    seed_base = int(batch.get("seed_base", 0))
    graph = JobGraph()
    plan = BatchPlan(batch_id=batch_id, target=target, graph=graph)
    plan.layers = layers

    include_shared = (LAYER_ART in layers)  # Pixelcoat is part of the Art layer
    shared_id = shared_pixelcoat_id(batch_id)
    if include_shared:
        graph.add(Job(
            job_id=shared_id, mission_id=f"batch:{batch_id}",
            stage_id=SHARED_PIXELCOAT_STAGE, adapter_id="pixelcoat",
            resource_class="python_cpu", depends_on=[],
            expected_outputs=["theme/theme.pack.json"],
        ))
        plan.shared_job_ids.append(shared_id)

    for brief in briefs:
        selected = selected_by_mission.get(brief.mission_id)
        # Any optional layer needs a selected+locked candidate; skip missions
        # without one. Graybox-only batches have no post-lock jobs to gate.
        if layers and not selected:
            plan.skipped_missions.append(brief.mission_id)
            continue
        mplan = plan_mission(brief, seed_base=seed_base, layers=layers,
                             selected_candidate=selected)
        for job in mplan.graph.jobs():
            # Drop the per-mission Pixelcoat node; the shared node replaces it.
            if include_shared and job.stage_id == "pixelcoat_build":
                continue
            deps = list(job.depends_on)
            if include_shared and job.stage_id == "zoo_kit_build":
                deps = [shared_id if d.endswith("pixelcoat_build") else d for d in deps]
            graph.add(replace(job, depends_on=deps))
        plan.mission_ids.append(brief.mission_id)

    return plan
