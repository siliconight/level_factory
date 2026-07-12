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
from packages.core.ids import slugify
from packages.core.models import MissionBrief
from packages.jobs.scheduler import Scheduler
from packages.pipeline.planner import (
    TARGET_FUNCTIONAL_LOCK, TARGET_SHELL_HANDOFF, plan_mission,
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
    batch_id, brief = _find_mission(ws, mission_id)
    batch = _load_batch(ws, batch_id)
    model = _brief_model(brief)
    selected = _resolve_selected_candidate(ws, mission_id)
    plan = plan_mission(
        model,
        seed_base=int(batch.get("seed_base", 0)),
        target=(TARGET_FUNCTIONAL_LOCK if target == "functional-lock" else TARGET_SHELL_HANDOFF),
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
                "seed": int(job.candidate_id.rsplit("_", 1)[-1]),
                "archetype": model.archetype,
                "theme": model.theme or batch.get("theme_family", ""),
                "output_formats": ["glb"],
            }
        elif job.adapter_id == "lot":
            deli_job = job.depends_on[0]
            deli_out = jobs_dir / deli_job
            specs[job.job_id] = {
                "site_shape": model.site_shape,
                "route_shape": model.route_shape,
                "target_minutes": list(model.target_minutes),
                "building_glbs": [str(_latest_output(deli_out, "shell.glb"))],
                "lights_jsons": [str(_latest_output(deli_out, "shell.lights.json"))],
            }
        elif job.adapter_id == "laser_tag":
            lot_job = job.depends_on[0]
            lot_out = jobs_dir / lot_job
            specs[job.job_id] = {
                "seed": int(job.candidate_id.rsplit("_", 1)[-1]),
                "run_count": 8,
                "evaluation_scene": str(_latest_output(lot_out, "site.tscn")),
            }
        elif job.adapter_id == "dispatch":
            lot_job = job.depends_on[0]
            lot_out = jobs_dir / lot_job
            spec_path = _write_dispatch_spec(ws, model, lot_out)
            specs[job.job_id] = {
                "mission_spec_path": str(spec_path),
                "mode": "shell-handoff",
                "inputs": {"site": str(_latest_output(lot_out, "site.tscn"))},
            }
    return specs


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
        "gameplay": str(_latest_output(lot_out, "site.gameplay.json")),
        "nav_hints": str(_latest_output(lot_out, "site.nav_hints.json")),
        "mode": "shell-handoff",
    }
    dest = ws.internal_dir / "temp" / f"{model.mission_id}.dispatch.mission.json"
    dest.write_text(pretty_dumps(spec), encoding="utf-8")
    return dest


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
