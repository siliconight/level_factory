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

# Composable output layers. Graybox (DC greybox+collision, assembled by Lot) is
# the always-on base; Art and Gameplay are independent optional layers.
LAYER_ART = "art"          # Zoo swaps + props/dressing, Pixelcoat, Patina, Lux
LAYER_GAMEPLAY = "gameplay"  # Dispatch objective/nav/spawn suggestions (advisory)
ALL_LAYERS = frozenset({LAYER_ART, LAYER_GAMEPLAY})

# Backward-compat: the legacy --target values map onto layer sets.
_TARGET_LAYERS = {
    TARGET_FUNCTIONAL_LOCK: frozenset(),                 # graybox only
    TARGET_SHELL_HANDOFF: frozenset({LAYER_GAMEPLAY}),   # graybox + gameplay
    TARGET_PRESENTATION: frozenset({LAYER_ART, LAYER_GAMEPLAY}),  # full stack
}


def layers_for_target(target: str) -> frozenset:
    """Map a legacy --target string to its composable layer set."""
    return _TARGET_LAYERS.get(target, frozenset({LAYER_GAMEPLAY}))


def label_for_layers(layers) -> str:
    """A short deliverable label for a layer set (for plan/report output)."""
    lset = frozenset(layers or ())
    if not lset:
        return "graybox"
    parts = ["graybox"]
    if LAYER_ART in lset:
        parts.append("art")
    if LAYER_GAMEPLAY in lset:
        parts.append("gameplay")
    return "+".join(parts)

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
_STAGE_ZOO_FIXTURES = "zoo_fixtures_build"
_STAGE_LUX_FIXTURE_GATE = "lux_fixture_gate"
_STAGE_REGRESSION = "regression"


def derive_seeds(seed_base: int, count: int) -> list[int]:
    """Deterministic, well-spread seeds from a base (TDD 25.1)."""
    # Simple LCG-style spread; deterministic and readable in ids.
    return [seed_base + i * 101 for i in range(count)]


class Plan:
    def __init__(self, mission_id: str, target: str, layers=None) -> None:
        self.mission_id = mission_id
        self.target = target
        self.layers = frozenset(layers or ())
        self.graph = JobGraph()
        self.candidate_ids: list[str] = []
        self.selected_candidate: str | None = None

    def as_dict(self) -> dict:
        return {
            "schema": "level_factory.pipeline_plan.v0.1",
            "mission_id": self.mission_id,
            "target": self.target,
            "layers": sorted(self.layers),
            "output_label": label_for_layers(self.layers),
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
    layers=None,
    selected_candidate: str | None = None,
) -> Plan:
    """Build the composable DAG for one mission.

    Graybox (DC greybox+collision assembled by Lot, with Laser Tag nav QA) is the
    always-on base. ``layers`` selects the optional layers on top:
      * LAYER_ART      -> Pixelcoat + Zoo (kit swaps + props/dressing) + Patina + Lux
      * LAYER_GAMEPLAY -> Dispatch objective/nav/spawn suggestions (advisory)
    Layers are independent and apply only once a candidate is selected + locked.
    ``layers`` wins if given; otherwise it's derived from the legacy ``target``.
    """
    layers = frozenset(layers) if layers is not None else layers_for_target(target)
    plan = Plan(brief.mission_id, target, layers)
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

    # Graybox base is the candidate shells above (DC+Lot+Laser Tag QA). With no
    # optional layers selected, the graybox site IS the deliverable.
    if not layers:
        return plan

    # Optional layers require a selected + locked candidate.
    plan.selected_candidate = selected_candidate
    if selected_candidate is None:
        return plan

    lot_jid = lot_job_ids_by_candidate[selected_candidate]
    dispatch_dep = lot_jid

    if LAYER_ART in layers:
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
            expected_outputs=[],  # zoo names by building_id at exec; adapter checks
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
            expected_outputs=[],  # zoo names by building_id at exec; adapter checks
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
        # Light-fixture pass (Zoo v0.30 emitter-marker contract): bake the
        # physical hardware from the locked shell's lights manifest, then
        # machine-gate it — spawn count, lamp<->hardware co-location, powered
        # kill/restore — in headless Godot. Gate findings are BLOCKING (a
        # floating light / dark fixture is broken output, not a style note).
        deli_sel_jid = job_id(brief.mission_id, _STAGE_DELI,
                              candidate=selected_candidate)
        zoo_fixtures_jid = job_id(brief.mission_id, _STAGE_ZOO_FIXTURES)
        plan.graph.add(Job(
            job_id=zoo_fixtures_jid, mission_id=brief.mission_id,
            stage_id=_STAGE_ZOO_FIXTURES, adapter_id="zoo",
            candidate_id=selected_candidate, resource_class="blender",
            depends_on=[deli_sel_jid],
            expected_outputs=[],  # zoo names by scope_id at exec; adapter checks
        ))
        fixture_gate_jid = job_id(brief.mission_id, _STAGE_LUX_FIXTURE_GATE)
        plan.graph.add(Job(
            job_id=fixture_gate_jid, mission_id=brief.mission_id,
            stage_id=_STAGE_LUX_FIXTURE_GATE, adapter_id="lux",
            candidate_id=selected_candidate, resource_class="godot_headless",
            depends_on=[zoo_fixtures_jid],
            expected_outputs=["fixture_gate.report.json"],
        ))
        # Dispatch depends on the Lux-applied presentation, not just the Lot site.
        dispatch_dep = lux_jid

    if LAYER_GAMEPLAY in layers:
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

    return plan
