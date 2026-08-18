# Walkable site: the deliverable Level Factory advertises and has never produced

**2026-08-06.** Diagnosis complete, implementation not started. Deliberately
not begun at the end of a long session -- the two retractions that session
produced both came from building before the mechanism was settled.

## The defect

`themed_site_assemble` emits `site.tscn` referencing its buildings like this:

```
[ext_resource type="PackedScene" path="res://C:/Projects/.../lot/final_stand/site.tscn" id="b1"]
```

`res://` is rooted at the Godot project directory, so `res://C:/...` looks for
a folder literally named `C:` inside the project. **These references cannot
resolve anywhere.** Not in a preview project, not in a consumer's project,
not at all.

This is not new and it is not specific to the varied lot. The single-shell
path emits the same shape. It has never been noticed because **nothing ever
loaded that scene**: `lf walk` wraps `presentation_compose` (ONE building),
never `themed_site_assemble`. An output that nobody reads cannot be seen to
be broken -- the same shape as the sightline suite that was not wired to
`check.py`, the circulation arm handed the stripped glb, and the two-week
stale `build/`.

`_runs/walk_category5_baie_dore_001` is a working walkable site project, with
the building copied to the project root as `building.tscn` and the reference
rewritten to `res://building.tscn`. Someone did by hand what the pipeline
should do.

## Evidence

```
jobs/lot_demo_001.themed_site_assemble/out/
  site.tscn            23628   five ext_resources, all res://C:/... (unusable)
  site_walk.tscn        5144   res://site.tscn + lot_player.gd + NavigationMesh
                               (cell 0.1, cell_h 0.15, radius 0.4, climb 0.15)
  site.site.gameplay.json 226220
  site.site.lights.json    32497
  (no project.godot)
```

Each composed building IS a self-contained Godot project:

```
presentation/lot/depot_a01/
  project.godot  site.tscn  site_main.tscn  site_base.glb  art/  (art/zoo/)
  compose.summary.json  portable_resource_manifest.json  HANDOFF.md
```

`site_main.tscn` is the portable entry: it instances `res://site.tscn`. Every
internal reference is `res://<something>` rooted at THAT package.

## The fix: stage the packages into the lot job, then reference relatively

Two options were considered.

**Chosen: `themed_site_assemble` stages the building packages into its own
job dir before assembling, and references them relatively.** This fixes the
ARTIFACT. The site output becomes a coherent package that means something to
anyone who receives it, not just to a preview builder that knows how to
repair it. `lf walk` wrapping a site then costs almost nothing.

**Rejected: teach `build_walk_preview` to copy in N packages and rewrite as
it goes.** It fixes the VIEWER and leaves the artifact broken, so the next
consumer hits the same wall. Its docstring already states the governing rule
-- *"Godot `res://` is rooted at the project dir and can't reach a sibling
folder, so the preview copies the content in"* -- which is exactly why the
copying belongs where the scene is written, not where it is read.

## Where the code is

- `level_factory/apps/cli/commands/__init__.py`
  - `_write_site_spec(...)` -- builds the Lot site spec; `themed_scene` is
    either a path string or, since 1ad02ae, `{archetype_id: scene_path}`.
    **This is where absolute paths enter.**
  - the `elif job.adapter_id == "lot":` branch -- computes `themed_scene`
    for `themed_site_assemble` via `_lot_for_compose(model, job.candidate_id)`.
  - `cmd_walk` -- currently hardcodes
    `jobs/<mission>.presentation_compose/out/presentation` as content_dir.
- `level_factory/packages/preview/walk_preview.py` -- `build_walk_preview`;
  copy-in + player + `project.godot` + `walk.tscn`.
- `level_factory/adapters/lot/` -- the Lot adapter.
- `lot/godot/addons/lot/` -- `lot_player.gd`, `lot_site_walk.gd` (canonical).
- `_runs/walk_category5_baie_dore_001/` -- a WORKING example to match:
  flat project, `project.godot` with `run/main_scene="res://site_walk.tscn"`,
  `gl_compatibility`, lux plugin enabled, plus `walk_fixtures.gd`.

## Acceptance test

Not "it opens". These, in order:

1. `lf run lot_demo_001 --art` (candidate already approved: seed_5118)
2. `themed_site_assemble/out/site.tscn` contains **no** `res://C:/` or other
   absolute path. Every `ext_resource` resolves relative to that out dir.
3. That directory opens in Godot as a project and `site_walk.tscn` runs.
4. **Five architecturally different buildings are visible and enterable**,
   themed, not five copies of one.
5. The headless import pass ran: module GLBs are present, not invisible
   walls over live collision.

## Traps, each already paid for once

- **The import pass is not optional.** `cmd_walk`'s own comment: a fresh
  project has no `.godot` import artifacts, and launching straight into play
  loads none of the new module GLBs -- invisible walls over live collision,
  dead ladders. Run `--headless --path <dest> --import` before handing over.
- **Per-package `res://` rewriting.** Five self-contained projects merged
  into one collide: every package has its own `site_base.glb`, `site.tscn`,
  `art/`. Either subfolder them (`lot/<id>/`, rewriting each package's
  internal `res://X` to `res://lot/<id>/X`) or flatten with unique names.
  Subfolders are cleaner; nothing collides.
- **Lighting does not come along.** `walk_fixtures.gd` exists because the
  walk project is assembled from `themed_site_assemble`'s scene and does not
  inherit `lux.applied.tscn`. Measured once: `lux.quality.json` reported 152
  fixture lights while the preview ran `OmniLight3D 0`. Its own comment:
  *"A preview that is lit differently from the level is worse than no
  preview, because it gets believed."*
- **Also in that script:** `LuxFixtureSpawner` reported 152 successes with
  `containers=0` because `_ready` ran while the parent was still setting up
  children and `add_child` was refused. It awaits a frame. Do not remove it.
- **A varied lot is currently UNLIT** regardless: `lux_apply` lights
  `presentation/site.tscn`, the mission shell, which a varied lot does not
  place. See `RENDER_PASS_SPLIT.md` and `VARIED_THEMED_LOT.md`.
  **SUPERSEDED 2026-08-17, and left standing rather than deleted.** That was
  true before `themed_site_assemble` existed. `commands/__init__.py:637-653`
  now picks the assembled SITE whenever that job is planned, and only falls
  back to the composer's root when it is not:

  ```python
  themed_job = _dep(job, "themed_site_assemble")
  if themed_job:
      composed_scene = _latest_output(jobs_dir / themed_job, "site.tscn")
  elif compose_job:
      composed_scene = _latest_output(jobs_dir / compose_job,
                                      "presentation/site.tscn")
  ```

  The branch carries the comment naming this exact defect as already fixed:
  *"Lighting the composed building instead put one LuxRoot over one building
  and called it a level (roadmap 29/34)."* The adapter hardcodes nothing --
  `adapters/lux/__init__.py:53` reads `job_spec["composed_scene"]` -- so the
  scene targeting was never Lux's to get wrong.

  WHAT IS STILL UNMEASURED, and it is now one step rather than a question:
  the assembly INSTANCES the composed buildings, and whether a LuxRoot over
  the assembly survives to a frame inside them is a render-time question.
  Measured 2026-08-17 on `lot_demo_001`, five buildings, exported both modes:
  `presentation/lux.applied.tscn` ships at 141,265 B and
  `presentation/lux.quality.json` reads `{"applied": true, "fixture_lights":
  136, "fixture_msg": "Spawned 136 fixture light(s) from 136 marker(s)",
  "preset": "Blue Hour"}`. So `lux_apply` reaches the assembly's markers on a
  varied lot -- which is what the bullet above denied. What it does NOT
  establish is rendering: Lux's own note is *"previews need a render
  context"*, and a spawn count is not a render count. That is precisely the
  pair four bullets up -- 152 reported against `OmniLight3D 0` running.
  Answering it needs the package opened in a clean Godot project with a
  render context; no export answers it.
- **Do not let a missing archetype scene fall back silently.** The varied lot
  already did this once: five composes wrote correct scenes, an `.is_file()`
  probe ran before they existed, and the site placed the mission shell five
  times with every stage reporting success. If a brief asks for a varied lot
  and a scene is missing at assemble time, fail.

## Related open work

- `--render` split (`RENDER_PASS_SPLIT.md`) -- lights the varied lot.
- Silent-fallback fix above -- small, and should land with this.
- `cr_deli`'s stair -- unrelated; needs its navmesh opened in Godot.
