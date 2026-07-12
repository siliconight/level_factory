# Batch Production Guide (Phase 4)

A batch runs N missions through production as one parallel DAG, building shared
assets once instead of per mission.

## Parallel scheduling

The scheduler runs independent jobs concurrently up to per-resource-class caps
(TDD 19.2):

```
python_cpu 4 · blender 1 · godot_headless 2 · godot_interactive 1 · io_heavy 2 · lightweight 8
```

Dependent jobs wait for their inputs; the first failure stops new dispatch and
drains in-flight jobs. The SQLite index is thread-safe (WAL + a lock), so the
worker threads share one index.

## The batch loop

1. `batch create <batch.json>` — materialize the batch and its briefs.
2. For each mission: `run --target functional-lock`, walk candidates,
   `approve ... candidate_selected`, `approve ... brief_approved`,
   `approve ... functional_shell_locked`. (A mission with no selected candidate
   is skipped by the batch run.)
3. **`batch run <batch-id> --target presentation`** — plans every locked
   mission into one combined DAG with a single shared Pixelcoat pack node that
   all missions' Zoo kits depend on, then runs it in parallel. The output line
   reports the shared-job count and how many jobs were reused from cache.
4. **`batch report <batch-id>`** — writes, under `batches/<id>/reports/`:
   - `batch_summary.md` / `.json` — mission-status matrix, shared asset packs,
     tool-version consistency, handoff-ready and failed/stale buckets, and the
     batch build lock.
   - `<mission>.summary.md` / `.json` per mission — selection, seeds, tool
     versions, validation, functional-lock status, and remaining runtime
     responsibilities.

## Shared work reuse

The shared Pixelcoat packs are an explicit batch-level node built once and
consumed by every mission. Beyond that, the content-addressed cache deduplicates
any incidental cross-mission work with an identical build fingerprint (you'll
see it in the `cache reuse` count).
