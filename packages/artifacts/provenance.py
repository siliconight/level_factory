"""Build fingerprints and provenance (TDD 12.10, 20.2, 21).

A build fingerprint is the deterministic identity of a job's *would-be* output.
If two jobs share a fingerprint, they must produce byte-identical artifacts, so
the fingerprint is the cache key.
"""
from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass, field
from typing import Any

from packages.core.hashing import hash_json


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat()


@dataclass(frozen=True)
class BuildFingerprint:
    adapter_id: str
    adapter_version: str
    tool_version: str | None
    repository_commit: str | None
    executable_versions: dict[str, str]
    normalized_arguments: list[str]
    input_hashes: dict[str, str]
    upstream_artifact_hashes: list[str]
    declared_environment: dict[str, str]
    seed: int | None
    schema_versions: dict[str, str]
    output_contract_version: str

    def digest(self) -> str:
        # Order-independent: hash_json sorts keys; lists are sorted where the
        # order is not semantically meaningful.
        payload = {
            "adapter_id": self.adapter_id,
            "adapter_version": self.adapter_version,
            "tool_version": self.tool_version,
            "repository_commit": self.repository_commit,
            "executable_versions": self.executable_versions,
            "normalized_arguments": self.normalized_arguments,
            "input_hashes": self.input_hashes,
            "upstream_artifact_hashes": sorted(self.upstream_artifact_hashes),
            "declared_environment": self.declared_environment,
            "seed": self.seed,
            "schema_versions": self.schema_versions,
            "output_contract_version": self.output_contract_version,
        }
        return hash_json(payload)

    def as_dict(self) -> dict:
        d = {
            "adapter_id": self.adapter_id,
            "adapter_version": self.adapter_version,
            "tool_version": self.tool_version,
            "repository_commit": self.repository_commit,
            "executable_versions": self.executable_versions,
            "normalized_arguments": self.normalized_arguments,
            "input_hashes": self.input_hashes,
            "upstream_artifact_hashes": sorted(self.upstream_artifact_hashes),
            "declared_environment": self.declared_environment,
            "seed": self.seed,
            "schema_versions": self.schema_versions,
            "output_contract_version": self.output_contract_version,
        }
        d["digest"] = self.digest()
        return d


@dataclass
class BuildLock:
    """The final handoff lock (TDD 21). Records everything needed to reproduce."""

    mission_id: str
    schema: str = "level_factory.build.lock.v0.1"
    tool_commits: dict[str, str | None] = field(default_factory=dict)
    adapter_versions: dict[str, str] = field(default_factory=dict)
    source_hashes: dict[str, str] = field(default_factory=dict)
    selected_seeds: dict[str, int] = field(default_factory=dict)
    approval_fingerprints: dict[str, str] = field(default_factory=dict)
    accepted_exceptions: list[dict] = field(default_factory=list)
    final_artifact_hashes: dict[str, str] = field(default_factory=dict)
    created_at: str = field(default_factory=_now)

    def as_dict(self) -> dict:
        return {
            "schema": self.schema,
            "mission_id": self.mission_id,
            "tool_commits": self.tool_commits,
            "adapter_versions": self.adapter_versions,
            "source_hashes": self.source_hashes,
            "selected_seeds": self.selected_seeds,
            "approval_fingerprints": self.approval_fingerprints,
            "accepted_exceptions": self.accepted_exceptions,
            "final_artifact_hashes": self.final_artifact_hashes,
            "created_at": self.created_at,
        }


def provenance_record(
    *,
    logical_name: str,
    tool: str,
    tool_version: str | None,
    repository_commit: str | None,
    adapter_version: str,
    job_id: str,
    inputs: list[dict[str, Any]],
    arguments: list[str],
    validation_status: str,
) -> dict:
    return {
        "schema": "level_factory.artifact.v0.1",
        "logical_name": logical_name,
        "produced_by": {
            "tool": tool,
            "tool_version": tool_version,
            "repository_commit": repository_commit,
            "adapter_version": adapter_version,
            "job_id": job_id,
        },
        "inputs": inputs,
        "command": {"arguments": arguments},
        "validation": {"status": validation_status},
        "created_at": _now(),
    }
