"""Source-control release helper (TDD 42 Phase 5).

A minimal, SAFE git integration: verify the working tree is clean, create an
annotated tag for a batch release, and record the commit + tag into release
provenance. It never pushes and never rewrites history — pushing stays a
deliberate human action (PR automation and remote SCM operations are deferred,
TDD 41.3).
"""
from __future__ import annotations

import datetime as _dt
import subprocess
from dataclasses import dataclass
from pathlib import Path

from packages.core.canonical import pretty_dumps


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat()


class ReleaseError(Exception):
    pass


def _git(repo: Path, *args: str) -> str:
    proc = subprocess.run(["git", "-C", str(repo), *args],
                          capture_output=True, text=True)
    if proc.returncode != 0:
        raise ReleaseError((proc.stderr or proc.stdout).strip())
    return proc.stdout.strip()


def is_clean(repo: Path) -> bool:
    try:
        return _git(repo, "status", "--porcelain") == ""
    except ReleaseError:
        return False


def current_commit(repo: Path) -> str | None:
    try:
        return _git(repo, "rev-parse", "HEAD")
    except ReleaseError:
        return None


@dataclass
class ReleaseRecord:
    batch_id: str
    tag: str
    commit: str
    created_at: str

    def as_dict(self) -> dict:
        return {"schema": "level_factory.release.v0.1", **self.__dict__}


def tag_release(repo: Path, *, batch_id: str, tag: str, message: str,
                require_clean: bool = True) -> ReleaseRecord:
    """Create an annotated tag for a batch release and return a record.

    Does not push. Raises if the tree is dirty (unless require_clean=False) or
    the tag already exists."""
    if require_clean and not is_clean(repo):
        raise ReleaseError("working tree is not clean; commit or stash first")
    existing = _git(repo, "tag", "--list", tag)
    if existing:
        raise ReleaseError(f"tag '{tag}' already exists")
    _git(repo, "tag", "-a", tag, "-m", message)
    commit = current_commit(repo) or ""
    return ReleaseRecord(batch_id=batch_id, tag=tag, commit=commit, created_at=_now())


def write_release_provenance(record: ReleaseRecord, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(pretty_dumps(record.as_dict()), encoding="utf-8")
    return dest
