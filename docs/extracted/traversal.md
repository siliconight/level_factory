# Traversal, Circulation & Movement — recovered theory of quality

Scope: `deli_counter/{circulation,stairwell,stair_core,stair_place,ladder,ladder_place,ladder_geom,enterability,navigability,layout_lint,floors,partition_bounds,nav_gate,agent_contract}.py`, `deli_counter/agent_contract.json`, `deli_counter/godot/addon/deli_counter/nav_gate.gd`, `lot/{site_steps,site_enterability,site_ground,site_layout_lint}.py`.

Repo root on device: `C:\Projects\gabagool_studios\gabagool_factory`. Line numbers below are from the staged copies, which are byte-identical to the device files.

Nothing here is proposed or invented. Everything is quoted or read out of the code as it stands.

---

## 1. ASSERTED DESIGN INTENT

Verbatim statements about what makes movement good or bad, and why a constraint exists.

### 1.1 The governing frame: circulation is RESERVED space, not leftover space

> "A dressed building must keep its CIRCULATION clear: the player has to be able to mount every ladder, pass every doorway, and walk every stair without a prop parked in the way."
> — `deli_counter/circulation.py:3-5`

> "The whole vertical column over a stair footprint is reserved circulation: a prop at ANY height inside the shaft is wrong (on a flight, on a landing, or floating in the well), so the volume is the rect extruded over the full z range under test."
> — `deli_counter/circulation.py:22-25`

> "stair runs, landings, and discharge are reserved space, not leftover space (Rule 10)."
> — `deli_counter/stairwell.py:1076-1077`

> "props/markers standing inside the reservation are EVICTED (Rule 10: reserved space, not leftover space)."
> — `deli_counter/stair_core.py:22-23`

> "the climbing volume is reserved space (Rule 8)."
> — `deli_counter/ladder.py:674-675`

Note the asymmetry the module itself flags: **the reserved stair column is enforced in plan (XY) at every z, but no vertical dimension of that column is ever measured against a body.** See §4.

> "A prop is a prop whoever placed it."
> — `deli_counter/circulation.py:49`

The measured incident behind that line:

> "Measured on ``art_probe_001`` seed 5017: ``VAULT`` (5.00 x 3.00 x 5.00 m) sits **1.6 m** inside the reserved column of ``stair_1``, overlapping 15 consecutive treads across the full 1.60 m stair width. The rule below already forbade it in as many words, ``prop_conflicts`` already detected it on the first run, and ``check_dressing`` was simply never handed DC's own geometry."
> — `deli_counter/circulation.py:40-45`

Doorways get a wider tolerance for a stated experiential reason:

> "a crate hard against either face of an open door blocks passage just as surely as one inside the frame."
> — `deli_counter/circulation.py:19-20`

> "Trim is thin along the wall normal, so its min-axis penetration stays at frame depth (<= ~5 cm measured on real builds); a free-standing prop parked in the walk path penetrates far deeper. 12 cm cleanly separates the two populations."
> — `deli_counter/circulation.py:68-71`

And a gate-integrity assertion that is really a statement about honesty of measurement:

> "A GATE WITH NO INPUT IS NOT A PASS."
> — `deli_counter/circulation.py:245`

> "``{"ok": true, "props": 0, "volumes": 9}`` while `surface_roles` declared ELEVEN props."
> — `deli_counter/circulation.py:251-252`

### 1.2 Buildings are designed circulation-first; the floorplan yields to the stair

> "Humans design multistory buildings roughly as: footprint -> entrances -> vertical circulation cores -> corridors -> rooms -> props. Deli Counter's recipes historically went footprint -> partitions -> 'find a rectangle where stairs might fit', which is how stairs ended up facing walls and landing in closets. This module inverts that order for generated buildings"
> — `deli_counter/stair_core.py:2-8`

> "the floorplan adapts to the reservation, never the other way around"
> — `deli_counter/stair_core.py:19-20`

> "walls may enclose the shaft, never cross it"
> — `deli_counter/stair_core.py:22`

> "doorless partitions crossing a landing get a DOOR punched at the crossing (the enclosure opens onto the landing)"
> — `deli_counter/stair_core.py:22-23`

> "a whole-basement vault would otherwise reject every through-running candidate on protected-room overlap, and real buildings interrupt public circulation at grade anyway (Rule 8)."
> — `deli_counter/stair_core.py:130-132`

> "A stair into the vault is how you reach the vault"
> — `deli_counter/stair_core.py:88-89`

### 1.3 A stair is an ORIENTED system, not a mesh

> "a stair stops being an isolated mesh and becomes a SYSTEM -- role, vertical stack, per-floor approach, and a ground-level discharge route"
> — `deli_counter/stairwell.py:5-6`

> "A stair is an ORIENTED system: approach -> lower landing -> flight -> upper landing -> departure. Both landings are reserved floor."
> — `deli_counter/stairwell.py:79-80`

> "Each endpoint is where a body enters (lower) or leaves (upper) the stair"
> — `deli_counter/stairwell.py:141-142`

> "candidates are axis-aligned rects of the profile's footprint, evaluated in ALL FOUR cardinal facings -- a candidate is (x, y, facing), never just a rectangle"
> — `deli_counter/stair_place.py:24-26`

> "ascent orientation is part of the placement, not a default."
> — `deli_counter/stairwell.py:1095-1096`

Failure messages that state the felt defect directly:

> "'{sid}' {what} faces a solid partition ... a body cannot step {'onto' if lower else 'off'} the stair."
> — `deli_counter/stairwell.py:274-277`

> "'{sid}' {what} discharges into the exterior shell on story {story} -- the {LANDING_DEPTH:g} m landing does not fit inside the walls."
> — `deli_counter/stairwell.py:230-233`

> "the stair floats in unrouted space."
> — `deli_counter/stairwell.py:948`

> "no room covers the {'approach' if lower else 'departure'}."
> — `deli_counter/stairwell.py:321-322`

> "a stair walking into a wall is broken geometry regardless of role or authorship."
> — `deli_counter/stairwell.py:22-23`

> "doors belong on landings, never treads (Rule 4)."
> — `deli_counter/stairwell.py:1177-1178`

### 1.4 An end must be OPEN; a side must be CLOSED (the two-axis containment contract)

This is the single densest statement of movement-feel intent in the area.

> "LATERAL CONTAINMENT -- a body may fall ALONG a stair, never OUT of it"
> — `deli_counter/stairwell.py:327`

> "clearance_findings above proves the LONGITUDINAL axis: the flight ENDS are open so a body can step on and off. This section proves the LATERAL axis: the flight SIDES (and every non-mouth edge of the reserved footprint) are closed so a body cannot step, be pushed, or fall off the side into the shaft, the floor below, or the atrium. The two are complementary halves of ONE contract -- an end must be open, a side must be closed"
> — `deli_counter/stairwell.py:329-334`

> "(Sealing a mouth is caught by STAIR_ENTRY/EXIT_FACES_SOLID above, so the two halves keep each other honest: you cannot 'contain' a stair you cannot enter.)"
> — `deli_counter/stairwell.py:336-337`

> "'{sid}' {side} side of the flight is open (largest gap {gap:.2f} m > {LATERAL_ENVELOPE:g} m envelope) -- a stair floating open in the floor plate: a body walks/is pushed off the side, and the shaft reads as a hole in the AI navmesh. Fix by relocating it against a wall/corridor (stair_place edge zones) or enclosing the side with a wall or guard along the full flight and landing. **A guarded feature stair is fine; a bare mid-floor one is not.**"
> — `deli_counter/stairwell.py:493-501`

> "'{sid}' {side} edge of the reserved opening is unguarded ... a body on the upper floor can walk into the stairwell; guard every floor-opening edge except the stair mouth (Rule 4)."
> — `deli_counter/stairwell.py:487-490`

> "A named guard with collision='none' contributes nothing (decorative rails do not contain a body -- audit M1)."
> — `deli_counter/stairwell.py:409-411`

Explicit statement of the proxy's limit — and it is precisely a headroom-shaped limit:

> "it works at spec/rect resolution and asks 'is a body-retaining barrier DECLARED along each hazardous edge, with no person-sized gap', NOT 'does the built collision form a continuous wall **taller than the capsule** at every point' -- that is the build-time geometry gate's job (Layer C of the containment audit)."
> — `deli_counter/stairwell.py:339-343`

### 1.5 Believability of placement — a stair must read as a stair

> "A human stair lives in a stairwell shaft, not sprouting in the middle of an open functional room. Nav still works via the ramp collider -- this is about believable placement so DC/LF stop shipping bare mid-floor stairs."
> — `deli_counter/stairwell.py:968-971`

> "it reads as a stair sprouting in the middle of an open room. Enclose it in a dedicated stairwell/corridor room ... with a doored approach."
> — `deli_counter/stairwell.py:975-978`

> "Narrower than CIRCULATION_ROLES on purpose: open spaces (lobby, public_entry, staging, open_floor) are where a bare stair 'sprouts in the middle of the floor' -- excluded here so the enclosure gate catches them."
> — `deli_counter/stairwell.py:65-68`

> "Room roles that read as circulation (a believable stair approach)."
> — `deli_counter/stairwell.py:58`

> "a spiral stair carrying role '{role}' -- spirals never serve as a required egress stair (spec 6.5)"
> — `deli_counter/stairwell.py:1013-1015`

> "the stair teleports laterally between floors (Rule 2)"
> — `deli_counter/stairwell.py:1226-1227`

> "a transfer floor must be walkable (Rule 2)."
> — `deli_counter/stairwell.py:1214-1215`

### 1.6 Egress routes must be short, legible, and independent

> "keep it short and legible (Rule 5)."
> — `deli_counter/stairwell.py:993`

> "one blocked room kills both routes (Rule 7)."
> — `deli_counter/stairwell.py:1254-1255`

> "removing room '{choke}' severs BOTH egress discharge routes ... routes must stay independently usable (Rule 7)."
> — `deli_counter/stairwell.py:1261-1263`

> "a required stair door that defaults to locked is only tolerable when another egress stair serves the floor AND the scenario says so; alone, it deletes the route."
> — `deli_counter/stairwell.py:1115-1117`

> "egress stair '{sid}' runs through grade into the basement in one shaft; offline review can't see a barrier -- make sure the grade landing interrupts descent (Rule 8)."
> — `deli_counter/stairwell.py:1005-1008`

> "each run ends against the slab above it; cut the holes or author the bulkhead."
> — `deli_counter/stairwell.py:1025-1026`

> "'{sid}' exterior tower serves story {s} but the {wall} facade has no door within reach of the tower there -- the floor cannot use it (s8.4)."
> — `deli_counter/stairwell.py:1039-1041`

Selection philosophy — pair quality, not two good singles:

> "select the best single stair or the best PAIR (s11.5 -- pair quality, not two individual winners)."
> — `deli_counter/stair_place.py:10-11`

> "the PAIR must be physically clean together: neither member may consume the other's landings"
> — `deli_counter/stair_place.py:563-564`

> "a candidate that is clean alone can still park its footprint on another pick's landing."
> — `deli_counter/stair_place.py:526-527`

> "Anchors that don't fit are REJECTED with a reason, never clamped back inside the shell (clamping used to collapse distinct strategies onto the same awkward edge spot)."
> — `deli_counter/stair_place.py:29-31`

> "a stair parked in the middle of the plate eats the most usable area"
> — `deli_counter/stair_place.py:500`

### 1.7 Ladders: a specialized connection with a purpose, an approach and a safe top

> "A ladder is a specialized connection between two usable surfaces. It must have a defined purpose, a safe approach, a safe transition at the top, and enough surrounding clearance to be climbed."
> — `deli_counter/ladder.py:16-19` (quoting spec s1/s23)

> "a ladder stops being decoration on a blank wall and becomes a SYSTEM"
> — `deli_counter/ladder.py:4-5`

> "unlike stairs (where an unclassified stair is intel), a ladder with NO role is a hard error (Rule 1 -- a ladder without a role is not generated)."
> — `deli_counter/ladder.py:22-24`

> "a ladder is never counted as ordinary required egress, no matter what it's labeled."
> — `deli_counter/ladder.py:26-27`

The most explicitly experiential line in the whole area:

> "'{lid}' clear width {ld.width:.2f} m **meets the technical minimum but may feel cramped for first-person traversal** (s10.4)."
> — `deli_counter/ladder.py:1015-1017`

> "a door swing into the ladder traps the climber (Rule 9)."
> — `deli_counter/ladder.py:688-689`

> "the climber lands outside the parapet with no way over (Rule 6 / PARAPET_CROSSOVER_MISSING)."
> — `deli_counter/ladder.py:711-713`

> "'{lid}' dismounts within a rail's length of an unguarded roof edge with no parapet there -- the top landing needs a secure standing surface (Rule 6)."
> — `deli_counter/ladder.py:847-851`

> "'{lid}' climber emerges under '{v.name}' -- the hatch dismount zone must be clear of ductwork/equipment (spec s8.3 / anti-pattern 'hatch collision')."
> — `deli_counter/ladder.py:886-891`

> "the dismount is valid but leads nowhere useful (s15.2)."
> — `deli_counter/ladder.py:665-667`

> "climbs to story {hi_story} but nothing walkable exists there and no upper_surface is declared (anti-pattern: ladder to nowhere)."
> — `deli_counter/ladder.py:648-651`

> "ladders over windows read as accidental unless it's a tagged fire escape (Rule 9 / anti-pattern 'window ladder')."
> — `deli_counter/ladder.py:868-869` (approx; message block `ladder.py:865-869`)

Multiplayer-specific movement failure:

> "'{lid}' allows {n} simultaneous climbers on a bidirectional fixed ladder -- two players from opposite ends can deadlock; prefer occupancy_limit 1 or a one-way direction (s15.3 / anti-pattern 'multiplayer deadlock')."
> — `deli_counter/ladder.py:998-1005`

> "'{lid}' uses scripted_direction -- AI cannot traverse it (ai_traversable is false); ensure another route serves any floor that depends on it (s15.3 / anti-pattern 'AI teleport ladder')."
> — `deli_counter/ladder.py:988-993`

> "keep ladders clear of the public approach (Rule 9 / s15.2)."
> — `deli_counter/ladder.py:820-822`

> "'{lid}' base is in a vehicle swept path ('{vz}') with no protection -- add a setback, bollards, or a protected alcove (Rule 10)."
> — `deli_counter/ladder.py:836-839`

> "water discharge on the climb path (Rule 12 / anti-pattern 'drainpipe ladder')."
> — `deli_counter/ladder.py:830-831`

The placement module's framing question:

> "not 'where can a ladder fit?' but 'what real access problem requires a ladder, and what complete route does that ladder create?' So candidates come from connection pairs, not from empty wall availability"
> — `deli_counter/ladder_place.py:14-16`

Ladder-hole traversability, from the linter:

> "every ladder must be TRAVERSABLE, not just present."
> — `deli_counter/layout_lint.py:189`

> "the climb dead-ends into the exterior shell (the ladder faces the wrong way for where it stands)."
> — `deli_counter/layout_lint.py:191-192`

> "the climber tops out inside a wall."
> — `deli_counter/layout_lint.py:194`

### 1.8 Getting IN is a distinct quality from getting AROUND

> "Deli Counter builds shells for a game where you ENTER buildings -- you walk up, open a door / vault a window / breach a wall, and the squad pushes in. A shell with no opening a player can fit through is a sealed box: it validates clean (geometry is fine, rooms are reachable FROM EACH OTHER) yet can't be played, because nobody can get inside in the first place. Nothing else catches that."
> — `deli_counter/enterability.py:5-8`

> "GATE THE CLEAR-CUT CASE, WARN THE REST: - HARD ERROR: no usable ground-level exterior entry at all -> sealed box. - WARN: there's a way in, but it's awkward (crouch-only, breach-only, vault-only, or a tight squeeze) -- playable, but design should know."
> — `deli_counter/enterability.py:15-19`

> "no standard door entry -- the only way in is via {kinds}. Playable, but the squad can't just walk in the front."
> — `deli_counter/enterability.py:124-126`

> "a window is an entry only if it's meant to be one: flagged vaultable, or sitting low enough to read as an openable/climb-through window."
> — `deli_counter/enterability.py:56-58`

> "window on the {wall} wall reads as an entry (vaultable/low) but a body won't fit -- widen/heighten it or drop the vaultable flag."
> — `deli_counter/enterability.py:142-145`

> "entry swing/vault clearance on both faces is a walk-test fact -- offline can't confirm the space is physically clear."
> — `deli_counter/enterability.py:163-164`

Site scale:

> "a building that's fine alone can become unenterable in a COMPOUND: its only door faces the perimeter wall, or a neighbour is parked against that face, or it sits in dead space with no path leading to it. Assembling buildings you can't get into is the site-scale version of shipping a sealed box"
> — `lot/site_enterability.py:5-9`

> "building '{bid}' is walled in: all {n} entrance(s) are blocked by a neighbour's footprint or the perimeter."
> — `lot/site_enterability.py:196-197`

> "building '{bid}' is reachable but no authored path/courtyard leads to a clear entry -- add an approach route so players (and AI) have a way to it."
> — `lot/site_enterability.py:201-204`

### 1.9 Steps, kerbs and the capsule — the physics of "feels walkable"

`lot/site_steps.py` is the clearest first-principles statement of movement feel in the repo.

> "A capsule does not meet a low step the way a box does. Contact lands on the bottom hemisphere, so the contact normal is sloped rather than horizontal, and the LOWER the step the more vertical that normal gets."
> — `lot/site_steps.py:4-6`

> "Above that the engine classifies the contact as a WALL and the capsule stops dead."
> — `lot/site_steps.py:13-14`

> "`agent_contract.json` states `max_step_up_m: 0.5` as though the body were a box; that number is what a controller can lift itself over, not what it can walk over."
> — `lot/site_steps.py:14-16`

> "Stepping off the ground onto a sidewalk is a 0.16 m rise. That is a wall to a stock CharacterBody3D, which is why walking from a spawn toward the street stops at the kerb and needs a jump. **It stays a wall on purpose; kerb cuts are what make the crossings legal.**"
> — `lot/site_steps.py:32-35`

> "A kerb is SUPPOSED to be a wall -- that is what stops you wandering into traffic -- so a transition above the step limit is only a defect where someone is meant to walk across it. Without this, the check fires on every metre of every kerb and can never go green, which makes it worse than no check at all: **nobody reads an instrument that is always red.**"
> — `lot/site_steps.py:65-70`

> "A body following the site's own circulation is stopped here."
> — `lot/site_steps.py:288-289`

> "Drop the kerb where the route crosses it. A kerb elsewhere is doing its job; a kerb on a crossing is a wall across the way in."
> — `lot/site_steps.py:290-292`

> "A body cannot get onto it and the navmesh will route around it silently."
> — `lot/site_steps.py:313-314`

> "the deliverable ships into projects with no step-up code in them ... it cannot assume the consumer implemented step-up."
> — `lot/site_steps.py:331-332`, `342-344`

> "Node-name prefixes that are surfaces a body walks ON. Everything else in the outdoor pass -- cover blocks, perimeter walls, blocker massing -- is an obstacle, and the height of an obstacle is not a step."
> — `lot/site_steps.py:47-49`

> "This reads the scene Lot actually wrote rather than re-deriving the numbers from the same constants that produced it -- the two agreeing costs microseconds, and the two disagreeing is the only class of defect the emitter cannot report on itself"
> — `lot/site_steps.py:37-40`

> "An instrument that reports a wall a body cannot touch is the same substitution defect it exists to catch"
> — `lot/site_steps.py:118-119`

### 1.10 The floor you stand on must exist

> "A solid ground slab running through a footprint seals the basement stairwell, and the building's own slabs are supposed to floor its interior. That reasoning has an unstated premise -- that the building's geometry file actually brings collision. A baked `shell.glb` does not."
> — `lot/site_ground.py:3-9`

> "a site assembled from plain shells cut a hole under every building and put nothing in it, and four adjacent footprints merged into one contiguous void with the spawn, the objective, the extraction and every enemy standing over it."
> — `lot/site_ground.py:11-14`

> "Keeping the ground can never create a fall -- the worst case is a floor under a building that had one already."
> — `lot/site_ground.py:23-25`

> "Only a demonstrated collider earns a hole in the ground."
> — `lot/site_ground.py:74`

> "they floor nothing and stop nothing ... the shells are pass-through"
> — `lot/site_ground.py:288-293`

> "Filling the hole stops the fall; it does not make the shell solid."
> — `lot/site_ground.py:275`

Interior analog, in `floors.py`:

> "The ceiling one caps the stairwell: you see ceiling above the staircase and you cannot climb it."
> — `deli_counter/floors.py:142-143`

> "A floor skin that carried its own collision would put a second walkable surface 2 cm above the first."
> — `deli_counter/floors.py:37-38`

> "circulation takes the traffic; tile is what a concourse gets and it changes underfoot from the carpet either side."
> — `deli_counter/floors.py:57-58`

### 1.11 The navmesh must not promise a route the body cannot take

The single richest engineering rationale in the area, `agent_contract.json:27`:

> "The navmesh routes a body over any riser up to this height; a capsule only WALKS up radius * (1 - cos(floor_max_angle)) = 0.117. Everything between was a route the bake promised and the body could not take. Measured on walkup_siege 2026-07-28: the walkers' route crossed a staircase's open lateral edge, a 0.49 m stringer, and four of them parked against it with a horizontal contact normal. Set to exactly one cell_height voxel (0.15) because Godot FLOORS this to whole voxels and warns that it does -- asking for 0.117 at this cell height quantises to zero and disconnects the map. **Stairs are unaffected: Deli Counter gives them a smooth ramp collider rather than per-step boxes, so they connect by agent_max_slope, not by climb.** The alternative -- enforcing lateral containment on every flight -- was rejected because it would put a barrier along the sides of every staircase in every building; open-sided stairs are ordinary architecture and the bake, not the building, is what was making the false claim."

> "Recast joins adjacent voxel columns only within walkableClimb, and on a ramp that gap is cell_size * tan(pitch). So the steepest ramp that stays CONNECTED is atan(agent_max_climb_m / cell_size_m) ... Measured 2026-07-29: eight path proofs across central_vault and warehouse_district failed as 'disjoint islands', **every one of them a storey change**, because those buildings have 4.2-5.0 m storeys over a 4.0 m run (46-51 deg) while walkup_siege's 3.2 m storeys (38.7 deg) stayed connected"
> — `agent_contract.json:28`

> "max_slope sits ABOVE the steepest legal stair pitch (~45 deg; **slope legality is validate.py's job, connectivity is the bake's**)."
> — `agent_contract.json:26`

Restated in the engine gate:

> "stairs bake as their collision RAMPS; the steepest legal stair is ~45 deg (STEP-RISE budget), and the baker's default 45 deg slope limit quantizes a 42 deg ramp into disjoint islands. Give the bake headroom: slope legality is validate.py's job, connectivity is this gate's."
> — `godot/addon/deli_counter/nav_gate.gd:118-121`

> "The AUTHORITATIVE answer to 'can a body actually walk this stair?', run without opening the editor"
> — `nav_gate.gd:3-4`

> "both endpoints must also SNAP onto the navmesh (an off-mesh endpoint is a landing that didn't bake -- exactly the failure this gate exists to catch)."
> — `nav_gate.gd:15-17`

> "0.15 m cells matter: the voxelizer erodes whole cells per side, so 0.25 m cells eat 1.0 m of every doorway and fragment rooms into islands."
> — `nav_gate.gd:31-32`

> "The offline analyzers (stairwell.py, navigability.py) are PROXIES; the authoritative answer to 'can a body walk this stair?' is the engine's own navmesh."
> — `deli_counter/nav_gate.py:4-6`

> "THE CONTRACT IS NOT OPTIONAL. ... A gate that silently bakes with pre-2026-07-28 numbers is not a gate."
> — `deli_counter/nav_gate.py:97-103`

And the ramp-foot rationale, which is a pure movement-feel argument:

> "The ramp is set half a step proud of the flight so its surface rides the step nosings. That is correct along the run and wrong where the run meets the floor: the surface starts `step_rise / 2` above it, plus half the slab's own thickness measured vertically through the tilt. **The result is a riser at the first step -- the exact thing a smooth ramp exists to remove.** ... Anything taller needs step-up code the shipped level cannot assume, so the ramp has to reach the floor rather than hover above it."
> — `deli_counter/stairwell.py:1350-1359`

### 1.12 Everything offline is a proxy; the walk is the truth

> "Treat a pass here as 'no obvious blocker,' not 'navigable.'"
> — `deli_counter/navigability.py:14-15`

> "an isolated room (no path from any entry) means AI literally can't get there"
> — `deli_counter/navigability.py:84-85`

> "(authoritative check = bake a navmesh in Godot)"
> — `deli_counter/navigability.py:100`

> "(authoritative check = walk it; this is room-graph intel)"
> — `deli_counter/stairwell.py:1344`

> "A pass here means 'nothing in the spec breaks the egress contract', not 'code-compliant'."
> — `deli_counter/stairwell.py:12-13`

> "A pass means 'nothing in the spec breaks the ladder-access contract', not 'safe to climb'."
> — `deli_counter/ladder.py:21-22`

> "Advisory layer: the engine gates (walktest, mp_smoke) stay the traversal truth."
> — `lot/site_layout_lint.py:24`

### 1.13 Rooms and openings must connect real, distinct space

> "every interior opening must connect two DISTINCT rooms; opening into unassigned space (no room on a side) is a navigation dead-end."
> — `deli_counter/layout_lint.py:288-289`

> "L12 -- every room must have a path from an exterior entrance. Catches SEALED spaces (a stair landing in a closed box, a room with no door)"
> — `deli_counter/layout_lint.py:317-318`

> "treats a stair/ladder as serving every floor it passes through (real stairwell behaviour), and counts ramps + floor-hole/hatch drops as connections."
> — `deli_counter/layout_lint.py:320-322`

> "outdoor / site rooms ... are contiguous with the exterior, so they are reachable from outside by definition."
> — `deli_counter/layout_lint.py:333-335`

> "An interior wall runs along ONE axis and its extent must stay within the footprint half-extent on THAT axis ... Authoring a Y-wall's end from the X half-width is the classic bug that ships interior partitions poking through the exterior shell."
> — `deli_counter/partition_bounds.py:6-9`

> "expect 2 ways out (common-path rule)"
> — `deli_counter/layout_lint.py:486-487`

---

## 2. MEASURED, WITH NUMBERS

### 2.1 The body and the bake — `deli_counter/agent_contract.json`

| Quantity | Value | Source line |
|---|---|---|
| player radius | **0.35 m** | `agent_contract.json:6` |
| player height | **1.8 m** | `:7` |
| eye height | **1.6 m** | `:8` |
| crouch height | **1.2 m** | `:9` |
| max_step_up (controller lift) | **0.5 m** | `:10` |
| walk speed | **4.0 m/s** | `:11` |
| npc_standard radius / height | 0.35 / 1.8 ("cops/civilians share player metrics") | `:14-16` |
| nav bake agent_radius | **0.4 m** (= fattest body + 0.05 safety) | `:20`, rationale `:26` |
| nav bake agent_height | **1.8 m** | `:21` |
| nav bake agent_max_climb | **0.15 m** (was 0.5) | `:22`, derivation `:27` |
| nav bake agent_max_slope | **55.0 deg** | `:23` |
| nav bake cell_size | **0.1 m** (was 0.15) | `:24`, derivation `:28` |
| nav bake cell_height | **0.15 m** | `:25` |
| min_door_width | **1.25 m** | `:31` |
| min_corridor_width | **1.1 m** (= 2*radius + 0.3 body margin) | `:32`, `:34` |
| min_headroom | **2.0 m** | `:33` — **defined, never consumed anywhere** (see §4) |
| unassisted_step_max | **0.1025 m** = 0.35 * (1 - cos 45deg) | `:35`, derivation `:36` |
| QA arrive_dist | 1.5 m | `:39` |
| QA stuck_seconds | 4.0 s | `:40` |
| QA snap_max | 2.0 m | `:41` |
| QA walker capsule | 0.35 m radius / 1.8 m height | `:42-43` |

Derived-slope arithmetic stated in the contract itself: steepest CONNECTED ramp = `atan(agent_max_climb / cell_size)` = atan(0.15/0.10) = **56.3 deg**, chosen so it carries the declared 55.0 deg (`agent_contract.json:28`). Door-width derivation: `2*ceil(agent_radius/cell_size)*cell_size + 2*cell_size = 2*ceil(0.4/0.15)*0.15 + 0.3 = 1.2`, "ratified 1.25 for margin" (`:34`) — note this derivation is still written against the OLD 0.15 cell.

### 2.2 Stair geometry — `stairwell.py` / `stair_place.py`

| Quantity | Value | Line |
|---|---|---|
| LANDING_DEPTH — clear floor at each entry/exit edge | **1.2 m** | `stairwell.py:81` |
| EXIT_STEP_OFF — slab hole past the top flight before the upper landing starts | **0.8 m** | `stairwell.py:82` |
| _SOLID_BAND — wall within this of the tread edge = "faces solid geometry" | **0.45 m** | `stairwell.py:84` |
| _TREAD_MARGIN — shaved off each run end for the door-on-tread test | **0.6 m** | `stairwell.py:76` |
| MIN_EGRESS_SEPARATION | **8.0 m** ("Rule 6 game-friendly floor") | `stairwell.py:73` |
| DEFAULT_SEPARATION_FACTOR | **0.33** of plate diagonal (sprinklered approximation) | `stairwell.py:74` |
| required separation | `max(8.0, diagonal * factor)` | `stairwell.py:1234` |
| DISCHARGE_MAX_CLEAN_HOPS | **3** rooms before warn | `stairwell.py:75` |
| LATERAL_ENVELOPE — max uncovered gap on a non-mouth edge | **0.5 m** | `stairwell.py:354` |
| _AGENT_PASS_WIDTH — capsule pass band | **0.7 m** | `stairwell.py:624` |
| max_agents_abreast (emitted) | `int(clear_width // 0.7)` | `stairwell.py:760` |
| two_way_passable (emitted) | `width >= 1.1` | `stairwell.py:761` |
| _AI_COST_ENCLOSED | **1.15x** route cost for enclosed stairs | `stairwell.py:623` |
| CONTAINMENT_ENFORCED | **False** — containment findings are warnings | `stairwell.py:353` |
| _TREAD_DEPTH | **0.28 m** (s10 commercial default) | `stair_place.py:144` |
| riser_target per archetype | **0.16 – 0.19 m** | `stair_place.py:60,68,76,84,92,100,108,116,124,132` |
| step count | `max(6, round(story_height / riser_target))` | `stair_place.py:191` |
| run | `min(8.0, max(3.0, round(n*0.28 / 0.5)*0.5))` — snapped to a 0.5 m grid, clamped 3–8 m | `stair_place.py:193` |
| clear_width per archetype | **1.0 – 1.4 m** (house 1.0, storefront 1.1, most 1.2, school 1.4) | `stair_place.py:60-132` |
| switchback footprint width | `2 * clear_width` | `stair_place.py:196` |
| _PERIMETER_NEAR | 2.5 m from a rect edge = "touches" exterior | `stair_place.py:143` |
| _ANCHOR_FIT_RADIUS | 3.0 m | `stair_place.py:145` |
| anchor wall allowance | `wall_thick + 0.3` | `stair_place.py:174` |
| clearance extents (entry / exit) | `run/2 + 1.2` / `run/2 + 0.8 + 1.2` | `stair_place.py:158-159` |
| two-stair trigger (occupancy policy) | plate area > **200 m²** or **>= 3 stories** | `stair_place.py:585` |

Resulting real pitch: at the common 1.2 m clear width, `riser_target 0.17`, a 3.5 m storey gives n=21, rise 0.1667 m, run = 6.0 m -> pitch atan(3.5/6.0) = **30.3 deg**. The 45 deg figure in the comments is the ceiling of the "STEP-RISE budget", not the produced value.

`stair_core.py` surgery constants: `_MIN_PIECE = 0.8` m (thinner room remnant is dropped, `:41`), `_MIN_WALL_SEG = 0.6` m (`:42`), `_PUNCH_DOOR_W = 1.1` m (`:43`).

### 2.3 Ladder geometry — `ladder.py` / `ladder_geom.py` / `circulation.py`

| Quantity | Value | Line | Enforced? |
|---|---|---|---|
| FALL_PROTECTION_TRIGGER_M | **7.30 m** climb | `ladder.py:53` | **yes, hard error** `:718-726` |
| LOWER_CLEAR_W / LOWER_CLEAR_D | 1.20 / 1.20 m | `ladder.py:54-55` | **no — never referenced** |
| CLIMB_HEAD_CLEAR | **2.20 m** above the top of the climb | `ladder.py:56` | yes — used as the z-extent of the climb envelope (`:389`) and the hatch dismount disc (`:886`) |
| GAMEPLAY_MOUNT_W | **0.80 m** | `ladder.py:57` | yes — `climb_rect` uses `max(width, 0.80)/2` (`:194`) |
| RUNG_SPACING_MIN / MAX | **0.25 / 0.36 m** | `ladder.py:58-59` | advisory warn `:1008-1012` |
| FIXED_CLEAR_WIDTH_MIN | 0.41 m | `ladder.py:60` | **no — never referenced** |
| GAMEPLAY_LOW_CLEAR | **0.50 m** | `ladder.py:61` | advisory warn ("may feel cramped") `:1013-1017` |
| HATCH_CLEAR_RADIUS | **0.9 m** dismount disc | `ladder.py:75` | yes, hard error `:884-891` |
| HATCH_SWING | **0.9 m** from a parapeted roof edge | `ladder.py:76` | yes, hard error `:900-904` |
| climb_rect reach off the wall | `max(depth + 1.0, 1.2)` m | `ladder.py:195` | yes |
| volume-intrusion area threshold | 0.05 m² plan overlap | `ladder.py:387` | yes |
| drainage hazard proximity | < 2.0 m | `ladder.py:826` | warn |
| vehicle swept path proximity | < 1.5 m | `ladder.py:833` | error |
| excessive climb | > 3 * story_height | `ladder.py:1020` | warn |
| CLIMB_STANDOFF | 0.5 m | `ladder_geom.py:25` | — |
| HOLE_ALONG / HOLE_BEHIND / HOLE_ACROSS_MARGIN | 1.3 / 0.2 / 0.6 m | `ladder_geom.py:28-30` | used by L14/L15 |
| _WALL_INSET (rail off facade) | 0.35 m | `ladder_place.py:103` | — |
| LADDER_CATCH_MARGIN / HEADROOM / DEPTH / STANDOFF (circulation gate) | 0.6 / **1.0** / 0.8 / 0.05 m | `circulation.py:56-59` | yes, package gate |

Note `LADDER_HEADROOM = 1.0` in `circulation.py:57` vs `CLIMB_HEAD_CLEAR = 2.20` in `ladder.py:56` — two mount-headroom numbers for the same physical thing, one used by the spec-time ladder review and one by the prop-conflict gate.

### 2.4 Doorway / body-fit numbers

| Quantity | Value | Line | Blocking? |
|---|---|---|---|
| DOOR_CLEARANCE (approach depth each side) | **0.6 m** | `circulation.py:61` | yes |
| PEN_MIN (ignore grazes) | 0.02 m | `circulation.py:63` | — |
| DOOR_TRIM_PEN | 0.12 m | `circulation.py:72` | — |
| MIN_NAV_DOOR_WIDTH | **1.25 m** (from contract; fallback 1.25) | `navigability.py:30,33` | **warn only** |
| AGENT_RADIUS (nav proxy) | 0.4 m (fallback) | `navigability.py:29,32` | — |
| MIN_PASS_WIDTH | **0.7 m** ("below this, the default capsule can't fit at all") | `enterability.py:35` | yes, part of sealed-box gate |
| CLEAN_WIDTH | **0.9 m** ("doc's minimum doorway width; below = a tight squeeze") | `enterability.py:36` | warn |
| MIN_PASS_HEIGHT | **1.1 m** ("below this, you can't even crouch through") | `enterability.py:37` | yes |
| STAND_HEIGHT | **1.8 m** | `enterability.py:38` | warn |
| VAULT_SILL_MAX | **1.2 m** | `enterability.py:39` | yes |
| LOW_WINDOW_SILL | **1.0 m** | `enterability.py:40` | classifier |
| APPROACH_CLEARANCE (site) | **1.5 m** in front of an entry | `lot/site_enterability.py:47` | yes (hard gate) |

`enterability.py:27-29` states the source band verbatim: "player 1.8 m tall, crouch ~1.1-1.25 m, capsule radius 0.35-0.45 m (so a ~0.7-0.9 m gap is the passable width band); doorway min width 0.9-1.1 m; a sill within ~1.2 m of the floor is vault-up reachable."

### 2.5 Site steps — `lot/site_steps.py`

| Quantity | Value | Line |
|---|---|---|
| `unassisted_step_max_m(R, angle) = R * (1 - cos(angle))` | function | `:153-155` |
| floor_max_angle used | **45.0 deg, hardcoded** | `:451` (`angle = 45.0`) |
| radius used | `characters.player.radius_m` from the contract = **0.35** | `:443` |
| resulting limit | **0.1025 m** | computed |
| assist | `characters.player.max_step_up_m` = **0.5 m** | `:444` |
| FLUSH_M (ignore) | 0.02 m | `:54` |
| MAX_STEP_OF_INTEREST_M | 1.0 m ("above this a transition is a wall by intent") | `:56` |
| SIDEWALK_H (quoted) | **0.16 m** — "a wall to a stock CharacterBody3D" | `:24`, `:32` |
| slab band each of road/path/courtyard must sit in | `[SIDEWALK_H - limit, limit]` = [0.0575, 0.1025] | `:28` |
| measured drift incident | COURT_THICK had drifted to **0.12** against a limit of **0.1025** | `:29-30` |
| route sampling step | `len/0.5` samples | `:96` |
| measured false-positive | clearance 3.43 m vs a 3.00 m half-width | `:116-118` |

Severity split: `LOT_STEP_BLOCKS_A_ROUTE` **major** (`:283`), `LOT_STEP_TOO_TALL_TO_WALK` **major** (`:307`), `LOT_STEP_NEEDS_ASSIST` **minor** (`:333`). Exit codes: 1 = major finding, 2 = could not check, 0 = clean (`:485-489`).

### 2.6 Layout lint — `deli_counter/layout_lint.py`

| Rule | Threshold | Line | Severity |
|---|---|---|---|
| COMMON_PATH_MAX (room depth needing 2 exits) | **7.0 m** | `:24`, used `:487` | WARN |
| TRAVEL_MAX (room-graph travel to an exterior exit) | **60.0 m** | `:25`, used `:526` | WARN |
| DEAD_END_MAX (single-opening connector depth) | **6.0 m** | `:26`, used `:531` | WARN |
| HALL_MIN_SH (venue public hall storey height) | **4.2 m** ("< reads flat") | `:27`, used `:573` | WARN |
| COVER_REPEAT_MAX | 3 identical volumes | `:28`, used `:593` | WARN |
| L2 exterior exits | >= 2 exits on >= 2 faces | `:495-497` | **FAIL** |
| L3 no path to EXT | — | `:521` | **FAIL** |
| L10 dead opening | opening must join two distinct rooms | `:288-313` | **FAIL** |
| L11 orphan wall | `real < 0.5 m` and `orphan > 0.5 m` of a 40-sample span, EPS 0.35 | `:256`, `:270`, `:284` | **FAIL** |
| L12 unreachable room | — | `:383-386` | **FAIL** |
| L13 partition overshoot | > **0.05 m** | `:177` | WARN |
| L14 ladder hole overshoot | > **0.05 m** | `:227` | **FAIL** |
| L15 partition blocks ladder hole | — | `:249` | WARN |
| L6 main-entry face touch tolerance | 0.3 m; entry door = width >= **2.0 m** or tag `entry*` | `:551-559` | WARN |
| L3 default hop distance | 3.0 m when a centroid is unavailable | `:508` | — |

Site scale, `lot/site_layout_lint.py:37-43`: SPINE_MIN **40 m**, SPINE_MAX **220 m**, EXTRACT_MIN **30 m**, LANE_MIN/MAX **3/8**, KILL_LANE **40 m**, COVER_NEAR **8 m**, SPREAD_MIN **90 deg**.

### 2.7 Scoring weights (stair placement, `stair_place.py:136-141`)

Positive: corridor_connection_quality **30**, discharge_quality **25**, vertical_stack_efficiency **20**, separation_from_other_stairs **15**, structural_grid_alignment **10**, archetype_fit **10**, exterior_visibility **5**.
Negative: usable_area_damage **-20**, corridor_dead_end_penalty **-20**, route_dependency_penalty **-30**, gameplay_chokepoint_penalty **-40**.

Discharge quality decays `max(0.2, 1.0 - 0.25 * hops)` (`:436`), times 0.8 when a direct-discharge profile lands off the perimeter (`:439`). Pair bonuses: `+10 * min(1, dist/diag)` coverage, `+5 * min(1, (dist-required)/diag)` separation, `-10` for a shared discharge destination (`:568-572`).

Ladder placement weights (`ladder_place.py:88-94`): route_continuity **30**, destination_relevance **25**, clear_upper_landing **25**, service_adjacency **20**, clear_lower_landing **20**, rear_or_side_facade_fit 12, structural_alignment 10, security_fit 8; penalties door_window_conflict **-40**, vehicle_conflict **-40**, utility_hazard -30, excessive_climb -25, weather_hazard -15, public_facade -12, visual_noise -5.

### 2.8 Numbers defined twice that should agree

1. **Unassisted step height — THREE different values for one quantity.**
   - `agent_contract.json:35` — **0.1025 m** (R = 0.35, the body), and `:36` explicitly narrates the fix: "using it recorded 0.117 while the gate enforcing it reported 0.103, two numbers for one quantity."
   - `lot/site_steps.py:12-13` — docstring still says "**0.117 m**" and "this stack's **0.4 m** player capsule". The *code* reads 0.35 from the contract (`:443`), so the shipped number is right and the prose is stale by the exact defect the contract was edited to close.
   - `deli_counter/stairwell.py:1356-1357` — "A capsule only walks up `radius * (1 - cos(floor_max_angle))`, which is **0.146 m** for the contract body." 0.146 implies R = 0.5, which is no radius in the contract (0.35 body, 0.4 bake, 0.35 walker). This is the ramp-foot module, i.e. the one place the number decides real geometry.

2. **`agent_contract.py` fallbacks are stale against `agent_contract.json`.** The module docstring asserts "every consumer keeps a hardcoded fallback equal to the ratified values" (`agent_contract.py:6-7`), but `_DEFAULTS` at `:34-35` carries `agent_max_climb_m: 0.5` and `cell_size_m: 0.15` — the pre-2026-07-28 / pre-07-29 numbers. `nav_gate.gd:43-58` fixed exactly this same class of staleness in itself and documented it; `agent_contract.py` did not get the same edit.

3. **`nav_gate.gd:31-32`** comment reads "0.15 m cells matter ... 0.25 m cells eat 1.0 m of every doorway" while `CELL_SIZE` beneath it is now **0.10** (`:57`). Stale prose against a corrected constant.

4. **Door width has four numbers.** `min_door_width_m 1.25` (contract, nav-warn only), `MIN_PASS_WIDTH 0.7` / `CLEAN_WIDTH 0.9` (`enterability.py:35-36`, the only *blocking* width), `_PUNCH_DOOR_W 1.1` (`stair_core.py:43`), and "doorway min width 0.9-1.1 m" quoted from scale_guidelines in `enterability.py:29`. A 0.95 m door passes the entry gate cleanly, fails the nav proxy as a warning, and is 0.3 m under the ratified minimum.

5. **Crouch height.** `enterability.py:37` `MIN_PASS_HEIGHT = 1.1` vs `agent_contract.json:9` `crouch_height_m: 1.2`. The gate lets a body through a 1.1 m opening the contract says it is 1.2 m tall crouching.

6. **Lateral containment envelope vs pass band.** `LATERAL_ENVELOPE = 0.5` (`stairwell.py:354`) with a comment instructing "use the largest body envelope per the invariant; cf. `_AGENT_PASS_WIDTH`" — and `_AGENT_PASS_WIDTH = 0.7` (`stairwell.py:624`). The constant used is 0.2 m below the constant it cites.

7. **Site body-fit thresholds are a hand-copy.** `lot/site_enterability.py:30-32`: "Body-fit thresholds mirror Deli Counter's enterability.py ... duplicated because Lot is a standalone repo with no Deli Counter import. Keep the two in sync if either changes." They currently agree (0.7 / 1.1 / 1.2 / 1.0), but `CLEAN_WIDTH` and `STAND_HEIGHT` are absent from the Lot copy, so the "tight squeeze" and "crouch-only" warnings do not exist at site scale.

8. **Mount headroom.** `LADDER_HEADROOM = 1.0` (`circulation.py:57`) vs `CLIMB_HEAD_CLEAR = 2.20` (`ladder.py:56`).

9. **Fall-protection trigger stated twice.** `FALL_PROTECTION_TRIGGER_M = 7.30` (`ladder.py:53`) and `fall_protection_trigger_m=7.3` repeated in all six profiles (`ladder_place.py:51,58,66,73,80,86`); the profile value is never read back against the constant.

10. **`cap_thick` deliberately duplicated.** `floors.py:88-91`: "Duplicated deliberately -- this module is pure and importing the Builder would drag bpy in -- and named the same so the pair is findable if either changes." An acknowledged, documented double definition.

---

## 3. MEASURED BUT ADVISORY (finds something, never blocks)

**Whole modules that are advisory by construction**

- `navigability.py` — every finding is a warning except a wholly isolated room: "All findings are reported as INTEL/warnings (navigation is a gameplay concern ...), EXCEPT a fully isolated room" (`:17-18`). So **every narrow doorway in the building is warn-only**: `f"NAV: {n} opening(s) narrower than ~{1.25}m may block a {0.4}m-radius nav agent"` (`:63-65`).
- `lot/site_layout_lint.py` — S1–S5 are all advisory: "Advisory layer: the engine gates (walktest, mp_smoke) stay the traversal truth" (`:24`).

**Stair findings that warn**

- `STAIR_LATERAL_OPEN` and `STAIR_OPENING_UNGUARDED` — the entire lateral-containment contract. `CONTAINMENT_ENFORCED = False` (`stairwell.py:353`); "findings are WARNINGS until deli_counter emits stair guard geometry; flip CONTAINMENT_ENFORCED to True to make them hard" (`:349-351`). They are also excluded from the `circulation_contract` stamp until then (`:1299-1300`, `:1313-1314`).
- `STAIR_DISCHARGE_ROUTE_HAS_MULTIPLE_TURNS` — > 3 rooms of discharge route, always a warning (`:989-993`).
- `BASEMENT_CONTINUATION_NOT_INTERRUPTED` — warning; "offline review can't see a barrier" (`:1004-1008`).
- `STAIR_TERMINATES_INTO_SLAB` — warning (`:1023-1026`).
- `STAIR_DOOR_OPENS_ONTO_TREAD` — Rule 4 door-on-treads, always a warning (`:1174-1178`).
- `STAIR_LOW_ARCHETYPE_FIT` — warning (`:1152-1157`).
- Unknown archetype / unknown role — warnings (`:936-938`, `:1144-1147`).
- Locked egress door **with** a backup egress stair — warning; only the no-backup case errors (`:1126-1137`).
- Declared transfer with no rooms to verify — warning (`:1217-1221`).
- Semantic findings (`STAIR_NOT_ENCLOSED`, `STAIR_ACCESS_THROUGH_PROHIBITED_ROOM`, `STAIR_NO_CORRIDOR_CONNECTION`, `STAIR_NO_GROUND_DISCHARGE`, `STAIR_VOLUME_INVADED`) are warnings for any stair **not** carrying an egress role — the `emit(gate, ...)` switch at `:920-921`, gated by `gate = role in EGRESS_ROLES` (`:930`). So a `public_convenience` stair sprouting mid-lobby with its shaft full of loot only warns.

**Ladder findings that warn**

- `LADDER_LOW_GAMEPLAY_CLEARANCE` — "may feel cramped for first-person traversal" (`ladder.py:1013-1017`).
- Rung spacing outside 0.25–0.36 m (`:1008-1012`).
- `LADDER_EXCESSIVE_HEIGHT` — > 3 storeys (`:1020-1024`).
- `LADDER_MULTIPLAYER_DEADLOCK_RISK` (`:998-1005`) and the AI-non-traversable warning (`:988-993`).
- `LADDER_NO_VISUAL_DESTINATION` — the dismount "leads nowhere useful" (`:664-667`).
- `LADDER_TOP_EDGE_RISK` — dismount near an unguarded roof edge (`:847-851`).
- `LADDER_PUBLIC_FACADE`, `LADDER_NEAR_PUBLIC_ENTRANCE`, `LADDER_NEAR_DRAINAGE` (`:812-831`).
- Unresolved top transition type (`:700-703`).
- `PARAPET_CROSSOVER_MISSING` — warning unless the role is an escape role (`:706-714`).
- Hatch ladder in a non-preferred room, hatch base sharing space with a door, missing access control (`:869-875`, `:908-914`, `:917-923`).

**Layout lint that warns**

L1 (deep room with < 2 openings), L3 travel > 60 m, L4 dead-end connector, L6 objective on the entry face, L7 flat venue hall, L8 missing signature program, L9 cover-box repetition, L11 orphan wall (WARN in the docstring at `:249-250` but appended to `fails` at `:284` — the code and its own doc disagree), L13 partition overshoot, L15 ladder tops into a wall, L16 marker/room mismatch.

L13's advisory status is explicitly justified: "This is a WARN, not a FAIL: the geometry builder now CLAMPS such walls at build time ... the warning just surfaces the authoring debt so presets get fixed at the source over time" (`layout_lint.py:163-166`).

**Entry findings that warn**

Every awkward-but-passable entry: breach/vault-only ways in, crouch-only entries, tight (0.7–0.9 m) entries, and a vaultable window a body cannot fit through (`enterability.py:122-145`).

**Site findings that warn**

- `LOT_STEP_NEEDS_ASSIST` — **minor** severity, off-route kerbs; "a kerb that is a wall is a kerb. Worth stating once ... but it is not a defect to go and fix" (`site_steps.py:330-333`).
- `LOT_SHELL_NO_COLLISION` — **major** severity but a *finding*, not a raise; the site still ships with the ground kept (`site_ground.py:280-293`).
- `LOT_SHELL_COLLISION_UNKNOWN` — **moderate** (`:295-306`).
- "building '{bid}' is reachable but no authored path/courtyard leads to a clear entry" (`site_enterability.py:201-204`).
- "building '{bid}' has no usable entry in its own gameplay.json" — a Deli Counter escape, warned rather than gated (`site_enterability.py:171-173`).

**The nav gate itself is advisory when Godot is missing**

> "a skip still returns True here, and that is why `check.py` printed 'All checks passed' for months with this gate never having baked anything. Changing it is a one-line edit; the reason it has NOT been changed here is that 13 of 103 shells currently fail, so flipping it now would block commits rather than inform anyone."
> — `deli_counter/nav_gate.py:134-138`

Also warn-only inside the gate: the marker-reachability section. "As a secondary section it checks every gameplay marker is reachable from the first spawn" (`nav_gate.gd:17-18`); `_check_markers` returns counts but `_exit_code` is only set by stair failures (`nav_gate.gd:202-208`). **A level where the objective is unreachable from the spawn still exits 0.**

---

## 4. CONSPICUOUSLY ABSENT

### 4.1 HEADROOM over a stair — answered directly: **NO. It is never checked.**

**Stair validity is floor-polygon / landing-rect connectivity only.** Evidence, in order of strength:

1. **`min_headroom_m: 2.0` exists in the contract and has zero consumers.** It is declared at `agent_contract.json:33` and mirrored into the fallback at `agent_contract.py:37`. A repo-wide search for `min_headroom` across the staged tree returns exactly three hits — the JSON, the Python fallback dict, and a copy inside `lot/lot.py:63`. `agent_contract.py` exposes accessors `min_door_width()` (`:84`) and `min_corridor_width()` (`:88`); **there is no `min_headroom()`**, and no module reads `clearances.min_headroom_m` by any path. It is a ratified number with no gate behind it.

2. **The clearance review is entirely planar.** `clearance_findings` (`stairwell.py:200-323`) tests four things per endpoint, all in XY: the landing rect against the inner wall faces (`:227-233`), partitions crossing the landing (`:246-283`), volumes on the landing (`:285-297`), and other stairs' footprints (`:299-309`). The only use of z is `z_lo, z_hi = story * H, (story + 1) * H` (`:286`) — a *storey band filter* deciding which volumes are on this floor at all, not a clearance measurement. Nothing computes distance from a tread to anything above it.

3. **The reserved stair column is explicitly infinite in z and never compared to a body height.** `circulation.stair_volume(system, z_lo=-1e6, z_hi=1e6)` (`circulation.py:140`) with the rationale "a prop at any height inside the shaft blocks a flight, a landing, or the well" (`:143-144`). This is a *prop-exclusion* volume. It answers "is something in the shaft" and never "is there 2 m of air above tread 7".

4. **`nav_endpoints` are 2D points lifted to the storey floor.** `stairwell.derive` writes `"point": [x, y, story * H]` (`stairwell.py:808-810`, `:813`). The upper endpoint's z is `hi_s * H` — the floor of the upper storey, with no reference to the slab above it.

5. **The authoritative engine gate proves connectivity, not clearance.** `nav_gate.gd` bakes and then asks exactly two questions per stair: do both endpoints snap within `SNAP_MAX` (2.0 m, `:185-189`), and is there a path in the undirected polygon graph (`:190-192`). Statuses are `ok` / `off_navmesh` / `no_path` (`:191`, `:186`, `:194`). There is no headroom status.

6. **The one *implicit* headroom check, and its limits.** `nm.agent_height = AGENT_HEIGHT` (1.8 m) is set at `nav_gate.gd:116`. Recast's `walkableHeight` does discard voxel spans with less than 1.8 m of vertical clearance, so a stair running under a 1.5 m soffit would fail to bake there and surface as `no_path` / disjoint islands. That is a real but **indirect and unnamed** protection: it (a) uses 1.8, not the ratified 2.0 `min_headroom_m`; (b) reports as a connectivity failure with no mention of headroom, so a reader gets "endpoints on disjoint islands (lower on 2, upper on 5)" (`:195-196`) and has to infer the cause; (c) only fires when the shell has actually been built and Godot is present — and a missing Godot binary **passes** (`nav_gate.py:134-140`); and (d) catches only total blockage, never the 1.9 m ducking-height stair the 2.0 m constant was written for.

7. **The stairwell module names headroom-shaped checking as somebody else's job and then that job never appears.** `stairwell.py:339-343` distinguishes its rect-resolution proxy from asking whether the built collision forms "a continuous wall **taller than the capsule** at every point — that is the build-time geometry gate's job (Layer C of the containment audit)". Nothing named Layer C exists in this area; the containment findings are also `CONTAINMENT_ENFORCED = False`.

8. **The test suite confirms it.** `test_stair_clearance.py` has 34 tests (`:20-334`); every one is a planar landing/endpoint/footprint/role test. No test name or body mentions height, ceiling, soffit, or vertical clearance.

9. **The ceiling that would eat a stairwell is subtracted geometrically, never measured.** `floors.room_voids` cuts the ceiling skin around slab holes with the explicit warning "The ceiling one caps the stairwell: you see ceiling above the staircase and you cannot climb it" (`floors.py:142-143`). So the failure mode is *known and named*. But the protection is "we remember to cut the hole", not "we measure the air above the flight". If a void were mis-tagged by the off-by-one the same docstring warns about (`floors.py:100-107`), the stair would be capped and nothing in this area would say so — the navmesh might still connect via the ramp, since the cap sits at ceiling level and the ramp is the only thing baked as walkable.

**Summary: the only thing standing between a shipped level and a stair you have to crawl up is Recast's `walkableHeight` at 1.8 m, applied silently, reported as a graph failure, skipped whenever Godot is absent — and it does not use the 2.0 m number the project ratified.**

### 4.2 Other things not measured that the area's own comments imply matter

**Stair pitch / slope is never validated anywhere in this area.** `agent_contract.json:26` and `nav_gate.gd:120-121` both say "slope legality is validate.py's job, connectivity is the bake's" — twice, as a deliberate division of labour. `validate.py` is outside this area, and nothing in `stairwell.py`, `stair_place.py` or `stair_core.py` computes a pitch angle from `story_height / run` or compares it to anything. `stair_place.stair_dims` (`:186-197`) produces run and rise and never checks the resulting angle. The riser itself is only ever a *target* (`riser_target` 0.16–0.19), never a bound: `n = max(6, round(H / riser_target))` means an unusual `story_height` silently yields whatever riser it yields. **There is no upper bound on riser height and no bound on pitch in this area.**

**Stair width is emitted but never gated.** `clear_width_m` goes into gameplay.json (`stairwell.py:800`), `two_way_passable: width >= 1.1` and `max_agents_abreast: width // 0.7` are computed (`:759-761`) — and none of the three is ever compared to a minimum or raised as a finding. A 0.6 m stair proposes `max_agents_abreast: 1`, `two_way_passable: false`, and passes. Contrast the ladder, which *does* warn at `width < 0.50` for exactly this reason (`ladder.py:1013-1017`).

**`min_corridor_width_m: 1.1` is defined and has an accessor but no caller.** `agent_contract.py:88-90` exposes `min_corridor_width()`; a repo-wide search finds no other reference. Corridors are matched by *role name* throughout (`CIRCULATION_ROLES`, `stairwell.py:59-62`) and never by measured width. `layout_lint` measures room depth (L1, L4) but never room *width*. So a "corridor" 0.8 m wide is a corridor by declaration.

**Ladder lower-landing clearance is declared and never enforced.** `LOWER_CLEAR_W = 1.20` / `LOWER_CLEAR_D = 1.20` (`ladder.py:54-55`) are the spec's s10 numbers for the safe approach the module's own governing rule demands — "It must have a defined purpose, **a safe approach**, a safe transition at the top" (`:17-18`). Neither constant is referenced anywhere. What actually gets checked is `climb_rect` (`:191-204`), which uses `GAMEPLAY_MOUNT_W = 0.80` and `max(depth + 1.0, 1.2)` — different numbers, and only for *intrusion*, never for "is there floor here". `FIXED_CLEAR_WIDTH_MIN = 0.41` is likewise dead.

**Nothing checks that a landing is level, or that two landings at the same nominal storey are at the same height.** Landings are rects with a z of `story * H` by assertion (`stairwell.py:808-810`). A mezzanine or split level would be invisible to every check in this area.

**No check that a stair's slab hole and its footprint agree.** `containment_findings` says so explicitly: "It drives off the reserved FOOTPRINT (always in the spec), not the slab holes, because a stair's own cut_slabs holes are appended by the builder and are not present at review time" (`stairwell.py:345-347`). So the hole that actually gets cut is never compared to the footprint that was reserved. `layout_lint` L14 does this for *ladders* (`:214-222`) and there is no L14 equivalent for stairs.

**Door swing is never checked, anywhere, and three modules say so.** `enterability.py:163-164` ("entry swing/vault clearance on both faces is a walk-test fact"), `stair_place.py:31` ("Enclosure walls, doors, and swings remain authoring work"), `ladder.py:911-914` ("confirm the door swing clears the ladder"), `site_enterability.py:22-24`. The *approach depth* is checked (`DOOR_CLEARANCE = 0.6`, `circulation.py:61`) but a 0.9 m door leaf swinging into a 0.6 m clearance box is not.

**No path-length or travel-time budget for vertical circulation.** `layout_lint` L3 measures horizontal room-graph travel against 60 m (`:25`, `:521-527`) using centroid distances; the graph in `reachability_findings` links stairs as free edges (`:343-354`). Climbing four storeys costs nothing in the travel metric. `walk_speed_mps: 4.0` sits in the contract (`agent_contract.json:11`) and is read by nothing in this area.

**No check that markers/objectives are reachable, at blocking severity.** `layout_lint` L12 gates room reachability (`:383-386`) but rooms only. The marker check exists solely in `nav_gate.gd:306-334` and never sets `_exit_code`. `navigability.py` errors on an isolated *room* (`:87-89`) and warns on everything else.

**No fall-damage or drop-height model.** `layout_lint.reachability_findings` counts "floor holes / hatches (vertical drops)" as connections (`:361-366`) with no height limit at all, so a room reachable only by a 12 m drop is a reachable room. `FALL_PROTECTION_TRIGGER_M = 7.30` exists for ladders (`ladder.py:53`) and nothing analogous exists for a hole in a slab.

**`LADDER_HEADROOM` and `CLIMB_HEAD_CLEAR` protect the *mount and dismount*, never the climb itself against a ceiling.** `_volumes_in_climb` (`ladder.py:377-391`) tests `not (v_top < z0 or v_bottom > z1 + CLIMB_HEAD_CLEAR)` — an intrusion test against declared *volumes*. Slabs, ceilings and roof structure are not `spec.volumes`, so the one place in the area with a genuine vertical-clearance constant still cannot see a ceiling.

**`STAND_HEIGHT`/`CLEAN_WIDTH` warnings do not exist at site scale.** `lot/site_enterability.py:38-43` copies only four of the six DC thresholds, so a compound of crouch-only, 0.75 m-wide buildings passes site enterability without comment.

**The prop-vs-circulation gate has no stair-side equivalent to `check_shell`'s own lesson for *ladders and doorways at spec time*.** `circulation.check_shell` runs on the built GLB (`:236`). The volumes it builds come from `gameplay.markers` and `slots` (`:154-176`) — i.e. post-build artifacts. There is no spec-time prop-vs-doorway check; `stairwell.py`'s Rule 10 covers the stair shaft only (`:1043-1077`), and nothing checks a `spec.volume` parked in a doorway aperture.
