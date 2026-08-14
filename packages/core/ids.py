"""Identifier and slug helpers.

Ids are deterministic and human-legible. We never use random UUIDs for things
that should be reproducible from the same inputs (candidate ids, job ids).
"""
from __future__ import annotations

import datetime as _dt
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


#: What a name part says when its value could not be established.
#:
#: WRITTEN, NEVER OMITTED. Dropping the part would give one artifact two
#: grammars, and the reason docs/EXPORT_NAMING.md gives for the timestamp --
#: "fixed width, so it sorts" -- stops holding the moment a field before it
#: can vanish. It also says something true: `fNA` tells a recipient the
#: provenance was not recoverable, so no factory tag pins what they hold.
UNKNOWN_PART = "NA"

#: An ISO-8601 instant, loose about the input so `_now()`'s output and a
#: hand-written stamp both land in the same place.
_ISO_UTC = re.compile(
    r"(\d{4})-?(\d{2})-?(\d{2})[T ]?(\d{2}):?(\d{2}):?(\d{2})")


def compact_utc(raw: str) -> str:
    """`2026-08-14T20:32:26.869174+00:00` -> `20260814T203226Z`.

    ISO-8601 basic, because a colon is illegal in a Windows filename and
    this string goes into one. Fixed width, so a directory listing sorts
    chronologically without anybody parsing anything.
    """
    m = _ISO_UTC.search(str(raw or ""))
    if not m:
        raise ValueError(f"not an ISO-8601 instant: {raw!r}")
    return "{}{}{}T{}{}{}Z".format(*m.groups())


def export_package_dir_name(mission_id: str) -> str:
    """The folder INSIDE the archive -- the one a recipient drops in.

    STABLE ACROSS EXPORTS, and that is the whole specification. This
    folder becomes part of every `res://` path in the recipient's
    project, so a build time or a seed in it would move every reference
    they wrote the last time they took an update. Dropping a newer export
    over an older one has to overwrite in place.

    Which is also why the seed is NOT here: shipping a different
    candidate is an update to the same mission, not a second thing to
    keep side by side.
    """
    mid = str(mission_id).strip()
    if not mid:
        raise ValueError("mission id is empty")
    bad = sorted(set(mid) & _UNSAFE_IN_A_PATH)
    if bad or mid in (".", ".."):
        raise ValueError(
            f"mission id {mid!r} is not usable as a directory name "
            f"(it becomes the package root): {bad or mid}")
    return f"{EXPORT_PREFIX}_{mid}"


def export_archive_name(mission_id: str, *, profile_mode: str,
                        seed=None, built_utc: str | None = None,
                        factory_version: str | None = None) -> str:
    """`LF_<mission>_s<seed>_<utc>_f<factory>_<profile>.zip`

    The archive is what gets sent and stored, so it is fully qualified --
    the opposite requirement from the folder inside it. See
    docs/EXPORT_NAMING.md for why these are two names and not one.

    TIME BEFORE FACTORY VERSION, on purpose: within one mission and seed
    the name then sorts chronologically. The other order does not, because
    `f1.9.0` sorts after `f1.17.0` lexically, which would list a
    nine-month-old export as the newest.

    `seed` and `factory_version` may be None; each renders as `NA` rather
    than disappearing. `built_utc` defaults to now, but a caller that
    wants the name and a manifest to agree should pass the same instant
    to both.
    """
    mid = str(mission_id).strip()
    mode = str(profile_mode).strip()
    for label, value in (("mission id", mid), ("profile mode", mode)):
        if not value:
            raise ValueError(f"{label} is empty")
        bad = sorted(set(value) & _UNSAFE_IN_A_PATH)
        if bad or value in (".", ".."):
            raise ValueError(
                f"{label} {value!r} is not usable in a filename: "
                f"{bad or value}")

    def _part(label: str, value) -> str:
        if value is None or str(value).strip() == "":
            return UNKNOWN_PART
        s = str(value).strip()
        bad = sorted(set(s) & _UNSAFE_IN_A_PATH)
        if bad:
            raise ValueError(
                f"{label} {s!r} is not usable in a filename: {bad}")
        return s

    stamp = compact_utc(built_utc) if built_utc else compact_utc(
        _dt.datetime.now(_dt.timezone.utc).isoformat())
    return (f"{EXPORT_PREFIX}_{mid}"
            f"_s{_part('seed', seed)}"
            f"_{stamp}"
            f"_f{_part('factory version', factory_version)}"
            f"_{mode}.zip")


def namespaced_anchor(mission_id: str, anchor_id: str) -> str:
    if anchor_id.startswith(f"{mission_id}/"):
        return anchor_id
    return f"{mission_id}/{anchor_id}"
