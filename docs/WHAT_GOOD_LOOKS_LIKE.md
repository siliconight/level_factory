# What a good level is, according to this pipeline

**2026-08-06, overnight.** Written after the first walkable multi-building
site, and after that walk showed stairs into ceilings, holes in walls and an
unreachable objective.

## How to read this

The brief was "what does fun and playable mean, without guessing." So this
document does not open with a theory of fun. It opens with the observation that
**this repo already contains a theory of what a good level is** -- a detailed,
opinionated, genre-specific one -- written down across roughly twenty gates and
audits by people who had clearly thought hard about it, and never collected in
one place. Recovering it is not guessing. Inventing a replacement would be.

Three labels are used throughout and never mixed:

- **RECOVERED** -- a design belief quoted verbatim from the codebase, with
  file:line. The authors' words, not mine.
- **MEASURED** -- something computed today, with the actual numbers and where
  they come from.
- **PROPOSED** -- mine, or general genre convention. Labelled every time. Any
  proposal that cannot be turned into a check is marked as such rather than
  dressed up.

Every quote below was extracted by reading the source this session. The four
source reports are in `/tmp/plan/{combat,traversal,site,world}.md` and carry the
full citations; this document is the synthesis.

---

## Part 1 — The theory that is already here

### Pillar 1: A level is a graph, and loops are the whole game

> "Zero loops = a tree = every fight is a one-corridor siege; players can never
> flank, AI can never surprise. **Interior loops are the single biggest lever.**"
> — `deli_counter/combat_audit.py:9-11` — RECOVERED

This is the most load-bearing sentence in the repository. Almost everything
else in the combat model is downstream of it. A tree-shaped building has one
way to everything; a looped building has choice, and choice is where tactics
live.

> "opposite-face entries create the strongest flank geometry"
> — `combat_audit.py:750-752` — RECOVERED

### Pillar 2: Quality is genre-relative, not universal

> "A heist drill room WANTS 2-3 coverable entries (the PayDay holdout rule);
> demanding >= 3 ingress there would contradict the heist grammar."
> — `combat_audit.py:646-650` — RECOVERED

This is unusually sophisticated and worth protecting. The pipeline explicitly
refuses to apply one "good level" standard everywhere: a drill room is *meant*
to be defensible, so the rule that would improve a lobby would ruin it. Any
future rule must ask "good for what role" before "good".

> "A heist is a loop, not a line: get in, do the thing under pressure, get the
> bags out. **The map succeeds if PLANS differ between crews and runs.**"
> — `deli_counter/docs/DESIGN_RULES.md:20-21` — RECOVERED

That last clause is the closest thing to a definition of success in the repo.
Not "the map is fair" or "the map is pretty" — *plans differ*. Replayability
through planning variety is the stated goal.

### Pillar 3: The escape is half the heist, and it must not be the entry backwards

> "the escape should not rewind the entry. If the extraction sits where the crew
> spawned AND the bearing home is the bearing in, the second half of the heist is
> the first half played backwards."
> — `lot/site_audit.py:9-12` — RECOVERED

> "every critical leg (spawn->objective, objective->extraction) needs
> punctuation. A long leg with zero cover in its corridor is an open-ground
> sprint, not a fight."
> — `lot/site_audit.py:20-22` — RECOVERED

> "if the only way out is a pinch, the exfil is a turnstile under fire"
> — `deli_counter` `H_CARRY_PINCH` — RECOVERED

### Pillar 4: A living world is purpose, use and change — not object count

> "A living environment is not one that contains the most objects. It is one
> where architecture, props, textures, light, wear, sound and movement all
> suggest that the space has a purpose, has been used, and is changing over
> time."
> — `patina/docs/DRESSING_CHECKLIST.md:453` — RECOVERED

That is a better answer to "what does a detailed live world look like" than
anything I would have written, and it is already in your repo.

> "Light in DELCO comes from the sun or from physical fixtures — never from
> nowhere." — `zoo/README.md:121` — RECOVERED

> "Every light performs a role: general visibility, navigation, landmark
> emphasis, functional explanation, mood, gameplay readability, faction
> identification, narrative state. **Remove lights with no role.**"
> — `DRESSING_CHECKLIST.md:216` — RECOVERED

> "Do not use props to hide weak architecture. Fix the shell first."
> "Empty space is an intentional design tool."
> — `DRESSING_CHECKLIST.md:94`, `:332` — RECOVERED

> "THE RULE. Dressing never sits where the player will stand, shelter, or look."
> — `patina/patina/gameplay.py:3` — RECOVERED

### Pillar 5: The tools make models, not fun — and they know it

> "These are intel for the gameplay engineer, NOT judgments — the tool makes
> models, not gameplay... Only reachability is a hard model-integrity gate."
> — `tactical.py:476-480` — RECOVERED

> "a structural estimate, not a measure of fun -- **walk it**."
> — `combat_audit.py:35-36`, repeated in four separate files — RECOVERED

This is the honest and correct position, and it explains why so much is
advisory. It is also, as Part 2 shows, the thing that has quietly gone wrong.

---

## Part 2 — The pattern: a proxy reported as a verdict

Four independent extractions, four different subsystems, one shape. In each
case the pipeline measures something **adjacent** to what matters, because the
adjacent thing is computable, and then reports the adjacent result under the
name of the thing that matters.

| what matters | what is measured | the gap |
|---|---|---|
| can a human climb this stair | do the floor polygons connect, lower↔upper | **headroom is never checked** |
| can players flank | how many room-disjoint routes exist | no route *bearing* — two routes 10° apart count as two flanks |
| can the crew get out under fire | does one path edge exist to extraction | no length, no route count, no width, no pressure |
| can a player orient by eye | props were placed, lights were mounted | **no landmark is ever tested for visibility** |

This is the same defect this session spent all day on, one level up. `res://C:/`
refs were never loaded, so nobody saw them. A lineage guard compared a field one
side never had, so it never fired. `ok = True` meant "the stairs traverse" and
was read as "the level works". In every case the instrument was pointed slightly
beside the target and the reading was trusted.

**MEASURED — the sharpest single instance.** `agent_contract.json:33` ratifies
`min_headroom_m: 2.0`. It has **zero consumers repo-wide.** There is no
`min_headroom()` accessor beside the existing `min_door_width()` and
`min_corridor_width()` (`agent_contract.py:84-90`). All 34 tests in
`test_stair_clearance.py` are planar. `circulation.stair_volume` spans
`z_lo=-1e6, z_hi=1e6` — that is prop exclusion, not clearance. The only
implicit vertical guard is Recast's `nm.agent_height = 1.8` in `nav_gate.gd:116`
— which uses **1.8, not the ratified 2.0**, surfaces failures as "disjoint
islands" rather than as a headroom finding, and is skipped entirely when Godot
is absent.

A ratified number with no reader is a decision the team made and the pipeline
never learned. That is why you walked into a stair that rises into a ceiling
while `nav_gate` reported both stairs `status: ok`.

---

## Part 3 — The four absences that matter, ranked by evidence

**1. Headroom. (Traversal.)** Stated in the contract, measured nowhere. Directly
explains a defect you photographed. Cheapest to fix of the four and the only one
where the number is already ratified and merely unread.

**2. The escape. (Site.)** `scale_guidelines.md:83-85` says a heist needs "a
bag-movement route, a secondary route... and an escape route". At site scale the
exfil is checked only for *existence of one declared path edge*
(`site_tactical.py:199-208`). The `≥2 approaches` gate applies to the objective
only. `S_ONE_APPROACH`, `S1` spine pacing and the responder-arc check all measure
`spawn→objective` and stop. There is no site-scale equivalent of
`H_CARRY_PINCH`. **The half of the heist the genre defines as the climax is
measured only for connectivity.**

**3. Flanking bearing. (Combat.)** It is the thesis — `combat_audit.py:10`, `:18`,
`:750-752`, `pvp_heist.py:346-348` — and nothing computes an approach angle
inside a building. What exists is a face-set membership test and a room-disjoint
path count *explicitly labelled* "a proxy for 'flanking options'"
(`tactical.py:287`). The bearing mathematics **already exists** at site scale —
`site_audit.py:126-133`, used for `RESPONDER_ARC=150°` and horde spread `<120°` —
and has never been lifted to the building layer, despite `site_tactical.py:6-11`
framing the two layers as the same ideas at two scales.

**4. Landmark visibility. (World.)** Landmarks are placed by centroid arithmetic
and given a 2.5 m keep-out sphere. No raycast, no sightline test, no
thumbnail/greyscale/blur separation test exists. `level_design.py:206` hands the
visual half away — "the art team makes it visually distinct" — and the three
tests specified to measure it (`CONTRAST_DIRECTION.md:241-256`) were never
built. Orientation-by-eye is asserted everywhere and measured nowhere.

**Named as absent, and then corrected — see Phase 4.** Sound has zero mechanism
despite appearing in the definition of "alive"; animated motion is assigned to
Lux/Zoo, and Lux ships only light flicker while Zoo ships static meshes; NPC
life does not exist as a concept; time of day is an API stub.

I first listed these as gaps in Level Factory. They are not. They are authored
outside LF, and LF's job is to emit a world they can be attached to. The real
question is not "why does LF not make sound" but **"does a level leave LF
carrying what the audio pass needs to work on it"** — and that question is
unanswered rather than answered badly. Phase 4 says how to answer it.

---

## Part 4 — What "fun and playable" means here, in checkable terms

**PROPOSED.** This section is mine, built on Part 1. Each line is written so it
could become a check, because a design goal that cannot be checked will drift
back to advisory and then to decoration — which is the failure mode of every
gate in Part 2.

**Playable** — the floor of the thing. Not fun, just not broken.
1. Every objective is reachable from every spawn. *Measured today, advisory,
   fails on 107 of 137 shells.*
2. Every route a human is meant to take has 2.0 m of headroom. *Ratified,
   unmeasured.*
3. Nothing the player must pass through is narrower than the carry width.
   *Measured inside a building, absent at site scale.*
4. The navmesh is one island where the design says it is connected. *12 islands
   on `final_stand` today, reported as `ok`.*

**Fun traversal** — PROPOSED, from Pillar 1 and the traversal report.
5. **Loops, not trees.** At least one interior loop per building above a size
   threshold; at least one site-scale loop. The repo already calls this the
   single biggest lever and already counts loops — it just never requires one.
6. **Choice under pressure.** ≥2 routes between spawn and objective *that arrive
   from different bearings* — the fix for absence #3, and it makes #5 mean
   something rather than counting two corridors that run side by side.
7. **Vertical choice is real choice.** A ladder or stair that only serves one
   route is scenery. Count vertical links that participate in ≥2 distinct routes.
8. **Movement should be comfortable where it is mandatory and awkward only where
   that is the point.** The repo already distinguishes these — `site_steps.py:65-70`
   only counts a kerb as a defect where circulation crosses it. Extend that
   principle: steepness, crouch-height entries and pinch widths are findings *on
   critical legs* and flavour elsewhere.

**A world that feels alive** — PROPOSED, from Pillar 4, which is already better
than anything I'd write.
9. **Every space answers "what is this for".** Patina's checklist asserts this;
   nothing checks it. The cheapest proxy: every room has at least one prop whose
   category matches the room's declared role.
10. **You can navigate by eye.** At least one landmark visible from each critical
    leg — a raycast, which is exactly the test `CONTRAST_DIRECTION.md` specified
    and nobody built.
11. **Light explains the space.** Lux already blocks on fixtures floating or
    dark. Extend to the stated rule: a light with no role is removed.
12. **Wear implies use.** The one genuinely unmeasurable item in this list, and I
    am marking it so rather than inventing a metric. It stays a human review
    question.

---

## Part 5 — The plan

Ordered by *evidence strength × cost*, not by ambition. Every step has a
falsifier, because the last two patches this session both needed a repair patch
and both would have been caught by stating the falsifier first.

### Phase 0 — Stop lying (days)

The pipeline currently reports success over 880 warnings and 107 unreachable
objectives. Nothing else is worth building on top of a verdict that is not true.

**0.1 Give `min_headroom_m` a reader.** Add `min_headroom()` beside
`min_door_width()`. Check stair and corridor volumes against it.
*Falsifier: `final_stand`'s blocked stair must produce a finding. If it does
not, the check is looking in the wrong place.*

**0.2 Split `ok`.** `nav_gate.gd` sets `ok = true` from stair traversal alone.
Rename to `stairs_ok` and add `navigable` = stairs pass AND every marker
reachable AND island count is 1. Do not change what blocks yet.
*Falsifier: `final_stand` reports `stairs_ok: true, navigable: false`.*

**0.3 Report the census in the run.** `library_census.py` and `library_clean.py`
exist and are the first honest picture of the library. A number nobody sees
becomes a number nobody acts on.

### Phase 1 — Stop shipping known-bad buildings (days)

**1.1 Slot coverage as a selection rule.** CONFIRMED tonight: `pharmacy_a02`
(137 slots, 9 modules) is solid; `final_stand` (9 slots, 0 modules) has the
holes. A themed lot must not select a shell with empty slot coverage — 13 of 136
excluded, no threshold invented, because 0-coverage is measured-bad and
128-coverage is measured-good and *the boundary between them is not known*.

**1.2 Reachability as a selection rule.** Combined with 1.1 that leaves **7
shells across 7 families** — enough for a five-family lot. Note the trap this
already avoided: reachability *alone* selects `rowhouse_raid` (1 slot),
`harbor_score` (3), `07_police_station` (4), `stop_n_go` (5) — the least
themeable buildings in the library. The two rules are only safe together.

*Falsifier for both: a themed lot built under these rules, walked, shows no
wall holes. If it still does, slot coverage was not the cause and 1.1 goes.*

### Phase 2 — Make the stated thesis real (weeks)

**2.1 Lift bearing to the building layer.** The maths is at
`site_audit.py:126-133`. Two routes to an objective count as distinct only if
their final approach bearings differ by more than a threshold. This converts
absence #3 into a measurement and makes "flanking", the repo's own thesis,
checkable for the first time.

**2.2 Measure the escape.** Mirror the spawn→objective machinery onto
objective→extraction: route count, cover punctuation, carry width, bearing
distinctness from the entry. `site_audit.py:9-12` already says what good looks
like; nothing implements it.

**2.3 Require a loop.** Buildings above a size threshold must have ≥1 interior
loop. The counter exists; the requirement does not.

### Phase 3 — Legibility (weeks)

**3.1 Landmark raycast.** Build the test `CONTRAST_DIRECTION.md:241-256`
specified and nobody built: from sample points along each critical leg, is any
landmark visible?

**3.2 Room purpose proxy.** Every room has ≥1 prop matching its declared role.

### Phase 4 — The handoff: build the stage, not the performance

**Corrected 2026-08-07 by B$, and the correction matters enough to keep the
original wrong version visible.**

I first wrote this phase as "sound, animated motion, NPC life and time of day
are absent from the pipeline, and that is a months-long product call." That
mistook Level Factory's job. Those things are authored **outside** Level
Factory. LF's role is to build the world they get attached to.

Which turns a vague roadmap item into a sharp, checkable one:

> **Level Factory succeeds when a level arrives carrying everything the
> downstream systems need in order to be attached to it — and fails silently
> when it does not, because the audio pass, the AI pass and the lighting pass
> will each discover the gap separately, weeks apart, and each will assume it is
> their own problem.**

That is the same defect shape as the rest of this document, moved to the
boundary between teams. It is also the most expensive place for it to happen,
because the cost is somebody else's week.

**MEASURED — LF already emits a substantial contract.** This is not a greenfield
problem. `merge_gameplay` produces a site-level document carrying `markers`,
`rooms`, `objectives`, `loot`, `zones`, `vertical_links`, `openings` and
`surfaces`, all world-space and namespaced. `<id>.lights.json` carries light
anchors with roles. Dispatch emits `gameplay_anchors.json`,
`navigation_hints.json`, `proposed_beat_graph.json` and
`runtime_ownership_requirements.json`. `interactives.py` exists. The stage is
already partly built and partly described.

**What is NOT known, and must not be guessed:** whether that contract is
*sufficient* for the teams consuming it. I do not know what your audio system
needs to place reverb zones, what your AI needs to author patrols, or what your
time-of-day system needs to distinguish an interior from a lit exterior. Writing
a list here would be inventing requirements on behalf of people who have them
already.

**So the first step of Phase 4 is not code. It is one question to each
downstream team:** *what do you need from a level that you currently have to add
by hand?* Every hand-added thing is either a gap in the contract or a thing LF
should be emitting. That answer is data, and it is cheap to get.

**Then the checkable form** — PROPOSED, and only meaningful once the above is
answered:

- **The contract is complete or the build says so.** Whatever the downstream
  list turns out to be, every item becomes a per-room or per-site assertion:
  this space declares its material surfaces, its enclosure, its mount points,
  its exterior openings. A room that declares none is not "undressed" — it is
  a room the audio pass will silently skip.
- **Anchors are checked for usability, not just presence.** The lesson of
  `min_headroom_m` — ratified, never read — and of the landmark keep-out sphere
  that is placed and never raycast. An anchor nothing can attach to is the same
  defect one layer over.
- **The handoff is walked, not just written.** `HANDOFF.md` and the manifests
  are generated today. Nothing confirms a consumer can act on them. The cheapest
  version of that check is the one this session kept relearning: have somebody
  downstream actually load it, once, before declaring the interface good.

---

## Part 6 — What I am not claiming

I have not played this game. Nothing here is validated against a player, and
every proposal in Parts 4 and 5 is a hypothesis about fun expressed as a check
— which is exactly the substitution Part 2 warns about. The mitigation is that
each is falsifiable and each is labelled.

The repo's own instruction is the right one and it is repeated in four files:
**"a structural estimate, not a measure of fun -- walk it."** Everything above is
in service of making the walk *worth doing* by removing the defects that
currently dominate it. None of it replaces the walk.

The single number that would tell you whether any of this worked — interventions
per level, before and after — has still never been counted. That remains the
most valuable unbuilt instrument in the project.
