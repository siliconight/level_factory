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
    #: A Deli Counter build directory to select the site's buildings FROM.
    #: Empty (the default) keeps the historical behaviour: one generated shell
    #: placed N times, which is roadmap item 37 -- a four-building site that is
    #: one building four times, with stairs and ladders landing identically in
    #: every one. Set it, and `_write_site_spec` picks N distinct archetypes
    #: from the library instead. Opt-in on purpose: re-placing a mission that
    #: has already been evaluated would be a different level carrying the old
    #: grade.
    lot_library: str = ""
    #: THE ENCOUNTER, which the brief could not previously express at all.
    #:
    #: Every mission Level Factory has ever evaluated was graded against Laser
    #: Tag's stock `default_laser_tag_scenario.tres`: one crew member with 5
    #: health against six enemies with 2 each. Measured on `lot_demo_001` seed
    #: 5118 over 50 runs, the crew must land twelve hits to clear the map, lands
    #: six to nine, and wipes 25 times out of 25. `route_completed` requires
    #: surviving the route, so traversal's 25 of 100 points were unreachable by
    #: any arrangement of geometry.
    #:
    #: DEFAULTS ARE THE STOCK NUMBERS on purpose. An existing brief produces a
    #: scenario identical to the one it was graded under, so no evaluated
    #: mission changes underneath its grade.
    #:
    #: Nothing here is derived from `building_count` or `target_minutes`. A crew
    #: size inferred from plate area would be a number nobody chose wearing the
    #: clothes of a decision; if a mission wants four people it says four.
    crew_size: int = 1
    crew_health: int = 5
    #: Lot still places six enemy hooks regardless (`place_enemies`' own
    #: default), and the harness spawns this many over the points it finds. Set
    #: it below six and the even spread along the route stops being even --
    #: wiring the count through to `_write_site_spec` is the follow-up.
    enemy_count: int = 6
    enemy_health: int = 2
    notes: str = ""

    def as_dict(self) -> dict:
        return _d(self)

    # The subset of the brief that functionally shapes geometry. Changes here
    # invalidate a functional lock; changes elsewhere (notes, weather) do not.
    def functional_signature(self) -> dict:
        sig = {
            "archetype": self.archetype,
            "building_count": self.building_count,
            "site_shape": self.site_shape,
            "route_shape": self.route_shape,
            "objective_hypotheses": list(self.objective_hypotheses),
            "extraction_relationship": self.extraction_relationship,
            "verticality": self.verticality,
            "landmark": self.landmark,
        }
        # WHICH BUILDINGS STAND ON THE SITE IS FUNCTIONAL -- it changes the
        # geometry, the routes and the cover, so it belongs in the lock.
        #
        # Added CONDITIONALLY, and that is the whole care in this method. An
        # unconditional key would change the signature of every brief ever
        # written, invalidating locks on missions nobody has touched, to record
        # that they still do not use a feature. A brief with no library keeps
        # the signature it has always had; the key's PRESENCE is the change.
        if self.lot_library:
            sig["lot_library"] = self.lot_library
        return sig


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
    #: WHICH BUILDING this job is for, when its stage runs once per building
    #: rather than once per mission.
    #:
    #: The art stages that bake a PLACEMENT -- patina dressing, zoo dressing,
    #: zoo fixtures -- position props against one specific shell's walls and
    #: roof. Planned once per mission, their single output was attached to
    #: every building in a varied lot: measured 2026-08-06, one dressing box of
    #: 30.4 x 8.4 x 22.4 inside five shells whose footprints ran from 26x20 to
    #: 46x32, standing up to 4.9 m above the roof it was supposed to sit under.
    #:
    #: `None` means the job is genuinely mission-wide. Pixelcoat's skin packs
    #: are: a skin is a material, not a dimension.
    #:
    #: `zoo_kit_build` was listed here as the example of one -- "a module
    #: LIBRARY ... resolves per slot at compose time and is correctly one job"
    #: -- and it is not. Every module but `wallEnd` is `fit: exact`, cut to ONE
    #: slot's dims. Measured 2026-08-09: one shared kit put 3.300 m walls in
    #: eight buildings whose slots asked 3.1 to 5.2, because the kit was built
    #: from the mission shell's `slots.json`. It fans out. See
    #: docs/PER_BUILDING_ART.md.
    archetype_id: str | None = None
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
