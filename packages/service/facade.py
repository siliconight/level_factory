"""Application service layer (TDD 9.1).

The desktop UI calls these services; it never executes tool processes itself.
Every method returns plain dataclasses (asdict-able) so the Qt views are thin
bindings and the whole layer is testable headlessly.

Query methods read canonical state + the SQLite index directly. Action methods
(run/approve/select/export/portability) reuse the already-tested CLI command
implementations via a captured-args shim, so there is exactly one code path for
each side-effect.
"""
from __future__ import annotations

import io
import json
from contextlib import redirect_stdout, redirect_stderr
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import Sequence

from packages.project_store.workspace import Workspace, find_workspace
from packages.project_store.index import Index
from packages.core import states
from packages.pipeline.planner import (
    TARGET_FUNCTIONAL_LOCK, TARGET_PRESENTATION, TARGET_SHELL_HANDOFF,
)


# --------------------------------------------------------------------------
# View-model dataclasses
# --------------------------------------------------------------------------
@dataclass
class ActionResult:
    ok: bool
    exit_code: int
    output: str = ""

    @property
    def blocked(self) -> bool:
        return self.exit_code == 2


@dataclass
class DashboardRow:
    mission_id: str
    batch_id: str
    state: str
    running_job: str | None
    latest_validation: str
    blocker_count: int
    approved_gates: list[str]
    selected_candidate: str | None
    presentation_status: str
    handoff_status: str


@dataclass
class PipelineNode:
    job_id: str
    stage_id: str
    adapter_id: str
    state: str
    depends_on: list[str]
    candidate_id: str | None


@dataclass
class NodeDetail:
    job_id: str
    stage_id: str
    adapter_id: str
    state: str
    attempts: int
    command: str
    tool_version: str
    fingerprint: str
    log_tail: list[str]
    outputs: list[str]
    dependents: list[str]


@dataclass
class CandidateCard:
    candidate_id: str
    seed: int
    metrics: dict
    validation_summary: str
    blocker_count: int
    floorplan_path: str | None
    screenshot_path: str | None


@dataclass
class ArtPassSection:
    name: str
    status: str  # not_started | in_progress | done


@dataclass
class ValidationIssueRow:
    mission_id: str
    code: str
    severity: str
    category: str
    source_tool: str
    message: str
    blocking: bool


@dataclass
class JobConsole:
    job_id: str
    state: str
    command: str
    resource_class: str
    elapsed_seconds: float
    work_folder: str | None
    log_tail: list[str]


@dataclass
class HandoffRow:
    label: str
    status: str


@dataclass
class HandoffStatus:
    mission_id: str
    rows: list[HandoffRow]
    export_ready: bool
    available_actions: list[str]


# --------------------------------------------------------------------------
# Service
# --------------------------------------------------------------------------
_HANDOFF_ARTIFACTS = [
    ("Functional Geometry", "mission.tscn"),
    ("Collision", "mission.tscn"),
    ("Gameplay Anchors", "gameplay_anchors.json"),
    ("Stable Shell IDs", "mission_manifest.json"),
    ("Proposed Beat Graph", "proposed_beat_graph.json"),
    ("Runtime Ownership Requirements", "runtime_ownership_requirements.json"),
    ("Navigation Hints", "navigation_hints.json"),
]
_BY_DESIGN = [
    ("Gameplay Runtime", "Not Implemented by Design"),
    ("Networking", "Not Implemented by Design"),
    ("Enemy AI", "Not Implemented by Design"),
]
_ART_SECTIONS = [
    ("Shared Pixelcoat packs", "pixelcoat_build"),
    ("Zoo structural kit", "zoo_kit_build"),
    ("Patina theme and overrides", "patina_apply"),
    ("Zoo dressing", "zoo_dressing_build"),
    ("Lux profiles", "lux_apply"),
]


def _elapsed(rec) -> float:
    import datetime as _dt
    if not (rec.started_at and rec.finished_at):
        return 0.0
    try:
        a = _dt.datetime.fromisoformat(rec.started_at)
        b = _dt.datetime.fromisoformat(rec.finished_at)
        return max(0.0, (b - a).total_seconds())
    except ValueError:
        return 0.0


class FactoryService:
    def __init__(self, workspace: Workspace) -> None:
        self.ws = workspace

    # ---- construction helpers ------------------------------------------
    @classmethod
    def open(cls, root: Path) -> "FactoryService":
        return cls(find_workspace(Path(root)))

    def _index(self) -> Index:
        return Index(self.ws.index_db)

    def _job_out(self, job_id: str) -> Path:
        return self.ws.jobs_dir / job_id / "out"

    def _selected_candidate(self, mission_id: str) -> str | None:
        p = self.ws.internal_dir / "approvals" / f"{mission_id}.selected"
        return p.read_text(encoding="utf-8").strip() if p.exists() else None

    # ---- Setup wizard (27.1) -------------------------------------------
    def doctor(self) -> dict:
        from packages.tools.doctor import run_doctor
        from packages.adapters.registry import AdapterRegistry
        report = run_doctor(
            tools_local=self.ws.load_tools_local(),
            tools_lock=self.ws.load_tools_lock(),
            registry=AdapterRegistry(),
            workspace_writable=True,
        )
        return report.as_dict()

    def save_tools_local(self, data: dict) -> None:
        self.ws.write_json(self.ws.tools_local, data)

    def load_tools_local(self) -> dict:
        return self.ws.load_tools_local()

    # ---- Dashboard (27.2) ----------------------------------------------
    def _iter_missions(self) -> list[tuple[str, str]]:
        """(batch_id, mission_id) from canonical on-disk state (index-independent)."""
        out: list[tuple[str, str]] = []
        batches = self.ws.batches_dir
        if not batches.exists():
            return out
        for batch_dir in sorted(p for p in batches.iterdir() if p.is_dir()):
            missions_dir = batch_dir / "missions"
            if not missions_dir.exists():
                continue
            for mdir in sorted(p for p in missions_dir.iterdir() if p.is_dir()):
                out.append((batch_dir.name, mdir.name))
        return out

    def dashboard(self) -> list[DashboardRow]:
        index = self._index()
        rows: list[DashboardRow] = []
        for batch_id, mid in self._iter_missions():
            jobs = index.jobs_for_mission(mid)
            running = next((j.job_id for j in jobs if j.status == states.RUNNING), None)
            state = index.mission_state(mid) or "draft"
            vsummary, blockers = self._validation_summary(mid)
            pres = self._job_out(f"{mid}.lux_apply") / "lux.applied.tscn"
            handoff = self._job_out(f"{mid}.dispatch_handoff") / "mission.tscn"
            rows.append(DashboardRow(
                mission_id=mid, batch_id=batch_id,
                state=state, running_job=running,
                latest_validation=vsummary, blocker_count=blockers,
                approved_gates=self._approved_gates(mid),
                selected_candidate=self._selected_candidate(mid),
                presentation_status="ready" if pres.exists() else "pending",
                handoff_status="ready" if handoff.exists() else "pending",
            ))
        return rows

    def _approved_gates(self, mission_id: str) -> list[str]:
        from packages.approvals import gates
        store = gates.ApprovalStore(self.ws.internal_dir / "approvals")
        out = []
        for gate in gates.REQUIRED_GATES:
            appr = store.get(mission_id, gate)
            if appr is not None and appr.decision == gates.DECISION_APPROVED:
                out.append(gate)
        return out

    def _validation_summary(self, mission_id: str) -> tuple[str, int]:
        vfile = self.ws.internal_dir / "validation" / f"{mission_id}.json"
        if not vfile.exists():
            return ("no validation yet", 0)
        try:
            data = json.loads(vfile.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return ("unreadable", 0)
        issues = data.get("issues", [])
        blockers = sum(1 for i in issues if i.get("blocking"))
        return (f"{len(issues)} findings, {blockers} blocking", blockers)

    # ---- Mission brief editor (27.3) -----------------------------------
    def load_brief(self, batch_id: str, mission_id: str) -> dict:
        p = self.ws.mission_subdir(batch_id, mission_id, "brief") / "brief.json"
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}

    def validate_brief(self, brief: dict) -> list[str]:
        problems: list[str] = []
        for field_name in ("mission_id", "archetype", "candidate_count"):
            if not brief.get(field_name):
                problems.append(f"missing required field: {field_name}")
        cc = brief.get("candidate_count")
        if isinstance(cc, int) and not (1 <= cc <= 8):
            problems.append("candidate_count must be between 1 and 8")
        return problems

    def seed_preview(self, mission_id: str, seed_base: int, count: int) -> list[int]:
        from packages.pipeline.planner import derive_seeds
        return derive_seeds(seed_base, count)

    # ---- Pipeline view (27.4) ------------------------------------------
    def pipeline(self, mission_id: str, target: str = "presentation") -> list[PipelineNode]:
        _, _, plan = self._plan(mission_id, target)
        index = self._index()
        nodes: list[PipelineNode] = []
        for job in plan.graph.topological_order():
            rec = index.get_job(job.job_id)
            nodes.append(PipelineNode(
                job_id=job.job_id, stage_id=job.stage_id, adapter_id=job.adapter_id,
                state=(rec.status if rec else "PLANNED"),
                depends_on=list(job.depends_on), candidate_id=job.candidate_id,
            ))
        return nodes

    def node_detail(self, mission_id: str, job_id: str, target: str = "presentation") -> NodeDetail:
        _, _, plan = self._plan(mission_id, target)
        job = next((j for j in plan.graph.jobs() if j.job_id == job_id), None)
        rec = self._index().get_job(job_id)
        out_dir = self._job_out(job_id)
        outputs = ([p.name for p in sorted(out_dir.iterdir())] if out_dir.exists() else [])
        dependents = [j.job_id for j in (plan.graph.jobs() if plan else [])
                      if job_id in j.depends_on]
        return NodeDetail(
            job_id=job_id,
            stage_id=(job.stage_id if job else ""),
            adapter_id=(job.adapter_id if job else (rec.adapter_id if rec else "")),
            state=(rec.status if rec else "PLANNED"),
            attempts=(rec.attempt if rec else 0),
            command=(" ".join(rec.command) if rec and rec.command else ""),
            tool_version=(rec.tool_version if rec and getattr(rec, "tool_version", None) else ""),
            fingerprint=(rec.build_fingerprint if rec else ""),
            log_tail=self._log_tail(rec),
            outputs=outputs, dependents=dependents,
        )

    def _log_tail(self, rec, n: int = 40) -> list[str]:
        if rec and getattr(rec, "log_path", None) and Path(rec.log_path).exists():
            return Path(rec.log_path).read_text(
                encoding="utf-8", errors="replace").splitlines()[-n:]
        return []

    # ---- Candidate gallery (27.5) --------------------------------------
    def candidates(self, mission_id: str) -> list[CandidateCard]:
        _, batch, plan = self._plan(mission_id, TARGET_FUNCTIONAL_LOCK)
        cards: list[CandidateCard] = []
        for cand in plan.candidate_ids:
            seed = int(cand.rsplit("_", 1)[-1])
            lt_out = self._job_out(f"{mission_id}.laser_tag_evaluate.candidate.seed_{seed}")
            metrics: dict = {}
            score_json = lt_out / "score.json"
            if score_json.exists():
                try:
                    metrics = json.loads(score_json.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    metrics = {}
            lot_out = self._job_out(f"{mission_id}.lot_assemble.candidate.seed_{seed}")
            floor = lot_out / "floorplan.svg"
            shot = lot_out / "preview.png"
            cards.append(CandidateCard(
                candidate_id=cand, seed=seed, metrics=metrics,
                validation_summary=f"score {metrics.get('score', '-')}",
                blocker_count=0,
                floorplan_path=str(floor) if floor.exists() else None,
                screenshot_path=str(shot) if shot.exists() else None,
            ))
        return cards

    # ---- Art pass screen (27.6) ----------------------------------------
    def art_pass(self, mission_id: str) -> list[ArtPassSection]:
        sections: list[ArtPassSection] = []
        for name, stage in _ART_SECTIONS:
            out = self._job_out(f"{mission_id}.{stage}")
            status = "done" if out.exists() and any(out.iterdir()) else "not_started"
            sections.append(ArtPassSection(name=name, status=status))
        return sections

    # ---- Validation center (27.7) --------------------------------------
    def validation(self, mission_id: str | None = None,
                   severity: str | None = None) -> list[ValidationIssueRow]:
        vdir = self.ws.internal_dir / "validation"
        rows: list[ValidationIssueRow] = []
        if not vdir.exists():
            return rows
        files = ([vdir / f"{mission_id}.json"] if mission_id
                 else sorted(vdir.glob("*.json")))
        for vf in files:
            if not vf.exists():
                continue
            try:
                data = json.loads(vf.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            mid = data.get("mission_id", vf.stem)
            for i in data.get("issues", []):
                if severity and i.get("severity") != severity:
                    continue
                rows.append(ValidationIssueRow(
                    mission_id=mid, code=i.get("code", "?"),
                    severity=i.get("severity", "moderate"),
                    category=i.get("category", "general"),
                    source_tool=i.get("source_tool", "?"),
                    message=i.get("message", ""), blocking=bool(i.get("blocking")),
                ))
        return rows

    # ---- Job console (27.8) --------------------------------------------
    def job_console(self, job_id: str) -> JobConsole | None:
        rec = self._index().get_job(job_id)
        if rec is None:
            return None
        out_dir = self._job_out(job_id)
        return JobConsole(
            job_id=job_id, state=rec.status,
            command=" ".join(rec.command) if rec.command else "",
            resource_class=rec.resource_class or "",
            elapsed_seconds=_elapsed(rec),
            work_folder=str(out_dir) if out_dir.exists() else None,
            log_tail=self._log_tail(rec),
        )

    # ---- Handoff screen (27.9) -----------------------------------------
    def handoff(self, mission_id: str) -> HandoffStatus:
        out = self._job_out(f"{mission_id}.dispatch_handoff")
        rows: list[HandoffRow] = []
        all_ready = out.exists()
        for label, fname in _HANDOFF_ARTIFACTS:
            ready = (out / fname).exists()
            all_ready = all_ready and ready
            rows.append(HandoffRow(label=label, status="Ready" if ready else "Pending"))
        pres = self._job_out(f"{mission_id}.lux_apply") / "lux.applied.tscn"
        rows.append(HandoffRow(
            label="Presentation", status="Ready" if pres.exists() else "Pending"))
        for label, status in _BY_DESIGN:
            rows.append(HandoffRow(label=label, status=status))
        actions = ["Validate handoff", "Open in Godot"]
        if all_ready:
            actions += ["Select export mode", "Export folder", "Create deterministic ZIP",
                        "Run portability test", "Record final approval"]
        return HandoffStatus(
            mission_id=mission_id, rows=rows, export_ready=all_ready,
            available_actions=actions)

    # ---- Actions (reuse CLI command implementations) -------------------
    def _plan(self, mission_id: str, target: str):
        from apps.cli.commands import _plan_for
        _, batch, model, plan = _plan_for(self.ws, mission_id, self._target_name(target))
        return model, batch, plan

    @staticmethod
    def _target_name(target: str) -> str:
        return {
            TARGET_FUNCTIONAL_LOCK: "functional-lock",
            TARGET_SHELL_HANDOFF: "dispatch-handoff",
            TARGET_PRESENTATION: "presentation",
            "functional-lock": "functional-lock",
            "dispatch-handoff": "dispatch-handoff",
            "presentation": "presentation",
        }.get(target, "presentation")

    def _invoke(self, fn, **attrs) -> ActionResult:
        args = SimpleNamespace(chdir=str(self.ws.root), **attrs)
        buf, ebuf = io.StringIO(), io.StringIO()
        with redirect_stdout(buf), redirect_stderr(ebuf):
            code = fn(args)
        return ActionResult(ok=code in (0, 1), exit_code=int(code),
                            output=(buf.getvalue() + ebuf.getvalue()).strip())

    def run(self, mission_id: str, target: str = "presentation") -> ActionResult:
        from apps.cli.commands import cmd_run
        return self._invoke(cmd_run, mission_id=mission_id,
                            target=self._target_name(target))

    def run_batch(self, batch_id: str, target: str = "presentation") -> ActionResult:
        from apps.cli.commands import cmd_batch_run
        return self._invoke(cmd_batch_run, batch_id=batch_id,
                            target=self._target_name(target))

    def batch_report(self, batch_id: str) -> ActionResult:
        from apps.cli.commands import cmd_batch_report
        return self._invoke(cmd_batch_report, batch_id=batch_id, json=True)

    def team_sign(self, mission_id: str, gate: str, approver: str,
                  note: str = "") -> ActionResult:
        from apps.cli.commands import cmd_team_sign
        return self._invoke(cmd_team_sign, mission_id=mission_id, gate=gate,
                            by=approver, note=note)

    def team_status(self, mission_id: str, gate: str) -> dict:
        from packages.approvals.team import TeamApprovalStore
        from apps.cli.commands import _protected_inputs_for_gate
        protected = _protected_inputs_for_gate(self.ws, mission_id, gate)
        store = TeamApprovalStore(self.ws.internal_dir / "team_approvals")
        return store.status(mission_id, gate, protected).as_dict()

    def accept_exception(self, mission_id: str, issue: str, approver: str,
                         reason: str) -> ActionResult:
        from apps.cli.commands import cmd_accept_exception
        return self._invoke(cmd_accept_exception, mission_id=mission_id, issue=issue,
                            by=approver, reason=reason, expires=None, ticket=None)

    def visual_review(self, mission_id: str) -> ActionResult:
        from apps.cli.commands import cmd_review
        return self._invoke(cmd_review, mission_id=mission_id)

    def approve(self, mission_id: str, gate: str, *, by: str = "desktop",
                candidate: str | None = None, note: str = "") -> ActionResult:
        from apps.cli.commands import cmd_approve
        return self._invoke(cmd_approve, mission_id=mission_id, gate=gate,
                            by=by, candidate=candidate, note=note)

    def select_candidate(self, mission_id: str, candidate: str,
                         by: str = "desktop") -> ActionResult:
        from packages.approvals import gates
        return self.approve(mission_id, gates.CANDIDATE_SELECTED,
                            by=by, candidate=candidate)

    def export(self, mission_id: str, mode: str = "portable-godot",
               fmt: str = "folder") -> ActionResult:
        from apps.cli.commands import cmd_export
        return self._invoke(cmd_export, mission_id=mission_id, mode=mode, format=fmt)

    def portability_test(self, mission_id: str,
                         mode: str = "portable-godot") -> ActionResult:
        from apps.cli.commands import cmd_portability_test
        return self._invoke(cmd_portability_test, mission_id=mission_id, mode=mode)
