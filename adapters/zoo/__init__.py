"""Zoo adapter (TDD 24.5) — bound to the REAL Zoo 0.27.0 CLI.

Real invocation (verified against the uploaded repo):

    python tools/zoo_cli.py --build-kit <slots.json> --skins <dir> --theme <t> \
                            --seed <n> --out <dir>          # structural kit (Blender)
    python tools/zoo_cli.py --dress <patina.dressing.json> --out <dir>   # dressing (Blender)
    python tools/zoo_cli.py --kit  <slots.json> --plan                   # headless plan

The kit/dress geometry builds need Blender; ``--kit ... --plan`` prints the
Intent + BuildPlan headlessly and is used as a pre-build validation gate (and as
the container-runnable path for the real-tool smoke). ``--dress`` consumes a
Patina ``<name>.patina.dressing.json`` (schema ``patina-dressing/1``); its covers
stay collision-free (24.5) so they never touch the locked functional shell.
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterable, Mapping, Sequence

from packages.adapters.sdk import BaseAdapter, PlannedCommand
from packages.core.hashing import hash_file
from packages.validation.kit_dims import kit_dimension_findings

# `tools/shape_metrics.py` is a FACTORY-level tool, not a Zoo one: it measures
# any GLB. Zoo's job runs it because Zoo is what built the GLBs -- measuring
# your own output belongs with the build, lands in the same artifact set, and
# is fingerprinted for free.
#
# Reaching it is a path walk, and a path walk is a silent failure waiting to
# happen. `validate_configuration` therefore CHECKS the tool is there, so a
# layout change is a configuration error someone reads rather than a
# measurement that quietly stopped happening.
#   adapters/zoo/__init__.py -> zoo -> adapters -> level_factory -> <factory>
_FACTORY_ROOT = Path(__file__).resolve().parents[3]
SHAPE_METRICS = _FACTORY_ROOT / "tools" / "shape_metrics.py"


class ZooAdapter(BaseAdapter):
    adapter_id = "zoo"
    # 0.4.0: `measure_shapes` adds a SECOND command to a build job. The
    # commands an adapter plans are not otherwise in the fingerprint, so
    # without the bump every existing zoo entry cache-hits and the metrics
    # sidecar the dressing planner needs is never produced -- the failure this
    # adapter's own 0.3.0 note describes, one stage later.
    adapter_version = "0.4.0"
    capabilities = frozenset(
        {"structural_kit", "dressing_build", "roof_props", "facade_kit",
         "skin_apply", "plan_dry_run", "deterministic_build",
         "light_fixtures", "measure_shapes"}
    )
    output_contract_version = "zoo.asset.0.30"

    def validate_configuration(self, job_spec, context) -> Sequence[str]:
        problems: list[str] = []
        mode = job_spec.get("mode", "kit")
        if mode == "kit":
            slots = job_spec.get("slots_path")
            if not slots:
                problems.append("zoo kit build requires a slots.json")
            elif not Path(str(slots)).exists():
                problems.append(f"slots.json missing: {slots}")
        elif mode == "fixtures":
            lights = job_spec.get("lights_path")
            if not lights:
                problems.append("zoo fixtures build requires a .lights.json")
            elif not Path(str(lights)).exists():
                problems.append(f"lights manifest missing: {lights}")
        elif mode == "dress":
            man = job_spec.get("manifest_path")
            if not man:
                problems.append("zoo dressing build requires a Patina dressing manifest")
            elif not Path(str(man)).exists():
                problems.append(f"dressing manifest missing: {man}")
        else:
            problems.append(f"unknown zoo mode: {mode}")
        if job_spec.get("measure_shapes") and not SHAPE_METRICS.is_file():
            problems.append(
                f"measure_shapes needs {SHAPE_METRICS}, which is not there. "
                "The path is walked up from this adapter's own location; if "
                "the repo layout moved, this is the message that says so "
                "rather than a metrics sidecar that silently stopped being "
                "written.")
        return problems

    def fingerprint_inputs(self, job_spec, context) -> Mapping[str, object]:
        fp: dict[str, object] = {
            "mode": job_spec.get("mode", "kit"),
            "plan_only": bool(job_spec.get("plan_only")),
            "seed": job_spec.get("seed"),
            "theme": job_spec.get("theme"),
            "measure_shapes": bool(job_spec.get("measure_shapes")),
        }
        # The measuring tool's own source is an input: a change to how a
        # footprint or a height is computed changes the catalogue the dressing
        # planner is built from, with every other input byte-identical.
        if job_spec.get("measure_shapes") and SHAPE_METRICS.is_file():
            fp["shape_metrics_hash"] = hash_file(SHAPE_METRICS)
        for key in ("slots_path", "manifest_path", "lights_path"):
            p = job_spec.get(key)
            if p and Path(str(p)).exists():
                fp[key + "_hash"] = hash_file(Path(str(p)))
        skins = job_spec.get("skins_dir")
        if skins and Path(str(skins)).exists():
            fp["skin_hashes"] = {
                pk.name: hash_file(pk)
                for pk in sorted(Path(str(skins)).rglob("*.pack.json"))
            }
        return fp

    def plan_commands(self, job_spec, context) -> Sequence[PlannedCommand]:
        import json as _json
        repo = Path(str(context["repository"]))
        work = Path(str(context["work_dir"]))
        py = context.get("python_executable") or "python"
        blender = str(context.get("blender_executable") or "blender")
        cli = str(repo / "tools" / "zoo_cli.py")
        mode = job_spec.get("mode", "kit")
        plan_only = bool(job_spec.get("plan_only"))

        def _bid(p: object) -> str:
            if not p:
                return ""
            try:
                return str(_json.loads(Path(str(p)).read_text(encoding="utf-8"))
                           .get("building_id") or "").strip()
            except (OSError, ValueError, AttributeError):
                return ""

        if mode == "kit" and plan_only:
            # Headless Intent + BuildPlan — pure Python, no bpy, no Blender.
            args = [cli, "--kit", str(job_spec.get("slots_path", "")), "--plan"]
            return [PlannedCommand(
                executable=Path(str(py)), arguments=tuple(args),
                working_directory=repo, expected_outputs=(),
                resource_class="python_cpu", timeout_seconds=300,
            )]

        # Geometry builds REQUIRE bpy: Zoo must run INSIDE Blender via
        # `blender --background --python tools/zoo_cli.py -- <zoo args>`. Run
        # with plain Python and bpy is absent, so Zoo degrades to a no-op skin
        # report and writes no index (the FAILED-exit=0 seen on hardware).
        def _scope(p: object) -> str:
            # Zoo names fixture outputs by the manifest's scope: building_id
            # (DC per-building) or site (Lot-merged). Mirrors core.fixtures.
            if not p:
                return ""
            try:
                man = _json.loads(Path(str(p)).read_text(encoding="utf-8"))
                return str(man.get("building_id") or man.get("site") or "scene").strip()
            except (OSError, ValueError, AttributeError):
                return ""

        zoo_args: list[str]
        if mode == "fixtures":
            zoo_args = ["--fixtures", str(job_spec.get("lights_path", "")),
                        "--out", str(work)]
            if job_spec.get("theme"):
                zoo_args += ["--theme", str(job_spec["theme"])]
            if job_spec.get("fixture_types"):
                zoo_args += ["--fixture-types",
                             *[str(t) for t in job_spec["fixture_types"]]]
            scope = _scope(job_spec.get("lights_path")) or "scene"
            expected = (f"{scope}_fixtures.built.json",)
            args = ["--background", "--python", cli, "--", *zoo_args]
            return [PlannedCommand(
                executable=Path(blender), arguments=tuple(args),
                working_directory=repo,
                expected_outputs=expected,
                resource_class="blender", timeout_seconds=1200,
            )]
        if mode == "dress":
            zoo_args = ["--dress", str(job_spec.get("manifest_path", "")),
                        "--out", str(work)]
            if job_spec.get("skins_dir"):
                zoo_args += ["--skins", str(job_spec["skins_dir"])]
            # --theme is not decoration on this branch. zoo_cli hands it to
            # `materials.set_skin_library(dir, theme)`, and `skins.find_pack`
            # looks for `<kind>_<theme>/` before bare `<kind>/`. A themed
            # library resolves ONLY under its own theme, so --skins without
            # --theme finds no pack and falls back to flat colour without
            # saying so: the two flags are one input, not two.
            if job_spec.get("theme"):
                zoo_args += ["--theme", str(job_spec["theme"])]
            if job_spec.get("seed") is not None:
                zoo_args += ["--seed", str(job_spec["seed"])]
            bid = _bid(job_spec.get("manifest_path")) or "building"
            # The .glb is DECLARED, not merely hoped for.
            # `presentation_compose` requires a `*_dressing.glb` in this
            # job's out/, so a bake that writes the index and no geometry
            # has failed -- and it has to fail as ITSELF. Measured
            # 2026-08-15: it reported `succeeded`, and compose failed for
            # it, naming a directory two stages upstream.
            expected = (f"{bid}_dressing.built.json",
                        f"{bid}_dressing.glb")
        else:  # kit build
            zoo_args = ["--build-kit", str(job_spec.get("slots_path", "")),
                        "--out", str(work)]
            if job_spec.get("skins_dir"):
                zoo_args += ["--skins", str(job_spec["skins_dir"])]
            if job_spec.get("theme"):
                zoo_args += ["--theme", str(job_spec["theme"])]
            if job_spec.get("seed") is not None:
                zoo_args += ["--seed", str(job_spec["seed"])]
            if job_spec.get("roof_props_slots"):
                zoo_args += ["--roof-props", str(job_spec["roof_props_slots"])]
                if job_spec.get("density"):
                    zoo_args += ["--density", str(job_spec["density"])]
            bid = _bid(job_spec.get("slots_path")) or "building"
            expected = (f"{bid}_kit.built.json",)

        # Blender passes everything after `--` through as user args; zoo_cli.py
        # reads them and adds its own repo root to sys.path.
        args = ["--background", "--python", cli, "--", *zoo_args]
        commands = [PlannedCommand(
            executable=Path(blender), arguments=tuple(args),
            working_directory=repo,
            expected_outputs=expected,
            resource_class="blender", timeout_seconds=1200,
        )]
        commands += self._measure_commands(job_spec, context)
        return commands

    def _measure_commands(self, job_spec, context) -> list:
        """Measure the GLBs this job just built.

        Plain Python, not Blender: `shape_metrics` reads the exported file, so
        it needs no bpy and costs seconds. The output is a normal job artifact,
        which is the point -- the dressing planner consumes measurements, and a
        measurement that lives outside the artifact set is a number nobody can
        trace to a build.
        """
        if not job_spec.get("measure_shapes"):
            return []
        work = Path(str(context["work_dir"]))
        py = context.get("python_executable") or "python"
        name = str(job_spec.get("metrics_name") or "shapes.metrics.json")
        return [PlannedCommand(
            executable=Path(str(py)),
            arguments=(str(SHAPE_METRICS), "--dir", str(work), "--json",
                       "--out", str(work / name)),
            working_directory=work,
            expected_outputs=(name,),
            resource_class="python_cpu", timeout_seconds=300,
        )]

    def collect_outputs(self, job_spec, context) -> Iterable[Path]:
        work = Path(str(context["work_dir"]))
        return sorted(p for p in work.rglob("*")
                      if p.is_file() and p.suffix in (".glb", ".json"))

    def normalize_validation(self, output_paths) -> Sequence[Mapping[str, object]]:
        import json
        issues: list[dict] = []
        for p in output_paths:
            if not p.name.endswith(".built.json"):
                continue
            try:
                man = json.loads(p.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            # Dressing covers MUST be collision-free (24.5). A cover asset that
            # declares collision is an ambiguous/functional change (30.3).
            for asset in man.get("dressing", []):
                if asset.get("collision") not in (None, "none", False):
                    issues.append({
                        "code": "ZOO_DRESSING_HAS_COLLISION",
                        "severity": "blocker", "category": "collision",
                        "message": f"dressing asset '{asset.get('id')}' declares collision",
                        "blocking": True, "raw_source_path": str(p),
                    })
            # Fixture builds (v0.30 emitter-marker contract): every placement
            # must ship a LuxEmit_* marker or downstream spawning is blind.
            if p.name.endswith("_fixtures.built.json"):
                built = man.get("fixtures_built")
                markers = man.get("emitter_markers")
                if markers is None:
                    issues.append({
                        "code": "ZOO_FIXTURES_NO_MARKER_CONTRACT",
                        "severity": "blocker", "category": "contract",
                        "message": ("fixtures index has no emitter_markers — "
                                    "built by a pre-v0.30 Zoo; the Lux fixture "
                                    "gate cannot spawn or verify these"),
                        "blocking": True, "raw_source_path": str(p),
                    })
                elif isinstance(built, int) and markers != built:
                    issues.append({
                        "code": "ZOO_FIXTURES_MARKER_MISMATCH",
                        "severity": "blocker", "category": "contract",
                        "message": (f"emitter_markers ({markers}) != "
                                    f"fixtures_built ({built})"),
                        "blocking": True, "raw_source_path": str(p),
                    })
                continue
            # THE KIT IS MEASURED AGAINST ITS OWN INDEX. Every entry states the
            # dims the planner asked for; the .glb beside it is what was built.
            # Nothing compared the two until 2026-08-09, when one shared kit was
            # found to have put 3.300 m walls in eight buildings whose slots
            # asked 3.1 to 5.2 -- a 0.95 m gap under every wall in `depot_a01`,
            # through every gate in the pipeline.
            #
            # HERE rather than downstream because this is the job that made
            # them: the producer holds both the claim and the artifact, so the
            # check needs nothing that could drift from the thing it checks.
            if p.name.endswith("_kit.built.json"):
                issues.extend(kit_dimension_findings(p))
            # Some modules can fail to build (Zoo exits 2, resolver falls back to
            # base for the rest). The kit is still usable — surface the miss as a
            # non-blocking quality finding for review, not a blocker.
            n_fail = man.get("n_fail")
            if isinstance(n_fail, int) and n_fail > 0:
                issues.append({
                    "code": "ZOO_PARTIAL_BUILD",
                    "severity": "moderate", "category": "art_coverage",
                    "message": (f"{n_fail} module(s) failed to build; the resolver "
                                f"falls back to base for those. Kit is usable — "
                                f"review skins/theme coverage."),
                    "blocking": False, "raw_source_path": str(p),
                })
        return issues
