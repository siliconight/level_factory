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
    # 0.4.0: the OUTPUT LAYOUT changed -- buildings are staged under lot/<id>/
    # and every ext_resource is relative rather than res://C:/... An entry
    # cached under the old rules is a site whose refs resolve nowhere, so it
    # must be retired rather than served alongside the new ones.
    adapter_version = "0.4.0"
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
        # The staged sources, by their ABSOLUTE build-time paths.
        #
        # The loop above reads the spec rather than trusting the caller's list,
        # so a building added to the spec cannot be missed by someone forgetting
        # to extend a parallel argument. That property depends on the paths in
        # the spec resolving, and they are now relative to the site out dir --
        # so `_fold` would test them against the process CWD, miss, and quietly
        # fold nothing. The manifest is derived from the same spec by the same
        # function, so folding it keeps the property rather than replacing it
        # with a promise.
        manifest_path = job_spec.get("staging_manifest_path")
        if manifest_path and Path(str(manifest_path)).exists():
            try:
                man = json.loads(
                    Path(str(manifest_path)).read_text(encoding="utf-8"))
            except (OSError, ValueError):
                man = {}
            for source in (man.get("packages") or {}).values():
                _fold(Path(str(source)) / "site.tscn")
            for source in (man.get("glbs") or {}).values():
                _fold(Path(str(source)))
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
        # Scene-relative ext_resource paths in the shipped scenes. Godot 4.7
        # resolves a non-res:// path against the referencing scene's own
        # directory (probed: a root scene instancing lot/a/inner.tscn, which
        # named a bare leaf.tscn existing only beside it, imported and loaded
        # clean), which is what makes the out dir droppable anywhere rather
        # than only at a consumer's project root.
        manifest = str(job_spec.get("staging_manifest_path", ""))
        if manifest:
            args.append("--portable")

        commands = []
        if manifest:
            # FIRST, and a separate command rather than a side effect inside
            # this function: plan_commands is called to build the fingerprint
            # as well as to run the job, including on the cache-hit path where
            # nothing is meant to execute. Copying geometry from here would run
            # at times nobody chose. As a planned command it is logged,
            # re-runnable alone, and folded into the fingerprint like any other.
            # this file is level_factory/adapters/lot/__init__.py, so the
            # level_factory root is three names up: lot -> adapters -> here.
            lf_root = Path(__file__).resolve().parents[2]
            commands.append(PlannedCommand(
                executable=Path(str(py)),
                arguments=(str(lf_root / "tools" / "stage_site_packages.py"),
                           manifest, str(work)),
                working_directory=lf_root,
                expected_outputs=tuple(self._staged_outputs(manifest)),
                resource_class="python_cpu",
                timeout_seconds=600,
            ))

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

        commands.append(PlannedCommand(
            executable=Path(str(py)),
            arguments=tuple(args),
            working_directory=repo,
            expected_outputs=tuple(expected),
            resource_class="python_cpu",
            timeout_seconds=600,
        ))
        return commands

    @staticmethod
    def _staged_outputs(manifest_path: str) -> list[str]:
        """What the staging step must have put in the out dir, by name.

        Named as expected outputs so the scheduler fails the job when a package
        did not arrive, instead of leaving it to Lot to emit a site with a
        building missing and every stage reporting success -- which a varied lot
        has already done once.
        """
        try:
            doc = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            # The manifest is written at plan time and read here at run time.
            # If it cannot be read there is nothing to assert; the staging
            # command will say so itself and exit nonzero.
            return []
        out = [f"lot/{pid}/site.tscn" for pid in (doc.get("packages") or {})]
        out += [f"buildings/{bid}.glb" for bid in (doc.get("glbs") or {})]
        return sorted(out)

    def collect_outputs(
        self, job_spec: Mapping[str, object], context: Mapping[str, object]
    ) -> Iterable[Path]:
        work = Path(str(context["work_dir"]))
        # .glb and .gd are here because the site now CONTAINS its buildings
        # rather than pointing at them. Left at (.tscn, .json, .csv), the staged
        # geometry and the walk scripts would never be published to out/ nor
        # written to the build cache: the attempt dir would look correct and a
        # cache hit would restore a site scene referencing files that are not
        # there. A published artifact has to be the whole artifact.
        wanted = (".tscn", ".json", ".csv", ".glb", ".gd")
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
