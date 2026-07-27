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
from packages.validation import model
from packages.validation.job_failure import issues_for_failure
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


#: Sidecar suffix for the record written next to each artifact.
PROVENANCE_SUFFIX = ".provenance.json"


def _without_provenance(paths):
    """Drop provenance sidecars from a job's output set.

    A sidecar is a record ABOUT an artifact, not an artifact, and treating it
    as one compounds: `collect_outputs` rglobs the work dir, so every run swept
    up the previous run's sidecars, wrote a sidecar for each, and added one
    level of nesting per run --
    `site.tscn.provenance.json.provenance.json...`.

    It read as cosmetic for eleven levels. At seventeen it stopped being
    cosmetic: the path passed Windows' MAX_PATH and the whole run died with
    `[Errno 22] Invalid argument` on a filename nobody had chosen, before a
    single stage had done any work. Filtering here rather than in each adapter
    means an adapter cannot opt into the recursion by rglobbing honestly.
    """
    return [p for p in paths if not p.name.endswith(PROVENANCE_SUFFIX)]


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
        force: bool = False,
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

        # Resume: pre-mark already-succeeded jobs and drop them from deps, so a
        # re-run after a crash skips finished work. This pre-skip trusts the
        # recorded status and does NOT re-check inputs, so it is UNSAFE when an
        # upstream changed (e.g. a new stage was inserted): the stale downstream
        # would never re-run. `force` disables the pre-skip, routing every job
        # through the normal fingerprint->cache path instead — unchanged jobs
        # still cache-hit instantly (no tool re-run); only jobs whose inputs
        # actually changed rebuild.
        if not force:
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
        """Run a job and hand back its findings, advisories included.

        The advisories are collected here rather than inside the attempt so a
        retry cannot report them twice, and so they survive every way the
        attempt can end -- including the ones that end it early. A tactical
        finding about a scene is worth the same whether the job that would have
        evaluated it succeeded, was refused at pre-flight or timed out; losing
        it on the failure path would mean the only runs that never explain what
        is wrong with a map are the runs that went worst.
        """
        advisories: list = []
        outcome = self._attempt_job(job, job_spec, cancel, advisories)
        if advisories:
            outcome.issues = advisories + list(outcome.issues)
        return outcome

    def _attempt_job(self, job: Job, job_spec: dict,
                     cancel: Cancellation | None, advisories: list) -> JobOutcome:
        adapter = self.registry.get(job.adapter_id)
        repo = self.installation.get("repositories", {}).get(job.adapter_id, "")
        # First execution is attempt 1; retries increment before recursing.
        if job.attempt == 0:
            job.attempt = 1
        work_dir = self.jobs_dir / job.job_id / str(job.attempt) / "out"
        work_dir.mkdir(parents=True, exist_ok=True)

        context = {
            "repository": repo,
            # Every configured tool checkout, not just this adapter's own. Some
            # questions are only answerable across two repositories at once --
            # whether the range Lot places enemies against is still the range
            # Laser Tag opens fire at is one of them, and neither tool can
            # answer it alone.
            "repositories": dict(self.installation.get("repositories", {})),
            "work_dir": str(work_dir),
            "blender_executable": self.installation.get("blender_executable", ""),
            "godot_executable": self.installation.get("godot_executable", ""),
            "python_executable": self.installation.get("python_executable", "") or "python3",
            "godot_project": str(self.godot_project or work_dir),
        }

        # 0. Tactical advisories -- what the tool will build and grade badly,
        # as opposed to what it will refuse. Collected before the pre-flight so
        # a refused job still carries them, and replaced rather than appended
        # so a transient retry does not double the list.
        advisories[:] = self._advise(adapter, job_spec, context, job)

        # 1. Validate configuration -- no silent fixes (TDD 5.4).
        problems = list(adapter.validate_configuration(job_spec, context))
        if problems:
            # Pass the list, not the joined sentence: a pre-flight that
            # objected four times is making four statements.
            return self._fail(job, INPUT_VALIDATION_ERROR, "; ".join(problems),
                              problems=problems)

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

        # FINGERPRINT RECEIPT (cache honesty): record WHAT this decision was
        # based on -- the digest and every per-input hash -- next to the job,
        # on every evaluation including cache hits. When a cache hit looks
        # suspicious ("but I changed the slots!"), the receipt shows exactly
        # which input hashes matched instead of leaving it to archaeology.
        try:
            import datetime as _dt
            import json as _json
            receipt_dir = self.jobs_dir / job.job_id
            receipt_dir.mkdir(parents=True, exist_ok=True)
            (receipt_dir / "fingerprint.last.json").write_text(_json.dumps({
                "digest": job.build_fingerprint,
                "adapter_version": adapter.adapter_version,
                # The tool revision the artifact came from. Carries a
                # "+dirty.<hash>" suffix when the tool repo has uncommitted
                # tracked edits -- without it, an on-disk fix that has not
                # been committed keeps cache-hitting the pre-fix artifact.
                "tool_version": probe.tool_version,
                "repository_commit": probe.repository_commit,
                "inputs": raw_inputs,
                "evaluated_utc": _dt.datetime.now(
                    _dt.timezone.utc).isoformat(),
            }, indent=2, sort_keys=True, default=str), encoding="utf-8")
        except OSError:
            pass  # a receipt must never break the build

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
                    return self._attempt_job(job, job_spec, cancel, advisories)
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

        outputs = _without_provenance(
            Path(p) for p in adapter.collect_outputs(job_spec, context))

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
    def _advise(self, adapter, job_spec: dict, context: dict, job: Job) -> list:
        """An adapter's tactical findings, forced non-blocking.

        The forcing is the point, and it lives here rather than in the adapters
        because it is an architectural rule and not an adapter's manners. A
        firefight evaluator saying an opening is unfair, or that two markers can
        see each other across ninety metres of empty street, is a design signal:
        the map exists, the evaluator will happily play it, and it will grade it
        down. Answering that by refusing to build stops the level existing long
        enough to be improved, and the finding is worth far more pointed forward
        -- at where cover belongs -- than backward as a refusal. So an adapter
        cannot make an advisory block by mislabelling it, no matter what
        severity it hands over.

        An adapter that has nothing to say, or no advisory path at all, costs
        nothing. An adapter whose advisory path raises says so as a finding
        rather than taking the build down with it: the whole reason this channel
        is separate from `validate_configuration` is that nothing on it is
        allowed to be the reason a level does not get made.
        """
        advise = getattr(adapter, "advise_configuration", None)
        if advise is None:
            return []
        try:
            raws = list(advise(job_spec, context))
        except Exception as exc:   # noqa: BLE001 - see the docstring
            raws = [{
                "code": "ADVISORY_FAILED",
                "severity": model.INFO,
                "category": "configuration",
                "message": (f"the {adapter.adapter_id} advisory pass raised "
                            f"{type(exc).__name__}: {exc} — the build was not "
                            f"affected, but this run has no tactical findings "
                            f"from it"),
            }]
        out = []
        for raw in raws:
            raw = dict(raw)
            raw["blocking"] = False
            if raw.get("severity") == model.BLOCKER:
                raw["severity"] = model.MAJOR
            out.append(issue_from_normalized(
                raw, source_tool=adapter.adapter_id, mission_id=job.mission_id,
                candidate_id=job.candidate_id, stage_id=job.stage_id))
        return out

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
        outputs = _without_provenance(outputs)
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
              *, issues=None, exit_code=None, problems=()) -> JobOutcome:
        job.status = states.BLOCKED if failure_class == VALIDATION_BLOCKER else states.FAILED
        if failure_class == "cancelled":
            job.status = states.CANCELLED
        job.failure = Failure(failure_class, message).as_dict()
        job.finished_at = _now()
        if exit_code is not None:
            job.exit_code = exit_code
        self.index.upsert_job(job)
        # A stopped job wrote no report, so `normalize_validation` had nothing
        # to read and the mission ended with zero findings -- which is what a
        # clean build also reports. Translate the failure itself into findings
        # so the reason travels with the run instead of dying on the job row.
        out = list(issues or [])
        if not out:
            out = issues_for_failure(
                failure_class=failure_class,
                message=message,
                problems=list(problems),
                source_tool=job.adapter_id,
                job_id=job.job_id,
                mission_id=job.mission_id,
                candidate_id=job.candidate_id,
                stage_id=job.stage_id,
                log_path=job.log_path,
            )
        return JobOutcome(job=job, issues=out)
