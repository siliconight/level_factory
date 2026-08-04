"""Lot adapter (TDD 24.2) — bound to the REAL Lot 0.18.0 CLI.

Real invocation (verified against the uploaded repo):

    python lot.py <site_spec.json> <out_dir> [--walkable] [--navqa] [--preview]

Lot is a positional script, not ``python -m lot``. The site spec references the
Deli Counter building GLBs; Lot assembles them, runs the audit + pacing inline,
and writes stem-named outputs into <out_dir>:

    <stem>.site.gameplay.json   (pacing folded in, an ESTIMATE — never blocks)
    <stem>.tscn                 (site scene)
    <stem>_walk.tscn            (walkable candidate scene, with --walkable)
    <stem>.site.lights.json     (merged light anchors)
    <stem>_navqa.tscn           (with --navqa)
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, Mapping, Sequence

from packages.adapters.sdk import BaseAdapter, PlannedCommand
from packages.core.hashing import hash_file, scene_payload_hashes

class LotAdapter(BaseAdapter):
    adapter_id = "lot"
    # 0.3.0: fingerprint_inputs also folds in the payload a composed .tscn
    # references by path. The rules for computing a fingerprint changed, so
    # entries computed under the old rules must not be trusted -- bumping
    # retires them once instead of leaving a mixed cache.
    adapter_version = "0.3.0"
    capabilities = frozenset(
        {
            "assemble_site",
            "preview_without_blender",
            "walkable_scene",
            "site_audit",
            "pacing_estimate",
            "encounter_intel",
        }
    )
    output_contract_version = "lot.site.0.18"

    def _stem(self, job_spec: Mapping[str, object]) -> str:
        spec = job_spec.get("site_spec_path")
        return Path(str(spec)).stem if spec else "site"

    def validate_configuration(
        self, job_spec: Mapping[str, object], context: Mapping[str, object]
    ) -> Sequence[str]:
        problems: list[str] = []
        spec = job_spec.get("site_spec_path")
        if not spec:
            problems.append("lot job requires a site_spec_path (site_spec.json)")
        elif not Path(str(spec)).exists():
            problems.append(f"lot site spec missing: {spec}")
        return problems

    def fingerprint_inputs(
        self, job_spec: Mapping[str, object], context: Mapping[str, object]
    ) -> Mapping[str, object]:
        fp: dict[str, object] = {
            "walkable": bool(job_spec.get("walkable", True)),
            "navqa": bool(job_spec.get("navqa", False)),
        }
        spec = job_spec.get("site_spec_path")
        if spec and Path(str(spec)).exists():
            fp["site_spec_hash"] = hash_file(Path(str(spec)))
        # Everything the site spec NAMES, not just the GLBs.
        #
        # This hashed `building_glbs` alone, and a building is more than its
        # mesh: Lot merges each building's `gameplay.json` into the site's, and
        # its `<stem>.lights.json` into `site.site.lights.json`. Deli Counter's
        # light-anchor fix (2026-08-02) changed only the light manifests --
        # every shell.glb came out byte-identical, because the geometry did not
        # move -- so the fingerprint was unchanged, Lot read `cache`, and the
        # site shipped the OLD anchor heights while DC's own output carried the
        # new ones. A stage whose output depends on a file its fingerprint does
        # not watch will serve a stale answer and call it a hit.
        #
        # Read the spec rather than trusting the caller's list: the spec is what
        # Lot actually consumes, so a building added there cannot be missed by
        # someone forgetting to extend a parallel argument.
        inputs: dict[str, str] = {}

        def _fold(path: Path) -> None:
            if path.exists() and path.is_file():
                inputs[path.name] = hash_file(path)
                inputs.update(scene_payload_hashes(path))

        for b in job_spec.get("building_glbs", []):
            _fold(Path(str(b)))
        if spec and Path(str(spec)).exists():
            try:
                doc = json.loads(Path(str(spec)).read_text(encoding="utf-8"))
            except (OSError, ValueError):
                doc = {}
            for b in doc.get("buildings", []) or []:
                for key in ("scene", "glb", "gameplay"):
                    ref = b.get(key)
                    if not ref:
                        continue
                    src = Path(str(ref))
                    _fold(src)
                    # The sibling manifests Lot reads off the same stem. A
                    # `shell.glb` is accompanied by `shell.gameplay.json` and
                    # `shell.lights.json`; the spec names the first two and
                    # never the third.
                    stem = src.with_suffix("")
                    for sibling in (".lights.json", ".gameplay.json"):
                        _fold(Path(str(stem) + sibling))
        if inputs:
            fp["building_hashes"] = inputs
        return fp

    def plan_commands(
        self, job_spec: Mapping[str, object], context: Mapping[str, object]
    ) -> Sequence[PlannedCommand]:
        repo = Path(str(context["repository"]))
        work = Path(str(context["work_dir"]))
        py = context.get("python_executable") or "python"
        spec = str(job_spec.get("site_spec_path", ""))
        stem = self._stem(job_spec)

        args = [str(repo / "lot.py"), spec, str(work)]
        if job_spec.get("walkable", True):
            args.append("--walkable")
        if job_spec.get("navqa"):
            args.append("--navqa")

        expected = [f"{stem}.site.gameplay.json", f"{stem}.tscn",
                    f"{stem}.site.lights.json"]
        if job_spec.get("walkable", True):
            expected.append(f"{stem}_walk.tscn")
        # Ask for what the flag was passed for. Without this the navqa scene is
        # requested and its absence is discovered downstream, by the walktest
        # stage failing its own pre-flight -- one stage further from the tool
        # that was supposed to write it.
        if job_spec.get("navqa"):
            expected.append(f"{stem}_navqa.tscn")

        return [
            PlannedCommand(
                executable=Path(str(py)),
                arguments=tuple(args),
                working_directory=repo,
                expected_outputs=tuple(expected),
                resource_class="python_cpu",
                timeout_seconds=600,
            )
        ]

    def collect_outputs(
        self, job_spec: Mapping[str, object], context: Mapping[str, object]
    ) -> Iterable[Path]:
        work = Path(str(context["work_dir"]))
        wanted = (".tscn", ".json", ".csv")
        return sorted(p for p in work.rglob("*") if p.is_file() and p.suffix in wanted)

    def normalize_validation(
        self, output_paths: Sequence[Path]
    ) -> Sequence[Mapping[str, object]]:
        issues: list[dict] = []
        gameplay = next(
            (p for p in output_paths if p.name.endswith(".site.gameplay.json")), None)
        if gameplay is None:
            return issues
        try:
            data = json.loads(gameplay.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return issues

        # Pacing is an ESTIMATE and never blocks (24.2). Surface an outside-target
        # window as an informational note the operator can weigh.
        pacing = data.get("pacing") or {}
        status = str(pacing.get("status", ""))
        if "outside target" in status:
            issues.append({
                "code": "LOT_PACING_OUTSIDE_TARGET",
                "severity": "moderate",
                "category": "pacing",
                "message": (f"pacing estimate {pacing.get('estimate_expected_min','?')} min "
                            f"({pacing.get('range_min','?')}) vs target "
                            f"{pacing.get('target_min','?')}: {status}"),
                "blocking": False,  # pacing never blocks
                "raw_source_path": str(gameplay),
            })

        # Structured tactical findings, if Lot emitted any.
        tactical = data.get("tactical") or {}
        for raw in (tactical.get("findings", []) if isinstance(tactical, dict) else []):
            sev = raw.get("severity", "moderate")
            issues.append({
                "code": raw.get("code", "LOT_TACTICAL_FINDING"),
                "severity": sev,
                "category": raw.get("category", "combat_structure"),
                "message": raw.get("message", ""),
                "blocking": sev == "blocker",
                "raw_source_path": str(gameplay),
            })
        return issues
