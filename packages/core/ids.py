"""Identifier and slug helpers.

Ids are deterministic and human-legible. We never use random UUIDs for things
that should be reproducible from the same inputs (candidate ids, job ids).
"""
from __future__ import annotations

import re

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def slugify(text: str) -> str:
    s = _SLUG_RE.sub("_", text.strip().lower()).strip("_")
    return s or "unnamed"


def candidate_id(mission_id: str, seed: int) -> str:
    return f"{mission_id}.candidate.seed_{seed}"


#: Segment that opens every candidate tail (`candidate.seed_1997`). An
#: archetype segment must never be this, or a job id stops being decodable by
#: eye -- which is the only way anyone reads these.
_CANDIDATE_SEGMENT = "candidate"

#: Characters that must never reach a job id, because job ids become job
#: DIRECTORIES (`scheduler.py` builds `jobs_dir / job_id / "out"`). A separator
#: or a drive colon would put a job's outputs somewhere nobody goes looking.
_UNSAFE_IN_A_PATH = set('/\\:*?"<>|') | set(" \t\r\n")


def job_id(mission_id: str, stage: str, *, candidate: str | None = None,
           archetype: str | None = None) -> str:
    """The id of one job: a mission, a stage, and optionally WHICH one.

    Two discriminators, and they answer different questions. `candidate` is
    which variant of the whole mission this is. `archetype` is which BUILDING
    within one mission this job is for -- the art stages that bake a placement
    against a specific shell need one job per building, and until this existed
    they could only be planned once per mission.

    Ids are used verbatim as directory names (the scheduler builds
    `jobs_dir / job_id / "out"`), so an archetype carrying a path separator
    would write outside its own job. That is refused here rather than
    sanitised: a silently rewritten id is a job whose outputs are somewhere
    nobody looks.
    """
    parts = [mission_id, stage]
    if candidate:
        # candidate ids already carry the mission prefix; keep the suffix only.
        parts.append(candidate.split(".", 1)[-1])
    if archetype:
        aid = str(archetype)
        if not aid.strip():
            raise ValueError("archetype id is empty")
        if aid == _CANDIDATE_SEGMENT:
            raise ValueError(
                f"archetype id {aid!r} collides with the candidate tail")
        bad = sorted(set(aid) & _UNSAFE_IN_A_PATH)
        if bad or aid in (".", ".."):
            raise ValueError(
                f"archetype id {aid!r} is not usable as a directory name "
                f"(job ids become job directories): {bad or aid}")
        parts.append(aid)
    return ".".join(parts)


#: The prefix every exported artifact carries. A level is the output of
#: the whole DAG -- Deli Counter shells, Zoo kits, Pixelcoat materials,
#: Patina wear, Lux light, Dispatch packaging, Lot assembly -- and naming
#: the result for the assembler tells a recipient the wrong thing about
#: what they have. See docs/EXPORT_NAMING.md.
EXPORT_PREFIX = "LF"


def export_build_dir_name(mission_id: str, profile_mode: str) -> str:
    """The workspace directory one export builds into.

    KEEPS THE PROFILE, unlike the folder that ends up inside the archive.
    The workspace holds `portable-godot` and `pure-shell` at the same
    time; give them one stable name and the second export silently
    overwrites the first. The folder a RECIPIENT drops in has the
    opposite requirement -- it must not change between exports, or every
    `res://` path in their project moves. One name cannot do both, which
    is why docs/EXPORT_NAMING.md specifies three.

    Refused rather than sanitised, for the reason `job_id` gives: this
    becomes a directory, and a silently rewritten name is output written
    somewhere nobody looks.
    """
    mid, mode = str(mission_id).strip(), str(profile_mode).strip()
    for label, value in (("mission id", mid), ("profile mode", mode)):
        if not value:
            raise ValueError(f"{label} is empty")
        bad = sorted(set(value) & _UNSAFE_IN_A_PATH)
        if bad or value in (".", ".."):
            raise ValueError(
                f"{label} {value!r} is not usable as a directory name "
                f"(the export becomes a directory): {bad or value}")
    return f"{EXPORT_PREFIX}_{mid}.{mode}"


def namespaced_anchor(mission_id: str, anchor_id: str) -> str:
    if anchor_id.startswith(f"{mission_id}/"):
        return anchor_id
    return f"{mission_id}/{anchor_id}"
