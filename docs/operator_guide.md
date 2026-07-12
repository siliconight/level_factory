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
