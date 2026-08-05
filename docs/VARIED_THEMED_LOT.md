# Varied themed lot: the `--render` split is the prerequisite

**Design note, 2026-08-05.** Not implemented. Written because the obvious
order of work is the wrong one.

## What you get today

```
run <mission>          -> varied greybox lot, N different buildings, no art
run <mission> --art    -> ONE building repeated N times, fully themed and lit
```

`_write_site_spec` activates the varied-library path only when

```python
library = getattr(model, "lot_library", None)
if library and (themed_map or not themed_scene):
```

`themed_map` is `themed_scene if isinstance(themed_scene, dict) else None`,
and `themed_scene` is a single path today, so with `--art` the varied path is
skipped by design. The comment there is right about why:

> Selecting varied greybox buildings and then dressing them all as the same
> themed scene would be a worse lie than the one it replaces.

## Why per-archetype compose looks cheap and isn't

The compose side really is cheap. `PresentationAdapter.plan_commands` returns
a **Sequence**, so one job can run N composes — no planner change, no new
jobs, same graph:

```python
complete, _ = building_library.index(dc_build_dir)      # pure: a listing + arithmetic
lot = building_library.pick_lot(complete, seed, count)  # deterministic on (library, seed, count)

return [PlannedCommand(..., "--greybox", a["glb"], "--slots", a["slots"],
                       "--gameplay", a["gameplay"], "--building-id", a["id"],
                       "--out", out_dir / "lot" / a["id"])
        for a in lot]
```

Everything that needs is already known at spec time: `building_library` is
free of workspace, Lot and Godot, and `model`/`seed`/`count` are all in scope
in `lf_commands`' presentation branch.

**Lux is what makes it expensive.** `lux_apply` declares
`depends_on=[compose_jid]` and lights `presentation/site.tscn` — one scene
from one compose. With N composes there is no single scene to light, so Lux
either runs N times (lighting each building in isolation, before it is placed
on the site — which is not what lighting means) or moves downstream of
`themed_site_assemble`. The Job also declares
`expected_outputs=["presentation/site.tscn"]`, which the scheduler enforces,
so the contract has to move with it.

## The order that works

**Step 1 — split `--render` out (see RENDER_PASS_SPLIT.md).** Lux stops being
a step inside the art pass and becomes a pass over the ASSEMBLED SITE:

```
zoo/pixelcoat/patina -> presentation_compose -> themed_site_assemble -> lux_apply
```

This is worth doing on its own merits — it is why the split was raised — and
it happens to remove the only thing coupling Lux to a single compose output.

**Step 2 — per-archetype compose.** With Lux downstream of the assembled
site, one compose job emitting N scenes is contained:

- `lf_commands` presentation branch: add `lot_archetypes` to the job spec
- `PresentationAdapter.plan_commands`: one command per archetype
- `PresentationAdapter.validate_configuration` / `fingerprint_inputs`: take
  the list rather than a single `slots_path` / `greybox_glb`
- `_write_site_spec`: build `themed_scene` as `{archetype_id: scene}` — the
  varied path already activates on `themed_map`, so nothing below changes
- the Job's `expected_outputs`: per-archetype scenes, not `presentation/site.tscn`

Done in this order, step 2 touches two files and adds no jobs.

## Things to get right

- **Keep the single-shell path byte-for-byte** when `lot_library` is unset.
  Existing missions have been evaluated against the shell they produced;
  re-placing one silently would be a different level wearing the same grade.
  The existing code is explicit about this and the new path should be too.
- **The lot must be picked once.** `pick_lot` is deterministic on
  (library, seed, count), so the compose spec and `_write_site_spec` will
  agree if both call it — but they should not both call it. Pick in the
  compose spec, publish the chosen ids as an output, and have
  `_write_site_spec` read them. Two callers deriving "the same" list is how
  they drift.
- **`--art` needs a selected candidate.** `plan_mission` returns before
  adding any optional layer when `selected_candidate is None`, which is why a
  three-candidate mission plans no art stages. That is correct, and it means
  a varied themed lot is only ever built for a locked candidate.
- **Cache fingerprints.** `fingerprint_inputs` currently hashes one
  `slots_path`/`gameplay_path`/`greybox_glb`. With N archetypes it must hash
  all of them, or swapping one building for another in the lot serves a stale
  compose.
