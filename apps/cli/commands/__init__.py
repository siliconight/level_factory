"""CLI command implementations (TDD 28).

Each command resolves the workspace, does the minimal orchestration, prints a
concise result, and returns a process exit code. Business logic lives in the
packages; commands are thin.
"""
from __future__ import annotations

import datetime as _dt
import json
import sys
from pathlib import Path

from packages.adapters.registry import AdapterRegistry
from packages.approvals import gates
from packages.artifacts.cache import ContentCache
from packages.core import states
from packages.core.canonical import pretty_dumps
from packages.core.hashing import hash_json
from packages.core.ids import export_build_dir_name, slugify
from packages.core.models import MissionBrief
from packages.jobs.scheduler import Scheduler
from packages.pipeline.planner import (
    TARGET_FUNCTIONAL_LOCK, TARGET_PRESENTATION, TARGET_SHELL_HANDOFF, plan_mission,
)
from packages.project_store.index import Index
from packages.project_store.workspace import Workspace, find_workspace, init_workspace
from packages.tools.doctor import run_doctor
from packages.validation.model import aggregate, issue_from_normalized, readiness_label

EXIT_OK, EXIT_FINDINGS, EXIT_BLOCKED = 0, 1, 2
EXIT_CONFIG, EXIT_TOOL, EXIT_INTERNAL = 3, 4, 5


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat()


def _ws(args) -> Workspace:
    return find_workspace(Path(args.chdir))


def _open_index(ws: Workspace) -> Index:
    return Index(ws.index_db)


def _cache(ws: Workspace) -> ContentCache:
    return ContentCache(ws.internal_dir / "cache")


# --------------------------------------------------------------------------
# Mission/batch resolution helpers
# --------------------------------------------------------------------------
def _find_mission(ws: Workspace, mission_id: str) -> tuple[str, dict]:
    """Return (batch_id, brief_dict) for a mission by scanning batches."""
    for batch_dir in sorted(ws.batches_dir.glob("*")):
        if not batch_dir.is_dir():
            continue
        brief_file = batch_dir / "missions" / mission_id / "brief" / "brief.json"
        if brief_file.exists():
            return batch_dir.name, ws.read_json(brief_file)
    raise SystemExit(f"mission '{mission_id}' not found in any batch")


def _load_batch(ws: Workspace, batch_id: str) -> dict:
    return ws.read_json(ws.batch_dir(batch_id) / "batch.json")


def _brief_model(brief: dict) -> MissionBrief:
    fields = {k: v for k, v in brief.items() if k in MissionBrief.__dataclass_fields__}
    fields.pop("schema", None)
    if "target_minutes" in fields and isinstance(fields["target_minutes"], list):
        fields["target_minutes"] = tuple(fields["target_minutes"])
    return MissionBrief(**fields)


# --------------------------------------------------------------------------
# Commands
# --------------------------------------------------------------------------
def cmd_init(args) -> int:
    root = Path(args.path).resolve()
    name = args.name or root.name
    project_id = args.project_id or slugify(name)
    ws = init_workspace(root, project_id=project_id, name=name)
    print(f"initialized workspace at {ws.root}")
    print(f"  project_id: {project_id}")
    print("  edit tools.local.json to point at your tool repositories, then run: level-factory doctor")
    return EXIT_OK


def cmd_doctor(args) -> int:
    ws = _ws(args)
    report = run_doctor(ws.load_tools_local(), ws.load_tools_lock(),
                        registry=AdapterRegistry())
    if args.json:
        print(pretty_dumps(report.as_dict()))
    else:
        for c in report.checks:
            print(f"  [{c.status:<14}] {c.name:<22} {c.detail}")
        print(f"\nworst: {report.worst}")
    return EXIT_OK if report.worst in ("PASS", "NOT_CONFIGURED", "WARN") else EXIT_CONFIG


def cmd_batch_create(args) -> int:
    ws = _ws(args)
    src = Path(args.batch_json)
    batch = json.loads(src.read_text(encoding="utf-8"))
    batch_id = batch["batch_id"]
    bdir = ws.batch_dir(batch_id)
    (bdir / "missions").mkdir(parents=True, exist_ok=True)
    (bdir / "approvals").mkdir(parents=True, exist_ok=True)
    (bdir / "reports").mkdir(parents=True, exist_ok=True)
    ws.write_json(bdir / "batch.json", batch)

    # Materialize each referenced brief into the mission tree.
    briefs_dir = src.parent / "briefs"
    created = []
    for mission_id in batch.get("missions", []):
        brief_src = briefs_dir / f"{mission_id}.json"
        if not brief_src.exists():
            print(f"  warning: brief for '{mission_id}' not found at {brief_src}",
                  file=sys.stderr)
            continue
        brief = json.loads(brief_src.read_text(encoding="utf-8"))
        mdir = ws.mission_dir(batch_id, mission_id)
        for sub in ("brief", "source", "candidates", "selected", "presentation",
                    "validation", "handoff", "history"):
            (mdir / sub).mkdir(parents=True, exist_ok=True)
        ws.write_json(mdir / "brief" / "brief.json", brief)
        created.append(mission_id)

    # Register the batch on the project.
    project = ws.load_project()
    if batch_id not in project.get("batches", []):
        project.setdefault("batches", []).append(batch_id)
        ws.write_json(ws.project_file, project)

    print(f"created batch '{batch_id}' with {len(created)} mission(s): {', '.join(created)}")
    return EXIT_OK


def _build_scheduler(ws: Workspace, index: Index) -> Scheduler:
    tools_local = ws.load_tools_local()
    return Scheduler(
        index=index,
        cache=_cache(ws),
        registry=AdapterRegistry(),
        jobs_dir=ws.jobs_dir,
        installation=tools_local,
    )


def _resolve_selected_candidate(ws: Workspace, mission_id: str) -> str | None:
    approval = gates.ApprovalStore(ws.internal_dir / "approvals").get(
        mission_id, gates.CANDIDATE_SELECTED
    )
    if approval and approval.decision == gates.DECISION_APPROVED:
        # The selected candidate id is stored in the approval notes payload.
        marker = ws.internal_dir / "approvals" / f"{mission_id}.selected"
        if marker.exists():
            return marker.read_text(encoding="utf-8").strip()
    return None


def _resolve_layers(args):
    """Resolve the composable layer set from CLI args. Explicit --art/--gameplay
    win; otherwise fall back to the legacy --target mapping; otherwise graybox.

    `--art` MEANS WHAT IT ALWAYS MEANT: art AND light. 0.35.0 split Lux's
    apply pass into its own layer, and if `--art` had quietly stopped
    producing lighting, every existing script saying `--art` would ship
    something different without anyone typing anything. `--unlit`
    subtracts the light layer; nothing subtracts it by default."""
    from packages.pipeline.planner import (
        LAYER_ART, LAYER_GAMEPLAY, LAYER_LIGHT, layers_for_target,
    )
    art = bool(getattr(args, "art", False))
    gameplay = bool(getattr(args, "gameplay", False))
    unlit = bool(getattr(args, "unlit", False))
    if art or gameplay:
        layers = set()
        if art:
            layers.add(LAYER_ART)
            if not unlit:
                layers.add(LAYER_LIGHT)
        if gameplay:
            layers.add(LAYER_GAMEPLAY)
        return frozenset(layers)
    target = getattr(args, "target", None)
    if target:
        return layers_for_target(target)
    return frozenset()  # bare `run` == graybox base


def _plan_for(ws: Workspace, mission_id: str, target: str, layers=None):
    batch_id, brief = _find_mission(ws, mission_id)
    batch = _load_batch(ws, batch_id)
    model = _brief_model(brief)
    selected = _resolve_selected_candidate(ws, mission_id)
    plan = plan_mission(
        model,
        seed_base=int(batch.get("seed_base", 0)),
        target=target or TARGET_SHELL_HANDOFF,
        layers=layers,
        selected_candidate=selected,
    )
    return batch_id, batch, model, plan


def cmd_plan(args) -> int:
    ws = _ws(args)
    _, _, _, plan = _plan_for(ws, args.mission_id, getattr(args, 'target', None),
                              layers=_resolve_layers(args))
    if args.json:
        print(pretty_dumps(plan.as_dict()))
    else:
        from packages.pipeline.planner import label_for_layers
        print(f"plan for {plan.mission_id} (output={label_for_layers(plan.layers)})")
        print(f"  candidates: {', '.join(plan.candidate_ids)}")
        if plan.selected_candidate:
            print(f"  selected:   {plan.selected_candidate}")
        for job in plan.graph.topological_order():
            deps = f" <- {', '.join(job.depends_on)}" if job.depends_on else ""
            print(f"  {job.job_id}  [{job.adapter_id}/{job.resource_class}]{deps}")
    return EXIT_OK


def _job_specs_for_plan(ws: Workspace, batch: dict, model: MissionBrief, plan) -> dict:
    """Map each planned job to the adapter job spec it needs to run."""
    specs: dict[str, dict] = {}
    jobs_dir = ws.jobs_dir

    # WHICH POOL THE GREYBOX PASS DRAWS FROM used to be decided here, by
    # reading `themed_site_assemble` off THIS INVOCATION'S planned graph.
    # Roadmap 48 measured what that cost: `batch create` plans no art layer
    # and drew from 123 shells, `run --art` plans one and drew from 98, and
    # the same job at the same seed produced two different buildings -- the
    # one every grader and the functional lock measured, and the one the
    # package would have shipped. The decision moved into `_write_site_spec`,
    # where it is keyed on the BRIEF (`lot_library`) and is therefore the same
    # answer in every invocation of the mission's life. Addendum item J.

    # ONE derivation per candidate. `_lot_for_compose` lists a directory and
    # prints what it excluded; with the placement stages fanned out there are
    # now twenty-odd jobs that need the same answer, and doing it per job would
    # list the library twenty times and say the same sentence twenty times.
    _lot_memo: dict[str, list] = {}

    def _lot_rows(candidate_id) -> list:
        cid = str(candidate_id)
        if cid not in _lot_memo:
            _lot_memo[cid] = _lot_for_compose(model, cid)
        return _lot_memo[cid]

    def _art_entry(job):
        """The library row for the building THIS job bakes, None if mission-wide.

        `job.archetype_id` was set by the planner from the same `lot_for` rule
        this reads, so a fanned job whose archetype is not in the candidate's lot
        means the planner and the spec builder disagree about which buildings the
        mission places. Refused rather than fallen back from: quietly using the
        mission's own shell instead is exactly the substitution being removed.
        """
        aid = getattr(job, "archetype_id", None)
        if not aid:
            return None
        row = next((a for a in _lot_rows(job.candidate_id)
                    if a.get("id") == aid), None)
        if row is None:
            raise RuntimeError(
                f"{job.job_id} is planned for archetype {aid!r}, which is not "
                f"in this candidate's lot -- the planner and the spec builder "
                f"disagree about which buildings this mission places")
        return row

    for job in plan.graph.topological_order():
        if job.adapter_id == "deli_counter":
            specs[job.job_id] = {
                "archetype": model.archetype,
                "mode": getattr(model, "mode", None) or "heist",
                "theme": model.theme or batch.get("theme_family", ""),
                "seed": int(job.candidate_id.rsplit("_", 1)[-1]),
                # Unique spec name per mission so parallel builds don't clash in
                # the DC repo's specs/ dir (DC writes specs there, not to work).
                "level_name": f"lf_{model.mission_id}",
            }
        elif job.adapter_id == "lot":
            seed = int(str(job.candidate_id).rsplit("_", 1)[-1])
            themed_scene = None
            if job.stage_id == "themed_site_assemble":
                # Same placement, themed geometry. The Deli Counter job is not
                # this job's dependency -- compose is -- so it is looked up by
                # candidate rather than taken from depends_on[0].
                compose_job = _dep(job, "presentation_compose")
                deli_job = next(
                    (j.job_id for j in plan.graph.jobs()
                     if j.adapter_id == "deli_counter"
                     and j.candidate_id == job.candidate_id), None)
                # A VARIED LOT publishes one scene per archetype under
                # presentation/lot/<id>/site.tscn. `_write_site_spec` switches
                # to the varied path on a MAPPING, so hand it one when the
                # brief asks for a varied lot and the single path otherwise.
                #
                # PATHS ARE CONSTRUCTED, NOT PROBED. Every spec in this
                # function is built BEFORE any job runs, so the compose output
                # does not exist yet -- an `.is_file()` here silently yielded
                # {} and the site placed the mission shell five times while
                # every archetype composed correctly beside it.
                #
                # Both stages call `_lot_for_compose`, which is one function
                # with one rule, not two derivations that happen to agree:
                # `pick_lot` is deterministic on (library, seed, count) and
                # the seed comes from this same candidate id.
                compose_out = _latest_output(jobs_dir / compose_job,
                                             "presentation")
                lot = _lot_rows(job.candidate_id)
                themed_scene = (
                    {a["id"]: str(compose_out / "lot" / str(a["id"])
                                  / "site.tscn") for a in lot}
                    if lot else str(compose_out / "site.tscn"))
            else:
                deli_job = job.depends_on[0]
            deli_out = jobs_dir / deli_job
            site_spec = _write_site_spec(
                ws, model, deli_out, seed=seed, themed_scene=themed_scene)
            specs[job.job_id] = {
                "site_spec_path": str(site_spec),
                # Written beside the spec by _write_site_spec. The adapter
                # plans a staging command against it before Lot runs.
                "staging_manifest_path": str(
                    Path(site_spec).parent / "packages.json"),
                "walkable": True,
                # Emit <stem>_navqa.tscn, the scene the walktest stage runs.
                # The Lot adapter has supported --navqa since it was written and
                # nothing had ever set the flag, so the nav QA scene was never
                # produced and the only navigation evidence in this pipeline
                # came from a firefight.
                # The nav QA scene is the greybox site's job. Re-baking it off
                # the themed site would judge navigation against geometry the
                # collision contract says is a VISUAL substitution, and the two
                # answers disagreeing would be a contract violation reported as
                # a nav finding.
                "navqa": not themed_scene,
                # Fingerprint inputs. The themed site's geometry is the composed
                # scene, so hashing shell.glb would miss every re-theme. A
                # varied lot has one scene PER BUILDING and every one of them
                # is geometry this site places -- flatten, or re-theming the
                # third building serves a stale site.
                "building_glbs": (
                    sorted(themed_scene.values())
                    if isinstance(themed_scene, dict)
                    else [themed_scene] if themed_scene
                    else [str(_latest_output(deli_out, "shell.glb"))]),
            }
        elif job.adapter_id == "walktest":
            lot_job = job.depends_on[0]
            lot_out = jobs_dir / lot_job
            repos = ws.load_tools_local().get("repositories", {})
            specs[job.job_id] = {
                "navqa_scene": str(_latest_output(lot_out, "site_navqa.tscn")),
                # walktest.py and the heist_nav_qa director both ship with Lot,
                # so the QA that judges a Lot site is always the version that
                # Lot built it with.
                "lot_repository": str(repos.get("lot", "")),
                "staging_dir": str(ws.internal_dir / "staging" / job.job_id),
                # walktest.py exits 1 when a leg is unpathable or a walker
                # stalls. That is a finding about the site, not a crash, and the
                # report is on disk to prove it ran -- so the job completes with
                # findings. A run that could NOT happen is a different thing
                # entirely: --require makes a missing Godot exit 1 with no
                # report, and the output contract fails the job for that.
                "exit_advisory": True,
            }
        elif job.adapter_id == "laser_tag":
            lot_job = job.depends_on[0]
            lot_out = jobs_dir / lot_job
            repos = ws.load_tools_local().get("repositories", {})
            lt_repo = Path(str(repos.get("laser_tag", "")))
            lot_repo = Path(str(repos.get("lot", "")))
            specs[job.job_id] = {
                "seed": int(job.candidate_id.rsplit("_", 1)[-1]),
                "run_count": 25,
                # THE MISSION'S ENCOUNTER, not Laser Tag's stock one. The
                # adapter has read `scenario_res` from this dict since it was
                # written and nothing ever set it, so every mission was graded
                # 1-versus-6 whatever its brief said.
                #
                # VALUES rather than a path, because `fingerprint_inputs`
                # already hashes `job_spec["scenario"]`: the numbers being here
                # means changing the encounter re-runs the evaluation. A path
                # would have fingerprinted the string while the file underneath
                # it moved.
                "scenario": {
                    "player_count": int(getattr(model, "crew_size", 1)),
                    "player_health": int(getattr(model, "crew_health", 5)),
                    "enemy_count": int(getattr(model, "enemy_count", 6)),
                    "enemy_health": int(getattr(model, "enemy_health", 2)),
                },
                # Already read by the staging hook injector and already in the
                # fingerprint; it just had no source but a default.
                "enemy_count": int(getattr(model, "enemy_count", 6)),
                # Laser Tag evaluates the walkable candidate scene.
                "evaluation_scene": str(_latest_output(lot_out, "site_walk.tscn")),
                "addon_dir": str(lt_repo / "addons" / "laser_tag_tool"),
                # The walkable scene references Lot's own runtime addon
                # (res://addons/lot/...), which ships under <lot_repo>/godot/.
                "extra_addon_dirs": [str(lot_repo / "godot" / "addons" / "lot")],
                "staging_dir": str(ws.internal_dir / "staging" / job.job_id),
                # Laser Tag is a readiness evaluator: a low/BROKEN grade exits
                # nonzero but is evidence, not a build failure. As long as it
                # produced its report, the job completes with findings.
                "exit_advisory": True,
            }
        elif job.adapter_id == "pixelcoat":
            # Build the whole themed skins library the Zoo kit resolves from:
            # one <kind>_<theme>/ pack per curated material in the building's
            # theme profile (profiles/themes/<theme>.json). The Zoo kit stage
            # below points --skins at this job's out/ and --theme at the same
            # theme, so the vocabulary a building wears IS its theme profile.
            specs[job.job_id] = {
                "theme": model.theme or batch.get("theme_family", "") or "delco",
            }
        elif job.adapter_id == "zoo":
            # Kit build depends on Lot(+Pixelcoat); dressing build depends on
            # Patina dressing(+Zoo kit); fixtures build consumes the locked
            # shell's lights manifest. Distinguish by stage id.
            if job.stage_id == "zoo_fixtures_build":
                # An archetype's lights manifest comes from the LIBRARY, where
                # it already exists; the mission's own shell reads the one its
                # Deli Counter job wrote. `building_library.index` carries the
                # path, and `require_art_inputs` has already refused the mission
                # if any picked building lacks one -- so this is a lookup, not a
                # probe with a fallback.
                entry = _art_entry(job)
                deli_job = _dep(job, "deli_generate") or job.depends_on[0]
                lights_path = (str(entry["lights"]) if entry
                               else str(_latest_output(jobs_dir / deli_job,
                                                       "shell.lights.json")))
                specs[job.job_id] = {
                    "mode": "fixtures",
                    "seed": int(str(job.candidate_id).rsplit("_", 1)[-1]),
                    "theme": model.theme or batch.get("theme_family", ""),
                    "lights_path": lights_path,
                    # A fixture build that fails IS a failure — hardware is
                    # load-bearing for the lighting contract, unlike kit
                    # module misses.
                }
            elif job.stage_id == "zoo_dressing_build":
                dress_job = _dep(job, "patina_dressing",
                                 getattr(job, "archetype_id", None))
                # The DRESSING build needs the same Pixelcoat library the KIT
                # build gets. Without it Zoo's material factory finds no pack
                # and every cover falls back to one flat colour: the shipped
                # dressing for category5_baie_dore_001 was 2255 meshes, 1
                # material, 0 images, while the walls they sit on carried a
                # real concrete_polished_casino pack. Pixelcoat's README draws
                # this line -- it "owns the themed skin library that Zoo kits
                # resolve against" -- so a cover gets its surface the same way
                # a wall does. Patina places; Pixelcoat skins.
                #
                # Found by candidate, not by walking depends_on like the kit
                # branch: this job depends on patina_dressing and zoo_kit, and
                # never directly on pixelcoat.
                pix_job = next(
                    (j.job_id for j in plan.graph.topological_order()
                     if j.adapter_id == "pixelcoat"
                     and j.candidate_id == job.candidate_id), None)
                specs[job.job_id] = {
                    "mode": "dress",
                    "seed": int(str(job.candidate_id).rsplit("_", 1)[-1]),
                    "theme": model.theme or batch.get("theme_family", ""),
                    "skins_dir": (str(_latest_output(jobs_dir / pix_job, "."))
                                  if pix_job else ""),
                    # Zoo --dress consumes Patina's <stem>.patina.dressing.json,
                    # and Patina takes that stem from its INPUT
                    # (adapters/patina/__init__.py:42-48). A dressing job for
                    # `final_stand.glb` therefore writes
                    # `final_stand.patina.dressing.json`; `shell` is the stem
                    # only for the mission's own shell.
                    "manifest_path": str(_latest_output(
                        jobs_dir / dress_job,
                        f"{getattr(job, 'archetype_id', None) or 'shell'}"
                        f".patina.dressing.json")),
                    # Zoo exits nonzero (2) when some modules fail to build but
                    # still writes its index and the modules that did build; the
                    # resolver falls back to base for the rest. That's a quality
                    # finding, not a crash — treat it as advisory.
                    "exit_advisory": True,
                }
            else:
                pix_job = _dep(job, "pixelcoat_build")
                # ITS OWN SLOTS. `_lot_slots` returns the MISSION SHELL's
                # slots, and while the kit was planned once per mission that
                # was the only manifest in play -- so every library building in
                # the lot wore modules cut to the mission shell's storey.
                # Measured 2026-08-09: 3.300 m in all eight buildings, against
                # slots asking 3.1 to 5.2. An archetype's slots come from the
                # LIBRARY row, the same lookup the fixtures branch above makes
                # for its lights manifest.
                entry = _art_entry(job)
                specs[job.job_id] = {
                    "mode": "kit",
                    "seed": int(str(job.candidate_id).rsplit("_", 1)[-1]),
                    "theme": model.theme or batch.get("theme_family", ""),
                    "slots_path": (str(entry["slots"]) if entry
                                   else str(_lot_slots(ws, jobs_dir, job))),
                    "skins_dir": (str(_latest_output(jobs_dir / pix_job, "."))
                                  if pix_job else ""),
                    "exit_advisory": True,
                }
        elif job.adapter_id == "patina":
            # The shell this pass treats. An archetype's greybox is the library
            # file the lot picked; the mission's own shell is what its Deli
            # Counter job built. Patina names every output from this path's
            # stem, so it also decides what the planner's expected_outputs say.
            entry = _art_entry(job)
            deli_glb = (str(entry["glb"]) if entry else
                        str(_latest_output(jobs_dir / _deli_for(plan, job),
                                           "shell.glb")))
            if job.stage_id == "patina_dressing":
                specs[job.job_id] = {
                    "input_glb": deli_glb,
                    "art_mode": "vertex-color",
                    # Patina validates themes against its builtins ("default",
                    # "delco_1997_gas_station") and errors hard on unknowns, so
                    # pass an explicit patina_theme if the brief sets one, else
                    # the always-present "default". (theme_family is for the
                    # other tools; it is NOT a valid patina theme name.)
                    "theme": getattr(model, "patina_theme", "") or "default",
                    "dressing": True,
                    "panel_size": 1.2, "panel_gap": 0.03,
                }
            else:
                specs[job.job_id] = {
                    "input_glb": deli_glb,
                    "art_mode": "vertex-color",
                    "theme": getattr(model, "patina_theme", "") or "default",
                }
        elif job.adapter_id == "presentation":
            # Compose the themed scene with DC's own collision-fit composer.
            # Inputs: DC slots + gameplay + greybox glb (collision truth), and
            # the themed Zoo kit modules that fill the slots.
            repos = ws.load_tools_local().get("repositories", {})
            deli_out = jobs_dir / _deli_for(plan, job)

            def _layer_paths(stage: str, suffix: str) -> dict:
                """``{archetype_id or "": out_dir}`` -- where each building's
                CONTENT LAYER will be, once its job has run.

                A DIRECTORY, and constructed from a job id rather than found on
                disk. This globbed for the file itself and returned `""` when it
                found nothing -- and it always found nothing, because this whole
                function runs BEFORE ANY JOB EXECUTES. Measured 2026-08-06: five
                composed buildings, zero `--dressing` flags, and a probe
                reporting no Dressing node anywhere. It had appeared to work only
                while a previous run's artifact happened to be sitting in a
                stable out dir for the glob to find.

                The adapter resolves the file inside this directory at execution
                time, when the producing job has finished. See
                docs/WALKABLE_SITE.md's rule: paths are constructed, not probed.

                The dressing and fixtures GLBs the composed scene instances
                (props + light-fixture hardware). A bake is a PLACEMENT against
                one specific shell's walls and roof, so the building it was
                built for is the key. This used to take `hits[-1]` -- whichever
                filename sorted last -- from whichever dependency matched first,
                and hand it to every building: measured 2026-08-06, one
                30.4 x 8.4 x 22.4 dressing box inside five shells whose
                footprints ran from 26.1 x 20.3 to 46.3 x 26.3.

                Keyed off the JOB's archetype rather than parsed back out of the
                filename, because reconstructing ids from strings is already the
                fragile part of this codebase.

                Several layers of one kind in one job dir is refused rather than
                resolved: one bake is one placement against one shell, so there
                is no basis for preferring one of them.
                """
                deps = set(job.depends_on)
                found: dict[str, str] = {}
                for dep in plan.graph.jobs():
                    if dep.job_id not in deps or dep.stage_id != stage:
                        continue
                    found[getattr(dep, "archetype_id", None) or ""] = str(
                        jobs_dir / dep.job_id / "out")
                return found

            dressing_glb = _layer_paths("zoo_dressing_build", "_dressing.glb")
            fixtures_glb = _layer_paths("zoo_fixtures_build", "_fixtures.glb")
            # THE KIT IS A LAYER TOO, and it took until 2026-08-09 to say so.
            # This was `_dep(job, "zoo_kit_build")` -- one job's output dir,
            # handed to every building's compose -- which is the identical
            # shape as the `hits[-1]` dressing defect described above, still
            # standing after that one was fixed, because a kit was believed to
            # be a shared library rather than a per-building bake.
            modules_dir = _layer_paths("zoo_kit_build", "")
            specs[job.job_id] = {
                # THE LOT IS CHOSEN HERE AND ONLY HERE. `pick_lot` is
                # deterministic on (library, seed, count), so `_write_site_spec`
                # calling it again would agree -- by luck, until someone
                # changes a signature. It reads the ids back off this compose's
                # own output instead. See docs/VARIED_THEMED_LOT.md.
                "lot_archetypes": _lot_rows(job.candidate_id),
                "deli_repo": str(repos.get("deli_counter", "")),
                "slots_path": str(_latest_output(deli_out, "shell.slots.json")),
                "gameplay_path": str(_latest_output(deli_out, "shell.gameplay.json")),
                "greybox_glb": str(_latest_output(deli_out, "shell.glb")),
                "modules_dir": modules_dir,
                "dressing_glb": dressing_glb,
                "fixtures_glb": fixtures_glb,
                "theme": model.theme or batch.get("theme_family", "") or "delco",
                "style": 1,
                # A partial kit (some slots keep greybox) is a quality finding,
                # not a crash — the composer still emits a complete walkable scene.
                "exit_advisory": True,
            }
        elif job.adapter_id == "lux":
            if job.stage_id == "lux_fixture_gate":
                repos = ws.load_tools_local().get("repositories", {})
                lux_repo = Path(str(repos.get("lux", "")))
                gate_driver = (Path(__file__).resolve().parents[3]
                               / "assets" / "godot" / "run_fixture_gate.gd")
                specs[job.job_id] = {
                    "mode": "fixture_gate",
                    "fixtures_dir": str(jobs_dir / job.depends_on[0]),
                    "addon_dir": str(lux_repo / "addons" / "lux"),
                    "driver_src": str(gate_driver),
                    "staging_dir": str(ws.internal_dir / "staging" / job.job_id),
                }
                continue
            # Lux now lights the COMPOSED themed presentation scene (DC's
            # collision-fit composer output), not the raw greybox site. This is
            # the fix for the --art contract: the compose stage produces
            # <compose>/presentation/site.tscn with the themed modules on DC's
            # collision, and Lux lights THAT.
            themed_job = _dep(job, "themed_site_assemble")
            compose_job = _dep(job, "presentation_compose")
            lot_job = next((j.job_id for j in plan.graph.jobs()
                            if j.stage_id == "lot_assemble"
                            and j.candidate_id == job.candidate_id), None)
            if themed_job:
                # The themed SITE: Lot's assembly of the composed building at
                # the candidate's own placements. Lighting the composed building
                # instead put one LuxRoot over one building and called it a
                # level (roadmap 29/34).
                composed_scene = _latest_output(jobs_dir / themed_job,
                                                "site.tscn")
            elif compose_job:
                composed_scene = _latest_output(jobs_dir / compose_job,
                                                "presentation/site.tscn")
            else:  # graybox-only fallback (should not happen under LAYER_ART)
                composed_scene = _latest_output(jobs_dir / lot_job, "site.tscn")
            repos = ws.load_tools_local().get("repositories", {})
            lux_repo = Path(str(repos.get("lux", "")))
            lot_repo = Path(str(repos.get("lot", "")))
            driver = Path(__file__).resolve().parents[3] / "assets" / "godot" / "run_lux_apply.gd"
            specs[job.job_id] = {
                "preset": _preset_for(model),
                "quality_tier": "standard",
                "composed_scene": str(composed_scene),
                "addon_dir": str(lux_repo / "addons" / "lux"),
                "extra_addon_dirs": [str(lot_repo / "godot" / "addons" / "lot")],
                "driver_src": str(driver),
                "staging_dir": str(ws.internal_dir / "staging" / job.job_id),
            }
        elif job.adapter_id == "dispatch":
            dep = job.depends_on[0]
            # Prefer the Lot site for the dispatch spec inputs regardless of
            # whether dispatch depends on Lot (functional) or Lux (presentation).
            lot_job = next((j.job_id for j in plan.graph.jobs()
                            if j.stage_id == "lot_assemble"
                            and j.candidate_id == job.candidate_id), dep)
            lot_out = jobs_dir / lot_job
            deli_out = jobs_dir / _deli_for(plan, job)
            spec_path = _write_dispatch_spec(ws, model, lot_out, deli_out)
            specs[job.job_id] = {
                "mission_spec_path": str(spec_path),
                "mode": "shell-handoff",
            }
    return specs


def _dep(job, stage: str, archetype: str | None = None) -> str | None:
    """The ONE dependency of ``job`` in ``stage``, or None.

    `next((d for d in job.depends_on if "<stage>" in d), None)` returns the
    FIRST match and drops the rest without a word. That was correct while every
    art stage was planned once per mission. The stages that bake a PLACEMENT now
    run once per building, and a resolver that takes whichever id happens to
    come first hands one building's props to all of them -- which is the defect,
    reintroduced one layer down.

    So: narrow by archetype when the caller has one, and REFUSE when more than
    one survives. A caller with several candidates and no way to choose between
    them does not have a default; it has a bug.
    """
    hits = [d for d in job.depends_on if f".{stage}" in d]
    if archetype:
        hits = [d for d in hits if d.endswith(f".{archetype}")]
    if len(hits) > 1:
        raise RuntimeError(
            f"{job.job_id} has {len(hits)} '{stage}' dependencies "
            f"({', '.join(hits)})"
            + (f" for archetype {archetype!r}" if archetype else
               " and no archetype to choose between them"))
    return hits[0] if hits else None


def _lot_slots(ws: Workspace, jobs_dir: Path, job) -> Path:
    """Slots.json for a presentation job's selected candidate (from the DC job)."""
    seed = str(job.candidate_id).rsplit("_", 1)[-1]
    deli_job = f"{job.mission_id}.deli_generate.candidate.seed_{seed}"
    return _latest_output(jobs_dir / deli_job, "shell.slots.json")


def _deli_for(plan, job):
    seed = str(job.candidate_id).rsplit("_", 1)[-1]
    return f"{job.mission_id}.deli_generate.candidate.seed_{seed}"


def _preset_for(model: MissionBrief) -> str:
    # Lux registers presets under their DISPLAY names ("Blue Hour"), not
    # resource stems — a wrong name makes blend_to_preset a silent no-op
    # (proven on hardware in the lux visual pass). Registered library:
    # Delco Summer Afternoon / Delco Arcade / Gas Station Fluorescent /
    # Blue Hour / Heavy Rain / Mission Goes Hot.
    tod = (model.time_of_day or "").lower()
    if tod in ("night", "evening"):
        return "Blue Hour"
    if tod == "afternoon":
        return "Delco Summer Afternoon"
    return "Gas Station Fluorescent"


def _lot_for_compose(model, candidate_id) -> list:
    """Archetypes a varied themed lot must compose, [] for the single shell.

    A varied lot is opt-in (`lot_library` on the brief) and only means
    anything when the brief asks for more than one building. Everything this
    needs is pure -- `building_library` is a directory listing and
    arithmetic -- so it runs at spec time with no workspace and no Godot.
    """
    from packages.pipeline import building_library
    # THEMED. Both callers of this function build a themed spec -- the
    # presentation compose's `lot_archetypes` and `themed_site_assemble`'s
    # scene map -- so the pool is the shells that can carry a theme, and a
    # library too small for the brief refuses HERE rather than composing a
    # short row that every stage then reports as a success. The greybox site
    # spec does not come through this function.
    lot, incomplete = building_library.lot_for(
        getattr(model, "lot_library", None),
        getattr(model, "building_count", 1),
        candidate_id,
        themed=True)
    if incomplete:
        # Same voice as the site builder: a silently shorter library is how a
        # lot quietly stops being varied.
        print(f"[compose] {len(incomplete)} archetype(s) not themeable "
              f"(incomplete manifest): "
              + ", ".join(e["id"] for e in incomplete[:5]))
    return lot


def _latest_output(job_root: Path, name: str) -> Path:
    """Path to a job's published output in its stable ``out/`` dir.

    The scheduler links every successful job's collected outputs into
    ``<jobs_dir>/<job_id>/out/`` so downstream jobs resolve them without
    knowing the attempt number.
    """
    return job_root / "out" / name


def _write_dispatch_spec(ws: Workspace, model: MissionBrief,
                         lot_out: Path, deli_out: Path) -> Path:
    """Stage DC + Lot outputs into Dispatch's required input trees, then write a
    valid dispatch.mission.v0.2 spec pointing at the staged manifests.

    The mission-objective layer is OPTIONAL in this pipeline (the model is just a
    shell for the gameplay team), so mission_flow is minimal and the validation
    block relaxes objective/runtime requirements — the deliverable is the
    collision shell + nav + packaging, not a fabricated mission.
    """
    from packages.staging.dispatch_inputs import stage_dispatch_inputs

    stage_dir = ws.internal_dir / "temp" / model.mission_id / "dispatch_inputs"
    manifests = stage_dispatch_inputs(
        stage_dir,
        deli_gameplay=_latest_output(deli_out, "shell.gameplay.json"),
        shell_glb=_latest_output(deli_out, "shell.glb"),
        lot_gameplay=_latest_output(lot_out, "site.site.gameplay.json"),
        mission_id=model.mission_id,
        theme=model.theme or "",
    )
    spec = {
        "schema": "dispatch.mission.v0.2",
        "mission_id": model.mission_id,
        "title": model.display_name or model.mission_id,
        "engine": "godot_4_7",
        "mode": "online_coop_pve",           # gameplay mode (NOT the build mode)
        "players": {"min": 1, "max": 4, "preferred": 4},
        "networking": {"model": "server_authoritative", "critical_state_owner": "server"},
        "theme": model.theme or "",
        "inputs": {
            "deli_counter": manifests["deli_counter"],
            "lot": manifests["lot"],
        },
        # Minimal, non-binding flow: just enough to be a valid spec. The gameplay
        # team authors the real objectives inside the shell.
        "mission_flow": [
            {"step": "spawn", "location_tag": "mission_start"},
            {"step": "extract", "location_tag": "extraction"},
        ],
        "validation": {
            "require_online_runtime_readiness": False,
            "require_all_objectives_reachable": False,
            "require_all_players_spawn_valid": True,
            "require_ai_navmesh": False,
            "require_performance_budget": False,
        },
    }
    dest = stage_dir / "dispatch.mission.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(pretty_dumps(spec), encoding="utf-8")
    return dest


def _write_site_spec(ws: Workspace, model: MissionBrief, deli_out: Path,
                     *, seed: int, themed_scene: str | None = None) -> Path:
    """Write ONE candidate's Lot site spec (named 'site.json' so Lot's stem-based
    outputs are canonical: site.tscn / site_walk.tscn / site.site.gameplay.json).

    The destination is per-CANDIDATE, and that is the whole point. It used to be
    per-mission, so every candidate's spec was written to the same path during
    planning and the last one written won: all N Lot jobs read one spec and
    produced byte-identical sites. The pipeline offered five choices that were
    one choice, and nothing noticed because nothing compared two candidates.

    Placement comes from ``site_variation``, keyed on the candidate seed. Deli
    Counter is deterministic by design (no --seed flag), so the site assembly is
    where candidates are supposed to diverge — per-building yaw, along-row nudge
    and across-row stagger, plus which building carries spawn / objective /
    extraction. Those role keys were never set either, so every candidate put the
    player down on Lot's origin default.

    Matches the REAL Lot 0.18 schema: a top-level ``name`` (Lot reads
    site_spec["name"]) and per-building placement ``at`` [x, y] + ``rot`` (yaw
    degrees). Extra keys Lot ignores (site_shape/route_shape/target_minutes) are
    kept for LF's own readers.
    """
    from packages.pipeline import site_variation
    from packages.pipeline.site_variation import (
        STREET, ground_size, row_spacing, shell_footprint, site_placements)

    count = max(1, int(getattr(model, "building_count", 1) or 1))
    glb = str(_latest_output(deli_out, "shell.glb"))
    gameplay = str(_latest_output(deli_out, "shell.gameplay.json"))

    # WHERE EACH BUILDING COMES FROM, beside where the spec will name it.
    #
    # The spec's geometry refs are relative to the site's own out dir, because
    # Lot writes each ext_resource as os.path.join(glb_dir, src) with
    # glb_dir=".": an absolute src passes straight through and ships as
    # res://C:/..., which is a request for a folder named "C:" inside the
    # consumer's project. So the spec says "lot/<id>/site.tscn" and a staging
    # step run before Lot puts the package there.
    #
    # These are ABSOLUTE and stay absolute. They are build inputs, not
    # deliverables -- the staging step reads them and the fingerprint watches
    # them, and neither of those happens inside a Godot project.
    #
    # CONSTRUCTED, NOT PROBED, for the same reason the rest of this function
    # is: it runs while the plan is built, before any compose job has produced
    # anything. Nothing here may ask whether a source exists in order to decide
    # what to do; the staging step refuses at run time if one is missing.
    staged_packages: dict[str, str] = {}
    staged_glbs: dict[str, str] = {}

    # A LOT OF DIFFERENT BUILDINGS, when the brief asks for one. Roadmap 37:
    # this function measured ONE shell and gave it N placements, so a
    # four-building site was one building four times and stairs and ladders
    # landed identically in every one. Deli Counter ships 103 complete
    # archetypes across 41 families; the site spec was asking for one thing.
    #
    # OPT-IN, and dormant until a brief sets `lot_library`. Existing missions
    # keep the single-shell row byte-for-byte -- re-placing a level that has
    # already been evaluated would be a different level wearing the same grade.
    #
    # GREYBOX ONLY, for now. `themed_scene` is ONE composed scene for the whole
    # site, so a varied THEMED lot needs one compose job per archetype (roadmap
    # 41 step 4). Selecting varied greybox buildings and then dressing them all
    # as the same themed scene would be a worse lie than the one it replaces,
    # so the themed path deliberately keeps the single shell until that lands.
    # `themed_scene` is EITHER one composed scene for the whole site (the
    # historical single-shell path) OR a mapping {archetype_id: scene} for a
    # varied lot, where each building is dressed as itself. One string cannot
    # express the second: five buildings all pointed at one themed scene would
    # place five different greyboxes and then dress them identically, which is
    # a worse lie than the repetition it replaces.
    themed_map = themed_scene if isinstance(themed_scene, dict) else None
    lot = []
    library = getattr(model, "lot_library", None)
    if library and (themed_map or not themed_scene):
        from packages.pipeline import building_library
        complete, incomplete, non_source = building_library.index(library)
        if incomplete:
            print(f"[site] {len(incomplete)} archetype(s) excluded from the lot "
                  f"for a missing manifest: "
                  + ", ".join(e["id"] for e in incomplete[:5]))
        if non_source:
            # A DIFFERENT SENTENCE FROM THE ONE ABOVE, and it has to be. These
            # are not archetypes with a hole in them; they are this pipeline's
            # own composed output and Deli Counter's facades, sitting in the
            # source library because `deli_counter/build/` is both the source
            # and the sink. Printing them as "a missing manifest" would send
            # somebody to rebuild a file that should never have been indexed.
            print(f"[site] {len(non_source)} entr(y/ies) in {library} are not "
                  f"source archetypes and were not offered to the lot: "
                  + ", ".join(e["id"] for e in non_source[:5]))
        # THE FOURTH LINE, and the one that was missing. The three above
        # describe what the library CONTAINS; this one describes whether any of
        # it is current. On 2026-08-12 all three printed over a library 4.2
        # days behind its code, and every gate downstream -- nav, walk, Laser
        # Tag, the export, a human's eyes -- graded geometry Deli Counter no
        # longer produces.
        #
        # Reported, not enforced. LF cannot rebuild somebody else's library,
        # and a gate that blocks without being able to fix anything is a gate
        # that gets worked around. Both commands are named so the next line
        # after this one is the fix.
        stale, worst_days = building_library.stale_shells(library)
        if stale:
            print(f"[site] STALE LIBRARY: {len(stale)} shell(s) in {library} "
                  f"are older than the code that builds them (worst "
                  f"{worst_days:.1f} days). Every gate below is grading "
                  f"geometry this code no longer produces.")
            print(f"[site]   name them:  python build_freshness.py --list"
                  f"   (in Deli Counter)")
            print(f"[site]   rebuild:    python build.py --all")

        # THE NARROWING, AND IT IS NOT CONDITIONAL ANY MORE. Roadmap 48.
        #
        # The themed pool is narrower, and it must be the SAME narrowing
        # `_lot_for_compose` applied: compose published one scene per
        # archetype and `themed_map` is keyed on those ids. A wider pool here
        # selects buildings that have no composed scene, `_source` finds no
        # match, and the row stands as greybox with every stage reporting
        # success -- the defect this file keeps finding, one layer down.
        #
        # IT USED TO BE GATED ON A PER-INVOCATION FLAG read off the planned
        # graph. That gate was itself a fix: `probe_pool_divergence.py` had
        # measured that across lot_demo_001's three candidates, 14 of 15
        # building slots already carried an archetype other than the one Laser
        # Tag graded and 13 graded archetypes never shipped at all, so the
        # greybox branch started narrowing too -- "grade the pool that ships".
        #
        # It made the greybox pass and the themed pass agree WITHIN one
        # invocation, and could not make them agree ACROSS invocations:
        # `batch create` plans no `themed_site_assemble`, so it drew from 123
        # shells while `run --art` drew from 98, and `batch create` is where
        # the graders, the structural checks and the functional lock all run.
        # Roadmap 48 caught it on unlit_probe_001 -- cr_garage graded,
        # landmark_hall_a03 shipped, one job id, one seed -- and it was the
        # functional lock that refused the export, because nothing else in the
        # pipeline can see both sites.
        #
        # SO IT IS KEYED ON THE BRIEF. Reaching this line already means
        # `lot_library` is set, which is also what gates the art layer, so the
        # pool a mission draws from is now the same in every invocation of its
        # life -- before approval, after approval, graded, shipped.
        #
        # THE COST, STATED: a brief that sets `lot_library` and is never run
        # with `--art` now draws from the narrower pool as well. It buys back
        # nothing and loses 25 of 123 shells of variety. That is the price of
        # the draw not moving, and it is the cheaper side of the trade -- a
        # graybox deliverable with less variety is a worse level; a graded
        # level that is not the shipped level is not a level at all.
        before = len(complete)
        complete = building_library.require_themed_shells(complete, count)
        which = "themed lot" if themed_map else "graded lot"
        print(f"[site] {which}: {len(complete)} of {before} shell(s) "
              f"can carry a theme -- keyed on the brief, so this is the same "
              f"pool in every invocation")
        lot = building_library.pick_lot(complete, seed, count)
        if len(lot) < count:
            # Loud, not silent. A short lot means the library is smaller than
            # the brief asked for, and a site quietly missing buildings is the
            # shape of defect this file keeps finding.
            print(f"[site] the library offers {len(lot)} building(s) for a lot "
                  f"of {count} -- the row will be short")

    if lot:
        footprints = building_library.footprints_for(lot, shell_footprint)
        placed = site_placements(seed, len(lot), footprints=footprints,
                                 shape=model.site_shape)
        # `scene` when this archetype has been composed, `glb` otherwise --
        # never both, same rule as the single-shell path. A lot part-way
        # through the art pass therefore stands its themed buildings themed and
        # its untouched ones as greybox, rather than failing or silently
        # dressing one as another.
        def _source(entry):
            aid = str(entry["id"])
            scene = (themed_map or {}).get(entry["id"])
            if scene:
                # The package is the composed scene's whole DIRECTORY: site.tscn
                # is useless without the site_base.glb and art/ beside it, every
                # one of which it references as res://<name> rooted at that
                # package.
                staged_packages[aid] = str(Path(scene).parent)
                return {"scene": f"lot/{aid}/site.tscn"}
            staged_glbs[aid] = str(entry["glb"])
            return {"glb": f"buildings/{aid}.glb"}

        buildings = [
            {"id": f"b{i}", **_source(e), "gameplay": e["gameplay"],
             "archetype": e["id"],
             "at": p["at"], "rot": p["rot"]}
            for i, (e, p) in enumerate(zip(lot, placed["buildings"]))
        ]
        span_x, span_y = ground_size(len(lot), footprints=footprints,
                                     shape=model.site_shape)
        footprint = None            # the row is measured per building now
    else:
        # Measure the shell once: the spacing between origins and the size of
        # the plate under them are both consequences of how big the building
        # is. Spacing was a hardcoded 45 m while the shells were 44 m wide, so
        # a candidate whose nudges closed the gap assembled two buildings
        # inside each other.
        footprints = None
        footprint = shell_footprint(glb)
        spacing = row_spacing(footprint)
        placed = site_placements(seed, count, spacing=spacing)
        # `scene` when the themed building exists, `glb` otherwise -- never
        # both. Lot prefers `scene` and warns when a building carries both, and
        # the warn would fire once per building for no information: the choice
        # is made here. The placement is IDENTICAL either way, deliberately.
        # The greybox site is the one the candidate was judged on, so a themed
        # site that stood its buildings anywhere else would be a different
        # level wearing the same evaluation.
        # Same defect, same fix, on the path that predates the varied lot: this
        # one has been emitting res://C:/ for as long as it has existed.
        if themed_scene and not themed_map:
            staged_packages["shell"] = str(Path(themed_scene).parent)
            source = {"scene": "lot/shell/site.tscn"}
        else:
            staged_glbs["shell"] = glb
            source = {"glb": "buildings/shell.glb"}
        buildings = [
            {"id": f"b{i}", **source, "gameplay": gameplay,
             "at": p["at"], "rot": p["rot"]}
            for i, p in enumerate(placed["buildings"])
        ]
        # Size the plate from the shell that is going to stand on it.
        span_x, span_y = ground_size(count, spacing=spacing, footprint=footprint)
    count = len(buildings)
    spec = {
        # Lot names its outputs from this field (site.tscn / site_walk.tscn /
        # site.site.gameplay.json), so it must be the canonical LF stem "site",
        # NOT the mission id — mission identity lives in the job/candidate ids.
        "name": "site",
        "ground": {"size_x": span_x, "size_y": span_y},
        "buildings": buildings,
        # Roads. Without these the site graph has no edges: Lot reported
        # "isolated buildings: b0, b2, b3" and "objective approaches: 0"
        # on a four-building site, because nothing had told it the
        # buildings are connected. cater's hand-authored specs carried
        # paths/courtyards/perimeter and the generated ones carried none;
        # the placement half came across and the connectivity half did
        # not. Roadmap item 29.
        #
        # Consecutive neighbours, because site_placements lays the row out
        # in index order along x -- b0..bN are already physically adjacent,
        # and a chain is the smallest edge set that leaves no island. The
        # mission spine may hop non-adjacent buildings; a connected chain
        # means every pair is still reachable.
        #
        # Width is STREET, not a number chosen here: that constant IS the
        # clear ground the placement reserves between two shells, so the
        # path fills the gap the layout already made for it. Two sides of
        # one contract asking for the same thing, the way CLEARANCE and
        # Lot's own CLEARANCE already do.
        "paths": [{"from": f"b{i}", "to": f"b{i + 1}", "width": STREET}
                  for i in range(count - 1)],
        # Closes the site. Lot lays four perim_ walls around the ground
        # rect; without them a walker can leave the plate entirely. Three
        # metres clears the 1.8 m standing body from agent_contract.json
        # by enough to read as a wall rather than a parapet, and is far
        # above agent_max_climb -- the same height cater used.
        "perimeter": {"height": 3},
        # NO courtyards, deliberately. A courtyard is a designed open
        # space and there is nothing here to derive its position from;
        # emitting one at an arbitrary point would be a number nobody
        # chose, dressed as a decision. It stays absent until something
        # in the brief or the route says where one belongs.
        # HOW MANY PEOPLE ARRIVE. Lot writes one `LT_PlayerSpawn` per crew
        # member from this, because Laser Tag drops every one of them on
        # `player_spawns[i % size()]` -- one hook and a crew of four is four
        # capsules inside each other, which graded 10/BROKEN with zero shots
        # fired. The spec is the contract between the brief and Lot, so the
        # number travels here rather than as a new function parameter.
        "crew_size": int(getattr(model, "crew_size", 1) or 1),
        # Building ids Lot resolves into the walkable scene's spawn_pos /
        # objective_pos / extraction_pos.
        "spawn": placed["spawn"],
        "objective": placed["objective"],
        "extraction": placed["extraction"],
        # LF-only metadata (ignored by Lot, read by LF's own tooling):
        "schema": "lot.site.v0.18",
        "site_id": model.mission_id,
        "candidate_seed": int(seed),
        "site_shape": model.site_shape,
        "route_shape": model.route_shape,
        "target_minutes": list(model.target_minutes),
    }
    # Self-check before the spec leaves the building. This can only fire if the
    # placement and the plate in site_variation have drifted apart, which is
    # exactly what happened for the whole life of the module: a row marching out
    # along +x under a plate centred on the origin, and a coverage test with a
    # fudge factor in the assertion that let it pass. A guardrail nobody runs is
    # decoration, so it runs here, on the real seed, on every write.
    faults = (site_variation.uncovered(spec, footprint, footprints=footprints)
              + site_variation.overlapping(spec, footprint, footprints=footprints))
    if faults:
        raise RuntimeError(
            "site_variation placed a row its own ground plate and spacing cannot "
            "carry — this is a bug in the pipeline, not in the brief:\n  - "
            + "\n  - ".join(faults))
    # One directory per candidate; the filename stays "site.json" so the Lot
    # adapter's stem and Lot's spec["name"]-derived output names stay canonical.
    # The themed spec is a separate file IN ITS OWN DIRECTORY, and the
    # directory is what varies -- the filename must stay "site.json".
    #
    # The Lot adapter derives its expected output names from the SPEC FILE's
    # stem (`_stem` -> Path(site_spec_path).stem) while Lot itself names its
    # outputs from spec["name"]. Calling the themed spec site_themed.json made
    # the adapter expect site_themed.tscn, Lot wrote site.tscn, the job failed
    # on a missing expected output, and lux_apply failed behind it. Two naming
    # authorities over one file, and only one of them was asked.
    #
    # Separate at all because overwriting the greybox spec would leave that job
    # unable to re-run from its own inputs -- a spec describing a different site
    # than the run that used it is the provenance trap roadmap 33 is about.
    dest = (ws.internal_dir / "temp" / model.mission_id
            / f"candidate_seed_{int(seed)}"
            / ("themed" if themed_scene else "")
            / "site.json")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(pretty_dumps(spec), encoding="utf-8")

    # The staging manifest, beside the spec it belongs to. Separate file rather
    # than extra keys in the spec because Lot reads the spec and this is not
    # Lot's business -- and because a spec that carried absolute source paths
    # would be exactly the artifact this change exists to stop shipping.
    #
    # `gameplay` refs stay absolute in the spec on purpose. They are read by
    # merge_gameplay at build time and never appear in any emitted scene, so
    # they are a build input like these are, and keeping them resolvable is
    # what lets fingerprint_inputs keep watching them.
    repos = ws.load_tools_local().get("repositories", {})
    lot_repo = str(repos.get("lot", ""))
    manifest = {
        "packages": staged_packages,
        "glbs": staged_glbs,
        # Lot's walk scene, asked for portably, names these bare at the site
        # root rather than under addons/lot/ -- so the pack never has to claim
        # an addons/ directory inside somebody else's project.
        "addon_dir": (str(Path(lot_repo) / "godot" / "addons" / "lot")
                      if lot_repo else ""),
    }
    (dest.parent / "packages.json").write_text(
        pretty_dumps(manifest), encoding="utf-8")
    return dest


# A known-valid 1x1 opaque PNG, so a recipe always resolves a source even when
# the shared texture library has none (the real tool needs a readable image).
_ONE_PX_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108020000009077"
    "53de0000000c4944415478da63f8cfc0f01f0005000155a2b4e10000000049454e44ae426082")


def _write_pixelcoat_recipe(ws: Workspace, batch: dict, model: MissionBrief):
    """Write a Pixelcoat recipe (+ resolvable source) for the shared theme pack.

    Prefers a real recipe from the shared library if present; otherwise writes a
    minimal recipe with a placeholder source so the real tool can still run.
    Returns (recipe_path, source_path)."""
    theme = model.theme or batch.get("theme_family", "delco_1997")
    shared = ws.shared_dir / "pixelcoat" / "recipes"
    existing = sorted(shared.glob("*.json")) if shared.exists() else []
    for cand in existing:
        try:
            raw = json.loads(cand.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if "asset_id" in raw and "source" in raw:  # a full recipe, not a palette
            src = raw["source"].get("path", "")
            src_path = (cand.parent / src) if src and not Path(src).is_absolute() else Path(src)
            return cand, src_path

    dest_dir = ws.internal_dir / "temp" / "pixelcoat"
    dest_dir.mkdir(parents=True, exist_ok=True)
    source = dest_dir / "theme_src.png"
    source.write_bytes(_ONE_PX_PNG)
    recipe = {
        "schema_version": "1",
        "asset_id": "theme",
        "source": {"path": "theme_src.png"},
        "palette": {"colors": ["#0b1020", "#233a52", "#88b0ac", "#f2f6ec"]},
        "meta": {"theme": theme},
    }
    recipe_path = dest_dir / "theme.recipe.json"
    recipe_path.write_text(pretty_dumps(recipe), encoding="utf-8")
    return recipe_path, source


# Outputs whose sameness means "the same level". The assembled site and the
# building shell only: logs, provenance and timing differ between runs that
# produced an identical level, and a gate that trips on those is a gate someone
# turns off.
_DIVERSITY_ARTIFACTS = (
    ("lot_assemble", "site.tscn"),
    ("deli_generate", "shell.glb"),
)


def candidate_artifact_hashes(ws: Workspace, candidate_ids, jobs) -> dict:
    """``{candidate_id: {artifact_name: content_hash}}`` for one mission.

    Candidates with no outputs stay in the mapping with an empty dict rather
    than being dropped -- "this candidate never built" and "this candidate is a
    copy" are different failures, and silently omitting the first would leave
    the pipeline reporting a clean comparison of the survivors.
    """
    from packages.core.hashing import hash_file

    by_candidate: dict[str, dict[str, str]] = {cid: {} for cid in candidate_ids}
    wanted = dict(_DIVERSITY_ARTIFACTS)
    for job in jobs:
        cand = getattr(job, "candidate_id", None)
        name = wanted.get(job.stage_id)
        if not cand or not name or cand not in by_candidate:
            continue
        path = _latest_output(ws.jobs_dir / job.job_id, name)
        if path.exists():
            by_candidate[cand][name] = hash_file(path)
    return by_candidate


def _candidate_diversity_issues(ws: Workspace, candidate_ids, jobs,
                                mission_id: str):
    """Compare a mission's candidates against each other and report copies.

    Every other check in the pipeline looks at one candidate at a time, which is
    precisely why five identical candidates passed validation five times. This
    is the only check that can see the difference between "N candidates" and
    "one candidate, N times", so it is the only place that failure can be
    caught. Returns ``(issues, one_line_summary)``.
    """
    from packages.validation.candidate_diversity import (
        check_candidate_diversity, summarize,
    )

    by_candidate = candidate_artifact_hashes(ws, candidate_ids, jobs)
    issues = []
    for n, raw in enumerate(check_candidate_diversity(by_candidate)):
        raw = {**raw, "issue_id": f"level_factory:{raw['code']}:{mission_id}:{n}"}
        issues.append(issue_from_normalized(
            raw, source_tool="level_factory", mission_id=mission_id,
            candidate_id=None, stage_id="candidate_diversity"))
    return issues, summarize(by_candidate)


def cmd_run(args) -> int:
    ws = _ws(args)
    index = _open_index(ws)
    batch_id, batch, model, plan = _plan_for(ws, args.mission_id,
                                              getattr(args, 'target', None),
                                              layers=_resolve_layers(args))
    specs = _job_specs_for_plan(ws, batch, model, plan)
    scheduler = _build_scheduler(ws, index)

    summary = scheduler.run(plan.graph, job_specs=specs, mission_id=args.mission_id,
                            force=bool(getattr(args, "force", False)))

    # A mission generates N candidates so a human can choose between them; that
    # only means something if the N are different. Nothing had ever compared
    # two, so five copies passed validation five times.
    diversity_issues, diversity_line = _candidate_diversity_issues(
        ws, plan.candidate_ids, plan.graph.jobs(), args.mission_id)
    summary.all_issues.extend(diversity_issues)

    # Persist normalized issues for `validate`.
    issue_dicts = [i.as_dict() for i in summary.all_issues]
    vdir = ws.internal_dir / "validation"
    vdir.mkdir(parents=True, exist_ok=True)
    (vdir / f"{args.mission_id}.json").write_text(
        pretty_dumps({"mission_id": args.mission_id, "issues": issue_dicts}), encoding="utf-8"
    )

    for o in summary.outcomes:
        tag = "cache" if o.cache_hit else o.job.status.lower()
        print(f"  {o.job.job_id:<48} {tag}")

    print(f"\n{diversity_line}")
    # THE ELIMINATED SET GOES IN. The scheduler discards a candidate whose own
    # job failed and carries on with the rest -- and until this was passed, one
    # discarded candidate's blocker labelled the whole mission "Blocked:
    # unresolved blocking issues" while `blocked_job` was never set. Addendum
    # item I: "N candidates exist so that some can be bad."
    _dropped = frozenset(getattr(summary, "eliminated_candidates", {}) or {})
    agg = aggregate(summary.all_issues, eliminated_candidates=_dropped)
    if _dropped:
        # `cmd_batch_run` has printed this for a while and `cmd_run` never did,
        # so on a single-mission run the reason the mission survived was
        # invisible. Not a failure line.
        print(f"  {len(_dropped)} candidate(s) eliminated (the rest carried "
              f"on): {', '.join(sorted(_dropped))}")
        if agg["blocking_eliminated"]:
            print(f"  {len(agg['blocking_eliminated'])} blocker(s) belong to "
                  f"eliminated candidate(s) and do not block the mission")

    # Record what this run left the mission in. Nothing wrote the missions table
    # before, so `status` with no mission id listed nothing and `batch report`
    # showed every mission as "draft" no matter how many times it had been
    # built -- an empty answer that looks exactly like a quiet one.
    index.upsert_mission(
        args.mission_id, batch_id,
        "blocked" if summary.blocked_job
        else ("findings" if agg["total"] else "built"),
        _now())
    print(f"\n{readiness_label(agg, run_completed=not summary.blocked_job)}  "
          f"(blockers open: {len(agg['blocking_open'])}, total findings: {agg['total']})")

    if summary.blocked_job:
        print(f"blocked at: {summary.blocked_job}", file=sys.stderr)
        failed = index.get_job(summary.blocked_job)
        if failed and failed.failure:
            fc = failed.failure.get("failure_class")
            if fc in ("tool_exit_failure", "timeout", "output_contract_error"):
                return EXIT_TOOL
        return EXIT_BLOCKED
    if agg["total"] > 0:
        return EXIT_FINDINGS
    return EXIT_OK


def _batch_briefs(ws: Workspace, batch_id: str, batch: dict):
    briefs = []
    for mission_id in batch.get("missions", []):
        bf = ws.mission_subdir(batch_id, mission_id, "brief") / "brief.json"
        if bf.exists():
            briefs.append(_brief_model(ws.read_json(bf)))
    return briefs


def _batch_job_specs(ws: Workspace, batch: dict, batch_plan) -> dict:
    """Specs for the combined batch graph: the shared Pixelcoat node plus every
    mission's jobs (with Zoo kit repointed at the shared pack output)."""
    from packages.pipeline.batch_planner import shared_pixelcoat_id, SHARED_PIXELCOAT_STAGE
    jobs_dir = ws.jobs_dir
    specs: dict = {}
    shared_id = shared_pixelcoat_id(batch["batch_id"])
    shared_out = str(_latest_output(jobs_dir / shared_id, "."))

    for brief in _batch_briefs(ws, batch["batch_id"], batch):
        _, _, _, mplan = _plan_for(ws, brief.mission_id, batch_plan.target,
                                     layers=batch_plan.layers)
        mission_specs = _job_specs_for_plan(ws, batch, brief, mplan)
        for job in batch_plan.graph.jobs():
            if job.mission_id != brief.mission_id:
                continue
            spec = mission_specs.get(job.job_id, {})
            # Repoint the (batch-merged) Zoo kit at the shared Pixelcoat packs.
            if job.stage_id == "zoo_kit_build" and shared_id in job.depends_on:
                spec = {**spec, "skins_dir": shared_out}
            specs[job.job_id] = spec

    # The shared Pixelcoat node (batch-level surface pack).
    _briefs = _batch_briefs(ws, batch["batch_id"], batch)
    recipe_path, source_path = _write_pixelcoat_recipe(ws, batch, _briefs[0])
    specs[shared_id] = {
        "recipe_path": str(recipe_path),
        "source_path": str(source_path),
        "asset_id": "theme",
    }
    return specs


def cmd_batch_run(args) -> int:
    from packages.pipeline.batch_planner import plan_batch
    ws = _ws(args)
    index = _open_index(ws)
    batch = _load_batch(ws, args.batch_id)
    briefs = _batch_briefs(ws, args.batch_id, batch)
    selected = {b.mission_id: _resolve_selected_candidate(ws, b.mission_id) for b in briefs}

    batch_plan = plan_batch(briefs, batch=batch,
                            selected_by_mission=selected,
                            target=args.target or TARGET_PRESENTATION,
                            layers=_resolve_layers(args))
    if not batch_plan.mission_ids:
        print("no missions ready to run (each needs a selected candidate)",
              file=sys.stderr)
        return EXIT_BLOCKED

    specs = _batch_job_specs(ws, batch, batch_plan)
    scheduler = _build_scheduler(ws, index)
    summary = scheduler.run(batch_plan.graph, job_specs=specs,
                            mission_id=f"batch:{args.batch_id}")

    # Same comparison as `run`, per mission: a batch that quietly built the same
    # level N times for every mission in it is the same fiction at scale.
    diversity_lines: list[str] = []
    for mid in batch_plan.mission_ids:
        mjobs = [j for j in batch_plan.graph.jobs() if j.mission_id == mid]
        mcands = sorted({j.candidate_id for j in mjobs if getattr(j, "candidate_id", None)})
        issues, line = _candidate_diversity_issues(ws, mcands, mjobs, mid)
        summary.all_issues.extend(issues)
        diversity_lines.append(f"  {mid}: {line}")

    # Persist per-mission validation for `validate` / reports.
    vdir = ws.internal_dir / "validation"; vdir.mkdir(parents=True, exist_ok=True)
    by_mission: dict[str, list] = {}
    for issue in summary.all_issues:
        by_mission.setdefault(getattr(issue, "mission_id", "") or "", []).append(issue.as_dict())
    for mid in batch_plan.mission_ids:
        (vdir / f"{mid}.json").write_text(
            pretty_dumps({"mission_id": mid, "issues": by_mission.get(mid, [])}),
            encoding="utf-8")
        # Same reason as cmd_run: a mission built through a batch was invisible
        # to `status` and reported as "draft" forever.
        index.upsert_mission(
            mid, args.batch_id,
            "blocked" if summary.blocked_job
            else ("findings" if by_mission.get(mid) else "built"),
            _now())

    print(f"batch {args.batch_id}: {len(batch_plan.mission_ids)} mission(s), "
          f"{len(batch_plan.shared_job_ids)} shared job(s)")
    cache_hits = sum(1 for o in summary.outcomes if o.cache_hit)
    print(f"  jobs: {len(summary.outcomes)}  (cache reuse: {cache_hits})")
    skipped = getattr(summary, "never_dispatched", []) or []
    if skipped:
        # A run that stops on the first blocker leaves the rest of the DAG
        # untouched, and every one of those jobs keeps a stable out/ directory
        # full of the PREVIOUS run's artifacts. "Never ran" and "ran and passed"
        # look identical from there. The count above is not a complete account
        # of the run until this prints too.
        print(f"  NOT RUN: {len(skipped)} job(s) never dispatched -- the run "
              f"stopped at its first blocker. Their out/ still holds the "
              f"PREVIOUS run's artifacts:")
        for _jid in skipped:
            print(f"    - {_jid}: "
                  f"{getattr(summary, 'not_run_reason', {}).get(_jid, '')}")
    dropped = getattr(summary, "eliminated_candidates", {}) or {}
    if dropped:
        # Not a failure line. Five candidates are generated so the weak
        # ones can be dropped, and until the scheduler learned to scope a
        # failure, one bad candidate halted the run and took the good ones
        # with it.
        print(f"  {len(dropped)} candidate(s) eliminated (the rest carried on):")
        for _cid, _at in sorted(dropped.items()):
            print(f"    - {_cid}  at {_at}")
    for line in diversity_lines:
        print(line)
    if batch_plan.skipped_missions:
        print(f"  skipped (no selection): {', '.join(batch_plan.skipped_missions)}")
    if summary.blocked_job:
        print(f"blocked at: {summary.blocked_job}", file=sys.stderr)
        return EXIT_BLOCKED
    return EXIT_OK


def _mission_report(ws: Workspace, batch: dict, mission_id: str):
    from packages.reporting.summaries import MissionSummary
    from packages.pipeline.planner import derive_seeds
    selected = _resolve_selected_candidate(ws, mission_id)
    seeds = derive_seeds(int(batch.get("seed_base", 0)),
                         int(next((b.candidate_count for b in
                                   _batch_briefs(ws, batch["batch_id"], batch)
                                   if b.mission_id == mission_id), 3)))
    lux = _latest_output(ws.jobs_dir / f"{mission_id}.lux_apply", "lux.applied.tscn")
    handoff = _latest_output(ws.jobs_dir / f"{mission_id}.dispatch_handoff", "mission.tscn")
    lock = _lock_path(ws, mission_id)
    vfile = ws.internal_dir / "validation" / f"{mission_id}.json"
    vsummary = "no validation"
    if vfile.exists():
        issues = json.loads(vfile.read_text(encoding="utf-8")).get("issues", [])
        vsummary = f"{len(issues)} findings, {sum(1 for i in issues if i.get('blocking'))} blocking"
    return MissionSummary(
        mission_id=mission_id, selected_candidate=selected, seeds=seeds,
        tool_versions=_adapter_versions(), validation=vsummary,
        functional_lock=("locked" if lock.exists() else "unlocked"),
        handoff_ready=handoff.exists(), presentation_ready=lux.exists())


def cmd_batch_report(args) -> int:
    from packages.reporting.summaries import BatchSummary
    from packages.pipeline.batch_planner import shared_pixelcoat_id
    ws = _ws(args)
    batch = _load_batch(ws, args.batch_id)
    briefs = _batch_briefs(ws, args.batch_id, batch)

    rows = []
    for b in briefs:
        mid = b.mission_id
        mrep = _mission_report(ws, batch, mid)
        state = _open_index(ws).mission_state(mid) or "draft"
        rows.append({
            "mission_id": mid, "state": state,
            "presentation": "ready" if mrep.presentation_ready else "pending",
            "handoff": "ready" if mrep.handoff_ready else "pending",
            "selected": mrep.selected_candidate,
            "validation": mrep.validation,
        })

    shared_out = ws.jobs_dir / shared_pixelcoat_id(args.batch_id) / "out"
    shared_packs = ([p.name for p in shared_out.rglob("*.pack.json")]
                    if shared_out.exists() else [])
    versions = _adapter_versions()
    summary = BatchSummary(
        batch_id=args.batch_id, mission_rows=rows, shared_packs=shared_packs,
        tool_versions=versions, tool_version_consistent=True,
        build_lock=hash_json({"batch": args.batch_id, "missions": rows,
                              "tools": versions}))

    reports_dir = ws.batch_dir(args.batch_id) / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    (reports_dir / "batch_summary.json").write_text(
        pretty_dumps(summary.as_dict()), encoding="utf-8")
    (reports_dir / "batch_summary.md").write_text(
        summary.to_markdown(), encoding="utf-8")
    for b in briefs:
        mrep = _mission_report(ws, batch, b.mission_id)
        (reports_dir / f"{b.mission_id}.summary.json").write_text(
            pretty_dumps(mrep.as_dict()), encoding="utf-8")
        (reports_dir / f"{b.mission_id}.summary.md").write_text(
            mrep.to_markdown(), encoding="utf-8")

    if args.json:
        print(pretty_dumps(summary.as_dict()))
    else:
        print(summary.to_markdown())
    return EXIT_OK


def cmd_status(args) -> int:
    ws = _ws(args)
    index = _open_index(ws)
    if args.mission_id:
        jobs = index.jobs_for_mission(args.mission_id)
        if not jobs:
            print(f"no jobs recorded for {args.mission_id}")
            return EXIT_OK
        for j in jobs:
            extra = f" exit={j.exit_code}" if j.exit_code is not None else ""
            print(f"  {j.job_id:<48} {j.status}{extra}")
    else:
        missions = index.list_missions()
        if not missions:
            # Silence here used to be ambiguous between "no missions" and
            # "the listing is broken". It was the second one.
            print("no missions have been run in this workspace yet")
            return EXIT_OK
        for m in missions:
            print(f"  {m['mission_id']:<32} {m['state']:<10} {m['batch_id']}")
    return EXIT_OK


def cmd_validate(args) -> int:
    ws = _ws(args)
    vfile = ws.internal_dir / "validation" / f"{args.mission_id}.json"
    if not vfile.exists():
        print(f"no validation recorded for {args.mission_id}; run the mission first")
        return EXIT_OK
    data = json.loads(vfile.read_text(encoding="utf-8"))
    issues = [
        issue_from_normalized(
            i, source_tool=i.get("source_tool", "?"), mission_id=args.mission_id,
            candidate_id=i.get("candidate_id"), stage_id=i.get("stage_id"),
        )
        for i in data.get("issues", [])
    ]
    agg = aggregate(issues)
    if getattr(args, "json", False):
        # Machine output carries the findings too, not just the histogram: a
        # caller that has to re-read the raw file to learn WHAT was found is
        # being handed a number, not a result.
        print(pretty_dumps({"aggregate": agg,
                            "issues": data.get("issues", [])}))
        return EXIT_BLOCKED if agg["has_blockers"] else EXIT_OK

    # Findings first, worst first. A count grouped by category tells you five
    # things are wrong and nothing about what to do, so it reads as weather
    # rather than as work -- which is how a finding count sits unchanged at 5
    # across every run for weeks.
    if not issues:
        print(f"{args.mission_id}: no findings")
        return EXIT_OK

    from packages.validation.model import severity_rank
    for issue in sorted(issues, key=lambda i: (severity_rank(i.severity),
                                               i.code)):
        mark = "BLOCKER" if issue.blocking else issue.severity.upper()
        where = " ".join(x for x in (issue.candidate_id, issue.location) if x)
        print(f"[{mark}] {issue.code} ({issue.category})"
              + (f"  {where}" if where else ""))
        if issue.message:
            print(f"    {issue.message}")
        if issue.suggested_fix:
            print(f"    fix: {issue.suggested_fix}")

    counts = ", ".join(f"{n} {sev}" for sev, n in agg["by_severity"].items() if n)
    print(f"\n{agg['total']} finding(s): {counts}"
          + ("  -- none blocking" if not agg["has_blockers"] else ""))
    return EXIT_BLOCKED if agg["has_blockers"] else EXIT_OK


def _protected_inputs_for_gate(ws: Workspace, mission_id: str, gate: str) -> dict:
    _, brief = _find_mission(ws, mission_id)
    model = _brief_model(brief)
    if gate == gates.BRIEF_APPROVED:
        return {"brief": model.as_dict()}
    # Later gates bind to the functional signature of the brief.
    return {"functional_signature": model.functional_signature()}


# --------------------------------------------------------------------------
# Phase 5: team approvals, exceptions, review, CI, release
# --------------------------------------------------------------------------
def _team_store(ws: Workspace):
    from packages.approvals.team import TeamApprovalStore
    return TeamApprovalStore(ws.internal_dir / "team_approvals")


def cmd_team_sign(args) -> int:
    ws = _ws(args)
    protected = _protected_inputs_for_gate(ws, args.mission_id, args.gate)
    store = _team_store(ws)
    store.sign(mission_id=args.mission_id, gate=args.gate, approver=args.by,
               protected_inputs=protected, note=args.note or "")
    status = store.status(args.mission_id, args.gate, protected)
    print(f"{args.by} signed {args.gate} for {args.mission_id} "
          f"({len(status.current_signoffs)}/{status.quorum}, "
          f"{'satisfied' if status.satisfied else f'{status.remaining} more needed'})")
    return EXIT_OK


def cmd_team_status(args) -> int:
    ws = _ws(args)
    protected = _protected_inputs_for_gate(ws, args.mission_id, args.gate)
    status = _team_store(ws).status(args.mission_id, args.gate, protected)
    print(pretty_dumps(status.as_dict()))
    return EXIT_OK if status.satisfied else EXIT_FINDINGS


def cmd_accept_exception(args) -> int:
    from packages.approvals.exceptions import ExceptionStore, ExceptionError
    ws = _ws(args)
    vfile = ws.internal_dir / "validation" / f"{args.mission_id}.json"
    if not vfile.exists():
        print(f"no validation for {args.mission_id}; run the mission first",
              file=sys.stderr)
        return EXIT_BLOCKED
    issues = json.loads(vfile.read_text(encoding="utf-8")).get("issues", [])
    issue = next((i for i in issues
                  if i.get("code") == args.issue or i.get("issue_id") == args.issue), None)
    if issue is None:
        print(f"no issue '{args.issue}' in {args.mission_id}", file=sys.stderr)
        return EXIT_BLOCKED
    # Bind the exception to the mission's functional-lock fingerprint (the
    # artifact whose change should invalidate the acceptance).
    lock_file = _lock_path(ws, args.mission_id)
    fp = ""
    if lock_file.exists():
        fp = json.loads(lock_file.read_text(encoding="utf-8")).get("collision_fingerprint", "")
    store = ExceptionStore(ws.internal_dir / "exceptions")
    try:
        exc = store.accept(mission_id=args.mission_id, issue=issue, approver=args.by,
                           reason=args.reason, artifact_fingerprint=fp,
                           expires_at=args.expires, follow_up_ticket=args.ticket)
    except ExceptionError as e:
        print(f"cannot accept: {e}", file=sys.stderr)
        return EXIT_BLOCKED
    print(f"accepted exception for issue '{exc.issue_id}' by {exc.approver}")
    return EXIT_OK


def cmd_review(args) -> int:
    from packages.review.visual import compare_presentation
    ws = _ws(args)
    after_dir = ws.jobs_dir / f"{args.mission_id}.lux_apply" / "out"
    if not after_dir.exists():
        print(f"no presentation previews for {args.mission_id}; run presentation first",
              file=sys.stderr)
        return EXIT_BLOCKED
    baseline = ws.internal_dir / "review" / args.mission_id / "baseline"
    before_dir = baseline if baseline.exists() else None

    review = compare_presentation(args.mission_id, before_dir=before_dir, after_dir=after_dir)

    rdir = ws.internal_dir / "review" / args.mission_id
    rdir.mkdir(parents=True, exist_ok=True)
    (rdir / "visual_review.json").write_text(pretty_dumps(review.as_dict()), encoding="utf-8")
    (rdir / "visual_review.html").write_text(review.to_html(), encoding="utf-8")

    # Snapshot the current previews as the new baseline for next time.
    import shutil as _sh
    baseline.mkdir(parents=True, exist_ok=True)
    for png in after_dir.glob("preview_*.png"):
        _sh.copy2(png, baseline / png.name)

    changed = review.as_dict()["changed_states"]
    print(f"visual review for {args.mission_id}: "
          f"{len(review.comparisons)} states, changed: {', '.join(changed) or '(none)'}")
    print(f"  report: {rdir / 'visual_review.html'}")
    return EXIT_OK


def cmd_ci_init(args) -> int:
    from packages.ci.templates import render_templates
    ws = _ws(args)
    root = Path(args.dest) if getattr(args, "dest", None) else ws.root
    written = []
    for rel, content in render_templates().items():
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        if rel.endswith(".sh"):
            target.chmod(0o755)
        written.append(rel)
    print("wrote CI templates:")
    for w in written:
        print(f"  {w}")
    return EXIT_OK


def cmd_release(args) -> int:
    from packages.release.scm import (
        ReleaseError, is_clean, tag_release, write_release_provenance,
    )
    ws = _ws(args)
    repo = ws.root
    if not (repo / ".git").exists():
        # Walk up: the workspace may live inside a repo.
        repo = next((p for p in [ws.root, *ws.root.parents] if (p / ".git").exists()), None)
        if repo is None:
            print("no git repository found for this workspace", file=sys.stderr)
            return EXIT_CONFIG
    try:
        record = tag_release(repo, batch_id=args.batch_id, tag=args.tag,
                             message=args.message or f"Level Factory release {args.tag}",
                             require_clean=not args.allow_dirty)
    except ReleaseError as e:
        print(f"release failed: {e}", file=sys.stderr)
        return EXIT_BLOCKED
    dest = ws.batch_dir(args.batch_id) / "reports" / "release.json"
    write_release_provenance(record, dest)
    print(f"tagged {args.tag} at {record.commit[:12]} (not pushed) -> {dest}")
    print("  push it yourself when ready: git push origin " + args.tag)
    return EXIT_OK


def _factory_pin() -> tuple[str | None, str | None, dict | None]:
    """The factory version an export was built by, or (None, None).

    Walks up from this file for factory.manifest.json. level_factory is
    a tool repo that lives INSIDE the factory checkout and nothing hands
    it the root -- `verify-manifest --factory` defaults to the working
    directory, which is right only when someone is standing in the right
    place, and an export should not depend on where it was launched.

    RESOLVED HERE, IN THE CLI, AND PASSED DOWN. A tool that reached up
    into the factory checkout to discover what it is would be code at
    the factory level wearing a tool's directory name.

    Not found returns None, which the archive name renders as `fNA`. A
    guessed number is worse than an absent one: it points a reader at a
    factory.manifest.json tag that never pinned this build.
    """
    for d in Path(__file__).resolve().parents:
        p = d / "factory.manifest.json"
        if not p.is_file():
            continue
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None, None, None
        v = data.get("factory_version")
        tools = {
            name: str(e.get("version"))
            for name, e in (data.get("tools") or {}).items()
            if isinstance(e, dict) and e.get("version")
        } or None
        return ((str(v), f"factory-v{v}", tools) if v
                else (None, None, tools))
    return None, None, None


def _lock_path(ws: Workspace, mission_id: str) -> Path:
    return ws.internal_dir / "locks" / f"{mission_id}.json"


def _selected_lot_out(ws: Workspace, mission_id: str) -> Path | None:
    cand = _resolve_selected_candidate(ws, mission_id)
    if not cand:
        return None
    seed = cand.rsplit("_", 1)[-1]
    return ws.jobs_dir / f"{mission_id}.lot_assemble.candidate.seed_{seed}" / "out"


def _refuse_vacuous_lock(ws: Workspace, mission_id: str) -> int:
    """Compute the lock and throw it away, to see whether it is refused.

    A dry run, so the decision happens BEFORE the approval is recorded.
    The cost is computing the signatures twice; the alternative is
    splitting `_store_functional_lock` in half for the sake of one
    branch, and hashing a few thousand records twice is cheaper than a
    seam nobody maintains.

    stderr is swallowed here because the real write below prints the
    same coverage report, and a warning printed twice reads like two
    problems.
    """
    import contextlib
    import io
    from packages.approvals.lock import VacuousLockError
    try:
        with contextlib.redirect_stderr(io.StringIO()):
            _store_functional_lock(ws, mission_id, write=False)
    except VacuousLockError as exc:
        print(f"functional_shell_locked REFUSED for {mission_id}: the "
              f"lock this would write protects nothing.",
              file=sys.stderr)
        print(str(exc), file=sys.stderr)
        print("  nothing was recorded and no lock was written.",
              file=sys.stderr)
        return EXIT_BLOCKED
    return EXIT_OK


def _store_functional_lock(ws: Workspace, mission_id: str,
                           write: bool = True) -> None:
    from packages.approvals.lock import compute_lock
    cand = _resolve_selected_candidate(ws, mission_id)
    lot_out = _selected_lot_out(ws, mission_id)
    if not cand or lot_out is None:
        return
    seed = int(cand.rsplit("_", 1)[-1])
    deli_out = ws.jobs_dir / f"{mission_id}.deli_generate.candidate.seed_{seed}" / "out"
    lock = compute_lock(
        mission_id=mission_id, candidate_id=cand, seed=seed,
        site_gameplay_path=lot_out / "site.site.gameplay.json",
        deli_gameplay_path=deli_out / "shell.gameplay.json",
    )
    if not write:
        return
    p = _lock_path(ws, mission_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(pretty_dumps(lock.as_dict()), encoding="utf-8")


def _refuse_bad_candidate(ws: Workspace, mission_id: str,
                          candidate: str) -> int:
    """Refuse a candidate id that cannot name a real candidate.

    `lot_demo_001.candidate.seed_XXXX` -- a doc's placeholder -- was the
    selected candidate for a day, because this file wrote `--candidate`
    to the marker verbatim and nothing looked at it. Everything
    downstream builds a job directory from that string.

    SHAPE is refused; EXISTENCE is only warned about. Whether
    lot_assemble has run by the time a candidate is selected is an
    ordering question this has no business deciding, but a marker that
    cannot possibly name a job is wrong at any point in the order.
    """
    import re
    want = re.compile(
        r"^" + re.escape(str(mission_id)) + r"\.candidate\.seed_\d+$")
    if not want.match(str(candidate).strip()):
        print(f"refusing --candidate {candidate!r}: expected "
              f"{mission_id}.candidate.seed_<number>", file=sys.stderr)
        print("  nothing is recorded; the gate is not approved",
              file=sys.stderr)
        return EXIT_BLOCKED
    seed = str(candidate).strip().rsplit("_", 1)[-1]
    job = ws.jobs_dir / f"{mission_id}.lot_assemble.candidate.seed_{seed}"
    if not job.is_dir():
        print(f"[approve] WARNING no {job.name} yet; the selection is "
              f"recorded and will resolve once that job runs",
              file=sys.stderr)
    return EXIT_OK


def cmd_approve(args) -> int:
    ws = _ws(args)
    # VALIDATED BEFORE ANYTHING IS RECORDED. It was not: store.record
    # ran first, so a refused candidate would still have left an
    # approved candidate_selected gate behind it. Nothing exercised that
    # path because nothing here had ever refused anything.
    if args.gate == gates.CANDIDATE_SELECTED and args.candidate:
        rc = _refuse_bad_candidate(ws, args.mission_id, args.candidate)
        if rc != EXIT_OK:
            return rc
    # SAME REASON, SAME FUNCTION, AND I MISSED IT THE FIRST TIME.
    # 0.28.0 moved the candidate check above store.record so a refusal
    # could not leave an approved gate behind it. With
    # LOCK_COVERAGE_ENFORCED on, a refused LOCK would do exactly that:
    # an approved functional_shell_locked with no lock behind it,
    # reported by a traceback out of _store_functional_lock.
    if args.gate == gates.FUNCTIONAL_SHELL_LOCKED:
        rc = _refuse_vacuous_lock(ws, args.mission_id)
        if rc != EXIT_OK:
            return rc
    store = gates.ApprovalStore(ws.internal_dir / "approvals")
    protected = _protected_inputs_for_gate(ws, args.mission_id, args.gate)
    store.record(
        mission_id=args.mission_id, gate=args.gate, decision=gates.DECISION_APPROVED,
        approved_by=args.by, protected_inputs=protected, notes=args.note,
    )
    if args.gate == gates.CANDIDATE_SELECTED and args.candidate:
        (ws.internal_dir / "approvals").mkdir(parents=True, exist_ok=True)
        (ws.internal_dir / "approvals" / f"{args.mission_id}.selected").write_text(
            args.candidate, encoding="utf-8"
        )
    if args.gate == gates.FUNCTIONAL_SHELL_LOCKED:
        _store_functional_lock(ws, args.mission_id)
    print(f"approved {args.gate} for {args.mission_id}")
    return EXIT_OK


def cmd_reject(args) -> int:
    ws = _ws(args)
    store = gates.ApprovalStore(ws.internal_dir / "approvals")
    protected = _protected_inputs_for_gate(ws, args.mission_id, args.gate)
    store.record(
        mission_id=args.mission_id, gate=args.gate, decision=gates.DECISION_REJECTED,
        approved_by=args.by, protected_inputs=protected, notes=args.reason,
    )
    print(f"rejected {args.gate} for {args.mission_id}")
    return EXIT_OK


def cmd_cache(args) -> int:
    ws = _ws(args)
    cache = _cache(ws)
    if args.action == "inspect":
        print(pretty_dumps(cache.inspect()))
    elif args.action == "forget":
        # THE DIGEST COMES FROM THE JOB'S OWN RECEIPT. The scheduler writes
        # `fingerprint.last.json` beside every job on every evaluation,
        # explicitly so that "but I changed the slots!" can be answered without
        # archaeology. Reading it here means a caller names a JOB -- the thing
        # they actually distrust -- instead of computing a digest by hand.
        if not getattr(args, "job_id", None):
            print("cache forget needs a job id, e.g. "
                  "lot_demo_001.presentation_compose")
            return EXIT_CONFIG
        receipt = ws.jobs_dir / args.job_id / "fingerprint.last.json"
        if not receipt.is_file():
            print(f"no fingerprint receipt for '{args.job_id}' at {receipt}")
            print("  the job has never been evaluated in this workspace")
            return EXIT_CONFIG
        try:
            digest = json.loads(receipt.read_text(encoding="utf-8"))["digest"]
        except (OSError, ValueError, KeyError) as exc:
            print(f"receipt unreadable: {exc}")
            return EXIT_CONFIG
        dropped = cache.forget(digest)
        print(pretty_dumps({"job_id": args.job_id, "digest": digest,
                            "forgotten": dropped,
                            "note": ("the job will re-run on the next pass"
                                     if dropped else
                                     "nothing was cached under that digest")}))
    else:
        print(pretty_dumps(cache.prune()))
    return EXIT_OK


def cmd_diagnostics(args) -> int:
    ws = _ws(args)
    index = _open_index(ws)
    job = index.get_job(args.job_id)
    if job is None:
        print(f"no job '{args.job_id}'")
        return EXIT_OK
    bundle = job.as_dict()
    if job.log_path and Path(job.log_path).exists():
        bundle["log_tail"] = Path(job.log_path).read_text(
            encoding="utf-8", errors="replace"
        ).splitlines()[-40:]
    print(pretty_dumps(bundle))
    return EXIT_OK


def _adapter_versions() -> dict:
    from packages.adapters.registry import AdapterRegistry
    reg = AdapterRegistry()
    return {aid: reg.get(aid).adapter_version for aid in reg.ids()}


def _probe_tool_versions(ws: Workspace) -> dict:
    """Probe every configured tool repo for the version it actually reports."""
    from packages.adapters.registry import AdapterRegistry
    reg = AdapterRegistry()
    tools_local = ws.load_tools_local()
    repos = tools_local.get("repositories", {})
    versions: dict = {}
    for aid in reg.ids():
        repo = repos.get(aid)
        if not repo:
            versions[aid] = None
            continue
        try:
            probe = reg.get(aid).probe({"repository": repo, **tools_local})
            versions[aid] = probe.tool_version
        except Exception:
            versions[aid] = None
    return versions


def cmd_verify_contracts(args) -> int:
    """Compare installed tool versions against the certified baseline (lock, else
    the grounded baseline the LF release was verified against)."""
    from packages.tools import contracts
    ws = _ws(args)
    installed = _probe_tool_versions(ws)
    lock_tools = ws.load_tools_lock().get("tools", {})
    results = contracts.verify(installed, lock_tools)

    if getattr(args, "json", False):
        print(pretty_dumps({"results": [r.as_dict() for r in results],
                            "worst": contracts.worst_status(results)}))
    else:
        width = max(len(r.adapter_id) for r in results)
        for r in results:
            print(f"  {r.status:<12} {r.adapter_id:<{width}}  {r.message}")

    worst = contracts.worst_status(results)
    strict = getattr(args, "strict", False)
    if worst == contracts.INCOMPATIBLE:
        return EXIT_CONFIG  # a major bump — the adapter is likely broken
    if worst == contracts.DRIFT:
        return EXIT_CONFIG if strict else EXIT_FINDINGS
    if worst == contracts.UNKNOWN:
        # Unverifiable (no version source). Informational by default; --strict
        # treats it as a gap to close.
        return EXIT_FINDINGS if strict else EXIT_OK
    return EXIT_OK


def cmd_verify_manifest(args) -> int:
    """Two-layer lockstep check: every tool's installed VERSION against the
    factory manifest's pinned set (factory.manifest.json at the factory root)."""
    from packages.tools import contracts
    factory_root = Path(str(getattr(args, "factory", None) or ".")).resolve()
    try:
        results = contracts.verify_manifest(factory_root)
        manifest = contracts.read_factory_manifest(factory_root)
    except FileNotFoundError as exc:
        print(str(exc))
        return EXIT_CONFIG
    if getattr(args, "json", False):
        print(pretty_dumps({"factory_version": manifest.get("factory_version"),
                            "results": [r.as_dict() for r in results],
                            "worst": contracts.worst_status(results)}))
    else:
        print(f"factory {manifest.get('factory_version')} @ {factory_root}")
        width = max(len(r.adapter_id) for r in results)
        for r in results:
            print(f"  {r.status:<12} {r.adapter_id:<{width}}  {r.message}")
    worst = contracts.worst_status(results)
    if worst == contracts.INCOMPATIBLE:
        return EXIT_CONFIG
    if worst == contracts.DRIFT:
        return EXIT_CONFIG if getattr(args, "strict", False) else EXIT_FINDINGS
    if worst in (getattr(contracts, "UNRELEASED", "UNRELEASED"),
                 getattr(contracts, "UNDOCUMENTED", "UNDOCUMENTED")):
        # The tool disagrees with ITSELF -- its CHANGELOG and its VERSION name
        # different releases. Nothing can be pinned correctly until that is
        # settled, so this exits the same way INCOMPATIBLE does under --strict
        # and as findings otherwise.
        return EXIT_CONFIG if getattr(args, "strict", False) else EXIT_FINDINGS
    if worst == getattr(contracts, "STALE", "STALE"):
        # A pin that matches a VERSION file older than its own code is not a
        # pass. Same exit treatment as DRIFT, because it wants the same thing
        # doing: bump the tool, then re-certify the set.
        return EXIT_CONFIG if getattr(args, "strict", False) else EXIT_FINDINGS
    if worst == contracts.UNKNOWN:
        return EXIT_FINDINGS if getattr(args, "strict", False) else EXIT_OK
    return EXIT_OK


def cmd_certify(args) -> int:
    """Record the currently-installed tool versions as certified in tools.lock.json.
    Run the real-tool smoke first — this asserts those versions pass it."""
    from packages.tools import contracts
    ws = _ws(args)
    installed = _probe_tool_versions(ws)
    updated = contracts.certify(ws.load_tools_lock(), installed)
    ws.write_json(ws.tools_lock, updated)
    print("certified tool versions into tools.lock.json:")
    for aid in sorted(contracts.GROUNDED):
        v = installed.get(aid)
        print(f"  {aid:<14} {v or '(no version reported)'}")
    print("\nReminder: certify only what the real-tool smoke has passed "
          "(LF_TOOLS_DIR=... pytest tests/real_tools).")
    return EXIT_OK


def walk_content_dir(jobs_dir, mission_id):
    """``(dir, stage)`` -- which artifact `walk` should wrap. ``(None, "")``
    when the mission has produced neither.

    THE ASSEMBLED SITE, NOT THE COMPOSE INTERMEDIATE. This named
    `presentation_compose` unconditionally, and on 2026-08-08 that put a
    five-building lot's preview on one building: the run composed five distinct
    scenes under `lot/<id>/`, `themed_site_assemble` placed them into a 26,731
    byte `site.tscn`, and `walk` opened compose's own 47,272 byte single-shell
    scene instead. The review frame showed one building against 86.7% void and
    every self-check passed.

    IT DOES NOT BRANCH ON WHETHER THE LOT IS VARIED. `themed_site_assemble` is
    the last stage that makes a PLACE -- buildings standing on ground -- while
    compose makes a content package for one building, and that is as true of a
    single-shell mission as of a five-building one. A `building_count > 1` test
    here would be a second derivation of "is this a varied lot" living in a
    third place, which is the shape of the last four defects in this file.

    The SCENE decides, not the directory. A job directory exists from the
    moment the scheduler creates it, before its tool has written anything --
    the same distinction `resolve_layer` exists to make.
    """
    jobs_dir = Path(str(jobs_dir))
    site_dir = jobs_dir / f"{mission_id}.themed_site_assemble" / "out"
    if (site_dir / "site.tscn").is_file():
        return site_dir, "themed_site_assemble"
    compose_dir = (jobs_dir / f"{mission_id}.presentation_compose" / "out"
                   / "presentation")
    if compose_dir.is_dir():
        return compose_dir, "presentation_compose"
    return None, ""


def cmd_walk(args) -> int:
    """Build (and optionally open) a DEV-ONLY first-person walk preview that
    wraps the mission's PORTABLE EXPORT so you can walk it and make refinements.

    This is deliberately NOT part of the drop-in package: the package is content
    a stranger instances into their own project, so it stays project-agnostic. A
    player needs its own project, so the preview is a separate, throwaway project
    that instances the export's `mission.tscn` and adds LF's dependency-free
    player. The preview project is never exported.

    It wraps the EXPORT rather than the job outputs so that what gets walked is
    what gets shipped -- see the WALK WHAT SHIPS note below.
    """
    import subprocess
    from packages.preview.walk_preview import build_walk_preview

    ws = _ws(args)
    mission_id = args.mission_id
    content_dir, source_stage = walk_content_dir(ws.jobs_dir, mission_id)
    if content_dir is None:
        print(f"no walkable level for {mission_id}; run `run {mission_id} "
              f"--art` first", file=sys.stderr)
        return EXIT_BLOCKED

    # WALK WHAT SHIPS. The job outputs are an intermediate: `lux.applied.tscn`
    # references `res://addons/lux/` six times and renders nothing without the
    # Lux checkout on disk, which PIPELINE_MAP calls "an instrument that
    # escaped". `export_mission` localizes that, `scan_closure` judges it, and
    # `write_entry_scene` writes a `mission.tscn` whose own comment says
    # "Self-contained (no addons)". Wrapping the export is how the preview shows
    # the lit look without carrying a tool into it.
    #
    # By CALLING `cmd_export` rather than reassembling its inputs. The handoff
    # dir, composed root, lux dir, addon sources, layer set and functional-lock
    # regression check are seventy lines of decisions; a second copy of them
    # here is the defect this file keeps finding in other people's code.
    #
    # A consequence, stated rather than left to be discovered: an export blocked
    # by the regression check now blocks the walk. That is the right way round.
    # A package that failed its own gate is not a thing to go and form opinions
    # about.
    import copy as _copy
    export_args = _copy.copy(args)
    export_args.mode = "portable-godot"
    export_args.format = "dir"
    export_args.include_walk = False
    code = cmd_export(export_args)
    if code != EXIT_OK:
        print(f"walk needs an export and the export was refused; fix that "
              f"first", file=sys.stderr)
        return code
    # ASK FOR THE MODE THIS BLOCK SET, four lines up, rather than naming
    # it again. Hardcoding it was right only for as long as the default
    # above never changed, and nothing would have said so if it had.
    export_dir = (ws.internal_dir / "exports"
                  / export_build_dir_name(mission_id, export_args.mode))
    if (export_dir / "mission.tscn").is_file():
        content_dir, source_stage = export_dir, "export (portable-godot)"
    else:
        print(f"[walk] the export produced no {export_dir / 'mission.tscn'}; "
              f"falling back to {source_stage}", file=sys.stderr)

    player_src = Path(__file__).resolve().parents[3] / "assets" / "godot"
    dest = ws.internal_dir / "preview" / f"{mission_id}_walk"
    try:
        report = build_walk_preview(content_dir, player_src, dest, name=mission_id)
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_BLOCKED

    # IMPORT GATE: a freshly built preview project has no .godot import
    # artifacts, and Godot only imports resources through an editor/import
    # pass -- launching straight into play loads NONE of the new module GLBs
    # (invisible walls over live collision, dead ladders). Run the headless
    # import HERE so the preview is playable the moment it is handed over;
    # a human must never have to remember `-e` first.
    godot_exe = str(ws.load_tools_local().get("godot_executable") or "")
    if godot_exe:
        try:
            subprocess.run([godot_exe, "--headless", "--path", report["dest"],
                            "--import"], capture_output=True, timeout=600)
            print("  imported: resources ready (headless --import pass)")
        except (OSError, subprocess.SubprocessError) as exc:
            print(f"  WARNING: headless import failed ({exc}) -- open once "
                  f"with -e before playing", file=sys.stderr)

    origin = report["spawn_transform"][9:]
    print(f"walk preview: {report['dest']}")
    # SAY WHICH ARTIFACT. "wraps site.tscn" was true of both the compose
    # intermediate and the assembled site, and that ambiguity is how a
    # one-building preview of a five-building lot read as normal.
    print(f"  source: {source_stage}")
    print(f"  wraps {report['level_scene']} + player at {report['spawn_source']} "
          f"(x={origin[0]}, y={origin[1]}, z={origin[2]})")
    # SAY WHAT IT WAS BUILT FROM, and leave the same words in the folder. A
    # preview read after a later `run` is the previous walk, and nothing said
    # so -- addendum item F. `walk.source.json` beside the scene carries this
    # verbatim, so the answer survives the terminal scrolling away.
    _prov = report.get("provenance") or {}
    if _prov:
        print(f"  content: {_prov['content_digest']} "
              f"({_prov['file_count']} file(s)) built {_prov['built_at']}")
        print(f"  recorded in {report['dest']}\\walk.source.json")

    # TRAVERSAL + VISUAL GATE. The preview exists so a human can find out whether
    # the level is broken. The bots find that out first, in seconds, every time
    # -- so the failure modes we already know how to detect (an unclimbable
    # ladder, a wall fighting the greybox underneath it) stop being something a
    # person has to notice. Requires the import pass above: the bots load the
    # same resources the player would.
    bot_rc = EXIT_OK
    if godot_exe and report.get("bots") and not getattr(args, "no_bot", False):
        from packages.preview import walk_bot as _bot
        walk_v = shot_v = None
        try:
            if "walk_bot.gd" in report["bots"]:
                walk_v = _bot.run_walk_bot(godot_exe, report["dest"],
                                           scene=report.get("level_scene"))
            if "shot_bot.gd" in report["bots"] and not getattr(
                    args, "no_shots", False):
                shot_v = _bot.run_shot_bot(godot_exe, report["dest"],
                                           scene=report.get("level_scene"))
        except _bot.BotUnavailable as exc:
            # The engine failed, not the level. Say which -- reporting this as a
            # level defect would train people to ignore the gate.
            print(f"  WARNING: self-check could not run: {exc}", file=sys.stderr)
        else:
            ok, lines = _bot.summarize(walk_v, shot_v)
            print("self-check:")
            for line in lines:
                print(line)
            if not ok:
                print("  the preview is built, but this level does not pass its "
                      "own traversal/visual check -- walk it and confirm before "
                      "shipping", file=sys.stderr)
                bot_rc = EXIT_FINDINGS

    godot = str(ws.load_tools_local().get("godot_executable") or "")
    launch = None
    if getattr(args, "play", False):
        launch = [godot, "--path", report["dest"]]
    elif getattr(args, "open", False):
        launch = [godot, "--path", report["dest"], "-e"]
    if launch and godot:
        print(f"launching Godot: {' '.join(launch)}")
        try:
            subprocess.Popen(launch)
        except OSError as exc:
            print(f"could not launch Godot: {exc}", file=sys.stderr)
            return EXIT_CONFIG
    else:
        if launch and not godot:
            print("godot_executable not configured in tools.local.json; "
                  "open it manually:", file=sys.stderr)
        print(f'  open:  & "{godot or "godot"}" --path "{report["dest"]}" -e')
        print(f'  play:  & "{godot or "godot"}" --path "{report["dest"]}"')
    # The preview always gets built and handed over -- a failing self-check is
    # exactly when you most want to go look at it. The exit code carries the
    # verdict so a pipeline can gate on it; a human just reads the lines above.
    return bot_rc


def _layers_produced(*, compose_root: Path, lux_dir: Path,
                     handoff_dir: Path) -> set:
    """Which composable layers a finished mission actually PRODUCED.

    THE ART LAYER IS NOT LUX. This was four inline lines in `cmd_export`
    and it read `lux_dir.exists()` to decide whether the art layer ran,
    so a mission whose Pixelcoat/Zoo/Patina pass succeeded and whose
    `lux_apply` failed exported an LF_MANIFEST.json declaring no art
    layer -- on a package full of art. Nothing reads that field, so
    nothing ever objected.

    `presentation_compose/out/presentation` is what the art layer
    produces and is therefore what stands for it.

    THE `or lux_dir.exists()` IS NOT REDUNDANT. This must never report
    fewer layers than the four lines it replaces, or a workspace that
    exports correctly today would describe itself differently after an
    upgrade. Lux runs on the composed site and cannot exist without
    one, so its output still implies an art pass. Strictly wider than
    the old test; strictly narrower than lying.

    It takes directories rather than a mission id BECAUSE the bug was
    never how a job path is spelled. Building `<mission>.<stage>/out`
    here would put a second derivation of that name in a second place --
    the failure `walk_content_dir` describes in its own docstring.
    """
    from packages.pipeline.planner import (
        LAYER_ART, LAYER_GAMEPLAY, LAYER_LIGHT,
    )
    layers = set()
    if compose_root.exists() or lux_dir.exists():
        layers.add(LAYER_ART)
    # `lux_apply`'s output is what this directory always meant. Since
    # 0.35.0 it answers its own question instead of standing in for the
    # art layer, which is what an art-unlit package needs LF_MANIFEST.json
    # to be able to say.
    if lux_dir.exists():
        layers.add(LAYER_LIGHT)
    if handoff_dir.exists():
        layers.add(LAYER_GAMEPLAY)
    return layers


def cmd_export(args) -> int:
    from packages.exporting.export import (
        MODES, ExportProfile, export_mission, zip_export,
    )
    ws = _ws(args)
    mission_id = args.mission_id
    jobs_dir = ws.jobs_dir
    from packages.pipeline.planner import LAYER_ART, LAYER_GAMEPLAY

    handoff_dir = jobs_dir / f"{mission_id}.dispatch_handoff" / "out"
    lux_dir = jobs_dir / f"{mission_id}.lux_apply" / "out"
    # The composed res:// root. lux_apply's out/ holds only
    # lux.applied.tscn and its two sidecars; the glb files that scene
    # instances live one job upstream, under presentation_compose, whose
    # out/presentation/ IS the res:// root Lux was run against. Same
    # string pattern as the two directories above. Roadmap item 27.
    compose_root = (jobs_dir / f"{mission_id}.presentation_compose"
                    / "out" / "presentation")
    # The assembled themed SITE. Not the same thing as the composed
    # building above it, and until 0.37.0 it reached no package.
    themed_site_dir = jobs_dir / f"{mission_id}.themed_site_assemble" / "out"
    lot_out = _selected_lot_out(ws, mission_id)

    # Resolve which layers were actually produced, and the functional base.
    # The mapping from artifacts to layers is a decision with a name and a
    # test now; see `_layers_produced` for why the art layer is not Lux.
    layers = _layers_produced(compose_root=compose_root, lux_dir=lux_dir,
                              handoff_dir=handoff_dir)
    graybox_dir = lot_out  # the assembled Lot site is the graybox base
    if not handoff_dir.exists() and (graybox_dir is None or not graybox_dir.exists()):
        print(f"nothing to export for {mission_id}; run it first "
              f"(graybox at minimum, optionally --art/--gameplay)", file=sys.stderr)
        return EXIT_BLOCKED

    presentation_dir = lux_dir if lux_dir.exists() else None
    source_dir = None  # source-authoring would gather briefs/specs; omitted in MVP folder

    # STRAIGHT THROUGH, as `cmd_portability_test` twelve lines below has
    # always done. This mapped each CLI string to the constant holding
    # that same string -- an identity dict that had to learn every new
    # mode and whose only real behaviour was KeyError on one it had not
    # been told about. `art-unlit` hit exactly that, on a real workspace,
    # after fourteen tests that all called export_mission directly.
    if args.mode not in MODES:
        print(f"unknown export mode {args.mode!r}; "
              f"known: {', '.join(sorted(MODES))}", file=sys.stderr)
        return EXIT_BLOCKED
    profile = ExportProfile(mode=args.mode,
                            include_walk=bool(getattr(args, "include_walk", False)))

    # Post-art regression: a functional drift after the art pass blocks export.
    lock_file = _lock_path(ws, mission_id)
    lot_out = _selected_lot_out(ws, mission_id)
    if lock_file.exists() and lot_out is not None:
        from packages.approvals.lock import (FunctionalLock,
                                             blocks_export,
                                             verify_no_drift)
        lock = FunctionalLock.from_dict(json.loads(lock_file.read_text(encoding="utf-8")))
        seed = lock.seed
        deli_out = ws.jobs_dir / f"{mission_id}.deli_generate.candidate.seed_{seed}" / "out"
        regression = verify_no_drift(
            lock, lot_out / "site.site.gameplay.json", deli_out / "shell.gameplay.json")
        if regression.needs_recompute:
            # NOT DRIFT, and not a pass either. The lock predates the
            # current signature definitions, so nothing was compared.
            print(f"[export] the functional lock for {mission_id} "
                  f"predates the current signature definitions; "
                  f"nothing was compared. Recompute it with "
                  f"approve --gate functional_shell_locked.",
                  file=sys.stderr)
        elif regression.vacuous_lock or regression.site_unguarded:
            # THE MOMENT A HUMAN IS TOLD SOMETHING REASSURING AND FALSE.
            # `passed` here means little was compared, not that nothing
            # moved. Printed on the pass, because the failure path
            # already speaks for itself.
            #
            # TWO CONDITIONS, because `vacuous` (all three signatures
            # empty) is not what is true here: Deli's stair_systems keep
            # one signature non-empty, so a lock guarding no site data
            # at all still reads as partly alive.
            what = ("protects nothing at all"
                    if regression.vacuous_lock else
                    "protects no site data -- every signature it checks "
                    "is filled from the Deli side")
            print(f"[export] WARNING the functional lock for "
                  f"{mission_id} {what}. The post-art regression check "
                  f"passed on that basis, which is weaker than it "
                  f"reads. Run tools/probe_selection_drift.py, or read "
                  f"the coverage block in the report.",
                  file=sys.stderr)
        if blocks_export(regression):
            print("export blocked by functional regression:",
                  file=sys.stderr)
            for d in regression.drift:
                print(f"  - {d}", file=sys.stderr)
            if not regression.drift:
                # THE HEADER USED TO PRINT ALONE. A blocked export whose
                # reasons are an empty list tells a reader nothing and
                # reads like a crash. If a future condition blocks
                # without producing drift entries, it says so.
                print("  - no drift entries; the block came from somewhere\n"
                      "    other than a signature comparison. This is a bug\n"
                      "    in level_factory, not a problem with the mission.",
                      file=sys.stderr)
            return EXIT_BLOCKED

    # WHICH LEVEL THIS IS. `lot_demo_001` at seed 5219 and at seed 5017
    # are different levels that graded 60 and 40, and the archive name
    # could not tell them apart. The functional lock first -- it is the
    # approved, drift-checked record of which candidate ships -- then
    # the selection marker. Neither existing is recorded as unknown
    # rather than guessed.
    selected_candidate = _resolve_selected_candidate(ws, mission_id)
    export_seed = None
    if lock_file.exists():
        try:
            export_seed = json.loads(
                lock_file.read_text(encoding="utf-8")).get("seed")
        except (OSError, ValueError):
            export_seed = None
    if export_seed is None and selected_candidate:
        tail = selected_candidate.rsplit("_", 1)[-1]
        export_seed = tail if tail.isdigit() else None
    # WHICH CANDIDATE, from the lock first. Same precedence as the seed
    # above, and for the same reason -- which is also the only reason
    # `seed` came out right while `candidate` did not: the marker holds
    # a literal `seed_XXXX` template that cmd_approve wrote verbatim
    # from --candidate, and nothing has ever checked it.
    lock_candidate = None
    if lock_file.exists():
        try:
            lock_candidate = json.loads(
                lock_file.read_text(encoding="utf-8")).get("candidate_id")
        except (OSError, ValueError):
            lock_candidate = None
    if (lock_candidate and selected_candidate
            and lock_candidate != selected_candidate):
        # SAY IT EVERY TIME. This has been true and silent since
        # 2026-08-13, and it only surfaced because someone opened the
        # archive and read the file it ended up in.
        print(f"[export] WARNING the candidate_selected marker and the functional lock disagree:", file=sys.stderr)
        print(f"[export]   marker: {selected_candidate}", file=sys.stderr)
        print(f"[export]   lock:   {lock_candidate}", file=sys.stderr)
        print(f"[export]   the lock wins for the export manifest; jobs are still resolved from the marker", file=sys.stderr)
    export_candidate = lock_candidate or selected_candidate
    factory_version, factory_tag, pinned_tools = _factory_pin()

    out_root = ws.internal_dir / "exports"
    repos = ws.load_tools_local().get("repositories", {})
    addon_sources = {name: Path(str(p)) for name, p in repos.items()}
    result = export_mission(
        mission_id=mission_id, handoff_dir=handoff_dir,
        presentation_dir=presentation_dir, source_dir=source_dir,
        themed_site_dir=(themed_site_dir if themed_site_dir.exists()
                         else None),
        profile=profile, tool_versions=_adapter_versions(), out_root=out_root,
        graybox_dir=graybox_dir, layers=frozenset(layers),
        addon_sources=addon_sources,
        composed_root=compose_root if compose_root.exists() else None,
        seed=export_seed, candidate_id=export_candidate,
        pinned_tools=pinned_tools,
        factory_version=factory_version, factory_tag=factory_tag,
    )
    if args.format == "zip":
        zip_export(result)
        print(f"exported {mission_id} [{args.mode}] -> {result.zip_path}")
    else:
        print(f"exported {mission_id} [{args.mode}] -> {result.export_dir}")
    return EXIT_OK


def cmd_portability_test(args) -> int:
    from packages.exporting.portability import run_portability_test
    ws = _ws(args)
    mission_id = args.mission_id
    tools_local = ws.load_tools_local()
    export_root = ws.internal_dir / "exports"
    # Default to the portable-godot export if a mode isn't given.
    mode = args.mode
    export_dir = export_root / export_build_dir_name(mission_id, mode)
    if not export_dir.exists():
        print(f"no export at {export_dir}; run 'export --mode {mode}' first",
              file=sys.stderr)
        return EXIT_BLOCKED

    report = run_portability_test(
        mission_id=mission_id, export_dir=export_dir, export_mode=mode,
        godot_executable=tools_local.get("godot_executable") or None,
        work_root=ws.temp_dir,
    )
    # Persist the report next to the export.
    (export_root / (export_build_dir_name(mission_id, mode)
                    + ".portability.json")).write_text(
        pretty_dumps(report.as_dict()), encoding="utf-8")
    print(pretty_dumps(report.as_dict()))
    return EXIT_OK if report.status == "PASS" else EXIT_BLOCKED
