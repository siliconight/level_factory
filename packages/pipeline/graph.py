"""Directed acyclic job graph (TDD 15).

A tiny dependency graph over Job objects. The scheduler consumes the topological
order; the planner produces the nodes and edges.
"""
from __future__ import annotations

from collections import deque

from packages.core.models import Job


class GraphError(Exception):
    pass


class JobGraph:
    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}

    def add(self, job: Job) -> None:
        if job.job_id in self._jobs:
            raise GraphError(f"duplicate job id: {job.job_id}")
        self._jobs[job.job_id] = job

    def jobs(self) -> list[Job]:
        return list(self._jobs.values())

    def get(self, job_id: str) -> Job:
        return self._jobs[job_id]

    def dependents(self, job_id: str) -> list[str]:
        return [j.job_id for j in self._jobs.values() if job_id in j.depends_on]

    def topological_order(self) -> list[Job]:
        """Kahn's algorithm; raises on cycles or dangling deps."""
        indegree: dict[str, int] = {jid: 0 for jid in self._jobs}
        for job in self._jobs.values():
            for dep in job.depends_on:
                if dep not in self._jobs:
                    raise GraphError(f"job '{job.job_id}' depends on unknown '{dep}'")
                indegree[job.job_id] += 1

        # Deterministic order: process ready nodes sorted by job_id.
        ready = deque(sorted(jid for jid, d in indegree.items() if d == 0))
        order: list[Job] = []
        while ready:
            jid = ready.popleft()
            order.append(self._jobs[jid])
            newly_ready = []
            for dependent in self.dependents(jid):
                indegree[dependent] -= 1
                if indegree[dependent] == 0:
                    newly_ready.append(dependent)
            for jid2 in sorted(newly_ready):
                ready.append(jid2)

        if len(order) != len(self._jobs):
            raise GraphError("cycle detected in job graph")
        return order
