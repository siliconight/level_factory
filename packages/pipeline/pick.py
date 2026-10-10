"""Which candidate to select after the shell leg, on its merits (0.169.0, roadmap 202).

The rule every cold run since 9194 has picked with, moved here from the factory's
`tools/cold_drive/pick_candidate.py` so that somebody making a level picks by the rule those
runs were graded under, and can see why:

* **Out:** a candidate whose nav walk test is not ok, or against which Laser Tag raised a major
  route or pathing finding (`OUT_CODES`).
* **Among the rest:** the fewest major findings wins, then the highest route completion Laser
  Tag measured, then the lowest seed.
* **If every candidate is out,** the one with the fewest major findings is still picked, and
  `every_out` says so. A run needs a selection, and a pick that says it is the least bad is
  better than one that says nothing.

ROUTE COMPLETION (2026-10-07, roadmap 203). Cold run 9194 picked seed_9054, whose crew finished
the route in 8% of Laser Tag's runs, over seed_9155 at 100%. Both had zero major findings,
because Laser Tag raises LT_ROUTE_NEVER_COMPLETED only at 0%, and the tie went to the lower
seed. Completion is read from each candidate's `lasertag.report.json`
(`summary.route_completion_rate`); a candidate without one sorts last and says so.

Everything is read from the workspace, from the files the shell leg wrote; nothing is run.
"""
from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

OUT_CODES = ("LT_ROUTE_NEVER_COMPLETED", "LT_MAP_ENEMY_PATHING_BROKEN")
MAJOR = ("major", "critical", "blocker")
_SEED = re.compile(r"seed_(\d+)$")


@dataclass
class Candidate:
    seed: int
    major: int = 0
    completion: float | None = None
    out: list = field(default_factory=list)

    def candidate_id(self, mission_id: str) -> str:
        return f"{mission_id}.candidate.seed_{self.seed}"

    def line(self) -> str:
        rc = "?" if self.completion is None else f"{self.completion:.2f}"
        why = ", ".join(self.out) if self.out else "nothing"
        return f"seed {self.seed}: {self.major} major, route completion {rc}, out for {why}"


def _newest(paths: list[Path]) -> Path | None:
    """The last attempt's file: attempt directories are numbered 1, 2, ..."""
    def attempt(p: Path) -> int:
        for part in reversed(p.parts):
            if part.isdigit():
                return int(part)
        return 0
    return max(paths, key=attempt) if paths else None


def candidates(internal_dir: Path, mission_id: str) -> list[Candidate]:
    """Every candidate the shell leg built, with what the rule reads about it.

    Raises ValueError when there is no candidate, or when the mission's validation file is
    missing or in another shape: a pick made without them would be a guess.
    """
    jobs = Path(internal_dir) / "jobs"
    seeds = sorted(int(m.group(1)) for p in jobs.glob(f"{mission_id}.lot_assemble.candidate.seed_*")
                   if (m := _SEED.search(p.name)))
    if not seeds:
        raise ValueError(f"no candidates for {mission_id} under {jobs}: run the shell leg first")
    vfile = Path(internal_dir) / "validation" / f"{mission_id}.json"
    try:
        issues = json.loads(vfile.read_text(encoding="utf-8"))["issues"]
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise ValueError(f"{vfile} cannot be read as a validation file: {exc}") from exc
    if not isinstance(issues, list):
        raise ValueError(f"{vfile}: `issues` is not a list")
    rows = {s: Candidate(s) for s in seeds}
    out = defaultdict(list)
    major = Counter()
    for issue in issues:
        m = _SEED.search(str(issue.get("candidate_id") or ""))
        if not m or int(m.group(1)) not in rows:
            continue
        seed = int(m.group(1))
        if issue.get("severity") in MAJOR:
            major[seed] += 1
            if issue.get("code") in OUT_CODES:
                out[seed].append(str(issue["code"]))
    for seed, row in rows.items():
        row.major = major[seed]
        row.out = list(out[seed])
        walk = _newest(list(jobs.glob(
            f"{mission_id}.walktest_navqa.candidate.seed_{seed}/*/out/*.walktest.json")))
        if walk is None:
            row.out.append("no walktest")
        else:
            try:
                if not json.loads(walk.read_text(encoding="utf-8")).get("ok"):
                    row.out.append("walktest not ok")
            except (OSError, ValueError) as exc:
                row.out.append(f"walktest unreadable ({type(exc).__name__})")
        report = _newest(list(jobs.glob(
            f"{mission_id}.laser_tag_evaluate.candidate.seed_{seed}/*/out/lasertag.report.json")))
        try:
            row.completion = float(json.loads(report.read_text(encoding="utf-8"))
                                   ["summary"]["route_completion_rate"])
        except (AttributeError, OSError, ValueError, KeyError, TypeError):
            row.completion = None
    return [rows[s] for s in seeds]


def pick(rows: list[Candidate]) -> tuple[Candidate, bool]:
    """``(the pick, whether every candidate was out)``."""
    good = [r for r in rows if not r.out]
    pool = good or rows
    best = sorted(pool, key=lambda r: (r.major,
                                       -(r.completion if r.completion is not None else -1.0),
                                       r.seed))[0]
    return best, not good
