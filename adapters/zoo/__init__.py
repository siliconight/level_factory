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


class ZooAdapter(BaseAdapter):
    adapter_id = "zoo"
    adapter_version = "0.2.0"
    capabilities = frozenset(
        {"structural_kit", "dressing_build", "roof_props", "facade_kit",
         "skin_apply", "plan_dry_run", "deterministic_build"}
    )
    output_contract_version = "zoo.asset.0.27"

    def validate_configuration(self, job_spec, context) -> Sequence[str]:
        problems: list[str] = []
        mode = job_spec.get("mode", "kit")
        if mode == "kit":
            slots = job_spec.get("slots_path")
            if not slots:
                problems.append("zoo kit build requires a slots.json")
            elif not Path(str(slots)).exists():
                problems.append(f"slots.json missing: {slots}")
        elif mode == "dress":
            man = job_spec.get("manifest_path")
            if not man:
                problems.append("zoo dressing build requires a Patina dressing manifest")
            elif not Path(str(man)).exists():
                problems.append(f"dressing manifest missing: {man}")
        else:
            problems.append(f"unknown zoo mode: {mode}")
        return problems

    def fingerprint_inputs(self, job_spec, context) -> Mapping[str, object]:
        fp: dict[str, object] = {
            "mode": job_spec.get("mode", "kit"),
            "plan_only": bool(job_spec.get("plan_only")),
            "seed": job_spec.get("seed"),
            "theme": job_spec.get("theme"),
        }
        for key in ("slots_path", "manifest_path"):
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
        zoo_args: list[str]
        if mode == "dress":
            zoo_args = ["--dress", str(job_spec.get("manifest_path", "")),
                        "--out", str(work)]
            if job_spec.get("skins_dir"):
                zoo_args += ["--skins", str(job_spec["skins_dir"])]
            bid = _bid(job_spec.get("manifest_path")) or "building"
            expected = (f"{bid}_dressing.built.json",)
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
        return [PlannedCommand(
            executable=Path(blender), arguments=tuple(args),
            working_directory=repo,
            expected_outputs=expected,
            resource_class="blender", timeout_seconds=1200,
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
        return issues
