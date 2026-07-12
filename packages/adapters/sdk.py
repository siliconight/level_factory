"""Adapter SDK (TDD 17).

Every tool is integrated through a concrete adapter implementing this protocol.
The orchestrator never learns a tool's CLI directly; it only knows this shape.
That isolation (TDD 5.1, 44.1, 44.2) is the whole point of the adapter layer.
"""
from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Mapping, Protocol, Sequence, runtime_checkable


@dataclass(frozen=True)
class ToolProbe:
    available: bool
    tool_version: str | None
    repository_commit: str | None
    executable_versions: Mapping[str, str]
    capabilities: frozenset[str]
    problems: tuple[str, ...] = ()

    def as_dict(self) -> dict:
        return {
            "available": self.available,
            "tool_version": self.tool_version,
            "repository_commit": self.repository_commit,
            "executable_versions": dict(self.executable_versions),
            "capabilities": sorted(self.capabilities),
            "problems": list(self.problems),
        }


@dataclass(frozen=True)
class PlannedCommand:
    executable: Path
    arguments: tuple[str, ...]
    working_directory: Path
    environment: Mapping[str, str] = field(default_factory=dict)
    expected_outputs: tuple[str, ...] = ()
    resource_class: str = "lightweight"
    timeout_seconds: int | None = None

    def argv(self) -> list[str]:
        return [str(self.executable), *self.arguments]

    def as_dict(self) -> dict:
        return {
            "executable": str(self.executable),
            "arguments": list(self.arguments),
            "working_directory": str(self.working_directory),
            "environment": dict(self.environment),
            "expected_outputs": list(self.expected_outputs),
            "resource_class": self.resource_class,
            "timeout_seconds": self.timeout_seconds,
        }


@runtime_checkable
class ToolAdapter(Protocol):
    adapter_id: str
    adapter_version: str

    def probe(self, installation: Mapping[str, str]) -> ToolProbe: ...

    def validate_configuration(
        self, job_spec: Mapping[str, object], context: Mapping[str, object]
    ) -> Sequence[str]: ...

    def fingerprint_inputs(
        self, job_spec: Mapping[str, object], context: Mapping[str, object]
    ) -> Mapping[str, object]: ...

    def plan_commands(
        self, job_spec: Mapping[str, object], context: Mapping[str, object]
    ) -> Sequence[PlannedCommand]: ...

    def collect_outputs(
        self, job_spec: Mapping[str, object], context: Mapping[str, object]
    ) -> Iterable[Path]: ...

    def normalize_validation(
        self, output_paths: Sequence[Path]
    ) -> Sequence[Mapping[str, object]]: ...


class BaseAdapter:
    """Common machinery shared by concrete adapters.

    Concrete adapters set ``adapter_id`` / ``adapter_version`` / ``capabilities``
    and implement ``plan_commands``. The rest have workable defaults.
    """

    adapter_id: str = "base"
    adapter_version: str = "0.0.0"
    capabilities: frozenset[str] = frozenset()

    # ---- probing ---------------------------------------------------------
    def probe(self, installation: Mapping[str, str]) -> ToolProbe:
        repo = installation.get("repository")
        if not repo or not Path(repo).exists():
            return ToolProbe(
                available=False,
                tool_version=None,
                repository_commit=None,
                executable_versions={},
                capabilities=self.capabilities,
                problems=(f"repository path missing for '{self.adapter_id}'",),
            )
        return ToolProbe(
            available=True,
            tool_version=self._read_tool_version(Path(repo)),
            repository_commit=self._read_git_commit(Path(repo)),
            executable_versions={},
            capabilities=self.capabilities,
        )

    def validate_configuration(
        self, job_spec: Mapping[str, object], context: Mapping[str, object]
    ) -> Sequence[str]:
        return []

    def fingerprint_inputs(
        self, job_spec: Mapping[str, object], context: Mapping[str, object]
    ) -> Mapping[str, object]:
        # Default: the whole job spec participates in the fingerprint. Adapters
        # override to exclude non-deterministic or irrelevant fields.
        return {"job_spec": dict(job_spec)}

    def plan_commands(
        self, job_spec: Mapping[str, object], context: Mapping[str, object]
    ) -> Sequence[PlannedCommand]:  # pragma: no cover - abstract
        raise NotImplementedError

    def collect_outputs(
        self, job_spec: Mapping[str, object], context: Mapping[str, object]
    ) -> Iterable[Path]:
        work = Path(str(context["work_dir"]))
        return sorted(p for p in work.rglob("*") if p.is_file())

    def normalize_validation(
        self, output_paths: Sequence[Path]
    ) -> Sequence[Mapping[str, object]]:
        return []

    # ---- helpers ---------------------------------------------------------
    @staticmethod
    def _read_tool_version(repo: Path) -> str | None:
        vf = repo / "VERSION"
        if vf.exists():
            return vf.read_text(encoding="utf-8").strip()
        return None

    @staticmethod
    def _read_git_commit(repo: Path) -> str | None:
        try:
            out = subprocess.run(
                ["git", "-C", str(repo), "rev-parse", "HEAD"],
                capture_output=True,
                text=True,
                timeout=10,
            )
        except (OSError, subprocess.SubprocessError):
            return None
        if out.returncode != 0:
            return None
        return out.stdout.strip() or None

    @staticmethod
    def run_contract_probe(argv: Sequence[str], cwd: Path | None = None) -> dict | None:
        """Run a tool's machine-readable ``contract`` command (Dispatch D12).

        Returns the parsed JSON, or ``None`` if the tool doesn't support it.
        This is the pattern every pipeline tool should copy so adapters read a
        contract instead of scraping human prose (TDD Phase 0).
        """
        try:
            out = subprocess.run(
                list(argv),
                capture_output=True,
                text=True,
                timeout=30,
                cwd=str(cwd) if cwd else None,
            )
        except (OSError, subprocess.SubprocessError):
            return None
        if out.returncode != 0 or not out.stdout.strip():
            return None
        try:
            return json.loads(out.stdout)
        except json.JSONDecodeError:
            return None
