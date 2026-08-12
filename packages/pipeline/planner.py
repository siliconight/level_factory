"""Pipeline planner (TDD 15, 16).

Phase 1 implements the *functional* pipeline plus the Dispatch shell-handoff
tail:

    brief -> deli(seed) x N -> lot(per candidate) -> walktest(per candidate)
                                                  -> laser_tag(per candidate)
          -> [candidate_selected gate] -> [functional_shell_locked gate]
          -> dispatch(shell-handoff)

Walktest and Laser Tag both depend on Lot and neither depends on the other, so
they run concurrently under the godot_headless cap. They answer different
questions and only one of them is a gate: walktest asks whether the site is
navigable, which this stack certifies; Laser Tag grades a firefight, which it
does not.

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
_STAGE_WALKTEST = "walktest_navqa"
_STAGE_LASER = "laser_tag_evaluate"
_STAGE_DISPATCH = "dispatch_handoff"

# Presentation pipeline stages (TDD 15.2).
_STAGE_PIXELCOAT = "pixelcoat_build"
_STAGE_ZOO_KIT = "zoo_kit_build"
_STAGE_PATINA_BASE = "patina_apply"
_STAGE_PATINA_DRESS = "patina_dressing"
_STAGE_ZOO_DRESS = "zoo_dressing_build"
_STAGE_COMPOSE = "presentation_compose"
_STAGE_THEMED_SITE = "themed_site_assemble"
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
                    # Only when the job HAS one. A mission-wide job carries no
                    # archetype, and adding a null to every line of every plan
                    # that has ever been written buys nothing; an absent key
                    # reads as "this stage runs once for the mission".
                    **({"archetype_id": j.archetype_id} if j.archetype_id else {}),
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

    Graybox -- DC greybox+collision assembled by Lot, nav QA by walktest, and a
    Laser Tag firefight grade beside it -- is the always-on base. (That line
    used to read "with Laser Tag nav QA", which is how a firefight ended up
    being the only evidence for every navigation claim in the roadmap.)
    ``layers`` selects the optional layers on top:
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

        # Navigability, answered by walking. Sibling of the Laser Tag job, not
        # downstream of it: nothing about a firefight is an input to "is the
        # mission spine pathable, and can a body walk it".
        walktest_jid = job_id(brief.mission_id, _STAGE_WALKTEST, candidate=cand)
        plan.graph.add(Job(
            job_id=walktest_jid,
            mission_id=brief.mission_id,
            stage_id=_STAGE_WALKTEST,
            adapter_id="walktest",
            candidate_id=cand,
            resource_class="godot_headless",
            depends_on=[lot_jid],
            expected_outputs=["site_navqa.walktest.json"],
        ))

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
        # Pixelcoat builds the themed skins LIBRARY (one <kind>_<theme>/ pack per
        # curated material) that the Zoo kit resolves from; the pack set is
        # dynamic (per theme profile), so the adapter validates it, not a fixed
        # expected-output name.
        pixelcoat_jid = job_id(brief.mission_id, _STAGE_PIXELCOAT)
        plan.graph.add(Job(
            job_id=pixelcoat_jid, mission_id=brief.mission_id,
            stage_id=_STAGE_PIXELCOAT, adapter_id="pixelcoat",
            candidate_id=selected_candidate, resource_class="python_cpu",
            depends_on=[lot_jid],
            expected_outputs=[],  # <kind>_<theme>/ library; adapter checks
        ))
        # The Zoo structural kit is planned PER BUILDING, in the art_buildings
        # loop below -- it needs `art_lot`, which is not resolved until there.
        #
        # It was planned here, once per mission, on the belief that "the kit is
        # a module library resolved per slot". It is not. Every module except
        # `wallEnd` is `fit: exact`, built to ONE slot's dims, so a kit belongs
        # to the building whose slots produced it exactly as much as a dressing
        # bake belongs to the walls it was baked against.
        #
        # Measured 2026-08-09 (`module_extents.py --sweep`): every kit module
        # in every building of `lot_demo_001` is 3.300 m, against slots asking
        # 3.1 / 3.9 / 4.2 / 4.7 / 5.2 -- 3.300 being the MISSION SHELL's
        # storey, because one kit job was fed `shell.slots.json` and its output
        # dir was handed to all of them. A clean per-building rebuild of
        # `depot_a01` gives 5.200, so Zoo was never wrong. `wallEnd` -- the
        # 1x1x1 unit box, and the one module that genuinely IS shared -- is the
        # only species that measured correct in all seven buildings.
        #
        # This costs one Blender build per building instead of one per mission.
        # That is what the thing being per-building costs.
        # WHICH BUILDINGS THIS MISSION PLACES, and therefore how many times a
        # placement stage runs. `lot_for` is the one selection rule -- the
        # compose spec and the site spec call the same function -- so the jobs
        # planned here are for the buildings that actually get placed by
        # construction, not by two derivations that happen to agree.
        #
        # AN EMPTY LOT IS THE SINGLE-SHELL PATH: one unnamed building, job ids
        # with no archetype segment, `shell.patina.*` outputs, and a compose
        # dependency list of the same length and order as before. Every mission
        # that does not set `lot_library` plans byte-for-byte what it planned
        # before this existed.
        from packages.pipeline import building_library
        # THEMED, and it must be, because these are the ART jobs. This is the
        # THIRD caller of `lot_for`, after the compose spec and the themed site
        # spec, and it was missed when themed selection landed: the planner
        # fanned out a Zoo bake for an archetype the narrower pool does not
        # contain, and `_art_entry` raised "the planner and the spec builder
        # disagree about which buildings this mission places" -- its own guard,
        # firing exactly as written.
        #
        # `grep lot_for` over the package names all three call sites in one
        # command. Changing what a shared rule selects obliges you to run it.
        art_lot, _art_excluded = building_library.lot_for(
            getattr(brief, "lot_library", None),
            getattr(brief, "building_count", 1),
            selected_candidate,
            themed=True)
        # RAISES rather than filtering. A building whose light manifest is
        # missing dropping quietly out here would turn a five building brief
        # into a four building site with every stage reporting success -- the
        # failure already recorded in docs/WALKABLE_SITE.md.
        if art_lot:
            building_library.require_art_inputs(art_lot)
        art_buildings = art_lot or [None]

        zoo_dress_jids: list[str] = []
        zoo_kit_jids: list[str] = []
        for _entry in art_buildings:
            aid = _entry["id"] if _entry else None
            # Zoo structural kit for THIS building, from ITS slots, skinned by
            # the Pixelcoat pack library (which really is mission-wide: a skin
            # is a material, not a dimension).
            zoo_kit_jid = job_id(brief.mission_id, _STAGE_ZOO_KIT,
                                 archetype=aid)
            plan.graph.add(Job(
                job_id=zoo_kit_jid, mission_id=brief.mission_id,
                stage_id=_STAGE_ZOO_KIT, adapter_id="zoo",
                candidate_id=selected_candidate, archetype_id=aid,
                resource_class="blender",
                depends_on=[lot_jid, pixelcoat_jid],
                expected_outputs=[],  # zoo names by building_id at exec
            ))
            zoo_kit_jids.append(zoo_kit_jid)
            # Patina names its outputs from the INPUT STEM
            # (adapters/patina/__init__.py:42-48), so a job pointed at
            # `final_stand.glb` writes `final_stand.patina.*`. The contract has
            # to follow the input. `shell.patina.glb` was hardcoded here and was
            # only ever right because every art job was pointed at the mission's
            # own shell; an archetype id IS its file stem, by construction in
            # `building_library.index`.
            stem = aid or "shell"
            # Patina base cohesion pass.
            patina_base_jid = job_id(brief.mission_id, _STAGE_PATINA_BASE,
                                     archetype=aid)
            plan.graph.add(Job(
                job_id=patina_base_jid, mission_id=brief.mission_id,
                stage_id=_STAGE_PATINA_BASE, adapter_id="patina",
                candidate_id=selected_candidate, archetype_id=aid,
                resource_class="python_cpu",
                depends_on=[lot_jid],
                expected_outputs=[f"{stem}.patina.glb", f"{stem}.patina.json",
                                  f"{stem}.patina.gameplay.json"],
            ))
            # Patina dressing manifest.
            patina_dress_jid = job_id(brief.mission_id, _STAGE_PATINA_DRESS,
                                      archetype=aid)
            plan.graph.add(Job(
                job_id=patina_dress_jid, mission_id=brief.mission_id,
                stage_id=_STAGE_PATINA_DRESS, adapter_id="patina",
                candidate_id=selected_candidate, archetype_id=aid,
                resource_class="python_cpu",
                depends_on=[patina_base_jid],
                expected_outputs=[f"{stem}.patina.glb", f"{stem}.patina.json",
                                  f"{stem}.patina.gameplay.json",
                                  f"{stem}.patina.dressing.json"],
            ))
            # Zoo dressing build from the Patina manifest (collision-free).
            # Depends on ITS OWN patina_dressing and ITS OWN kit. The kit used
            # to be shared here, described as "a module library resolved per
            # slot" -- see the note above where it was planned. Both of this
            # job's inputs are now this building's.
            zoo_dress_jid = job_id(brief.mission_id, _STAGE_ZOO_DRESS,
                                   archetype=aid)
            plan.graph.add(Job(
                job_id=zoo_dress_jid, mission_id=brief.mission_id,
                stage_id=_STAGE_ZOO_DRESS, adapter_id="zoo",
                candidate_id=selected_candidate, archetype_id=aid,
                resource_class="blender",
                depends_on=[patina_dress_jid, zoo_kit_jid],
                expected_outputs=[],  # zoo names by building_id at exec; adapter checks
            ))
            zoo_dress_jids.append(zoo_dress_jid)
        # Named before the fixtures jobs are added, because compose depends on
        # them and is added first -- as it was when there was one.
        zoo_fixtures_jids = [
            job_id(brief.mission_id, _STAGE_ZOO_FIXTURES,
                   archetype=(_e["id"] if _e else None))
            for _e in art_buildings]
        # Presentation compose — THE step that makes --art mean "themed level".
        # Deli Counter is the source of collision truth, so its own composer
        # (portable_building -> themed_tscn) fits each themed Zoo module onto the
        # greybox slot footprint and keeps the greybox floors+collision as the
        # walkable base. Without this, Lux would light the raw greybox and --art
        # would ship a grey level (the contract gap this closes). Runs on DC's
        # bpy-free scene serializer, so it's pure-Python (no Blender/Godot).
        deli_sel_jid = job_id(brief.mission_id, _STAGE_DELI,
                              candidate=selected_candidate)
        compose_jid = job_id(brief.mission_id, _STAGE_COMPOSE)
        plan.graph.add(Job(
            job_id=compose_jid, mission_id=brief.mission_id,
            stage_id=_STAGE_COMPOSE, adapter_id="presentation",
            candidate_id=selected_candidate, resource_class="python_cpu",
            depends_on=[deli_sel_jid, *zoo_kit_jids,
                        *zoo_dress_jids, *zoo_fixtures_jids],
            expected_outputs=["presentation/site.tscn"],
        ))
        # Themed SITE assemble — Lot again, over the composed themed BUILDING.
        #
        # presentation_compose composes one building and names its output
        # site.tscn so the Lux stage can resolve it without knowing DC's
        # building_id. Everything downstream then read that name as the site,
        # and it is not: measured 2026-08-02, Lot's greybox spans ~150 m with
        # four buildings while the themed export spanned ~27 m with one
        # (roadmap 34). Lot already knows how to build a site out of scenes --
        # `_building_source` prefers `scene` over `glb` and instances both the
        # same way — so this asks it to, using the SAME placement the greybox
        # candidate was judged on. Cheap, because every building in the spec
        # points at one shell: there is a single themed scene to instance.
        themed_jid = job_id(brief.mission_id, _STAGE_THEMED_SITE)
        plan.graph.add(Job(
            job_id=themed_jid, mission_id=brief.mission_id,
            stage_id=_STAGE_THEMED_SITE, adapter_id="lot",
            candidate_id=selected_candidate, resource_class="python_cpu",
            depends_on=[compose_jid],
            expected_outputs=["site.tscn"],
        ))
        # Lux apply (final PS2 look) over the themed SITE — not the greybox
        # site, and not the single composed building it used to light.
        lux_jid = job_id(brief.mission_id, _STAGE_LUX)
        plan.graph.add(Job(
            job_id=lux_jid, mission_id=brief.mission_id,
            stage_id=_STAGE_LUX, adapter_id="lux",
            candidate_id=selected_candidate, resource_class="godot_headless",
            depends_on=[themed_jid],
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
        for _entry, zoo_fixtures_jid in zip(art_buildings, zoo_fixtures_jids):
            aid = _entry["id"] if _entry else None
            # The lights manifest an archetype bake reads is a LIBRARY file that
            # exists before the run, so this edge is the locked-candidate gate
            # rather than a data dependency. It is kept because the single-shell
            # path genuinely reads that job's `shell.lights.json`, and because a
            # placement bake for a mission that has not locked a shell is a bake
            # for a level nobody has chosen.
            plan.graph.add(Job(
                job_id=zoo_fixtures_jid, mission_id=brief.mission_id,
                stage_id=_STAGE_ZOO_FIXTURES, adapter_id="zoo",
                candidate_id=selected_candidate, archetype_id=aid,
                resource_class="blender",
                depends_on=[deli_sel_jid],
                expected_outputs=[],  # zoo names by scope_id at exec; adapter checks
            ))
            # The gate follows the bake. One gate over five bakes would either
            # take `depends_on[0]` and report the mission passed on the strength
            # of one building, or hold five reports in one job directory. A gate
            # that examines one of five and says nothing about the other four is
            # the failure mode this whole document is about.
            fixture_gate_jid = job_id(brief.mission_id, _STAGE_LUX_FIXTURE_GATE,
                                      archetype=aid)
            plan.graph.add(Job(
                job_id=fixture_gate_jid, mission_id=brief.mission_id,
                stage_id=_STAGE_LUX_FIXTURE_GATE, adapter_id="lux",
                candidate_id=selected_candidate, archetype_id=aid,
                resource_class="godot_headless",
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
