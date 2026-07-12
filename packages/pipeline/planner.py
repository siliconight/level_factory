"""Pipeline planner (TDD 15, 16).

Phase 1 implements the *functional* pipeline plus the Dispatch shell-handoff
tail:

    brief -> deli(seed) x N -> lot(per candidate) -> laser_tag(per candidate)
          -> [candidate_selected gate] -> [functional_shell_locked gate]
          -> dispatch(shell-handoff)

Deterministic seeds are derived from the batch seed base and candidate index so
the same brief always plans the same candidates.
"""
from __future__ import annotations

from packages.core.ids import candidate_id, job_id
from packages.core.models import Job, MissionBrief
from packages.pipeline.graph import JobGraph

# Pipeline targets a caller can request.
TARGET_FUNCTIONAL_LOCK = "functional-lock"
TARGET_SHELL_HANDOFF = "dispatch-handoff"

_STAGE_DELI = "deli_generate"
_STAGE_LOT = "lot_assemble"
_STAGE_LASER = "laser_tag_evaluate"
_STAGE_DISPATCH = "dispatch_handoff"


def derive_seeds(seed_base: int, count: int) -> list[int]:
    """Deterministic, well-spread seeds from a base (TDD 25.1)."""
    # Simple LCG-style spread; deterministic and readable in ids.
    return [seed_base + i * 101 for i in range(count)]


class Plan:
    def __init__(self, mission_id: str, target: str) -> None:
        self.mission_id = mission_id
        self.target = target
        self.graph = JobGraph()
        self.candidate_ids: list[str] = []
        self.selected_candidate: str | None = None

    def as_dict(self) -> dict:
        return {
            "schema": "level_factory.pipeline_plan.v0.1",
            "mission_id": self.mission_id,
            "target": self.target,
            "candidates": list(self.candidate_ids),
            "selected_candidate": self.selected_candidate,
            "jobs": [
                {
                    "job_id": j.job_id,
                    "adapter": j.adapter_id,
                    "stage": j.stage_id,
                    "candidate_id": j.candidate_id,
                    "depends_on": list(j.depends_on),
                    "resource_class": j.resource_class,
                    "expected_outputs": list(j.expected_outputs),
                }
                for j in self.graph.topological_order()
            ],
        }


def plan_mission(
    brief: MissionBrief,
    *,
    seed_base: int,
    target: str = TARGET_SHELL_HANDOFF,
    selected_candidate: str | None = None,
) -> Plan:
    """Build the functional (+handoff) DAG for one mission.

    ``selected_candidate`` gates the presentation/handoff tail: Dispatch is only
    planned once a candidate has been selected and locked, and it depends on the
    Lot site of exactly that candidate.
    """
    plan = Plan(brief.mission_id, target)
    seeds = derive_seeds(seed_base, brief.candidate_count)

    laser_job_ids: list[str] = []
    lot_job_ids_by_candidate: dict[str, str] = {}

    for seed in seeds:
        cand = candidate_id(brief.mission_id, seed)
        plan.candidate_ids.append(cand)

        deli_jid = job_id(brief.mission_id, _STAGE_DELI, candidate=cand)
        deli = Job(
            job_id=deli_jid,
            mission_id=brief.mission_id,
            stage_id=_STAGE_DELI,
            adapter_id="deli_counter",
            candidate_id=cand,
            resource_class="blender",
            depends_on=[],
            expected_outputs=["shell.glb", "shell.gameplay.json", "shell.slots.json",
                              "shell.manifest.json", "shell.lights.json"],
        )
        plan.graph.add(deli)

        lot_jid = job_id(brief.mission_id, _STAGE_LOT, candidate=cand)
        lot = Job(
            job_id=lot_jid,
            mission_id=brief.mission_id,
            stage_id=_STAGE_LOT,
            adapter_id="lot",
            candidate_id=cand,
            resource_class="python_cpu",
            depends_on=[deli_jid],
            expected_outputs=["site.tscn", "site.gameplay.json", "site.nav_hints.json",
                              "site.audit.json", "pacing.json"],
        )
        plan.graph.add(lot)
        lot_job_ids_by_candidate[cand] = lot_jid

        laser_jid = job_id(brief.mission_id, _STAGE_LASER, candidate=cand)
        laser = Job(
            job_id=laser_jid,
            mission_id=brief.mission_id,
            stage_id=_STAGE_LASER,
            adapter_id="laser_tag",
            candidate_id=cand,
            resource_class="godot_headless",
            depends_on=[lot_jid],
            expected_outputs=["lasertag.report.json", "lasertag.report.csv"],
        )
        plan.graph.add(laser)
        laser_job_ids.append(laser_jid)

    if target == TARGET_FUNCTIONAL_LOCK:
        return plan

    # Handoff tail requires a selected+locked candidate.
    plan.selected_candidate = selected_candidate
    if selected_candidate is not None:
        dispatch_jid = job_id(brief.mission_id, _STAGE_DISPATCH)
        dispatch = Job(
            job_id=dispatch_jid,
            mission_id=brief.mission_id,
            stage_id=_STAGE_DISPATCH,
            adapter_id="dispatch",
            candidate_id=selected_candidate,
            resource_class="python_cpu",
            depends_on=[lot_job_ids_by_candidate[selected_candidate]],
            expected_outputs=["mission.tscn", "mission_manifest.json",
                              "gameplay_anchors.json", "runtime_ownership_requirements.json",
                              "proposed_beat_graph.json", "navigation_hints.json",
                              "build.lock.json", "HANDOFF.md"],
        )
        plan.graph.add(dispatch)

    return plan
