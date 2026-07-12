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
TARGET_PRESENTATION = "presentation"

_STAGE_DELI = "deli_generate"
_STAGE_LOT = "lot_assemble"
_STAGE_LASER = "laser_tag_evaluate"
_STAGE_DISPATCH = "dispatch_handoff"

# Presentation pipeline stages (TDD 15.2).
_STAGE_PIXELCOAT = "pixelcoat_build"
_STAGE_ZOO_KIT = "zoo_kit_build"
_STAGE_PATINA_BASE = "patina_apply"
_STAGE_PATINA_DRESS = "patina_dressing"
_STAGE_ZOO_DRESS = "zoo_dressing_build"
_STAGE_LUX = "lux_apply"
_STAGE_REGRESSION = "regression"


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
            expected_outputs=["site.tscn", "site_walk.tscn",
                              "site.site.gameplay.json", "site.site.lights.json"],
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

    # Handoff / presentation tail requires a selected+locked candidate.
    plan.selected_candidate = selected_candidate
    if selected_candidate is None:
        return plan

    lot_jid = lot_job_ids_by_candidate[selected_candidate]
    dispatch_dep = lot_jid

    if target == TARGET_PRESENTATION:
        # Presentation DAG (TDD 15.2), rooted at the locked functional shell.
        # Pixelcoat shared packs.
        pixelcoat_jid = job_id(brief.mission_id, _STAGE_PIXELCOAT)
        plan.graph.add(Job(
            job_id=pixelcoat_jid, mission_id=brief.mission_id,
            stage_id=_STAGE_PIXELCOAT, adapter_id="pixelcoat",
            candidate_id=selected_candidate, resource_class="python_cpu",
            depends_on=[lot_jid],
            expected_outputs=["theme/theme.pack.json"],
        ))
        # Zoo structural kit from DC slots, skinned by Pixelcoat packs.
        zoo_kit_jid = job_id(brief.mission_id, _STAGE_ZOO_KIT)
        plan.graph.add(Job(
            job_id=zoo_kit_jid, mission_id=brief.mission_id,
            stage_id=_STAGE_ZOO_KIT, adapter_id="zoo",
            candidate_id=selected_candidate, resource_class="blender",
            depends_on=[lot_jid, pixelcoat_jid],
            expected_outputs=["zoo.manifest.json"],
        ))
        # Patina base cohesion pass.
        patina_base_jid = job_id(brief.mission_id, _STAGE_PATINA_BASE)
        plan.graph.add(Job(
            job_id=patina_base_jid, mission_id=brief.mission_id,
            stage_id=_STAGE_PATINA_BASE, adapter_id="patina",
            candidate_id=selected_candidate, resource_class="python_cpu",
            depends_on=[lot_jid],
            expected_outputs=["shell.patina.glb", "shell.patina.json",
                              "shell.patina.gameplay.json"],
        ))
        # Patina dressing manifest.
        patina_dress_jid = job_id(brief.mission_id, _STAGE_PATINA_DRESS)
        plan.graph.add(Job(
            job_id=patina_dress_jid, mission_id=brief.mission_id,
            stage_id=_STAGE_PATINA_DRESS, adapter_id="patina",
            candidate_id=selected_candidate, resource_class="python_cpu",
            depends_on=[patina_base_jid],
            expected_outputs=["shell.patina.glb", "shell.patina.json",
                              "shell.patina.gameplay.json",
                              "shell.patina.dressing.json"],
        ))
        # Zoo dressing build from the Patina manifest (collision-free).
        zoo_dress_jid = job_id(brief.mission_id, _STAGE_ZOO_DRESS)
        plan.graph.add(Job(
            job_id=zoo_dress_jid, mission_id=brief.mission_id,
            stage_id=_STAGE_ZOO_DRESS, adapter_id="zoo",
            candidate_id=selected_candidate, resource_class="blender",
            depends_on=[patina_dress_jid, zoo_kit_jid],
            expected_outputs=["zoo.manifest.json"],
        ))
        # Lux apply (final PS2 look) over the composed presentation scene.
        lux_jid = job_id(brief.mission_id, _STAGE_LUX)
        plan.graph.add(Job(
            job_id=lux_jid, mission_id=brief.mission_id,
            stage_id=_STAGE_LUX, adapter_id="lux",
            candidate_id=selected_candidate, resource_class="godot_headless",
            depends_on=[zoo_dress_jid],
            expected_outputs=["lux.applied.tscn", "lux.quality.json",
                              "lux.validation.json"],
        ))
        # Dispatch depends on the Lux-applied presentation, not just the Lot site.
        dispatch_dep = lux_jid

    dispatch_jid = job_id(brief.mission_id, _STAGE_DISPATCH)
    dispatch = Job(
        job_id=dispatch_jid,
        mission_id=brief.mission_id,
        stage_id=_STAGE_DISPATCH,
        adapter_id="dispatch",
        candidate_id=selected_candidate,
        resource_class="python_cpu",
        depends_on=[dispatch_dep],
        expected_outputs=["mission.tscn", "mission_manifest.json",
                          "gameplay_anchors.json", "runtime_ownership_requirements.json",
                          "proposed_beat_graph.json", "navigation_hints.json",
                          "build.lock.json", "HANDOFF.md"],
    )
    plan.graph.add(dispatch)

    return plan
