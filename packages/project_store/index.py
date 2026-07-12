"""Rebuildable SQLite index (TDD 8.3, open decision 11: per-workspace).

The SQLite database is a *query accelerator*, never the source of truth. It can
be deleted and rebuilt from the canonical JSON at any time. Job records live
here because they are high-churn local state, not shareable project inputs.
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from packages.core.canonical import canonical_dumps
from packages.core.models import Job

_SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS missions (
    mission_id TEXT PRIMARY KEY,
    batch_id TEXT NOT NULL,
    state TEXT NOT NULL,
    updated_at TEXT
);
CREATE TABLE IF NOT EXISTS jobs (
    job_id TEXT PRIMARY KEY,
    mission_id TEXT NOT NULL,
    stage_id TEXT NOT NULL,
    adapter_id TEXT NOT NULL,
    candidate_id TEXT,
    status TEXT NOT NULL,
    attempt INTEGER NOT NULL DEFAULT 0,
    build_fingerprint TEXT,
    exit_code INTEGER,
    payload TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS jobs_by_mission ON jobs(mission_id);
CREATE INDEX IF NOT EXISTS jobs_by_status ON jobs(status);
CREATE TABLE IF NOT EXISTS artifacts (
    artifact_id TEXT PRIMARY KEY,
    logical_name TEXT NOT NULL,
    type TEXT NOT NULL,
    producing_job_id TEXT,
    payload TEXT NOT NULL
);
"""

SCHEMA_VERSION = "1"


class Index:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path))
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.execute(
            "INSERT OR IGNORE INTO meta(key, value) VALUES('schema_version', ?)",
            (SCHEMA_VERSION,),
        )
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    @contextmanager
    def tx(self) -> Iterator[sqlite3.Connection]:
        try:
            yield self._conn
            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise

    # ---- missions --------------------------------------------------------
    def upsert_mission(self, mission_id: str, batch_id: str, state: str, updated_at: str) -> None:
        with self.tx() as c:
            c.execute(
                "INSERT INTO missions(mission_id, batch_id, state, updated_at) "
                "VALUES(?,?,?,?) ON CONFLICT(mission_id) DO UPDATE SET "
                "batch_id=excluded.batch_id, state=excluded.state, updated_at=excluded.updated_at",
                (mission_id, batch_id, state, updated_at),
            )

    def mission_state(self, mission_id: str) -> str | None:
        row = self._conn.execute(
            "SELECT state FROM missions WHERE mission_id=?", (mission_id,)
        ).fetchone()
        return row["state"] if row else None

    def list_missions(self) -> list[dict]:
        rows = self._conn.execute(
            "SELECT mission_id, batch_id, state, updated_at FROM missions ORDER BY mission_id"
        ).fetchall()
        return [dict(r) for r in rows]

    # ---- jobs ------------------------------------------------------------
    def upsert_job(self, job: Job) -> None:
        with self.tx() as c:
            c.execute(
                "INSERT INTO jobs(job_id, mission_id, stage_id, adapter_id, candidate_id, "
                "status, attempt, build_fingerprint, exit_code, payload) "
                "VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(job_id) DO UPDATE SET "
                "status=excluded.status, attempt=excluded.attempt, "
                "build_fingerprint=excluded.build_fingerprint, exit_code=excluded.exit_code, "
                "payload=excluded.payload",
                (
                    job.job_id,
                    job.mission_id,
                    job.stage_id,
                    job.adapter_id,
                    job.candidate_id,
                    job.status,
                    job.attempt,
                    job.build_fingerprint,
                    job.exit_code,
                    canonical_dumps(job.as_dict()),
                ),
            )

    def get_job(self, job_id: str) -> Job | None:
        row = self._conn.execute(
            "SELECT payload FROM jobs WHERE job_id=?", (job_id,)
        ).fetchone()
        if not row:
            return None
        import json

        return Job(**json.loads(row["payload"]))

    def jobs_for_mission(self, mission_id: str) -> list[Job]:
        rows = self._conn.execute(
            "SELECT payload FROM jobs WHERE mission_id=? ORDER BY job_id", (mission_id,)
        ).fetchall()
        import json

        return [Job(**json.loads(r["payload"])) for r in rows]

    def unfinished_jobs(self, mission_id: str, resumable: frozenset[str]) -> list[Job]:
        placeholders = ",".join("?" for _ in resumable)
        rows = self._conn.execute(
            f"SELECT payload FROM jobs WHERE mission_id=? AND status IN ({placeholders})",
            (mission_id, *sorted(resumable)),
        ).fetchall()
        import json

        return [Job(**json.loads(r["payload"])) for r in rows]

    # ---- artifacts -------------------------------------------------------
    def upsert_artifact(self, artifact_id: str, logical_name: str, type_: str,
                        producing_job_id: str, payload: str) -> None:
        with self.tx() as c:
            c.execute(
                "INSERT INTO artifacts(artifact_id, logical_name, type, producing_job_id, payload) "
                "VALUES(?,?,?,?,?) ON CONFLICT(artifact_id) DO UPDATE SET "
                "logical_name=excluded.logical_name, type=excluded.type, "
                "producing_job_id=excluded.producing_job_id, payload=excluded.payload",
                (artifact_id, logical_name, type_, producing_job_id, payload),
            )
