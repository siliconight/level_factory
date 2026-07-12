"""Zoo adapter (TDD 24.5).

Bound to Zoo v0.27.0: procedural asset compiler. Two LF stages map to Zoo modes:
  * ``zoo_kit_build``  -> structural modules from DC slots (``build`` + --skins)
  * ``zoo_dressing_build`` -> collision-free dressing from a Patina manifest
    (``dress`` + --skins)
Dressing covers stay ``collision:none`` (24.5 required check) so they never
touch the locked functional shell.
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterable, Mapping, Sequence

from packages.adapters.sdk import BaseAdapter, PlannedCommand
from packages.core.hashing import hash_file


class ZooAdapter(BaseAdapter):
    adapter_id = "zoo"
    adapter_version = "0.1.0"
    capabilities = frozenset(
        {"structural_kit", "dressing_build", "roof_props", "facade_kit",
         "skin_apply", "deterministic_build"}
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
                problems.append("zoo dressing build requires a Patina manifest")
            elif not Path(str(man)).exists():
                problems.append(f"dressing manifest missing: {man}")
        else:
            problems.append(f"unknown zoo mode: {mode}")
        return problems

    def fingerprint_inputs(self, job_spec, context) -> Mapping[str, object]:
        fp: dict[str, object] = {
            "mode": job_spec.get("mode", "kit"),
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
        repo = Path(str(context["repository"]))
        work = Path(str(context["work_dir"]))
        py = context.get("python_executable") or "python"
        mode = job_spec.get("mode", "kit")

        if mode == "dress":
            args = ["-m", "zoo", "dress",
                    "--manifest", str(job_spec.get("manifest_path", "")),
                    "--out", str(work)]
            if job_spec.get("slots_path"):
                args += ["--slots", str(job_spec["slots_path"])]
        else:
            args = ["-m", "zoo", "build",
                    "--slots", str(job_spec.get("slots_path", "")),
                    "--out", str(work)]
            if job_spec.get("roof_props"):
                args.append("--roof-props")
        if job_spec.get("seed") is not None:
            args += ["--seed", str(job_spec["seed"])]
        if job_spec.get("theme"):
            args += ["--theme", str(job_spec["theme"])]
        if job_spec.get("skins_dir"):
            args += ["--skins", str(job_spec["skins_dir"])]

        return [PlannedCommand(
            executable=Path(str(py)), arguments=tuple(args),
            working_directory=repo,
            expected_outputs=tuple(job_spec.get("expected_outputs", [])),
            resource_class="blender", timeout_seconds=900,
        )]

    def collect_outputs(self, job_spec, context) -> Iterable[Path]:
        work = Path(str(context["work_dir"]))
        return sorted(p for p in work.rglob("*")
                      if p.is_file() and p.suffix in (".glb", ".json"))

    def normalize_validation(self, output_paths) -> Sequence[Mapping[str, object]]:
        import json
        issues: list[dict] = []
        for p in output_paths:
            if p.name != "zoo.manifest.json":
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
