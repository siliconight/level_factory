"""Prove that a mission's candidates are actually different levels.

A mission generates N candidates so a human can choose between them. That only
means something if the N are distinct; if they are copies, the choosing is
theatre and every downstream signal -- scores, comparisons, the selection gate
itself -- is measuring one level N times and reporting it as N results.

This failed silently for the entire life of the pipeline. The site spec was
written to one path per *mission* rather than per candidate, so all N Lot jobs
read whichever spec was written last and produced byte-identical sites. Nothing
noticed, because nothing had ever compared two candidates to each other: the
per-candidate validation ran N times and passed N times, which is exactly what
it would do if the candidates were real.

That is the shape of the bug this module exists to make impossible. A count of
candidates is not evidence of candidates. The only evidence is a comparison, so
the comparison is a gate.

It BLOCKS, and the reason it is allowed to block is worth stating: this is not a
claim about whether a level is good. It is the pipeline reporting that it did
something it did not do. TDD 5.5 forbids gating on fun, balance or network
readiness; it does not ask us to ship a fiction quietly.

Pure: hashes in, findings out. No filesystem, no workspace, no engine.
"""
from __future__ import annotations

from typing import Mapping, Sequence

CODE_NOT_DISTINCT = "CANDIDATES_NOT_DISTINCT"
CODE_NO_CANDIDATES = "CANDIDATES_MISSING_ARTIFACTS"


def _signature(artifacts: Mapping[str, str]) -> tuple:
    """Order-independent identity of one candidate's outputs."""
    return tuple(sorted(artifacts.items()))


def check_candidate_diversity(
    by_candidate: Mapping[str, Mapping[str, str]],
) -> list[dict]:
    """``{candidate_id: {artifact_name: content_hash}}`` -> normalized findings.

    Single-candidate missions are exempt: one candidate cannot fail to differ
    from itself, and treating that as a finding would train people to ignore the
    code. Candidates whose artifacts are missing entirely are reported
    separately -- an absent output is a different problem from a duplicated one,
    and collapsing the two would hide whichever is rarer.
    """
    findings: list[dict] = []
    present = {c: a for c, a in by_candidate.items() if a}
    missing = sorted(c for c in by_candidate if not by_candidate[c])

    if missing:
        findings.append({
            "code": CODE_NO_CANDIDATES,
            "severity": "major", "category": "configuration",
            "message": ("no comparable build outputs for candidate(s) "
                        + ", ".join(missing)
                        + "; they cannot be compared against the others"),
            "suggested_fix": ("check whether those candidate jobs ran at all -- "
                              "a candidate with no artifacts is not a candidate"),
            "blocking": False,
        })

    if len(present) < 2:
        return findings

    groups: dict[tuple, list[str]] = {}
    for cand, arts in present.items():
        groups.setdefault(_signature(arts), []).append(cand)

    for sig, cands in sorted(groups.items(), key=lambda kv: sorted(kv[1])):
        if len(cands) < 2:
            continue
        names = ", ".join(sorted(cands))
        which = ", ".join(name for name, _ in sig)
        findings.append({
            "code": CODE_NOT_DISTINCT,
            "severity": "blocker", "category": "configuration",
            "message": (f"candidates {names} are byte-identical ({which}); "
                        f"{len(cands)} candidates were generated but only one "
                        f"level exists, so there is nothing to choose between"),
            "suggested_fix": ("candidate variation comes from the per-candidate "
                              "site spec -- check that each candidate is given "
                              "its own spec path and its own seed-derived "
                              "placements, not a shared one"),
            "blocking": True,
        })
    return findings


def distinct_count(by_candidate: Mapping[str, Mapping[str, str]]) -> int:
    """How many genuinely different levels a candidate set contains."""
    return len({_signature(a) for a in by_candidate.values() if a})


def summarize(by_candidate: Mapping[str, Mapping[str, str]]) -> str:
    """One line a human can read in a run log."""
    total = len(by_candidate)
    distinct = distinct_count(by_candidate)
    if total == 0:
        return "candidates: none built"
    if distinct == total:
        return f"candidates: {total} built, all distinct"
    return (f"candidates: {total} built but only {distinct} distinct "
            f"-- {total - distinct} are copies")


def artifact_names(names: Sequence[str]) -> tuple[str, ...]:
    """The outputs worth comparing, in a stable order.

    Deliberately the assembled site and the building shell rather than every
    file a job emits: logs, provenance and timing differ between runs that
    produced the same level, and a gate that trips on those is a gate that gets
    turned off.
    """
    return tuple(sorted(set(names)))
