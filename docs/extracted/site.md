# The SITE and the MISSION: the theory of a good heist level, recovered from the pipeline

Scope: the multi-building space, the routes across it, pacing, the objective/spawn/extraction
relationship, and the heist structure itself. Sources are `lot/` (the site assembler),
`level_factory/packages/pipeline/` (the candidate producer), and `deli_counter/` where its docs
speak to what a heist *is* rather than to interior rooms.

Repo root on device: `C:\Projects\gabagool_studios\gabagool_factory`. Paths below are
repo-relative.

A note on layering that governs everything below, stated in the site assembler's own README:

> "This repo owns sites: buildings, routes, cover, spawns, and the walkable scene. The last tool
> that can still change the geometry, so most guardrails belong here. **It does not decide what a
> fight feels like — it decides what the ground affords.**"
> — `lot/README.md:10-11`

---

## 1. ASSERTED DESIGN INTENT

Verbatim statements about what makes a SITE or a MISSION good. Grouped by claim.

### 1.1 What a site *is*, and why it must be several buildings

> "Deli Counter makes one monolithic, deterministic building per spec. **A PAYDAY-scale heist is
> several buildings with space between them.** Lot is the sibling tool that COMPOSES already-built
> Deli Counter buildings into a site"
> — `lot/lot.py:4-6`

> "Lot composes several already-built Deli Counter buildings into a single **site** — a PAYDAY-scale
> compound of multiple buildings with space between them — which a single Deli Counter spec cannot
> make"
> — `lot/README.md:15-18`

> "Deli Counter makes the buildings; Lot composes them into a PAYDAY-scale **site** and lets you
> walk it. **A heist level = 1–4 Deli Counter buildings = one Lot site.**"
> — `lot/README.md:64-65`

> "Buildings are atoms; the site spec is the molecule."
> — `lot/README.md:33-34`

The scale of "space between them" is asserted as a quality, not a convenience:

> "Clear ground between two neighbouring shells, in metres. Wide enough to move down and to fight
> across once the navmesh has eroded both edges by the agent radius, **and wide enough that the pair
> reads as two buildings on a street rather than one damaged block.**"
> — `level_factory/packages/pipeline/site_variation.py:76-79` (defining `STREET = 8.0`)

### 1.2 The heist as a shape: get in, do the thing under pressure, get out

The clearest statement of the genre's structure in the whole pipeline:

> "**A heist is a loop, not a line: get in, do the thing under pressure, get the bags out. The map
> succeeds if PLANS differ between crews and runs.**"
> — `deli_counter/docs/DESIGN_RULES.md:20-21`

And the checklist of parts a heist level is expected to contain:

> "**A good heist has: casing/entry area, public area, restricted staff area, security room,
> objective room, loot/vault/stash, a bag-movement route, a secondary route, responder entry points,
> a holdout area, and an escape route.**"
> — `deli_counter/docs/scale_guidelines.md:83-85`

Adjacent: the heist canvas and route-length ambitions.

> "### heist (crew objective box) / Smaller than a route map but dense and reusable — **players loop
> through the same spaces completing objectives, moving loot, and escaping.** Best first canvas:
> 128 × 128 m."
> — `deli_counter/docs/scale_guidelines.md:69-73`

The mode's own definitions, at site scale:

> "`heist` — `spawn → objective → extraction` must be path-connected."
> — `lot/README.md:157`

> "heist : traverse spawn -> objective (+ dwell to do the objective) -> extraction"
> — `lot/site_pacing.py:29-31`

> "Roles: which building you start at, which one holds the objective, which one you leave from. On a
> one-building site all three collapse onto it, which is correct rather than degenerate."
> — `level_factory/packages/pipeline/site_variation.py:136-138`

### 1.3 The exfil must not be the entry played backwards

The single strongest site-scale assertion about route shape:

> "  EXFIL SHAPE   PayDay: **the escape should not rewind the entry.** If the extraction sits where
> the crew spawned AND the bearing home is the bearing in, **the second half of the heist is the
> first half played backwards.**"
> — `lot/site_audit.py:9-12`

Stated again in the finding text itself:

> "extraction sits {near:.0f} m from the crew spawn and {ang:.0f} deg off the entry bearing: the
> exfil rewinds the entry -- the second half of the heist is the first half backwards. **Move the
> extraction to a different edge or corner of the site.**"
> — `lot/site_audit.py:170-174`

The producer encodes the same intent when it assigns roles:

> "**Prefer an extraction that is not the spawn, so the route crosses the site.**"
> — `level_factory/packages/pipeline/site_variation.py:142`

And the site lint states it as a *pull*, an economic requirement rather than a geometric one:

> "  S2 extraction pull  **extraction is a REAL second trip:** away from the attacker spawn, outside
> every building footprint, inside the ground"
> — `lot/site_layout_lint.py:11-13`

Failure text: `"S2 extraction {d_ext:.0f}m from attacker spawn (< {EXTRACT_MIN:.0f}m: **no loop,
spawn-camp exit**)"` — `lot/site_layout_lint.py:108-109`.

### 1.4 Pressure: waves must change direction, and must not land on the anchors

> "  RESPONDER     PayDay: **assault waves should arrive from spread directions.**
>   PRESSURE      **Responders bunched in one arc = every wave is the same wave;** a responder spawn
>                 on top of the exfil = **spawn camping by construction.**"
> — `lot/site_audit.py:13-16`

> "all {len(resp)} responder spawns arrive from a {spread:.0f} deg arc around the objective: **every
> assault wave is the same wave. Spread spawns so pressure changes direction between waves.**"
> — `lot/site_audit.py:188-191`

> "a responder spawn sits {d:.0f} m from the {kind}: **waves materialize on top of the anchor --
> spawn camping by construction.** Keep responder spawns >= {CAMP_RADIUS:.0f} m from both anchors."
> — `lot/site_audit.py:199-202`

The absence of pressure entirely is called out as a structural gap in the heist:

> "no responder_spawn markers: **the heist has no escalation pressure layer at site level.**"
> — `lot/site_audit.py:205-206`

Escalation staging is explicitly assigned to the site, not the building:

> "**JUDGMENT:** escalation staging (where responders arrive as waves build — **site-level, Lot's
> `responder_spawn` markers own it**); which walls should be soft (drama says: the one the crew
> doesn't expect); civilian placement."
> — `deli_counter/docs/DESIGN_RULES.md:49-51`

### 1.5 The endpoints of the run want a backstop

> "  SAFE ANCHORS  L4D2: **the run's endpoints (crew spawn, extraction) want a backstop** -- cover or
> a building edge to fight from. **A naked anchor in open ground is a shooting-gallery
> start/finish.**"
> — `lot/site_audit.py:17-19`

> "the {kind} at ({pt[0]:.0f}, {pt[1]:.0f}) has no cover or building edge within
> {ANCHOR_RADIUS:.0f} m: **a naked anchor in open ground -- the hold there is a shooting gallery.**
> Give it a backstop (cover cluster, alcove, or wall)."
> — `lot/site_audit.py:216-219`

### 1.6 Every leg of the run needs punctuation

> "  LEG RHYTHM    L4D2: **every critical leg (spawn->objective, objective->extraction) needs
> punctuation. A long leg with zero cover in its corridor is an open-ground sprint, not a fight.**"
> — `lot/site_audit.py:20-22`

> "the {label} leg is {L:.0f} m with zero cover in its {LEG_COVER_RADIUS:.0f} m corridor: **an
> open-ground sprint, not a fight. One or two cover pieces along the line give the leg a rhythm.**"
> — `lot/site_audit.py:233-236`

### 1.7 Streets are exposure moments, and that is a decision the author makes

> "  STREET CROSS  CQB, site-scale: **a road is a long sightline both ways; every critical-leg
> crossing is an exposure moment.** Reported so the author places cover or accepts the dash."
> — `lot/site_audit.py:23-25`

> "the {label} leg crosses a road: a long sightline both ways at the crossing -- an exposure moment.
> **Cover near the crossing or accept the dash.**"
> — `lot/site_audit.py:245-248`

### 1.8 The approach must not be a single funnel; one angle must not hold everything

> "  S5 approach spread  **the objective building's path neighbors approach from >= 90 degrees
> apart, so one defender angle cannot hold every approach**"
> — `lot/site_layout_lint.py:18-20`

> "one route from '{sb}' to '{ob}' across the site graph: **the approach is a single funnel between
> buildings.**"
> — `lot/site_audit.py:277-279`

> "  S4 lane structure   **3-8 building-graph edges (FPS lane canon: 3-4 lanes, chokepoints not all
> coverable from one spot)**"
> — `lot/site_layout_lint.py:16-17`

The building-interior version of the same rule, which the site layer explicitly echoes:

> "**H_ONE_ROUTE — plans must be able to differ.** If every route from the entries to the objective
> passes through the same interior rooms, **there is exactly one plan and every run is that plan.**"
> — `deli_counter/docs/DESIGN_RULES.md:23-26`

And the site's own statement of that echo:

> "`assault` — the `objective` building must be reachable by **≥2 distinct approaches** (multiple
> routes in — **the site echo of an assault objective room needing ≥2 access**)."
> — `lot/README.md:152-155`

For the PvP profile, the same requirement is a hard gate with prose intent:

> "pvp_heist: objective building '{obj}' has {n} approach route(s); pvp_heist requires >= 2 distinct
> attacker approaches (declare another path to it)"
> — `lot/site_tactical.py:230-233`

> "**PVP-ROUTES: only one room-disjoint attacker route to the objective; pvp_heist requires at least
> two meaningfully different routes** (add an entrance, breach, or vertical route)"
> — `deli_counter/pvp_heist.py:288-290`

### 1.9 Isolation is the site echo of "no isolated rooms"

> "**Intel** (never fails the build), emitted into the site `gameplay.json` under `tactical`: the
> site connectivity graph, **isolated-building detection (the site echo of Deli Counter's 'no
> isolated rooms')**, spawn→objective distance, and the count of distinct approaches to the
> objective."
> — `lot/README.md:135-139`

> "    Deli Counter:  reachability + modes  within a building   (rooms, doors)
>     Lot:           reachability + modes  across the site      (buildings, paths)
> Same two ideas, one scale up."
> — `lot/site_tactical.py:9-11`

### 1.10 A building the crew cannot get into is a sealed box at site scale

> "But a building that's fine alone can become unenterable in a COMPOUND: its only door faces the
> perimeter wall, or a neighbour is parked against that face, or it sits in dead space with no path
> leading to it. **Assembling buildings you can't get into is the site-scale version of shipping a
> sealed box -- and only Lot can see it, because only Lot knows the placements.**"
> — `lot/site_enterability.py:4-10`

The governing rule of the whole layer, stated here:

> "Same rules as the rest of the toolchain: **GATE THE CLEAR-CUT CASE, WARN THE REST, and never
> auto-fix** (we don't move your doors or reroute your paths -- we tell you)."
> — `lot/site_enterability.py:12-14`

### 1.11 Why buildings should differ — the strongest statement in the corpus

> "The variation here is **deliberately structural, not cosmetic. Yaw is what changes a building's
> relationship to the street: which face carries the entrance, which side the ladder climbs, whether
> the approach is across open ground or along a wall. Stagger changes sightlines down the row.** A
> metre of random jitter would have made the hashes differ while leaving the level identical to play,
> which is precisely the failure this module exists to prevent — **passing a diversity gate is not the
> goal, being different levels is.**"
> — `level_factory/packages/pipeline/site_variation.py:16-21`

The failure it was written against:

> "Nothing was using any of it. Every candidate was handed the same evenly-spaced, zero-rotation row,
> so **five seeds produced five byte-identical sites and the candidate mechanism was decorative —
> five choices that were one choice, offered to a human as though the choosing meant something.**"
> — `level_factory/packages/pipeline/site_variation.py:11-14`

Why the cardinals and not arbitrary yaw — a legibility argument:

> "Cardinal yaws only. **A building is a rectangle on a lot, and 15-degree increments read as a
> mistake rather than as a choice;** the cardinals rotate which facade fronts the street without
> making the block look damaged."
> — `level_factory/packages/pipeline/site_variation.py:46-48`

> "Across-row stagger. **This is the one that changes sightlines: a staggered row breaks the single
> long firing lane a flush row creates.**"
> — `level_factory/packages/pipeline/site_variation.py:58-60`

And that variety must be of *archetype*, not of authoring:

> "**VARIANTS ARE NOT VARIETY.** `deli_a01`, `deli_a02` and `deli_a03` are three authorings of one
> archetype; a lot of all three is item 37 wearing a different hat. **Selection is by FAMILY first,
> then a variant within it.**"
> — `level_factory/packages/pipeline/building_library.py:20-23`

> "Item 37: `_write_site_spec` measures one `shell.glb` and gives it N placements, **so a
> four-building site is one building four times and stairs and ladders land identically in every
> one.**"
> — `level_factory/packages/pipeline/building_library.py:3-5`

A mixed row is asserted to need per-gap spacing, for a reason about how the space reads:

> "A row of DIFFERENT buildings cannot share one spacing: **the gap a stadium needs would strand a
> deli in forty metres of empty street, and the gap a deli needs would put the stadium through its
> neighbour.**"
> — `level_factory/packages/pipeline/site_variation.py:115-118`

> "**Deli Counter ships 41 archetypes, and a deli beside a stadium breaks the assumption.**"
> — `level_factory/packages/pipeline/building_library.py` / `site_variation.py:207-208`

The acceptance test for the walkable site names the visible outcome:

> "4. **Five architecturally different buildings are visible and enterable**, themed, not five copies
> of one."
> — `level_factory/docs/WALKABLE_SITE.md:99-100`

And a shortfall is asserted to be a *different brief*, not a smaller one:

> "**A lot that cannot be dressed is not a smaller version of the brief. It is a different brief, and
> nobody asked for it.**"
> — `level_factory/packages/pipeline/building_library.py:137-138`

### 1.12 The crew's first second is sacred

The spawn placer's whole thesis:

> "**A spawn goes on the street: outside every footprint, inside the ground rect, far enough from the
> crew that first contact is not immediate,** and at the ground plane rather than at an interpolated
> height."
> — `lot/site_spawns.py:19-21`

> "**The crew's first second is the only moment it has no cover, no information and no ability to
> react,** and that is the moment Laser Tag measures as `time_to_first_contact`."
> — `lot/site_spawns.py:284-287`

> "**The crew needs the fight to start after it has had a chance to move,** so the standoff is the
> range plus the ground the crew covers in the time it is being given. One second is the floor, not a
> target. It is roughly a human reaction plus a step, and **it is what separates 'the map opened with
> a shot' from 'the map opened'.**"
> — `lot/site_spawns.py:100-106`

An engagement sequence is asserted to be a spread, not a cluster:

> "**The even spread is the design;** the slide is the fallback for when it cannot be honoured.
> **Sliding forward rather than back means an enemy that cannot be placed fairly ends up deeper into
> the mission, never behind the crew.**"
> — `lot/site_spawns.py:315-317`

> "Enemies closer together than this are **one encounter wearing six hats.**"
> — `lot/site_spawns.py:119` (defining `MIN_SEPARATION = 4.0`)

### 1.13 The defect is empty ground, not distance

The single most explicit "what a good site affords" statement in the codebase:

> "Lot's answer to an unfair opening engagement used to be arithmetic on distance: if an enemy could
> see the crew, move the enemy. That is the cheapest possible response and almost never the right
> one. Push a spawn far enough out and the map still grades badly -- now for a first contact past the
> ceiling and a crew that walks a minute before it meets anything -- and the site is no better than it
> was. **What made the opening unfair was that two markers could see each other across ninety metres
> of empty ground. The distance was the symptom; the empty ground was the defect, and the fix for
> empty ground is to put something in it.**"
> — `lot/site_cover.py:3-11`

> "**an enemy 20 m away around a corner is a fair fight and an enemy 30 m away down an open street is
> not** -- so distance alone is not what the search below tests"
> — `lot/site_spawns.py:80-82`

> "Which makes this Lot's job rather than the evaluator's. **Laser Tag can say the map plays badly
> and it cannot place a crate, because it does not own the geometry. Lot owns the geometry.** So a
> firefight evaluator's finding is a *soft* gate here: **it never refuses a build, it changes what the
> build contains.**"
> — `lot/site_cover.py:12-15`

Cover must be beside the lane, not in it:

> "The samples join the markers a piece has to stand clear of, so cover lands beside the lane instead
> of in it. **Cover the crew has to walk around is an obstacle; cover it can walk behind is cover.**"
> — `lot/site_cover.py:683-685`

The walk is a distinct thing from the opening:

> "**Marker pairs alone answer the opening and nothing else:** on seed 5017 every pair was answered
> and **the crew still crossed 74 m of bare approach, because the approach is not a marker pair.**"
> — `lot/site_cover.py:604-607`

> "Deliberately after the marker pass and on its own budget. **The marker lines describe who can shoot
> whom at t=0** and are the more urgent statement; sharing one allowance would let a site with nine
> long spawn lines spend everything before reaching the approach"
> — `lot/site_cover.py:672-677`

The approach bias states where cover belongs on a leg:

> "Where in the usable interval to sit, 0 being the crew's end. **A third of the way from the crew is
> deliberate: it gives the crew something to move between on its approach rather than handing the far
> end a wall to hold.**"
> — `lot/site_cover.py:135-138`

### 1.14 Pacing is honestly computable; fun is not

> "**Neither predicts 'fun' — fun is a feel property that only a playthrough reveals.** These describe
> STRUCTURE: how long the declared route takes, and where the geometry creates combat opportunity.
> Every number is an estimate from declared inputs, shown with its breakdown, **never a verdict.**"
> — `lot/site_pacing.py:4-8`

> "**WHY pacing is honestly computable (and fun isn't): duration is a function of distances +
> objective timings + mode structure — all declared or derived. 'How many minutes' is arithmetic.
> 'How tense' is not.**"
> — `lot/site_pacing.py:16-18`

> "**These are opportunities the geometry creates. Whether they make a good firefight is for the walk
> to tell you.**"
> — `lot/site_pacing.py:53-55`

> "geometric facts about each route leg (route choice, open ground, nearby cover). **Describes
> opportunity, not quality** — whether it plays well is for the walk to tell you."
> — `lot/site_pacing.py:295-297`

> "approaches : how many distinct path-routes reach the destination building (**more = more tactical
> choice; a fact, not a grade**)"
> — `lot/site_pacing.py:47-48`

The remedy vocabulary — what an author is expected to *do* with a pacing verdict:

> "So you might see *'~2.7 min, likely TOO SHORT vs target — travel 12s, objective 120s'* and respond
> by **spreading the buildings out, adding objectives, or lengthening the holdout** — in the same
> iterate-the-spec loop."
> — `lot/README.md:207-209`

> "Everything here is a structural estimate. **The audit exists to make the walk cheaper, not to
> replace it.**"
> — `deli_counter/docs/DESIGN_RULES.md:131-132`

> "**a walked site that plays well should sweep clean (gs_heist is the calibration site).**"
> — `lot/site_audit.py:27-28`; restated `lot/README.md:219-222`

### 1.15 Ground is a design object, not a backdrop

> "**Extra ground can never create a fall** -- the worst case is ground under a building that floored
> itself already... **A plate too small, by contrast, is a void.**"
> — `lot/site_extent.py:31-35`

> "Ground kept outside the outermost solid, in metres. **Not styling:** Godot erodes the navmesh by
> the 0.4 m agent radius at every geometry edge, from the plate rim as much as from a wall, **so a
> plate that stops flush with a building leaves a walkable strip of nothing and the building is an
> island again by a narrower route.** Four metres leaves ~3.2 m of navmesh to walk."
> — `lot/site_extent.py:48-52`

> "**Past this span a site is not a site, it is a placement bug** that would otherwise be honoured
> with a kilometre of ground."
> — `lot/site_extent.py:59-61` (defining `MAX_SPAN = 2000.0`)

> "What the player finds there is **a wall through a room, a doorway into solid geometry, and a
> navmesh with a hole in it where the two floors fight.**"
> — `lot/site_extent.py:401-403` (on overlapping buildings)

### 1.16 City grain exists to shape the approach

> "**City grain (`roads` + `blockers`)** — flat asphalt `roads` with optional raised sidewalks, and
> solid `blockers` (StaticBody3D massing you can't enter) **to wall streets and funnel the crew toward
> the heist fronts.**"
> — `lot/README.md:54-58`

> "Stepping off the ground onto a sidewalk is a 0.16 m rise. That is a wall to a stock
> CharacterBody3D... **It stays a wall on purpose; kerb cuts are what make the crossings legal.**"
> — `lot/site_steps.py:33-36`

### 1.17 The mission's nav hooks are standing positions, not marker positions

> "**A marker is where a thing IS. An anchor is where a body has to be able to stand to use it, and
> those are not the same point.** Deli Counter puts OBJECTIVE_CAGE at the cashier counter,
> LOOT_VAULT_CASH on the vault block"
> — `lot/lot.py:1490-1493`

> "A hook names a spot in a particular room; **walking it across the site to find open floor would
> trade a blocker for a mission that no longer happens where it was designed to happen.**"
> — `lot/site_spawns.py:151-154`

> "where the crew stages is a SITE concern"
> — `lot/lot.py:1112-1113`; echoed at `lot/site_pacing.py:134-138`

### 1.18 The whole thing must survive leaving the toolchain

> "the deliverable is a level shell that must work standalone in somebody else's Godot project with
> none of these tools present, and **these tools are not the authority on gameplay or networking**"
> — `lot/README.md:6-8`

> "**A passing structural score is never labeled fun, balanced, multiplayer-verified, network-ready,
> or shipping-ready.**"
> — `level_factory/README.md:91-92`

> "**Anything that only works because a repo here is on disk is an instrument, not a deliverable.**"
> — `level_factory/README.md:96-97`

> "A preview that is lit differently from the level is worse than no preview, **because it gets
> believed.**"
> — quoted in `level_factory/docs/WALKABLE_SITE.md:119-120`

---

## 2. MEASURED, WITH NUMBERS

Every threshold, its file:line, and where the number comes from.

### 2.1 Pacing (`lot/site_pacing.py`) — the mission clock

| Quantity | Value | Line | Origin stated |
|---|---|---|---|
| Target window | 7–15 min (`TARGET_MIN_S = 7*60`, `TARGET_MAX_S = 15*60`) | 70-71 | Asserted default; per-spec override via `pacing.target_minutes` (74-83) |
| `move_speed` | 4.0 m/s | 62 | "jogging player, conservative" (35) |
| `objective_secs` | 120 s per objective marker | 63 | "per objective marker (drill/hack/search)" (36) |
| `loot_trip_secs` | 25 s per loot marker | 64 | "grab + carry one way" (37) |
| `wave_secs` / `waves` | 35 s × 6 | 65-66 | survival holdout (38-39) |
| `setup_secs` | 30 s | 67 | "pre-objective approach/positioning" (40) |
| `skill_spread` | ±0.35 | 68 | "+/- fraction for the min/max band" (41) |

Composition of the heist estimate (`estimate_pacing`, 126-218): travel = leg distance ÷ move_speed
summed over `spawn→objective→extraction` (158-164); + `setup_secs` (167-168); +
`n_objectives × 120` where `n_obj = max(1, count of 'objective' markers in the objective building)`
(171-178); + `n_loot × 25` (179-184); survival adds `waves × wave_secs` (187-192). Band is
`base × (1 ± 0.35)` (194-195). Verdicts: `"likely TOO SHORT vs target"` if `hi < tlo`, `"likely TOO
LONG vs target"` if `lo > thi`, `"partly outside target (range straddles the window)"` otherwise
(198-204).

Route endpoints are refined by *site* markers when present — `crew_spawn` replaces the spawn
building's anchor, and `extraction` replaces the last leg's endpoint **for heist mode only**
(143-157).

Encounter intel per leg (`encounter_intel`, 280-298): `length_m` (straight-line building-to-building),
`approaches` (count of the destination's neighbours reachable from the start without passing through
the destination — `_distinct_approaches`, 224-244), `open_ground_m`, and `cover_near`.

- `open_ground_m` = leg length minus a **flat 12.0 m** cover allowance, "~6 m of near-cover at each
  end, capped" — `lot/site_pacing.py:255-258`. Explicitly an approximation: "we don't have footprints
  precisely, so we approximate building cover as a radius around each building origin" (249-251).
- `cover_near` counts declared cover pieces within a **10.0 m band** of the leg segment
  (`_cover_near_leg`, `band=10.0`, 261).

### 2.2 Site grammar audit (`lot/site_audit.py`) — constants at lines 46-52

| Constant | Value | Meaning as written |
|---|---|---|
| `LEG_COVER_RADIUS` | 6.0 m | "corridor half-width when counting leg cover" (46) |
| `LEG_BARE_MIN_LEN` | 20.0 m | "legs shorter than this may be bare" (47) |
| `ANCHOR_RADIUS` | 8.0 m | "backstop search radius around spawn/extraction" (48) |
| `BACKTRACK_ANGLE` | 35.0 deg | "tighter than this = same bearing" (49) |
| `BACKTRACK_NEAR` | 18.0 m | "spawn and extraction basically co-located" (50) |
| `RESPONDER_ARC` | 150.0 deg | "all responders inside this arc = one-note waves" (51) |
| `CAMP_RADIUS` | 12.0 m | "responder spawn this close to an anchor = camp" (52) |

Derived measurements:

- **Exfil rewind** fires only when BOTH `dist(spawn, extraction) < 18 m` AND the arc between
  `bearing(obj→spawn)` and `bearing(obj→extraction)` is `< 35°` — `lot/site_audit.py:165-174`. Heist
  mode only.
- **Responder spread** = `360 − max consecutive-bearing gap`, measured *around the objective*; flags
  when `spread < 360 − 150 = 210°` — 182-191.
- **Backstops** for the naked-anchor test = declared cover rects **plus** approximated building rects
  **plus** blockers — 155-156, `_building_rects` 91-108. Building footprints are approximated as a
  **conservative 8.0 m radius box around the anchor**: "Exact extents live in the built gameplay; at
  spec level a conservative box around the anchor is enough for backstop tests" (93-95, `r = 8.0` at
  99).
- **Horde spread**: `< 3` horde spawns is INFO; spread `< 120°` is MED — 250-267.

### 2.3 Site layout lint (`lot/site_layout_lint.py`) — constants at lines 35-41

| Constant | Value | Rule as written |
|---|---|---|
| `SPINE_MIN` | 40.0 m | "spawn->objective floor (no instant rush)" (35) |
| `SPINE_MAX` | 220.0 m | "spawn->objective ceiling (no marathon)" (36) |
| `EXTRACT_MIN` | 30.0 m | "extraction pulled away from attacker spawn" (37) |
| `LANE_MIN, LANE_MAX` | 3, 8 | "FPS lane canon: 3-4 lanes" (38, and 16-17) |
| `KILL_LANE` | 40.0 m | "uncovered straight leg" (39) |
| `COVER_NEAR` | 8.0 m | "cover counts if within this of the leg line" (40) |
| `SPREAD_MIN` | 90.0 deg | "angular spread of objective approaches" (41) |

Provenance stated in the header: "the level-design rules from **LAYOUT_RULES.md sections A/D**
applied to the site" — `lot/site_layout_lint.py:5-6`. Applies **only** to `mode == "pvp_heist"`
(line 66-68).

Which of these block: `S1 < 40 m` is a **fail**; `S1 > 220 m` is only a **warn**; `S2 < 30 m` is a
**fail**; extraction outside ground bounds is a **fail**; extraction inside a non-extraction
building footprint is a **warn**; `S3`, `S4`, `S5` are **warns** — lines 96-153, and `main()` exits
non-zero only on fails (182).

Ground bounds for S2 come from `site_extent.resolve(s).rect`, and the code explains why not from the
declared size: "Halving the declared size assumes the plate is centred on the origin, and a site
whose row is not centred fails S2 for markers that are standing on ground" — 72-79.

Building footprints for S2's inside-footprint test are read from the Deli Counter spec's
`footprint_x`/`footprint_y`, defaulting to **20.0 × 20.0** when the spec is absent — 44-50.

### 2.4 Ground extent (`lot/site_extent.py`)

| Constant | Value | Origin |
|---|---|---|
| `CLEARANCE` | 4.0 m | Derived from Godot's 0.4 m navmesh agent-radius erosion; "Four metres leaves ~3.2 m of navmesh to walk" (48-53) |
| `SNAP` | 1.0 m | "A plate whose extent is a rounded number is one a human can check against the spec by eye" (55-57) |
| `MAX_SPAN` | 2000.0 m | "past the limit... a placement error rather than a level" (59-62, 382-388) |
| `OVERLAP_TOLERANCE` | 0.5 m | Derived: "Deli Counter's exterior walls are 0.25 m, so half a metre is 'the cladding is kissing'" (72-75) |

The required rect is the union of *everything*: building footprints (rotation-aware, with non-cardinal
yaw bounded by its enclosing box — 147-167), blockers (default 12×12 — 204-205), courtyards (default
10×10 — 213-215), cover, paths (default width 3.0) and roads (default width **9.0**) grown by half
their width (232-242), and every site marker as a point (244-249) — then grown by `CLEARANCE`
(254-263).

Overlap severity is bimodal: depth `> 0.5 m` is **blocker** ("one of these walls is standing inside
the other's rooms" — 422-430); depth `≤ 0.5 m` is **minor** ("intentional terracing reads this way,
so it is reported rather than gated" — 431-436).

### 2.5 Enemy spawn placement (`lot/site_spawns.py`)

| Constant | Value | Origin as stated |
|---|---|---|
| `WALL_MARGIN` | 1.0 m | Godot 0.4 m agent radius erodes walkable surface from every solid; a spawn in the eroded band "has a floor and no navmesh polygon, which is UNREACHABLE_SPAWN" (33-37) |
| `EDGE_MARGIN` | 1.0 m | same at the site edge (39-40) |
| `MIN_STANDOFF` | 8.0 m | "**chosen by eye**"; explicitly demoted: "A floor, not the rule. It was written as the rule" (42-49) |
| `OPENING_RANGE` | 45.0 m | `LT_BotPlayerController`'s `@export var sight_range: float = 45.0` — the **crew's** reach, not the enemy's `enemy_sight_range = 35.0` in `default_laser_tag_scenario.tres` (51-84) |
| `CREW_SPEED` | 4.5 m/s | `LT_BotPlayerController.move_speed = 4.5` (91-92) |
| `REACTION_SECONDS` | 1.0 s | "roughly a human reaction plus a step" (94-107) |
| `OPENING_CLEARANCE` | 4.5 m | Derived: `CREW_SPEED × REACTION_SECONDS` (109-111) |
| `MAX_PUSH` | 80.0 m | "on a site whose buildings are 44 m across, the nearest street can be twenty-odd metres from the line" (113-116) |
| `PUSH_STEP` | 0.5 m | (117) |
| `MIN_SEPARATION` | 4.0 m | "one encounter wearing six hats" (119-120) |
| `SLIDE_STEP` | 0.05 (a 20th of the route) | "Perpendicular search alone cannot fix an opening engagement" (122-128) |
| `GROUND_Z` | 0.0 | Lot seats ground slabs so the top face is exactly z=0 (130-134) |
| `AGENT_CLIMB` | 0.5 m | "What a Laser Tag agent can step up without a ladder or a stair" (136-139) |
| `FURNITURE_MAX` | 2.0 m | Above this "the drop is a storey -- and Lot has no storey model" (141-146) |
| `AGENT_HEIGHT` | 1.8 m | "The pill Laser Tag walks" (148-149) |
| `RESOLVE_RADIUS` | 6.0 m | "clears the deepest counter Deli Counter bakes and still lands inside the room that counter is in" (151-156) |
| `RESOLVE_STEP` | 0.25 m | "coarse enough that a 6 m disc is a few thousand tests" (158-160) |
| default `enemy_count` | 6 | signature at 383-385 |
| default `lateral` kick | 1.5 m | signature at 384 |

The **fairness test** (`opening_engagement_is_fair`, 288-311) is a disjunction, not a distance:
`dist ≥ 45 + 4.5 = 49.5 m` **OR** a building stands between the two. Sample positions along the route
are `(index + 1) / (count + 1)` — the even spread (313-317). Candidates are priced in metres of
deviation and cheapest taken, so push and slide compete rather than being ordered by loop order
(326-352).

Occluders are the footprints at **margin=0.0**, deliberately not the navmesh-grown rects: "Occluding
with the grown rects would credit a metre of open street on either side of every wall as cover"
(419-422). Props are excluded entirely: "a sightline model that credits a planter with cover is worse
than one that admits it only knows about walls" (270-274).

### 2.6 Cover planning (`lot/site_cover.py`)

| Constant | Value | Origin as stated |
|---|---|---|
| `EYE_HEIGHT` | 1.4 m | `LT_BotPlayerController` sights from `body.global_position + UP * 1.4` (44-52) |
| `CHEST_HEIGHT` | 1.0 m | `LT_LineOfSightTester.CHEST_OFFSET = UP * 1.0` (44-52) |
| `MIN_COVER_HEIGHT` | **1.2 m** | **Derived, not chosen**: `(EYE + CHEST)/2` is where the two crossing sightlines meet (55-59) |
| `COVER_HEIGHT` | 2.0 m | "Two metres breaks the line over most of its length" (61-66) |
| `COVER_SIZE` | 3.0 m | "a 3 m block in a 12 m street leaves better than three metres of navmesh on each side" (68-72) |
| nav bake fallback | radius 0.4, cell 0.15 | equal to `deli_counter/agent_contract.json`'s `nav_bake` (74-78) |
| `MARKER_CLEARANCE` | 3.0 m | "A crate on a spawn is a spawn inside a solid, which is `UNREACHABLE_SPAWN`" (126-129) |
| `COVER_SEPARATION` | 6.0 m | "Two crates in contact are one wall, and a wall across a street is a route that no longer exists" (131-133) |
| `APPROACH_BIAS` | 0.35 | "A third of the way from the crew is deliberate" (135-139) |
| `SEARCH_STEP` | 0.02 m | (141-142) |
| `PERIMETER_THICKNESS` | 0.3 m | mirrored from `lot.WALL_THICK` (373-376) |
| `ROUTE_SAMPLE_SPACING` | 15.0 m | "The crew moves at 4.5 m/s, so 15 m is about three seconds of walking" (514-518) |
| `ROUTE_METRES_PER_PIECE` | 25.0 m | "twelve pieces is generous on a 40 m approach and nothing at all on a 250 m one" (520-523) |
| marker-pair cover `limit` | 12 pieces | `plan_cover` signature (585) |

Route cover budget = `ceil(route_length / 25)`, on a **separate allowance** from the 12-piece marker
budget (`plan_cover`, 680-682). Sightlines are re-measured after every placement, longest first
(590-593). `min_passable_gap` and `building_clearance` are derived from the nav bake rather than
pinned (81-124).

### 2.7 Site tactical gates (`lot/site_tactical.py`)

Hard gates, raising `SiteTacticalError`, only when a `mode` is declared (161-249):

- `assault`: route from spawn to objective **and** `_distinct_routes_to ≥ 2` (183-197).
- `heist`: `spawn→objective` and `objective→extraction` both path-connected (199-208). **No approach
  count required.**
- `survival`: `safe→objective` connected (210-215).
- `pvp_heist`: both legs connected, `≥ 2` distinct attacker approaches, **and** at least one
  site-level `attacker_spawn`/`crew_spawn` marker (217-248).

Post-merge PvP gates (`gate_merged`, 261-339):

- `DEFAULT_MIN_SPAWN_SEPARATION = 25.0` m between any attacker staging marker and any defender spawn;
  overridable via `site_spec["pvp"]["min_spawn_separation"]` — 258, 324-333, failure text: "attackers
  would start on top of the defense".
- At least one `defender_spawn` must exist in the merged site (285-288).
- **Protected hold**: defenders must spawn in the objective building, or in a building whose route to
  the objective survives deleting the attacker staging building — 316-338.

### 2.8 Producer-side placement (`level_factory/packages/pipeline/site_variation.py`)

| Constant | Value | Origin |
|---|---|---|
| `_YAW` | (0, 90, 180, 270) | cardinals only (46-49) |
| `_ALONG` | (−6, −3, 0, 3, 6) m | "closes the gap between a pair by up to 12 m" (51-56) |
| `_ACROSS` | (−10, −5, 0, 5, 10) m | stagger; "the one that changes sightlines" (58-60) |
| `CLEARANCE` | 4.0 m | matches Lot's own `CLEARANCE` (62-67) |
| `DEFAULT_FOOTPRINT` | 48.0 × 48.0 m | "Deli Counter's shells run 40-50 m on a side, so this is the top of that range" (69-73) |
| `STREET` | 8.0 m | clear ground between neighbouring shells (75-79) |
| default `spacing` | 45 m | `site_placements` signature (102-103) |

Derived spacing (`row_spacing`, 231-247): `ceil(longest_axis + 2 × 6 + STREET)`. Per-gap offsets for
mixed rows (`row_offsets`, 197-228): `gap = reach_a + reach_b + street + 2 × slack`, snapped to whole
metres, row centred on origin. Ground size (`ground_size`, 250-285) is bounded **over every seed**,
not computed for one: "all five candidates of a mission get the same plate and stay comparable to each
other" (256-260).

Reach is pessimistic on both axes because yaw is cardinal and a quarter turn swaps them (`_reach`,
186-194).

The failure these numbers were written against, with measurements:

> "the spacing was a constant 45 while the shells were 44 m wide, so a candidate whose nudges pushed
> two neighbours to the inside of their range **put 42 m between two 44 m buildings** and the pipeline
> assembled them interpenetrating."
> — `site_variation.py:236-240`

> "placements marched out along +x from the origin while `ground_size` returned a symmetric span from
> the building *count*, so the plate Lot centred on the origin sat about **66 m west** of the row it
> was supposed to carry. The last building on `category5_baie_dore_001` **overhung the plate by 44 m**,
> its ground hole was clipped out of existence, and the crew spawned on that building's interior floor
> as an island. **Laser Tag graded the map BROKEN on zero runs.**"
> — `site_variation.py:29-33`

### 2.9 Library selection (`level_factory/packages/pipeline/building_library.py`)

- `REQUIRED = (".glb", ".gameplay.json", ".slots.json")` (48) — all three or the archetype is not
  placeable. "A GLB missing its `slots.json` cannot be themed. It must **drop out HERE, at
  selection**, and not at compose" (14-17).
- `ART_REQUIRED = (".lights.json",)` (61) — **135 of the library's 138 shells** ship one (57-58).
- `deli_counter/build/` is "a flat directory of ~330 files" (7-8); "Deli Counter ships **41
  archetypes**" (`site_variation.py:207`).
- `pick_lot` draws families **without replacement**, then unused variants, then repeats (152-190) —
  "two delis beats one deli and a hole" (164-165).

### 2.10 Per-building art, measured (`level_factory/docs/PER_BUILDING_ART.md`)

Measured off a loaded scene, 2026-08-06. Shell footprints ranged **26.1 × 20.3 to 46.3 × 26.3 m**;
shell roofs **3.4 m to 12.7 m**. Every building's dressing bounding box was **exactly 30.4 × 8.4 ×
22.4 m** and every fixture box **exactly 30.5 × 3.7 × 17.9 m**. Three buildings had dressing standing
**+1.8 m, +3.8 m and +4.9 m above their own roofs**; on `pharmacy_a02` "the dressing footprint is
LARGER than the shell." — `PER_BUILDING_ART.md` table and surrounding text.

### 2.11 Interior heist grammar the site inherits (`deli_counter/`)

Numbers stated for heist rooms, which the site's objective building is expected to contain:

- **Holdout**: "2–3 coverable entries (1 is a camping closet, 4+ is indefensible), ≥ 12 m², and
  something to shelter behind" — `docs/DESIGN_RULES.md:32-37`.
- **Bag route**: "From every objective there must be a route to a **≥ 1.4 m** exterior egress using
  only **≥ 1.2 m** openings — stairs carry bags, ladders don't... If the only way out is a pinch, the
  exfil is a turnstile under fire." — `docs/DESIGN_RULES.md:39-43`.
- **First slice**: 50–90% band; ">97% no cover = the room is a formality; <35% = every entry is
  grenade-bait" — `docs/DESIGN_RULES.md:74-81`.
- **Flow rhythm**: room scale should change more than ~1.4× step to step — `docs/DESIGN_RULES.md:95-99`.
- **Heist canvas / route**: best first canvas 128×128 m; route length 150–350 m (small), 300–700 m
  (medium), 700 m–1.5 km (large) — `docs/scale_guidelines.md:69-79`.
- **Outdoor staging strip** 8–20 m deep; **escape/extraction room** 10×15 m; parking 30×50 m;
  residential street 8–12 m, big street 14–20 m — `docs/scale_guidelines.md:60, 82-83, 101-103`.
- `pvp_heist` spawn envelope: `SPAWN_MARGIN = 8.0` beyond footprint, `ROOM_MARGIN = 0.5`, with the
  comment "Lot owns true site-level placement" — `deli_counter/pvp_heist.py:42-48`.
- Coordinate tolerances for the whole pipeline: structural alignment 2 cm, gameplay-marker placement
  **5 cm**, floor elevation 2 cm, rotation 0.5°, seam gap 1 cm — `lot/COORDINATE_CONTRACT.md:58-67`.

### 2.12 Traversal underfoot (`lot/site_steps.py`)

The only step number in the corpus that is *derived* rather than declared:

> "for a capsule of radius R meeting a step of height h, the normal's vertical component is
> (R − h)/R, so the tallest step a body can walk up with no step-up assistance at all is
> `unassisted_step_max = R × (1 − cos(floor_max_angle))` which for Godot's default 45 degree floor
> angle and this stack's 0.4 m player capsule is **0.117 m**."
> — `lot/site_steps.py:6-13`

And the correction it makes to a declared contract:

> "`agent_contract.json` states `max_step_up_m: 0.5` as though the body were a box; **that number is
> what a controller can lift itself over, not what it can walk over.**"
> — `lot/site_steps.py:14-16`

Site surfaces: ground 0.00, sidewalk top **0.16 m** ("concrete, raised curb"); road/path/courtyard
thicknesses are derived from the limit rather than pinned, and must satisfy it in both directions —
`site_steps.py:18-30`. A measured drift: "COURT_THICK had drifted to 0.12 against a limit of 0.1025
-- a wall, on ballpark_block's own circulation" (29-30).

---

## 3. MEASURED BUT ADVISORY

Everything below is computed and reported and **never blocks the build**. The severity vocabulary
differs per module and is reproduced verbatim.

### 3.1 `site_audit.py` — the entire site grammar layer is report-only

Severity words: **HIGH / MED / INFO** (`site_audit.py:26`, counts at 283-287).

> "**Report-only, like combat_audit:** severities HIGH / MED / INFO, and a walked site that plays well
> should sweep clean"
> — `lot/site_audit.py:26-28`

> "`site_audit.py` is Deli Counter's `combat_audit --rules` continued at site scale... **Report-only;
> it prints at the end of every `lot.py` assembly**"
> — `lot/README.md:218-222`

Every genre-grammar finding in the corpus is therefore advisory:

| Code | Severity | Never blocks |
|---|---|---|
| `S_BACKTRACK` (exfil rewinds the entry) | **MED** | yes — 169 |
| `S_RESPONDER_ARC` (one-note waves) | **MED** | yes — 187 |
| `S_RESPONDER_CAMP` (spawn camping by construction) | **MED** | yes — 198 |
| `S_NO_RESPONDERS` (no escalation pressure layer) | **INFO** | yes — 204 |
| `S_NAKED_ANCHOR` (shooting-gallery start/finish) | **MED** | yes — 215 |
| `S_BARE_LEG` (open-ground sprint, not a fight) | **MED** | yes — 232 |
| `S_STREET_CROSS` (exposure moment) | **INFO** | yes — 245 |
| `S_FEW_HORDE` | **INFO** | yes — 255 |
| `S_HORDE_ARC` | **MED** | yes — 265 |
| `S_ONE_APPROACH` (single funnel) | **MED** | yes — 276 |

Note that **no site_audit finding is ever HIGH** — the severity exists in the counter (283) and no
call site emits it. The route-diversity check is additionally wrapped in a bare `except Exception:
pass` (280-281), so it can silently not run at all.

The clean-sweep message states its own limit:

> "clean -- **structural estimate, not a measure of fun; walk it**"
> — `lot/site_audit.py:299-300`

### 3.2 `site_layout_lint.py` — advisory by declaration, with a hard/soft split inside it

> "**Advisory layer: the engine gates (walktest, mp_smoke) stay the traversal truth.**"
> — `lot/site_layout_lint.py:24`

Vocabulary: `SITE-LINT-FAIL` / `SITE-LINT-WARN` (175-178). Fails do exit non-zero (182), but the
module states it is not the truth layer. Which side each rule falls on:

- **FAIL**: S1 spine `< 40 m` (98-100); S2 extraction `< 30 m` from attacker spawn (108-109); S2
  extraction outside ground bounds (110-112); missing `attacker_spawn` marker or objective (91-93).
- **WARN (never blocks)**: S1 spine `> 220 m` — "**marathon approach**" (101-102); S2 extraction inside
  a building footprint (114-118); S3 naked crossing `> 40 m` with no cover within 8 m (121-131); S4
  lane count outside 3–8 (134-136); S5 approach spread `< 90°` (149-151); S5 objective has a single
  path neighbour (152-153).

So: **a marathon approach never blocks. A single-angle objective never blocks. A 40 m+ naked killing
lane never blocks. A lane count of 1 or 20 never blocks.** Only the instant-rush floor and the
spawn-camp exit do.

Additionally the entire module is a no-op unless `mode == "pvp_heist"` (66-68) — the PvE `heist` mode
gets none of S1–S5.

### 3.3 `site_pacing.py` — never a verdict, by construction

> "Estimates time-to-complete... **Compared against a target window** (default 7-15 min)"
> and "Every number is an estimate from declared inputs, shown with its breakdown, **never a
> verdict.**"
> — `lot/site_pacing.py:23-26`, `4-8`

> "Return a pacing estimate (dict). **Pure arithmetic; never raises.**"
> — `lot/site_pacing.py:127`

> "estimate from declared structure + derived timings; **not a measure of fun. Walk it to feel the
> pacing.**"
> — `lot/site_pacing.py:216-217`

The status strings — `"within target"`, `"likely TOO SHORT vs target"`, `"likely TOO LONG vs target"`,
`"partly outside target (range straddles the window)"` (198-204) — are emitted into the site
gameplay.json and read by a human. **A heist estimated at 90 seconds or at 40 minutes ships.**

Encounter intel likewise: "**Per-leg structural facts about combat OPPORTUNITY. Not a quality
score.**" (281).

### 3.4 `site_tactical.py` — intel vs gates, explicitly split

> "Two kinds of output, mirroring Deli Counter:
>   * **INTEL (never fails the build):** connectivity, route distances, per-building reachability from
>     spawn.
>   * GATES (fail the build) only when a site `mode` is declared"
> — `lot/site_tactical.py:18-22`

> "**Intel** (never fails the build), emitted into the site `gameplay.json` under `tactical`"
> — `lot/README.md:135-136`

Advisory items:

- **Isolated buildings** — computed (`analyze`, 134-141) and emitted as a `warnings` string:
  "buildings with no declared path-route from '{root}'". **Never gates.** A building nobody can walk
  to is a warning.
- **`objective_approaches`** count — intel only in PvE heist mode (152-154). It gates in `assault` and
  `pvp_heist` but not in `heist`.
- **PvP staging marker counts** — "(**never gates here**)" (143).
- `spawn_to_objective_dist` — intel only (150-151).

### 3.5 `site_extent.py` — severities `blocker` / `moderate` / `minor`

Advisory:

- `LOT_GROUND_EXTENDED` — **moderate** (359). The plate is silently grown to fit; growth is reported
  but the build proceeds. "Growth is never quiet" (35).
- `LOT_GROUND_OFF_CENTRE` — **minor** (367-373). Diagnoses that "whatever wrote this spec sized the
  ground from the building count and then assumed the row was centred on the origin".
- `LOT_GROUND_EXTENT_UNKNOWN` — **moderate** (375-380). Buildings with unreadable footprints: the
  ground "may not reach their walls".
- `LOT_BUILDINGS_OVERLAP` at depth `≤ 0.5 m` — **minor**, "reported rather than gated" (431-436).

Blocking: `LOT_GROUND_UNREASONABLE` (> 2000 m span) — **blocker**, but the ground is still built
(382-388: "the ground was still built to cover it"). `LOT_GROUND_HOLE_OUTSIDE` — **blocker** (440-456).
`LOT_BUILDINGS_OVERLAP` at depth `> 0.5 m` — **blocker** (422-430).

### 3.6 `site_spawns.py` — severities `major` / `moderate` / `minor`; none stop the build

- `LOT_ENEMY_SPAWN_UNPLACEABLE` — **major** (631-648). Enemies are silently dropped; "Laser Tag will
  evaluate {n} enemies instead of {requested}". The rationale is explicit: "**a spawn Lot cannot
  defend is worse than a spawn Lot does not write, because the first one costs a full evaluation to
  discover**" (22-25).
- `LOT_ENEMY_SPAWN_PUSHED` — **minor** (649-663).
- `LOT_ENEMY_SPAWN_STANDOFF` — **minor** (665-687).
- `LOT_ENEMY_SPAWN_IN_THE_OPEN` — **major** (718-736). The readback finding. Its own text says the
  placer is supposed to make this impossible: "**if this finding is present, the positions in the
  scene did not come from the rule that was supposed to have produced them.**" It is still a finding,
  not a gate.
- `LOT_ENEMY_SPAWN_CLOSE` — **minor** (737-753). States the fragility of a fair-by-occlusion opening:
  "it stays fair only for as long as that building does".
- `LOT_SPAWN_PLACEMENT_UNCHECKED` — **moderate** (`place_enemies`, 407-418). A site with no ground and
  no footprints gets unchecked spawns and a note.

The readback finding exists precisely because the search cannot audit itself:

> "**it is the one class of defect the search cannot report on itself** -- if the placer's model of
> what counts as cover is wrong, or the code that ran is not the code that was reviewed, every enemy
> passes on the way in and the map still opens with a shot. That is not hypothetical. **Seed 5320 of
> `category5_baie_dore_001` wrote Enemy_0 23.0 m from the crew down a clear street**, and the only
> finding the run carried about the opening engagement was the reassuring one"
> — `lot/site_spawns.py:694-706`

### 3.7 `site_cover.py` — "**All advisory**", stated in the function that produces the findings

> "What the producer should say about the cover it just placed. **All advisory. A site with an open
> sightline is a site Laser Tag will play and mark down, which is a design signal and not a build
> failure** -- the same split the evaluator's own findings are read under. The one thing worth saying
> loudly is a line nothing could break, because that is a request for a building and no amount of
> street furniture will answer it."
> — `lot/site_cover.py:731-738`

| Code | Severity | Meaning |
|---|---|---|
| `LOT_COVER_PLACED` | **minor** | 741-753 |
| `LOT_SIGHTLINE_UNBREAKABLE` | **moderate** | 761-771 — "a request for a building rather than street furniture" |
| `LOT_COVER_PINCH` | **moderate** | 774-788 — lanes closed below the passable gap; "a bot meeting one of these reads as stuck" |
| `LOT_ROUTE_COVER_PLACED` | **minor** | 790-801 |
| `LOT_ROUTE_EXPOSED` | **moderate** | 803-818 — "the crew is inside the firing envelope while it walks" |
| `LOT_SIGHTLINE_OPEN` | **minor** | 820-831 — "**Laser Tag will play the map and grade the exposure; it is a design note, not a broken level.**" |

And the module-level statement that this whole class of finding is deliberately non-blocking:

> "So a firefight evaluator's finding is a *soft* gate here: **it never refuses a build, it changes
> what the build contains.**"
> — `lot/site_cover.py:14-15`

### 3.8 `site_enterability.py` — gate the clear-cut, warn the rest

Hard gate: every entry's approach blocked = walled in. **Warn (never blocks)**: "you can reach it, but
**no authored path/courtyard actually leads to a clear entry**; or the building's own gameplay.json
has no usable entry" — `site_enterability.py:16-20`. And the stated limit of even a clean pass:

> "**A clean pass means 'the spec doesn't wall the building in,' not 'certified walkable.'**"
> — `lot/site_enterability.py:22-24`; restated `lot/README.md:172-175`

### 3.9 `cater.py` — the spec-drift warning is explicitly not a gate

> "**Warning only;** divergence can be deliberate (a frozen level is a valid choice) -- **but it
> should be a CHOICE.**"
> — `lot/cater.py:220-221`

> "(If the divergence is deliberate, carry on -- **this is a warning, not a gate**.)"
> — `lot/cater.py:259-260`

The drift check is additionally wrapped in `except Exception: pass` at the call site
(`cater.py:280-284`), so a missing Deli Counter checkout silently disables it.

### 3.10 `building_library.py` — reports rather than decides

- `index()` reports `.lights.json` presence but "**is reported and never used to EXCLUDE**" (78-81).
- `art_incomplete()` "**Reports rather than decides**" (110-112).
- `require_art_inputs()` is the one place that raises — and the docstring explains why raising is the
  design: "**RAISES rather than filtering, and the distinction is the whole point.** If a building
  without a light manifest simply dropped out, a five building brief would produce a four building
  site with every stage reporting success" (129-135).
- `pick_lot` degradation is invisible except by inspection: "each fallback is a real degradation and
  **the caller can see it by comparing families to count**" (164-166) — nothing computes or reports
  that comparison.

### 3.11 The producer's self-checks

`site_variation.overlapping()` and `uncovered()` (288-345) run "on every spec write and would refuse
the build" (`site_variation.py:212-214`) — but the module notes: "**Not quietly... but refusing is not
placing.**" (212-214). `uncovered()` "is not a second opinion on Lot's `site_extent` -- it asks the
narrower question this module is responsible for" (319-322).

---

## 4. CONSPICUOUSLY ABSENT

What a heist level needs that nothing in this area measures. Each is supported by the pipeline's own
text.

### 4.1 The escape route under pressure — the exit is a *connectivity* fact only

The corpus states the requirement plainly:

> "**A good heist has:** casing/entry area, public area, restricted staff area, security room,
> objective room, loot/vault/stash, **a bag-movement route, a secondary route,** responder entry
> points, a holdout area, **and an escape route.**"
> — `deli_counter/docs/scale_guidelines.md:83-85`

At site scale the only thing measured about the escape is that a declared path edge exists:

> "`heist` — `spawn → objective → extraction` must be path-connected."
> — `lot/README.md:157`; implemented `lot/site_tactical.py:199-208`

Nothing at site scale asks:

- whether the exfil leg is **survivable under pressure** — responder arc is measured *around the
  objective* only (`site_audit.py:179-191`), never around the extraction or along the objective→
  extraction leg. `S_RESPONDER_CAMP` checks proximity to the anchors (12 m) but not whether the escape
  corridor is enfiladed.
- whether the exfil offers **a choice of routes**. The `≥ 2 distinct approaches` gate applies only to
  the objective, and only in `assault` and `pvp_heist` (`site_tactical.py:183-197, 217-248`). **The
  heist mode's extraction leg is gated at exactly one route.** `site_audit.py`'s `S_ONE_APPROACH`
  likewise measures only `spawn → objective` (273-279).
- whether the **loot is carryable across the site**. Deli Counter measures `H_CARRY_PINCH` inside a
  building — "From every objective there must be a route to a ≥ 1.4 m exterior egress using only
  ≥ 1.2 m openings — stairs carry bags, ladders don't... If the only way out is a pinch, the exfil is
  a turnstile under fire" (`docs/DESIGN_RULES.md:39-43`). No site-level equivalent exists: nothing
  measures the width of the gap between two buildings on the bag route, and `pacing` prices loot as a
  flat `loot_trip_secs = 25` per marker regardless of distance (`site_pacing.py:64, 179-184`). The
  only site-scale width check is `site_cover.pinches()`, which measures lanes closed **by Lot's own
  cover** (`site_cover.py:400-427, 774-788`), not lanes closed by the building placement.

### 4.2 Escalation over time — pressure is a static geometry check

The pipeline names escalation as site-owned:

> "**JUDGMENT:** escalation staging (where responders arrive as waves build — **site-level, Lot's
> `responder_spawn` markers own it**)"
> — `deli_counter/docs/DESIGN_RULES.md:49-51`

But `site_audit` measures only two static facts about responders — bearing spread around the objective
(182-191) and distance from anchors (192-202) — and reports their total absence as **INFO**
(`S_NO_RESPONDERS`, 203-206). Nothing measures:

- **when** waves arrive relative to the pacing estimate. `site_pacing.py` has no pressure term at all
  for heist mode: the breakdown is travel + setup + objective work + loot trips (`estimate_pacing`,
  126-218). Only `survival` gets a wave model (`waves × wave_secs`, 187-192). So a heist's
  `objective_secs = 120` drill is priced as 120 seconds of *nothing*, when the genre statement is "do
  the thing **under pressure**" (`DESIGN_RULES.md:20`).
- whether responder ingress **reaches** the objective. The responder spawns are bearing-checked but
  never route-checked against the site graph; `site_tactical.build_graph` (49-61) contains only
  building nodes joined by declared `paths`, and responder markers are not nodes.

### 4.3 A site-scale holdout — the drill has no defensible ground between buildings

Interior grammar demands one, with numbers:

> "**H_NO_HOLDOUT — the drill needs a room to defend.** The objective-wait phase (drill, hack, timer)
> is a fight in place. The objective room or a neighbor must work as a holdout: **2–3 coverable
> entries (1 is a camping closet, 4+ is indefensible), ≥ 12 m², and something to shelter behind.**"
> — `deli_counter/docs/DESIGN_RULES.md:32-37`

And the good-heist checklist asks for "a holdout area" (`scale_guidelines.md:84`). At site scale,
`survival` mode is the only one that names a holdout (`site_tactical.py:210-215`,
`site_pacing.py:31`). In `heist` mode the objective building is never asked to be defensible — no
count of entries into it, no measure of coverable approaches, no area. `site_audit`'s
`S_NAKED_ANCHOR` checks a backstop within 8 m of the **crew spawn and extraction only** (209-219) —
**the objective is explicitly not in that loop.**

### 4.4 Stealth — named as a heist requirement, absent at site scale

> "**H_NO_STEALTH — a heist map should have a stealth layer to beat.** `camera_socket` and
> `patrol_point` markers are the stealth vocabulary. A heist spec with neither is **loud-only by
> construction.** INFO, not a demand."
> — `deli_counter/docs/DESIGN_RULES.md:45-48`

Those two marker types survive the merge — they appear in `deli_counter/floorplan.py`'s
`MARKER_STYLE` (55-56) and in the gameplay contract's marker list
(`docs/GAMEPLAY_JSON_CONTRACT.md:64-65`) — but nothing at site scale reads them. `lot/lot.py`'s
nav-QA proxy sets are `_PROXY_TYPES = ("crew_spawn", "attacker_spawn", "objective", "loot",
"extraction")`, `_COVER_TYPES`, and `_BOT_TYPES = ("responder_spawn", "horde_spawn",
"defender_spawn")` (1447-1449) — **no camera or patrol type appears anywhere in `lot/`**. There is no
site-scale question of whether the approach across open ground can be made unobserved, whether the
casing phase has vantage, or whether a loud/quiet branch exists between buildings.

Note also the mode vocabulary: the heist's "casing/entry area" and "public area"
(`scale_guidelines.md:83`) have no site-level representation at all. Site roles are exactly four —
`objective`, `spawn`, `extraction`, `safe` (`site_tactical.py:26-29`).

### 4.5 The site's own pacing has no beat structure

`site_pacing` produces one number and a band. It measures duration, not shape:

> "duration is a function of distances + objective timings + mode structure... 'How many minutes' is
> arithmetic. **'How tense' is not.**"
> — `lot/site_pacing.py:16-18`

The L4D2 grammar the site audit borrows from *does* have a shape rule at the building level —
"**F_FLAT_RHYTHM — alternate tight and open.** Along the entry→objective path, room scale should
change. If every step is within ~1.4× of the last, the run reads as one long corridor"
(`docs/DESIGN_RULES.md:95-99`). Its own doc hands the site the rest and then nothing takes it:

> "**JUDGMENT:** lighting-as-signposting, **safe-room placement rhythm across a CAMPAIGN (site/Lot
> level — `site_pacing.py` owns travel legs)**, crescendo trigger placement"
> — `deli_counter/docs/DESIGN_RULES.md:115-117`

`site_pacing.py` owns travel legs and measures only their length, approach count, open ground and
nearby cover count (`encounter_intel`, 280-298). There is **no site-scale compression/release
measure** — no check that the crossing between buildings alternates tight and open, no measure of
courtyard-to-alley variation, nothing that would distinguish four buildings on one long street from
four buildings around a plaza.

### 4.6 Verticality across the site

Every vertical statement in the corpus is building-local. The heist scale table gives a "Vertical"
column of 0–25 m (`scale_guidelines.md:75-79`); `pvp_heist.py` gates `PVP-VERT` and `PVP-FLANK`'s
"vertical/breach alternate approach" (`pvp_heist.py:19-25, 335-348`); Deli Counter owns ladders,
stairs, roofs and fire escapes. At site scale, `lot/site_steps.py` measures step-up heights of
**0.117 m** against kerbs and sidewalks (6-30) and that is the whole of it. Nothing measures whether
a roof route exists between two buildings, whether a fire escape lands on reachable ground, or whether
the site has any traversal above grade — even though `S_BARE_LEG` treats every critical leg as a
ground-plane run (`site_audit.py:221-236`) and `site_spawns` explicitly disclaims a storey model:
"the drop is a storey -- and **Lot has no storey model**, so it says so and moves nothing"
(`site_spawns.py:141-145`).

### 4.7 What the *crew* is — four players, measured as one

The design intent is stated:

> "**DELCO is a PAYDAY-style 4-player PvE co-op heist loop**, NOT a PvP-symmetric shooter"
> — `deli_counter/level_design.py:25-26`

Every site-scale measure treats the crew as a single point. `site_spawns` places against one `spawn`
coordinate (383-460); `site_cover` biases cover toward "the crew's end" of a line via a single
`CREW_MARKER = "LT_PlayerSpawn"` (506-509); pacing assumes one traversal at one `move_speed`
(`site_pacing.py:62`). Nothing measures whether four bodies fit through the gap between two buildings,
whether a spawn area can stage four players, whether the extraction can hold four, or whether the
site supports the split-up-and-regroup that "a bag-movement route **and a secondary route**"
(`scale_guidelines.md:84`) implies. The nearest thing is `site_enterability.APPROACH_CLEARANCE = 1.5`,
which is per-entry, not per-crew, and is described as "the minimum outdoor staging depth in the scale
guidelines" (`site_enterability.py:45-47`).

### 4.8 Whether the buildings differ *as a level*, only as assets

`site_variation.py` states the goal — "**passing a diversity gate is not the goal, being different
levels is**" (20-21) — and `building_library.py` states "**VARIANTS ARE NOT VARIETY**" (20). What is
actually computed is family-distinctness at selection (`pick_lot`, 152-190) and a directory listing of
`REQUIRED` suffixes (69-105). Nothing measures whether the *assembled site* is different: no measure of
role diversity across the picked lot (a five-deli lot and a deli/bank/depot/pharmacy/stadium lot pass
identically once families differ), no measure of whether the placement seed actually changed the route
shape, no comparison between two candidates of the same mission. The diversity check is referenced as
living elsewhere — "`cmd_run`'s diversity check exists because '**N candidates that are all the same**'
shipped once already" (`building_library.py:158-160`) — and its criterion is not stated here.

The known consequence is documented rather than measured:

> "**A varied lot is currently UNLIT** regardless: `lux_apply` lights `presentation/site.tscn`, the
> mission shell, which a varied lot does not place."
> — `level_factory/docs/WALKABLE_SITE.md:124-126`

> "run <mission>          -> varied greybox lot, N different buildings, no art
>  run <mission> --art    -> **ONE building repeated N times**, fully themed and lit"
> — `level_factory/docs/VARIED_THEMED_LOT.md:8-11`

So the pipeline can produce a varied site or a themed site, and **no measure exists that would catch
being handed the wrong one** — that fact is carried in a mission brief's prose `notes` field
(`PER_BUILDING_ART.md`, quoting `lot_demo_001`) rather than in a check.

### 4.9 Nobody measures the walk, and the walk is the stated authority

Every module in this area defers the verdict to the same place, and that place is unmeasured:

- "The in-engine walk remains the only thing that tells you if it's actually fun." — `site_pacing.py:13-14`
- "whether it plays well is for the walk to tell you" — `site_pacing.py:296-297`
- "clean -- structural estimate, not a measure of fun; walk it" — `site_audit.py:299-300`
- "the engine gates (walktest, mp_smoke) stay the traversal truth" — `site_layout_lint.py:24`
- "an offline graph can't prove you can physically cross a courtyard" — `site_tactical.py:14-16`,
  `lot/README.md:132-134`
- "whether the swing/vault space is physically clear is a walk-test fact" — `site_enterability.py:22-23`
- "The audit exists to make the walk cheaper, not to replace it." — `DESIGN_RULES.md:131-132`

And the walkable deliverable those verdicts depend on has, by the pipeline's own diagnosis, never been
produced:

> "# Walkable site: **the deliverable Level Factory advertises and has never produced**"
> — `level_factory/docs/WALKABLE_SITE.md:1`

> "`res://` is rooted at the Godot project directory, so `res://C:/...` looks for a folder literally
> named `C:` inside the project. **These references cannot resolve anywhere.** Not in a preview
> project, not in a consumer's project, not at all... It has never been noticed because **nothing ever
> loaded that scene**"
> — `level_factory/docs/WALKABLE_SITE.md:15-24`

> "An output that nobody reads cannot be seen to be broken -- the same shape as the sightline suite
> that was not wired to `check.py`, the circulation arm handed the stripped glb, and the two-week
> stale `build/`."
> — `level_factory/docs/WALKABLE_SITE.md:24-27`

This is the load-bearing absence. The site layer's entire theory of quality is: measure structure,
report advisorily, and **let the walk decide** — and the walk is an artifact the pipeline has been
emitting in an unloadable form. Every "walk it" in every docstring above cashes out against that.

### 4.10 Smaller absences, each evidenced

- **No check that the site *has* an objective marker.** `site_pacing` does `n_obj = max(1,
  _count_type(merged, obj, "objective"))` (173) — a building with zero objective markers is priced as
  one. `_walk_positions` falls back to the building anchor, then to `(0,0,0)`
  (`lot/lot.py:1128-1137`), so a heist with no objective produces a beacon at the origin.
- **No check that extraction is reachable from ground.** S2 checks bounds and footprints
  (`site_layout_lint.py:104-118`) and only in `pvp_heist`. The PvE heist's extraction is checked for
  path-connectivity between *buildings*, and the site-level `extraction` marker — which overrides the
  building for both pacing (`site_pacing.py:154-157`) and the audit (`site_audit.py:72-80`) — is never
  itself route-checked.
- **`site_audit`'s building rects are a fiction.** "a conservative box around the anchor is enough for
  backstop tests" with `r = 8.0` (`site_audit.py:93-99`) — while `site_variation.DEFAULT_FOOTPRINT` is
  48 × 48 (69-73) and measured shells run 26–46 m. So the naked-anchor test credits a 16 m box where
  the building is 46 m, and the audit's own building-as-backstop reasoning is running on the wrong
  geometry.
- **No site-scale first-slice / readability measure.** The CQB rule "the first slice should answer
  50–90%" (`DESIGN_RULES.md:74-81`) is interior-only. Nothing asks what a crew can see of the site when
  it spawns, whether the objective building is legible from the approach, or whether landmarks read at
  site scale — even though `deli_counter/level_design.py` builds landmarks precisely so a crew "can
  call 'vault', 'lobby', 'extraction' and read the space at a glance instead of burning attention on
  navigation" (202-206) and those landmarks stop at the building wall.
- **No measure of the space *between* the mission's three points as a shape.** `site_layout_lint`'s S1
  measures spawn→objective only (96-102). Nothing measures the objective→extraction leg length at all —
  so "no marathon" applies to the entry and not to the escape.
