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
from packages.core.ids import slugify
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


def _plan_for(ws: Workspace, mission_id: str, target: str):
    from packages.pipeline.planner import TARGET_PRESENTATION
    batch_id, brief = _find_mission(ws, mission_id)
    batch = _load_batch(ws, batch_id)
    model = _brief_model(brief)
    selected = _resolve_selected_candidate(ws, mission_id)
    target_map = {
        "functional-lock": TARGET_FUNCTIONAL_LOCK,
        "dispatch-handoff": TARGET_SHELL_HANDOFF,
        "presentation": TARGET_PRESENTATION,
    }
    plan = plan_mission(
        model,
        seed_base=int(batch.get("seed_base", 0)),
        target=target_map.get(target, TARGET_SHELL_HANDOFF),
        selected_candidate=selected,
    )
    return batch_id, batch, model, plan


def cmd_plan(args) -> int:
    ws = _ws(args)
    _, _, _, plan = _plan_for(ws, args.mission_id, args.target)
    if args.json:
        print(pretty_dumps(plan.as_dict()))
    else:
        print(f"plan for {plan.mission_id} (target={plan.target})")
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
            deli_job = job.depends_on[0]
            deli_out = jobs_dir / deli_job
            site_spec = _write_site_spec(ws, model, deli_out)
            specs[job.job_id] = {
                "site_spec_path": str(site_spec),
                "walkable": True,
                "building_glbs": [str(_latest_output(deli_out, "shell.glb"))],
            }
        elif job.adapter_id == "laser_tag":
            lot_job = job.depends_on[0]
            lot_out = jobs_dir / lot_job
            specs[job.job_id] = {
                "seed": int(job.candidate_id.rsplit("_", 1)[-1]),
                "run_count": 8,
                # Laser Tag evaluates the walkable candidate scene.
                "evaluation_scene": str(_latest_output(lot_out, "site_walk.tscn")),
            }
        elif job.adapter_id == "pixelcoat":
            recipe_path, source_path = _write_pixelcoat_recipe(ws, batch, model)
            specs[job.job_id] = {
                "recipe_path": str(recipe_path),
                "source_path": str(source_path),
                "asset_id": "theme",
            }
        elif job.adapter_id == "zoo":
            # Kit build depends on Lot(+Pixelcoat); dressing build depends on
            # Patina dressing(+Zoo kit). Distinguish by stage id.
            if job.stage_id == "zoo_dressing_build":
                dress_job = next(d for d in job.depends_on if "patina_dressing" in d)
                specs[job.job_id] = {
                    "mode": "dress",
                    "seed": int(str(job.candidate_id).rsplit("_", 1)[-1]),
                    "theme": model.theme or batch.get("theme_family", ""),
                    # Zoo --dress consumes Patina's <stem>.patina.dressing.json.
                    "manifest_path": str(_latest_output(jobs_dir / dress_job,
                                                        "shell.patina.dressing.json")),
                }
            else:
                pix_job = next((d for d in job.depends_on if "pixelcoat" in d), None)
                specs[job.job_id] = {
                    "mode": "kit",
                    "seed": int(str(job.candidate_id).rsplit("_", 1)[-1]),
                    "theme": model.theme or batch.get("theme_family", ""),
                    "slots_path": str(_lot_slots(ws, jobs_dir, job)),
                    "skins_dir": (str(_latest_output(jobs_dir / pix_job, "."))
                                  if pix_job else ""),
                }
        elif job.adapter_id == "patina":
            deli_glb = str(_latest_output(jobs_dir / _deli_for(plan, job), "shell.glb"))
            if job.stage_id == "patina_dressing":
                specs[job.job_id] = {
                    "input_glb": deli_glb,
                    "art_mode": "vertex-color",
                    "theme": model.theme or batch.get("theme_family", ""),
                    "dressing": True,
                    "panel_size": 1.2, "panel_gap": 0.03,
                }
            else:
                specs[job.job_id] = {
                    "input_glb": deli_glb,
                    "art_mode": "vertex-color",
                    "theme": model.theme or batch.get("theme_family", ""),
                }
        elif job.adapter_id == "lux":
            zoo_dress_job = job.depends_on[0]
            lot_job = next((j.job_id for j in plan.graph.jobs()
                            if j.stage_id == "lot_assemble"
                            and j.candidate_id == job.candidate_id), None)
            lights = (str(_latest_output(jobs_dir / _deli_for(plan, job), "shell.lights.json"))
                      if _deli_for(plan, job) else "")
            specs[job.job_id] = {
                "preset": _preset_for(model),
                "quality_tier": "standard",
                "composed_scene": str(_latest_output(jobs_dir / (lot_job or zoo_dress_job),
                                                     "site.tscn")),
                "lights_json": lights,
                "preview_states": ["calm", "alarm"],
            }
        elif job.adapter_id == "dispatch":
            dep = job.depends_on[0]
            # Prefer the Lot site for the dispatch spec inputs regardless of
            # whether dispatch depends on Lot (functional) or Lux (presentation).
            lot_job = next((j.job_id for j in plan.graph.jobs()
                            if j.stage_id == "lot_assemble"
                            and j.candidate_id == job.candidate_id), dep)
            lot_out = jobs_dir / lot_job
            spec_path = _write_dispatch_spec(ws, model, lot_out)
            specs[job.job_id] = {
                "mission_spec_path": str(spec_path),
                "mode": "shell-handoff",
                "inputs": {"site": str(_latest_output(lot_out, "site.tscn"))},
            }
    return specs


def _lot_slots(ws: Workspace, jobs_dir: Path, job) -> Path:
    """Slots.json for a presentation job's selected candidate (from the DC job)."""
    seed = str(job.candidate_id).rsplit("_", 1)[-1]
    deli_job = f"{job.mission_id}.deli_generate.candidate.seed_{seed}"
    return _latest_output(jobs_dir / deli_job, "shell.slots.json")


def _deli_for(plan, job):
    seed = str(job.candidate_id).rsplit("_", 1)[-1]
    return f"{job.mission_id}.deli_generate.candidate.seed_{seed}"


def _preset_for(model: MissionBrief) -> str:
    tod = (model.time_of_day or "").lower()
    if tod in ("night", "evening"):
        return "gothic_street_night"
    if tod == "afternoon":
        return "delco_summer_afternoon"
    return "blue_hour"


def _latest_output(job_root: Path, name: str) -> Path:
    """Path to a job's published output in its stable ``out/`` dir.

    The scheduler links every successful job's collected outputs into
    ``<jobs_dir>/<job_id>/out/`` so downstream jobs resolve them without
    knowing the attempt number.
    """
    return job_root / "out" / name


def _write_dispatch_spec(ws: Workspace, model: MissionBrief, lot_out: Path) -> Path:
    spec = {
        "schema": "dispatch.mission.v0.2",
        "mission_id": model.mission_id,
        "site_scene": str(_latest_output(lot_out, "site.tscn")),
        "gameplay": str(_latest_output(lot_out, "site.site.gameplay.json")),
        "lights": str(_latest_output(lot_out, "site.site.lights.json")),
        "mode": "shell-handoff",
    }
    dest = ws.internal_dir / "temp" / f"{model.mission_id}.dispatch.mission.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(pretty_dumps(spec), encoding="utf-8")
    return dest


def _write_site_spec(ws: Workspace, model: MissionBrief, deli_out: Path) -> Path:
    """Write a Lot site spec (named 'site.json' so Lot's stem-based outputs are
    canonical: site.tscn / site_walk.tscn / site.site.gameplay.json). References
    the Deli Counter building shell for this candidate."""
    spec = {
        "schema": "lot.site.v0.18",
        "site_id": model.mission_id,
        "site_shape": model.site_shape,
        "route_shape": model.route_shape,
        "target_minutes": list(model.target_minutes),
        "buildings": [{"id": "b0", "glb": str(_latest_output(deli_out, "shell.glb")),
                       "gameplay": str(_latest_output(deli_out, "shell.gameplay.json"))}],
    }
    dest = ws.internal_dir / "temp" / model.mission_id / "site.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(pretty_dumps(spec), encoding="utf-8")
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


def cmd_run(args) -> int:
    ws = _ws(args)
    index = _open_index(ws)
    batch_id, batch, model, plan = _plan_for(ws, args.mission_id, args.target)
    specs = _job_specs_for_plan(ws, batch, model, plan)
    scheduler = _build_scheduler(ws, index)

    summary = scheduler.run(plan.graph, job_specs=specs, mission_id=args.mission_id)

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

    agg = aggregate(summary.all_issues)
    print(f"\n{readiness_label(agg)}  "
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
        _, _, _, mplan = _plan_for(ws, brief.mission_id, batch_plan.target)
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

    target_map = {"functional-lock": TARGET_FUNCTIONAL_LOCK,
                  "dispatch-handoff": TARGET_SHELL_HANDOFF,
                  "presentation": TARGET_PRESENTATION}
    batch_plan = plan_batch(briefs, batch=batch,
                            selected_by_mission=selected,
                            target=target_map.get(args.target, TARGET_PRESENTATION))
    if not batch_plan.mission_ids:
        print("no missions ready to run (each needs a selected candidate)",
              file=sys.stderr)
        return EXIT_BLOCKED

    specs = _batch_job_specs(ws, batch, batch_plan)
    scheduler = _build_scheduler(ws, index)
    summary = scheduler.run(batch_plan.graph, job_specs=specs,
                            mission_id=f"batch:{args.batch_id}")

    # Persist per-mission validation for `validate` / reports.
    vdir = ws.internal_dir / "validation"; vdir.mkdir(parents=True, exist_ok=True)
    by_mission: dict[str, list] = {}
    for issue in summary.all_issues:
        by_mission.setdefault(getattr(issue, "mission_id", "") or "", []).append(issue.as_dict())
    for mid in batch_plan.mission_ids:
        (vdir / f"{mid}.json").write_text(
            pretty_dumps({"mission_id": mid, "issues": by_mission.get(mid, [])}),
            encoding="utf-8")

    print(f"batch {args.batch_id}: {len(batch_plan.mission_ids)} mission(s), "
          f"{len(batch_plan.shared_job_ids)} shared job(s)")
    cache_hits = sum(1 for o in summary.outcomes if o.cache_hit)
    print(f"  jobs: {len(summary.outcomes)}  (cache reuse: {cache_hits})")
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
        for m in index.list_missions():
            print(f"  {m['mission_id']:<32} {m['state']}")
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
    print(pretty_dumps(agg))
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


def _lock_path(ws: Workspace, mission_id: str) -> Path:
    return ws.internal_dir / "locks" / f"{mission_id}.json"


def _selected_lot_out(ws: Workspace, mission_id: str) -> Path | None:
    cand = _resolve_selected_candidate(ws, mission_id)
    if not cand:
        return None
    seed = cand.rsplit("_", 1)[-1]
    return ws.jobs_dir / f"{mission_id}.lot_assemble.candidate.seed_{seed}" / "out"


def _store_functional_lock(ws: Workspace, mission_id: str) -> None:
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
    p = _lock_path(ws, mission_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(pretty_dumps(lock.as_dict()), encoding="utf-8")


def cmd_approve(args) -> int:
    ws = _ws(args)
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


def cmd_export(args) -> int:
    from packages.exporting.export import (
        ExportProfile, MODE_PORTABLE, MODE_PURE_SHELL, MODE_SOURCE,
        export_mission, zip_export,
    )
    ws = _ws(args)
    mission_id = args.mission_id
    jobs_dir = ws.jobs_dir
    handoff_dir = jobs_dir / f"{mission_id}.dispatch_handoff" / "out"
    if not handoff_dir.exists():
        print(f"no dispatch handoff for {mission_id}; run --target dispatch-handoff first",
              file=sys.stderr)
        return EXIT_BLOCKED

    lux_dir = jobs_dir / f"{mission_id}.lux_apply" / "out"
    presentation_dir = lux_dir if lux_dir.exists() else None
    source_dir = None  # source-authoring would gather briefs/specs; omitted in MVP folder

    mode_map = {"portable-godot": MODE_PORTABLE, "pure-shell": MODE_PURE_SHELL,
                "source-authoring": MODE_SOURCE}
    profile = ExportProfile(mode=mode_map[args.mode])

    # Post-art regression: a functional drift after the art pass blocks export.
    lock_file = _lock_path(ws, mission_id)
    lot_out = _selected_lot_out(ws, mission_id)
    if lock_file.exists() and lot_out is not None:
        from packages.approvals.lock import FunctionalLock, verify_no_drift
        lock = FunctionalLock.from_dict(json.loads(lock_file.read_text(encoding="utf-8")))
        seed = lock.seed
        deli_out = ws.jobs_dir / f"{mission_id}.deli_generate.candidate.seed_{seed}" / "out"
        regression = verify_no_drift(
            lock, lot_out / "site.site.gameplay.json", deli_out / "shell.gameplay.json")
        if not regression.passed:
            print("export blocked by functional regression:", file=sys.stderr)
            for d in regression.drift:
                print(f"  - {d}", file=sys.stderr)
            return EXIT_BLOCKED

    out_root = ws.internal_dir / "exports"
    result = export_mission(
        mission_id=mission_id, handoff_dir=handoff_dir,
        presentation_dir=presentation_dir, source_dir=source_dir,
        profile=profile, tool_versions=_adapter_versions(), out_root=out_root,
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
    export_dir = export_root / f"{mission_id}.{mode}"
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
    (export_root / f"{mission_id}.{mode}.portability.json").write_text(
        pretty_dumps(report.as_dict()), encoding="utf-8")
    print(pretty_dumps(report.as_dict()))
    return EXIT_OK if report.status == "PASS" else EXIT_BLOCKED
