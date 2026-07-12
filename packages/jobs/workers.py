"""Worker abstraction for distributed execution (TDD 42 Phase 5).

The scheduler executes jobs through a Worker. The default LocalWorker runs a job
in-process (the current behavior). A remote/distributed worker only needs to
transport a serializable JobEnvelope to another machine, run the same adapter
command there, and return a JobResult. This module defines that seam and a
FakeRemoteWorker used in tests; a real cloud transport is deferred (TDD 41.3),
so no network client ships here.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Protocol

from packages.core.models import Job


@dataclass
class JobEnvelope:
    """Everything a worker needs to run one job, independent of process/host."""
    job: Job
    job_spec: dict
    repository: str
    work_dir: str

    def as_dict(self) -> dict:
        return {
            "job": self.job.as_dict(),
            "job_spec": self.job_spec,
            "repository": self.repository,
            "work_dir": self.work_dir,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "JobEnvelope":
        return cls(job=Job(**d["job"]), job_spec=d["job_spec"],
                   repository=d["repository"], work_dir=d["work_dir"])


@dataclass
class JobResult:
    job_id: str
    status: str
    exit_code: int | None
    output_files: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return self.__dict__.copy()


class Worker(Protocol):
    name: str

    def run(self, envelope: JobEnvelope) -> JobResult: ...


@dataclass
class LocalWorker:
    """Runs a job in-process via a supplied execute function (the scheduler's)."""
    execute: Callable[[JobEnvelope], JobResult]
    name: str = "local"

    def run(self, envelope: JobEnvelope) -> JobResult:
        return self.execute(envelope)


@dataclass
class FakeRemoteWorker:
    """Round-trips the envelope through serialization (proving it's transport-
    ready) then delegates to a local execute — a stand-in for a real remote
    transport in tests."""
    execute: Callable[[JobEnvelope], JobResult]
    name: str = "fake-remote"

    def run(self, envelope: JobEnvelope) -> JobResult:
        # Prove the envelope survives a serialize/deserialize hop.
        round_tripped = JobEnvelope.from_dict(envelope.as_dict())
        return self.execute(round_tripped)
