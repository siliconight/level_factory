## [0.48.0] - the lock learns what a state machine is

Roadmap item 46, steps 2 and 3 (the level_factory half). The pipe Lot 0.48.0
and Dispatch 0.4.0 connected runs through this repo twice: staging shapes the
inputs, and the functional lock decides what must not change.

### Added
- `staging/dispatch_inputs.py` passes `interactives` through VERBATIM into
  both Dispatch input trees (lot side: the site-level concatenation; deli
  side: the building's own declaration, which wins only when Lot is absent).
  No anchor mapping, no id rewriting -- the ids are the network handle.
- `approvals/lock.py`: third protected signature, `interactive_registry_hash`
  over the `interactives` declaration whole (states, default, transitions,
  state_geometry, collision_per_state, transform). Keyed on `id` -- the
  OPPOSITE call from anchors, deliberately: interactive ids are globally
  unique by construction. `interactives` joins BACKFILLED_FROM_DELI so a
  pre-carry site file falls back to the building's declaration instead of
  hashing an empty list that reads as coverage.

### Changed
- Lock schema `v0.2 -> v0.3`. Same rule as the last bump: a v0.2 lock
  reports as needing recompute, never as drift, and does not block export.
- docs/FUNCTIONAL_LOCK.md (factory root) answers the question item 46 parked
  there -- "two collision states, one hash": the locked shell is the DEFAULT
  state (the level at rest, the only state offline artifacts realize and
  gates measure); the per-state truth is protected as DATA by the new
  signature. Worst-case and per-state-set hashing rejected for the same
  reason the 25 unplaced collision nodes stay out of `surfaces`: the lock
  must not protect what the package does not contain.
- `tests/unit/test_lock_regression.py`: semantics-drift-without-geometry,
  dropped-fixture drift, deli backfill, v0.2 recompute-not-drift.

## [0.47.0] - flipping collision on a .glb is a rename

### Added
- **`packages/exporting/glb_collision_flag.py`** -- set or clear the collision
  a `.glb` generates in Godot, one policy per file.

  Godot's glTF importer has no collision field to toggle: it reads the NODE
  NAME and generates a physics body when that name ends in one of the `-col`
  family. So this is a rename inside the JSON chunk. No vertex is touched, no
  accessor moves, and trailing chunks are copied through byte for byte --
  checked on the real Zoo dressing exports, where `pebble_9bac1d.glb` and
  `weed_tuft_4cc3aa.glb` round-trip `colonly` -> `none` with their node names
  restored and their BIN chunks byte-identical.

  `--collision none|col|colonly|convcol|convcolonly|rigid|vehicle|wheel`. That
  list is DERIVED from `validation.glb_collision.COLLISION_SUFFIXES` rather
  than typed out again, so a suffix added there appears here.

  **It refuses to clear collision on a file whose sibling `.import` sets
  `generate/physics=true`.** That setting bodies every mesh whatever the nodes
  are called, so clearing the names would produce a file that reads as
  collisionless and imports with collision on everything -- the same shape of
  wrong as measuring a MultiMesh buffer through the dummy renderer. Adding
  collision under that setting is still allowed; only the false-negative
  direction is dangerous.

  Every write is re-read through `collision_solids`, which walks the container
  and the node tree independently. A writer that grades its own homework is
  what 0.46.0 was about.

### Changed
- **`validation.glb_collision.strip_duplicate` is now public.** Blender appends
  `.001` AFTER the marker Godot matches, so a writer has to insert the suffix
  BEFORE that tail -- `floor-colonly.001`, never `floor.001-colonly`, which
  Godot would not match. Reader and writer have to agree where the tail is, and
  one of them owning the regex is how they agree. `name_generates_collision` is
  rewritten on top of it; equivalence was checked over 525 generated names, and
  that module's own 21 tests are untouched and still pass.

### Tests
- `tests/unit/test_glb_collision_flag.py` -- 28 tests. Every test that claims a
  file collides asks the READER, never the writer.
- **Mutation-tested, and the run earned its keep.** Eleven mutants: suffix
  written after the `.001` tail, zero-padded JSON chunk, stale container
  length, dropped BIN chunk, removed `generate/physics` refusal, suffix on
  meshless nodes, read-back pointed at the input instead of the output, mutated
  input document, and three uncounted report fields. Ten die.
- The eleventh survives and that is the correct answer: stripping the shortest
  suffix first changes nothing, because the leading hyphen makes every marker
  distinct -- `floor-convcolonly` does not end with `-colonly`.
  `test_no_suffix_is_a_suffix_of_another` pins the invariant that makes the
  sort inert, so if Godot ever adds a marker that IS a tail of another, the
  sort stops being decoration and that test says so.
- **Two tests were found passing for the wrong reason by that run.** One
  asserted `-convcolonly` ends with `-colonly`, which is false, and passed
  whatever the sort did. The other checked JSON chunk padding with a single
  fixture that happened to need no padding -- true three times in four. Both
  are rewritten, and both say in their docstrings what they used to get wrong.

### Notes
- **Whole-file policy, not per-node.** An asset has one answer to "does this
  collide" everywhere this pipeline asks: dressing is collisionless by
  definition and `dressing_scene.check_manifest` enforces it, while a shell
  exists to be stood on. Naming individual nodes would allow a file to be half
  of each, a state no consumer here can represent.
- `--in-place` has to be asked for. Given neither `--out` nor `--in-place` it
  refuses rather than guessing which was meant.
- Only nodes carrying a mesh GAIN a suffix -- a marker on an empty generates
  nothing in Godot and leaves a name that lies about the file. Clearing reaches
  every node, because `none` means none.

## [0.46.0] - the MultiMesh buffer was transposed

`tools/dressing_ab.ps1` loaded both dressing scenes in a real Godot window and
compared transform against transform on the coldrun_pawn_job plan. **4372 of
4374 instances disagreed.** The 2 that agreed were at zero yaw.

### Fixed
- **`multimesh_floats()` packed the basis transposed.** It read
  `godot_transform`'s three tuples as basis COLUMNS and interleaved them into
  rows. They are ROWS -- `lot.py:_godot_transform` says so in its own comment,
  and Godot reads the `.tscn` `Transform3D(...)` literal and the MultiMesh
  buffer with the SAME row-major ordering. The two forms differ only in where
  the origin sits: appended at the end in the literal, every fourth float in
  the buffer.

  For a pure yaw a transpose is the inverse rotation, so nothing crashed and
  nothing looked broken -- every dressed object simply faced the mirrored way,
  in a scatter layer where no one direction is expected. Instance 0 read back
  from the engine as `X: (1.31838, 0, 0.007699)` where the node scene had
  `X: (1.31838, 0, -0.007699)`: the transpose exactly, origins identical.

  **Any `_dressing.tscn` written by 0.45.0 is wrong and must be regenerated.**
  `mode="nodes"` was correct throughout -- it emits Lot's ordering, which has
  shipped on hardware.

### Changed
- **`bx, by, bz` -> `r0, r1, r2` throughout the module.** The name was the
  defect. A reader who takes a row for a basis vector transposes the matrix,
  and for a pure yaw a transpose IS the negation the docstrings kept warning
  about -- so the rule and the mistake are spelled the same way and cancel out
  in your head. The docstrings now carry the checkable form instead, which is a
  column: site +X under yaw r lands on Godot (cos r, 0, -sin r), and basis
  column 0 is (row0[0], row1[0], row2[0]). Callers pass positionally, so
  nothing outside the module moves.

### Tests
- `test_site_plus_x_lands_where_the_axis_map_says` (yaw 0.7),
  `test_the_buffer_is_not_the_transpose_of_itself` (yaw 0.6, on the two
  off-diagonals, which swap under a transpose), and
  `test_the_buffer_and_the_literal_describe_the_same_transform` (yaw 0.9,
  position by position).
- `test_both_modes_place_things_in_the_same_spot` now asserts the twelve floats
  as one ORDERED substring. Asserting each value appears somewhere in the text
  is order-blind, and order was the whole defect.

### Notes
- **Why the old tests were all green against the bug.** Three of the four
  buffer tests used a yaw of zero, where the identity basis is symmetric and a
  transpose changes nothing. The fourth used a real yaw and compared
  `sorted(floats)` to `sorted(from_literal)` -- its docstring believed the two
  orderings genuinely differed, so only the multiset of values could be
  compared. A transpose is a permutation; no multiset comparison can detect
  one. The original 23-test file passes, all green, against the transposed
  module AND the fixed one. It was not a weak suite. It was a suite that could
  not express the property under test.
- **The first A/B run was invalid and said the same thing.** It ran
  `--headless`, where MultiMesh transforms read back as exact identity because
  `RendererDummy` stores none -- so it also reported every instance
  disagreeing, for a reason that had nothing to do with the layout. The
  harness now runs windowed and carries an `AB INVALID` branch (exit 3) that
  separates "the experiment did not run" from "the thing under test failed".
  A verdict and a broken instrument are not the same finding.
- **What this does not settle.** How a `.glb` becomes an addressable Mesh is
  still supplied by the caller; this module still refuses to invent a path.
  One run, one plan, one machine (Godot 4.7.stable, Vulkan, RTX 2060).

## [0.45.0] - the dressing manifest becomes a scene

The last stage of the Layer 3 chain. Lot said where dressing may go, Patina
decided what goes where, and this turns that decision into something the
engine loads.

### Added
- **`packages/exporting/dressing_scene.py`** -- a `surface-dressing/1`
  manifest as a Godot scene of `MultiMeshInstance3D` nodes, one per asset.

  Run on the real coldrun_pawn_job plan: **3,948 instances of 4 meshes -> 4
  draw calls**, a 326 KB scene. The same manifest as one node per placement is
  3,948 draw calls and 888 KB, which is the load hitch this layer was told not
  to cause.

  It writes `<site>_dressing.tscn` as a SEPARATE scene the site instances. The
  site scene is the functional shell and the shell is locked; a dressing pass
  that edits it has broken the one promise the layer makes, whatever the
  geometry does.

  Both gates are re-checked here, at the last stage, deliberately -- a
  manifest is data and data travels, so the gate that matters is the one
  standing where the geometry is about to become real. A collider in the
  manifest, a Y-up manifest, or a placement over `unassisted_step_max` in
  traversed space all refuse to write rather than writing something wrong.

- **`tests/test_dressing_scene.py`** -- 23 tests.

### Notes
- **The coordinate conversion is transcribed from `lot.py:_godot_transform`,
  not re-derived.** Site XY -> Godot XZ, site Z -> Godot Y, origin
  (x, y, z) -> (x, z, -y), and yaw about site Z becomes yaw about Godot Y
  NEGATED -- the handedness flip that comes with the axis swap. That negation
  is the whole game and it is not obvious; re-deriving it would have given
  this repo two answers to a question it already answered once. The tests pin
  it at yaw 0 and yaw 90, where the answer is known by inspection.
- **Two things this module cannot verify without Godot, and says so.** The
  MultiMesh buffer layout is isolated in one function with one test, so if the
  engine disagrees that function changes and nothing else does; and
  `mode="nodes"` emits the same transforms as ordinary `MeshInstance3D` nodes
  using the `Transform3D` string Lot already ships on hardware, as an A/B
  reference for the editor. How a mesh resource is addressed (`.tres`, `.res`,
  or a `glb::SubResource` path) depends on import settings, so the caller
  supplies the path per asset and an asset without one is an ERROR -- a
  dressing layer missing a species is not a smaller layer.
- Negative zero is normalised out of the emitted text. `-sin(0)` is -0.0 and
  `%g` renders it `-0`; Godot reads it fine, but a sign on a zero is not
  information and it makes two scenes that place things identically differ as
  text, which is how a rebuild is checked.

## [0.44.0] - the Layer 3 chain becomes three jobs

`docs/SURFACE_DRESSING.md` section 2 has three tools in sequence, and none of
them were pipeline steps. Now each is a job that produces what the next
consumes:

    zoo    --measure_shapes        -> <name>.metrics.json
    lot    (site_surfaces CLI)     -> surfaces.json
    patina --mode surface_dressing -> <site>.surface_dressing.json

### Changed
- **`ZooAdapter` 0.3.0 -> 0.4.0**, capability `measure_shapes`. A build job
  can now measure the GLBs it just built, with `tools/shape_metrics.py`, as a
  second plain-Python command. Measuring your own output belongs with the
  build: it lands in the same artifact set and is fingerprinted for free.

  `shape_metrics.py` is a FACTORY-level tool and reaching it is a path walk up
  from the adapter's own location, which is a silent failure waiting to
  happen. `validate_configuration` checks the tool is actually there, so a
  layout change is a configuration error someone reads rather than a
  measurement that quietly stopped happening. The tool's own SOURCE is in the
  fingerprint too -- a change to how a footprint is computed changes the
  catalogue the dressing planner is built from with every other input
  byte-identical, which is the executes-a-sub-tool problem
  `test_presentation_fingerprint` documents, one stage over.

- **`PatinaAdapter` 0.3.0 -> 0.4.0**, capability `surface_dressing`. A new
  mode plans `-m patina.surface_dressing` instead of `-m patina.cli`. It takes
  no `input_glb` -- Layer 3 dresses an assembled SITE, not a shell -- and
  requires `source`, the scene the plan was made against, because a plan
  applied to a different assembly is a different plan. `--audit` is always
  passed, so an illegal plan fails the JOB rather than travelling downstream
  to be discovered by a level that does not walk right.

  Both version bumps are load-bearing for the same reason 0.3.0's note gives:
  the commands an adapter plans are not otherwise in the fingerprint, so
  without them every existing entry cache-hits and the new artifacts are never
  produced.

- **`tools/shape_metrics.py` 0.3.0 -> 0.3.1** gains `--out`. A
  `PlannedCommand` is argv without a shell, so `> file` is not available to
  it: a tool that only writes to stdout cannot be a pipeline step.

### Added
- **`tests/test_dressing_jobs.py`** -- 18 tests, on the wiring rather than the
  planning. What goes wrong at this layer is different in kind from what goes
  wrong in a planner: a command that is never planned, an input that is not in
  the fingerprint, a version that was not bumped when the commands changed.
  Each is silent, and each produces a cache hit that ships the wrong thing.

### Notes on versioning
This entry is 0.44.0; VERSION reads 0.43.3 until the release patch bumps it,
which `verify-manifest` reports as UNRELEASED and is the ordinary state
between writing an entry and making the claim.

`lot`, `zoo` and `patina` will report DRIFT against their manifest pins after
this batch (0.46.0 vs 0.44.0, 0.38.0 vs 0.36.0, 0.21.0 vs 0.19.0). Moving
those pins is re-certification, which asserts the real-tool smoke passed, and
is deliberately not done here.

CORRECTION. An earlier draft of this entry claimed VERSION had regressed to
0.22.0 and that pyproject.toml hard-coded a matching stale number. Both were
false. They were read from files served stale by the file bridge, and
`verify-manifest` -- run against the real tree -- reported the truth: VERSION
is 0.43.3, and pyproject has carried `dynamic = ["version"]` with
`version = {file = "VERSION"}` for some time, so it cannot disagree with
VERSION by construction. The instrument was right and the report about it was
wrong; the paragraph is replaced rather than deleted so the correction is on
the record next to the claim.

## [0.43.3] - the per-object cap is needed after all, and 40 is why

0.43.2 removed `limits/opengl/max_lights_per_object` on the grounds that it
"was never the binding constraint". True of the symptom that had been tested --
blinking -- and false of the one that had not. Standing still in an interior,
adjacent floor slabs each select their own lights and meet at a HARD BRIGHTNESS
STEP. Same limit, no camera motion, and it would have shipped.

Measured in the walk preview, one room, three runs:

    per-object  8 (engine default)   a hard cut across the floor
    per-object 64                    seam gone, no blinking
    per-object 40                    seam gone, no blinking

40 rather than 64 because that value sizes the shader light loop for EVERY
object, so the smallest sufficient number is the correct one -- and 40 is the
smallest the data supports. The worst mesh measured across lot_demo_001's five
buildings sees 36 lights (`pvp_station_ref`'s roof).

BOTH CAPS ARE NOW DERIVED FROM THE PACKAGE

    max_renderable_lights  = light count
    max_lights_per_object  = min(light count, 40)

The second bound matters: a 20-light package cannot put more than 20 lights on
one mesh, so it gets 20 rather than paying for the ceiling. Below the engine
defaults -- 32 and 8 -- neither line is written and an unlit package carries no
rendering override at all.

THE SEAM IS EVIDENCE FOR ROADMAP 54, NOT AGAINST IT

It exists because one floor mesh spans a whole room. Room-sized meshes would
each sit inside the engine default and need no cap. This release ships a
mitigation with a stated cost; the geometry is still the fix.

THE PROCESS NOTE. Three releases in a row set this cap on an unisolated
mechanism -- 0.43.0 wrote it for blinking (wrong), 0.43.2 removed it having
tested only blinking (wrong the other way), 0.43.3 tested both symptoms
separately. The tests now pin each property rather than leaving it to a
comment, because a comment is what was wrong twice.

## [0.43.2] - one derived light cap, and the expensive one removed

0.43.0 wrote `limits/opengl/max_lights_per_object=64` and named it as the
mechanism. It was not. Measured on hardware, in this order:

    per-object 64, global 32 (default)   still blinks, areas stay dark
    per-object  8 (default), global 256  clean, and first-load stutter SMALLER

GL Compatibility carries two separate light limits, and the binding one is
`rendering/limits/opengl/max_renderable_lights` -- a GLOBAL budget, engine
default 32, against a package shipping 136 lights. Most of them were never
drawn at all, which is why whole areas stayed dark permanently rather than
flickering. Asked directly, the engine confirmed both names and both values:

    max_renderable_lights   exists=true  value=32
    max_lights_per_object   exists=true  value=64

So 0.43.0's line took effect and did nothing useful. Corrected in place rather
than quietly rewritten.

REMOVING THE PER-OBJECT CAP IS A PERFORMANCE CHANGE. In GL Compatibility that
value sizes the light loop in the shader for EVERY object, multiplying variants
and per-fragment work. Dropping it measurably improved first-load stutter,
reported from the walk. This layer has to stay cheap while the game grows into
it, and it was carrying a cost for a mechanism that had never been isolated.

THE REMAINING CAP IS DERIVED

`count_package_lights` globs the scenes the exporter just wrote -- the same
"glob it, do not reason about it" approach `closure.py` takes -- and the cap is
set to that count. A package cannot render more lights than it contains, so its
own total is a true upper bound: sufficient by construction, with no headroom
to pay for. At or below the engine default of 32, no cap line is written at
all and an unlit export pays nothing.

ONE RULE, TWO IMPORTERS

`packages/core/godot_project.py` holds `rendering_block`, and `export.py` and
`walk_preview.py` both call it. Two hand-kept copies is exactly how the
preview's own comment says lighting gets signed off missing a rig, and 0.43.0
had left them as two copies that a test compared. Now there is one, and the
test checks the properties instead of the coincidence.

## [0.43.1] - the suite was red, and a version pin is why

`test_both_adapters_use_the_one_rule` carried, under the comment "and the bump
that makes the fix take effect":

    assert LuxAdapter.adapter_version == "0.4.0"

0.42.0 moved `LuxAdapter.adapter_version` to 0.5.0 for exactly the reason that
assertion exists -- it folded the staged Godot driver into the fingerprint, so
entries cached before the driver was visible had to retire. The assertion read
the invalidation as a regression:

    AssertionError: assert '0.5.0' == '0.4.0'

A check written to protect a cache invalidation fired ON a cache invalidation.

The intent was right; the expression was equality on a value that only goes up,
which is true only until the next legitimate bump. Both assertions now compare
version TUPLES with `>=`. A revert to 0.3.x -- the case the test was written
for -- still fails. A bump does not.

Only two such pins existed; both were in this file. `test_tool_revision_dirty`
pins `tool_version == "0.88.0"` but that is a repository revision compared
clean-against-dirty, which is the subject of the test rather than a version
floor, and it is left alone.

TWO PROCESS FAILURES, RECORDED BECAUSE NO CODE FIXES THEM

0.42.0's `--selftest` runs the full suite and would have caught this. Its
output was never read; the release was called green from the commit line alone
-- the same shape as reading a git tag and concluding a commit had happened,
which had already been corrected once the same day.

0.43.0 was then committed with the suite red, because the commit ran in the
same pasted block as the selftest that failed. A selftest whose result nobody
waits for is a check that cannot fail, which is the defect class this release
series has spent itself on.

## [0.43.0] - a per-object light cap, and a test that the two writers agree

A package with 136 fixture lights blinks when you walk it. The compatibility
renderer selects at most N lights per MESH and re-selects as geometry moves
through range; a mesh over the cap drops lights.

Measured on lot_demo_001, 2026-08-18, counting lights whose range reaches each
mesh's bounding box:

    building              meshes   >8   >16  >32  worst  worst mesh
    mansion_a02              163   26    11    0     26  roof_footprint
    pvp_station_ref          240   49    15    1     36  roof_footprint
    large_warehouse_a01      117    3     1    0     17  roof_footprint
    arena_a03                227   10     3    0     26  roof_footprint
    strip_club_a03           173   23     9    0     25  roof_footprint
    across all five          920  111    39    1

Every offender is a building-wide roof or floor/ceiling plate 34-52 m across,
competing for the same slots as a 2 m wall segment. When one loses, a whole
room goes dark at once -- which is what a human reported before any of this was
measured: "lights still blink a bit, or just turn off in certain rooms".

Confirmed in the walk preview, in this order: heavy blinking at the engine
default of 8; mostly gone at 32, with certain rooms still dropping -- which is
the single mesh at 36; none at all under forward_plus. The response tracks the
NUMBER, not just the renderer, and that is what pins the mechanism. A renderer
difference alone would not have improved at 32.

`max_lights_per_object=64` clears the measured worst case with headroom and
keeps `gl_compatibility`, which is the property the portable profile exists
for. IT IS A MITIGATION AND THE CHANGELOG SHOULD SAY SO: the fix is that one
mesh should not span a building, and that is roadmap 54.

THE SECOND HALF, WHICH IS THE MORE IMPORTANT ONE

`walk_preview._PROJECT` already carried this, in a comment:

    ; Verbatim from export.py::_write_project_godot, and it must stay verbatim
    ; Two projects disagreeing about what a complete project.godot contains is
    ; how a human signs off lighting that was missing a rig.

An invariant asserted in prose with nothing enforcing it -- in a file whose own
history records it being broken: on 2026-08-12 the preview lacked the debug
block and `lux_area_light_rig.gd:61` failed to parse in a walk of the same
package whose portability test had scored `parser_error_count 0`.

So the cap lands in BOTH writers, and `tests/unit/test_project_godot_agreement.py`
asserts that every setting the exporter writes under `[rendering]` and
`[debug]` also appears in the preview. The comment stops being a promise.

## [0.42.0] - the Lux stage never hashed the program it runs

0.41.0 rewrote `assets/godot/run_lux_apply.gd`. The next run would have
CACHE-HIT, never executed it, kept the old `lux.quality.json`, and reported
success. The evidence run for 0.41.0 would have produced no evidence.

WHY, from `scheduler.py:414-437` rather than from assumption. The cache key is
`BuildFingerprint.digest()` over twelve components, and this change moves none
of them:

    adapter_id / adapter_version / schema_versions   unchanged
    tool_version / repository_commit                 LUX's repository --
                                                     `probe` reads
                                                     installation["repository"]
    normalized_arguments                             --scene/--preset/--out
    input_hashes                                     the scene, the lights
                                                     json, the scene's art
                                                     payload. Not the driver.
    everything else                                  unchanged

`tool_version` even carries a `+dirty.<hash>` suffix for uncommitted tool
edits, added because "an on-disk fix that has not been committed keeps
cache-hitting the pre-fix artifact". It tracks the Lux repository. This driver
is not in it.

This is the fault `adapter_version = "0.4.0"` was cut for, one level further
out. That one hashed the scene's bytes and not the art the scene names. This
one hashes the inputs and not the program that reads them.

WHY ONLY THIS ADAPTER

Lux is the only tool whose driver Level Factory ships. Laser Tag runs
`res://addons/laser_tag_tool/runners/run_map_eval.gd` out of its own
repository, so `repository_commit` covers it. `lot` and `walktest` fold `.gd`
files into their own input scans. Only the Lux adapter copies a GDScript out
of `level_factory/assets/godot/` while reporting a different repository's
commit -- and it does so in BOTH modes, under the same `driver_src` key.

THE FIX

`driver_src` is hashed in `fingerprint_inputs` ABOVE the fixture-gate branch,
so one statement covers `lux_apply` and `lux_fixture_gate`. `adapter_version`
goes to 0.5.0, which invalidates every existing Lux cache entry exactly once
-- which is what gives 0.41.0 an execution to be measured on.

`tests/unit/test_lux_driver_in_fingerprint.py` is a BEHAVIOURAL test, not a
source-shape one: it calls `fingerprint_inputs`, edits the driver on disk, and
asserts the fingerprint moved -- in both modes, and asserts the rest of the
fingerprint did not move with it.

## [0.41.0] - the applied preset is read off Lux, not echoed from the request

`lux.quality.json["preset"]` was the `--preset` argument written straight back
out:

    var quality := {"preset": preset_name, ...}

Roadmap item 53 ranked FIRST a comparison of that field against Level
Factory's `_preset_for(model)`, and its status line said the file "already
echoes the applied preset back". It echoed the REQUEST. The two strings are
the same string; the check could not fail. That is a check that cannot fail,
proposed inside an item about checks that cannot fail, and it was caught by
reading `run_lux_apply.gd` rather than by running it.

WHAT LUX ACTUALLY OFFERS

`LuxRoot.get_current_preset()` returns `_current`, assigned in exactly one
place -- `_apply_immediate`, from the library resource. Reading it back after
the blend also covers the failure the driver's existing library-dictionary
check cannot see:

    func apply_preset(preset, blend_time = 0.0) -> void:
        if not _initialized:
            active_preset = preset      # and applies NOTHING
            return

The name is in the library, so `preset_known` is true, so no issue is raised,
and the level ships with no look. The dictionary says the preset exists; only
LuxRoot says it arrived.

THE CHANGES

    lux.quality.json   "preset"          the REQUEST, unchanged meaning
                       "preset_applied"  NEW -- LuxRoot.get_current_preset()

    lux.validation.json  LUX_PRESET_NOT_APPLIED (moderate) when the name
                         resolved and the look still did not land

No Python changed. The driver already writes findings to
`lux.validation.json` and the Lux adapter's `normalize_validation` already
passes arbitrary codes through, so the new finding reaches the findings
channel without touching the adapter.

Third edit, same file, same shape of defect: `ResourceSaver.save(...)`'s
return was discarded and `applied_ok` tracked only `pack()`, so a save that
failed reported `applied: true` for a scene never written.

`tests/unit/test_lux_preset_readback.py` is a SOURCE-SHAPE test and says so
in its own docstring: applying a preset needs a Godot process and unit CI has
no headless-Godot harness. It cannot prove the driver works. It pins the one
regression that would restore the tautology without changing an output key --
re-pointing `preset_applied` at `preset_name`.

Roadmap item 53, first ranked fix. The item's premise is corrected in place
rather than quietly dropped.

## [0.40.0] - one resource manifest per package, and it is the current one

A package shipped two. `resource_manifest.json` is
`dispatch.resource_manifest.v0.2`, written by the handoff stage about the
handoff; `export_mission` copies that directory in, overwrites `mission.tscn`
with its own portable entry, adds the composed building and its art, and
writes `portable_resource_manifest.json`. By the time the package is
finished, Dispatch's file describes something that no longer exists.

Measured on unlit_probe_001, 2026-08-16, art-unlit:

    resource_manifest.json           17 entries; mission.tscn at 16,246 bytes
    mission.tscn on disk                                             688 bytes
    portable_resource_manifest.json  58 resources, sha256 + size each,
                                     including lot/shell/site.tscn and all
                                     31 art/zoo GLBs

The mtimes said which way round it happened without needing anybody's memory:
the manifest was written at ...388494 and `mission.tscn` at ...389514, one
second later. A recipient verifying the package against its own manifest
fails on the first file -- and the stale one has the better name, so it is
the one they open.

THE FIX

`resource_manifest.json` joins the `skip` set the handoff copy already uses.
Dropped rather than regenerated, following the precedent twelve lines below
it: the composed-root copy already skips `portable_resource_manifest.json`
because the composer writes one and LF writes its own, and two answers to one
question is the defect. If a recipient contract ever requires that exact
name, the fix is to regenerate it there rather than un-skip it -- the problem
was never the file, it was the file being stale.

Roadmap item 50.

## [0.39.0] - the composed root lands where the assembly says it does

Every single-shell themed export since 0.37.0 has shipped a level that cannot
open, in BOTH `portable-godot` and `art-unlit`. Measured on unlit_probe_001,
2026-08-16: 56 files, 7,158,515 bytes, and the entry scene reaches TWO of
them.

    site.tscn: relative ext_resource resolves to nothing: lot/shell/site.tscn
    resource_count: 2

WHY

`export_mission` step 2 copies the composed root to the package ROOT. Step
2.5 -- added in 0.37.0 -- then copies `themed_site_assemble/out/site.tscn`
over the root `site.tscn`, and copies nothing else out of that job. On a
VARIED lot that is fine: the composed root already holds `lot/<archetype>/`
per building, so the assembly's references resolve. On a SINGLE-SHELL mission
the composed root IS the one building laid flat, and the assembly names
`lot/<id>/site.tscn` -- a directory `site_packages.py` staged in the job's
out dir and the export never carried.

0.37.0 was right about the problem it fixed -- on lot_demo_001 the assembly
scene reached no package at all and an unlit export instanced nothing -- and
it was measured on that five-building mission, which is the shape where this
does not bite.

THE FIX

`_assembly_building_dir` reads the assembly scene and returns `lot/<id>` when
it names exactly one such package AND the composed root has no `lot/` of its
own. The composed root is then copied there instead of to the package root,
so the building lives under `lot/<id>/` on both mission shapes and the
assembly's reference resolves. The composer's own `site.tscn` stops being
skipped in that case, because under `lot/<id>/` it IS the building.

ASKED, NOT INFERRED. The first attempt at this used
`_root_site_wanted(presentation_dir)` as the single-shell test. It is not
one: it returns True whenever there is no Lux scene to ask, which on a
mission that never ran Lux is every time. The scene that names the path is
the artefact that knows, which is the rule this file already states about the
presentation scene two comments earlier.

Roadmap item 49, third reading. The two earlier readings -- the lot drawing
this pipeline's own output, and the export flattening `lot/shell/` -- are
recorded there as wrong, with what refuted each.

## [0.38.0] - the pool a mission draws from is a property of the mission

`unlit_probe_001`, one fresh workspace, one candidate, seed 5017, run once
from empty. `lot_assemble.candidate.seed_5017` succeeded twice and produced
two different sites.

    batch create                    123 shells -> cr_garage
    run --art --unlit --gameplay     98 shells -> landmark_hall_a03

    graybox   17 openings, 178 colliders, 12 markers
    art       13 openings, 176 colliders,  7 markers
    shell.glb sha256:a929d7d2... in BOTH -- same lot, different building

Everything that graded the mission ran under `batch create` and measured
`cr_garage`: walktest nav QA, Laser Tag, the structural checks, and the
functional lock. The package would have shipped `landmark_hall_a03`.

THE MECHANISM WAS ONE BOOLEAN

    commands/__init__.py:238   _art_run = any(j.stage_id == "themed_site_assemble"
                                              for j in plan.graph.jobs())
    commands/__init__.py:942   if themed_map or art_run:   # narrow 123 -> 98

`_art_run` described THE INVOCATION, not the mission. `batch create` plans no
art layer; `run --art` plans one.

AND THE GATE IT SAT IN WAS ITSELF A FIX

The greybox branch started narrowing because `probe_pool_divergence.py` had
measured that on lot_demo_001, 14 of 15 building slots already carried an
archetype other than the one Laser Tag graded and 13 graded archetypes never
shipped at all. "Grade the pool that ships" was the right goal. It made the
two passes agree within one invocation and could not make them agree across
invocations -- so the divergence moved from inside a run to between the run
that grades and the run that ships, where only the functional lock stands.

THE FIX

The narrowing is keyed on the BRIEF. Reaching that line already means
`lot_library` is set, which is also what gates the art layer, so the pool is
now the same in every invocation of a mission's life. `art_run` is gone from
the signature, the call site and the module.

THE COST, STATED: a brief that sets `lot_library` and never runs `--art` now
draws from the narrower pool too -- 98 of 123 shells. Missions without
`lot_library` are untouched byte-for-byte.

WHAT THIS DOES NOT DO. Missions already built with `lot_library` will
re-select buildings on their next run, and their existing grades stop
describing them. That is the point -- those grades already described a
different level -- but it is not free, and `--force` is what re-runs it.
Whether the draw may move behind `candidate_selected` AT ALL is roadmap item
48 question 1 and is still open.

Evidence, in the repo because `_runs/` is gitignored:
`docs/findings/ITEM48_THE_DRAW_MOVED.md`.

## [0.37.0] - the package that opened to nothing, and passed

The first art-unlit package built from a real mission -- lot_demo_001, 180
files, 28.6 MB of themed geometry -- opened to an empty scene. Its whole
entry was `print('scene instantiated ok')`: no `load()`, no `add_child()`.

EVERY INSTRUMENT AGREED IT WAS FINE

    export_closure_scan.json: {"ok": true, "resource_count": 6,
                               "missing_resource_count": 0}

Six resources in a 180-file package. Closure walks FROM the entry scene, so
an entry that references nothing is trivially closed -- the emptier the
package, the more certainly it passes. The portability test would have agreed
too, because `mission.tscn` prints its marker whether or not it added a
child.

WHY

There is no `site.tscn` at the export root, in EITHER package.
`themed_site_assemble` writes one -- 31,872 bytes on lot_demo_001 -- and it
reached no package. The lit export got away with it because
`presentation/lux.applied.tscn` is Lux's output OVER that assembly and stands
in for it. Drop Lux and the five `lot/<archetype>/site.tscn` packages have
nothing positioning them.

`write_entry_scene`'s `elif site.exists()` could never have caught this: the
file it looks for was never in the package. 0.36.0's docstring called that
fallback correct for art-unlit, and it would have been, if the file were
there.

TWO CHANGES

The assembly scene ships. `themed_site_assemble`'s `site.tscn` is copied to
the package root for every mode carrying art, AFTER the composed root --
`_root_site_wanted` may have let the composer's own root site.tscn through,
and for a single-shell mission that is the composed BUILDING while this is
the assembled SITE. Lux runs against the assembly, so `res://site.tscn` must
resolve to the assembly.

This is not the RETRACTED position in export.py's comment. That is about the
COMPOSER's root site.tscn, whose art/ directories are empty for a themed
mission and which arrives referencing twenty modules that exist nowhere
(measured: 21 unresolved of 40). Different file, different stage, and its
references are the five the package already carries.

An entry that instances nothing is an error. `write_entry_scene` raises
`ExportContentError` instead of writing an empty body. It knows nothing about
modes, so a mode nobody has written yet cannot ship hollow either -- the
repair is specific, this guard is general, and the repair alone would have
left the next empty package to be found by whoever opened it.
`export_closure.json` also records `entry_instances`, because `entry_scene`
says `mission.tscn` for a hollow package too.

WHAT THE OLD TESTS COULD NOT SEE

0.36.0's fourteen tests build a handoff containing `site.tscn`, so the base
copy always left something at the export root and every package had something
to instance. The fixture was accidentally healthier than a real mission. The
new tests build one without it.

AMENDED, SAME VERSION -- THE GRAYBOX IS A BASE, NOT AN ALTERNATIVE

The new guard fired on PURE-SHELL, in two unit tests and the integration
export test. It was right, and pure-shell was broken:

    base_dir = handoff_dir if (handoff_dir and handoff_dir.exists())
               else graybox_dir

An either/or, where the comment three lines above already says the
Dispatch handoff is a LAYER -- and a layer goes on a base rather than
replacing it. The moment a mission gained a dispatch_handoff, Lot's
site.tscn stopped shipping with it.

Two exports of lot_demo_001 measure it: the one from 2026-08-10, before
this mission had a handoff, carries a 25,378 byte site.tscn and a 688
byte entry; today's carries neither and its entry instances nothing. For
every mode carrying art this was invisible, because the themed assembly
replaces the graybox one. Pure-shell has no replacement.

The graybox tree is now copied UNDER the handoff for pure-shell only,
with the same `skip` applied. Art modes are untouched.

RECORDED, NOT CHANGED: Dispatch writes a 65,493 byte `mission.tscn` --
the composed mission scene -- and every export discards it and writes a
~600 byte stub instead. export.py says that is deliberate, an export
carrying one entry. Whether it is still right is unmeasured.

AMENDED AGAIN -- THE 656 TESTS NOBODY WAS RUNNING

0.34.0, 0.35.0, 0.36.0 and 0.37.0 each reported "still green" against
`tests/service` and `tests/integration`: 28 tests. `tests/unit` is 656,
and nothing in this arc ran it. `test_fanout.py` had been failing since
0.35.0 and said so to nobody. Every selftest from here runs `tests/unit`
whole -- a subset described as the suite is this release's own subject,
one level up.

test_fanout.py's `_plan` asked for `layers={LAYER_ART}` and asserted
`lux_apply` is planned once. 0.35.0 fixed exactly that in
test_planner_graph.py and missed this file, because the search was "the
file I know about" rather than `grep -rn lux_apply tests`.

The two closure fixtures build a handoff whose only scene is
`mission.tscn` -- which `write_entry_scene` overwrites with its stub, so
they have described a package that opens to nothing since the day they
were written. They gain a `site.tscn`. Neither assertion is weakened.
That is lot_demo_001's empty art-unlit package in miniature, and it is
why the guard lives in `write_entry_scene` rather than in a mode.

## [0.36.0] - art-unlit: the same build, shipped twice

0.35.0 made the light layer declinable at RUN time. A mission run unlit
already exported correctly, with no code: no `lux_apply` output means no
`presentation/` directory, so `_root_site_wanted` keeps the themed
`site.tscn` and `write_entry_scene`'s `elif` makes it the entry.

What could not be done was taking a mission that DID run Lux and shipping an
unlit package from it -- two archives out of one build, so a recipient can
drop in ours and theirs and compare the same geometry under two lighting
solutions. `MODE_ART_UNLIT` is that subtraction, at export time.

TWO QUESTIONS THAT LOOKED LIKE ONE

`profile.mode == MODE_PURE_SHELL` gated three separate things and stayed
correct only while pure-shell was the only mode that declined anything:

    does this mode ship Lux's RESULT?    pure-shell no   art-unlit no
    does this mode ship the themed ART?  pure-shell no   art-unlit YES

The `_PRESENTATION_FILES` skip and the copy of `presentation/` now ask
`ships_lux(mode)`. The third branch, which copies the composed themed root,
still asks about pure-shell alone -- and carries a comment saying why
`ships_lux` there would strip the art out of the art-without-light mode.

THE MANIFEST DESCRIBES THE PACKAGE, NOT THE RUN

`cmd_export` derives layers from what is on disk, so a lit mission reports
the light layer -- correctly, `lux_apply` ran. Exporting art-unlit from that
mission would have declared a layer the package does not contain, which is
0.34.0's failure with the sign reversed. `export_mission` subtracts the light
layer whenever the mode ships no Lux.

THE ENTRY SCENE NEEDED NO CODE AND ITS COMMENT DID

`write_entry_scene` prefers the presentation scene and falls back to
`site.tscn`. With Lux dropped the fallback fires and names the THEMED site,
which is right. Its docstring said site.tscn is the entry "only for a graybox
export that has no presentation pass", and an art-unlit export is neither
graybox nor without an art pass. Code that is correct for a case its own
explanation excludes is code somebody later 'fixes'. The comment is
corrected; the condition still asks what EXISTS rather than what mode this
is, because export.py already decided by not copying the file.

MEASURED

`tests/unit/test_art_unlit_export.py` builds real packages from fabricated
job directories and reads back what landed: art-unlit keeps `wall.glb` and
the themed material and drops both Lux files and the whole `presentation/`
folder; portable-godot still ships both; pure-shell still drops both. The two
archives differ in name and share an interior folder, so a recipient can swap
one for the other without every `res://` path moving.

NOT MEASURED

An actual unlit RUN through the real tools, and an art-unlit package opened
in Godot. Stage 3. These prove which files a mode copies and what the
manifest claims, not that the engine likes the result.

AMENDED, SAME VERSION -- A FOURTH LIST NOBODY KNEW WAS A LIST

The first real `export --mode art-unlit` against a workspace failed:
`internal error: 'art-unlit'`. A KeyError, from a third place the mode
had to be registered:

    mode_map = {"portable-godot": MODE_PORTABLE, ...}

Every entry mapped a value to itself -- `MODE_PORTABLE` IS the string
`"portable-godot"` -- so the dict's only real behaviour was raising
KeyError on a mode it had not been told about. `cmd_portability_test`
twelve lines below already read `args.mode` straight through, which is
the proof it was never needed.

The fourteen tests missed it because they exercise `export_mission`,
which is the right unit for 'which files does this mode copy'. Nothing
exercised `cmd_export`. So the map is deleted, `export.py` publishes
`MODES`, and a new test PARSES `main.py` with `ast` and asserts the
argparse `--mode` choices and that set are equal in both directions.
Adding a fifth mode and forgetting one place is now a failing test
rather than a bare KeyError in front of whoever typed it.

## [0.35.0] - Lux becomes a layer you can decline

`LAYER_ART` meant "Zoo + Pixelcoat + Patina + Lux", one indivisible thing, so
a team bringing its own renderer had no way to ask for the art pass without
the render. `LAYER_LIGHT` splits Lux's apply pass out. Roadmap item 47,
stage 1.

ONLY THE APPLY PASS MOVED

`lux_apply` is the render solution and it is the only stage behind the new
layer. `zoo_fixtures_build` bakes the physical light hardware from the locked
shell's manifest and `lux_fixture_gate` machine-checks it -- spawn count,
lamp-to-hardware co-location, powered kill/restore, findings BLOCKING. A
floating light or a dark fixture is broken GEOMETRY whoever lights it, so
both stay in `LAYER_ART`.

That is the useful part: an unlit art package still ships validated fixtures
and their `LuxEmit` markers, which another lighting system can read as a
contract rather than a guess.

`--art` STILL MEANS WHAT IT MEANT

`--art` produces a lit level and `--target presentation` plans the full
stack, both unchanged. If `--art` had quietly stopped producing lighting,
every existing script saying `--art` would ship something different without
anyone typing anything. `--unlit` subtracts the light layer; nothing
subtracts it by default.

THE ONE LINE THAT CARRIES THE RISK

    dispatch_dep = lux_jid if LAYER_LIGHT in layers else themed_jid

Falling through to the graybox default would build the Dispatch handoff on a
site with no art pass on it and report success. `themed_site_assemble` is the
last stage that makes a place, and an unlit art package is still that place.
`themed_jid` is bound unconditionally at the same indentation in the same
branch, so the else cannot raise -- checked rather than assumed. Six tests in
`tests/unit/test_light_layer.py` cover this line, including one that asserts
no job in either plan depends on a job that was never planned.

LIGHT REQUIRES ART, AND IS REFUSED WITHOUT IT

`lux_apply` runs over `themed_site_assemble`'s output, so light-without-art
asks to light a place that was never themed. The DAG's answer would be a plan
with no optional jobs -- which is legal, runs, and succeeds, producing a
graybox nobody asked for. `normalize_layers` raises instead, and
`plan_mission` routes every path through it, including the legacy `--target`
mapping. Adding the missing layer silently would be worse: a caller who asked
for light would be billed for four tools it never requested. An unknown layer
name is refused the same way, which it never was -- `--art` misspelt used to
plan the graybox and report success.

THE EXPORT SIDE

`_layers_produced` reads the light layer from `lux_apply`'s output, which is
what that directory always meant; 0.34.0 had just finished stopping it from
standing in for the art layer as well. A workspace with Lux output now
reports `{art, light}` rather than `{art}` -- one more layer than before,
never fewer, and the distinction is what `LF_MANIFEST.json` needs to describe
an art-unlit package honestly.

NOT IN THIS RELEASE

There is no `art-unlit` export MODE. A mission RUN without the light layer
already exports correctly: no `lux_apply` output means no `presentation/`
directory, `_root_site_wanted(None)` keeps the themed `site.tscn`, and
`write_entry_scene`'s `elif` makes that the entry. What is missing is
export-time subtraction -- taking a mission that DID run Lux and shipping an
unlit package from it, so two archives from one build can be compared. Stage
2.

AMENDED, SAME VERSION -- ONE VERSION, READ FROM ONE FILE

This release bumped `VERSION` and not `pyproject.toml`, so the drift
0.34.0 had just finished correcting -- eleven releases of it -- restarted
at one release, in the patch immediately after the one that fixed it. The
check 0.34.0 added caught it.

The correction is not another bump. `pyproject.toml` no longer states a
version at all: it declares `dynamic = ["version"]` and points
`[tool.setuptools.dynamic]` at `VERSION`, which is the file the running
code already read. There is no second copy to disagree. A check that two
files match has to be remembered by every future release patch, and the
one that forgets is the one that drifts; deleting the copy cannot be
forgotten.

## [0.34.0] - the art layer was reported from Lux's output

`cmd_export` does not take the layer set from the run. It infers it from what
is on disk, and it asked the wrong directory:

    if lux_dir.exists():
        layers.add(LAYER_ART)

`lux_dir` is `<mission>.lux_apply/out`. "Did the art layer run?" was answered
by "did Lux produce output?" Everything Pixelcoat, Zoo and Patina built, and
the themed site assembled from it, was invisible to that test.

WRONG TODAY, with no new feature involved. A mission whose art pass succeeded
and whose `lux_apply` failed exports an `LF_MANIFEST.json` declaring no art
layer, on a package full of art. Nothing reads that field, so nothing has
ever objected.

It becomes structural under roadmap 47, where `lux_apply` moves behind its
own layer and art-without-light is the normal case rather than a failure --
every such package would ship a manifest denying its own contents. This
lands first, alone, against a suite measured green, rather than inside the
change that makes it urgent.

THE FIX IS A UNION

    art = compose_root.exists() or lux_dir.exists()

`presentation_compose/out/presentation` is what the art layer produces, so it
is what stands for it. The `or` is deliberate: this must never report FEWER
layers than the lines it replaces, or a workspace that exports correctly
today would describe itself differently after an upgrade. Lux runs on the
composed site and cannot exist without one. Strictly wider than the old test,
strictly narrower than lying, and `test_it_is_never_narrower_than_the_code_it_replaced`
asserts exactly that over all eight combinations.

It is a named function with a test now. The reason this survived weeks is
that the decision was four inline lines in the middle of a 90-line command.
The directories are still spelled in `cmd_export` -- building
`<mission>.<stage>/out` inside the helper would put a second derivation of
that name in a second place, which is the failure `walk_content_dir`
describes in its own docstring.

ALSO

`pyproject.toml` said `0.22.0` against a `VERSION` of `0.33.0` -- eleven
releases of drift. Nothing reads pyproject for the running version, so
nothing broke, but an installed copy reported a version six days stale. The
selftest now asserts the two agree.

RECORDED FOR THE NEXT PERSON: `pyproject.toml` carries `addopts = "-q"`, so
every `pytest ... -q` actually runs at `-qq`, and at two the run summary line
is suppressed entirely. That is why a green suite writes 80 bytes of dots
with no `28 passed` line in it, and why two attempts to detect "did the test
run" by reading pytest's prose were both wrong. The return code was always
the answer.

## [0.33.0] - a bake that published nothing, and a test that could not see it

0.32.0 repaired collection, so `tests/service` and `tests/integration` ran
for the first time in weeks and nine tests failed. They are ONE failure with
eight downstream absences:

    bank_block_001.presentation_compose              failed

`themed_site_assemble`, `lux_apply` and `dispatch_handoff` never ran. That is
why the facade reported PLANNED nodes, the dashboard stayed `pending`, no
`mission.tscn` appeared, and `review` said "no presentation previews".

THE CAUSE

`diagnostics bank_block_001.presentation_compose`:

    failure_class: input_validation_error
    message: dressing_glb for the mission shell: no '*_dressing.glb' in
             ...jobs/bank_block_001.zoo_dressing_build/out -- the job that
             bakes it reported success without publishing one

The test-fixture Zoo stub's `--dress` branch wrote its index and no geometry.
Its own `--fixtures` branch has always written both, which is why
`lux_fixture_gate succeeded` in the same run this broke. Real Zoo's `--dress`
publishes geometry. The guard was right; the stub was one line short.

NOT A 0.32.0 REGRESSION. `dressing_glb", "_dressing.glb"` appears twice in
`adapters/presentation/__init__.py.pre_032` and twice in the current file,
unchanged. This has been failing since the dressing guard landed around
2026-08-06 and nothing could see it, because collection was aborting.

TWO BLIND SPOTS, BOTH CLOSED

THE BAKE DID NOT DECLARE ITS GEOMETRY. `ZooAdapter.plan_commands` declared
only the index for mode `dress`. Its declared outputs appeared, so the job
reported `succeeded`, and the missing geometry surfaced two stages later as
somebody else's input error naming a directory upstream. A job that does not
publish what the next stage requires has failed, and it must fail as itself.

The `fixtures` branch has the same shape and is LEFT ALONE. No run has failed
on it, and a mission with zero light fixtures may legitimately bake no
geometry -- declaring it on a guess is how a working mission starts refusing.
Measured and left open rather than fixed blind.

THE TEST COULD NOT TELL SUCCESS FROM FAILURE. It asserted `stage in r.stdout`
against a run that prints a status word at the end of each job line, so
`bank_block_001.presentation_compose  failed` CONTAINS "presentation_compose"
and that assertion passed on the stage that broke the run. Six of its eight
checks passed. The only two that caught anything, `lux_apply` and
`dispatch_handoff`, caught it by never appearing at all. It now reads the
status word and accepts only `succeeded` or `cache`.

WHAT THIS DOES NOT CLAIM

It fixes the stage that failed. It does not promise the nine go green. The
run has not reached `themed_site_assemble`, `lux_apply`, `dispatch_handoff`,
export or the portability test since roughly 2026-08-06, and everything
behind this wall is unmeasured. The selftest runs the integration test and
prints what happens rather than asserting a pass it has not earned.

AMENDED, SAME VERSION -- WHAT THE FIX UNCOVERED

The presentation chain runs. Under the strict status check all eight
stages reported `succeeded` or `cache`, including `lux_apply` and
`dispatch_handoff`, which had not run since roughly 2026-08-06, and
both export commands returned 0.

The next wall is our own rename. The test still expected
`exports/bank_block_001.portable-godot/HANDOFF.md` and
`exports/bank_block_001.zip`; 0.26.0 and 0.27.0 replaced both with the
three names in docs/EXPORT_NAMING.md. Written 2026-07-24, it has not
run since we renamed the thing it checks.

The directory is now spelled out literally rather than imported from
`export_build_dir_name` -- a test that asks the code for the name it
expects passes whatever the code does. The archive carries a seed, a
UTC instant and the factory version, so it is matched by shape and
exactly one must match. The `HANDOFF.md` assertion searches the package
instead of asserting a path, and prints the real tree when it fails,
because whether a folder export nests an interior `LF_<mission>/` has
not been observed. Loose on purpose, and recorded as such.

## [0.32.0] - the composer fingerprint, which was never there

`pytest tests` has been aborting during collection on
`tests/test_presentation_fingerprint.py`, which imports `_COMPOSER_SOURCES`
from `adapters.presentation`. I went in expecting a stale import against a
renamed symbol.

Neither `_COMPOSER_SOURCES` nor `_composer_fingerprint` exists anywhere in
the repository, and `fingerprint_inputs` has no `composer` key. The test is
not stale. It describes a guard that was never implemented, and because
collection aborted, nothing ever said so.

WHAT THE GUARD IS FOR, IN THE TEST'S OWN WORDS

Measured 2026-08-05. `strip_greybox_base` was fixed in Deli Counter. DC
committed, DC's suite went green, `run --art --force` reported
`deli_generate SUCCEEDED` and `zoo_kit_build SUCCEEDED`, and this job
reported `cache`. The composed `site_base.glb` came back byte-identical and
the invisible wall the fix was supposed to remove was still there.

The presentation job does not merely read DC's data -- it EXECUTES DC's code,
`portable_building.build_package` through a driver. Its output can change
while every input hash stays identical. Nothing hashed DC's source.

`verify-contracts` catches a sub-tool drifting out from under an adapter.
This is that failure with the opposite sign: a sub-tool FIX not reaching a
cached job.

One line in the file already knew. The comment above the `lot` block reads
"The composer fingerprint had exactly this hole for its own sources and it
took a walk to find" -- written about something that is not in the file.

WHICH SOURCES, MEASURED

The import closure of `portable_building` inside DC 0.89.0 is two modules:
`portable_building.py` and `themed_tscn.py`. Both are declared.

`circulation.py` is declared too and does not exist in 0.89.0. That is
deliberate -- `_COMPOSER_SOURCES` is a hand-maintained list of what composes
a building, not a computed closure, and an absent declared source is SKIPPED,
never faked. A placeholder hash for a missing file is identical across every
DC version that lacks it, which is the opposite of a fingerprint.

`presets.py` and every `test_*.py` are deliberately excluded. A cache that
invalidates on everything is a cache nobody keeps.

ONE LINE OF ONE TEST IS REPAIRED

`test_missing_source_files_are_skipped_not_faked` unlinked `circulation.py`
by name. It now deletes the first declared source, whatever that is --
hardcoding one member of a list the same module parametrises over breaks on
an unrelated edit. Nothing else in that file changes. It was right the whole
time; it just could not run.

WHAT THIS COSTS

Every mission recomposes once. `composer` is a new fingerprint key, so no
existing compose matches. That is the correct behaviour for a guard whose
whole premise is that a stale compose is invisible -- and it is the last
recompose that will be needed for this reason.

The key is written even when the DC repo cannot be resolved, as `{}`. A
mission that later gains a resolvable `deli_repo` then recomposes once,
rather than silently keeping a fingerprint taken without one.

## [0.31.0] - the coverage report counts, and the gate turns on

`LOCK_COVERAGE_ENFORCED` is True. The mission that earned it is
`lot_demo_001`, recomputed under schema v0.2:

    counts       markers 55, openings 76, surfaces 1029,
                 vertical_links 4, ground 5, stair_systems 2
    site_counts  markers 42, openings 76, surfaces 1029,
                 vertical_links 4, ground 5, stair_systems 0

`markers` 55 against 42 is the union -- exactly the thirteen Deli
anchors 0.30.0 stopped dropping. `stair_systems` 2 against 0 is the
Deli backfill, and it is everything this lock protected before 0.29.0:
two records, for months, under three signatures that all reported
healthy. The protected set now carries 1,171.

IT REFUSES A VACUOUS LOCK, NOT AN UNGUARDED SITE

Enforcement rejects a lock whose every signature is empty. It does NOT
reject `guards_no_site`, which is stricter and more meaningful, because
exactly one mission has been measured under this spec and refusing on
the stricter test would fail missions nobody has looked at. That is the
argument `CLOSURE_ENFORCED`'s comment makes, and it is the second time
this factory has avoided a day-one over-enforcement by copying it.
Widen it when a second and third mission have been measured, naming
them where this names lot_demo_001.

THE GATE IMMEDIATELY FAILED THE UNIT SUITE, AND IT WAS RIGHT TO

`test_anchor_drift_is_detected` uses a Deli-shaped fixture -- `anchors`,
no `markers` -- and turning enforcement on made it raise. Not a bad
test: `_anchor_registry` falls back to Deli's `anchors` when the site
publishes no `markers`, and 0.29.0 wrote that fallback while leaving
`anchors` out of `PROTECTED_KEYS`. So coverage reported the registry
UNGUARDED while it was hashing that very list, and the same omission
had dropped `anchors` from `BACKFILLED_FROM_DELI` even though
`_merged_gameplay` still backfills it.

Harmless while the flag was off. The moment it went on, a misreading
became a refusal. 0.28.0's selftest asserts exactly this invariant for
`_collision_signature` -- that coverage reads what the signature reads
-- and there was never an equivalent for the registry. There is now.

AND AN ORDERING BUG I HAD ALREADY FIXED ONCE, IN THE SAME FUNCTION

`cmd_approve` recorded the approval and then called
`_store_functional_lock`. With enforcement on, a refused lock raises
out of a gate already recorded as approved -- an approved
`functional_shell_locked` with no lock behind it, delivered as a
traceback. 0.28.0 fixed precisely this for `--candidate`, four lines
higher, and I did not look for it here. The lock is now attempted
before anything is recorded, and a refusal returns EXIT_BLOCKED with
the coverage report.

WHY COUNTS, ORIGINALLY

`coverage` answered "is something there" and never "how much".
`markers: guarding=True` read identically whether the registry held
fifty-five anchors or one.

That is the gap that hid the whole defect. Before 0.29.0 the collision
signature reported `guarding=True` while carrying two Deli stair systems and
nothing else, and every report in the system agreed with it. A count would
have shown it the first time anyone looked.

- **`coverage.counts`** -- per protected key, in the MERGED view. What is
  actually hashed.
- **`coverage.site_counts`** -- the same keys in the site file alone.

The pair is the useful part. For a unioned key the two differ by exactly what
the other tool contributed, so the union's effect is a subtraction a reader
can do in their head, from the lock file, without a probe.

WHAT THE HASHES ALONE COULD NOT SAY

After 0.30.0 the recomputed lock's `anchor_registry_hash` moved from
`b47f0dc` to `6dd9d16` while `collision_fingerprint` stayed at `091d798` --
the registry changed, the collision signature did not, which is the right
shape: Deli's anchors in, Deli's 238 surfaces still out. It proved the union
fired. It could not say how many anchors it added, and the difference between
"it fired" and "it added thirteen" is the entire lesson of the last two days.

## [0.30.0] - the registry stops dropping Deli's anchors

`tools/probe_site_vocabulary.py` compared what both tools publish for the
keys they share:

    markers   site 42, deli 14 -- of deli's 14, ONE appears in the site's 42
    no match: CREW_SPAWN_A, RESPONDER_SPAWN_1, COVER_LOW_AUTO_TELLER_COUNTER,
              COVER_LOW_AUTO_DESK_MANAGER_OFFICE_0, ... (13 in all)

Thirteen gameplay anchors -- two spawns and eleven cover points -- were being
dropped from the gameplay-anchor registry.

THEY WERE NEVER A SUBSET

Lot's markers are site-level (`b0/ATTACKER_SPAWN_FRONT`, building entries).
Deli's are interior anchors, and the same report's `rooms` line confirms it:
Deli's unmatched `manager_office`, `security_room` and `vault_room` are
exactly where those cover points live. The same shape as `vertical_links`
(4 hatches) against `stair_systems` (2) -- complementary, not competing.

`_merged_gameplay` had one rule for a shared key: the site wins. That is
right when Lot restates what Deli said and wrong when each says something the
other does not, and nothing distinguished the two cases.

- **`UNIONED_WITH_DELI` is the second rule**, beside `BACKFILLED_FROM_DELI`,
  and `markers` is its only member. Both tools' records are kept.
- **Deduped by NAME-TAIL, not exact id.** Lot namespaces what it does
  restate -- Deli's `VAULT` becomes `b0/VAULT` -- so an exact-match dedupe
  would keep both and count one anchor twice. Exactly one of Deli's 14
  matches this way; the rule exists for that one.
- **`coverage.unioned_with_deli` names it**, for the reason
  `backfilled_from_deli` exists: a signature carrying two tools' records
  should say so.

WHY NOT `surfaces`

213 of Deli's 238 matched by tail. The 25 that did not are `int_col_-1_2_*`
-- story -1, a basement -- and window sub-parts (pane, sill, lintel). If Lot
never places that geometry it is not in the shipped level, and hashing it
would protect what the package does not contain, and report drift the day Lot
legitimately stops emitting it. Deli's markers ship: the Dispatch handoff
carries them into the export. That asymmetry is the whole argument.

`openings` is 0 of 19, but that compares whole records against coordinates
Lot transforms when it places a shell. Undecidable from these two files, and
not decided here.

NOT DONE HERE

`LOCK_COVERAGE_ENFORCED` stays False. The order is land the change, recompute
`lot_demo_001`, confirm the registry grew by 13, THEN flip. Flipping now
would assert the fix worked without looking, which is the failure this
factory has hit five times in two days.

Those 25 collision nodes are a question for `lot`: geometry present in the
shell and absent from the assembled site is either a deliberate drop nobody
recorded, or loss between two stages. The lock cannot tell which.

## [0.29.0] - the lock protects the site

The repair. `docs/FUNCTIONAL_LOCK.md`, accepted 2026-08-14, is the spec;
every decision here is argued there.

    collision_fingerprint   + surfaces node names, ground sources,
                              openings, vertical_links
    anchor_registry_hash    markers, keyed on `name`, WITH position
    route_graph_hash        retired

- **`surfaces` contributes node names only.** The material dict beside each
  node is rewritten by Patina and Pixelcoat during the art pass; hashing it
  would report drift on every normal run, and a gate that cries drift gets
  switched off. A lock that never fires and a lock that always fires protect
  the same amount.
- **`ground` contributes each building's source glb.** Swapping a building's
  mesh is exactly what this gate is for and need not rename a single node.
- **`openings` and `vertical_links` are hashed whole**, breach fields
  included. A door that stops being vaultable is a functional change even if
  it does not move. Lot's four `vertical_links` are a different population
  from Deli's two `stair_systems`, not a replacement: both are kept.
- **`markers` replaces `anchors`, keyed on `name`.** `id` is `"FRONT"` scoped
  to a building and every building has one; the old registry sorted and keyed
  on `id`, so two distinct anchors normalised to identical entries and it
  silently under-counted.
- **Anchor position joins the registry, and that is a change of meaning.**
  The art pass could move every spawn point in the level and the hash would
  not move. Nothing else checks anchor position either.
- **`route_graph_hash` is retired**, not left hashing two empty dicts. An
  empty signature is not neutral -- it reads as coverage, and its drift
  message has never been capable of firing. Nothing in the factory publishes
  a route graph; if one is wanted it belongs in `lot`'s output contract.
- **`collision` is deliberately not used.** It is a four-field report
  (`colliders: 1067`) and a count is a weak fingerprint: geometry can be
  replaced wholesale at 1067 colliders. It looks like the obvious mapping and
  it is the wrong one.

AND THEN IT BLOCKED THE EXPORT ANYWAY, WHICH IS THE ENTRY

The selftest passed 29 of 29 and the unit suite passed. Then the export
printed the schema warning and stopped:

    export blocked by functional regression:
    <nothing>

`drift` was empty, exactly as designed. `passed` was False -- also as
designed, because nothing was compared -- and `cmd_export` reads
`passed` as the block signal. So a version bump blocked every export,
which is the outcome `docs/FUNCTIONAL_LOCK.md` argued against in those
words, and which the paragraph below repeats. The doc and the code
disagreed and the doc was right.

Reasoning carefully about one field and then routing the same failure
through another is a new variant of a pattern this factory has now hit
four times in two days. The fix is shaped to stop it: the decision is a
named predicate, `blocks_export(result)`, living beside the result it
reads, so a test can exercise the actual decision instead of asserting
that a line of source contains a substring.

The empty reason was a second defect. `export blocked by functional
regression:` printed its header unconditionally and its detail from a
loop over `drift`, so any blocking condition that is not a drift entry
produced a bare header. It now names its reason or says it has none and
calls that a bug in level_factory.

An export against a stale lock proceeds with a warning. The lock is
regenerable, the skew is this release's own doing, and refusing to ship
a level because a hash format changed is how a gate gets deleted.

SCHEMA v0.2, AND A MISMATCH IS NOT DRIFT

The signatures change definition, so an old lock and a new one are not
comparable; diffing them reports every field as drift, for every mission,
immediately. That is version skew. `verify_no_drift` now returns
`needs_recompute` with the comparison SKIPPED, `passed` False and `drift`
empty -- a comparison that did not happen did not pass, and calling it drift
would block every export on a version bump and teach the next reader that
drift means nothing.

THE DELI BACKFILL STAYS AND IS NOW VISIBLE

`stair_systems`, `ladders`, `platforms`, `fire_escapes` still come from Deli.
That was never wrong. What was wrong is that it silently propped up a
signature carrying nothing else, which is why the whole thing looked healthy
for months. `coverage.backfilled_from_deli` names them now.

NOT DONE HERE

`LOCK_COVERAGE_ENFORCED` stays False. The order the doc sets is: land the
mapping, recompute a real lock, confirm `guards_no_site` is false, then flip
and name the mission that earned it. Recomputing `lot_demo_001` needs
`approve --gate functional_shell_locked`, which resolves job paths through
the `seed_XXXX` marker -- so the marker has to be repaired first. That is the
next patch.

Whether Lot's `vertical_links` need splitting by `kind` is open: all four are
`hatch`, which is too small a sample to decide.

## [0.28.0] - the lock says what it is guarding

`tools/probe_selection_drift.py` established that every functional lock this
factory has written protects nothing: `site.site.gameplay.json` publishes
twenty top-level keys and none of the eleven `_merged_gameplay` reads. Lot and
Deli name the same concepts differently and the extraction is written in
Deli's vocabulary.

THIS IS NOT THAT FIX. Mapping the two vocabularies is a contract question
between two tool repos, and the obvious-looking pairs -- `collision` ->
`collision_hulls`, `openings` -> `doorways`, `vertical_links` -> ladders and
stairs, `markers`/`site_markers` -> anchors -- have not been opened and
checked. A guessed mapping gives a lock that hashes real data and still
protects the wrong thing, which is harder to notice than one that hashes
nothing.

This is the reason nobody noticed for months.

- **`compute_lock` now measures what it is protecting, every time**, and
  stores it in the lock as `coverage`: which signatures have no content at
  all, which protected keys the SITE supplied, and -- the field that would
  have found this years earlier -- `site_publishes_unread`, the site's own
  keys that nothing here reads. The vocabulary gap, written beside the
  hashes.
- **`PROTECTED_KEYS` is now one list.** The coverage report reads the same
  names the three signatures hash, so it cannot drift away from them.
- **`verify_no_drift` carries `vacuous_lock` through to
  `RegressionResult`** -- not folded into `drift`, because a vacuous lock is
  not drift and reporting it as drift would block exports on a defect in the
  lock.
- **`cmd_export` warns when the regression check PASSES against a lock that
  protects nothing.** That is the moment a human is told something reassuring
  and false; the failing path already speaks for itself.
- **The warning has two conditions, because `vacuous` was not the one
  that is true here.** `vacuous` means all three signatures are empty;
  Deli's two `stair_systems` keep `collision_fingerprint` non-empty, so
  a lock guarding no site data at all still reads as partly alive. The
  condition that describes every lock in this factory is
  `guards_no_site`: no protected key came from the site. Found by
  running the report against the real key shape, after this correction
  had already been written to fix the previous miss.
- **Coverage is measured by `verify_no_drift` from the files it is
  handed, not read off the lock.** The first cut of this release read
  `lock.coverage`, which only exists on locks written by 0.28.0 or
  later -- so on every lock that exists today it was empty, and the
  warning this release was built to produce could not fire. It was
  caught by running the export, not by the selftest, which had asserted
  the broken behaviour as though it were a virtue: "absence is not a
  claim" is right about a stored report and wrong here, because the
  evidence was never absent. Both gameplay files are open in
  `verify_no_drift`, which already merges them to compute the
  signatures it compares.
- **`RegressionResult.coverage` and `lock.coverage` answer different
  questions** -- what this comparison protected, versus what the lock
  protected when it was written -- and are deliberately not merged. If
  they disagree, the site's shape changed between locking and checking.
- **Old locks load unchanged.** `from_dict` filters to known fields, so a
  pre-0.28.0 lock arrives with no coverage rather than failing -- and an
  absent report is not a claim that the lock was covered.

LOCK_COVERAGE_ENFORCED IS False, WHICH IS THE PRECEDENT AND NOT A DODGE

`export.py`'s `CLOSURE_ENFORCED` was False for the same reason, in its own
words: no export had ever been scanned at that point, the first run that did
found the current one broken, and promoting on day one would have failed
every export before anyone had looked at one. Every lock here is vacuous
today; enforcing would refuse `approve --gate functional_shell_locked` for
every mission, including ones whose art pass is already running.

The measurement ALWAYS runs and ALWAYS lands in the lock file. The flag
decides only whether it stops the gate. Flip it once a mapping exists and one
real mission produces a non-vacuous lock -- and name that mission in the
comment, the way this one names its reason.

THE SECOND DEFECT, AND THE ORDERING BUG INSIDE IT

`cmd_approve` wrote `--candidate` to `<mission>.selected` verbatim, which is
how `lot_demo_001.candidate.seed_XXXX` became the selected candidate for a
day. The shape is now checked and a bad one refused.

Refused BEFORE the approval is recorded, which it was not: `store.record` ran
first, so a rejected candidate would still have left an approved
`candidate_selected` gate behind it. Nothing had exercised that path because
nothing here had ever refused anything.

Job existence is warned about, not refused -- whether `lot_assemble` has run
when a candidate is selected is an ordering question this has no business
deciding.

NOT DONE HERE

The vocabulary mapping, which is the actual repair. The marker on disk:
`workspaces/lot-demo-ws/.level_factory/approvals/lot_demo_001.selected` still
says `seed_XXXX` while the lock beside it says `seed_5219`; that is data, and
this does not rewrite data. `_selected_lot_out` still resolves jobs from the
marker, so `graybox_dir` is still a dead path for that mission.

## [0.27.0] - the archive says which level it is

Stage 1b of `docs/EXPORT_NAMING.md`. 0.26.0 landed the build directory; this
lands the archive name, the stable folder inside it, and `LF_MANIFEST.json`.

CORRECTED BEFORE COMMIT, AND THE CORRECTION IS THE INTERESTING PART

The selftest passed 40 of 40 and the real export ran green. Then the
archive was opened and `LF_MANIFEST.json` -- the file whose whole job is
telling a recipient what they hold -- was wrong about two fields. Neither
check would ever have caught it: both asserted that the plumbing carried
what it was handed, and both times it did. What was handed in was wrong.

    "candidate": "lot_demo_001.candidate.seed_XXXX"
    "tools": { "deli_counter": "0.2.0", "lot": "0.4.0" }

`tools` was the ADAPTER versions. `export_mission` is handed
`_adapter_versions()` -- the version of the code that DRIVES each tool --
and that is correct for `build_license_manifest`, which is what the
parameter was added for. Putting it under a key named `tools` shipped
`lot: 0.4.0` to a reader asking what built their level, when lot is
0.41.0. That is the same defect factory-v1.17.0 was spent on: a number
under a label naming something else. `tools` is now the pinned set from
`factory.manifest.json` -- the set `factory_tag` recovers, and therefore
the only one consistent with the two fields beside it -- and the adapter
versions keep their place under `adapters`, labelled for what they are.

`candidate` came from `.selected`, which holds the literal string
`lot_demo_001.candidate.seed_XXXX`. `cmd_approve` writes `--candidate`
to that file verbatim and nothing checks it; someone approved the gate
with a doc's placeholder. The functional lock has the real answer, and
the manifest now reads the lock first -- the same precedence the seed
already used, which is the only reason `"seed": 5219` was right in the
same file where `candidate` was not. When the two disagree, `cmd_export`
now prints both to stderr instead of picking one quietly.

AND THE FIX FOR THAT SHIPPED A NameError, WHICH IS WORTH RECORDING.

The first draft of the correction rewrote only `_factory_pin`'s return
statement and referred to a `data` the lines above never bind. It
compiled, applied, and passed a selftest of seventeen checks -- all of
which read STRINGS out of the patched file rather than calling the
function. The first real export died with `name 'data' is not defined`
after the manifest work had already run. The same edit left the
`except` branch returning a 2-tuple into a 3-way unpack, reachable only
on an unreadable manifest, which no check would have reached either.
The selftest now calls `_factory_pin` against this checkout and against
a deliberately corrupt manifest. A helper that resolves something from
disk is exercised against disk, or it is not tested.

STILL WRONG, NOT FIXED HERE. `_selected_lot_out` builds a job path from
that same marker, so `graybox_dir` points at
`lot_assemble.candidate.seed_XXXX/out`, which does not exist -- the
export has been succeeding on the Dispatch handoff alone. The same
function feeds the post-art regression check a `site.site.gameplay.json`
that is not there. Whether that check still compares anything real
depends on what the site file contributes to signatures
`_merged_gameplay` otherwise fills from the Deli side, and that has not
been measured. Changing which job directory an export reads from does
not belong in a patch about filenames, and a gate should not be called
vacuous without running it.

    LF_lot_demo_001_s5219_20260814T203226Z_f1.18.0_portable-godot.zip
    LF_lot_demo_001/            the folder inside, stable across exports
    LF_MANIFEST.json            the first file inside that folder

- **`export_mission` gains five keyword-only parameters, all defaulting to
  `None`** -- seed, candidate_id, factory_version, factory_tag, built_utc.
  Defaulting is not laziness: `tests/unit/test_closure_export.py` calls this
  with the old argument set, and a required parameter would fail the unit
  suite on a patch about filenames. It also decides what a caller with
  nothing to pass gets, which is the part that matters.
- **An unknown part is written `NA`, never omitted.** `LF_m1_sNA_<utc>_fNA_
  portable-godot.zip`. Dropping it would give one artifact two grammars, and
  the doc's argument for the timestamp -- "fixed width, so it sorts" -- stops
  holding the moment a field before it can vanish. `fNA` is also a true
  statement: no factory tag pins that build.
- **The seed comes from the functional lock first**, the selection marker
  second. The lock is the approved, drift-checked record of which candidate
  ships. `cmd_export` resolves it; `export_mission` never goes looking.
- **The factory version is resolved in the CLI by walking up for
  `factory.manifest.json`**, and passed down. A tool that reached up into the
  factory checkout to discover what it is would be code at the factory level
  wearing a tool's directory name.
- **The archive name is composed once, at build time**, hung on
  `ExportResult`, and used by `zip_export`. That is what lets
  `LF_MANIFEST.json` state `archive_name` and be right: the manifest is
  written before the archive exists, so a second composition of that string
  is a chance for the file inside to disagree with the file containing it.
- **The folder inside the archive is not the build directory.** The build dir
  carries the profile so two profiles coexist in one workspace; the dropped
  folder must not change between exports or every `res://` path a recipient
  integrated moves. `zip_export` rewrites the arcname prefix; the bytes are
  identical.

THE CONTENT IS STILL DETERMINISTIC; THE NAME IS NOT

Entries are still sorted and timestamps still fixed at 1980-01-01, so the
same inputs still produce the same archive bytes.
`test_export_zip_is_deterministic` asserts existence and suffix, not the
name, and stays green. But the PATH now carries a build time by design --
two exports of one mission from different weeks must not look alike -- so
"deterministic" in that test's title now means something narrower than it
did, and this says so rather than letting a reader find out.

WHAT LF_MANIFEST.json REFUSES TO CLAIM

The doc's example shows `verified: {portability: PASS}`. A build-time
manifest cannot say that: `portability-test` runs afterwards, as a separate
command, and at the moment the file is written the answer does not exist. So
`verified` carries `export_closure` -- the one check that ran inside this
build -- names portability under `not_run`, and carries a note that
pipeline-stage results are not visible from here and their absence is not a
claim they were skipped. A block listing only passes invites the reader to
assume the rest.

`spec_sha256` IS DELIBERATELY NOT IMPLEMENTED

The doc names one field. `FunctionalLock` carries two hashes -- deli and lot
-- answering different questions: what the shell generator was told, and what
the assembler was told. Collapsing them into one field named for neither is
the kind of decision that looks like an implementation detail and reads as a
fact later. Left out, and the doc should name the field before anything
writes it.

NOT DONE HERE

Stage 2, the interior renames (`lot/<building>/` -> `sites/<building>/`,
dropping `assets/lot.glb`), which move `res://` paths inside the package and
want their own portability run. `portability-test` does not update
`LF_MANIFEST.json` afterwards -- it could, and then the build directory's
copy would carry a verdict the archive's copy does not. `HANDOFF.md` still
opens with its original 437 bytes; the doc says it should lead with these
same facts for the human who opens it first.

## [0.26.0] - the export name has one home

`docs/EXPORT_NAMING.md`, accepted 2026-08-14, specifies three names for an
export. Before writing any of them, the grammar was measured: it is composed
in five places.

    export.py       out_root / f"{mission_id}.{profile.mode}"
    export.py       zip_path = result.export_dir.with_suffix(".zip")
    commands        f"{mission_id}.portable-godot"      hardcoded, in cmd_walk
    commands        export_root / f"{mission_id}.{mode}"
    commands        f"{mission_id}.{mode}.portability.json"

- **`ids.export_build_dir_name`** is now the only definition. It lives beside
  `candidate_id` and `job_id` because those already own the rule that an id
  becoming a directory is refused rather than sanitised, and this is the same
  rule for the same reason.
- **The build dir keeps the profile**, and the docstring says why: the
  workspace holds `portable-godot` and `pure-shell` at once, so one stable
  name would have the second export overwrite the first. The folder a
  recipient drops in has the opposite requirement — it must not change between
  exports or their `res://` paths move — which is why the doc specifies three
  names and not two. That correction came from reading `export.py:232`; the
  first draft of the doc had two and was wrong.
- **The archive stops losing its profile, and that needed no plumbing.**
  `with_suffix(".zip")` treats `.portable-godot` as a file extension and
  replaces it. That is the entire reason the archive was `lot_demo_001.zip`.
  Appending instead of substituting gives
  `LF_lot_demo_001.portable-godot.zip`.
- **`cmd_walk` stops hardcoding the profile** four lines after setting it. It
  was right, and it would have gone on looking in the same place if the
  default above it had ever changed.

- **The import merged into the line that was already there.**
  `commands/__init__.py` has imported `slugify` from `packages.core.ids`
  since before this work started. The patch's first draft assumed it imported
  nothing from there and was going to insert a second import line. It refused
  and named the file instead of writing one, which is the guard doing its
  job -- recorded because the near-miss is the useful part, not the fix.

Renames on disk: `lot_demo_001.portable-godot/` becomes
`LF_lot_demo_001.portable-godot/`, and the `.portability.json` beside it
follows. Existing export directories are not migrated — they are regenerable
output under `.level_factory/`.

NOT DONE HERE, AND NAMED SO IT IS NOT MISTAKEN FOR DONE: the full archive
name (`LF_<mission>_s<seed>_<utc>_f<factory>_<profile>.zip`) needs the seed,
the build time and the factory version plumbed to `export_mission`, which
changes its signature; `LF_MANIFEST.json` and repacking the archive under a
stable `LF_<mission>/` come with them. The interior renames
(`lot/<building>/` -> `sites/<building>/`, dropping `assets/lot.glb`) change
`res://` paths inside the package and want their own portability run.

`cmd_portability_test` composes one of the five names and is updated here, so
its pass has to be re-earned by a real run rather than assumed.

## [0.25.0] - the CHANGELOG is the third number, and now it is read

0.24.0 taught `verify-manifest` to notice a pin matching a stale VERSION, and
closed by naming what it still could not see:

    KNOWN AND NOT ADDRESSED HERE: the CHANGELOG is a third number this does
    not read. `lot`'s CHANGELOG documents 0.41.0 while its VERSION says
    0.33.0 and the manifest pins 0.32.0 -- three answers to one question, and
    this check compares two of them.

On 2026-08-14 finding that out cost twenty staged files and a person reading
them. The check said `lot` was STALE, which was true and the least
interesting true thing about it. `zoo` was worse and entirely invisible: it
had shipped 0.32.0 with no entry for it, and its CHANGELOG carried the number
0.31.0 twice -- once above the document's own title.

- **Two statuses, not one.** `UNRELEASED` is the CHANGELOG ahead of VERSION:
  entries for releases the tool never claimed to be. `UNDOCUMENTED` is
  VERSION ahead of the CHANGELOG: a release with no entry. They want opposite
  fixes -- bump the version, or write the entry -- and one status could not
  say which.
- **Checked first, and not only from OK.** STALE escalates only from OK on
  the argument that DRIFT's message is more useful when the numbers already
  disagree. `lot` refutes that: it was DRIFT, and DRIFT says "re-run the
  smoke and re-certify", which would have pinned 0.33.0 -- wrong by eight
  releases. A tool that does not know its own version cannot be pinned by
  anyone, so it outranks a pin being behind. `_SEVERITY` gains two ranks
  between DRIFT and INCOMPATIBLE.
- **`newest_changelog_entry` reads both heading shapes in use.** `patina`
  writes `## [0.19.0] - ...`, `dispatch` writes `## v0.3.0 - ...`, `pipeline`
  writes `## [v0.1.0] - ...`. The first cut of this reader took only the
  bracketed form and reported `dispatch` -- in perfect agreement with itself
  -- as disagreeing. An instrument that misreads the record is precisely the
  failure this module exists to catch, so the bug is recorded rather than
  quietly fixed.
- **Newest means FIRST, not highest.** These files are written newest-first
  and the top entry is the claim being made. Taking the maximum would have
  hidden `zoo`, whose stray entry sat above the title carrying a number
  already used below it.
- **No CHANGELOG means no opinion.** `laser_tag` is an addon directory
  holding VERSION and `addons/`. A missing file yields None and the tool is
  judged on the two numbers it has, the same way a missing version degrades
  to UNKNOWN rather than to a false OK.
- **`cli/commands`:** both statuses exit EXIT_FINDINGS, or EXIT_CONFIG under
  `--strict`.

Against the factory as of factory-v1.16.0 this reports nine tools OK and one
UNDOCUMENTED: `pipeline`, whose VERSION says 0.5.0 while its newest entry is
v0.1.0 -- four releases with no entry. That one is real and still open.

Worth noting which status that is, because the first draft of this entry said
UNRELEASED and its own selftest refuted it. `pipeline` has releases with no
entries, not entries with no release; the CHANGELOG is BEHIND. Two statuses
exist precisely so that distinction cannot be waved at, and it caught the
person who wrote them within a minute of their existing.

## [0.24.0] - A pin that matches a stale VERSION is not a pass

`verify-manifest` compared the manifest's pin against each tool's VERSION
file and stopped there. On 2026-08-14 that reported:

    OK  deli_counter    0.88.0 matches certified 0.88.0
    OK  level_factory   0.22.0 matches certified 0.22.0

while both tools had nineteen days of commits newer than the VERSION naming
them. Two numbers agreeing with each other, and with nothing on disk. The
same failure `deli_counter/build_freshness.py` exists for, and the same one
that made every recorded Laser Tag grade describe a draw that never shipped
-- this time in the check whose entire job is catching drift.

- **`packages/tools/contracts.py`:** new `STALE` status, ranked between
  UNKNOWN and DRIFT. Reached only from what would have been a bare OK: if
  the numbers already disagree the staleness question is moot and DRIFT's
  message is the more useful one. `ContractResult` carries
  `stale_because`, the file that outran VERSION, because naming it is the
  difference between a verdict and a place to look.
- **`stale_source()` asks git, not the filesystem.** The first cut compared
  mtimes and reported six of ten tools stale, every one naming
  `.gitignore`. Excluding `.gitignore` would only have moved the problem to
  the next non-source file -- an exclusion list always trails what gets
  added. History is the allow-list that cannot fall behind, and it is
  immune to fresh clones, which rewrite every mtime and no commit dates.
  Unknowable answers (no git, not a repo, no commit touching VERSION)
  report OK; a warning nobody can act on is worse than silence.
- **`cli/commands`:** STALE exits EXIT_FINDINGS, or EXIT_CONFIG under
  `--strict`, matching DRIFT. It wants the same thing doing.

First run against the real factory: 1 OK, 4 DRIFT, 5 STALE, where the
previous check said 8 OK and 2 DRIFT. Eight of ten tools had moved since
their versions were written and nothing was saying so.

KNOWN AND NOT ADDRESSED HERE: the CHANGELOG is a third number this does not
read. `lot`'s CHANGELOG documents 0.41.0 while its VERSION says 0.33.0 and
the manifest pins 0.32.0 -- three answers to one question, and this check
compares two of them.

## [0.23.0] - A blocked candidate is not a blocked mission

- **validation/model.py:** `aggregate()` takes `eliminated_candidates` and
  partitions blockers into `blocking_open` and `blocking_eliminated`;
  `has_blockers` follows `blocking_open` as it always did. The scheduler has
  scoped candidate failures for a while -- a candidate-scoped failure
  eliminates that candidate and the run carries on -- but the reporting never
  followed. Measured 2026-08-12 on lot_demo_001: one candidate's
  `dispatch_handoff` exited 1, all three candidates built, `blocked_job` was
  never set, and the summary still read "Blocked: unresolved blocking
  issues". The run that continued reported as the run that halted.
  Opt-in: the default is an empty set and every issue lands in
  `blocking_open` exactly as before, so `cmd_validate` and both suites are
  byte-identical.
- **cli/commands:** `cmd_run` passes the eliminated set and prints the
  eliminations. `cmd_batch_run` had printed them for a while; on a
  single-mission run the reason the mission survived was invisible.
- Findings are partitioned, never dropped: `total` still counts a blocker on
  a discarded candidate, because it is still a real finding about a real
  defect -- it is just not the mission's to answer for.

Downstream of this: `lot_demo_001` was re-run on the art layer and its three
candidates graded 40 / 55 / 60. SESSION_0811 concluded Laser Tag's score was a
step function stuck on a plateau, from five evaluations that all returned 45 --
but those were grading the greybox draw while the themed draw shipped. Grading
what ships, the score separates the candidates. The plateau was an artifact of
grading the wrong geometry.

## [0.22.0] - a candidate that fails is eliminated, not fatal

Five candidates are generated so the weak ones can be dropped. Mission-wide
fail-fast defeated exactly that: the first blocked job halted the whole DAG, so
a candidate was never eliminated -- it took its siblings down with it, their
jobs never dispatched, and their stable `out/` directories kept the previous
run's artifacts where the next reader mistook them for current answers. A Laser
Tag finding on seed 5320 is how seed 5320's own walktest came to be skipped for
an evening and read as a passing geometry check.

`Job.candidate_id` already carried the distinction; the scheduler was not using
it. A candidate-scoped failure now records the candidate in
`RunSummary.eliminated_candidates` and lets every other candidate finish. A
mission-level failure still stops the run and drains what is in flight, because
nothing downstream of one can be salvaged by carrying on.

Dependents needed no special handling: `ready` is only appended when a
dependency SUCCEEDS, so anything downstream of a failed job never becomes ready.
What was missing was saying so. `RunSummary.not_run_reason` gives every
un-dispatched job its sentence -- "candidate X was eliminated at Y", "the run
stopped at Z", "a dependency did not succeed" -- because the list alone reads as
five things going wrong on a run where four candidates built cleanly and one was
correctly dropped.

This is the precondition for WALKTEST_ENFORCED. Flipping it before this would
have turned one flawed candidate into a dead mission.

## [0.21.0] - the stuck finding carries the contact

`WALKTEST_WALKER_STUCK` named a walker, a target index and a coordinate. Lot
0.38.0's director now records what the capsule was pressing against and which
waypoint it was steering to, so the finding says it: "pressing against
gaming_tables_col; 5.6 m from waypoint 3/9 at (26.0, 0.2, -2.0)".

An empty contact list reads differently on purpose -- "touching NOTHING -- the
geometry did not block it, the steering froze, and that is this tool's defect
rather than the level's". A finding that cannot tell those apart sends a reader
to fix the wrong repo, and older reports that carry neither field still report
exactly as before.

## [0.20.0] - a firefight was gating the walktest, and the walktest never ran

`LT_ROUTE_NEVER_COMPLETED` blocked when Laser Tag played the full clock and the
bot never finished the route. The reasoning in `lasertag_report.py` was right
when it was written -- "the crew was given the full clock, nobody killed them,
and they still never reached the objective" is a measurement, not a score -- and
one fact has changed since: `walktest_navqa` measures the same claim directly,
on every candidate, with no combat in it.

Laser Tag's route number is confounded, and seed 5320's report shows all three
confounds at once: 835 player-stuck events, six of twenty-five runs ending in a
team wipe, and a 180 s clock. The finding keeps its category and stops blocking;
its message now points at the walktest as the authority.

The ordering was worse than the imprecision. The scheduler fail-fasts on the
first blocked job, so a candidate whose Laser Tag blocked never dispatched its
own `walktest_navqa` -- the coarse instrument silenced the precise one. Seed 5320
spent an evening looking like a geometry failure it does not have, because its
`out/` still held a report from seven hours earlier and nothing distinguishes
"never ran" from "ran and passed" once you are reading the artifact.

So `RunSummary` grows `never_dispatched`, `cmd_run` prints it, and the `run()`
docstring stops claiming "Every job is dispatched" -- a sentence 0.14.0 left
behind when it removed the resume pre-skip, and one fail-fast has always made
false.

All five category5_baie_dore_001 candidates now walk: 0 of 31 legs failing on
every one, 0 stranded anchors, 0 anchors without standing room. Seed 5421 had
never been walktested at all.

## [0.19.0] - the one pass that is a substitution says so

`WALKTEST_ANCHOR_BEHIND_BARRIER`, minor and never blocking. Lot 0.37.0's
director resolves an anchor whose nearest standing room is unreachable to the
nearest connected one instead -- for the vault, the floor outside a reinforceable
concrete breach panel. The leg then passes, and it passes over a substitution,
which is the one thing this stack has been bitten by often enough to warrant a
finding of its own. The message carries both distances.

It fires instead of `WALKTEST_ANCHOR_ISOLATED`, not alongside it: after the
resolution the anchor is on the main cluster by construction, and reporting both
would tell the reader the same anchor is fine and broken.

## [0.18.1] - a finding must not be able to kill the run that produced it

`WALKTEST_MARKER_BURIED` passed `location=report` -- the `Path` -- where the
other seven findings pass an f-string. It fires only when a buried marker
exists, so it first fired on the run that proved the anchor fix, and the run
died with `Object of type WindowsPath is not JSON serializable` after three of
four seeds had already spent 200 s each on their walker sims.

`_finding` now calls `str()` on `location` rather than trusting its own
annotation, and a test serializes the findings from every payload in the suite.
Every test in that file asserted codes and messages; not one had ever written
the result out, which is the only thing the pipeline does with it.

## [0.18.0] - a room that did not bake is not an anchor that drifted

`WALKTEST_ANCHOR_ISOLATED` says an anchor stands somewhere real and connects to
nothing. Lot 0.36.0's director can now report something different: it searched
the anchor's own storey for anywhere a body fits and found nowhere at all. That
is a room that produced no navmesh, and it sends a reader to different geometry
than a placement defect does, so it gets its own code --
`WALKTEST_ANCHOR_NO_FLOOR`. Like the isolated finding, it suppresses the legs it
poisons, because a leg into a floorless room is that fact restated.

`WALKTEST_MARKER_BURIED` is the other half. `LOOT_VAULT_CASH` sits at the centre
of an 8 x 6 m vault block, so the nearest place a body fits is 3 m away; the
route is fine and the marker is inside the furniture. The old proximity test
failed this as an off-mesh anchor, which blamed the navmesh for where a marker
was put. It is now one `minor` line naming the markers, and it does not become a
blocker when `WALKTEST_ENFORCED` flips -- enforcement is about navigability, and
a marker a player reaches from three metres away is a content note.

`_finding` grows a `severity` override for exactly that case, and a finding that
overrides its severity never sets `blocking`.

## [0.17.0] - off the network, not merely far from it

`WALKTEST_ANCHOR_ISOLATED` fired on `reaches == 0` and found nothing on a site
where sixteen of twenty-one anchors were off the main network. Lot emits four
duplicate marker pairs per site, so each stranded anchor still reached its own
twin and passed the threshold.

Lot 0.27.0's report carries `cluster_size` and `main_cluster_size`, so the
finding now asks whether an anchor is on the LARGEST cluster rather than whether
it can see anybody at all, and says "on a cluster of 2 while the main one has 5"
instead of a count. Where the director names a `coincident_with` partner, the
message says the two are one anchor emitted twice -- that is the reason the old
threshold missed them and it belongs in the finding rather than in a commit
message.

A report from an older director carries no clusters and falls back to the
`reaches` threshold, so nothing goes quiet; the fallback is documented as the
threshold that under-reported rather than as an equivalent.

## [0.16.0] - WALKTEST_ANCHOR_ISOLATED

Lot 0.26.0's nav QA report carries an `anchors` array saying, per anchor, how
many other anchors it can reach. Zero means it snapped onto a navmesh fragment:
on the mesh by every distance check, and unable to appear in any route.

`WALKTEST_ANCHOR_ISOLATED` (category `anchor`) reports each one with where it
snapped, how far it moved, and how many anchors it failed to reach. Its
suggested fix says the thing that took a day to establish: fix where the anchor
is placed, not the navmesh.

Legs the director blamed on a stranded anchor -- `isolated_endpoint` set -- no
longer emit `WALKTEST_LEG_UNPATHABLE` as well. One defect, one finding.
Otherwise the count grows with the size of the leg graph and every extra entry
points the reader at routing. The suppression is deliberately narrow: it applies
only where the director itself attributed the failure, so a route blocked
between two healthy anchors still fails as before, and a report written by an
older director with no `anchors` array behaves exactly as it did.

Four tests cover the four cases that matter: the anchor is reported, its legs
are not double-reported, a genuinely blocked leg still is, and an old report
does not go quiet.

## [0.15.0] - navigability answered by walking

Every navigation conclusion this pipeline had drawn was inferred from a Laser
Tag firefight. Nineteen timeouts on seed 5219 is not an answer to "is the route
pathable?"; it is a symptom with several possible causes, arrived at through an
instrument confounded by combat. The planner's own docstring said the graybox
base was "DC greybox+collision assembled by Lot, with Laser Tag nav QA", which
is how a firefight became the only evidence for a claim about geometry.

`walktest.py` and the `heist_nav_qa` director have shipped with Lot the whole
time. They bake the navmesh, prove a path along the mission spine leg by leg,
then spawn physical walkers and drive them. No enemies, no weapons, no scoring.
On seed 5219 this says in one run whether the route is pathable.

### the stage

`walktest_navqa`, one job per candidate, `depends_on=[lot]` -- a SIBLING of the
Laser Tag job, not a dependent. Nothing about a firefight is an input to "can a
body walk this", and chaining them would serialise two long headless Godot runs
that can share the `godot_headless` cap instead.

`adapters/walktest/` stages a throwaway project the way the Laser Tag adapter
does, outside `work_dir` so the project's copies of the building GLBs are not
collected as this job's outputs and cached twice, then runs Lot's runner against
it. `probe()` points at the Lot checkout: there is no walktest repository, and
left to the default the adapter would report unavailable and contribute no tool
version, so the fingerprint would forget which Lot ran the QA. The director's
sources are hashed into `fingerprint_inputs` for the same reason the Laser Tag
addon is -- Lot's VERSION moves for reasons unrelated to the nav QA scripts, and
the scripts change without Lot's VERSION moving.

### the flag nothing had ever set

`LotAdapter` has supported `--navqa` since it was written, and no job spec had
ever passed it, so `<stem>_navqa.tscn` was never emitted. The `lot` branch of
the job-spec builder now sets `navqa=True`, and the Lot adapter adds the navqa
scene to its expected outputs when the flag is on -- otherwise its absence is
discovered one stage downstream, by walktest failing its own pre-flight, rather
than by the tool that was asked to write it.

### two ways a nav check can be silent, and neither is allowed

`walktest.py` treats a missing Godot 4 binary as a SKIP and returns 0 without
writing a report. That is right for a hand-run and catastrophic for a pipeline
stage: a navigation check that never happened, reported as success -- the exact
defect 0.14.0 removed from the scheduler, offered back through a runner flag.
The adapter passes `--require`, so the run fails, no report is written, and the
output contract fails the job for the honest reason.

The other silence is a report that says `ok=false` and itemises nothing.
Anything counting findings reads that as a pass, so it gets its own code,
`WALKTEST_FAILED_WITHOUT_DETAIL`, rather than an empty list.

### findings that will block, but not yet

Laser Tag grades a map and never refuses one, because the combat model it
measures belongs to the consumer. Navigability is not like that: reachability
and closure are exactly what this stack certifies about the asset it ships. A
site whose objective cannot be reached is broken output, not a design note.

So the findings are built to block, behind `WALKTEST_ENFORCED`, currently False.
The existing library has never been checked this way and promoting on day one
would fail missions wholesale before anyone has looked at one. This is the same
rollout `deli_counter.stairwell.CONTAINMENT_ENFORCED` uses: warn while the
library is remediated, flip the flag once it is clean. The finding itself --
code, message, location -- is identical either way, so the flag changes what
happens to a bad site and never whether it is noticed.

Codes: `WALKTEST_LEG_UNPATHABLE` (reachability, names the leg and the director's
detail), `WALKTEST_WALKER_STUCK` (traversal, carries the coordinates the
director records for a walker that ran out the clock), `WALKTEST_NAVMESH_EMPTY`
and `WALKTEST_NO_SPAWNS` (the director's early-outs -- "there was nothing to
walk on" is a different failure with a different fix than "the route is
blocked"), `WALKTEST_FAILED_WITHOUT_DETAIL`, `WALKTEST_REPORT_UNREADABLE`.

Requires Lot 0.25.0 for `--report-dir`.

## [0.14.1] - laser_tag stops reporting UNKNOWN, for a boring reason

`verify-manifest` had said `no comparable version (certified=None,
installed=None) -- cannot verify this tool` about Laser Tag since the manifest
was written, and the manifest explained it as a property of the tool: "Godot
addon exposes no version string; unpinned". That was never true. The addon
declared `version="0.7.3"` in `addons/laser_tag_tool/plugin.cfg` the whole time.

`contracts.installed_factory_versions` reads `<factory_root>/<path>/VERSION` and
nothing else, and `BaseAdapter._read_tool_version` also looks there first. The
repo simply had no root `VERSION` file, so both layers looked in the one place
the version was not. Every other tool repo has one, including pixelcoat, whose
real version lives in `version.py` and whose root `VERSION` is a mirror.

Laser Tag now carries `VERSION` at 0.8.0 and no adapter code changed: `probe()`
picks it up through the inherited helper. That is worth a test precisely because
nothing in the adapter guards it -- `test_laser_tag_reports_a_version_now`, plus
a companion asserting an empty repo still degrades to UNKNOWN rather than
inheriting the grounded pin. A missing version has to look different from a
matching one.

### what still does the real work

The addon-source hashing in `fingerprint_inputs` stays, and its comment now says
why rather than describing a gap that is closed. A version string only moves
when somebody remembers to move it; the question a build fingerprint asks is
whether the CODE changed. A tool edited without a bump is exactly the case a
version cannot see and a hash cannot miss. The version is for humans reading a
receipt and for the lockstep check. The hash is what keeps a stale grade from
being served.

The two files that now carry the version are mirrors, and a mirror nobody
enforces drifts -- see the Lot version disagreement this repo has carried as a
known wart for weeks. The lasertag repo's `lint` job gains a step that fails
with "VERSION says X, plugin.cfg says Y" if they diverge, in the repo that owns
both files.

### GROUNDED

`laser_tag` moves from `{"version": None, "source": None}` to 0.8.0 from
`VERSION`. 0.8.0 rather than 0.7.3 because the addon changed behaviour on the
same day it got a version: the physics-frame clock in `LT_RunState`, two new
published metrics in `LT_MetricsCollector`, different inputs to pacing and
exposure in `LT_ScoreCalculator`, and a reachability bound on the bot's
cover-seek.

## [0.14.0] - a run that reports a grade has looked at one

`--art` printed `Structural checks passed (blockers open: 0, total findings: 0)`
over a mission whose reports on disk held six findings each, a FAIL on
`TRAVERSAL` among them. Nothing was corrupt and nothing had crashed. The run
simply never looked.

### the resume pre-skip is gone

`Scheduler.run` opened by reading every job's status out of the index and, for
any it found already succeeded, marking it complete without dispatching it. The
`JobOutcome` it fabricated took the default `issues=[]`. A pre-skipped job never
reached `_attempt_job`, so `_normalize` never ran over its outputs and the
findings in them were never replayed.

Nothing downstream could recover them. The index has no findings table -- jobs,
artifacts, missions, meta, and nothing else -- so a finding exists only in the
run that produced it. `cmd_run` then wrote the empty `summary.all_issues` over
`.level_factory/validation/<mission>.json` and stamped the mission `built`. The
run that failed to notice the findings also destroyed the record left by the run
that had found them.

The tell was in the stage lines, and it read as reassurance. `cache_hit` was set
only when the recorded status was literally `SKIPPED_CACHE_HIT`, so a job an
earlier run had EXECUTED came back with `cache_hit=False` and the CLI printed
`succeeded` -- a stage announcing work that did not happen. Two better-looking
hypotheses were eliminated first: the cache-hit path does replay findings, and
the execute path does carry them on the outcome. It was the third path, the one
that runs before either.

### what makes a re-run cheap now

The content cache, which was always the right mechanism for this. It is keyed on
the build fingerprint rather than on a recorded status, so it cannot be fooled by
an upstream that moved underneath a stale success -- the failure mode the old
comment here described and accepted. `_attempt_job` materialises the cached
outputs, re-runs `_normalize` over them and returns the findings, and every
successful execution publishes to it. An unchanged stage still skips its tool.
What it no longer does is report a grade it never looked at.

`--force` existed solely to opt out of the pre-skip, which means the honest
behaviour was opt-in and the default was the one that could lie. The flag is
still accepted, now changes nothing, and its help text says so.

### the test that was green the whole time

`test_force_reruns_already_succeeded_job` asserted `"a" not in executed`, and had
passed every run since the pre-skip was written. The behaviour was not an
oversight; it was specified, and the specification said a re-run may report a
grade it never looked at. A green suite confirms the code matches the intent. It
cannot tell you the intent was wrong.

That test is now `test_a_recorded_success_is_still_dispatched`, which runs the
same graph with `force` both ways and asserts the two results are identical --
the new contract stated as an equality rather than a difference. Six more in
`tests/unit/test_resume_replays_findings.py` cover the replay itself, that it
costs no tool invocation, and that a second run labels itself `cache` rather
than `succeeded`.

### still open, and named here so it is not mistaken for fixed

`cmd_run` overwrites the persisted validation file unconditionally, so a run
that evaluates nothing still overwrites what the last run found. And the index
still has nowhere to put a finding. Neither is the cause of this defect; both
are what turned it from a wrong number into a lost record.

### versions

0.14.0 rather than 0.13.5, because `run` behaves differently. It also lands
above this file's previous 0.13.19, so `VERSION`, `pyproject.toml` and the
CHANGELOG agree again without anything being rewritten.

## [0.13.19] - a firefight evaluator grades a map, it does not certify one

Every tactical thing Laser Tag's pre-flight knew how to say, it said by refusing
to build. An enemy standing too close to the crew spawn, a marker hanging three
metres over its floor, two markers with ninety-two metres of open street between
them -- all of them came back as `JOB_PREFLIGHT_REFUSED`, and all of them
describe a level that loads, bakes, plays and comes back with a mediocre score.
Trading a level somebody can put cover into for no level at all is the wrong
trade, and the finding that mattered most is not a complaint about the map. It
is a coordinate. Somebody just has to be handed it.

### the advisory channel, and why the forcing lives in the scheduler

`BaseAdapter.advise_configuration` is the companion to `validate_configuration`,
and the split between them is authority rather than subject. A refusal says the
tool cannot produce information from these inputs -- no floor, sealed
destination, no executable configured -- and spending 900 seconds of Godot would
buy a report about a match nobody played. An advisory says the tool will run
fine and mark the result down, which belongs beside the score.

`Scheduler._advise` forces every advisory non-blocking and demotes a `blocker`
severity to `major`, so an adapter cannot promote a design signal into a gate by
mislabelling it. That is an architectural rule rather than an adapter's manners,
which is why it is enforced somewhere no adapter can reach.

Two properties that only look like details until a run goes wrong:

* Advisories are collected **before** the pre-flight and prepended on every
  return path, so a refused or timed-out job still carries them. Losing them on
  the failure path would mean the only runs that never explain what is wrong
  with a map are the runs that went worst.
* They are slice-assigned rather than appended, and the transient-retry
  recursion routes through `_attempt_job` rather than `_execute_job`, so a retry
  cannot report the same finding twice.

An `advise_configuration` that raises comes back as one INFO `ADVISORY_FAILED`
finding and the build completes. Nothing on this channel is allowed to be the
reason a level does not get made, including a bug in the channel. The
`ToolAdapter` protocol is unchanged and the scheduler reaches the method by
`getattr`, so the channel is opt-in and every adapter written before it is
unaffected.

### `packages/validation/tactical.py`

Composes three sources that had never been in the same room into normalized
findings:

* `spawn_placement`'s advisory pass, now returning `(code, message)` pairs --
  `LT_OPENING_STANDOFF` and `LT_MARKER_OFF_FLOOR` are fixed by different people
  in different files, and a caller telling them apart by matching prose is
  coupled to a sentence that lasts until somebody improves it;
* `sightlines`, now splitting `(what is open, what to do about it)` so the
  coordinate reaches `ValidationIssue.suggested_fix` rather than being buried in
  the tail of a message -- `LT_OPEN_SIGHTLINE`;
* `lasertag_contract` -- `LT_ENGAGEMENT_DRIFT` when Lot's stated
  `OPENING_RANGE` stops matching the evaluator's real one, and
  `LT_ENGAGEMENT_NOT_CONFIGURABLE` because the number that decides first contact
  is an `@export` default with no field in the scenario resource anybody would
  go looking in.

The drift check is the only check in either repository that can catch those two
numbers separating, because Level Factory is the only place that can see both
checkouts at once: Lot cannot import Level Factory and Laser Tag has never heard
of Lot. `Scheduler` now passes the whole `repositories` map in the adapter
context rather than only the adapter's own, which is what makes the question
askable at all.

### the duplicate street

Writing the tests found a real defect. `spawn_placement.classify` collapses
destinations sharing a position -- Lot emits its objective a second time as
`Route_1` -- but the crew spawn is not a destination and escaped it. A
defend-style mission, objective on the crew spawn, drew every street twice at
identical lengths with identical cover proposals. That does not read as a
duplicate. It reads as a site twice as open as it is, which is the wrong number
to hand somebody deciding how much cover to build. `_one_name_per_position`
collapses them and keeps the spawn's name, because "LT_ObjectivePoint sees
Enemy_0" sends the reader looking at the objective.

428 tests, 11 skipped.

## [0.13.18] - the good news was filed as damage, and the map that nobody walked shipped clean

Three separate readings of the same Laser Tag report were wrong in three
different directions. Two of them made the report louder than the truth and one
made it quieter, and the quiet one is the one that let a level ship.

**A pass was being filed as a defect.** `LT_ScoreCalculator` emits its verdicts
into a single `findings` array and tells the good ones apart only by
`severity: "PASS"` -- the same array carries "Bot rarely completed the route
[FAIL]" and "World collision blocked 40% of shots [PASS]". `_SEVERITY` had no
`PASS` key, so `.get(..., "minor")` turned every pass into a MINOR problem with
the level. In the 56-finding run the user was reading, roughly a dozen entries
were good news wearing a problem's clothes, and one of them -- cover blocking --
was the map doing exactly what a cover-heavy map is supposed to do.

Passes now skip the issue loop entirely. They are not deleted: `passing_findings()`
returns them, `metrics()["lasertag_passes"]` counts them, and `failure_summary()`
-- which is pasted verbatim into the `LT_NOT_EVALUATED` blocker as "Laser Tag
said:" -- now quotes only the failures, so a blocker can no longer cite a pass as
a reason the map failed.

**An unrecognised severity defaulted to minor.** Same `.get()` call, other half.
A severity string this module has never seen is a report format that moved, and
the cost of the two guesses is not symmetric: guessing low buries a real defect
in the minor pile where nobody looks, guessing high is a false alarm someone
closes in a minute. `UNKNOWN_SEVERITY` is `"moderate"` now, the same asymmetry
`NAV_DERIVED_TYPES` already follows.

### the fourth state, and where TDD 5.5 actually stops

TDD 5.5 says a readiness score must never block a build, and this module has been
applying that to everything Laser Tag says. Three states had already been carved
out of it -- the evaluator never ran (blocks), it ran without navigation (blocks),
it graded the map (never blocks). The first run that got past all three produced
a fourth, and nothing was watching for it.

Seed 5320: navigation baked, 1025 polygons, 25 matches played, every number in
the report real for the first time. Route completion 0% on every seed. The build
passed with **none blocking**.

That reading of 5.5 is too broad. A *score* is a judgement -- 50/100, grade WARN,
"is this map good" -- and it stays non-blocking forever. "The crew was given the
full clock, nobody killed them, and they still never reached the objective" is
not a judgement. It is the same statement the pre-flight already blocks on when
it reads the scene text and finds the destination sealed off, arrived at by
measurement instead of by geometry, and there is no defensible reason for the
static form of a fact to block while the measured form of it ships.

The gate turns on whether a run had the *time* to prove the route walkable:

  - `LT_ROUTE_NEVER_COMPLETED` (blocker, reachability) -- completion is 0 and at
    least one run ran the full clock out. Nothing was stopping the crew walking
    except the map.
  - `LT_ROUTE_UNPROVEN` (moderate, non-blocking) -- completion is 0 but every run
    was cut short by a team wipe. That is difficulty, not geometry, and the route
    is simply untested; the finding says so rather than implying a verdict.

An absent `route_completion_rate` is never read as zero -- `route_completion_rate()`
returns `None` when the report does not say, because absent is not zero and the
whole reason this file exists is that those two kept being confused. A degraded
run raises neither, since `LT_EVALUATED_DEGRADED` already blocks and already names
the cause.

For seed 5320 -- completion 0.0, four timeouts -- the blocker fires. The next real
run is expected to *gain* a blocker rather than lose one. That is the point.

### ENEMY_PATHING joined the pathfinding demotions

`NAV_DERIVED_TYPES` lists the finding types whose numbers are meaningless without
a baked navmesh, so they are demoted rather than reported at face value.
`ENEMY_STUCK` and `PLAYER_STUCK` were on it; `ENEMY_PATHING` -- which on an
unbaked map cheerfully reports "No enemy stuck events recorded" because nothing
ever moved -- was not. It is now.

Ten tests in `tests/unit/test_lasertag_readiness.py`, built on a fixture modelled
directly on the seed 5320 report rather than an invented one.

## [0.13.17] - the pipeline was guessing how big its own buildings are

Lot 0.30.0 made the ground plate survive the spec Level Factory writes. This is
the other half: Level Factory stops writing that spec. Two numbers were made up
rather than measured, and both of them are consequences of the same fact -- how
big the shell is -- which the pipeline has been able to read all along and never
did.

**The row was not centred and the plate was.** `site_placements` anchored the
first building at the origin and marched +x, so four buildings 45 m apart ran
x 0..135 before nudges. `ground_size` returned a span from the building count and
Lot centred it on the origin. Nothing reconciled the two. The row now starts at
`-(count - 1) * spacing // 2`, which is centred for the same reason the plate is:
a reader that halves `size_x` and a reader that resolves the true extent then give
the same answer, and neither can be wrong on its own.

**The spacing was a hardcoded 45 m and the shells are 44 m wide.** With +/- 6 m of
along-axis nudge available to the variation, a candidate whose neighbours nudged
toward each other placed origins 42 m apart -- two metres of one building standing
inside the other, on every seed, since the row existed. `row_spacing()` now
derives it: the measured shell span, plus twice the nudge range, plus an 8 m
street. For the shipped 44 m shell that is 64 m rather than 45, and the closest
pair across the five real seeds sits 52 m apart -- an 8 m street, as asked.

### shell_footprint()

The extent of the shell about its own origin, in site XY metres, read out of
`shell.glb` through the existing `packages.validation.glb_collision`. Reported as
the extent *about the origin* -- twice the furthest face -- and not as the collider
bounding box, because Lot places a building by its origin: a shell modelled 30 m
off-origin needs 80 m of clearance, not 20.

It returns `None` when the geometry cannot be read, and that distinction is the
point. A shell that could not be measured is not a shell of size zero; returning
`(0, 0)` would have every downstream consumer confidently size a plate for
nothing. Callers fall back to `DEFAULT_FOOTPRINT` explicitly, which is a stated
assumption rather than a silent one. This is the same "silent emptiness" shape
that Lot 0.30.0's `_ground_tiles` clip had, caught before it could be written.

### the self-check that runs on every write

`_write_site_spec` measures the shell once, derives the spacing and the plate from
it, and then -- before the spec leaves the building -- runs
`site_variation.uncovered()` and `site_variation.overlapping()` over what it just
produced and raises if either says anything. A guardrail nobody runs is
decoration, so this one runs on the real seed, on every write, not only under
pytest.

These are deliberately the producer's own readers, distinct from Lot's
`site_extent.resolve()` and `overlap_findings()` on the far side of the gate --
the same arrangement as `glb_collision.py` and Lot's `site_collision.py`. One
shared implementation would mean a bug in it blinds the producer and the check
meant to catch the producer in the same instant. They agree because the contract
is written down: for the shipped footprint the producer's plate and Lot's derived
requirement coincide exactly at the worst-case bound, half_x 99.5 m both sides,
and all five real seeds now resolve in Lot with `extended=False` and zero
findings.

### two tests that were measuring the wrong thing

`test_the_ground_plate_covers_the_placed_row` asserted
`abs(b["at"][0]) <= span_x / 2 + 90`. The `+ 90` was added to make a real
coverage failure go green, and it checks *origins* against the plate, which is
not the claim -- a building's walls stand where its footprint reaches, not where
its origin is. It now asserts `abs(x) + reach <= span_x / 2` on both axes.

`test_buildings_never_overlap_their_neighbours` asserted `min(gaps) >= 30` while
the spacing was 45 and the shells were 44 m wide. A 30 m origin gap between 44 m
shells is fourteen metres of interpenetration; the test measured what was easy to
measure and passed for years while the thing it is named after was false on every
seed. It now calls `overlapping()` and requires `min(gaps) >= max(footprint) +
STREET`.

Seven tests added, including the shell measured out of a fixture GLB, a shell
modelled off its origin, the unmeasurable shell returning `None`, and the
pre-0.13.17 spec (232 x 100 plate, buildings at -6/39/93/138) asserted to produce
exactly one fault naming `b3` -- guarding the guard, so the fixture can still
express the failure the fix removed.

## [0.13.16] - the obvious way to start the CLI now works

`python -m level_factory -C <factory-root> run <mission> --art` is the command
that gets typed, and both halves of it were wrong in a way the tool did nothing
to help with.

**No module named level_factory.** The CLI lives at `apps/cli/main.py` and ships
as a `level-factory` console script for installed copies. A source checkout with
nothing installed had neither: the natural guess failed with a bare import error
that named what you asked for and said nothing about where the CLI actually is.
The factory root now carries a `__main__.py` that resolves the repo root from
its own location and delegates to `apps.cli.main`. The directory has no
`__init__.py`, so Python treats it as a namespace package -- which means this
works for any checkout directory name, and the test asserts it that way rather
than hard-coding `level_factory`.

**-C pointed at the wrong tree.** The workspace is the folder holding
`.level_factory/`, not the factory root that contains the tool repos. Workspace
discovery searches at and above the given path and never below, so aiming it at
`gabagool_factory` while the workspace sits in `gabagool_factory/rockay-ws`
cannot find anything. That path already failed loudly -- `error: no Level
Factory workspace found at or above ...` -- and a test now pins that it keeps
doing so, because the failure mode worth guarding is a future version quietly
guessing a workspace instead.

Neither of these is a pipeline bug; both cost a run. `tests/unit/test_cli_entrypoint.py`
covers the shim by path, the checkout as a module from its parent, and the
non-workspace error. README's quick start now names all three spellings of the
CLI and what `-C` expects.

Suite: 337 passing, 11 skipped (was 333).

## [0.13.15] - a fix verified against a reconstruction was not verified

No code changed here. What changed is a claim that should not have been made.

0.13.14 and Lot 0.28.0 both ended by reporting that the rebuilt scene "checks
clean -- 0 findings, down from 3". That was measured by running
`check_spawn_placement` against a hand-built Python reconstruction of the
seed's geometry rather than against the scene the pipeline shipped. The next
real run disagreed, and the run is the thing that counts:

    [BLOCKER] JOB_PREFLIGHT_REFUSED
      1 of 3 mission destination(s) cannot be walked to from the player spawn:
      LT_ObjectivePoint is sealed off from the crew spawn

Both entries now carry corrections. The dedupe in 0.13.14 and the height
seating in Lot 0.28.0 are real and did what they said; neither cleared the
blocker, because the marker's *footprint* was still on the counter. Lot 0.29.0
is the fix that does clear it.

The reconstruction was not a shortcut taken knowingly -- it was written to
stand in for artifacts that were awkward to reach, and then trusted as though
it were them. A reconstruction can only reproduce the geometry its author
already believes is there, which makes it exactly the wrong instrument for
finding out that the geometry is not what its author believes. From here a
"verified" claim about a scene means the bytes of that scene were read.

### How the real fix was measured instead

`check_spawn_placement` -- the production function, unmodified -- run against
the byte-verified `site_walk.tscn` and `shell.glb` from the shipped pack,
before and after applying exactly the move Lot 0.29.0 now computes:

    --- as shipped
      findings: 1
       * 1 of 3 mission destination(s) cannot be walked to from the player
         spawn: LT_ObjectivePoint is sealed off from the crew spawn ...
    --- objective resolved 1.5 m
      findings: 0

Staged files are byte-checked before use: the device mount can serve a stale
copy while reporting the device's true size, so `stat` and the reported byte
count have to agree or the file is discarded. The stale copy of this scene was
3336 bytes against the real 5347, and it was the smaller one that made the
reconstruction look right.

## [0.13.14] - one unreachable marker should read as one unreachable marker

The 0.13.13 gate did its job on its first real run: it refused
`laser_tag_evaluate.candidate.seed_5118` at pre-flight instead of spending 900
seconds discovering the same thing and reporting it as a level-design grade.
What it said was "2 of 4 mission destination(s) cannot be walked to ...
LT_ObjectivePoint is sealed off; Route_1 is sealed off".

Route_1 is LT_ObjectivePoint. Lot builds its route as `[spawn, objective,
extraction]`, so the second waypoint is the objective's own coordinate emitted
a second time under the name LaserTag's traversal test reads. One misplaced
marker was being counted twice, which turns a single placement defect into a
map that looks riddled with them -- the wrong signal to hand someone deciding
what to fix first, and a denominator ("of 4") that overstates how much of the
mission is broken.

`classify` now collapses destinations that share a position. Which name
survives is not cosmetic: `LT_ObjectivePoint` says what is wrong with the map,
while `Route_1` says only that the second waypoint of something is unreachable
and sends whoever reads it looking for a route generator that is working fine.
So the objective outranks an index-named waypoint at its own position.

On the real seed_5118 scene the finding goes from "2 of 4" naming both to "1 of
3" naming the objective.

**Correction (0.13.15).** This entry originally ended by claiming that with Lot
0.28.0's seating fix applied the scene "checks clean -- 0 findings, down from
3". That claim was produced against a Python reconstruction of the seed's
geometry, not against the shipped scene, and it was wrong: the real run came
back blocked with "1 of 3 mission destination(s) cannot be walked to from the
player spawn: LT_ObjectivePoint is sealed off from the crew spawn". The dedupe
described above is real and is what changed "2 of 4" into "1 of 3"; the
blocker's disappearance was not. See 0.13.15 for what the marker was actually
standing on.

# Changelog

All notable changes to Level Factory are documented here. Commit messages stay
short (< 200 chars); detail lives here.

## [0.13.13] - a floor under your feet is not a route to you

The navmesh fix in 0.13.12 let Laser Tag bake and play for real, and the first
thing a real bake produced was a refusal:

    seed_5118  UNREACHABLE_SPAWN x6, runs: 0, grade BROKEN
    seed_5017  INSTANT_CONTACT 0.0s, NO_REACTION_TIME 3.0s, TRAVERSAL 0%

`validate_map()` asks every enemy spawn to path to the crew before it plays a
single run, and refuses the whole map when one cannot. All six of seed_5118's
enemies were sealed inside building interiors -- and `check_ground_contact`
had passed the scene without a word, because every one of them had a slab
underneath it. "Standing on something" and "standing somewhere the crew can get
to" are different claims. Only the second one is what the evaluator checks, and
nothing in this pipeline was making it.

### packages/validation/spawn_placement.py

A 2.5-D walkability heightfield over the scene's box colliders plus a flood
fill from the player spawn -- a coarse imitation of what Recast does during the
bake, at 0.5 m cells with an `agent_max_climb` step rule. Deliberately
*optimistic*: it does not erode by agent radius, so a gap a 0.4 m agent could
not squeeze through still reads as open. Optimism is the safe direction for a
check that blocks a build. This module under-reports rather than inventing a
wall, and everything it does report the bake will refuse too.

It answers three questions the same field is good for: is a spawn sealed off,
embedded in a solid, or on a different storey; is a marker hanging in the air
above the floor it names; and is an enemy close enough that first contact
happens before the crew has moved -- measured as *walking* distance, because an
enemy three metres away through a wall is not an ambush.

On the real seed_5118 scene it returns in 0.6 s with three findings where the
evaluation took 900 s to return one misattributed grade. It stays silent where
another check already speaks: no hooks belongs to `check_scene_hooks`, no
readable collision and no floor under the spawn belong to
`check_ground_contact`. Wired into `adapters/laser_tag/validate_configuration`
behind both of them.

### ground_contact could not see a node that was in a group

`_SECTION` matched a scene header with `[^\]]*`, which cannot span the bracket
inside `groups=["ladder"]`. Those headers did not match at all -- so the node
never entered the frame table or the type table, its children composed against
the identity, and its body type was unknown. Concretely: Lot writes four ladder
climb volumes as `Area3D` nodes in the `ladder` group, and every one of them
read as a solid 1.3 x 5 x 1.3 floor slab standing at the world origin. Four
trigger volumes counted as ground, 27 m from where the scene put them.

A missing header is not a missing attribute. Greedy now, so the run backtracks
to the last bracket on the line: 1509 boxes to 1505 on the real scene, and no
ladder among them.

## [0.13.12] - the evaluator played twenty-five matches and measured nothing

The pre-flight gate cleared and Laser Tag played its first real firefights in
the life of this pipeline. Then `run category5_baie_dore_001 --art` came back
with sixteen findings, two of them blockers, and not one of them named the
defect:

    [BLOCKER] JOB_TIMEOUT (runtime_requirement) ... tool exited 3221225786
    [BLOCKER] JOB_TIMEOUT (runtime_requirement) ... tool exited 3221225786
    [MAJOR]   LT_MAP_NO_REACTION_TIME   player survives 9.4s
    [MAJOR]   LT_MAP_TRAVERSAL          0% route completion
    [MODERATE] LT_LOW_READINESS         grade FAIL, score 40, 25 runs
    [MODERATE] LT_MAP_ENEMY_STUCK       57 times
    [MODERATE] LT_MAP_INSTANT_CONTACT   0.0s
    [MODERATE] LT_MAP_NAVIGATION_MISSING ...falling back to direct movement
    [MINOR]    LT_MAP_COVER_BLOCKING    20% of shots blocked

Fifteen of those describe a level. One describes the tool. The fifteen are the
artifacts of the one, and it was printed sixth.

### One bug, sixteen findings

The map scene and the evaluation runner both bake the navmesh, and Godot's bake
is threaded:

1. `level.tscn` loads. Lot's `lot_site_walk.gd::_ready()` calls
   `nav.bake_navigation_mesh()` -- dispatched to a thread pool, unawaited.
2. The runner (invoked with `--bake-nav`, which is what Laser Tag's own CI
   passes) takes *that same NavigationMesh resource* and calls
   `NavigationServer3D.bake_from_source_geometry_data()` on it.
3. Godot refuses: `ERROR: NavigationMesh is already baking. Wait for current
   bake to finish.` The resource is left with zero polygons.
4. The runner reads `get_polygon_count()` -> 0 and warns `Baked 0 polygons on
   Nav -- no static colliders on layer 1 under site_walk?`

Step 4 is the silent-emptiness family once more, and this time with a
confabulated cause attached. A *refused* operation printed the same number as a
*completed* operation that found nothing, and then guessed at a reason that was
flatly false: the site carries 374 collision bodies, which 0.13.11 verified by
reading the shell's bytes.

Downstream the harness sees a zero-polygon region, reports
`NAVIGATION_MISSING`, and falls back to direct movement (TDD 29.1) -- bots walk
in straight lines into walls. `route_completion_rate 0.0`,
`enemy_stuck_events 57`, and `first_contact_stddev` exactly `0.0` across
twenty-five seeded runs. Zero variance over twenty-five runs is the tell: that
is not a measurement of anything.

The two `JOB_TIMEOUT` blockers are the same bug wearing a different hat. With
no pathfinding, whether a run ends depends only on whether the player happens
to die. Seed 5017's player died every time (9.4 s average), so 25 short runs
fit inside the 900 s job cap and the job "succeeded" with grade FAIL and a full
set of meaningless numbers. Seeds 5118 and 5219's players mostly did not die,
so every run burned the 180 s in-sim cap (~47 s wall), only 19-20 of 25 fit,
and Level Factory's own timeout killer fired -- exit 3221225786 is
`STATUS_CONTROL_C_EXIT`, the process being killed by us. Same defect, sorted by
luck.

### The third state

`packages/validation/lasertag_report.py` knew two states: the evaluator ran, or
it never ran. This report is neither. Twenty-five runs completed, a complete
130 KB report was written, `was_evaluated()` said yes -- and nothing was
measured. So there is now a third:

* **`LT_EVALUATED_DEGRADED`** -- blocker, category `tool_contract`. Emitted when
  a report completed runs but carries a `DEGRADED_TYPES` finding
  (`NAVIGATION_MISSING`). It names the run count, the cause, and states plainly
  that the grade and every derived number describe the fallback rather than the
  level. It does not fire when zero runs completed: `LT_NOT_EVALUATED` is the
  earlier and more useful statement, and two blockers for one fault is noise.
* **Pathfinding-derived findings are demoted to `info`** with the reason carried
  on the finding text, so the line still reads correctly quoted on its own.
  `NAV_DERIVED_TYPES` lists them explicitly. Sightline findings (`BLIND_MAP`,
  `EXPOSURE`) are deliberately *not* in that set -- they ray between statically
  sampled positions and never consult the navmesh, so they remain the one real
  measurement in a degraded report. An unlisted finding type keeps the severity
  Laser Tag gave it: overstating a finding is recoverable with the degraded
  blocker sitting above it, whereas silently demoting a type this list has not
  heard of would hide a real defect behind a bug in the list.
* **`LT_LOW_READINESS` is suppressed when degraded.** Grade FAIL over a match
  played without pathfinding is not a readiness signal, and printing it as one
  sends someone off to tune combat pacing on a level whose only defect is a
  missing navmesh.
* **`metrics()` carries `lasertag_degraded`** so candidate selection never
  ranks two candidates whose bots both walked into walls as if the comparison
  meant something, and **`summarize()` stops printing `3/3 evaluated`** for
  three navigation-less runs -- it now says `3/3 evaluated, 2 without
  navigation`.

TDD 5.5 is intact: a readiness score still never blocks a build. "The evaluator
ran without the thing it measures with" is a contract failure, the same class
as "the evaluator never started", and it blocks.

Nine tests in `tests/unit/test_lasertag_readiness.py` (18 total in the file),
including one that pins a healthy report passing through the degraded path with
its severities untouched -- a gate that hides findings is just an outage.

### Upstream, in the two tools that raced

* **Lot** (`godot/addons/lot/lot_site_walk.gd`): the walkthrough bake now
  returns early when `DisplayServer.get_name() == "headless"`. Headless means
  nobody is walking the scene -- it was loaded by an evaluation runner that
  bakes navigation itself, against its own agent parameters. When there is no
  walker, the right amount of baking is none. Pinned by a Lot test that reads
  the shipped `.gd` and asserts the guard precedes the call.
* **Laser Tag** (`addons/laser_tag_tool/runners/run_map_eval.gd`): the runner
  bakes into a *fresh* `NavigationMesh` rather than the region's own. It
  overrode every parameter anyway, so reuse bought nothing but the race -- and
  a new resource carries the engine-default `cell_size`/`cell_height`, which is
  what the navigation map itself uses, so the rasterization-mismatch warnings
  go with it. It also waits out an in-flight bake the map started (bounded, and
  it says so if the wait runs out) and separates the two failures it used to
  merge: `source.has_data()` false means no static colliders were parsed at
  all, while zero polygons from a non-empty parse means geometry was found and
  none of it is walkable at the configured agent radius, height and slope. Two
  faults with different fixes; the old message guessed at the first and the
  truth was usually neither.

## [0.13.11] - the pre-flight refused a floored map because it would not open the shell

`run category5_baie_dore_001 --art` stopped at the gate with:

    [BLOCKER] JOB_PREFLIGHT_REFUSED (configuration)
    12 of 15 mission point(s) have no ground beneath them: LT_CoverTestPoints/
    Cover_0, ... (collision inside 5 instanced resource(s) is not readable from
    the scene text); Laser Tag would refuse the map with NO_WORLD_COLLISION and
    complete zero runs

Read that sentence twice. The parenthesis says the check could not see inside
the buildings; the verdict says there is no floor inside the buildings. A check
gets one of those two positions, not both — and this one had picked the wrong
one. The shell it declined to open, `shell.glb` from `deli_generate`, holds 855
nodes of which 374 are `-col`-family colliders, including four
`slab_col_*-colonly` floor slabs at 44 x 32 m, one per storey. Every one of the
twelve "floating" points was standing on a slab. The map was walkable and the
pipeline refused to build it.

This is the silent-emptiness family again, in its purest form: *I cannot see it*
rendered identically to *it is not there*. The previous entries in that family
were surfaces that said nothing when they had nothing to say. This one says
something, and what it says is false.

The fix is that the binary describes itself. Godot's glTF importer generates a
physics body for a node whose name ends in the `-col` family of suffixes, and
the extent of that body is fully determined by the JSON chunk: the node
hierarchy carries the transforms, and each mesh primitive's `POSITION` accessor
carries `min`/`max`. A collider's world-space AABB can therefore be computed
without decoding a single vertex buffer, without Blender and without Godot.

- **New: `packages/validation/glb_collision.py`.** Pure stdlib, bytes in and
  boxes out, importable with nothing else from Level Factory on the path — the
  same question gets asked from Lot's side of the fence. Reads the container
  (chunks in any order), the `-col` suffix family (case-insensitive, tolerating
  Blender's `.001`), the `generate/physics=true` import setting that bodies
  every mesh instead, `matrix` and TRS node transforms, and nested hierarchies
  with a depth guard so a cyclic file cannot turn a pre-flight into an infinite
  walk. Returns a tri-state `GlbReading`: parsed-with-colliders,
  parsed-and-confidently-hollow, and could-not-be-read, which stay three
  different answers all the way to the message.
- **`ground_contact` now reads instanced `.glb`s** instead of recording them as
  opaque, composes 3x4 matrices down the node path instead of adding origins,
  and honours axis-aligned rotations exactly. That last part is load-bearing:
  three of the four buildings on this site are placed at 90 degrees, so their
  44 x 32 slab is a 32 x 44 footprint in site space, and the objective at
  (-6, -16) only lands on it when the quarter turn is carried through. A basis
  that is *not* axis-aligned is still reported opaque, because this reader
  cannot state that footprint as a box without inventing area.
- **`resolver()` finds a shell that lives in another job directory.** Three
  reference forms land: `res://name`, a bare filename beside the scene, and the
  `res://C:/...` absolute form Lot writes for a local preview. Without the
  basename fallback a mission scene and its shell — which routinely sit in
  different job dirs — would report opaque and re-open this bug from the side.
- **A ladder's `Area3D` is no longer counted as floor.** Lot writes a climb
  volume per ladder; an `Area3D` stops no ray and bakes into no navmesh, so
  treating its box as ground would floor a point hanging in mid-air. Named
  exclusion, not a whitelist of solid bodies — a whitelist drops the floor
  under any body type not thought of here, and dropping a real floor is exactly
  the direction that caused this defect.
- **Whatever is still unreadable is named in the message**, with its shape type
  where there is one (`Player/col (CapsuleShape3D)`). "N resources are
  unreadable" tells an operator the verdict is partly a guess without telling
  them which file to go and look at, which is most of the way back to saying
  nothing at all.

Pinned by 22 tests in `tests/unit/test_glb_collision.py` against real `.glb`
binaries written by `tests/unit/glb_fixture.py` — a hand-rolled dict would test
nothing that ships — plus a trimmed copy of the shell that produced the blocker
at `tests/fixtures/glb/shell_slabs.glb`, and 8 more in
`tests/unit/test_ground_contact.py` covering a floored instance, a genuinely
hollow one that *must still* report the hole, the quarter-turned building, the
shell found by name, the odd-angle instance that stays opaque, and the ladder
trigger. Against the real failing scene the pre-flight now reads 1516 boxes and
floors all 15 mission points.

## [0.13.10] - laser_tag had never evaluated anything

Every `validate` on the real workspace printed five `LT_LOW_READINESS` findings:
grade BROKEN, score None. Read literally that says the pipeline built five
levels whose firefights play badly. The actual report said something else
entirely — `{"grade": "BROKEN", "overall_score": 0, "runs": 0, "findings":
[{"type": "NO_RUNS", "message": "No runs completed — map could not be
evaluated."}]}`. Zero runs. Not one firefight had ever been played, on any
candidate, in the life of the pipeline, and the surface reporting it said
"readiness grade" — a claim about the level rather than about the tool.

Five independent defects were stacked behind that one line:

1. **The map contract was never met.** Laser Tag's harness walks the tree for
   nodes named `LT_PlayerSpawn`, `LT_EnemySpawnPoints`, `LT_ObjectivePoint`
   (plus optional `LT_PlayerRoutePoints` / `LT_CoverTestPoints`); absent them
   `validate_map()` fails and `run_evaluation` returns before the first run.
   Nothing in the pipeline had ever written one of those nodes. Fixed at the
   source in Lot 0.24.0 (`_lasertag_hook_nodes` in `write_walk_scene`), with
   `packages/staging/lt_hooks.py` as Level Factory's staging-time net for
   scenes that arrive without them — derived from the `spawn_pos` /
   `objective_pos` / `extraction_pos` the walk scene already carries.
2. **The score was read from a key the report does not write.** The 0.7
   contract is `overall_score`; the adapter read `score`. Every candidate card
   said `score -`. `report_score()` reads the real key and keeps `score` as a
   fallback.
3. **Laser Tag's own `findings` array was read by nothing** — the list that says
   *why* the map could not be played. Now surfaced verbatim as
   `LT_MAP_<TYPE>` findings, so the pipeline can say what is wrong rather than
   only that something is.
4. **"Could not evaluate" was filed as "evaluated poorly."** These are different
   statements. A readiness score never blocks (TDD 5.5) and still does not —
   but a tool that reports a grade for a match it never played is a contract
   failure, the same class as reporting five candidates it did not build, and
   `LT_NOT_EVALUATED` blocks. A report that omits `runs` entirely counts as
   never evaluated: silence is not a pass.
5. **`facade.py` read a `score.json` no version of Laser Tag has ever written**,
   which is why every candidate card showed a blank score even when a report
   existed. It reads `lasertag.report.json` through the same module now.

Also fixed on the way through, because staging is where it could be caught:
Godot rewrites `. : @ / " %` in a node name to `_` at load time, so Lot's
`[node name="b0/LADDER_0_climb"]` became `b0_LADDER_0_climb` while its
CollisionShape3D's `parent="b0/LADDER_0_climb"` was parsed as a *path*, matched
nothing, and the child was dropped. Every ladder volume in every level shipped
without collision. `packages/staging/tscn_names.py` applies Godot's own rule to
names and to every path referencing them, and reports each repair in
`staging.notes.json` rather than fixing it invisibly. (Source fix: Lot 0.24.0.)

The Laser Tag fingerprint now includes `map_contract` and `enemy_count`. The
evaluator reads the *staged* scene but the fingerprint hashed only the *source*
scene, so baking hooks in at staging would have been called a cache hit and
never re-run — the fix would have shipped and changed nothing.

The stub godot in `tests/fixtures/bin/` used to write a grade-B report no matter
what scene it was handed, so no test could ever observe an unmet contract. It
now reads the staged scene and refuses exactly as the real harness does, and the
stub Lot fixture emits both the root positions and the illegal ladder name on
purpose — a net is only proven by a scene that needs it.
`test_laser_tag_actually_evaluates_the_map` asserts `runs > 0` end to end.

## [0.13.9] - five candidates that were one candidate

Running the pipeline on the real workspace showed five candidates for
`category5_baie_dore_001`. All five `site.tscn` were md5-identical, every
building in every one of them instanced seed_5421's shell, and the whole mission
had exactly one site spec on disk.

`_write_site_spec` wrote to `.level_factory/temp/<mission>/site.json` — one path
per *mission*. Job specs are all built up front, so the five calls clobbered one
file and the last candidate planned won; all five Lot jobs then read that spec
and assembled the same site. The candidate mechanism was decorative: five
choices presented to a human that were one choice.

Underneath it, nothing was ever varying in the first place. Deli Counter is
deterministic by design — `new_level.py` has no `--seed`, and the adapter's own
comment says variation is supposed to come from Lot's site assembly. Lot has the
vocabulary for it (per-building `rot` is honoured through placement, marker
rotation, the Godot transforms and the site audit; `spawn`/`objective`/
`extraction` name the buildings the walkable scene starts, targets and exits
from). LF used none of it, handing every candidate the same evenly-spaced,
zero-rotation row with the role keys unset, so every candidate also spawned the
player at Lot's origin default.

It survived for the life of the pipeline because nothing had ever compared two
candidates to each other. Per-candidate validation ran five times and passed
five times — which is exactly what it does when the candidates are real.

- `packages/pipeline/site_variation.py` (new): `site_placements(seed, count)`
  derives per-building cardinal yaw, along-row nudge and across-row stagger from
  the candidate seed, plus which building carries spawn / objective /
  extraction. The variation is structural on purpose — a metre of jitter would
  make the hashes differ while leaving the level identical to play, and passing
  the gate is not the goal. Deterministic without `random` so the builder, the
  cache fingerprint and the gate all re-derive the same site.
- `packages/validation/candidate_diversity.py` (new): compares a mission's
  candidates against each other. Byte-identical candidates are a **blocking**
  `CANDIDATES_NOT_DISTINCT`; a candidate with no outputs is a separate,
  non-blocking `CANDIDATES_MISSING_ARTIFACTS`, because "never built" and
  "duplicate" are different problems and collapsing them hides the rarer one.
  Blocking is consistent with TDD 5.5: this is not a claim about whether a level
  is good, it is the pipeline reporting that it did something it did not do.
- `apps/cli/commands/__init__.py`: `_write_site_spec` takes the candidate seed
  and writes to `temp/<mission>/candidate_seed_<n>/site.json` (filename kept as
  `site.json` so Lot's stem-derived output names stay canonical). `run` and
  `batch run` compare the candidates they built and print how many distinct
  levels came out, so "5 candidates" can never again be printed for one level
  built five times.
- `tests/fixtures/repos/lot/lot.py`: the stub bakes `at`/`rot` into the scene as
  real Lot does — a stub that ignores placement emits one scene for every
  candidate and hides the exact bug the gate exists to catch.

## [0.13.8] - findings you can read, runs you can see

Two reporting surfaces were quietly empty, in the same way the Windows display
probe was: they rendered "nothing to say" identically to "nothing happened".

`validate` printed a histogram. `"combat_structure": 5` is a number, not a
finding — there is nothing in it to go fix, so the same 5 sat on every run for
weeks and read as weather rather than as work. It now prints the findings
themselves, worst first, each with its code, the candidate and location it
belongs to, the message, and the suggested fix. `--json` is new and carries the
aggregate *plus* every finding, so a caller no longer has to re-read the raw
file to learn what was found.

`status` with no mission id printed nothing at all. The cause was that
`Index.upsert_mission` had no callers anywhere in the codebase — the missions
table was never written, so the listing was empty forever and `batch report`
showed every mission as "draft" no matter how many times it had been built.

- `apps/cli/commands/__init__.py`: `cmd_run` and `cmd_batch_run` now record the
  state a run leaves behind (`built` / `findings` / `blocked`) against the
  mission's batch. `cmd_status` prints batch and state, and says so explicitly
  when a workspace genuinely has no runs rather than exiting silent.
- `apps/cli/main.py`: `validate --json`.
- `tests/integration/test_end_to_end.py`: a run must leave a trace both surfaces
  can show — the mission listed and attributed to its batch, and findings
  rendered as text with the machine output carrying them one for one.

## [0.13.7] - the visual pass no longer skips itself on Windows

First run on a Windows dev machine reported `shot bot: SKIPPED -- no display and
no xvfb-run`. The host had a display; the probe was asking the wrong question.

`display_wrapper` decided whether a renderer was available by reading `DISPLAY`
and `WAYLAND_DISPLAY`. Those are X11 and Wayland variables. Windows and macOS
sessions have a window server and never set them, so the check concluded
"headless" on every Windows machine and skipped the visual pass permanently —
while phrasing the skip as a property of the host. A gate that reports a clean
skip is worse than one that fails, because nothing about the log says to go
look.

- `packages/preview/walk_bot.py`: the X-server probe now runs only where an X
  server is the thing in question (linux, the BSDs). Elsewhere the wrapper is
  empty and the engine renders directly. Where that assumption is wrong — a
  Windows service account with no desktop — the engine fails to open a window
  and surfaces as `BotUnavailable`, which is an actionable message rather than a
  silent pass.
- `tests/unit/test_walk_bot_runner.py`: both halves pinned. A desktop OS without
  `DISPLAY` must render (`win32`, `darwin`, `cygwin`); headless Linux without
  xvfb must still skip rather than launch a renderer that cannot open a window.
  The existing X-server tests now pin the platform, so they assert the same
  thing on a Windows machine as they do in Linux CI.

## [0.13.6] - walk preview self-checks itself: traversal bot + visual bot

The preview existed so a human could find out whether a level was broken. Now
the level finds out first, and the human is only asked to look at something that
already has a name.

- `assets/godot/walk_bot.gd`: a stalled climb is diagnosed instead of merely
  reported. The bot names the collider in the way, measures the slab aperture in
  ladder-local axes, compares it against the climb column the capsule needs
  (`CLIMB_STANDOFF +/- CAPSULE_R`), and states the fix. Its capsule and standoff
  are now pinned to the same constants as the player and DC's climb contract —
  a bot of a different size proves nothing about the player.
- `assets/godot/shot_bot.gd` (new): the visual pass. Renders canonical stations
  (exterior, each ladder's approach, each ladder's top-of-climb) and measures two
  things physics cannot see. VOID FRACTION: the camera environment is overridden
  to a flat magenta no material produces, so leftover background pixels are
  places the camera looked and found nothing. JITTER DIFF: each station renders
  twice, one millimetre apart — solid geometry does not change at that scale,
  but coplanar surfaces flip which one wins the depth test, so a z-fighting pair
  lights up. No golden baselines: both measurements compare a frame against
  another frame of the same build, so the pass is meaningful the first time it
  runs on a level nobody has seen.
- `packages/preview/walk_bot.py` (new): runs both bots and folds their verdicts
  into a pass/fail. Reads the verdict FILE rather than the engine's exit code
  (Godot exits non-zero over a missing audio device; that is not a level
  defect), and reports engine trouble as engine trouble. The visual pass needs a
  display — where there is none it is SKIPPED and says so in the log, never
  silently counted as a pass.
- `packages/preview/walk_preview.py`: copies the bots into the preview project
  alongside the player; reports them as `bots`.
- `apps/cli`: `walk` runs the self-check after the import pass and returns
  EXIT_FINDINGS when it fails — the preview is still built and handed over,
  because a failing check is exactly when you want to go look. `--no-bot` and
  `--no-shots` opt out.

Calibration, both directions, on the same mission: a correctly composed package
scored 0.68% jitter at worst (edge aliasing on ladder rungs) and passed; the
same package rebuilt with un-stripped greybox walls under the themed modules
scored 30.67% and failed. The threshold sits at 2%.

## [0.13.5] - build fingerprint: uncommitted tool edits invalidate the cache

A Deli Counter fix to the ladder slab-hole never reached a shipped package. The
fix was on disk but not committed, so `git rev-parse HEAD` was unchanged, so the
build fingerprint was unchanged, so every rebuild cache-hit the pre-fix shell and
the ladder stayed unclimbable. Nothing failed — the pipeline just kept handing
back the old artifact. This is the compose fingerprint anomaly, root-caused.

- `packages/adapters/sdk.py`: `_read_git_commit` now returns HEAD plus a
  `+dirty.<sha16>` marker over the CONTENT of tracked files that differ from
  HEAD, so an on-disk edit changes the revision the fingerprint is keyed on and
  reverting it restores the original digest. Untracked files are deliberately
  excluded: pipelines write generated specs and work dirs into tool repos, and
  folding those in would churn the revision on every run and destroy caching.
- `packages/jobs/scheduler.py`: the per-job fingerprint receipt records
  `tool_version` and `repository_commit`, so a stale artifact can be traced to
  the revision that produced it.
- `tests/unit/test_tool_revision_dirty.py` (new): pins the contract — clean tree
  is the bare sha, a tracked edit changes it, a revert restores it, untracked
  generated inputs do not touch it.

## [0.13.4] - `run --force`: re-evaluate stages when an upstream changed

The scheduler's crash-resume pre-skips any already-succeeded job by recorded
status WITHOUT re-checking inputs. That is unsafe when an upstream changes — e.g.
after `presentation_compose` was inserted, `lux_apply` (already succeeded on the
pre-compose greybox) was skipped on re-run, so Lux kept lighting the greybox
instead of the composed themed scene.

- `packages/jobs/scheduler.py`: `run(..., force=False)`. With `force`, the
  resume pre-skip is disabled and every job goes through the normal
  fingerprint->cache path: unchanged stages still cache-hit instantly (no tool
  re-run), only stages whose inputs actually changed rebuild.
- `apps/cli`: `run <mission> --art --force`. Use after inserting/altering an
  upstream stage to make stale downstream (Lux, Dispatch) re-light the new scene.

## [0.13.3] - walk preview: fix stair speed lurch + restore readable greybox

Two follow-ups from the walkthrough.

- `assets/godot/player_walk.gd`: the stair step-up moved a FIXED 0.35 m forward
  each frame on top of the normal move, so near a step the player rocketed ~4x.
  It now completes only the blocked REMAINDER of the frame's intended move, so
  total horizontal displacement is exactly one frame's worth — no speed boost.
- `packages/preview/walk_preview.py`: reverted the preview renderer to
  `gl_compatibility` (0.13.2's `forward_plus` dropped the material-less greybox
  base into hard shadow -- "anti-graybox"). With flat, brighter ambient and the
  sun shadow off, the un-themed base renders as clean, readable DC greybox again.
  (The greybox base carries 0 materials by design; theming those surfaces is a
  separate pipeline lever, tracked below.)

## [0.13.2] - walk preview: stair-stepping + forward+ renderer

Two preview fixes from a live walkthrough. Both are preview-only (never shipped).

- `assets/godot/player_walk.gd`: adds basic STAIR-STEPPING (raise-forward-settle
  via `test_move`) so the player climbs greybox stairs instead of getting stuck
  on the first riser; sets `floor_snap_length`/`floor_max_angle` so descending
  stairs is smooth. A real wall still blocks (only climbs when lifting a step
  clears the way).
- `packages/preview/walk_preview.py`: the preview project now uses the
  `forward_plus` renderer instead of `gl_compatibility`, so the themed PBR
  materials render as intended rather than dull/flat.

## [0.13.1] - walk preview: light the scene (was pitch black)

The walk preview wraps the pre-Lux content scene, which carries no lighting
(Lux lights the level downstream in the pipeline), so the preview rendered pitch
black. The walk scene now includes a preview-only light rig: a sky + strong
colour ambient (visible regardless of renderer/sky quirks) + a shadow-casting
sun. It's dev chrome — never shipped, and not Lux's final look, just enough light
to walk and inspect the geometry.

- `packages/preview/walk_preview.py`: `walk.tscn` now emits a `WorldEnvironment`
  (sky background + colour ambient) and a `DirectionalLight3D` under a
  `PreviewLighting` node, alongside the level + player.

## [0.13.0] - `walk` preview: walk the themed level without polluting the package

Adds a dev-only first-person walk preview so you can walk the composed themed
level and make refinements. Kept strictly SEPARATE from the drop-in package: the
package is content a stranger instances into their own project, so it stays
project-agnostic (no player, no forced main scene). A player needs its own
project, so the preview is a distinct throwaway project that wraps the same
content scene — it is never exported.

- `packages/preview/walk_preview.py`: builds a separate preview project that
  copies the drop-in content in, adds LF's dependency-free player, and writes a
  `walk.tscn` (content instance + player) + its own `project.godot`
  (main_scene=walk.tscn). Spawns the player at the best baked marker
  (player_start > spawn > attacker_spawn > entrance > door), lifted so gravity
  settles it onto the floor. Never mutates the package.
- `assets/godot/player_walk.{tscn,gd}`: dependency-free CharacterBody3D FPS
  controller (WASD, mouse-look, jump, sprint) — no addons, no project input
  actions (polls keys directly), so it drops into any preview as-is.
- `apps/cli`: new `walk <mission> [--open|--play]` command. Resolves the
  presentation_compose output, builds the preview under
  `.level_factory/preview/<mission>_walk/`, and optionally launches Godot.
- Tests: prove the preview is a separate project wrapping the content, does not
  leak the package harness, leaves the package untouched, and spawns at the
  highest-priority marker. 159 passed, 11 skipped.

## [0.12.0] - `--art` composes the themed level onto DC's collision (contract fix)

The `--art` layer promised a themed level but shipped a grey one: Zoo built the
themed modules, but nothing instanced them onto the shell, so `lux_apply` lit the
raw greybox `site.tscn`. The named-but-unimplemented `presentation_compose` stage
is now real, closing that gap.

- `packages/pipeline/planner.py`: new `presentation_compose` stage (adapter
  `presentation`) between `zoo_dressing_build` and `lux_apply`, depending on the
  selected DC shell (collision truth) + the Zoo kit. `lux_apply` now depends on
  `presentation_compose` and lights the COMPOSED themed scene, not the greybox.
- `adapters/presentation/`: new adapter. Deli Counter is the source of collision
  truth, so composition uses DC's OWN composer (`portable_building.build_package`
  -> `themed_tscn` fit-to-greybox rotation) rather than a reimplementation: it
  strips the greybox to its floors+collision base (walkable shell), fits each
  themed module onto its slot footprint, bakes markers, and runs a placement gate
  + closure check. Surfaces a non-blocking placement-mismatch advisory and a
  blocking dangling-ref finding.
- `assets/scripts/run_presentation_compose.py`: thin LF driver that adds the DC
  repo to `sys.path` and calls `build_package` out-of-process (bpy-free), with a
  stable `building_id=site` so Lux resolves `presentation/site.tscn` without
  reading DC's building_id at plan time. Clear pygltflib hint on missing dep.
- `apps/cli/commands`: builds the compose job spec (DC slots/gameplay/greybox +
  Zoo kit modules) and repoints `lux_apply.composed_scene` at the composed scene.
- `packages/staging/godot_project.py`: `stage_godot_project` now carries sibling
  SUBDIRECTORIES (skipping `addons`/`.godot`) so the themed scene's
  `res://art/zoo/*.glb` refs resolve under Lux — the documented closure follow-up.
- Composition uses Deli Counter's fit-to-collision composer as the single
  source of truth (no LF-side naive/raw-`rot_y` composer).
- Tests: planner locks `presentation_compose` presence + `lux_apply` dependency;
  the P2 integration test asserts `presentation/site.tscn` is composed and lit.
  Fast-suite `deli_counter` fixture gains a stub `portable_building.build_package`.
  154 passed, 11 skipped.

## [0.11.4] - Export localizer: preset-dir trailing slash + bare res:// asset refs

Two portable-export closure bugs, both found opening a real Category 5 export in
Godot 4.7 (the build/art pass was clean; these are export-localizer only).

- `packages/exporting/localize.py`:
  1. Localizing an addon DIRECTORY ref dropped its trailing slash
     (`res://addons/lux/presets/` -> `res://runtime/lux/presets`), so
     `lux_root.gd`'s `dir + filename` load produced
     `res://runtime/lux/presetsX.tres` (no separator) and every Lux preset
     failed to load. `_localize_script` now preserves the trailing slash when
     `<rest>` is a directory ref.
  2. A presentation scene (Lux apply) references the building as a bare
     `res://shell.glb`, but the same asset was bundled to
     `res://assets/shell.glb` from the site scene's absolute ref — and the
     absolute-ref rewriter never sees a bare `res://` path. A new post-pass
     reconciles every root-level `res://<name>` against what actually landed in
     `assets/`. Idempotent (a ref already under `assets/` can't re-match).

### Verified
- Focused repro of both bugs now passes; fast suite 148 passed / 11 skipped.
  The same two fixes, hand-applied to the existing Category 5 export, make it
  open and instantiate in Godot 4.7 (site shells + Lux presets resolve); fresh
  exports now apply them automatically.

## [0.11.3] - Staging runs a real Godot --import pass to register class_name types

- `packages/staging/godot_project.py`: after staging the throwaway project, run
  `godot --headless --path <proj> --import` so Godot itself registers the addon's
  global `class_name` types. Verified on hardware (Blender 5.1.1 + Godot 4.7): the
  0.11.2 synthesized `global_script_class_cache.cfg` is present and correct, yet
  `-s <runner>.gd` still failed "Could not find type" (LT_MapEvalHarness /
  LT_TestScenario) — Godot only resolves class_name types it registered during an
  import scan. The import pass (mirroring exporting/portability) fixes it; the
  synthesized cache stays as the offline fallback. Adds a `godot_executable` param
  to `stage_godot_project`.
- `adapters/laser_tag`, `adapters/lux`: pass `godot_executable` into
  `stage_godot_project` so both Godot-addon stages get the import pass.

### Verified
- Full Category 5 mission built end to end on hardware (2026-07-23): graybox
  (Deli Counter + Lot + Laser Tag, 5 candidates) AND art pass (Pixelcoat `rockay`
  theme-library -> Zoo kit + dressing -> Patina -> Lux apply), 0 blockers, 0
  findings. Fast suite unchanged: 148 passed / 11 skipped.

## [0.11.2] - Staging self-generates the Godot class cache

- `packages/staging/godot_project.py`: when an addon repo carries no
  `.godot/global_script_class_cache.cfg` (Godot writes it from the editor and
  every tool repo gitignores `.godot/`, so a fresh checkout has none), staging
  now synthesizes the cache by scanning the addon's own `class_name`
  declarations instead of copying that editor artifact. Removes the hidden
  precondition that a tool repo must have been opened in the Godot editor
  before Laser Tag / Lux staging could resolve class_name TYPES
  (LT_MapEvalHarness, LT_TestScenario, LuxRoot). The copy-from-repo fast path
  still runs first when the cache is present.
- `tests/real_tools/test_real_adapters.py`: `test_real_dispatch` now skips
  when the bundled `gas_station_robbery_001` example's referenced `build/`
  inputs are absent (a dispatch-repo fixture gap, not an LF defect), matching
  the skip convention of the other real-tool tests. The real LF->dispatch
  bridge stays covered by `test_real_dispatch_handoff_from_lf_staged_inputs`.

### Verified
- Real-tool smoke green on hardware (2026-07-20): `tests/real_tools` 9 passed,
  1 skipped (dispatch example inputs absent), 0 failed. Class-cache synthesis
  validated against the real laser_tag_tool and lux addons —
  LT_MapEvalHarness / LT_TestScenario / LuxRoot emitted with correct base
  types and res:// paths. Fast suite unchanged: 148 passed / 11 skipped.

## [0.11.1] - Fast-suite pixelcoat stub learns theme-library

- `tests/fixtures/repos/pixelcoat/pixelcoat/cli/main.py`: the stub CLI now
  implements `theme-library --theme <t> --out <dir>` (the command 0.11.0's
  adapter change started issuing), emitting one resolvable `<kind>_<theme>/`
  pack per curated kind with its maps written alongside. Without it the
  fast-suite presentation pipeline blocked at `pixelcoat_build` (exit 3),
  cascading into 8 service/integration failures. Production code is unchanged
  -- this realigns the test double with the 0.11.0 pixelcoat-stage contract.

## [0.11.0] - Pixelcoat stage builds the themed skins library

- `adapters/pixelcoat`: theme mode -- when a job spec carries `theme`, the
  stage plans `pixelcoat theme-library --theme <t> --out <work>` (one
  `<kind>_<theme>/` pack per curated material) instead of a single legacy
  recipe. `validate_configuration`/`fingerprint_inputs` accept a theme and
  invalidate on the theme profile's hash.
- `_job_specs_for_plan`: the pixelcoat job now derives
  `{theme: model.theme or batch.theme_family or "delco"}`. The Zoo kit stage
  already points `--skins` at that job's `out/` and `--theme` at the same
  theme, so a building wears its theme profile's curated vocabulary end to end.
- `packages/pipeline/planner`: pixelcoat stage `expected_outputs` relaxed to
  `[]` -- the library is a dynamic set of `<kind>_<theme>/` dirs, validated
  by the adapter in `normalize_validation`.

### Verified
- Seam confirmed against the real scheduler: `_publish_stable` reconstructs
  each output's path relative to work_dir, so the `<kind>_<theme>/`
  subdirectories survive into the stable `out/` the Zoo stage resolves from.

## [0.10.5] - Run artifacts land in _runs\

- `tools/smoke_lf.ps1` (incl. the `_lf_tools` junctions) write run folders and results zips under the factory's `_runs\`
  directory instead of the factory root — tool repos and the coordination
  files stay alone at the top level. No behavior change.

## [0.10.4] - 2026-07-15

### Changed
- Re-grounded lux 0.15.2 -> 0.15.3 (the blend_to_preset typing pair fix).
  Bookkeeping only — this is the release under which the full pipeline,
  export included, first passed portability on hardware (2026-07-15 smoke:
  status PASS, all closure counters zero, clean-project instantiate green).

## [0.10.3] - 2026-07-15

Third hardware pass, root-caused IN-CONTAINER against B$'s actual export with
a real Godot binary: parse errors 30 -> 2 -> 0.

### Fixed
- **Exported project.godot downgrades inference-on-Variant to WARN**: engine
  defaults escalate it to a load-killing error; tool scripts are strict-clean
  under their home projects' warning config (proven: lux_root.gd:218 —
  `var p := _preset_library.get(...)` — killed the script load and took
  lux_runtime_api + lux_emissive_binder down as compile knock-ons). Verified
  green against the real export in a clean project (0 errors, instantiated,
  exit 0). Pair fix: lux v0.15.3 types the line properly.
- **Closure judge**: `export_closure.json` (and `output_layers.json`) are LF
  metadata — the audit report records the original absolute paths it
  rewrote, so the scanner was incriminating the auditor.
- **Portability failures name themselves**: matching Parse/SCRIPT/load-fail
  lines from Godot's output are attached to report issues (first ~10).

## [0.10.2] - 2026-07-15

Second hardware pass on the export closure: the mission INSTANTIATED in a
clean project for the first time (scene_instantiated true, shell bundled,
walk stripped, presets traveling) — remaining failure was 30 parse errors.

### Fixed
- **Class-name script closure**: lux scripts reference each other by GLOBAL
  CLASS NAME (LuxLighting, LuxEmissiveBinder, ...) — no res:// path for the
  ref rewriter to chase, so the named scripts never got localized. The
  localizer now builds a class_name -> script map per tool repo and pulls
  scripts referenced by name from localized .gd files, recursively; names
  need no rewriting — presence plus the portability import pass registers
  them in the class cache.
- **Closure judge**: directory references (lux's preset-library scan) count
  as present when the path exists — the present-set only listed files, so
  res://runtime/lux/presets false-flagged as unresolved.

### Testing
- 147 passed, 1 skipped; regressions for recursive class-name pulls and
  directory-ref resolution.

## [0.10.1] - 2026-07-15

Hardware fixes from the first v0.10.0 smoke: the fixture pipeline held green
(23/23/23, powered exact) but export crashed (exit 5) inside the localizer.

### Fixed
- **Directory addon refs**: `lux_root.gd` scans `res://addons/lux/presets` —
  a DIRECTORY — and the localizer's copy2 died with Errno 13 on Windows,
  killing the export. Directories are now copytree'd (a localized LuxRoot
  needs its preset library to travel with it), and every copy/rewrite is
  wrapped so closure trouble lands in export_closure.json and the
  portability verdict, never in a dead export.
- **Portability engine check runs an `--import` pass first**: the clean
  project has no `.godot`, so the bundled GLB has no import artifacts and
  localized scripts have no global class cache — the staged-project lesson,
  applied to the clean-project test.

### Testing
- 145 passed, 1 skipped; new regressions: directory-ref localization with
  preset payload, copy-failure recorded-not-raised.

## [0.10.0] - 2026-07-15

Export closure: portable exports are now portable by construction. Root-caused
from the 2026-07-15 hardware smoke (first run to reach portability with art
layers): the exporter was a straight tree copy — absolute input paths (Lot's
site.tscn shell ref, mangled to res://C:/...), addon script refs
(site_walk/lux.applied), no mission.tscn entry, and workspace paths embedded
in tool JSON all leaked into the "clean" package. Provenance note from the
same root-cause: the seed_2199-path-in-seed_1997-output scare was the
content-addressed cache working correctly on byte-identical candidate shells
(DC seed variance lives in gameplay/lights data, not graybox geometry); only
the absolute path was poison.

### Added
- **`packages/exporting/localize.py`** — scan_closure stays the judge; this is
  the fixer, run inside `export_mission` for every mode:
  - Absolute ext-resource refs -> bundled `assets/` (content-hash dedupe,
    collision-safe naming) with refs rewritten.
  - `res://addons/<tool>/...` -> localized `runtime/<tool>/...` with refs
    rewritten RECURSIVELY (localized .gd preloads pull their own deps) —
    LUX_LOCALIZED finally does what its README stub promised.
  - Walk scenes (`*_walk.tscn`): STRIPPED by default (portable-godot promises
    no addons; walk is dev chrome, not mission content); `export
    --include-walk` localizes them instead.
  - Tool JSON hygiene: absolute-path string values in exported data files
    neutralized to basenames (dead paths in a clean project either way).
  - `export_closure.json` records every rewrite/localize/strip/sanitize.
- **Synthesized `mission.tscn` entry**: instances site (+ localized
  presentation) via an embedded, addon-free script that prints the
  instantiate marker and self-quits under `--lf-portability-check` — the
  clean-project engine check becomes a real load test instead of a
  missing-main-scene failure or a headless hang.
- `ExportProfile.include_walk` + `export --include-walk` CLI flag.

### Testing
- 143 passed, 1 skipped. New `tests/unit/test_export_localize.py` (abs-ref
  bundling, recursive addon localization, strip-vs-include-walk, entry
  synthesis, hash-deduped name collisions, closure judge green). End-to-end
  stub pipeline now runs export -> **portability-test PASS exit 0, zero
  issues** — first time the full chain closes.

## [0.9.1] - 2026-07-15

### Added
- `tools/smoke_lf.ps1`: the hardware smoke runner, homed in-repo and rebuilt
  for the gabagool_factory layout (paths derive from the repo location;
  `_lf_tools` junctions map LF tool keys onto factory folder names —
  laser_tag -> lasertag). Stage 10 explicitly dumps the fixture-pipeline
  evidence: the zoo fixtures index (`emitter_markers`) and the full
  `fixture_gate.report.json`. Results land in `_lf_smoke_<stamp>` at the
  factory root (run artifact, not repo content).

## [0.9.0] - 2026-07-15

The light-fixture pipeline (Zoo v0.30 emitter markers -> Lux v0.15 spawner),
machine-gated, plus two-layer factory versioning. Binds only to contracts that
passed a hardware run on 2026-07-15 (20 markers -> 20 spawned, co-location
0.049-0.051 m, powered kill/restore exact).

### Added — fixture pipeline
- **`zoo_fixtures_build` stage**: bakes physical light hardware from the locked
  shell's `shell.lights.json` (Blender; `zoo --fixtures`). Zoo adapter gains
  `mode="fixtures"` (adapter 0.3.0, contract `zoo.asset.0.30`); its
  `normalize_validation` enforces the marker contract — a fixtures index with
  no `emitter_markers`, or markers != built, is a BLOCKER (pre-v0.30 output is
  invisible to the spawner).
- **`lux_fixture_gate` stage**: headless Godot gate over the fixtures GLB —
  spawn count vs markers, lamp<->hardware co-location (LuxValidator), and the
  `set_fixtures_powered` kill/restore beat. New driver
  `assets/godot/run_fixture_gate.gd` load()s Lux scripts BY PATH (no
  class_name annotations, so no staged-class-cache dependency — the
  LT_MapEvalHarness lesson) and the adapter plans an explicit `--import`
  command before the gate run. Gate failures are BLOCKING findings
  (`LUX_FIXTURE_SPAWN_MISMATCH` / `LUX_FIXTURE_COLOCATION` /
  `LUX_FIXTURE_POWER_GATE`); a marker-less GLB is a non-blocking
  `LUX_NO_FIXTURE_MARKERS`. Lux adapter 0.3.0, contract `lux.look.0.15`.

### Added — two-layer factory versioning
- **`verify-manifest`** command + `contracts.verify_manifest()`: checks every
  tool's `VERSION` against the pin set in `factory.manifest.json` at the
  factory root (OK/DRIFT/INCOMPATIBLE/UNKNOWN, same semantics and exit codes
  as `verify-contracts`). The manifest is DATA at the factory level; the
  checking CODE lives here — code never lands at the factory level.

### Changed / Fixed
- **Re-grounded**: zoo 0.27.0 -> 0.30.1, lux 0.13.0 -> 0.15.2, deli_counter
  0.74.2 -> 0.75.0 (additive lights.json 1.1; CLI unchanged, exercised across
  the 2026-07-14/15 walkabout chain on hardware).
- **`_preset_for` display-name fix**: Lux registers presets under DISPLAY
  names; `"gothic_street_night"` was never in the library, making
  `blend_to_preset` a silent no-op (proven on hardware in the lux visual
  pass). Now emits "Blue Hour" / "Delco Summer Afternoon" / "Gas Station
  Fluorescent", and `run_lux_apply.gd` checks the registered library and
  reports `LUX_PRESET_UNKNOWN` (non-blocking) instead of applying nothing
  silently.
- Contracts unit test updated to track the re-grounded baseline.

### Testing
- 138 passed, 1 skipped (fast suite; integration tests run the full stub
  pipeline WITH the two new stages). Stubs: zoo `--fixtures`, godot
  `run_fixture_gate.gd` + bare `--import`. New
  `tests/unit/test_fixture_pipeline.py` (planner wiring, zoo fixtures mode,
  marker-contract blockers, gate normalization, factory-manifest lockstep).
- Real-Godot execution of the gate still needs one hardware run (same class
  as every prior Godot-side feature).

## [0.8.1] - 2026-07-13

Re-grounded pixelcoat after an intended tool update — the contract guard's first
real exercise. All eight updated repos were re-verified; only pixelcoat's version
moved.

### Changed
- `verify-contracts` flagged **pixelcoat DRIFT (0.2.0 -> 0.9.0)** against the
  updated repos and everything else OK. The real-tool smoke was re-run: pixelcoat
  0.9.0's CLI (`build <recipe> --output --json`), output tree, and pack schema
  (`pixelcoat-pack/1`) are unchanged — the richer 0.9.0 recipe format is additive
  and LF's minimal recipe is still accepted (new pack keys `export_type`/
  `processing_mode` are additive). So the contract holds; the grounded baseline is
  moved to 0.9.0 (pixelcoat also now ships a clean `version.py`). Stub bumped to
  0.9.0 for parity.
- The other seven tools re-verified OK with unchanged versions and a passing smoke
  against the updated repos.

### Testing
- 134 passed, 10 skipped; real-tool smoke 10 pass against the updated repos;
  `verify-contracts` exit 0 after re-grounding.

## [0.8.0] - 2026-07-13

Tool-contract verification — the integration-drift guard. When one of the eight
sub-tools is updated, its CLI/output contract can drift out from under the adapter
grounded against it; this turns silent drift into a loud, gating signal.

### Added — `packages/tools/contracts.py`
- A **grounded baseline** (`GROUNDED`) recording the version each adapter was
  certified against (deli_counter 0.74.2, lot 0.18.0, pixelcoat 0.2.0, zoo 0.27.0,
  patina 0.18.0, lux 0.13.0, dispatch 0.3.0 / contract dispatch.mission.v0.2;
  laser_tag has no version source and is marked unpinned).
- Semver-tolerant comparison → OK / DRIFT (same major, re-certify) / INCOMPATIBLE
  (major bump, adapter likely broken) / UNKNOWN (no version to compare). Handles
  the tools' heterogeneous version strings ("Deli Counter 0.74.2", bare semver,
  `version.py`, or absent).

### Added — commands
- `verify-contracts` — probes installed tool versions and compares to the
  certified baseline (the workspace lock if set, else GROUNDED). Exit 0 all-clear,
  1 on drift, 3 on incompatible; `--strict` also fails on unverifiable tools;
  `--json` for CI.
- `certify` — records the currently-installed versions as certified into
  `tools.lock.json` (extends the existing per-tool lock section, preserving
  `required_schema`/`required_contract`). Run the real-tool smoke first.

### Changed
- `doctor` now compares each tool's installed version to the certified baseline
  and reports drift (WARN) / incompatible (FAIL) inline, not just the version.
- Tool-version probing reads more sources (VERSION -> package `__version__` incl.
  `version.py` -> pyproject), preferring the runtime version over packaging
  metadata (patina's pyproject 0.1.1 vs runtime 0.18.0 was the motivating case).
- `ci-init` templates gain a **contract-guard** job that runs the fast suite +
  `verify-contracts` + the real-tool smoke (when `LF_TOOLS_DIR` is set) on every
  push — so a tool-pin bump that breaks a contract fails CI instead of surfacing
  as a broken output later.

### Testing
- 134 passed (+6 contract tests), 10 skipped; real-tool smoke 10 pass. Verified
  live against the real repos: 7/8 tools verify clean, laser_tag honestly reported
  as unpinned (default exit 0); a simulated drift/major-bump flags correctly.

### Still needs the tool repos (not LF)
- Extending Dispatch's machine-readable `contract` command to the other seven
  tools would let LF diff the *contract* (schemas, CLI surface, outputs), not just
  the version — the durable fix. The three layers here are the safety net around
  it. laser_tag and pixelcoat would also benefit from a static VERSION file.

## [0.7.1] - 2026-07-13

Docs only. The README predated the composable-layer work (0.7.0) and several
grounding versions — it still described a fixed functional-pipeline + art-pass +
handoff flow and used stale `--target` examples.

### Changed — README
- Leads with the **Output layers** model: Graybox base + independent Art/Gameplay,
  the four `run` combinations, and the DC/Zoo boundary (DC builds greybox +
  collision standalone; Zoo is the art-pass swap/props/dressing). Notes the
  `--target` legacy alias.
- Quick start and batch examples use `--art`/`--gameplay`; adapter list corrected
  to all eight tools; added `packages/staging/` and the `LF_TOOLS_DIR` real-tool
  smoke to the docs. No code changes (still 128 passed / 10 skipped).

## [0.7.0] - 2026-07-13

Composable output layers. The deliverable is now a **Graybox** base (DC greybox +
collision, assembled by Lot, with Laser Tag nav QA) plus two independent optional
layers — **Art** and **Gameplay** — in any combination. Corrects an earlier
mental model: Zoo is an *art-pass* tool (kit swaps at DC's slot transforms + non-
collision props/dressing), NOT a graybox collision producer — DC builds the
greybox with functional collision standalone (`docs/ASSET_SWAP_CONTRACT.md`,
point 5: swaps "provide collision or inherit DC's auto-collision rule").

### Added — composable layers (`packages/pipeline/planner.py`)
- `LAYER_ART` (Pixelcoat + Zoo kit/dressing + Patina + Lux) and `LAYER_GAMEPLAY`
  (Dispatch objective/nav/spawn suggestions, advisory) are independent. Graybox
  is the always-on base. Four real outputs: graybox, +art, +gameplay, +art+gameplay.
- `--art` alone now produces the art pass with **no Dispatch** (new capability —
  previously the only art path, `presentation`, always ran Dispatch). Dispatch's
  dependency follows the stack: on the Lux art scene when `--art` is set, else on
  the graybox Lot site directly.
- `plan_mission(..., layers=...)` is the new primary API; `target=` still works
  and maps via `layers_for_target` (functional-lock → graybox, dispatch-handoff →
  +gameplay, presentation → +art+gameplay), so existing CI/scripts don't break.

### Added — CLI + batch
- `run` / `plan` / `batch run` take `--art` and `--gameplay` (independent flags);
  bare `run <mission>` is graybox. `--target` kept as a legacy alias
  (`--art`/`--gameplay` take precedence). `plan` prints the output label
  (e.g. `output=graybox+art`).
- Batch planner is layer-driven: the shared Pixelcoat node is included only when
  the Art layer is on; any optional layer requires a locked candidate.

### Changed — layer-aware export
- `export` resolves its functional base from what was actually built: the
  Dispatch handoff when the Gameplay layer ran, otherwise the graybox Lot site.
  A graybox or art-only mission exports a valid self-contained Godot package with
  no phantom art/gameplay references. Each export records `output_layers.json`.

### Testing
- Fast suite: 128 passed (+8 layer tests), 10 skipped. Real-tool smoke: 10 pass.
  Verified end-to-end through the CLI: bare `run`=graybox, `--art`=art pass w/o
  dispatch, `--gameplay`=dispatch on graybox, `--art --gameplay`=full stack;
  graybox-only export produces a clean package from the Lot site.

## [0.6.11] - 2026-07-13

Grounded the LAST un-rebound stage: the Dispatch handoff. LF was assembling a
mission spec against an *assumed* flat contract that real Dispatch 0.3.0 rejects,
and it fed Dispatch none of the input files its resolver requires. Fixed and
verified end-to-end against the real tool (readiness 100, 0 blockers).

### Fixed — `_write_dispatch_spec` wrote an invalid mission spec
- Wrote `"mode": "shell-handoff"` into the spec's `mode` field, but Dispatch
  only accepts `online_coop_pve` there — `shell-handoff` is the *build* mode,
  already passed correctly by the adapter as `--mode`. Now writes a valid v0.2
  spec: correct `mode`, `players`/`networking` defaults, real `inputs`, and a
  minimal `mission_flow`. The old top-level `site_scene`/`gameplay`/`lights`
  fields (ignored by Dispatch) are gone.
- The mission-objective layer is OPTIONAL in this pipeline (the model is just a
  shell the gameplay team fills), so the spec's `validation` block relaxes
  objective-reachability and runtime-readiness — the shell is never gated on a
  fabricated mission.

### Added — Dispatch-input staging bridge (`packages/staging/dispatch_inputs.py`)
- Dispatch's resolver needs `deli_counter` = `shell.gameplay.json` + `shell.glb`
  + `shell.nav_hints.json`, and `lot` = `lot.layout.json` + `lot.gameplay.json`
  + `lot.nav_hints.json` + `lot.glb`. DC and Lot natively emit a richer
  `markers`/`objectives`/`loot` schema (x/y/z), not Dispatch's `anchors:[{pos}]`
  + nav `{nodes,links}`. The staging layer maps between them: affordance markers
  (doors, cover, landmarks, loot) become anchors (descriptive model data, not a
  mission), a connectivity nav graph is derived, and the DC shell glb is reused
  as the passthrough `lot.glb` (Dispatch only copies it).
- Anchor ids are namespaced per source (`deli_counter:` / `lot:`) for the global
  uniqueness Dispatch requires; a `player_start` + `extraction` are guaranteed so
  spawn/extraction checks bind without inventing objectives.

### Testing
- Fast suite: 120 passed, 9 skipped. Real-tool smoke: **10 pass** (+1: real Lot
  → staging → real `dispatch build`, asserting a blocker-free handoff). Full CLI
  `run m1 --target dispatch-handoff` completes (exit 0) with the full handoff
  (mission.tscn, manifests, anchors, beat graph, nav hints, build.lock, HANDOFF.md).
- DC stub aligned to the real DC schema (markers/objectives/loot) so stub and
  real tool share the staging path.

### Now unblocked on hardware
- The Dispatch handoff from an LF-generated mission is verified in-container
  against the real tool. On your machine the remaining real-Blender/Godot steps
  (DC build.py, Zoo kit/dress, Lux headless apply) feed this same bridge — the
  handoff itself is no longer the unknown.

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
