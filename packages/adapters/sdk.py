"""Adapter SDK (TDD 17).

Every tool is integrated through a concrete adapter implementing this protocol.
The orchestrator never learns a tool's CLI directly; it only knows this shape.
That isolation (TDD 5.1, 44.1, 44.2) is the whole point of the adapter layer.
"""
from __future__ import annotations

import hashlib
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

    def advise_configuration(
        self, job_spec: Mapping[str, object], context: Mapping[str, object]
    ) -> Sequence[Mapping[str, object]]:
        """Findings about the inputs that are never a reason to refuse them.

        The companion to `validate_configuration`, and the split between the two
        is authority rather than subject. A refusal says the tool cannot produce
        information from these inputs -- the scene has no floor, the destination
        is sealed, the executable is not configured -- and spending the run
        would buy a report about nothing. An advisory says the tool will run
        fine and mark the result down, which is a design signal and belongs
        beside the score rather than in front of the build.

        Returns normalized finding dicts, the same shape `normalize_validation`
        speaks. The scheduler forces every one of them non-blocking, so an
        adapter cannot promote an advisory into a gate by mislabelling its
        severity; if something here really should stop a build, it belongs in
        `validate_configuration` where the reason travels with the refusal.
        """
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
        # Tools expose versions inconsistently. Try, cheapest first (no tool
        # execution): a VERSION file, then pyproject.toml, then a package
        # __version__. Returns the raw string; comparison normalizes the semver.
        vf = repo / "VERSION"
        if vf.exists():
            txt = vf.read_text(encoding="utf-8").strip()
            if txt:
                return txt
        import re as _re
        # A package __version__ (runtime truth) is preferred over pyproject,
        # whose packaging metadata can lag behind the shipped tool. Check the
        # common homes: <pkg>/__init__.py, <pkg>/version.py, <pkg>/_version.py.
        _vpat = _re.compile(r'(?m)^\s*__version__\s*=\s*["\']([^"\']+)["\']')
        for pattern in ("*/__init__.py", "*/version.py", "*/_version.py"):
            for mod in repo.glob(pattern):
                m = _vpat.search(mod.read_text(encoding="utf-8", errors="ignore"))
                if m:
                    return m.group(1)
        pp = repo / "pyproject.toml"
        if pp.exists():
            m = _re.search(r'(?m)^\s*version\s*=\s*["\']([^"\']+)["\']',
                           pp.read_text(encoding="utf-8"))
            if m:
                return m.group(1)
        return None

    # Cap on how much modified source is hashed into the dirty marker. A tool
    # repo's tracked sources are small; anything past this is not source.
    _DIRTY_BYTE_CAP = 8 * 1024 * 1024

    @staticmethod
    def _read_git_commit(repo: Path) -> str | None:
        """The tool revision a build will actually run: HEAD, plus a marker
        for uncommitted TRACKED changes.

        HEAD alone is not the revision that runs. Editing a tool's source
        changes its output while leaving HEAD where it was, so a fingerprint
        keyed on HEAD alone keeps serving the pre-edit artifact from cache
        until someone happens to commit -- silently, with no failure to
        notice. That is not hypothetical: a shell whose ladder slab-hole had
        been fixed to bias onto the approach side kept shipping the old
        symmetric cut (an unclimbable ladder) because the fix was staged on
        disk but not yet committed, and every rebuild cache-hit.

        Only TRACKED modifications count. Untracked files are deliberately
        excluded: pipelines write generated inputs (specs, work dirs) into
        tool repos, and folding those in would change the revision on every
        run and destroy caching altogether. The marker covers file CONTENT,
        not just names, so reverting an edit restores the original digest.
        """
        head = BaseAdapter._git(repo, "rev-parse", "HEAD")
        if head is None:
            return None
        # ``diff HEAD --name-only`` gives bare paths of tracked files that
        # differ from HEAD, staged or not, and excludes untracked ones by
        # construction -- unlike ``status --porcelain``, whose status column
        # has to be sliced off (and whose leading space is easy to lose).
        dirty = BaseAdapter._git(repo, "diff", "HEAD", "--name-only")
        if not dirty:
            return head
        h = hashlib.sha256()
        for rel in sorted(dirty.splitlines()):
            rel = rel.strip()
            if not rel:
                continue
            h.update(rel.encode("utf-8", "replace"))
            h.update(b"\0")
            path = repo / rel
            try:
                if path.is_file() and path.stat().st_size <= \
                        BaseAdapter._DIRTY_BYTE_CAP:
                    h.update(path.read_bytes())
                else:
                    h.update(b"<absent-or-oversized>")
            except OSError:
                h.update(b"<unreadable>")
        return f"{head}+dirty.{h.hexdigest()[:16]}"

    @staticmethod
    def _git(repo: Path, *args: str) -> str | None:
        try:
            out = subprocess.run(
                ["git", "-C", str(repo), *args],
                capture_output=True,
                text=True,
                timeout=20,
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
