"""Which candidate to select after the shell leg, on its merits (0.169.0, roadmap 202).

The rule every cold run since 9194 has picked with, moved here from the factory's
`tools/cold_drive/pick_candidate.py` so that somebody making a level picks by the rule those
runs were graded under, and can see why:

* **Out:** a candidate whose nav walk test is not ok, or against which Laser Tag raised a major
  route or pathing finding (`OUT_CODES`).
* **Among the rest:** the fewest major findings wins, then the highest route completion Laser
  Tag measured, then the higher Laser Tag score, then the lowest seed. Two kinds of major
  are shown and not counted (WHAT A PICK COUNTS, below).
* **If every candidate is out,** the one with the fewest major findings is still picked, and
  `every_out` says so. A run needs a selection, and a pick that says it is the least bad is
  better than one that says nothing.

ROUTE COMPLETION (2026-10-07, roadmap 203). Cold run 9194 picked seed_9054, whose crew finished
the route in 8% of Laser Tag's runs, over seed_9155 at 100%. Both had zero major findings,
because Laser Tag raises LT_ROUTE_NEVER_COMPLETED only at 0%, and the tie went to the lower
seed. Completion is read from each candidate's `lasertag.report.json`
(`summary.route_completion_rate`); a candidate without one sorts last and says so.

THE GRADE (0.202.0; the walker, 2026-10-13: "ties should go to the higher grade"). Cold run 9283
picked card_block_001's seed_9061 at PASS_WITH_TUNING 77 over seed_9263 at 89, one major each and
route completion 1.00 each, on the lower seed. The report's score (`lasertag_report.report_score`)
now breaks that tie before the seed; Laser Tag's grade is a pure function of it, so the higher score
is the higher grade. A report without one sorts last among its ties. The factory's copy of this
rule, `tools/cold_drive/pick_candidate.py`, learned it first and this file did not, so for a day the
cold runs and `level-factory pick` picked by two rules; that copy now reads this one.

WHAT A PICK COUNTS (0.202.0). The walker asked which finding types should stop counting as majors
for picking and left the call to the factory; its census (`docs/findings/pick_majors/` in the
factory root, 62 cold workspace missions, 186 candidates) decided it. A major counts unless it is
one of two kinds, each shown on the candidate's line as "not counted":

* `ADVISORY` -- Laser Tag's verdicts on the fight its bots played, not on the level: a crew that
  lost nobody (TRIVIAL_ENCOUNTER), died before it could react (NO_REACTION_TIME,
  LT_NO_SURVIVABLE_OPENING), or never fired or was fired on (NO_ENGAGEMENT, NO_CONTACT). Its bots,
  weapons and time-to-kill are not the game's -- `lasertag_report`'s reason LT_NO_SURVIVABLE_OPENING
  does not block -- and the fight moves when the level does not: Laser Tag 0.31.0 changed only how
  its guards walk and moved gas_block_001 seed_9181's crew survival from 9.51 to 18.88 s. They are
  one set because they bracket one fight. Cold run 9283's three candidates carried one each,
  NO_REACTION_TIME twice (crews dead in 6.44 and 7.80 s) and TRIVIAL_ENCOUNTER once, and not counting
  either alone would have picked the other's failure. They still reach the pick through the score;
  taken together they change none of the 62 picks.
* `ANSWERED_BY_WALK` -- a doubt raised by a tool that cannot see what the walk test measures, not
  counted where the walk test walked every leg (`walked_every_leg`). LOT_DESTINATION_ABOVE_FLOOR is
  Lot saying an objective 3.3 to 4.0 m up -- a storey -- may stand where no stair reaches; the walk
  test walks a crew body to it. It was on 96 of the 186 candidates, walked to on 95, and Laser Tag's
  crew completed the route on 93. Counted, it chose 28 of the 62 picks: on 12 a lower route
  completion or score than this rule picks, on 16 an equal one, on none a higher.

Still counted: the out codes; the structural findings (a spawn missing, in collision or cut off; no
world collision); every other tool's majors; and TRAVERSAL. On both of the two candidates that
carried it the crew was wiped in 20 and 21 of 25 runs, a fight outcome, but a crew held by the
geometry reads the same way.

Everything is read from the workspace, from the files the shell leg wrote; nothing is run.
"""
from __future__ import annotations

import json
import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from packages.validation.lasertag_report import report_score

OUT_CODES = ("LT_ROUTE_NEVER_COMPLETED", "LT_MAP_ENEMY_PATHING_BROKEN")
MAJOR = ("major", "critical", "blocker")
#: Laser Tag's verdicts on the fight its bots played: shown, not counted (WHAT A PICK COUNTS).
ADVISORY = frozenset({"LT_MAP_TRIVIAL_ENCOUNTER", "LT_MAP_NO_REACTION_TIME",
                      "LT_NO_SURVIVABLE_OPENING", "LT_MAP_NO_ENGAGEMENT", "LT_MAP_NO_CONTACT"})
#: Doubts the walk test answers: not counted where it walked every leg (WHAT A PICK COUNTS).
ANSWERED_BY_WALK = frozenset({"LOT_DESTINATION_ABOVE_FLOOR"})
_SEED = re.compile(r"seed_(\d+)$")


@dataclass
class Candidate:
    seed: int
    major: int = 0
    completion: float | None = None
    out: list = field(default_factory=list)
    score: float | None = None
    grade: str = "?"
    walked: bool = False
    not_counted: list = field(default_factory=list)

    def candidate_id(self, mission_id: str) -> str:
        return f"{mission_id}.candidate.seed_{self.seed}"

    def line(self) -> str:
        rc = "?" if self.completion is None else f"{self.completion:.2f}"
        sc = "?" if self.score is None else f"{self.score:g}"
        nc = f" (not counted: {', '.join(self.not_counted)})" if self.not_counted else ""
        why = ", ".join(self.out) if self.out else "nothing"
        return (f"seed {self.seed}: {self.major} major{nc}, route completion {rc}, "
                f"grade {self.grade} {sc}, out for {why}")


def _newest(paths: list[Path]) -> Path | None:
    """The last attempt's file: attempt directories are numbered 1, 2, ..."""
    def attempt(p: Path) -> int:
        for part in reversed(p.parts):
            if part.isdigit():
                return int(part)
        return 0
    return max(paths, key=attempt) if paths else None


def walked_every_leg(walk) -> bool:
    """True when the walk test passed and a crew body walked every leg to every anchor.

    Stricter than its `ok`, which also passes a leg Lot's director CREDITS as vertical access
    without walking it ("ok(N vertical leg(s) via ladder)", `nav_qa_director._set_leg`), and an
    objective only a ladder reaches is exactly the doubt LOT_DESTINATION_ABOVE_FLOOR raises. So
    every crew walker (`player_*`; its targets are every heist anchor, the objective at its room's
    floor among them) must read exactly "ok" with every target reached. A walk test that names no
    crew walker has answered nothing and reads False. Bots are not read: the director credits a
    bot with no walkable target as a matter of course.
    """
    if not isinstance(walk, dict) or not walk.get("ok"):
        return False
    crew = [w for w in walk.get("walkers") or []
            if isinstance(w, dict) and str(w.get("name", "")).startswith("player_")]
    return bool(crew) and all(w.get("status") == "ok"
                              and w.get("targets_reached") == w.get("targets_total") for w in crew)


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
    majors = defaultdict(list)
    for issue in issues:
        m = _SEED.search(str(issue.get("candidate_id") or ""))
        if not m or int(m.group(1)) not in rows:
            continue
        if issue.get("severity") in MAJOR:
            majors[int(m.group(1))].append(str(issue.get("code")))
    for seed, row in rows.items():
        row.out = [code for code in majors[seed] if code in OUT_CODES]
        walk = _newest(list(jobs.glob(
            f"{mission_id}.walktest_navqa.candidate.seed_{seed}/*/out/*.walktest.json")))
        if walk is None:
            row.out.append("no walktest")
        else:
            try:
                walked = json.loads(walk.read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:
                row.out.append(f"walktest unreadable ({type(exc).__name__})")
            else:
                if not isinstance(walked, dict) or not walked.get("ok"):
                    row.out.append("walktest not ok")
                row.walked = walked_every_leg(walked)
        for code in majors[seed]:
            if code in ADVISORY or (code in ANSWERED_BY_WALK and row.walked):
                row.not_counted.append(code)
            else:
                row.major += 1
        report = _newest(list(jobs.glob(
            f"{mission_id}.laser_tag_evaluate.candidate.seed_{seed}/*/out/lasertag.report.json")))
        try:
            data = json.loads(report.read_text(encoding="utf-8"))
        except (AttributeError, OSError, ValueError):
            data = None
        try:
            row.completion = float(data["summary"]["route_completion_rate"])
        except (KeyError, TypeError, ValueError):
            row.completion = None
        if isinstance(data, dict):
            row.score = report_score(data)
            row.grade = str(data.get("grade") or "?")
    return [rows[s] for s in seeds]


def pick(rows: list[Candidate]) -> tuple[Candidate, bool]:
    """``(the pick, whether every candidate was out)``."""
    good = [r for r in rows if not r.out]
    pool = good or rows
    best = sorted(pool, key=lambda r: (r.major,
                                       -(r.completion if r.completion is not None else -1.0),
                                       -(r.score if r.score is not None else -1.0),
                                       r.seed))[0]
    return best, not good
