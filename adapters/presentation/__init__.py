"""Presentation compose adapter (TDD 15.2 — the --art wiring).

This is the stage that fulfils the README "Output layers" promise: with
``--art`` selected, Zoo's themed modules must actually *fill Deli Counter's
slots at DC's collision*, not just be built and left on the shelf. Before this
stage existed, ``lux_apply`` lit the raw greybox ``site.tscn`` and the export
shipped a grey level — a broken contract, not a missing feature.

Deli Counter is the source of collision truth, so the composition is done by
DC's OWN composer, not a reimplementation here: ``portable_building.build_package``
strips the greybox down to its floors+collision base (the walkable shell),
then instances each themed Zoo module onto its slot with the fit-to-greybox
rotation (``themed_tscn._fit_rotation`` over ``tscn_export.godot_basis``) so the
visual sits exactly on the collision. It also runs a ground-truth placement gate
(visual footprint vs greybox footprint) and a closure self-check.

We invoke it out-of-process through a thin LF driver (``run_presentation_compose.py``)
that adds the DC repo to ``sys.path`` and calls ``build_package`` — DC keeps
ownership of the geometry/alignment logic; LF just orchestrates. It's bpy-free
pure Python (no Blender, no Godot), so it runs anywhere.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, Mapping, Sequence

from packages.adapters.sdk import BaseAdapter, PlannedCommand
from packages.core.hashing import hash_file

# The composed scene is always emitted under a STABLE building id ("site") so
# downstream (Lux) can resolve it without reading DC's building_id at plan time.
_STABLE_BID = "site"
_OUT_SUBDIR = "presentation"
_SCENE_REL = f"{_OUT_SUBDIR}/{_STABLE_BID}.tscn"


def _driver_path() -> Path:
    # <repo_root>/assets/scripts/run_presentation_compose.py
    return (Path(__file__).resolve().parents[2]
            / "assets" / "scripts" / "run_presentation_compose.py")


#: DC modules this job actually executes, relative to the DC repo root. Listed
#: rather than globbed: a glob over the repo would rebuild the compose whenever
#: any unrelated DC file moved (a test, a preset, a status script), and a cache
#: that invalidates on everything is a cache nobody keeps.
_COMPOSER_SOURCES = (
    "portable_building.py",   # build_package / strip_greybox_base / roof_covered_nodes
    "themed_tscn.py",         # themed_slot_ids + the fit-to-greybox instancing
    "tscn_export.py",         # godot_basis, the rotation the fit depends on
    "zfight_gate.py",         # the coplanar gate whose findings ride the manifest
    "circulation.py",         # the prop-vs-circulation gate, likewise
    "VERSION",
)


def _composer_fingerprint(job_spec, context) -> dict:
    """Hash of the DC code this compose runs.

    Returns ``{}`` when the repo is not resolvable -- a missing repo is
    `plan_commands`' problem to report, and a fingerprint that raises would turn
    a bad path into a crash at cache-lookup time.
    """
    repo = job_spec.get("deli_repo") or context.get("repository")
    if not repo:
        return {}
    root = Path(str(repo))
    out: dict = {}
    for rel in _COMPOSER_SOURCES:
        p = root / rel
        if p.exists():
            out[rel] = hash_file(p)
    return out


class PresentationAdapter(BaseAdapter):
    adapter_id = "presentation"
    # 0.1.2: compose gates (z-fight/ladder/lineage) + dressing/fixtures
    # layers -- version participates in the build fingerprint, so bumping it
    # guarantees every mission recomposes under the new gates.
    adapter_version = "0.2.0"
    capabilities = frozenset(
        {"themed_compose", "collision_fit", "greybox_base", "placement_gate",
         "marker_bake", "closure_check"}
    )
    output_contract_version = "presentation.compose.0.1"

    def probe(self, installation: Mapping[str, str]):
        # This adapter has no repo of its own; it drives DC's composer. Report
        # available whenever the DC repo carries portable_building.py.
        from packages.adapters.sdk import ToolProbe
        deli = installation.get("repositories", {}).get("deli_counter", "")
        ok = bool(deli) and (Path(str(deli)) / "portable_building.py").exists()
        problems = () if ok else (
            "deli_counter repo missing portable_building.py (DC's composer)",)
        return ToolProbe(
            available=ok, tool_version=self.adapter_version,
            repository_commit=None, executable_versions={},
            capabilities=self.capabilities, problems=problems)

    def validate_configuration(self, job_spec, context) -> Sequence[str]:
        problems: list[str] = []
        deli_repo = job_spec.get("deli_repo") or context.get("repository")
        if not deli_repo:
            problems.append("presentation compose requires the deli_counter repo path")
        elif not (Path(str(deli_repo)) / "portable_building.py").exists():
            problems.append(
                f"DC composer not found: {deli_repo}/portable_building.py")
        for key in ("slots_path", "greybox_glb"):
            p = job_spec.get(key)
            if not p:
                problems.append(f"presentation compose requires {key}")
            elif not Path(str(p)).exists():
                problems.append(f"{key} missing: {p}")
        mods = job_spec.get("modules_dir")
        if not mods:
            problems.append("presentation compose requires modules_dir (Zoo kit out)")
        elif not Path(str(mods)).exists():
            problems.append(f"modules_dir missing: {mods}")
        if not _driver_path().exists():
            problems.append(f"LF compose driver missing: {_driver_path()}")
        return problems

    def fingerprint_inputs(self, job_spec, context) -> Mapping[str, object]:
        fp: dict[str, object] = {
            "theme": job_spec.get("theme"),
            "style": job_spec.get("style", 1),
        }
        for key in ("slots_path", "gameplay_path", "greybox_glb"):
            p = job_spec.get(key)
            if p and Path(str(p)).exists():
                fp[key + "_hash"] = hash_file(Path(str(p)))
        mods = job_spec.get("modules_dir")
        if mods and Path(str(mods)).exists():
            fp["module_hashes"] = {
                g.name: hash_file(g)
                for g in sorted(Path(str(mods)).rglob("*.glb"))
            }
        # Content layers (dressing props / light fixtures) are compose inputs
        # exactly like the kit: a changed layer MUST invalidate the compose,
        # or a stale prop pass ships against fresh architecture.
        for key in ("dressing_glb", "fixtures_glb"):
            lp = job_spec.get(key)
            if lp and Path(str(lp)).exists():
                fp[key + "_hash"] = hash_file(Path(str(lp)))
        # ...AND THE COMPOSER ITSELF. This job does not merely read DC's data,
        # it EXECUTES DC's code -- `portable_building.build_package`, through
        # the driver, per this module's own docstring. So a change to that code
        # changes this job's output while every hash above stays identical, and
        # the cache serves the old package.
        #
        # Measured 2026-08-05: `strip_greybox_base` was fixed in DC (exact
        # slot-id match, so `VAULT` stopped deleting `VAULTLEDGE_0`'s visual and
        # leaving its collider -- an invisible wall). DC committed, DC's suite
        # went green, `run --art --force` reported deli_generate SUCCEEDED and
        # zoo_kit_build SUCCEEDED, and this job reported `cache`. The composed
        # `site_base.glb` came back byte-identical, invisible wall intact. The
        # rebuild looked real and wasn't.
        #
        # `verify-contracts` guards a sub-tool DRIFTING out from under an
        # adapter. This is the same failure with the opposite sign -- a sub-tool
        # FIX not reaching a cached job -- and nothing was watching for it.
        fp["composer"] = _composer_fingerprint(job_spec, context)
        return fp

    def plan_commands(self, job_spec, context) -> Sequence[PlannedCommand]:
        work = Path(str(context["work_dir"]))
        py = context.get("python_executable") or "python"
        deli_repo = str(job_spec.get("deli_repo") or context.get("repository") or "")
        out_dir = work / _OUT_SUBDIR

        args = [
            str(_driver_path()),
            "--deli-repo", deli_repo,
            "--slots", str(job_spec.get("slots_path", "")),
            "--modules", str(job_spec.get("modules_dir", "")),
            "--theme", str(job_spec.get("theme", "") or "delco"),
            "--style", str(job_spec.get("style", 1)),
            "--greybox", str(job_spec.get("greybox_glb", "")),
            "--building-id", _STABLE_BID,
            "--out", str(out_dir),
        ]
        if job_spec.get("gameplay_path"):
            args += ["--gameplay", str(job_spec["gameplay_path"])]
        # content layers: bundled + instanced by the composer, lineage-guarded
        # by the driver (a layer from a different build fails the job).
        if job_spec.get("dressing_glb"):
            args += ["--dressing", str(job_spec["dressing_glb"])]
        if job_spec.get("fixtures_glb"):
            args += ["--fixtures", str(job_spec["fixtures_glb"])]

        return [PlannedCommand(
            executable=Path(str(py)), arguments=tuple(args),
            working_directory=Path(str(deli_repo)) if deli_repo else work,
            expected_outputs=(_SCENE_REL,),
            resource_class="python_cpu", timeout_seconds=600,
        )]

    def collect_outputs(self, job_spec, context) -> Iterable[Path]:
        # Publish the WHOLE composed package, not just scene/asset files — the
        # portable project needs project.godot + the entry scene to open
        # standalone in Godot. An earlier suffix filter dropped project.godot,
        # so the published folder wasn't a Godot project (opened the Project
        # Manager instead of the level).
        work = Path(str(context["work_dir"]))
        return sorted(p for p in work.rglob("*") if p.is_file())

    def normalize_validation(self, output_paths) -> Sequence[Mapping[str, object]]:
        issues: list[dict] = []
        manifest = next((p for p in output_paths
                         if p.name == "portable_resource_manifest.json"), None)
        if manifest is None:
            return issues
        try:
            man = json.loads(manifest.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return issues

        # Closure: a dangling res:// ref means Lux will light a broken scene.
        closure = man.get("closure") or {}
        if closure and not closure.get("portable", True):
            issues.append({
                "code": "PRESENTATION_UNRESOLVED_REF",
                "severity": "blocker", "category": "packaging",
                "message": ("composed scene has dangling/absolute resource refs: "
                            f"{(closure.get('dangling_refs') or [])[:5]}"),
                "blocking": True, "raw_source_path": str(manifest)})

        # Ground-truth placement gate: themed visuals must sit on DC's collision.
        # Advisory (non-blocking) for now — a partial kit legitimately leaves some
        # slots greybox — but surfaced loudly so a real alignment regression shows.
        pc = man.get("placement_check")
        if pc and pc.get("mismatched"):
            issues.append({
                "code": "PRESENTATION_PLACEMENT_MISMATCH",
                "severity": "moderate", "category": "collision",
                "message": (f"{pc.get('mismatched')} themed module(s) do not match "
                            f"the greybox footprint (visual off the collision); "
                            f"{pc.get('matched')}/{pc.get('checked')} aligned"),
                "blocking": False, "raw_source_path": str(manifest)})

        # No themed modules resolved at all = the kit didn't feed the compose.
        if not man.get("walkable", True):
            issues.append({
                "code": "PRESENTATION_NO_BASE",
                "severity": "moderate", "category": "packaging",
                "message": "no greybox base composed — level has no floors to stand on",
                "blocking": False, "raw_source_path": str(manifest)})
        return issues
