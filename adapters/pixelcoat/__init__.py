"""Pixelcoat adapter (TDD 24.4) — bound to the REAL Pixelcoat 0.2.0 CLI.

Real invocation (verified against the uploaded repo):

    python -m pixelcoat.cli.main build <recipe.json> --output <dir> [--json] [--force]

The recipe is POSITIONAL and self-describing (asset_id + source.path + palette).
A build writes into ``<output>/<asset_id>/``:

    <asset_id>.pack.json      (the pixelcoat-pack/1 manifest Zoo reads via --skins)
    <asset_id>_albedo.png     (+ _normal.png, _roughness.png)
    <asset_id>.pixelcoat.json (recipe record)
    build_report.json

``--json`` prints a machine-readable report (tool_version, files, maps) to stdout.
Shared surface packs are a batch-level asset (this stage's output dir is reused
by every mission's Zoo kit).
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterable, Mapping, Sequence

from packages.adapters.sdk import BaseAdapter, PlannedCommand
from packages.core.hashing import hash_file


class PixelcoatAdapter(BaseAdapter):
    adapter_id = "pixelcoat"
    adapter_version = "0.2.0"
    capabilities = frozenset(
        {"process_texture", "build_recipe", "validate_recipes",
         "material_pack", "deterministic_build"}
    )
    output_contract_version = "pixelcoat-pack/1"

    def _asset_id(self, job_spec) -> str:
        return str(job_spec.get("asset_id", "theme"))

    def validate_configuration(self, job_spec, context) -> Sequence[str]:
        problems: list[str] = []
        recipe = job_spec.get("recipe_path")
        if not recipe:
            problems.append("pixelcoat job requires a recipe_path (a recipe JSON)")
        elif not Path(str(recipe)).exists():
            problems.append(f"pixelcoat recipe missing: {recipe}")
        return problems

    def fingerprint_inputs(self, job_spec, context) -> Mapping[str, object]:
        fp: dict[str, object] = {"asset_id": self._asset_id(job_spec)}
        recipe = job_spec.get("recipe_path")
        if recipe and Path(str(recipe)).exists():
            fp["recipe_hash"] = hash_file(Path(str(recipe)))
            # The source image is referenced (relative) inside the recipe; fold
            # its hash in when resolvable so a source edit invalidates the pack.
            src = job_spec.get("source_path")
            if src and Path(str(src)).exists():
                fp["source_hash"] = hash_file(Path(str(src)))
        return fp

    def plan_commands(self, job_spec, context) -> Sequence[PlannedCommand]:
        repo = Path(str(context["repository"]))
        work = Path(str(context["work_dir"]))
        py = context.get("python_executable") or "python"
        recipe = str(job_spec.get("recipe_path", ""))
        asset_id = self._asset_id(job_spec)

        args = ["-m", "pixelcoat.cli.main", "build", recipe,
                "--output", str(work), "--json", "--force"]

        return [PlannedCommand(
            executable=Path(str(py)), arguments=tuple(args),
            working_directory=repo,
            expected_outputs=(f"{asset_id}/{asset_id}.pack.json",),
            resource_class="python_cpu", timeout_seconds=600,
        )]

    def collect_outputs(self, job_spec, context) -> Iterable[Path]:
        work = Path(str(context["work_dir"]))
        return sorted(p for p in work.rglob("*")
                      if p.is_file() and p.suffix in (".png", ".json"))

    def normalize_validation(self, output_paths) -> Sequence[Mapping[str, object]]:
        import json
        issues: list[dict] = []
        for p in output_paths:
            if not p.name.endswith(".pack.json"):
                continue
            try:
                pack = json.loads(p.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            # A pack manifest must resolve its map files (TDD 24.4 required check).
            maps = pack.get("maps", {})
            names = maps.values() if isinstance(maps, dict) else []
            for fname in list(names) + [pack.get("albedo")]:
                if fname and not (p.parent / str(fname)).exists():
                    issues.append({
                        "code": "PIXELCOAT_PACK_UNRESOLVED",
                        "severity": "major", "category": "presentation",
                        "message": f"pack {p.name} references missing map '{fname}'",
                        "blocking": True, "raw_source_path": str(p),
                    })
        return issues
