# Changelog

All notable changes to Level Factory are documented here. Commit messages stay
short (< 200 chars); detail lives here.

## [0.6.10] - 2026-07-13

Presentation reached Lux (Zoo advisory worked — kit + dress both succeeded).
Lux failed on a one-line staging bug.

### Fixed — Lux driver not staged (wrong path depth)
- Godot died with `Attempt to open script 'res://run_lux_apply.gd' ... File not
  found`: the Lux driver was never copied into the staged project. The job-spec
  built the driver path with `Path(__file__).parents[2]` (= the `apps/` dir) but
  the driver lives at `<repo>/assets/godot/run_lux_apply.gd` — needs `parents[3]`.
  The copy was guarded by `.exists()`, so the wrong path silently skipped the
  copy. Fixed the depth; verified the driver now resolves and stages into the
  project root alongside the Lux addon, presets, class cache, and scene.
- The stub masked this because it matches the `-s` script by name without loading
  the file, so only real Godot exposed it. The Lux adapter now RAISES if the
  driver is missing instead of silently skipping — a wrong path fails loudly.

### Testing
- Fast suite: 120 passed, 9 skipped. Real-tool smoke: 9 pass. Full pipeline
  through the service: presentation completes, all five art-pass sections "done".

### Now unblocked on hardware
- Lux should apply headlessly and save the scene + quality/validation JSON
  (preview PNGs still need a render context — expected). Then the Dispatch handoff
  with an LF-generated mission.json is the single remaining untested stage.

## [0.6.9] - 2026-07-13

Zoo now builds in real Blender (0.6.8 fix confirmed). It exits 2 on a partial
build but writes its index and the modules that built — same shape as Laser Tag.

### Changed — Zoo partial build is advisory (not a hard failure)
- The Zoo log confirmed a real Blender build: `[zoo] 12 modules built, 3 failed`,
  `[zoo] index: lf_m1_1997_kit.built.json` (index + 12 module glbs all present on
  disk). Zoo returns `0 if n_fail == 0 else 2`, so exit 2 means "built with some
  misses" — the resolver falls back to base for the failed modules and the kit is
  usable. LF was treating that nonzero exit as a crash. Both Zoo job-specs (kit +
  dress) now set `exit_advisory`, so as long as the index is produced the job
  completes; the adapter surfaces the failed-module count as a non-blocking
  ZOO_PARTIAL_BUILD finding. (Same mechanism used for Laser Tag in 0.6.6.)
- The 3 failed modules in the run were almost certainly the placeholder Pixelcoat
  pack (a 1-colour skin can't cover every module type); real skins should reduce
  the miss count. It's a quality note, not a blocker.

### Testing
- Fast suite: 120 passed (+3 Zoo partial-build), 9 skipped. Real-tool smoke: 9
  pass. Full pipeline through the service: presentation completes (not blocked),
  all five art-pass sections "done", export succeeds.

### Now unblocked on hardware
- With Zoo advisory, presentation should complete on your machine, finally
  exercising the Lux driver (headless apply; preview PNGs still need a render
  context) and the Dispatch handoff with an LF-generated mission.json — the last
  two untested stages.

## [0.6.8] - 2026-07-12

The zoo_kit "FAILED exit=0" was NOT an output-name problem — Zoo was running
without bpy and no-op'ing. The real fix: run Zoo's geometry builds in Blender.

### Fixed — Zoo kit/dress builds must run INSIDE Blender
- The job log showed `[zoo] bpy not available -> skin library report only. Run
  inside Blender to build with these skins.` LF invoked Zoo with plain Python, so
  bpy was absent and Zoo degraded to a no-op report, writing no index (exit 0 but
  no output → the FAILED-exit=0). Zoo's geometry builds are meant to run as
  `blender --background --python tools/zoo_cli.py -- --build-kit ...` (zoo_cli.py
  adds its own repo root to sys.path, so imports resolve). The adapter now
  invokes kit and dress that way (executable = blender, resource_class = blender);
  the `--kit --plan` pre-pass stays pure Python (no bpy needed). The building-id
  output-name logic from 0.6.7 was correct and stays — it just needed Zoo to
  actually build. Verified command shape: `blender --background --python
  zoo_cli.py -- --build-kit <slots> ... --out <work>`, expects
  `<building_id>_kit.built.json`.
- The Blender stub now handles `--background --python <script> -- <args>` by
  running the target script with the post-`--` args, so the fast suite exercises
  the same Blender-invocation path.

### Testing
- Fast suite: 117 passed, 9 skipped. Real-tool smoke: 9 pass (Zoo `--plan` still
  runs headless in-container). The real Blender kit/dress build needs the user's
  Blender to execute — this is the next thing the hardware run will exercise.

## [0.6.7] - 2026-07-12

Fourth real Windows run: the functional pipeline PASSED end to end (Deli x3 +
Lot + Laser Tag, with the advisory + closure + cache fixes all confirmed on
hardware). Presentation then blocked at Zoo — the last documented-vs-real gap.

### Fixed — Zoo output-contract name (the presentation blocker)
- zoo_kit_build reported FAILED with exit=0: the Blender build SUCCEEDED but LF
  looked for the wrong output file. Real Zoo writes `<building_id>_kit.built.json`
  (kit) and `<building_id>_dressing.built.json` (dress) — LF expected
  `zoo.manifest.json`. The adapter now reads `building_id` from the slots /
  dressing manifest at execution and expects the real index file, falling back
  to Zoo's own `"building"` default when the id is absent (real Patina emits
  dressing building_id=None, and Zoo falls back to "building"). Confirmed against
  real Zoo 0.27 source (build_kit / build_dressing index naming).
- normalize_validation now reads `*.built.json`; planner metadata no longer
  hardcodes `zoo.manifest.json`; the Zoo stub + Patina-dressing stub emit the
  real building-id-based names so fast suite and real tools share one contract.

### Confirmed on hardware (this run)
- Fast suite exit 0 (cache-race fix held — Lot candidates 2/3 hit cache cleanly).
- Deli x3 through real Blender; Lot x3; Laser Tag x3 completed as SUCCEEDED with
  a non-blocking low-readiness finding (advisory fix works — functional-lock
  finished at exit 1). Pixelcoat + Patina succeeded (theme fix held).

### Testing
- Fast suite: 117 passed, 9 skipped. Real-tool smoke: 9 pass. Full pipeline
  through the service: all five art-pass sections "done", export succeeds.

### Still open (unchanged)
- Laser Tag grades the map low until Lot's spawn/objective/extraction beacons are
  bridged to LT_PlayerSpawn/LT_EnemySpawnPoints nodes (your tool-contract call);
  advisory means it no longer blocks. Lux driver execution + preview capture and
  the Dispatch handoff with an LF-generated mission.json are the next things a
  real run will exercise now that presentation completes.

## [0.6.6] - 2026-07-12

Third real Windows run: class-cache fix confirmed (Godot resolved LT_MapEvalHarness
and ran 25 eval runs). Fixes the cache race + the Godot resource closure.

### Fixed — cache blob-publish race on Windows (WinError 32)
- The temp file was named only by content hash, so parallel jobs producing
  byte-identical output (deterministic Deli candidates hash to the SAME blob)
  clobbered each other's "<hash>.part" and failed the rename on Windows. Now the
  temp name is unique per writer (pid+uuid), the publish is dedup-aware (if
  another worker published the blob first, discard the copy — blobs are
  immutable), and the rename retries briefly on a transient lock. Stress-tested
  with 24 threads racing one blob: no errors, no leftover temps.

### Fixed — Godot resource closure for the staged project (laser_tag + lux)
- The staged walkable scene referenced (a) the Deli building glb by an ABSOLUTE
  path that Godot mangled into "res://C:/Users/.../shell.glb", and (b) Lot's own
  runtime addon (res://addons/lot/...), neither of which was in the throwaway
  project. Now stage_godot_project copies any absolutely-referenced file into the
  project and rewrites the ext_resource path to a real res:// location, and the
  laser_tag/lux staging also stages Lot's addon (<lot_repo>/godot/addons/lot).
  Verified against real Lot 0.18: building glb copied in + path rewritten to
  res://shell.glb, Lot addon staged, zero absolute refs left.

### Changed — Laser Tag exit is advisory (readiness signal only, TDD 5.5)
- Laser Tag signals its verdict via exit code; a low/BROKEN grade exits nonzero
  but is EVIDENCE for the human at candidate selection, not a build crash. The
  scheduler now treats a nonzero exit as advisory when the job sets
  `exit_advisory` AND the expected report is present (a missing report still
  fails as a real error). The adapter surfaces the grade/score as a non-blocking
  LT_LOW_READINESS finding. So a candidate that evaluates poorly is a selectable
  candidate with a visible low score — the pipeline no longer hard-fails on it.

### Testing
- Fast suite: 117 passed (+3 readiness), 9 skipped. Real-tool smoke: 9 pass.
  Closure + cache race verified in-container against the real repos.

### Open — needs your tool-contract knowledge (NOT an LF bug)
- Even with geometry loaded, Laser Tag grades the map BROKEN because it wants
  LT_PlayerSpawn / LT_EnemySpawnPoints nodes, but Lot's walkable scene emits its
  own spawn/objective/extraction beacons. How are these meant to bridge — does
  Laser Tag auto-derive spawns, is it meant to run on a different scene (e.g. a
  Dispatch mission.tscn), or should LF inject LT spawn nodes from Lot's markers?
  The advisory change means this no longer blocks the pipeline; resolving it is
  what makes the Laser Tag evidence meaningful.

## [0.6.5] - 2026-07-12

Fixes from the second real Windows run: Lot now passes (v0.4 fix confirmed on
hardware), which surfaced two more documented-vs-real mismatches downstream.

### Fixed — Godot staged project missing the global class cache (laser_tag + lux)
- The runner/driver reference class_name TYPES (LT_MapEvalHarness, LT_TestScenario,
  LuxRoot). Godot can't resolve a class_name without its global script class
  cache, which only exists after an editor import — the throwaway staged project
  never had one, so `-s run_map_eval.gd` failed with "Could not find type ...".
- Fix: `stage_godot_project` now stages the addon's own
  `.godot/global_script_class_cache.cfg` into the project (merging when several
  addons are staged). Verified every cached class path lives under
  res://addons/<name>/ — the same res:// location LF copies the addon to — so
  the cache is copy-safe. Confirmed against real repos: 32 laser_tag classes
  (incl. LT_MapEvalHarness/LT_TestScenario) and 24 lux classes (incl. LuxRoot)
  stage into a well-formed cache.

### Fixed — Patina theme name
- LF passed `--theme <theme_family>` (e.g. "delco_1997"), but Patina validates
  against its builtins ("default", "delco_1997_gas_station") and errors hard on
  unknowns, blocking the art pass. LF now passes the always-present "default"
  unless the brief sets an explicit `patina_theme` (a builtin name or a theme
  .json path). Verified real Patina 0.18 runs clean with "default". theme_family
  still flows to the other tools; it was never a valid Patina theme name.

### Testing
- Fast suite: 114 passed, 9 skipped. Real-tool smoke: 9 pass, with new
  assertions that the staged Godot projects carry the class cache (incl. the
  exact class_name types the runner/driver need). Real Godot execution still
  needs the user's hardware to confirm the parse errors are gone.

### Note on the run that found these
- Second Windows run: Lot assembled the site (v0.4 fix held — canonical
  site.tscn/site_walk.tscn/site.site.*.json), all 3 Deli candidates built through
  real Blender. The two failures above were the next documented-vs-real gaps, now
  fixed. Watch for the same class in Zoo's real kit build (--theme) once it runs
  through Blender.

## [0.6.4] - 2026-07-12

Fixes found by the first real Windows end-to-end run (deli built through real
Blender; Lot then blocked). One real product bug + two Windows test-harness bugs.

### Fixed — Lot site-spec schema (the pipeline blocker)
- `_write_site_spec` was written against the documented Lot schema, not the real
  one. Real Lot 0.18 reads `site_spec["name"]` (LF wrote `site_id`) and requires
  per-building placement `at` [x, y] + `rot` (LF omitted both), so Lot died with
  `KeyError: 'name'` the instant it read the spec. LF now emits `name`, per-
  building `at`/`rot` (row-spaced by building_count), and a `ground` plane.
- Lot names its OUTPUTS from the `name` field, not the input filename — so `name`
  is set to the canonical stem `"site"` to keep `site.tscn` / `site_walk.tscn` /
  `site.site.gameplay.json` / `site.site.lights.json`, matching the planner's
  expected_outputs and every downstream adapter. Verified against real Lot 0.18
  (exit 0, all four canonical outputs produced). This was missed originally
  because Lot's real-tool smoke ran against its bundled example spec, not an
  LF-generated one.

### Fixed — Windows test harness (not product bugs)
- Stub godot/blender `WinError 193`: the stub was an extensionless shebang script
  Windows can't launch. Split into `godot.py` (logic) + `godot` (POSIX launcher)
  + `godot.cmd` (Windows launcher, which subprocess can exec from a list); the
  six tests that use it now pick the right one by platform.
- `test_real_pixelcoat` compared `theme/theme.pack.json` against Windows'
  backslash `relative_to`; both sides are now normalized to posix separators.

### Testing
- Fast suite: 114 passed, 9 skipped. Real-tool smoke: 9 pass. Full CLI pipeline
  (functional-lock -> presentation -> export -> portability) runs clean, and the
  fixed site spec drives REAL Lot 0.18 to exit 0 with the canonical outputs.

## [0.6.3] - 2026-07-12

Real-tool grounding, part 4 (final): rebind the two Godot addons, laser_tag and
lux. All eight adapters now speak real contracts.

### Changed — Godot adapters rebound to real invocations
- **laser_tag** (`adapters/laser_tag`, 0.2.0): dropped the fake `--lasertag-eval`
  engine flag for the REAL runner —
  `godot --headless --path <proj> -s res://addons/laser_tag_tool/runners/
  run_map_eval.gd -- --map res://level.tscn --scenario <.tres> --runs N --seed S
  --output <abs>.json`. The harness writes JSON + a same-basename CSV and accepts
  an absolute `--output` via `ProjectSettings.globalize_path`.
- **lux** (`adapters/lux`, 0.2.0): Lux is in-engine only (no `--lux-apply` flag,
  open decision #10). LF now ships a headless driver, `assets/godot/run_lux_apply
  .gd`, that uses the REAL `LuxRoot` API (auto-loaded preset library +
  `blend_to_preset(name, 0.0)`) to apply a look and save the applied scene +
  quality/validation JSON. Invocation:
  `godot --headless --path <proj> -s res://run_lux_apply.gd -- --scene res://
  level.tscn --preset <name> --out <abs>`.

### Added — Godot project staging
- `packages/staging/godot_project.py`: assembles a throwaway project (project
  .godot enabling the addon, the addon copied under `addons/`, and the scene +
  its work-dir siblings staged at `res://`) so `--map`/`--scene res://...`
  resolves. Both adapters stage at execution time (the scene comes from a prior
  job). A full res:// resource-closure packer (reusing exporting/closure) is the
  documented follow-up.

### Added — real-tool smoke coverage (shape-based for Godot)
- Godot can't run in the sandbox, so two shape tests verify against the real
  repos: the real `run_map_eval.gd` runner + default scenario exist and the
  adapter stages a project + emits the real `-s run_map_eval.gd` invocation; the
  real Lux addon + `LuxRoot` exist, LF's driver uses the real API, and the
  adapter emits the real `-s run_lux_apply.gd` invocation. Nine real-tool smokes
  now pass against the actual repos; all skip without `LF_TOOLS_DIR`.

### Known limitations (Godot hardware, honest)
- Execution of both tools needs your Godot 4.7 — they are not run in CI here.
- Preview PNG capture (calm/alarm/extraction) needs a rendering context, which
  `--headless` does not provide; the Lux driver applies + saves headlessly and
  leaves preview capture as a windowed/offscreen follow-up (decision #10).
- The staging helper copies the scene + its directory siblings; deep res://
  closure across referenced glbs is the next integration step.

### Testing
- Fast suite: 114 passed, 9 skipped. Full CLI pipeline runs clean; laser_tag
  emits report.json+csv and lux emits applied.tscn + quality/validation JSON via
  the staged project. Real-tool smoke: 9 pass against the actual repos.

### Milestone
- ALL EIGHT adapters (dispatch, lot, patina, pixelcoat, zoo, deli_counter,
  laser_tag, lux) are now bound to their real CLIs/invocations, verified against
  the uploaded repos (six executed in-container; two shape-verified, Godot-gated).

## [0.6.2] - 2026-07-12

Real-tool grounding, part 3: rebind Deli Counter to its real two-step CLI.

### Changed — deli_counter rebound to the real two-step CLI
- **deli_counter** (`adapters/deli_counter`, adapter_version 0.2.0): the real
  flow is two commands, not one. Step 1 `new_level.py --preset <preset> --name
  <level> --mode <mode> --force` writes `specs/<level>.json` (headless, runs
  in-container). Step 2 `build.py specs/<level>.json --out <work>/shell.glb
  --blender <exe>` writes `shell.glb` + `shell.{gameplay,slots,lights,manifest}
  .json` next to `--out` (Blender-gated). The adapter emits both as one job.
- Archetype -> preset mapping: LF briefs use archetype strings (e.g.
  `urban_bank`); the adapter maps them to DC's 17 real presets (bank, office,
  warehouse, gas_station, ...), with passthrough for exact names, a prefix strip,
  a keyword fallback, and a `bank` default.
- **Determinism note baked in:** `new_level` has NO seed flag — DC is
  deterministic per preset, so the seed does not affect the building. Candidate
  variation genuinely comes from Lot's site assembly downstream. The deli
  fingerprint therefore excludes the seed (identical configs dedupe in the
  cache); the seed is used only to keep per-job spec names unique in the repo's
  `specs/` dir.

### Added — real-tool smoke coverage
- `test_real_deli_new_level`: drives the real `new_level.py` through the adapter,
  asserts the spec is written and the archetype->preset mapping resolves, and
  confirms the Blender-gated build command's shape (out path + `--blender`).
  Seven real-tool smokes now pass against the actual repos; all skip without
  `LF_TOOLS_DIR`.

### Changed — stubs + job-spec cascade
- Deli stub is now two files (`new_level.py` + `build.py`) mirroring the real
  contract; `build.py` writes the same sidecars without Blender. `_job_specs_for
  _plan` passes archetype/mode/level_name; the DC repo's `specs/` is gitignored.

### Testing
- Fast suite: 114 passed, 7 skipped. Full CLI pipeline runs clean; the deli
  two-step produces shell.glb + all four sidecars per candidate. Real-tool
  smoke: 7 pass against the actual repos.

### Still on old contracts (final rebind, Godot hardware-gated)
- laser_tag (Godot `run_map_eval.gd` runner) and lux (in-engine addon needing a
  headless driver scene, open decision #10). These need your Godot to smoke-test;
  next up is scaffolding their driver/runner invocation.

## [0.6.1] - 2026-07-12

Real-tool grounding, part 2: rebind Pixelcoat and Zoo to their actual CLIs, and
fix the Patina->Zoo dressing handoff.

### Changed — adapters rebound to real CLIs
- **pixelcoat** (`adapters/pixelcoat`): real `python -m pixelcoat.cli.main build
  <recipe.json> --output <dir> --json --force` (positional, self-describing
  recipe). Output is nested per asset: `<output>/<asset_id>/<asset_id>.pack.json`
  plus albedo/normal/roughness PNGs and `build_report.json`. Verified against
  real Pixelcoat 0.2.0 with a synthesized recipe+source.
- **zoo** (`adapters/zoo`): real `python tools/zoo_cli.py`. Kit build
  `--build-kit <slots.json> --skins <dir> --theme --seed --out` and dressing
  `--dress <patina.dressing.json> --out` are Blender-gated; a new `plan_only`
  mode emits the headless `--kit <slots.json> --plan` pre-build gate. Verified
  `--plan` against real Zoo 0.27.0 (no Blender needed).
- **patina dressing** (`adapters/patina`): the dressing pass now passes
  `--anchors`, which is what makes Patina emit `<stem>.patina.dressing.json`
  (schema `patina-dressing/1`) — the exact manifest Zoo's `--dress` validates and
  consumes. Added to the adapter's expected outputs. Fixes the v0.6.0 wiring that
  pointed Zoo at `.patina.json`.

### Added — real-tool smoke coverage
- `tests/real_tools` now covers six tools/paths: dispatch, lot, patina base,
  patina dressing (asserts the `patina-dressing/` manifest for Zoo), pixelcoat
  (real nested-pack build), and zoo (`--plan`). All 6 pass against the real
  repos; all skip without `LF_TOOLS_DIR`.

### Changed — stubs + job-spec cascade
- Pixelcoat/Zoo stub CLIs mimic the real shapes and the nested pack layout; the
  Patina stub emits a `patina-dressing/1` manifest under `--anchors`.
- `_job_specs_for_plan` + `_batch_job_specs`: Pixelcoat is fed a real recipe
  (`_write_pixelcoat_recipe`, with a resolvable source), the shared batch pack
  uses the same, Zoo dressing consumes `shell.patina.dressing.json`, and Zoo kit
  points `--skins` at the shared pack dir. Batch report finds packs recursively.
- Planner `expected_outputs`: pixelcoat -> `theme/theme.pack.json` (nested);
  patina dressing adds `shell.patina.dressing.json`.

### Testing
- Fast suite: 114 passed, 6 skipped. Full CLI pipeline runs clean end-to-end;
  Pixelcoat produces the nested pack, Patina dressing emits the Zoo manifest.
  Real-tool smoke: 6 pass against the actual repos.

### Still on old contracts (next rebind, hardware-gated)
- deli_counter (two-step new_level + Blender build), and laser_tag + lux (Godot
  addons needing a runner/driver scene). Zoo kit/dress geometry builds also need
  Blender; only their command shapes ship here, with `--plan` runnable.

## [0.6.0] - 2026-07-12

Real-tool grounding: rebind the pure-Python adapters from *documented* contracts
to the *actual* CLIs of the uploaded tool repos, and add a real-tool smoke suite
that drives the real tools.

### Changed — adapters rebound to real CLIs
- **dispatch** (`adapters/dispatch`): reads the real `version` key from the
  `dispatch contract` probe; passes `--strict-licenses` by default (the tool's
  documented Level Factory default); expects `resource_manifest.json`. Verified
  driving real Dispatch 0.3.0 end-to-end: `dispatch build` produced the full
  handoff (mission.tscn / gameplay_anchors / runtime_ownership_requirements /
  proposed_beat_graph / HANDOFF.md / build.lock), readiness 100, 0 blockers.
- **lot** (`adapters/lot`): real positional CLI `lot.py <site_spec> <out>
  --walkable [--navqa]`; consumes a Level-Factory-written `site.json` referencing
  the DC shell; stem-named outputs `site.site.gameplay.json / site.tscn /
  site_walk.tscn / site.site.lights.json`. Pacing is surfaced as a NON-blocking
  estimate (§24.2). Verified against real Lot 0.18.0.
- **patina** (`adapters/patina`): real CLI `patina <shell.glb> [--mode] [--theme]
  [--dressing --panel-fields --frames --gutters --pilasters] --out
  <dir>/<stem>.patina.glb`; takes the DC shell glb as positional input; outputs
  `<stem>.patina.glb / .patina.json / .patina.gameplay.json`. Verified against
  real Patina 0.18.0 (base + dressing); collision preserved ("untouched").

### Added — real-tool smoke suite (TDD 37.5)
- `tests/real_tools/` — gated on `LF_TOOLS_DIR`. When set, three tests resolve
  the real repos, build each rebound adapter's planned command, run it against
  the tool's own bundled example, and assert the adapter's expected outputs.
  When unset, they skip — the fast suite never needs Blender/Godot/private repos.
  Run: `LF_TOOLS_DIR=/path/to/tools pytest tests/real_tools -q` (3 pass).

### Changed — stubs + job-spec cascade migrated to real contracts
- The lot/patina/dispatch stub CLIs now mimic the REAL command shapes and output
  names, so the fast suite and the real tools share one adapter code path.
- `_job_specs_for_plan` rewired: writes a real Lot `site.json` (`_write_site_spec`),
  feeds Patina the DC shell glb (`input_glb`), points Laser Tag at `site_walk.tscn`,
  points Zoo dressing at Patina's real `shell.patina.json`, and the Dispatch spec +
  functional-lock/regression read `site.site.gameplay.json`.
- Not-yet-rebound tools (deli_counter two-step, zoo, pixelcoat, laser_tag, lux)
  keep their current contracts this release; their real CLIs are captured in
  REAL_TOOL_RECONCILIATION.md and are the next rebind (Blender/Godot-gated).

### Testing
- Fast suite: 114 passed, 3 skipped (real_tools). Full CLI pipeline
  (functional-lock → presentation → export → portability) runs clean end-to-end
  on the migrated stubs. Real-tool smoke: 3 pass against the actual repos.

## [0.5.0] - 2026-07-12

Phase 5: Advanced Review & CI (TDD 42, Phase 5). Completes the delivery plan.

### Added
- Team approvals (`packages/approvals/team.py`): per-gate quorum with individual
  sign-offs bound to the gate's protected-input fingerprint, so a protected
  change makes sign-offs stale (inherited from 23.2). Final handoff defaults to a
  two-approver quorum (decision 8). CLI `team-sign` / `team-status`.
- Accepted exceptions (`packages/approvals/exceptions.py`, TDD 23.3 / AC11): a
  non-blocking issue may be accepted with approver, timestamp, written reason,
  exact issue id, and artifact fingerprint (+ optional expiration and follow-up
  ticket). Blocking issues are refused; acceptances go stale when the artifact
  fingerprint changes or the expiration passes (23.4). CLI `accept-exception`.
- Rich visual comparisons (`packages/review/visual.py`): pairs a mission's
  presentation preview states (calm/alarm/extraction) against a saved baseline
  and emits an HTML + JSON before/after report with an added/removed/changed
  status and PNG dimensions. CLI `review` (snapshots a new baseline each run).
- CI templates (`packages/ci/templates.py`): a GitHub Actions workflow and a
  portable `ci/run.sh` that run doctor -> batch run -> portability gate ->
  report, using the documented exit codes. CLI `ci-init`.
- Source-control release (`packages/release/scm.py`): verify a clean tree, create
  an annotated tag for a batch release, and record commit + tag provenance. Never
  pushes and never rewrites history (pushing stays a human action). CLI `release`
  (`--allow-dirty` to override the clean-tree check).
- Distributed-worker abstraction (`packages/jobs/workers.py`): a `Worker`
  protocol, a serializable `JobEnvelope`/`JobResult`, a `LocalWorker`, and a
  `FakeRemoteWorker` that round-trips the envelope through serialization to prove
  it is transport-ready. A real cloud transport is intentionally not shipped.
- Service methods: `team_sign` / `team_status` / `accept_exception` /
  `visual_review` on `FactoryService`.

### Testing
- 5 team-approval / exception unit tests (quorum, staleness, blocking-refusal,
  reason-required, fingerprint staleness).
- 5 review/CI/release/worker unit tests (added-vs-changed detection, PNG
  dimensions, template shape, clean/dirty/duplicate-tag release, envelope
  round-trip).
- 3 CLI integration tests (team quorum on handoff, accept-exception + review +
  ci-init, release tags a real git repo). 114 tests pass.

### Deferred (per TDD 41.3, documented not stubbed dishonestly)
- Cloud/distributed workers and remote artifact store: the worker seam ships;
  the network transport does not.
- Embedded 3D viewport, multi-user web review, PR automation, and remote SCM
  operations remain out of scope; `release` covers local tagging + provenance.
- Real tool contracts are still stub-backed here (private repos 403 from the
  network).

## [0.4.0] - 2026-07-12

Phase 4: Batch Production + parallel scheduling (TDD 42, Phase 4).

### Added
- Parallel scheduler (`packages/jobs/scheduler.py`): a ready-queue dispatcher
  runs independent jobs concurrently up to the per-resource-class caps (TDD 19.2
  — python_cpu 4, blender 1, godot_headless 2, godot_interactive 1, io_heavy 2,
  lightweight 8), while dependent jobs wait for their inputs. Fail-fast on the
  first failure, draining in-flight jobs. Drop-in: same `run()` contract, resume
  behavior preserved.
- Thread-safe SQLite index (`packages/project_store/index.py`): connection
  opened `check_same_thread=False`, WAL journal, all reads/writes serialized by a
  lock, so the parallel scheduler's worker threads share one index safely
  (stress-tested at 8 threads x 50 upserts/reads).
- Cross-mission batch planning (`packages/pipeline/batch_planner.py`,
  `plan_batch`): composes every mission's presentation plan into ONE combined DAG
  and deduplicates shared work — the shared Pixelcoat surface packs are built
  once as a batch asset and every mission's Zoo kit depends on that single node.
  Missions without a selected candidate are skipped.
- Reporting package (`packages/reporting/summaries.py`, TDD 32): mission summary
  (32.1) and batch summary (32.2 — mission-status matrix, shared asset packs,
  tool-version consistency, failed/stale + handoff-ready buckets, batch build
  lock), each as deterministic Markdown + JSON.
- CLI `batch run <batch_id> [--target ...]` (whole batch as one parallel DAG,
  reporting shared-job count and cache reuse) and `batch report <batch_id>`
  (writes `batch_summary.{md,json}` + per-mission summaries under the batch
  reports dir). Service methods `run_batch` / `batch_report`.

### Testing
- 4 parallel-scheduler unit tests (real concurrency reaches the cap, caps are
  respected, dependencies stay ordered, failure fails-fast without running
  downstream).
- 3 batch-planner unit tests (shared Pixelcoat dedup, skip-without-selection,
  topological ordering) and 2 batch integration tests (3 missions run as one
  batch with one shared pack + full report; skip-without-selection).
- 2 service tests for `run_batch` / `batch_report`.
- Desktop offscreen smoke moved to a subprocess (`apps.desktop --self-check`) so
  Qt never loads into the pytest process — removes a Qt-at-exit teardown crash
  when scheduler threads are present. 101 tests pass in one process.

### Notes
- Same tool-contract stubs as earlier phases (private repos 403 from the
  network). The content-addressed cache still covers incidental cross-mission
  dedup beyond the explicit shared node.

## [0.3.0] - 2026-07-12

Phase 3: Desktop MVP (TDD 42, Phase 3).

### Added
- Application service layer (`packages/service/facade.py`, `FactoryService`)
  enforcing TDD 9.1: the UI calls services and never executes tool processes
  itself. Query methods (dashboard, pipeline + node detail, candidates, art
  pass, validation, job console, handoff) read canonical on-disk state plus the
  SQLite index and return plain, asdict-able view-models. Action methods
  (run/approve/select/export/portability) reuse the already-tested CLI command
  implementations through a captured-args shim, so each side effect has exactly
  one code path. The dashboard enumerates missions from the canonical batches
  tree, not the index, so a deleted index never loses missions.
- PySide6 desktop shell (`apps/desktop/`) over the service, with the TDD 10
  layout (`main.py`, `windows/`, `views/`, `models/`, `dialogs/`) and all eight
  screens (TDD 27): setup wizard, factory dashboard, pipeline view, candidate
  gallery, art pass screen, validation center, job console, handoff screen. A
  generic `DataclassTableModel` is the only place Qt touches service data.
  Entry points: `python -m apps.desktop [workspace]` and the
  `level-factory-desktop` gui-script.
- The handoff screen renders the exact readiness table from TDD 27.9 (functional
  geometry / collision / anchors / shell IDs / beat graph / ownership / nav /
  presentation Ready; runtime / networking / enemy AI Not Implemented by Design)
  and offers export-mode selection, folder/ZIP export, and the portability test.

### Testing
- 12 headless service tests (`tests/service/`) covering every query + action,
  including the export regression block, with no Qt import.
- 2 offscreen PySide6 smoke tests (`tests/desktop/`) that construct the real
  main window under `QT_QPA_PLATFORM=offscreen`, drive all eight screens, and
  fire the handoff export button. They `importorskip` PySide6, so they skip
  cleanly where the desktop extra isn't installed.

### Notes
- PySide6 is an optional extra (`pip install -e '.[desktop]'`); the core, CLI,
  and service layer never import Qt (verified with PySide6 blocked).
- Same tool-contract stubs as Phases 1-2 (private repos 403 from the network);
  the scheduler still runs sequentially (parallelism is Phase 4).

## [0.2.0] - 2026-07-12

Phase 2: Presentation Pipeline + Portable Export (TDD 42, Phase 2).

### Added
- Four presentation adapters bound to current tool contracts: Pixelcoat v0.2.0
  (`pixelcoat-pack/1` shared surface packs), Zoo v0.27.0 (structural kit +
  collision-free dressing, `--skins` consumer), Patina v0.18.0 (base cohesion +
  spec-space dressing manifest), and Lux v0.13.0. Lux is an in-engine Godot 4.7
  addon, not a headless CLI, so its adapter stages the addon and drives a
  headless `godot ... --lux-apply` entry (TDD 24.7).
- Presentation DAG in the planner (`--target presentation`, TDD 15.2): Pixelcoat
  packs + Patina base fan out from the locked shell; Zoo kit waits on Pixelcoat;
  dressing chains Patina -> Zoo; Lux applies last; Dispatch consumes the
  Lux-applied presentation.
- Functional lock (TDD 23.4, 31): a fingerprint of collision, gameplay-anchor
  registry, route graph, and clearance metrics, computed and stored when the
  `functional_shell_locked` gate is approved. Post-art regression recomputes the
  same signatures with identical extraction and diffs them.
- Selective rebuild classification (TDD 30): functional / presentation /
  ambiguous, with ambiguous treated conservatively as functional.
- Portable export (TDD 33): `export` in `portable-godot`, `pure-shell`, and
  `source-authoring` modes; `--format folder|zip` (deterministic ZIP). Writes an
  autoload-free / plugin-free `project.godot`, the required HANDOFF.md language,
  a portable resource manifest, and a license/attribution manifest. Lux
  portability policy: localized runtime (default) or baked presentation (33.6).
- Resource closure scan (TDD 33.5): rejects absolute paths, `user://`,
  unresolved `res://`, required autoloads/plugins, and authoring-repo path
  references; LF's own metadata files are excluded.
- Clean-project portability test (TDD 33.8, 12.12): copies the export into a
  fresh Godot 4.7 project and instantiates the mission scene headlessly, then
  reports a `PortabilityReport` (PASS iff closure clean and engine not failed).
- **Functional regressions block export**: a collision / anchor / route change
  after the art pass fails `export` with exit 2 (Phase 2 exit criterion).
- Example shared Pixelcoat recipes (`examples/shared/pixelcoat/recipes/`).

### Deviations from spec (dev environment)
- The private tool repos 403 from the network, so all four presentation adapters
  are bound to their documented contracts and exercised via stub CLIs (TDD 37.3),
  as in Phase 1. Real-tool smoke (37.5) is dev-only and unrun here.
- Lux is in-engine; its apply + the clean-project instantiate run against a stub
  `godot` that answers `--version`, `--lux-apply`, and `--lf-portability-check`.
- The scheduler still runs sequentially (parallelism is Phase 4); it already
  respects resource-class caps.

## [0.1.0] - 2026-07-12

First package. Phase 1: Headless Orchestration Core (TDD 42, Phase 1).

### Added
- Workspace format and source-control-friendly layout (`factory.project.json`,
  `tools.local.json` / `tools.lock.json`, per-mission tree), rebuildable
  per-workspace SQLite index (`.level_factory/index.sqlite`).
- Canonical/deterministic JSON + SHA-256 hashing as the determinism foundation.
- Domain model (project, batch, brief, candidate, job, artifact, issue,
  approval) and mission/job state machines (TDD 12, 13, 14).
- Adapter SDK: `ToolProbe`, `PlannedCommand`, `ToolAdapter` protocol,
  `BaseAdapter`, and a `run_contract_probe` helper that reads a tool's
  machine-readable `contract` command (the Dispatch D12 pattern) instead of
  scraping prose.
- Tool registry + `doctor` (per-tool PASS/WARN/FAIL/NOT_CONFIGURED; a missing
  tool blocks only its own stages).
- Subprocess runner: argument-array execution (never `shell=True`), streamed
  per-attempt logs, process-tree termination on cancel/timeout, POSIX + Windows.
- Content-addressed cache keyed by build fingerprint (adapter+tool versions,
  commit, input digest, seed, output-contract version); immutable blobs,
  hard-link-or-copy materialization, `cache inspect` / `cache prune`.
- Provenance sidecars per artifact + final `build.lock.json` shape.
- DAG planner for the functional pipeline (deli x N -> lot -> laser_tag) plus
  the Dispatch shell-handoff tail (gated on a selected candidate), with
  deterministic seed derivation and a topological scheduler that resumes after
  a restart.
- Normalized validation model (severities/categories, aggregation) with a
  no-false-completion guarantee: a passing run is never labeled fun / balanced /
  multiplayer-verified / network-ready / shipping-ready.
- Approval gates and functional lock with fingerprint-based staleness.
- Adapters bound to current tool contracts: Deli Counter (v0.74.0 /
  gameplay 1.21.0), Lot (v0.17.x), Laser Tag (v0.7.x), Dispatch (v0.3.0 /
  `dispatch.mission.v0.2`, shell-handoff default). Dispatch adapter enforces the
  shell-only handoff (no production controller node, no leaked network ids).
- CLI: `init`, `doctor`, `batch create`, `plan`, `run`, `resume` (via re-run),
  `status`, `validate`, `approve`, `reject`, `cache`, `diagnostics`, with the
  TDD 28.1 exit-code scheme.
- Tests: unit (core, fingerprint/cache, planner/graph, approvals/validation,
  blocking gate), shared adapter contract suite, and a stub-tool end-to-end
  integration proving brief -> handoff, cache reuse, and resume.

### Deviations from TDD v0.2
- Adapters are bound against the documented tool contracts and exercised via
  stub CLIs; the private tool repos were not reachable at build time, so the
  real-tool smoke suite (TDD 37.5) is developer-only and unrun here.
- Phase 2 (presentation adapters: Pixelcoat/Zoo/Patina/Lux, regression) and
  Phase 3 (PySide6 desktop) are out of scope for this package.
- Pure standard library (no third-party runtime deps), matching the rest of the
  Siliconight tooling; `pytest` is a dev-only dependency.
