"""Generate a level's layouts and choose one (the factory's roadmap 314; increment 4 of `docs/AUTHORING_LOOP.md`).

GENERATE runs the legs `make` runs and the cold runs proved -- ``init`` (once), ``batch create``, ``plan``, the shell
``run`` -- each as its own `level-factory` process, for `cmd_make`'s reason: state one command leaves behind would
reach the next in one process. What came of them is read from STRUCTURED sources, never from their printed text:
the job index while the shell leg runs (progress), `pick.candidates` afterwards (each candidate's majors, route
completion, grade and the reasons it is out), and the validation file `run` writes. The legs' own output goes to a
log beside the run, for whoever needs it.

THE REQUEST IS RECORDED WITH THE BUILD: the batch and the brief derived from the design are written into the design's
folder (``request/``) and imported from there, and ``builds/revision_<n>.json`` names the design revision, the brief,
the candidates and their states. A build is always traceable to the design that asked for it.

STOP: a client writes ``cancel`` into the run directory. The leg running is ended with its whole process tree
(`packages.jobs.runner`'s termination) and the operation refuses with ``cancelled``, saying which legs finished; jobs
that finished stay cached, and Generate again carries on from them.

A CANDIDATE'S STATE is the plan's four words: ``valid`` (nothing puts it out and no major finding), ``needs attention``
(major findings that do not put it out), ``failed`` (something puts it out), ``not checked`` (its walk test never
ran). The automated recommendation is `pick.pick`'s, and when every candidate is out it says so: a least-bad pick is
never presented as a recommendation.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

from packages.service import design as design_mod

#: Seconds between looks at the job index and the cancel file while a leg runs.
POLL_S = 1.0
STATES = ("valid", "needs attention", "failed", "not checked")


class LayoutError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _cli() -> Path:
    return Path(__file__).resolve().parents[2] / "apps" / "cli" / "main.py"


def _popen_kwargs() -> dict:
    from packages.jobs import runner
    return runner._popen_kwargs()


def run_leg(argv: list[str], log: Path, *, cancel_file: Path, on_poll=None) -> int:
    """Run one `level-factory` command as its own process, its output appended to ``log``. Every `POLL_S` it calls
    ``on_poll()`` and looks for ``cancel_file``; when that appears the process tree is ended and `LayoutError`
    ``cancelled`` is raised. Returns the exit code."""
    from packages.jobs import runner
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    with open(log, "a", encoding="utf-8", newline="\n") as out:
        out.write("\n== %s\n" % " ".join(argv))
        out.flush()
        proc = subprocess.Popen([sys.executable, str(_cli()), *argv], stdout=out, stderr=subprocess.STDOUT,
                                stdin=subprocess.DEVNULL, env=env, **_popen_kwargs())
        while True:
            try:
                return proc.wait(timeout=POLL_S)
            except subprocess.TimeoutExpired:
                pass
            if cancel_file.exists():
                runner._terminate_tree(proc, 3.0)
                raise LayoutError("cancelled", "stopped at %s" % argv[2 if argv[:1] == ["-C"] else 0])
            if on_poll is not None:
                on_poll()


def _status(row) -> str:
    out = list(row.out)
    if out and all(o == "no walktest" for o in out):
        return "not checked"
    if out:
        return "failed"
    return "needs attention" if row.major else "valid"


def candidate_rows(internal_dir: Path, mission_id: str) -> dict:
    """The candidates the shell leg built, each with its state and evidence, and the automated recommendation."""
    from packages.pipeline import pick
    rows = pick.candidates(internal_dir, mission_id)
    best, every_out = pick.pick(rows)
    out = []
    for r in rows:
        out.append({"candidate_id": r.candidate_id(mission_id), "seed": r.seed, "state": _status(r),
                    "major_findings": r.major, "not_counted": list(r.not_counted), "out_for": list(r.out),
                    "route_completion": r.completion, "grade": r.grade, "score": r.score, "walked": r.walked,
                    "summary": r.line()})
    return {"candidates": out, "recommended": best.candidate_id(mission_id), "every_out": every_out,
            "recommendation": ("Every layout failed a check; the one listed first failed least. It is not a "
                               "recommendation: read why each failed." if every_out else
                               "Ranked by fewest major findings, then route completion, then grade.")}


def _write_json(path: Path, data) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(".%s.tmp" % path.name)
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    os.replace(tmp, path)
    return path


def _design_folder(path: str) -> tuple[Path, dict]:
    got = design_mod.read_design(Path(path))
    if got["problems"]:
        raise LayoutError("design_unusable", "; ".join(got["problems"]))
    return Path(got["path"]).parent, got["design"]


def generate(path: str, events, run_dir: Path, leg=run_leg) -> dict:
    """Generate the design at ``path``'s layouts. Returns the candidates (`candidate_rows`), the workspace, the
    mission, and the build record's path."""
    folder, doc = _design_folder(path)
    brief = design_mod.brief_from_design(doc)
    mission = brief["mission_id"]
    t = design_mod.template(doc["template"])
    batch = {"schema": "level_factory.batch.v0.1", "batch_id": doc["slug"], "name": doc["name"],
             "seed_base": int(t["batch"]["seed_base"]), "theme_family": t["batch"]["theme_family"],
             "missions": [mission]}
    request = folder / "request"
    batch_path = _write_json(request / "batch.json", batch)
    _write_json(request / "briefs" / ("%s.json" % mission), brief)
    ws = folder / "workspace"
    log = run_dir / "legs.log"
    cancel = run_dir / "cancel"
    legs = []
    if not (ws / "factory.project.json").exists():
        legs.append(("init", ["init", str(ws), "--name", doc["name"]]))
    legs += [("import", ["-C", str(ws), "batch", "create", str(batch_path)]),
             ("plan", ["-C", str(ws), "plan", mission]),
             ("layouts", ["-C", str(ws), "run", mission])]
    done = []

    def progress():
        from packages.core import states
        from packages.project_store.index import Index
        db = ws / ".level_factory" / "index.sqlite"
        if not db.exists():
            return
        try:
            idx = Index(db)
            jobs = idx.jobs_for_mission(mission)
            idx.close()
        except Exception:  # a read racing the writer: the next poll asks again
            return
        if jobs:
            finished = sum(1 for j in jobs if j.status in states.JOB_TERMINAL)
            events.emit("layouts", "running", "%d of %d steps done" % (finished, len(jobs)),
                        progress=finished / len(jobs))

    for i, (name, argv) in enumerate(legs):
        events.emit(name, "running", {"init": "Making the level's workspace", "import": "Reading the level",
                                      "plan": "Planning the layouts", "layouts": "Building the layouts"}[name],
                    progress=i / len(legs) if name != "layouts" else None)
        try:
            code = leg(argv, log, cancel_file=cancel, on_poll=progress if name == "layouts" else None)
        except LayoutError as exc:
            if exc.code == "cancelled":
                raise LayoutError("cancelled", "Stopped while %s. Finished before stopping: %s. Finished steps are "
                                  "kept; Generate again carries on from them." % (name, ", ".join(done) or "nothing"))
            raise
        # `run` exits 1 for findings and 2 when a job blocks: either way the candidates that were built are read
        if code not in (0, 1) and not (name == "layouts" and code == 2):
            raise LayoutError("leg_failed", "%s exited %d; its output is in %s" % (name, code, log))
        done.append(name)
    try:
        result = candidate_rows(ws / ".level_factory", mission)
    except ValueError as exc:
        raise LayoutError("no_layouts", "no layouts came out of the build: %s (output in %s)" % (exc, log)) from None
    record = _write_json(folder / "builds" / ("revision_%d.json" % doc["revision"]),
                         {"schema": "gabagool.build_record.v1", "design_id": doc["design_id"],
                          "design_revision": doc["revision"], "mission_id": mission, "brief": brief,
                          "workspace": str(ws), "candidates": result["candidates"],
                          "recommended": result["recommended"], "every_out": result["every_out"],
                          "recorded_at": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime())})
    events.emit("layouts", "ok", "%d layouts" % len(result["candidates"]), progress=1.0)
    return dict(result, workspace=str(ws), mission_id=mission, build_record=str(record),
                design_revision=doc["revision"])


def choose(path: str, candidate_id: str, events, run_dir: Path, leg=run_leg) -> dict:
    """Record the designer's choice of layout: the `candidate_selected` gate, approved by the panel on the designer's
    word. It is a choice, not a review: nothing about the layout's quality is signed off by it."""
    folder, doc = _design_folder(path)
    mission = design_mod.mission_id(doc)
    ws = folder / "workspace"
    if not (ws / "factory.project.json").exists():
        raise LayoutError("no_layouts", "generate the level's layouts first")
    rows = candidate_rows(ws / ".level_factory", mission)
    known = [c["candidate_id"] for c in rows["candidates"]]
    if candidate_id not in known:
        raise LayoutError("unknown_candidate", "%s is not one of %s" % (candidate_id, ", ".join(known)))
    log = run_dir / "legs.log"
    code = leg(["-C", str(ws), "approve", mission, "candidate_selected", "--candidate", candidate_id,
                "--by", "panel", "--note", "chosen in the Factory panel; a choice, not a review"],
               log, cancel_file=run_dir / "cancel")
    if code != 0:
        raise LayoutError("leg_failed", "recording the choice exited %d; its output is in %s" % (code, log))
    chosen = next(c for c in rows["candidates"] if c["candidate_id"] == candidate_id)
    events.emit("choose", "ok", "Chose %s" % candidate_id)
    return {"chosen": chosen, "mission_id": mission, "design_revision": doc["revision"]}
