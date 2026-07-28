"""Walktest adapter -- navigability answered by walking, not by shooting.

Every navigation conclusion this pipeline has drawn was inferred from a Laser
Tag firefight, which is the wrong instrument twice over: confounded by combat,
and asking a nav question of a gameplay simulation. Nineteen timeouts on a seed
is not an answer to "is the route pathable?"; it is a symptom with several
possible causes.

`lot/walktest.py` answers it directly. It runs Lot's `<stem>_navqa.tscn` under
headless Godot, where the `heist_nav_qa` director bakes the navmesh, proves a
path along the mission spine leg by leg, then spawns physical walkers and drives
them. No enemies, no weapons, no scoring. The report says which leg had no
navmesh path and where a walker stalled.

The authority split is different from Laser Tag's, and deliberately so. Laser
Tag grades a map and never refuses one, because the combat model it measures
belongs to the consumer. Navigability does not: reachability and closure are
exactly what this stack certifies about the asset it ships (see PIPELINE_MAP.md
and ENGINE_GATES.md). A site whose objective cannot be reached is broken output,
not a design note.

So walktest findings are built to block -- gated, for now, behind
``WALKTEST_ENFORCED``. The existing library has never been checked this way and
promoting on day one would fail missions wholesale before anyone has looked at
one. This mirrors `deli_counter.stairwell.CONTAINMENT_ENFORCED`: warn while the
library is remediated, flip the flag once it is clean.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, Mapping, Sequence

from packages.adapters.sdk import BaseAdapter, PlannedCommand
from packages.core.hashing import hash_file

#: Promote walktest findings from warnings to hard blockers. False while the
#: existing library is remediated. Everything else about the findings -- codes,
#: messages, locations -- is identical either way, so flipping this changes what
#: happens to a bad site, never whether it is noticed.
WALKTEST_ENFORCED = False

#: The report the director writes, named after the staged scene.
SCENE_RES_NAME = "site_navqa.tscn"
REPORT_NAME = "site_navqa.walktest.json"

#: Import pass (up to 600 s on a cold project) plus the run itself.
TIMEOUT_SECONDS = 1200


class WalktestAdapter(BaseAdapter):
    adapter_id = "walktest"
    adapter_version = "0.1.0"
    capabilities = frozenset(
        {
            "navmesh_bake",
            "path_proof",
            "simulated_walkers",
            "json_report",
        }
    )
    output_contract_version = "lot.walktest.0.1"

    # ---- probing ---------------------------------------------------------
    def probe(self, installation: Mapping[str, str]):
        """The tool behind this adapter is Lot.

        `Scheduler._attempt_job` resolves `installation["repositories"][
        adapter_id]`, and there is no "walktest" repository -- walktest.py and
        the heist_nav_qa director ship inside Lot. Left to the default, probe()
        would report unavailable and contribute no tool version, so the
        fingerprint would forget which Lot ran the QA. Point it at the Lot
        checkout instead of inventing a repository that does not exist.
        """
        repos = dict(installation.get("repositories", {}) or {})
        lot_repo = repos.get("lot") or installation.get("repository") or ""
        return super().probe({**installation, "repository": lot_repo})

    # ---- pre-flight ------------------------------------------------------
    def validate_configuration(
        self, job_spec: Mapping[str, object], context: Mapping[str, object]
    ) -> Sequence[str]:
        problems: list[str] = []
        scene = job_spec.get("navqa_scene")
        if not scene:
            problems.append(
                "navqa_scene is not set -- Lot emits <stem>_navqa.tscn only "
                "when the job spec passes navqa=True")
        elif not Path(str(scene)).exists():
            problems.append(f"navqa scene does not exist: {scene}")
        if not job_spec.get("lot_repository"):
            problems.append("lot_repository is not set (walktest.py lives there)")
        if not job_spec.get("staging_dir"):
            problems.append("staging_dir is not set")
        if not context.get("godot_executable"):
            problems.append(
                "godot_executable is not configured; walktest needs headless "
                "Godot 4 and a skipped nav check is worse than an absent one")
        return problems

    # ---- fingerprint -----------------------------------------------------
    def fingerprint_inputs(
        self, job_spec: Mapping[str, object], context: Mapping[str, object]
    ) -> Mapping[str, object]:
        fp: dict[str, object] = {"contract": self.output_contract_version}
        scene = job_spec.get("navqa_scene")
        if scene and Path(str(scene)).exists():
            fp["scene_hash"] = hash_file(Path(str(scene)))

        # The director is an input, the same way Laser Tag's addon is. Lot's
        # VERSION moves for reasons that have nothing to do with the nav QA
        # scripts, and the nav QA scripts change without Lot's VERSION moving.
        # Neither direction is safe to infer, so hash what actually runs. Keyed
        # by path relative to the Lot repo so two same-named files under
        # different addons cannot mask each other.
        repo = job_spec.get("lot_repository")
        if repo:
            root = Path(str(repo))
            sources: dict[str, str] = {}
            runner = root / "walktest.py"
            if runner.is_file():
                sources["walktest.py"] = hash_file(runner)
            for addon in ("heist_nav_qa", "lot"):
                base = root / "godot" / "addons" / addon
                if not base.is_dir():
                    continue
                for f in sorted(base.rglob("*")):
                    if not f.is_file() or f.suffix not in (".gd", ".tres", ".cfg"):
                        continue
                    if any(part == ".godot" for part in f.parts):
                        continue
                    sources[f.relative_to(root).as_posix()] = hash_file(f)
            if sources:
                fp["director_hashes"] = sources
        return fp

    # ---- run -------------------------------------------------------------
    def plan_commands(
        self, job_spec: Mapping[str, object], context: Mapping[str, object]
    ) -> Sequence[PlannedCommand]:
        work = Path(str(context["work_dir"]))
        py = Path(str(context.get("python_executable") or "python3"))
        godot = str(context.get("godot_executable") or "godot")
        # Fall back rather than index. `plan_commands` must describe a command
        # for any spec it is handed -- the shared adapter contract suite calls
        # it with a generic one -- and objecting to a spec is
        # `validate_configuration`'s job, which the scheduler runs first. An
        # adapter that raises here turns a stated problem into a stack trace.
        repo = Path(str(job_spec.get("lot_repository")
                        or context.get("repository") or "."))
        scene_src = Path(str(job_spec.get("navqa_scene") or ""))
        staging_dir = job_spec.get("staging_dir")

        # A throwaway project, exactly as Laser Tag does it: the navqa scene at
        # res:// with its work-dir siblings, and the absolute res://C:/... refs
        # Lot bakes in rewritten on the way. Staged OUTSIDE work_dir so the
        # project's copies of the building GLBs are not collected as this job's
        # outputs and stored in the content cache a second time.
        project = Path(str(context.get("godot_project") or work))
        if staging_dir and scene_src.is_file():
            from packages.staging.godot_project import stage_godot_project

            addon_dirs = [repo / "godot" / "addons" / "heist_nav_qa",
                          repo / "godot" / "addons" / "lot"]
            project, _res = stage_godot_project(
                Path(str(staging_dir)),
                addon_dirs=[a for a in addon_dirs if a.exists()],
                scene_src=scene_src,
                plugins=[],
                scene_res_name=SCENE_RES_NAME,
                godot_executable=godot)

        args = [
            str(repo / "walktest.py"), str(project), SCENE_RES_NAME,
            # Without --require, walktest.py treats a missing Godot 4 binary as
            # a SKIP and returns 0 -- a nav check that never ran, reported as
            # success. That is the defect this pipeline spent a day removing
            # from its own scheduler; it is not being invited back in through a
            # runner flag. With --require the run fails, no report is written,
            # and the output contract fails the job for the honest reason.
            "--require",
            # The director names the report after the scene and writes it beside
            # it, which puts it in the throwaway project. Copy it where the
            # scheduler looks.
            "--report-dir", str(work),
        ]
        return [
            PlannedCommand(
                executable=py,
                arguments=tuple(args),
                working_directory=repo,
                # walktest.py discovers Godot through $LOT_GODOT / $DC_GODOT /
                # PATH. `run_command` copies os.environ and updates it with this
                # mapping, so the child sees it; passing the configured binary
                # explicitly means the stage works on a machine where Godot is
                # not on PATH, which is the machine this runs on.
                environment={"LOT_GODOT": godot},
                expected_outputs=(REPORT_NAME,),
                resource_class="godot_headless",
                timeout_seconds=TIMEOUT_SECONDS,
            )
        ]

    def collect_outputs(
        self, job_spec: Mapping[str, object], context: Mapping[str, object]
    ) -> Iterable[Path]:
        work = Path(str(context["work_dir"]))
        return sorted(p for p in work.rglob("*")
                      if p.is_file() and p.suffix == ".json")

    # ---- findings --------------------------------------------------------
    def normalize_validation(
        self, output_paths: Sequence[Path]
    ) -> Sequence[Mapping[str, object]]:
        report = next((p for p in output_paths if p.name == REPORT_NAME), None)
        if report is None:
            # Silence here would be a lie, but it is not this method's lie to
            # tell: a missing report means the command did not produce its
            # declared output, and the scheduler's output-contract check fails
            # the job before validation is consulted.
            return []
        try:
            data = json.loads(report.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            return [self._finding(
                "WALKTEST_REPORT_UNREADABLE", "provenance",
                f"walktest report could not be read: {exc}",
                location=str(report))]

        issues: list[dict] = []

        # The director's early-outs. These are not "the level plays badly" --
        # they are "there was nothing to walk on", and they arrive with `ok`
        # false and no proofs at all.
        error = str(data.get("error") or "")
        if error:
            code = ("WALKTEST_NAVMESH_EMPTY" if "navigation map is EMPTY" in error
                    else "WALKTEST_NO_SPAWNS" if "player proxies" in error
                    else "WALKTEST_SETUP_FAILED")
            issues.append(self._finding(
                code, "navigation", error, location=str(report)))

        # An anchor that reaches no other anchor is standing on a navmesh scrap.
        # It passes every distance check the director makes -- it is ON the mesh
        # -- and it can never appear in a route. Reported first and separately,
        # because for a day this arrived only as its consequence: legs failing
        # with "disjoint islands", a true statement about the navmesh that reads
        # as a claim about the whole site rather than about one endpoint.
        stranded = set()
        for anchor in data.get("anchors") or []:
            if not isinstance(anchor, dict):
                continue
            size = anchor.get("cluster_size")
            main = anchor.get("main_cluster_size")
            if size is not None and main is not None:
                off_network = size < main
            else:
                # Reports from a director older than Lot 0.27.0 carry no
                # clusters. Fall back rather than go quiet -- but note that
                # "reaches 0" is the threshold that missed sixteen of
                # twenty-one anchors, because each still reached its own
                # duplicate.
                off_network = anchor.get("reaches") == 0
            if not off_network:
                continue
            name = str(anchor.get("name", "?"))
            stranded.add(name)
            snap = anchor.get("snap") or []
            where = (f" at ({snap[0]}, {snap[1]}, {snap[2]})"
                     if len(snap) >= 3 else "")
            twin = str(anchor.get("coincident_with") or "")
            also = (f"; it also shares a position with {twin}, so the two are "
                    f"one anchor emitted twice") if twin else ""
            scale = (f"on a cluster of {size} while the main one has {main}"
                     if size is not None and main is not None
                     else f"reaching 0 of {anchor.get('of', '?')} other anchors")
            issues.append(self._finding(
                "WALKTEST_ANCHOR_ISOLATED", "anchor",
                f"anchor {name} snapped {anchor.get('snap_m', '?')} m onto the "
                f"navmesh{where} and is {scale}: it is on the mesh and off the "
                f"network{also}",
                location=f"{report}#{name}",
                suggested_fix="Fix where the anchor is placed, not the navmesh. "
                              "Distance-to-mesh already passes; what is missing "
                              "is a surface that connects to the rest of the "
                              "site."))

        for proof in data.get("path_proofs") or []:
            if not isinstance(proof, dict) or proof.get("ok"):
                continue
            # A leg that failed because one of its ends is stranded is the same
            # defect restated. Report the anchor once rather than every leg it
            # touches.
            if str(proof.get("isolated_endpoint", "")) in stranded and stranded:
                continue
            leg = str(proof.get("leg", "?"))
            issues.append(self._finding(
                "WALKTEST_LEG_UNPATHABLE", "reachability",
                f"no navmesh path for the '{leg}' leg of the mission spine: "
                f"{proof.get('detail', 'no detail')}",
                location=f"{report}#{leg}",
                suggested_fix="Widen the lane or lower the step: Lot derives "
                              "its clearance from deli_counter/agent_contract."
                              "json, so a leg that fails here fails the same "
                              "contract LOT_COVER_PINCH is measured against."))

        for walker in data.get("walkers") or []:
            if not isinstance(walker, dict):
                continue
            status = str(walker.get("status", ""))
            # Every ok-flavoured status passes: "ok", "ok(1 vertical leg(s)..)",
            # "ok_vertical_targets_only". An exact match would reject the
            # vertical ones, which is a bug the director itself carries a
            # comment about.
            if status.startswith("ok"):
                continue
            at = walker.get("at")
            where = (f" at ({at[0]}, {at[1]}, {at[2]})"
                     if isinstance(at, (list, tuple)) and len(at) >= 3 else "")
            issues.append(self._finding(
                "WALKTEST_WALKER_STUCK", "traversal",
                f"walker {walker.get('name', '?')} reached "
                f"{walker.get('targets_reached', 0)}/"
                f"{walker.get('targets_total', 0)} targets ({status})"
                f"{where}",
                location=f"{report}#{walker.get('name', 'walker')}"))

        # A report that says ok=false while naming nothing is worse than one
        # that names a leg, because it looks like a pass to anything counting
        # findings. Say so rather than returning an empty list.
        if not data.get("ok") and not issues:
            issues.append(self._finding(
                "WALKTEST_FAILED_WITHOUT_DETAIL", "navigation",
                "the walktest reported ok=false but named no failing leg or "
                "walker; the report is at "
                f"{report}",
                location=str(report)))
        return issues

    @staticmethod
    def _finding(code: str, category: str, message: str, *,
                 location: str = "", suggested_fix: str = "") -> dict:
        return {
            "code": code,
            "severity": "blocker" if WALKTEST_ENFORCED else "major",
            "category": category,
            "message": message,
            "location": location,
            "suggested_fix": suggested_fix,
            "blocking": bool(WALKTEST_ENFORCED),
        }
