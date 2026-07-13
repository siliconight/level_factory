"""Job scheduler and executor (TDD 15-21 wired together).

Executes a planned DAG in topological order, honoring resource-class
concurrency limits. Independent jobs run in parallel up to the per-class
caps (TDD 19.2); dependent jobs wait for their inputs. For each job it:

1. builds the adapter context and validates configuration (no silent fixes)
2. computes the build fingerprint and checks the content-addressed cache
3. on a miss, runs the planned command(s) in an isolated per-attempt work dir
4. verifies the expected-output contract, hashes artifacts, publishes to cache
5. normalizes tool validation into the shared model
6. blocks the job if any normalized issue is a blocker (validation_blocker)

Resume: unfinished jobs are re-derived from the plan; SUCCEEDED /
SKIPPED_CACHE_HIT jobs are skipped, so re-running ``run`` after a crash picks
up where it left off (Phase-1 exit criterion).
"""
from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping

from packages.adapters.registry import AdapterRegistry
from packages.artifacts.cache import ContentCache
from packages.artifacts.provenance import BuildFingerprint, provenance_record
from packages.core import states
from packages.core.canonical import pretty_dumps
from packages.core.errors import (
    Failure, INPUT_VALIDATION_ERROR, OUTPUT_CONTRACT_ERROR, TOOL_EXIT_FAILURE,
    VALIDATION_BLOCKER, is_transient_eligible,
)
from packages.core.hashing import hash_file, hash_json
from packages.core.models import Artifact, Job
from packages.jobs.runner import Cancellation, run_command
from packages.pipeline.graph import JobGraph
from packages.project_store.index import Index
from packages.validation.model import issue_from_normalized

# Default per-resource-class concurrency caps (TDD 19.2).
DEFAULT_CONCURRENCY = {
    "python_cpu": 4, "blender": 1, "godot_headless": 2,
    "godot_interactive": 1, "io_heavy": 2, "lightweight": 8,
}

MAX_TRANSIENT_RETRIES = 1


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat()


@dataclass
class JobOutcome:
    job: Job
    cache_hit: bool = False
    issues: list = field(default_factory=list)
    artifacts: list = field(default_factory=list)


@dataclass
class RunSummary:
    mission_id: str
    outcomes: list = field(default_factory=list)
    blocked_job: str | None = None
    all_issues: list = field(default_factory=list)

    @property
    def succeeded(self) -> bool:
        return self.blocked_job is None and all(
            states.job_succeeded(o.job.status) for o in self.outcomes
        )


class Scheduler:
    def __init__(
        self,
        *,
        index: Index,
        cache: ContentCache,
        registry: AdapterRegistry,
        jobs_dir: Path,
        installation: Mapping[str, str],
        godot_project: Path | None = None,
        concurrency: Mapping[str, int] | None = None,
    ) -> None:
        self.index = index
        self.cache = cache
        self.registry = registry
        self.jobs_dir = jobs_dir
        self.installation = dict(installation)
        self.godot_project = godot_project
        self.concurrency = dict(concurrency or DEFAULT_CONCURRENCY)

    # ------------------------------------------------------------------
    def run(
        self,
        graph: JobGraph,
        *,
        job_specs: Mapping[str, dict],
        mission_id: str,
        cancel: Cancellation | None = None,
    ) -> RunSummary:
        """Execute the DAG with real parallelism, honoring per-resource-class
        concurrency caps (TDD 19.2). Independent jobs run concurrently; a job
        starts only once all its dependencies have succeeded. On the first
        failure the scheduler stops dispatching new work and drains in-flight
        jobs (fail-fast, matching the sequential contract). Resumes by honoring
        already-terminal successes recorded in the index."""
        from collections import Counter, deque
        from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait

        summary = RunSummary(mission_id=mission_id)
        order = graph.topological_order()
        jobs_by_id = {j.job_id: j for j in order}
        remaining: dict[str, set[str]] = {
            jid: set(j.depends_on) for jid, j in jobs_by_id.items()
        }
        completed: set[str] = set()

        # Resume: pre-mark already-succeeded jobs and drop them from deps.
        for jid, job in jobs_by_id.items():
            existing = self.index.get_job(jid)
            if existing and states.job_succeeded(existing.status):
                completed.add(jid)
                summary.outcomes.append(JobOutcome(
                    job=existing,
                    cache_hit=existing.status == states.SKIPPED_CACHE_HIT))
        for deps in remaining.values():
            deps -= completed

        ready: deque[str] = deque(
            jid for jid in jobs_by_id
            if jid not in completed and not remaining[jid]
        )
        running: Counter = Counter()
        stop = False
        max_workers = max(1, sum(self.concurrency.values()))

        with ThreadPoolExecutor(max_workers=max_workers) as ex:
            futures: dict = {}
            while (ready or futures):
                # Dispatch every ready job that fits under its class cap.
                if not stop:
                    deferred: deque[str] = deque()
                    while ready:
                        jid = ready.popleft()
                        cls = jobs_by_id[jid].resource_class
                        cap = self.concurrency.get(cls, 1)
                        if running[cls] < cap:
                            running[cls] += 1
                            fut = ex.submit(self._execute_job, jobs_by_id[jid],
                                            job_specs.get(jid, {}), cancel)
                            futures[fut] = jid
                        else:
                            deferred.append(jid)
                    ready = deferred

                if not futures:
                    break  # nothing running and nothing dispatchable

                done, _ = wait(futures, return_when=FIRST_COMPLETED)
                for fut in done:
                    jid = futures.pop(fut)
                    cls = jobs_by_id[jid].resource_class
                    running[cls] -= 1
                    outcome = fut.result()
                    summary.outcomes.append(outcome)
                    summary.all_issues.extend(outcome.issues)
                    if states.job_succeeded(outcome.job.status):
                        completed.add(jid)
                        for other, deps in remaining.items():
                            if jid in deps:
                                deps.discard(jid)
                                if (other not in completed and not deps
                                        and other not in ready
                                        and other not in futures.values()):
                                    ready.append(other)
                    else:
                        summary.blocked_job = summary.blocked_job or jid
                        stop = True  # fail-fast; drain remaining in-flight jobs

        return summary

    # ------------------------------------------------------------------
    def _stable_out(self, job_id: str) -> Path:
        """Canonical, attempt-independent location for a job's published outputs."""
        return self.jobs_dir / job_id / "out"

    def _publish_stable(self, job_id: str, work_dir: Path, outputs: list[Path]) -> None:
        """Link a job's collected outputs into its stable ``out/`` dir so
        downstream jobs resolve them without knowing the attempt number."""
        import os as _os
        import shutil as _shutil

        stable = self._stable_out(job_id)
        stable.mkdir(parents=True, exist_ok=True)
        for src in outputs:
            rel = src.relative_to(work_dir)
            dst = stable / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            if dst.exists():
                dst.unlink()
            try:
                _os.link(src, dst)
            except OSError:
                _shutil.copy2(src, dst)

    def _execute_job(self, job: Job, job_spec: dict, cancel: Cancellation | None) -> JobOutcome:
        adapter = self.registry.get(job.adapter_id)
        repo = self.installation.get("repositories", {}).get(job.adapter_id, "")
        # First execution is attempt 1; retries increment before recursing.
        if job.attempt == 0:
            job.attempt = 1
        work_dir = self.jobs_dir / job.job_id / str(job.attempt) / "out"
        work_dir.mkdir(parents=True, exist_ok=True)

        context = {
            "repository": repo,
            "work_dir": str(work_dir),
            "blender_executable": self.installation.get("blender_executable", ""),
            "godot_executable": self.installation.get("godot_executable", ""),
            "python_executable": self.installation.get("python_executable", "") or "python3",
            "godot_project": str(self.godot_project or work_dir),
        }

        # 1. Validate configuration -- no silent fixes (TDD 5.4).
        problems = list(adapter.validate_configuration(job_spec, context))
        if problems:
            return self._fail(job, INPUT_VALIDATION_ERROR, "; ".join(problems))

        # 2. Build fingerprint + cache lookup.
        probe = adapter.probe({"repository": repo, **self.installation})
        raw_inputs = dict(adapter.fingerprint_inputs(job_spec, context))
        planned = list(adapter.plan_commands(job_spec, context))
        args = [a for cmd in planned for a in cmd.argv()]
        fp = BuildFingerprint(
            adapter_id=adapter.adapter_id,
            adapter_version=adapter.adapter_version,
            tool_version=probe.tool_version,
            repository_commit=probe.repository_commit,
            executable_versions=dict(probe.executable_versions),
            normalized_arguments=[a for a in args if not a.startswith(str(self.jobs_dir))],
            # Fold the ENTIRE declared input set (including nested content hashes)
            # into one digest so any input change invalidates the cache entry.
            input_hashes={"inputs_digest": hash_json(raw_inputs)},
            upstream_artifact_hashes=list(job_spec.get("upstream_hashes", [])),
            declared_environment=dict(planned[0].environment) if planned else {},
            seed=job_spec.get("seed"),
            schema_versions={"adapter": adapter.adapter_version},
            output_contract_version=getattr(adapter, "output_contract_version", "unknown"),
        )
        job.build_fingerprint = fp.digest()

        cached = self.cache.lookup(job.build_fingerprint)
        if cached is not None:
            self.cache.materialize(cached, work_dir)
            job.status = states.SKIPPED_CACHE_HIT
            job.finished_at = _now()
            job.log_path = None
            self.index.upsert_job(job)
            outputs = [work_dir / o.relative_path for o in cached.outputs]
            self._publish_stable(job.job_id, work_dir, outputs)
            issues = self._normalize(adapter, outputs, job)
            if any(i.blocking for i in issues):
                return self._fail(job, VALIDATION_BLOCKER,
                                  "blocking validation issue in cached output",
                                  issues=issues)
            return JobOutcome(job=job, cache_hit=True, issues=issues)

        # 3. Run the planned command(s).
        job.status = states.RUNNING
        job.started_at = _now()
        job.command = args
        job.working_directory = str(work_dir)
        self.index.upsert_job(job)

        result = None
        for cmd in planned:
            log_path = self.jobs_dir / job.job_id / str(job.attempt) / "job.log"
            result = run_command(
                cmd.argv(),
                cwd=cmd.working_directory,
                env={**cmd.environment, "DELI_OUT": str(work_dir),
                     "LF_OUT": str(work_dir)},
                log_path=log_path,
                timeout_s=cmd.timeout_seconds,
                cancel=cancel,
            )
            job.log_path = str(log_path)
            if result.cancelled:
                return self._fail(job, "cancelled", "job cancelled", exit_code=result.exit_code)
            if result.exit_code != 0:
                # One transient retry if eligible and adapter isn't deterministic-fail.
                fail_class = "timeout" if result.timed_out else TOOL_EXIT_FAILURE
                if (is_transient_eligible(fail_class)
                        and job.attempt <= MAX_TRANSIENT_RETRIES
                        and job_spec.get("transient_ok")):
                    job.attempt += 1
                    return self._execute_job(job, job_spec, cancel)
                # A readiness EVALUATOR (e.g. Laser Tag) signals its verdict via
                # exit code: a low/BROKEN grade exits nonzero but is EVIDENCE for
                # the human at candidate selection, not a build crash. Fall
                # through to the output-contract check — if the report is present
                # the job "completed with findings"; if it's missing, that check
                # will fail it as a real error.
                if not (result.timed_out or job_spec.get("exit_advisory")):
                    return self._fail(job, fail_class,
                                      f"tool exited {result.exit_code}",
                                      exit_code=result.exit_code)
                if result.timed_out:
                    return self._fail(job, fail_class,
                                      f"tool exited {result.exit_code}",
                                      exit_code=result.exit_code)

        # 4. Verify expected-output contract.
        missing = [o for o in planned[0].expected_outputs
                   if not (work_dir / o).exists()] if planned else []
        if missing:
            return self._fail(job, OUTPUT_CONTRACT_ERROR,
                              f"expected outputs missing: {', '.join(missing)}",
                              exit_code=result.exit_code if result else None)

        outputs = [Path(p) for p in adapter.collect_outputs(job_spec, context)]

        # 5. Normalize validation; block on any blocker.
        issues = self._normalize(adapter, outputs, job)
        val_status = "PASS" if not any(i.blocking for i in issues) else "BLOCKED"

        # 6. Hash artifacts + record provenance, then publish to cache.
        artifacts = self._record_artifacts(job, adapter, probe, outputs, work_dir, val_status)
        self.cache.publish(
            fingerprint=job.build_fingerprint,
            adapter_id=adapter.adapter_id,
            job_id=job.job_id,
            output_root=work_dir,
            output_files=outputs,
            validation_status=val_status,
        )

        self._publish_stable(job.job_id, work_dir, outputs)

        if any(i.blocking for i in issues):
            return self._fail(job, VALIDATION_BLOCKER,
                              "blocking validation issue", issues=issues,
                              exit_code=result.exit_code if result else 0)

        job.status = states.SUCCEEDED
        job.exit_code = result.exit_code if result else 0
        job.finished_at = _now()
        job.artifact_ids = [a.artifact_id for a in artifacts]
        self.index.upsert_job(job)
        return JobOutcome(job=job, issues=issues, artifacts=artifacts)

    # ------------------------------------------------------------------
    def _normalize(self, adapter, outputs, job: Job) -> list:
        raws = adapter.normalize_validation(outputs)
        return [
            issue_from_normalized(
                raw, source_tool=adapter.adapter_id, mission_id=job.mission_id,
                candidate_id=job.candidate_id, stage_id=job.stage_id,
            )
            for raw in raws
        ]

    def _record_artifacts(self, job, adapter, probe, outputs, work_dir, val_status) -> list:
        artifacts = []
        for out in outputs:
            content_hash = hash_file(out)
            rel = out.relative_to(work_dir).as_posix()
            art = Artifact(
                artifact_id=content_hash,
                type=out.suffix.lstrip("."),
                logical_name=f"{job.job_id}:{rel}",
                content_hash=content_hash,
                size_bytes=out.stat().st_size,
                source_path=str(out),
                cache_path="",
                producing_job_id=job.job_id,
                tool_id=adapter.adapter_id,
                tool_version=probe.tool_version,
                tool_commit=probe.repository_commit,
                created_at=_now(),
                validation_status=val_status,
            )
            artifacts.append(art)
            self.index.upsert_artifact(
                art.artifact_id, art.logical_name, art.type, job.job_id,
                pretty_dumps(art.as_dict()),
            )
            prov = provenance_record(
                logical_name=art.logical_name, tool=adapter.adapter_id,
                tool_version=probe.tool_version, repository_commit=probe.repository_commit,
                adapter_version=adapter.adapter_version, job_id=job.job_id,
                inputs=[], arguments=job.command, validation_status=val_status,
            )
            (out.parent / (out.name + ".provenance.json")).write_text(
                pretty_dumps(prov), encoding="utf-8"
            )
        return artifacts

    def _fail(self, job: Job, failure_class: str, message: str,
              *, issues=None, exit_code=None) -> JobOutcome:
        job.status = states.BLOCKED if failure_class == VALIDATION_BLOCKER else states.FAILED
        if failure_class == "cancelled":
            job.status = states.CANCELLED
        job.failure = Failure(failure_class, message).as_dict()
        job.finished_at = _now()
        if exit_code is not None:
            job.exit_code = exit_code
        self.index.upsert_job(job)
        return JobOutcome(job=job, issues=issues or [])
