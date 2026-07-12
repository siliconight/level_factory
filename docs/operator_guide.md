# Operator Guide (Phase 1)

## The loop

1. `init` a workspace; edit `tools.local.json` with repo + executable paths.
2. `doctor` until every required tool is PASS (NOT_CONFIGURED blocks only that
   tool's stages).
3. `batch create` from a `batch.json` + `briefs/*.json`.
4. `plan --target functional-lock` to preview the DAG.
5. `run --target functional-lock` to generate candidates and their evidence.
6. Walk candidates in Godot (open the Lot walkable scene). Metrics compare;
   they do not select. `approve ... candidate_selected --candidate <id>`.
7. `approve ... brief_approved` and, once locked, `run --target dispatch-handoff`
   to package the shell handoff.

## Exit codes

0 ok · 1 non-blocking findings · 2 blocked (validation/approval) · 3 config ·
4 tool failure · 5 internal · 130 cancelled.

## Cache

`cache inspect` shows blob/manifest counts; `cache prune` drops unreferenced
blobs. Changing a tool commit or any declared input invalidates dependent jobs.

## Presentation + export (Phase 2)

Once a shell is locked (`functional_shell_locked` approved — this also records
the **functional lock**: hashes of collision, the anchor registry, the route
graph, and clearance metrics):

8. `run --target presentation` runs the PS2 art pass: shared Pixelcoat packs,
   Zoo structural kit (skinned by the packs), Patina base cohesion + dressing
   manifest, Zoo collision-free dressing, then Lux apply, then the Dispatch
   handoff. Put shared recipes in `<workspace>/shared/pixelcoat/recipes/`
   (see `examples/shared/pixelcoat/`).
9. `export <mission> --mode portable-godot|pure-shell|source-authoring
   --format folder|zip` assembles a self-contained mission folder. Before it
   writes anything it runs the **post-art regression**: if collision, an anchor,
   or the route graph moved during the art pass, export fails with exit 2.
   - `portable-godot` — runnable in a clean project, no authoring tools/add-ons.
   - `pure-shell` — functional geometry + collision + anchors only (no art).
   - `source-authoring` — includes source specs for re-authoring.
10. `portability-test <mission> --mode <mode>` copies the export into a fresh
    Godot 4.7 project and instantiates the mission scene headlessly. PASS
    requires a clean resource closure (no absolute paths, no `user://`, no
    unresolved `res://`, no required autoload/plugin) **and** a non-failing
    engine instantiate. The report is written to
    `.level_factory/exports/<mission>.<mode>.portability.json`.

### What the functional lock protects
Collision, the gameplay-anchor registry, the route graph, and critical
clearance metrics. It does **not** protect non-colliding dressing, materials,
decals, Lux presets, or presentation lights — those are free to change without
re-locking. A functional change (or an ambiguous one) invalidates the lock and
forces re-approval; see `packages/pipeline/invalidation.py`.
