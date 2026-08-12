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

# A VARIED THEMED LOT composes one scene per archetype, here. The mission's
# own shell is still composed to `_SCENE_REL` -- it satisfies the job's output
# contract, keeps the single-shell path byte-for-byte, and is what Lux still
# lights. See docs/VARIED_THEMED_LOT.md: until `--render` moves Lux to the
# assembled site, a varied lot is SKINNED AND WALKABLE BUT UNLIT, and that is
# a stated limitation rather than a surprise.
_LOT_SUBDIR = f"{_OUT_SUBDIR}/lot"


def _lot_archetypes(job_spec) -> list:
    """The archetypes this compose must theme, [] for the single-shell path.

    Entries are `building_library.index` rows: {id, family, glb, gameplay,
    slots}. The list is chosen ONCE, in the job spec, and travels with it --
    re-deriving it here from (library, seed, count) would be a second caller
    of `pick_lot` agreeing by luck rather than by construction.
    """
    lot = job_spec.get("lot_archetypes") or []
    return [a for a in lot if a.get("id") and a.get("glb") and a.get("slots")]


def _layer_map(value) -> dict:
    """``{archetype_id: path}`` for a content layer, keyed ``""`` for the shell.

    The mission's own shell has no archetype id and is keyed on the empty
    string, which is what the spec builder writes for a job with no
    `archetype_id`. A bare string is the PRE FAN-OUT shape and can only mean the
    mission shell -- back then there was exactly one layer to mean.
    """
    if isinstance(value, str):
        return {"": value} if value else {}
    return {str(k): str(v) for k, v in (value or {}).items() if v}


def resolve_layer(directory: str, suffix: str) -> tuple[str, str]:
    """``(path, problem)`` -- the one ``*<suffix>`` file in ``directory``.

    Called at EXECUTION time, from `validate_configuration` and
    `plan_commands`, both of which run after this job's dependencies have
    succeeded. The spec can only construct the directory: it is written while
    the plan is built, before the job that fills it has run.

    Returns a problem string rather than raising so the caller can collect
    every fault and report them together -- a compose missing three layers is
    making three statements.

    Absence is a PROBLEM, not an empty answer. Passing no `--dressing` composes
    a bare building and exits zero, so a building silently missing its props
    looks exactly like a building that was never meant to have any.
    """
    root = Path(str(directory))
    if not root.is_dir():
        return "", f"layer directory missing: {root}"
    hits = sorted(root.glob(f"*{suffix}"))
    if not hits:
        return "", (f"no '*{suffix}' in {root} -- the job that bakes it "
                    f"reported success without publishing one")
    if len(hits) > 1:
        return "", (f"{root} holds {len(hits)} '{suffix}' layers "
                    f"({', '.join(h.name for h in hits)}); one bake is one "
                    f"placement against one shell and there is no basis for "
                    f"choosing between them")
    return str(hits[0]), ""


def _driver_path() -> Path:
    # <repo_root>/assets/scripts/run_presentation_compose.py
    return (Path(__file__).resolve().parents[2]
            / "assets" / "scripts" / "run_presentation_compose.py")


class PresentationAdapter(BaseAdapter):
    adapter_id = "presentation"
    # 0.1.2: compose gates (z-fight/ladder/lineage) + dressing/fixtures
    # layers -- version participates in the build fingerprint, so bumping it
    # guarantees every mission recomposes under the new gates.
    # 0.3.0: the probe now reports DELI COUNTER's revision rather than this
    # adapter's version. The rules for computing this stage's fingerprint
    # changed, so entries computed under the old rules are not comparable and
    # must be retired rather than served alongside the new ones.
    adapter_version = "0.3.0"
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
        # THE TOOL THIS STAGE RUNS IS DELI COUNTER, so DC's revision is what
        # has to reach the fingerprint.
        #
        # This reported `self.adapter_version` -- which `BuildFingerprint`
        # already carries in its own `adapter_version` field -- and `None` for
        # the commit. Net effect: no edit to DC's composer could change this
        # stage's fingerprint. Measured 2026-08-09, `themed_tscn.PLATE_ROLES`
        # was corrected so the composer names the roof module Zoo builds; the
        # next run reported `cache` and shipped the scene naming the old one.
        #
        # `_read_git_commit` carries a `+dirty.<hash>` marker over the CONTENT
        # of modified tracked files, which is the state a fix in progress is
        # always in -- see its docstring, written after the same failure.
        repo = Path(str(deli)) if ok else None
        return ToolProbe(
            available=ok,
            tool_version=(self._read_tool_version(repo) if repo else None),
            repository_commit=(self._read_git_commit(repo) if repo else None),
            executable_versions={},
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
        # One kit per building, keyed like the other layers. Every one is
        # named, and every one has to be there: a compose that silently drops
        # a building's kit is the substitution this fan-out removed.
        mods = _layer_map(job_spec.get("modules_dir"))
        if not mods:
            problems.append("presentation compose requires modules_dir (Zoo kit out)")
        for aid, d in sorted(mods.items()):
            if not Path(str(d)).exists():
                problems.append(
                    f"modules_dir for {aid or 'the mission shell'} missing: {d}")
        if not _driver_path().exists():
            problems.append(f"LF compose driver missing: {_driver_path()}")
        # A varied lot fails HERE if a building is unusable, not three stages
        # downstream. `building_library.index` already drops archetypes with a
        # missing part, so anything that reaches this list should be complete;
        # if it is not, the selection and the filesystem disagree and that is
        # worth saying out loud.
        for a in _lot_archetypes(job_spec):
            for key in ("glb", "slots", "gameplay"):
                p = a.get(key)
                if p and not Path(str(p)).exists():
                    problems.append(
                        f"lot archetype {a['id']}: {key} missing: {p}")
        # Every content layer this job was told about must actually be there.
        # It runs after the bakes have succeeded, so an empty directory here is
        # a real fault -- and the alternative is composing a bare building and
        # exiting zero, which is how five buildings came out undressed with
        # every stage reporting success.
        for key, suffix in (("dressing_glb", "_dressing.glb"),
                            ("fixtures_glb", "_fixtures.glb")):
            for aid, directory in sorted(_layer_map(job_spec.get(key)).items()):
                _, problem = resolve_layer(directory, suffix)
                if problem:
                    problems.append(
                        f"{key} for {aid or 'the mission shell'}: {problem}")
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
        # Per building, and keyed by building. Hashing every kit into one flat
        # `{name: hash}` would let two buildings' `wall_rockay_01_w200.glb`
        # collide on the key -- which is the same blindness, in the instrument
        # that is supposed to notice it.
        for aid, d in sorted(_layer_map(job_spec.get("modules_dir")).items()):
            p = Path(str(d))
            if p.exists():
                fp[f"module_hashes[{aid}]"] = {
                    g.name: hash_file(g) for g in sorted(p.rglob("*.glb"))
                }
        # Content layers (dressing props / light fixtures) are compose inputs
        # exactly like the kit: a changed layer MUST invalidate the compose,
        # or a stale prop pass ships against fresh architecture.
        for key, suffix in (("dressing_glb", "_dressing.glb"),
                            ("fixtures_glb", "_fixtures.glb")):
            for aid, directory in sorted(_layer_map(job_spec.get(key)).items()):
                # The spec names a DIRECTORY -- the job that fills it has not
                # run when the spec is written. Resolve it the same way the
                # other two readers do. This hashed the value directly, and
                # `Path(a_directory).exists()` is True, so it opened a
                # directory as a file: [Errno 13] on Windows, mid-run.
                lp, problem = resolve_layer(directory, suffix)
                if problem:
                    # `validate_configuration` has already failed this job and
                    # named the building. A hashing routine should not be the
                    # thing that reports it.
                    continue
                # The mission shell keeps the historical key, so a single-shell
                # mission that has already composed does not recompose for a
                # rename. Per-building layers are new keys, so a varied lot
                # recomposes exactly once -- which it must, because until now
                # every building was fingerprinted against one building's props.
                fp[f"{key}_hash" if not aid else f"{key}_hash.{aid}"] = (
                    hash_file(Path(str(lp))))
        # EVERY archetype in the lot, or swapping one building for another
        # serves a stale compose. The composer fingerprint had exactly this
        # hole for its own sources and it took a walk to find.
        lot = _lot_archetypes(job_spec)
        if lot:
            fp["lot"] = {
                a["id"]: {
                    k: hash_file(Path(str(a[k])))
                    for k in ("glb", "slots", "gameplay")
                    if a.get(k) and Path(str(a[k])).exists()
                }
                for a in lot
            }
        return fp

    def plan_commands(self, job_spec, context) -> Sequence[PlannedCommand]:
        work = Path(str(context["work_dir"]))
        py = context.get("python_executable") or "python"
        deli_repo = str(job_spec.get("deli_repo") or context.get("repository") or "")
        cwd = Path(str(deli_repo)) if deli_repo else work

        # `dressing` and `fixtures` are ARGUMENTS, and deliberately have no
        # defaults. They used to be read from the closed-over `job_spec` while
        # the six geometry arguments were overridden per archetype, so the loop
        # below dressed five different buildings out of one building's bake --
        # the failure the comment above that loop names. A layer that is not
        # visible at the call site is a layer nobody notices is shared.
        def compose(*, slots, gameplay, greybox, out, bid, scene_rel,
                    dressing, fixtures, modules):
            args = [
                str(_driver_path()),
                "--deli-repo", deli_repo,
                "--slots", str(slots or ""),
                # A PARAMETER, not the closed-over spec. This read
                # `job_spec["modules_dir"]` until 2026-08-09 -- exactly the
                # shape the comment above describes for dressing and fixtures,
                # and exactly the same outcome: every building in the lot
                # composed with one building's kit.
                "--modules", str(modules or ""),
                "--theme", str(job_spec.get("theme", "") or "delco"),
                "--style", str(job_spec.get("style", 1)),
                "--greybox", str(greybox or ""),
                "--building-id", bid,
                "--out", str(out),
            ]
            if gameplay:
                args += ["--gameplay", str(gameplay)]
            # content layers: bundled + instanced by the composer,
            # lineage-guarded by the driver (a layer from a different build
            # fails the job).
            if dressing:
                args += ["--dressing", str(dressing)]
            if fixtures:
                args += ["--fixtures", str(fixtures)]
            return PlannedCommand(
                executable=Path(str(py)), arguments=tuple(args),
                working_directory=cwd, expected_outputs=(scene_rel,),
                resource_class="python_cpu", timeout_seconds=600,
            )

        # The mission's own shell, always, unchanged. It satisfies the job's
        # `presentation/site.tscn` output contract and is what the
        # single-shell site places. A varied lot does not place it -- see the
        # note by _LOT_SUBDIR -- but composing it keeps this path identical
        # for every mission that does not set `lot_library`, and a level that
        # has already been evaluated must not quietly become a different one.
        # Directories in the spec, files here. `validate_configuration` has
        # already refused this job if any of them cannot be resolved, so a
        # blank at this point cannot be reached by a job that is running.
        dressing = {aid: resolve_layer(d, "_dressing.glb")[0]
                    for aid, d in _layer_map(
                        job_spec.get("dressing_glb")).items()}
        fixtures = {aid: resolve_layer(d, "_fixtures.glb")[0]
                    for aid, d in _layer_map(
                        job_spec.get("fixtures_glb")).items()}
        # The kit is a DIRECTORY of modules, not one file picked by suffix, so
        # it needs no `resolve_layer` -- but it is keyed per building exactly
        # like the two above.
        modules = _layer_map(job_spec.get("modules_dir"))
        cmds = [compose(
            slots=job_spec.get("slots_path"),
            gameplay=job_spec.get("gameplay_path"),
            greybox=job_spec.get("greybox_glb"),
            out=work / _OUT_SUBDIR, bid=_STABLE_BID, scene_rel=_SCENE_REL,
            dressing=dressing.get(""), fixtures=fixtures.get(""),
            modules=modules.get(""),
        )]

        # ONE COMPOSE PER ARCHETYPE. Each building is dressed AS ITSELF: its
        # own slots, its own gameplay markers, its own greybox, its own
        # dressing and its own light fixtures. Pointing five different
        # buildings at one composed scene would place five greyboxes and
        # dress them identically, which is the lie this exists to remove --
        # and which it performed until 2026-08-06, because dressing and
        # fixtures were the two things this list did not name.
        for a in _lot_archetypes(job_spec):
            rel = f"{_LOT_SUBDIR}/{a['id']}/{_STABLE_BID}.tscn"
            cmds.append(compose(
                slots=a.get("slots"), gameplay=a.get("gameplay"),
                greybox=a.get("glb"),
                out=work / _LOT_SUBDIR / str(a["id"]),
                bid=_STABLE_BID, scene_rel=rel,
                # ITS OWN props, ITS OWN light hardware and ITS OWN kit. The
                # three geometry arguments above were already per building;
                # these were not, and that is the entire difference between a
                # building dressed as itself and five buildings wearing one
                # building's clothes. `modules` joined them on 2026-08-09 --
                # the walls, which is to say the building.
                dressing=dressing.get(str(a["id"])),
                fixtures=fixtures.get(str(a["id"])),
                modules=modules.get(str(a["id"])),
            ))
        return cmds

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
