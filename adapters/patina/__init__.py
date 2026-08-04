"""Patina adapter (TDD 24.6) — bound to the REAL Patina 0.18.0 CLI.

Real invocation (verified against the uploaded repo):

    patina <shell.glb> [--mode vertex-color|procedural|byo] [--theme NAME]
           [--dressing --panel-fields --frames --gutters --pilasters]
           --out <dir>/<stem>.patina.glb

Patina consumes a Deli Counter / Zoo-kit ``.glb`` shell as POSITIONAL input and
writes, next to the ``--out`` glb path:

    <stem>.patina.glb            (treated geometry; collision UNTOUCHED)
    <stem>.patina.json           (art-pass manifest)
    <stem>.patina.gameplay.json  (gameplay passthrough)

Collision preservation is a hard guarantee (Patina prints "collision N tris
(untouched)"); the LF post-art regression re-checks it against the lock.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, Mapping, Sequence

from packages.adapters.sdk import BaseAdapter, PlannedCommand
from packages.core.hashing import hash_file


class PatinaAdapter(BaseAdapter):
    adapter_id = "patina"
    # 0.3.0 stopped asking for --panel-fields and --pilasters (see the flag
    # block below). The bump is load-bearing: the flags an adapter passes are
    # not otherwise in the fingerprint, so without it every dressing stage
    # cache-hits and the pipeline ships the covers it was told to stop making.
    adapter_version = "0.3.0"
    capabilities = frozenset(
        {"base_cohesion", "dressing_manifest", "trim_atlas", "photo_projection",
         "templates", "overrides", "deterministic_build"}
    )
    output_contract_version = "patina.pass.0.18"

    def _stem(self, job_spec: Mapping[str, object]) -> str:
        glb = job_spec.get("input_glb")
        return Path(str(glb)).stem if glb else "shell"

    def _out_glb(self, job_spec, context) -> Path:
        work = Path(str(context["work_dir"]))
        return work / f"{self._stem(job_spec)}.patina.glb"

    def validate_configuration(self, job_spec, context) -> Sequence[str]:
        problems: list[str] = []
        glb = job_spec.get("input_glb")
        if not glb:
            problems.append("patina job requires an input_glb (a DC/Zoo shell .glb)")
        elif not Path(str(glb)).exists():
            problems.append(f"patina input glb missing: {glb}")
        mode = job_spec.get("art_mode", "vertex-color")
        if mode not in ("vertex-color", "procedural", "byo"):
            problems.append(f"unknown patina art mode: {mode}")
        return problems

    def fingerprint_inputs(self, job_spec, context) -> Mapping[str, object]:
        fp: dict[str, object] = {
            "art_mode": job_spec.get("art_mode", "vertex-color"),
            "theme": job_spec.get("theme"),
            "dressing": bool(job_spec.get("dressing")),
            "panel_size": job_spec.get("panel_size"),
            "panel_gap": job_spec.get("panel_gap"),
            "seed": job_spec.get("seed"),
        }
        glb = job_spec.get("input_glb")
        if glb and Path(str(glb)).exists():
            fp["input_glb_hash"] = hash_file(Path(str(glb)))
        for key in ("overrides_path", "family_path"):
            p = job_spec.get(key)
            if p and Path(str(p)).exists():
                fp[key + "_hash"] = hash_file(Path(str(p)))
        return fp

    def plan_commands(self, job_spec, context) -> Sequence[PlannedCommand]:
        repo = Path(str(context["repository"]))
        py = context.get("python_executable") or "python"
        glb = str(job_spec.get("input_glb", ""))
        out_glb = self._out_glb(job_spec, context)
        stem = self._stem(job_spec)

        args = ["-m", "patina.cli", glb,
                "--mode", str(job_spec.get("art_mode", "vertex-color")),
                "--out", str(out_glb)]
        if job_spec.get("theme"):
            args += ["--theme", str(job_spec["theme"])]
        if job_spec.get("seed") is not None:
            args += ["--seed", str(job_spec["seed"])]
        # Dressing pass adds the facade-kit order flags and --anchors, which is
        # what makes Patina emit <stem>.patina.dressing.json (schema
        # patina-dressing/1) — the manifest Zoo's --dress consumes.
        if job_spec.get("dressing"):
            # --frames is DELIBERATELY absent. Patina's frame cover draws a
            # head, sill and two jambs around every opening -- and every Zoo
            # module that has an opening already frames it: doorway ships
            # Jamb_L / Jamb_R / Header, window ships those plus Sill and
            # Glass. The result was two nested frames on every door and
            # window, 16 openings x 4 strips of duplicate geometry, which
            # reads to a human as a smaller door frame inside the door frame.
            # Patina's version also adds a SILL to doorways, a bar across a
            # threshold you walk over, which Zoo's doorway correctly omits.
            # A breach is a hole blown through a wall and should carry no
            # frame at all.
            #
            # frame_orders is kept in Patina for a greybox build with no
            # themed modules to do the framing; it is simply not asked for
            # when Zoo modules are in play, which in this pipeline is always.
            #
            # --panel-fields and --pilasters are gone for a related but worse
            # reason: not duplicate geometry, a broken rule. Both draw a box
            # standing PROUD of the wall -- 1.2 cm for a panel, 5 cm for a
            # pilaster -- and a Zoo module's collider is built from the same
            # slab as its visual, so the collision volume ends exactly at the
            # wall face. Every one of those boxes was therefore non-collision
            # geometry standing in space a body walks through, which is "no
            # dressing in walkable space or firing lines" broken by the SHAPE
            # of the solution rather than by a placement mistake.
            #
            # There is no aiming fix. Patina now takes the outward face from
            # the building centroid and the inward count went 416 -> 0; the
            # covers then stood in the gaps BETWEEN buildings, which Lot makes
            # into routes. Both sides of a wall are walkable.
            #
            # So wall articulation moved INTO the module: `arch.relief_parts`
            # carves a plinth, piers and recessed fields within the authored
            # depth, where nothing can be outside the collider by construction.
            # --gutters stays -- a gutter is a roofline object, 7.6 m up on a
            # 3.7 m storey, well clear of the 1.8 m a body occupies.
            #
            # panel_orders and pilaster_orders are kept in Patina for a greybox
            # build whose modules carry no relief of their own; like --frames,
            # they are simply not asked for when Zoo modules are in play.
            args += ["--dressing", "--anchors", "--gutters"]
        if job_spec.get("templates"):
            args.append("--templates")
        if job_spec.get("overrides_path"):
            args += ["--overrides", str(job_spec["overrides_path"])]
        if job_spec.get("family_path"):
            args += ["--family", str(job_spec["family_path"])]

        expected = [f"{stem}.patina.glb", f"{stem}.patina.json",
                    f"{stem}.patina.gameplay.json"]
        if job_spec.get("dressing"):
            # --anchors makes Patina emit the dressing manifest Zoo consumes.
            expected.append(f"{stem}.patina.dressing.json")

        return [PlannedCommand(
            executable=Path(str(py)), arguments=tuple(args),
            working_directory=repo,
            expected_outputs=tuple(expected),
            resource_class="python_cpu", timeout_seconds=600,
        )]

    def collect_outputs(self, job_spec, context) -> Iterable[Path]:
        work = Path(str(context["work_dir"]))
        return sorted(p for p in work.rglob("*")
                      if p.is_file() and p.suffix in (".glb", ".png", ".json"))

    def normalize_validation(self, output_paths) -> Sequence[Mapping[str, object]]:
        issues: list[dict] = []
        manifest = next((p for p in output_paths if p.name.endswith(".patina.json")), None)
        if manifest is not None:
            try:
                data = json.loads(manifest.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                data = {}
            # Surface Patina's own structured warnings, if any.
            for raw in (data.get("warnings", []) if isinstance(data, dict) else []):
                issues.append({
                    "code": "PATINA_WARNING", "severity": "minor",
                    "category": "presentation", "message": str(raw),
                    "blocking": False, "raw_source_path": str(manifest),
                })
        return issues
