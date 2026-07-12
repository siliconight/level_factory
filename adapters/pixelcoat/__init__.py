"""Pixelcoat adapter (TDD 24.4).

Bound to Pixelcoat v0.2.0: deterministic, recipe-driven low-res material packs.
Emits the ``pixelcoat-pack/1`` contract (``<id>.pack.json`` naming albedo /
normal[OpenGL Y+] / roughness / optional emissive+height, tileable axes,
meters_per_tile) that Zoo consumes via ``--skins``. Shared surface packs are a
batch-level asset, so this stage's outputs live under ``shared/pixelcoat``.
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterable, Mapping, Sequence

from packages.adapters.sdk import BaseAdapter, PlannedCommand
from packages.core.hashing import hash_file


class PixelcoatAdapter(BaseAdapter):
    adapter_id = "pixelcoat"
    adapter_version = "0.1.0"
    capabilities = frozenset(
        {"process_texture", "build_recipe", "validate_recipes",
         "material_pack", "deterministic_build"}
    )
    output_contract_version = "pixelcoat-pack/1"

    def validate_configuration(self, job_spec, context) -> Sequence[str]:
        problems: list[str] = []
        recipes = job_spec.get("recipes_dir")
        if not recipes:
            problems.append("pixelcoat job requires a recipes directory")
        elif not Path(str(recipes)).exists():
            problems.append(f"recipes directory missing: {recipes}")
        return problems

    def fingerprint_inputs(self, job_spec, context) -> Mapping[str, object]:
        fp: dict[str, object] = {
            "theme": job_spec.get("theme"),
            "output_size": job_spec.get("output_size"),
            "dither": job_spec.get("dither"),
        }
        recipes = job_spec.get("recipes_dir")
        if recipes and Path(str(recipes)).exists():
            fp["recipe_hashes"] = {
                p.name: hash_file(p)
                for p in sorted(Path(str(recipes)).rglob("*.json"))
            }
        palette = job_spec.get("shared_palette")
        if palette and Path(str(palette)).exists():
            fp["palette_hash"] = hash_file(Path(str(palette)))
        return fp

    def plan_commands(self, job_spec, context) -> Sequence[PlannedCommand]:
        repo = Path(str(context["repository"]))
        work = Path(str(context["work_dir"]))
        py = context.get("python_executable") or "python"
        args = ["-m", "pixelcoat", "build",
                "--recipes", str(job_spec.get("recipes_dir", "")),
                "--out", str(work)]
        if job_spec.get("theme"):
            args += ["--theme", str(job_spec["theme"])]
        if job_spec.get("shared_palette"):
            args += ["--palette", str(job_spec["shared_palette"])]
        if job_spec.get("force"):
            args.append("--force")
        return [PlannedCommand(
            executable=Path(str(py)), arguments=tuple(args),
            working_directory=repo,
            expected_outputs=tuple(job_spec.get("expected_packs", [])),
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
            # A pack manifest must resolve its files (TDD 24.4 required check).
            for role in ("albedo",):
                fname = pack.get("maps", {}).get(role) or pack.get(role)
                if fname and not (p.parent / fname).exists():
                    issues.append({
                        "code": "PIXELCOAT_PACK_UNRESOLVED",
                        "severity": "major", "category": "presentation",
                        "message": f"pack {p.name} references missing {role} '{fname}'",
                        "blocking": True, "raw_source_path": str(p),
                    })
            if "meters_per_tile" not in pack:
                issues.append({
                    "code": "PIXELCOAT_NO_PHYSICAL_SCALE",
                    "severity": "moderate", "category": "presentation",
                    "message": f"pack {p.name} missing meters_per_tile",
                    "blocking": False, "raw_source_path": str(p),
                })
        return issues
