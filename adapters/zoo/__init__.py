"""Zoo adapter (TDD 24.5) — bound to the REAL Zoo CLI, grounded against 1.1.1.

The invocation below is the 0.27.0 shape and still the current one; what HAS
moved since is the fixtures index, whose 0.94 contract `normalize_validation`
reads at the bottom of this file.

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

import os
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
#
# IT WAS COUNTED, AND THE COUNT WAS A LAYOUT ASSUMPTION (0.94.0):
# `parents[3]` is `adapters/zoo -> adapters -> level_factory -> <factory>`
# from a checkout sitting beside its siblings, and `scratchpad` from a git
# WORKTREE, where `tools/shape_metrics.py` is not. The check above then did
# its job -- `measure_shapes needs C:\...\scratchpad\tools\shape_metrics.py,
# which is not there` -- and the measurement stopped, three tests with it.
# That is the same defect `tests/siblings.py` removes on the test side, in
# the production path.
#
# So: SEARCH for the tool rather than count to it, `LF_FACTORY_ROOT` first.
# No behaviour changes from a checkout -- the walk's first hit is the
# directory the count named.
_TOOL_REL = Path("tools") / "shape_metrics.py"


def _factory_root() -> Path:
    """The directory holding `tools/shape_metrics.py`, at or above this file.

    When nothing above carries it, this answers with THIS REPO's root -- found
    the same way, by the file that marks it -- so the refusal
    `validate_configuration` prints names a real directory instead of a
    counted guess at one. Nothing reads that path except the message:
    `SHAPE_METRICS.is_file()` is False on both branches, which is the answer
    that matters.
    """
    env = os.environ.get("LF_FACTORY_ROOT")
    if env and (Path(env) / _TOOL_REL).is_file():
        return Path(env)
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / _TOOL_REL).is_file():
            return parent
    for parent in here.parents:
        if (parent / "pyproject.toml").is_file():
            return parent
    return here.parent


_FACTORY_ROOT = _factory_root()
SHAPE_METRICS = _FACTORY_ROOT / _TOOL_REL


def _is_count(value: object) -> bool:
    """A non-negative integer count, as an index field.

    `bool` is a subclass of `int` in Python, so a plain `isinstance(v, int)`
    accepts `true` and reads it as 1. An index whose `fixtures_built` is a
    boolean is a file nobody should be counting from, so it is excluded here
    rather than silently arithmetic'd.
    """
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


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
        elif mode == "habitat":
            # A SET of standalone species -- the Layer 3 clutter (roadmap
            # 110): pebble, rubble_frag, weed_tuft, litter_scrap. Named
            # outright, comma-separated, exactly as `zoo_cli --habitat`
            # takes them; Zoo refuses an unknown species by name, so a typo
            # fails the job rather than building three of four.
            if not str(job_spec.get("habitat") or "").strip():
                problems.append("zoo habitat build requires `habitat`: a "
                                "comma-separated species list")
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
        # The species list IS the habitat job's input: two clutter sets with
        # the same theme and seed are two different builds. Folded in ONLY for
        # that mode: a new key on every zoo fingerprint would retire every
        # cached kit, dressing and fixture bake in every workspace for a
        # layer none of them contains.
        if job_spec.get("mode") == "habitat":
            fp["habitat"] = str(job_spec.get("habitat") or "")
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
        if mode == "habitat":
            # Standalone species, one specimen each, named outright. Built
            # WITHOUT collision on purpose: these are Layer 3 surface
            # dressing, and the manifest that places them carries
            # `collision_policy: none` -- a pebble a body can trip on is the
            # "believable but false traversal promise" the layer forbids.
            # `--prompt` is the shared theme; Zoo's `species_prompt` folds it
            # into each species' intent. The habitat id is a hash Zoo derives
            # at build time, so no output name can be declared here; the
            # measuring command that follows declares its own.
            zoo_args = ["--habitat", str(job_spec.get("habitat", "")),
                        "--out", str(work), "--no-collision", "--no-blend"]
            if job_spec.get("theme"):
                zoo_args += ["--prompt", str(job_spec["theme"])]
            # --skins with --theme, the pair the dress branch below explains:
            # a themed library resolves only under its own theme. Without
            # them a species takes the flat path, and the clutter shipped as
            # untextured light-grey lumps (level_factory 0.86.0).
            if job_spec.get("skins_dir"):
                zoo_args += ["--skins", str(job_spec["skins_dir"])]
                if job_spec.get("theme"):
                    zoo_args += ["--theme", str(job_spec["theme"])]
            if job_spec.get("seed") is not None:
                zoo_args += ["--seed", str(job_spec["seed"])]
            args = ["--background", "--python", cli, "--", *zoo_args]
            commands = [PlannedCommand(
                executable=Path(blender), arguments=tuple(args),
                working_directory=repo, expected_outputs=(),
                resource_class="blender", timeout_seconds=1200,
            )]
            commands += self._measure_commands(job_spec, context)
            return commands
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
            # `.built.json` are the kit, dressing and fixture indexes;
            # `.habitat.json` is the clutter build's (roadmap 110).
            if not (p.name.endswith(".built.json")
                    or p.name.endswith(".habitat.json")):
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
            # Fixture builds. THE V0.30 EMITTER-MARKER CONTRACT WAS "every
            # placement ships a LuxEmit_* marker or downstream spawning is
            # blind", and this gate spelled that `emitter_markers ==
            # fixtures_built`. Zoo 0.94 made that spelling wrong, and cold run
            # 9064 was refused for it: `ZOO_FIXTURES_MARKER_MISMATCH:
            # emitter_markers (18) != fixtures_built (25)` on strip_club_a02,
            # whose index in the same breath said `markerless_fixtures: 7`.
            # 18 + 7 = 25 -- the generator was right and the gate was reading
            # two of the three numbers it writes. The same shell one stack
            # earlier (cold run 9060, Zoo 0.92.0) read built 18, markers 18:
            # the markers did not fall, the fixtures rose by 7, because the
            # club anchors that used to be SKIPPED as "no fixture species"
            # now build.
            #
            # `zoo_keeper/bpylayer/build.py` writes `emitter_markers = built -
            # markerless` on purpose. A club fixture is hardware with no
            # marker BY DESIGN: `core.fixtures.FIXTURES` marks `club_wash` and
            # `stage_light` `marker: False` because the spawner hands
            # `rig_for_anchor` only {type, id, drop}, so a marker would lose
            # the zone colour and pool radius Deli Counter measured -- and
            # would DOUBLE the light the manifest bake (`bake_club`) already
            # makes, not supply it.
            #
            # So the rule that holds is
            #
            #     emitter_markers + markerless_fixtures == fixtures_built
            #
            # with an absent `markerless_fixtures` read as 0. That is not a
            # relaxation: for every index an older Zoo wrote it is the v0.30
            # check to the bit, and the failure it exists for -- a placement
            # with no marker and nothing SAYING so, which is a light nothing
            # downstream can spawn or count -- is still a blocker.
            #
            # THE ARITHMETIC ALONE WOULD BE A CHECK THAT CANNOT FAIL. On any
            # index Zoo itself wrote, `emitter_markers` is DERIVED as
            # `built - markerless`, so the sum is an identity and proves
            # nothing about the build. The second opinion is `placements`,
            # which carries the per-placement `marker` flag the counts were
            # tallied from -- independent data in the same file. It is the
            # half with teeth; the arithmetic is the half that still works on
            # a summary-only index.
            if p.name.endswith("_fixtures.built.json"):
                built = man.get("fixtures_built")
                markers = man.get("emitter_markers")
                # Absent means "this Zoo had no such concept", i.e. none.
                markerless = man.get("markerless_fixtures", 0)
                # An anchor type Zoo has no fixture species for is a
                # capability gap (roadmap 62): the manifest asked for light
                # there and nothing will be built. Daylight skips and
                # `--fixture-types` filtering are by design and stay quiet.
                # Measured 2026-09-11 over 82 shipped fixture indexes: 430
                # skips, every one `window` daylight, none of this kind --
                # the `pendant` silence that raised the item is closed.
                unserved = [s for s in man.get("skipped", []) or []
                            if str(s.get("reason", "")).startswith(
                                "no fixture species")]
                if unserved:
                    types = sorted({str(s.get("type")) for s in unserved})
                    issues.append({
                        "code": "ZOO_CAPABILITY_GAP",
                        "severity": "moderate", "category": "art_coverage",
                        "message": (f"CAPABILITY_GAP: {len(unserved)} light "
                                    f"anchor(s) of type {', '.join(types)} "
                                    f"have no fixture species in Zoo; no "
                                    f"fixture and no marker will be built "
                                    f"there, so the room stays dark"),
                        "suggested_fix": ("grow the species in Zoo "
                                          "(FIXTURES row + genome + recipe); "
                                          "owner=zoo"),
                        "blocking": False, "raw_source_path": str(p),
                    })
                if markers is None:
                    issues.append({
                        "code": "ZOO_FIXTURES_NO_MARKER_CONTRACT",
                        "severity": "blocker", "category": "contract",
                        "message": ("fixtures index has no emitter_markers — "
                                    "built by a pre-v0.30 Zoo; the Lux fixture "
                                    "gate cannot spawn or verify these"),
                        "blocking": True, "raw_source_path": str(p),
                    })
                    continue
                # AN UNRECOGNISED SHAPE FAILS RATHER THAN PASSES. The line
                # this replaces was `elif isinstance(built, int) and markers
                # != built`, so a `fixtures_built` that was null, a string or
                # absent took the else branch and the index went through
                # UNCHECKED -- the gate reporting clean about a file it could
                # not read. Named separately from the mismatch so a run
                # summary distinguishes "the numbers disagree" from "the
                # numbers are not numbers".
                bad = {k: v for k, v in (("fixtures_built", built),
                                         ("emitter_markers", markers),
                                         ("markerless_fixtures", markerless))
                       if not _is_count(v)}
                if bad:
                    issues.append({
                        "code": "ZOO_FIXTURES_INDEX_UNREADABLE",
                        "severity": "blocker", "category": "contract",
                        "message": ("fixtures index does not carry countable "
                                    "fixture numbers: "
                                    + ", ".join(f"{k}={v!r}"
                                                for k, v in sorted(bad.items()))
                                    + " — this index cannot be verified, so it "
                                      "is not being passed"),
                        "blocking": True, "raw_source_path": str(p),
                    })
                    continue
                if markers + markerless != built:
                    issues.append({
                        "code": "ZOO_FIXTURES_MARKER_MISMATCH",
                        "severity": "blocker", "category": "contract",
                        "message": (f"emitter_markers ({markers}) + "
                                    f"markerless_fixtures ({markerless}) != "
                                    f"fixtures_built ({built}): "
                                    f"{built - markers - markerless} "
                                    f"placement(s) are unaccounted for — a "
                                    f"fixture with neither a marker nor a "
                                    f"declared reason is a light nothing "
                                    f"downstream can spawn"),
                        "blocking": True, "raw_source_path": str(p),
                    })
                # The second opinion: the per-placement `marker` flags the
                # summary was tallied from. `build.py` reads `p.get("marker",
                # True)`, so an absent flag means marked -- the default is
                # mirrored here rather than guessed, because getting it
                # backwards would report every ordinary index as broken.
                # Skipped when the index carries no placements: an older or
                # summary-only index has no second opinion to give, and the
                # arithmetic above has already run on it.
                places = man.get("placements")
                if isinstance(places, list) and all(isinstance(x, dict)
                                                    for x in places):
                    marked = sum(1 for x in places if x.get("marker", True))
                    unmarked = len(places) - marked
                    if marked != markers or unmarked != markerless:
                        issues.append({
                            "code": "ZOO_FIXTURES_MARKER_TALLY_MISMATCH",
                            "severity": "blocker", "category": "contract",
                            "message": (f"the index's own placements do not "
                                        f"tally with its counts: "
                                        f"{len(places)} placement(s), {marked} "
                                        f"marked and {unmarked} markerless, "
                                        f"against emitter_markers={markers} "
                                        f"and markerless_fixtures={markerless}"),
                            "blocking": True, "raw_source_path": str(p),
                        })
                # AN OBSERVATION, NOT A GATE. Removing the blocker must not
                # take the number with it: `fixtures_built` is what a reader
                # sees, and on a club shell it is 7 higher than the count of
                # lamps Lux will spawn from markers. That gap is by design and
                # the reader still has to be told it exists, or the next
                # person to compare Zoo's 25 against Lux's 18 re-opens this
                # from scratch. Measured on cold run 9064: strip_club_a02 7 of
                # 25, clinic_a01 0 of 15, mansion_a01 0 of 32 -- it is a club
                # phenomenon, and staying quiet on the other two is the point.
                if markerless:
                    kinds = sorted({str(x.get("type")) for x in places
                                    if isinstance(x, dict)
                                    and not x.get("marker", True)}) \
                        if isinstance(places, list) else []
                    issues.append({
                        "code": "ZOO_FIXTURES_MARKERLESS",
                        "severity": "info", "category": "contract",
                        "message": (f"{markerless} of {built} fixture(s) are "
                                    f"hardware with no emitter marker by "
                                    f"design"
                                    + (f" ({', '.join(kinds)})" if kinds else "")
                                    + f"; Lux's fixture gate will count "
                                      f"{markers} marker(s) here and their "
                                      f"light comes from the manifest bake "
                                      f"instead"),
                        "blocking": False, "raw_source_path": str(p),
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
                # A module the genome library cannot build. Zoo plans it,
                # reports it under `missing_modules` with the nearest species
                # it does have, and builds nothing; Deli Counter's resolver
                # keeps the greybox box there. That is the capability-gap
                # signal (roadmap 62) reaching a run summary.
                missing = man.get("missing_modules") or []
                if missing:
                    species = sorted({str(m.get("species")) for m in missing})
                    near = sorted({n for m in missing
                                   for n in (m.get("nearest") or [])})
                    issues.append({
                        "code": "ZOO_CAPABILITY_GAP",
                        "severity": "moderate", "category": "art_coverage",
                        "message": (f"CAPABILITY_GAP: {len(missing)} module(s) "
                                    f"need species Zoo does not carry: "
                                    f"{', '.join(species)}"
                                    + (f" (nearest: {', '.join(near)})"
                                       if near else "")
                                    + "; the greybox box stands in"),
                        "suggested_fix": ("grow the species in Zoo (genome + "
                                          "recipe); owner=zoo"),
                        "blocking": False, "raw_source_path": str(p),
                    })
            # A habitat index (the Layer 3 clutter build) lists one member per
            # species with a status. A member that failed is a species the
            # dressing layer will silently lack -- Patina skips an asset the
            # metrics do not carry rather than guessing -- so it is said here.
            if p.name.endswith(".habitat.json"):
                failed = sorted(str(m.get("species")) for m in
                                (man.get("members") or [])
                                if isinstance(m, dict)
                                and m.get("status") == "fail")
                if failed:
                    issues.append({
                        "code": "ZOO_PARTIAL_BUILD",
                        "severity": "moderate", "category": "art_coverage",
                        "message": (f"{len(failed)} clutter species failed to "
                                    f"build: {', '.join(failed)}; the surface "
                                    f"dressing will not carry them"),
                        "blocking": False, "raw_source_path": str(p),
                    })
                continue
            # Some modules can fail to build (Zoo exits 2, resolver falls back to
            # base for the rest). The kit is still usable — surface the miss as a
            # non-blocking quality finding for review, not a blocker.
            #
            # `n_fail` is read from the index, and until Zoo 0.58.0 the index
            # never carried it -- it was returned to the in-process caller
            # only. This check therefore never fired: 37 shipped indexes on
            # 2026-09-11, 98 modules with status "fail", zero findings. The
            # per-module `status` was in every one of those files, so the
            # count is derived from it when the key is absent, and the
            # check is live on every index Zoo has ever written.
            n_fail = man.get("n_fail")
            if not isinstance(n_fail, int):
                mods = man.get("modules")
                n_fail = (sum(1 for m in mods if isinstance(m, dict)
                              and m.get("status") == "fail")
                          if isinstance(mods, list) else None)
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
