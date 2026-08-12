# Per-building art: five buildings wearing one building's clothes

**2026-08-06.** Diagnosis complete and measured, implementation not started.
Written before building because the mechanism is settled and the cost is not
small, and because the last two retractions in this repo both came from
building before the mechanism was settled.

## This was already known

`lot_demo_001`'s own brief says it, in `notes`:

> GREYBOX ONLY: run without --art. The themed path composes one scene per
> archetype (roadmap 41 step 4) and **the planner does not yet fan out for it,
> so --art here would place five different buildings and dress them all as
> one.**

`WALKABLE_SITE.md` records the same defect for a different layer -- *"lux_apply
lights `presentation/site.tscn`, the mission shell, which a varied lot does not
place"* -- and calls a varied lot UNLIT as a stated limitation.

So the finding below is a CONFIRMATION, not a discovery. What is new is the
measurement, the exact line, and the observation that the same modelling error
has now appeared in three subsystems, which is what makes it worth fixing
upstream rather than three more times.

## What it looks like from inside the level

The first walkable multi-building site (2026-08-06) showed props standing above
roofs and pushing out through walls. Measured off the loaded scene, per
building, world-space bounding boxes:

| building | shell footprint | shell roof | dressing footprint | dressing top | |
|---|---:|---:|---:|---:|---|
| b0 final_stand | 42.3 x 30.3 | 12.7 m | 30.4 x 22.4 | 8.3 m | inside |
| b1 supermarket_a01 | 44.2 x 32.3 | 4.5 m | 30.4 x 22.4 | 8.3 m | **+3.8 m above roof** |
| b2 pharmacy_a02 | 26.1 x 20.3 | 3.4 m | 30.4 x 22.4 | 8.3 m | **+4.9 m above roof** |
| b3 depot_a01 | 46.3 x 26.3 | 6.5 m | 30.4 x 22.4 | 8.3 m | **+1.8 m above roof** |
| b4 lf_lot_demo_001_5017 | 22.0 x 30.0 | 8.3 m | 22.4 x 30.4 | 8.3 m | inside |

The dressing bounding box is **exactly 30.4 x 8.4 x 22.4 in all five** (b4 is
the same box rotated 90 degrees). Fixtures likewise, exactly 30.5 x 3.7 x 17.9
everywhere. Five shells with footprints from 26x20 to 46x32 and roofs from
3.4 m to 12.7 m are wearing one identically-sized set of props pinned to a
fixed height band. In `b2` the dressing footprint is LARGER than the shell.

Reproduce with `probe_dressing.tscn` against a built walk project. It prints
each building's `WHOLE / GreyboxBase / Dressing / Fixtures` extents and needs
no Blender.

## The mechanism, at three levels

**1. The planner builds the art DAG once, for the mission shell.**
`packages/pipeline/planner.py`, the `LAYER_ART` block: `pixelcoat`,
`zoo_kit_build`, `patina_apply`, `patina_dressing`, `zoo_dressing_build` and
`zoo_fixtures_build` are each added as ONE job keyed to `selected_candidate`,
with expected outputs named `shell.patina.glb`, `shell.patina.dressing.json`
and so on. Singular, by construction.

**2. The compose adapter fans out for geometry and not for content.**
`adapters/presentation/__init__.py`. `compose()` takes six keyword arguments --
`slots, gameplay, greybox, out, bid, scene_rel` -- and the per-archetype loop
overrides all six. Dressing and fixtures are not arguments; they are read from
the **closed-over `job_spec`**:

```python
def compose(*, slots, gameplay, greybox, out, bid, scene_rel):
    ...
    if job_spec.get("dressing_glb"):
        args += ["--dressing", str(job_spec["dressing_glb"])]
    if job_spec.get("fixtures_glb"):
        args += ["--fixtures", str(job_spec["fixtures_glb"])]
```

The comment directly above that loop is:

> ONE COMPOSE PER ARCHETYPE. Each building is dressed AS ITSELF: its own slots,
> its own gameplay markers, its own greybox. Pointing five different buildings
> at one composed scene would place five greyboxes and dress them identically,
> **which is the lie this exists to remove.**

It promises "dressed AS ITSELF", enumerates three things, and dressing is not
one of them. The failure it names is the one it performs.

**3. `_layer_glb` picks one arbitrarily and will keep doing so after a fix.**
`apps/cli/commands/__init__.py` globs `*_dressing.glb` in the dependency's out
dir and returns `hits[-1]` -- last by sort. Its own docstring says *"Resolved
by suffix because the filename carries the building id"*, so the author
expected several and then took one. Today only one exists. The moment the
dressing stage fans out, this silently selects whichever archetype sorts last
and gives it to everybody.

## Why no gate caught it -- measured, and worse than expected

There IS a lineage guard, in `assets/scripts/run_presentation_compose.py:52-80`.
It was written for exactly this failure; its own comment says *"dressing/fixtures
are Patina-placed against ONE specific build's walls and roof. Mixing a layer
from a different build variant embeds props inside the wrong geometry."*

```python
slots_sha = json.loads(Path(a.slots).read_text(
    encoding="utf-8")).get("spec_sha256_16")
...
for layer in (a.dressing, a.fixtures):
    side = Path(layer).with_suffix("").as_posix() + ".built.json"
    lsha = _spec_sha(side)
    if slots_sha and lsha and lsha != slots_sha:
        ... return 5
```

**It never ran.** `spec_sha256_16` is written by Deli Counter into a GENERATED
shell's `slots.json`. The library archetypes do not have it. Measured directly:

```
final_stand.slots.json    keys: building_id, coverage, module_library,
                                module_size, slot_manifest_version, slots,
                                space, theme
                          spec_sha256_16: ABSENT
pharmacy_a02.slots.json   same shape, spec_sha256_16: ABSENT
```

`slots_sha` is therefore `None` for every archetype in a varied lot, and
`if slots_sha and lsha and ...` short-circuits to False. The guard silently
skips on precisely the path it was written to protect, and passes.

**And the right field is sitting there unused.** Both files carry
`building_id` -- `final_stand`, `pharmacy_a02` -- and the Zoo layer's sibling
`.built.json` carries `building_id` too; that is how `_bid` and `_scope` name
the layer outputs in the first place. The two things that needed comparing were
both present, under the same key, and the guard compared a different key that
one side never has.

So this is not "the guard checks build rather than building". It is a guard
that CANNOT FIRE, on the path that matters, and reports nothing when it skips.
That is the exact failure this repo has written down twice: a check that cannot
fail is indistinguishable from one that passed.

Two consequences for the fix. The guard must compare `building_id`, which both
sides always have. And it must REFUSE when it cannot make the comparison,
rather than falling through -- otherwise the next input format that drops a
field turns it back off silently.

## The kit is NOT part of this defect

`zoo_kit_build` is also a single mission-scoped job, and that is correct. A kit
is a LIBRARY of modules resolved per slot at compose time -- the five packages
demonstrably drew different module sets from it (`final_stand` took none,
`lf_lot_demo_001_5017` took 25). Dressing and fixtures are different in kind:
they are BAKED PLACEMENTS of props against one specific shell's geometry. A
library shared across buildings is fine; a placement shared across buildings is
the defect. Fixing the wrong one of these would cost a Blender build per
building for no gain.

## The fix: fan the placement stages out per building

Make "the set of buildings this mission places" a first-class input to the art
DAG, and fan out exactly the stages that bake a placement:

- `patina_apply` / `patina_dressing` -> per archetype
- `zoo_dressing_build` -> per archetype
- `zoo_fixtures_build` -> per archetype
- `zoo_kit_build`, `pixelcoat` -> unchanged, one per mission

Then `dressing_glb` and `fixtures_glb` become `{archetype_id: path}` mappings
and the compose loop passes each archetype its own -- **exactly the change
`themed_scene` already received in 1ad02ae**, one layer down. That commit is
the template; this is the part that was left behind.

### Feasibility: the inputs already exist

`deli_counter/build/` holds 1,375 files. Per-suffix: 138 `.glb`, 137
`.gameplay.json`, 136 `.slots.json`, **135 `.lights.json`**. Every archetype in
`lot_demo_001`'s lot carries `.glb`, `.gameplay.json`, `.slots.json`,
`.lights.json`, `.navigation.json`, `.manifest.json` and `.validation.json`.

`building_library.REQUIRED` is `(".glb", ".gameplay.json", ".slots.json")` and
does not index `.lights.json` -- which is why per-archetype fixtures look
impossible and are not. REQUIRED needs a fourth entry for the art path, and the
three archetypes lacking one must drop out of a THEMED lot loudly, the same way
a missing `slots.json` already drops one out of any lot.

### The cost, and the reason it is worth paying twice over

Five buildings x (patina base, patina dressing, zoo dressing, zoo fixtures) is
10 extra Blender jobs and 10 extra Python jobs per themed run. That is real.

Against it: **per-building art is cacheable and mission-independent.** A
dressing bake keyed on (archetype, theme, seed) is the same artifact for every
mission that ever places that archetype, so the second mission to use
`pharmacy_a02` pays nothing. Per-mission art is rebuilt for every mission
forever. The expensive version is the one in the repo now.

### What the fan-out actually costs in the code

Mapped 2026-08-06 against the real source, because "fan out the planner" hides
three things that are not free:

**`job_id` has ONE discriminator.** `core/ids.py:22` is
`job_id(mission_id, stage, *, candidate=None)`. Every art-layer call omits
`candidate=`, so art job ids are `<mission>.<stage>` -- one per mission by
construction. An `archetype=` axis can be added safely (the candidate tail is
always literally `candidate.seed_<int>`, so the two cannot be confused), and
job ids are used verbatim as directory names, which archetype ids already
satisfy.

**`Job` has no building field.** `core/models.py:159-186`. The spec builder
dispatches on `stage_id ==`, so five `zoo_dressing_build` jobs would all land
in one branch with no way to tell which archetype each is for. `Job` needs an
`archetype_id` field, or the spec builder has to parse job ids -- and parsing
ids back apart is already the fragile part of this codebase.

**`next(...)` silently takes the first match.** Six places resolve a dependency
by substring against `depends_on` -- `commands/__init__.py:240, 363, 397, 434,
443, 490, 493` -- e.g.
`next((d for d in job.depends_on if "zoo_dressing_build" in d), None)`. With
one job per stage that is correct. With five, it picks one and drops four
without a word. These are not incidental; they are the mechanism by which a
fan-out would appear to work and quietly not.

**Job ids reconstructed by string template.** `f"{mission_id}.lux_apply"`,
`f"{mission_id}.presentation_compose"` and similar at `commands/__init__.py:1152,
1153, 1362, 1639, 1742-1749` and `service/facade.py:335, 349, 368`
(`_ART_SECTIONS`, `facade.py:153-159`). Each assumes one directory per stage.

**Two hardcoded names to un-hardcode.** Patina derives its output names from the
input stem (`adapters/patina/__init__.py:42-48`), so per-archetype jobs produce
`final_stand.patina.*` with no adapter change -- but `planner.py:253-254, 263-265`
hardcodes `shell.patina.glb` etc. in `expected_outputs`, and
`commands/__init__.py:388-389` hardcodes `shell.patina.dressing.json` as the
consumer path. Zoo already names by `building_id` from its input manifest
(`adapters/zoo/__init__.py:155, 131`), with constant fallbacks `"building"` and
`"scene"` that WOULD collide across archetypes if a manifest ever lacks the
field.

## Rejected alternatives

**Stop attaching the mismatched layers.** Pass no `--dressing`/`--fixtures` to
archetype composes, leaving four buildings as clean themed greybox. Cheap,
honest, and it removes the floating props tonight. Rejected as the ANSWER
because it makes a varied themed lot permanently less finished than a single
themed shell, which converts a bug into a product limitation. Worth keeping in
a pocket as an interim if the fan-out lands over more than one session.

**Fix it at compose only.** Have the composer scale or clip a layer to the
shell it is attached to. Rejected: it would make wrong props look plausible
instead of obviously wrong, which is worse. The dressing for a pharmacy is not
the dressing for a depot at a different scale.

## Acceptance test

1. `lf run lot_demo_001 --art`.
2. `probe_dressing.tscn` reports **five different** dressing spans, not one box
   repeated. This is the falsifier: identical spans mean the fan-out did not
   take, whatever else passed.
3. For every building, `dressing top <= shell roof` and the dressing footprint
   fits inside the shell footprint. Concretely, against today's numbers: b1
   <= 4.5 m (now 8.3), b2 <= 3.4 m (now 8.3), b3 <= 6.5 m (now 8.3), and b2's
   footprint inside 26.1 x 20.3 (now 30.4 x 22.4).
4. A second mission placing any of the same archetypes gets CACHE HITS on their
   dressing and fixtures jobs. If it does not, the fan-out is keyed on the
   mission and has bought the cost without the benefit.
5. Walk it. Props inside buildings, not above them.

## Traps

- **`hits[-1]` in `_layer_glb`.** It will keep compiling and keep being wrong
  the instant several dressing GLBs exist. Change it to a mapping in the same
  commit as the fan-out, not after.
- **The lineage guard must learn to check the BUILDING.** Otherwise the fixed
  pipeline has exactly the same blind spot and the next regression is silent
  again. A layer should name the building it was built for and compose should
  refuse one built for a different building.
- **`REQUIRED` must fail loudly, not filter quietly.** An archetype with no
  `.lights.json` dropping silently out of a themed lot is how a five-building
  brief becomes a four-building site with every stage reporting success. That
  exact failure is already in `WALKABLE_SITE.md`'s trap list.
- **Do not fan out `zoo_kit_build`.** See above; it costs a Blender build per
  building and fixes nothing.
- **Lighting is the same defect and is NOT fixed by this.** `lux_apply` still
  lights the mission shell. Whatever shape the fan-out takes here should be the
  shape `--render` uses, or this document gets written a third time.

## Where this stands (2026-08-06, end of session)

Landed, each verified against the real files and the full unit suite:

| step | change | files | bytes |
|---|---|---|---|
| 1 | `job_id(..., archetype=)`, `Job.archetype_id` | `core/ids.py`, `core/models.py` | 981→2833, 6902→7753 |
| 2 | index `.lights.json`; `art_incomplete` / `require_art_inputs` | `pipeline/building_library.py` | 5610→8858 |
| 3a | `lot_for` -- the selection rule the planner can reach | `building_library.py`, `commands/__init__.py` | 8858→10241, 90776→**90612** |

Tests: `tests/unit/test_archetype_axis.py` (18), `tests/unit/test_art_inputs.py`
(16). Both pure. Also repaired: `test_scene_payload.py`'s LotAdapter version
pin, which the walkable-site patch's `adapter_version` bump invalidated.

Steps 1, 2 and 3a are all INERT. Nothing plans a per-archetype job yet, so no
artifact changes. `require_art_inputs` has no caller.

## Next: 3b and 3c, and they MUST land together

**3b -- the planner fans out.** In `planner.py`'s `LAYER_ART` block, replace the
single `patina_apply`, `patina_dressing`, `zoo_dressing_build` and
`zoo_fixtures_build` jobs with one per building, via
`building_library.lot_for(brief.lot_library, brief.building_count,
selected_candidate)`. `pixelcoat_build` and `zoo_kit_build` stay single. Also
un-hardcode `expected_outputs` -- `planner.py:253-254, 263-265` names
`shell.patina.glb` etc., but Patina derives its output names from the input
stem (`adapters/patina/__init__.py:42-48`), so a job pointed at
`final_stand.glb` writes `final_stand.patina.*` and the contract must follow.

**3c -- the spec builder stops taking the first match.** Six places resolve a
dependency by substring against `depends_on`, and `next(...)` returns the first
and drops the rest silently:

```
commands/__init__.py:240   "presentation_compose" in d
commands/__init__.py:363   "patina_dressing" in d
commands/__init__.py:397   "pixelcoat" in d
commands/__init__.py:434   "zoo_kit_build" in d
commands/__init__.py:443   dep_key in d          <- _layer_glb, both layers
commands/__init__.py:490   "themed_site_assemble" in d
commands/__init__.py:493   "presentation_compose" in d
```

Plus `_layer_glb`'s `hits[-1]` (`:450`), and the hardcoded consumer path
`shell.patina.dressing.json` (`:388-389`). And `dressing_glb`/`fixtures_glb`
become `{archetype_id: path}`, which is the change `themed_scene` already had
in 1ad02ae.

**WHY TOGETHER.** 3b without 3c is worse than neither. The planner would emit
five dressing jobs, five Blender builds would run, and `next(...)` would hand
the first one's output to all five buildings -- today's defect exactly, with
five times the build cost and a green suite over it. If only one of these can
land, land neither.

**The test that proves it took.** Not "the planner emitted five jobs" -- assert
that the spec builder produced five DISTINCT `--dressing` arguments. A per-job
count passes while the bug is fully intact; the distinctness of the arguments
is the thing that was wrong.

Then 3d (compose takes the layers as arguments; the lineage guard compares
`building_id` and refuses when it cannot) and 3e (`lux_apply` over the
assembled site). The guard will START FAILING builds the moment it works, which
is correct -- so it lands with 3b/3c, not before.

### How to do it without guessing

**Write the failing test first, and watch it fail.** Not "add tests after".
Author the assertion that the spec builder emits five DISTINCT `--dressing`
arguments, run it against today's code, and confirm it goes red. A test written
after a fix can pass vacuously, and this repo has already paid for that: the
buried-treads theory was written, tested for correctness, committed and
described as the cause before any experiment that could refute it, and the
refuting run took one command. A test proven able to fail is the difference
between evidence and decoration.

**Read this much before cutting anything:** `commands/__init__.py` roughly
217-560 (the whole spec builder, not the branch being edited),
`planner.py:223-350`, and the patina and zoo adapters end to end. About 600
lines. The failure mode here is editing one branch of a dispatch whose other
branches share its assumptions.

**Evidence ladder, cheapest first. Do not skip up.**

1. `pytest tests/unit` -- milliseconds, no engine.
2. `lf plan lot_demo_001 --json` -- five dressing jobs with distinct
   `archetype_id`, and NOTHING BUILDS. Free.
3. A unit test over `_job_specs_for_plan` against a synthetic plan: five
   distinct `--dressing` paths. Still no Blender.
4. One real `lf run lot_demo_001 --art`. ~10 extra Blender jobs.
5. `probe_dressing.tscn`: five different spans, each under its own roof.
6. A SECOND run, or another mission reusing an archetype: cache hits on the
   per-building art jobs.

Three layers of evidence before spending a build, and step 6 is the one that
says the cost bought something.

**Pre-commit to what would mean it is still broken**, so a green suite cannot
be mistaken for a working fix:

- five jobs but identical `--dressing` -> `next(...)` is still first-match
- five distinct `--dressing` but identical probe spans -> compose is not using
  what it was handed
- everything green but no cache hits on run 2 -> the art is keyed on the
  mission, and the fan-out bought cost without the benefit

**Still unverified. Settle these before building, not during:**

- `service/facade.py:153-159` (`_ART_SECTIONS`) maps each art stage to ONE
  directory, and `:335, :349, :368` resolve `f"{mission_id}.{stage}"`. With
  five `patina_apply` jobs this either breaks or silently reports one building.
  Decide aggregate-vs-per-building deliberately.
- Three of the library's 138 archetypes have no `.lights.json`. `final_stand`,
  `supermarket_a01`, `pharmacy_a02` and `depot_a01` all do (checked). The
  generated shell `lf_lot_demo_001_5017` is NOT checked -- if it is one of the
  three, `require_art_inputs` will refuse the demo mission and that needs to be
  understood before it looks like a regression.

**Verified, so nobody re-checks it:** library `.lights.json` carry
`building_id` (`final_stand`, `depot_a01` inspected), so Zoo's `_scope` names
fixtures outputs per building rather than collapsing onto its `"scene"`
fallback. Per-archetype fixtures jobs will not collide on output names.

## Not covered here

The walk also showed stair runs ending flush against solid walls, and a stair
rising into an uncut ceiling slab. Those are Deli Counter greybox composition,
upstream of everything above, and nothing in this document bears on them. They
have not been measured yet and no mechanism is proposed for them. `cr_deli`'s
stair is already open in `WALKABLE_SITE.md`; whether these are the same defect
is unknown and should not be assumed.
