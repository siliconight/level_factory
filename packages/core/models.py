"""Domain model (TDD 12).

These are plain, serializable dataclasses. Business logic lives in the packages
that operate on them (planner, scheduler, cache, approvals); the models stay
dumb so the JSON on disk stays the canonical source of truth (TDD 5.2).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from packages.core import states

SCHEMA_PROJECT = "level_factory.project.v0.1"
SCHEMA_BATCH = "level_factory.batch.v0.1"
SCHEMA_BRIEF = "level_factory.mission_brief.v0.1"
SCHEMA_PLAN = "level_factory.pipeline_plan.v0.1"
SCHEMA_ARTIFACT = "level_factory.artifact.v0.1"
SCHEMA_ISSUE = "level_factory.validation_issue.v0.1"
SCHEMA_APPROVAL = "level_factory.approval.v0.1"
SCHEMA_BUILD_LOCK = "level_factory.build.lock.v0.1"


def _d(obj: Any) -> dict:
    return asdict(obj)


@dataclass
class FactoryProject:
    project_id: str
    name: str
    schema_version: str = SCHEMA_PROJECT
    created_at: str = ""
    default_engine_version: str = "4.7"
    default_candidate_count: int = 3
    default_target_minutes: tuple[int, int] = (25, 35)
    default_player_count: int = 4
    batch_ids: list[str] = field(default_factory=list)
    shared_theme_ids: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return _d(self)


@dataclass
class Batch:
    batch_id: str
    name: str
    mission_ids: list[str] = field(default_factory=list)
    theme_family: str = ""
    seed_base: int = 0
    candidate_count: int = 3
    target_minutes: tuple[int, int] = (25, 35)
    status: str = "draft"
    created_at: str = ""
    approved_at: str | None = None

    def as_dict(self) -> dict:
        return _d(self)


@dataclass
class MissionBrief:
    mission_id: str
    display_name: str
    archetype: str = ""
    building_count: int = 1
    site_shape: str = ""
    route_shape: str = ""
    objective_hypotheses: list[str] = field(default_factory=list)
    extraction_relationship: str = ""
    verticality: str = "medium"
    landmark: str = ""
    time_of_day: str = "afternoon"
    weather: str = "clear"
    theme: str = ""
    seed_policy: str = "derived"
    candidate_count: int = 3
    target_minutes: tuple[int, int] = (25, 35)
    notes: str = ""

    def as_dict(self) -> dict:
        return _d(self)

    # The subset of the brief that functionally shapes geometry. Changes here
    # invalidate a functional lock; changes elsewhere (notes, weather) do not.
    def functional_signature(self) -> dict:
        return {
            "archetype": self.archetype,
            "building_count": self.building_count,
            "site_shape": self.site_shape,
            "route_shape": self.route_shape,
            "objective_hypotheses": list(self.objective_hypotheses),
            "extraction_relationship": self.extraction_relationship,
            "verticality": self.verticality,
            "landmark": self.landmark,
        }


@dataclass
class Candidate:
    candidate_id: str
    mission_id: str
    seed: int
    building_artifact_ids: list[str] = field(default_factory=list)
    site_artifact_id: str | None = None
    metrics: dict[str, Any] = field(default_factory=dict)
    validation_summary: dict[str, Any] = field(default_factory=dict)
    preview_artifact_ids: list[str] = field(default_factory=list)
    status: str = "generated"
    selected: bool = False
    rejection_reason: str | None = None

    def as_dict(self) -> dict:
        return _d(self)


@dataclass
class Artifact:
    artifact_id: str  # sha256:<hex> content address
    type: str
    logical_name: str
    content_hash: str
    size_bytes: int
    source_path: str
    cache_path: str
    producing_job_id: str
    tool_id: str
    tool_version: str | None = None
    tool_commit: str | None = None
    input_artifact_ids: list[str] = field(default_factory=list)
    created_at: str = ""
    validation_status: str = "unknown"

    def as_dict(self) -> dict:
        return _d(self)


@dataclass
class Job:
    job_id: str
    mission_id: str
    stage_id: str
    adapter_id: str
    candidate_id: str | None = None
    status: str = states.PLANNED
    attempt: int = 0
    priority: int = 0
    resource_class: str = "lightweight"
    depends_on: list[str] = field(default_factory=list)
    command: list[str] = field(default_factory=list)
    working_directory: str = ""
    environment_fingerprint: str = ""
    input_fingerprint: str = ""
    build_fingerprint: str = ""
    started_at: str | None = None
    finished_at: str | None = None
    exit_code: int | None = None
    log_path: str | None = None
    artifact_ids: list[str] = field(default_factory=list)
    expected_outputs: list[str] = field(default_factory=list)
    failure: dict | None = None

    def as_dict(self) -> dict:
        return _d(self)


@dataclass
class ValidationIssue:
    issue_id: str
    source_tool: str
    mission_id: str
    severity: str
    category: str
    code: str
    message: str
    schema: str = SCHEMA_ISSUE
    candidate_id: str | None = None
    stage_id: str | None = None
    suggested_fix: str = ""
    location: str = ""
    related_shell_ids: list[str] = field(default_factory=list)
    blocking: bool = False
    raw_source_path: str | None = None

    def as_dict(self) -> dict:
        return _d(self)


@dataclass
class Approval:
    approval_id: str
    mission_id: str
    gate: str
    decision: str  # approved | rejected
    approved_by: str
    timestamp: str
    artifact_fingerprint: str
    schema: str = SCHEMA_APPROVAL
    notes: str = ""
    accepted_issue_ids: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return _d(self)
