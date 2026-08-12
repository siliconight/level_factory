# Combat, Threat and Readability — recovered theory of quality

Scope: `deli_counter/{combat_audit,tactical,sightlines,probe_fights,pvp_heist,guards,agent_contract}.{py,json}`
and `lot/{site_cover,site_tactical,site_audit}.py`.

All line references are to the files as staged on 2026-08-07 from
`C:\Projects\gabagool_studios\gabagool_factory`.

Two scales run the same theory:

| | building scale (Deli Counter) | site scale (Lot) |
|---|---|---|
| structural grammar | `combat_audit.py` | `lot/site_audit.py` |
| graph / mode gates | `tactical.py`, `pvp_heist.py` | `lot/site_tactical.py` |
| geometry / LOS / cover | `sightlines.py` | `lot/site_cover.py` |

`site_tactical.py` states the parallel explicitly (`site_tactical.py:6-11`):
> "Deli Counter reasons about reachability and the three modes WITHIN a building
> (over rooms and doorways). Lot reasons about them ACROSS the site (over
> buildings and the paths you declared between them). Same two ideas, one scale up."

---

## 1. ASSERTED DESIGN INTENT

### 1.1 The thesis statement

`combat_audit.py:3-6`:
> "The existing checkers answer "is it buildable / reachable / sane?". This one
> answers "will it FIGHT well?" -- 4-player PvE co-op FPS combat lives or dies
> on structure the other gates don't measure"

`combat_audit.py:35-36` (and repeated verbatim at `:988`, and echoed at
`site_audit.py:299-300`):
> "Severity: HIGH structural combat problems; MED costs fun but playable; INFO
> context. This is a structural estimate, not a measure of fun -- walk it."

This is the governing epistemic claim of the whole area: the pipeline believes
structure *predicts* fight quality but does not *constitute* it. Every module in
this area says some version of it (`sightlines.py:20-22`, `site_tactical.py:11-16`,
`site_cover.py:12-16`, `site_audit.py:30-31`).

### 1.2 Loops — the single biggest lever

`combat_audit.py:9-11`:
> "LOOPS route-graph cycles. Zero loops = a tree = every fight is a
> one-corridor siege; players can never flank, AI can never surprise.
> Interior loops are the single biggest lever."

`combat_audit.py:718-722` (the HIGH finding text):
> "route graph is a pure tree (0 interior loops): every fight is a one-corridor
> siege; no flanking for players or AI. Add at least one second connection
> between wings (a door, a breach wall, a window vault)."

`combat_audit.py:724-727`:
> "only 1 interior loop across {n_nodes} rooms; combat will settle into one
> circuit. A second loop (upper story or back-of-house) adds real route choice."

### 1.3 Chokepoints — drama in moderation

`combat_audit.py:12-13`:
> "CHOKES articulation rooms (removing one disconnects the graph). A few are
> good drama; a graph that is ALL chokepoints is a slog."

This is the clearest statement in the codebase that a design property is
*non-monotonic* — some is good, all is bad. Nothing else in this area says that.

### 1.4 Dead ends and the climax

`combat_audit.py:14-16`:
> "DEAD ENDS degree-1 rooms. Fine for closets; bad for combat rooms; a
> dead-end OBJECTIVE room turns the climax into door-camping."

`combat_audit.py:731-733`:
> "objective room is a dead end: the climax becomes door-camping one threshold"
> / "combat-intent room is a dead end (one way in = one way out)"

`combat_audit.py:157-159` — the counter-case, why open ground is exempt:
> "Outside-the-footprint grade room (forecourt, yard): open ground, so a graph
> 'dead end' there is not a siege -- it's approachable from anywhere outside."

### 1.5 Faces and flanking geometry

`combat_audit.py:17-18`:
> "FACES which building faces carry entries. One-face entry = attackers and
> reinforcements all use the same funnel; no exterior flank."

`combat_audit.py:744-748`:
> "all exterior entries sit on {faces} face(s): no exterior flank pressure is
> possible; attackers and reinforcements share one funnel. Add a rear/side door,
> breach panel, or vault window on another face."

`combat_audit.py:750-752` — a ranked preference, not a binary:
> "entries on adjacent faces only ({faces}); opposite-face entries create the
> strongest flank geometry."

`pvp_heist.py:346-348`:
> "PVP-FLANK: all entries on one face and no vertical alternate -- no flanking
> opportunity exists (attackers are fully predictable)"

### 1.6 Width — the squad is four bodies, and it carries things

`combat_audit.py:19-21`:
> "WIDTH a 1.1-1.2 m door passes ONE agent. Co-op wants at least one wide
> (>=1.4 m) route toward the objective or fights stack up in frames."

`combat_audit.py:53`:
> "WIDE_DOOR = 1.4  # >= passes two agents / a loot carry comfortably"

`combat_audit.py:767-770`:
> "objective room '{ob}': widest way in is {w} m (single-file). One >= 1.4 m
> opening lets the squad enter as a unit and loot-carry out."

`combat_audit.py:493-494`:
> "loot carry: from each objective, a >= 1.2 m route must reach a >= 1.4 m
> exterior egress (bags don't fit through squeezes)"

`combat_audit.py:516-519`:
> "the loot leaves single-file through a pinch."

`combat_audit.py:384-385` names the concept: "The loot-carry graph."
`combat_audit.py:399-400` gives the transport rule:
> "open plan is carry-wide; verticals: stairs carry bags, ladders don't"

### 1.7 Verticality — a floor with one stair is not a level

`combat_audit.py:21-22`:
> "VERTICAL an upper story with exactly one way up is a vertical dead end:
> the whole floor plays as one siege. Two+ links make it a level."

`combat_audit.py:791-795`:
> "stories {st}->{st+1} connect by exactly 1 vertical link: the upper floor
> plays as a single siege. A second link (ladder, second stair, roof hatch)
> turns it into a level."

Note the word "level" is being used as a quality threshold, not a noun.

### 1.8 Cover and kill boxes

`combat_audit.py:23-24`:
> "COVER combat-range rooms >35 m^2 with no waist-high volume and no cover
> markers = open kill boxes."

`combat_audit.py:809-812`:
> "room '{r.id}' is {area} m^2 with combat intent and ZERO waist-high volumes
> or cover markers: an open kill box. Two or three 0.9-1.2 m volumes fix it."

`combat_audit.py:239-240` — what counts as cover, and why:
> "anything solid and at least waist-high breaks sightlines: crates, counters,
> machines, pillars, shelving, the vault box itself"

### 1.9 Cramp — four capsules plus enemies

`combat_audit.py:25-26`:
> "CRAMP rooms narrower than ~2.2 m that author a combat_range: four capsules
> + enemies do not fit."

`combat_audit.py:803-806`:
> "room '{r.id}' authors combat_range={cr} but is only {d} m at its narrowest:
> four capsules + enemies do not fit. Drop the combat intent or widen it."

The player-count assumption (4 co-op) is load-bearing for both this rule and
WIDTH; it appears nowhere as a constant.

### 1.10 The three genre grammars (PayDay 2 / Ready or Not / L4D2)

`combat_audit.py:279-283`:
> "genre rule packs -- PayDay 2 / Ready or Not / Left 4 Dead 2 grammars.
> Enabled with --rules; "auto" picks packs by spec mode."

**Heist grammar (PayDay).** `combat_audit.py:467-471`:
> "[heist] every route to objective '{ob}' funnels through the same rooms: one
> crew plan, no split assault. A second disjoint approach (breach wall, window
> vault, vertical) makes plans differ."

`combat_audit.py:472-473`:
> "holdout: the drill-defense space -- objective room or a neighbor with 2-3
> coverable ways in and something to hide behind"

`combat_audit.py:488-492`:
> "[heist] no defensible holdout at/next to objective '{ob}' (want a room with
> 2-3 coverable entries, >= 12 m^2, and cover): the drill/objective-wait phase
> has nowhere to fight from."

`combat_audit.py:526-528`:
> "[heist] no camera_socket or patrol_point markers: the map has no stealth
> layer to beat -- loud-only by construction."

**CQB grammar (Ready or Not).** `combat_audit.py:345-349`:
> "Fraction of the room's floor visible from a point 0.5 m inside the
> threshold, occluded by solid volumes (>= 0.9 m tall) in the room. The Ready
> or Not 'first slice' number: how much of the room can be cleared from the
> doorway before committing."

`combat_audit.py:365-367` — an explicit model of what a player physically does:
> "nudge the vantage toward the room centroid (an entering player steps in, not
> stands in the frame) and never count a blocker the vantage is inside of --
> that's the ray-caster blinding itself"

`combat_audit.py:541-543`:
> "feed type: distance from the door to the nearest corner along its wall.
> Corner-fed doors give the entry team one hard angle; center-fed doors expose
> them to both flanks at once."

`combat_audit.py:557-560`:
> "[cqb] the approach to '{r.id}' via '{other}' is {d} m deep at the door: no
> room to pie the threshold -- the stack breaches blind."

`combat_audit.py:562-564` — a statement about player agency:
> "threshold visibility per room, judged on the BEST door: the entry team picks
> its threshold, so a room is only blind if EVERY way in is blind, and only
> naked if every way in sees everything."

`combat_audit.py:574-578`:
> "[cqb] '{r.id}': every doorway sees {p}% of the room -- nothing to clear,
> nowhere to hide. One or two hard corners or tall blockers give the entry a
> decision."

`combat_audit.py:580-584`:
> "[cqb] '{r.id}': the BEST doorway sees only {p}% of the room -- every entry
> commits blind into hard corners, grenade-bait. Open the first slice from at
> least one threshold to ~50-90%."

`combat_audit.py:601-603`:
> "[cqb] all {tot} interior doors are {only}-fed: every room clears the same
> way. Mixing feed types varies the entries."

**Flow grammar (L4D2).** `combat_audit.py:635-639`:
> "[flow] the entry->objective path ({path}) never changes scale: no
> compression/release rhythm, the run reads as one long corridor. Alternate
> tight connectors with open rooms."

`combat_audit.py:642-645`:
> "[flow] '{rid}' on the main path has {n} connections: heavy wayfinding load
> at one decision point."

`combat_audit.py:667-670`:
> "[flow] holdout room '{a}' has only {n} way(s) in: the horde single-files and
> the holdout is a shooting gallery. Arenas want >= 3 ingress vectors from >= 2
> directions."

`combat_audit.py:675-677`:
> "[flow] only {hs} horde_spawn marker(s): director has few ingress choices;
> waves will feel same-y."

**The grammars are declared mutually contradictory and reconciled by mode.**
`combat_audit.py:646-650` is the most interesting design note in the file:
> "horde-arena rules apply to horde contexts: finale rooms always, and
> fortifiable/objective rooms only in survival/assault modes. A heist drill room
> WANTS 2-3 coverable entries (the PayDay holdout rule); demanding >= 3 ingress
> there would contradict the heist grammar."

i.e. "how many ways into the holdout" has no universal right answer: 2-3 for a
heist drill, >=3 from >=2 directions for a horde finale.

### 1.11 Authored intent can override the audit

`combat_audit.py:883-886`:
> "author-accepted findings: a spec can declare intended designs
> ("audit_accept": [{"code","room","why"}]) -- a one-breach vault may be the
> climax. Accepted findings downgrade to INFO with the reason, so they stay
> visible without nagging."

Also `combat_audit.py:773-776` (OBJ_AT_DOOR):
> "a designed breach shortcut if intended; gate it in game code or accept the
> speedrun line."
And `:778-780` (OBJ_DEEP): "long approach -- fine if the route fights well."

### 1.12 Intel vs judgement (tactical.py)

`tactical.py:476-480` — the sharpest statement of the tool's self-limit:
> "PATH METRICS (informational): route count + chokepoints from entries to each
> objective. These are intel for the gameplay engineer, NOT judgments -- the tool
> makes models, not gameplay. A single route to an objective may be exactly what
> the designer wants; we report it, we don't flag it. Only reachability (above)
> is a hard model-integrity gate."

Repeated for heist (`tactical.py:629-631`: "a single forced route may be the
intended design (a committed push). Reported, not flagged.") and survival
(`tactical.py:758-762`).

`tactical.py:286-290`:
> "How many node-disjoint paths reach target from the start set -- a proxy for
> 'flanking options'. 1 = single forced route; >=2 = at least one flank.
> Node-disjoint means the paths share no intermediate room, so two routes that
> both funnel through one hallway count as one."

`tactical.py:259-264`:
> "These work on the room adjacency graph... They answer "design quality"
> questions, not just "is it connected": how many distinct ways to reach a
> target, what gets funneled through a single room, how long the route is.
> Room-resolution (not capsule-accurate)"

`tactical.py:104-107` — why open plans are a special case:
> "open-plan adjacency: two same-story rooms whose rects share an edge with NO
> partition covering it are one continuous space (a lobby flowing into a
> bullpen). Without this, open floor plans read as disconnected and open-plan
> rooms false-flag as dead ends."

`tactical.py:669-677` — the survival level as a shape:
> "Survival mode: co-op PvE horde defense. The level is a directional run --
> players move from a start safe-room, through the building, to a finale holdout
> where they survive a final wave (and optionally a rescue/escape)... validate
> that (1) there's a start and a finale, (2) the finale is reachable from the
> start through the building, and (3) there are horde spawns to apply pressure
> along the way."

`tactical.py:684` — the boundary of the tool's ambition:
> "The AI director / wave state machine lives in your game code; the level just
> provides geometry."

### 1.13 Sightlines: the five things geometry says about a fight

`sightlines.py:10-19`:
> "- death lane : the longest unobstructed sightline on a floor (the angle
>    that dominates every fight near it).
> - exposed run : the longest stretch of the spawn->objective approach with no
>    cover marker within reach (where you get caught out).
> - weak cover : cover markers with clear line of sight from the attack
>    direction (cover that isn't actually cover).
> - intent mismatch : a room's authored combat_range vs the sightlines its
>    geometry actually produces (a "close" room that plays long).
> - objective entries: independent ways into the objective room (1 = a funnel)."

`sightlines.py:20-22`:
> "This is INTEL, never a gate: it never fails a build... It is a GUIDE to
> authoring better buildings, not a pass/fail."

`sightlines.py:30-33` — the greybox epistemics:
> "Greybox assumptions (deliberately conservative): every opening is see-through
> (worst-case LOS through doors/windows); a volume blocks standing sight only if
> it is tall enough to cross eye height; cover markers are the authored intent
> for where cover will exist after the art pass."

`sightlines.py:261-263`:
> "Count openings bordering each objective room on this story (independent ways
> in). 1 = a funnel into the holdable point."

### 1.14 PvP: the same findings, promoted to gates

`pvp_heist.py:4-7` — the single most important structural claim in the area:
> "Unlike the PvE `heist` mode (crew vs. AI), both sides are players, so the
> *balance-critical* findings that combat_audit/sightlines report as advisory
> intel become hard gates here."

`pvp_heist.py:330-333`:
> "PVP-ROTATE: no protected defender rotation -- every defender route to the
> objective passes through an attacker entry room (defenders are exposed the
> moment they move)"

`pvp_heist.py:286-290`:
> "PVP-ROUTES: only one room-disjoint attacker route to the objective;
> pvp_heist requires at least two meaningfully different routes (add an
> entrance, breach, or vertical route)"

`pvp_heist.py:406-409`:
> "PVP-SPAWN-LOS: attacker spawn '{a}' and defender spawn '{d}' (story {s})
> have a direct clear sightline at spawn time"

`pvp_heist.py:118-125` — why parallel doors are not two routes:
> "every interior room can carry one route; each room-adjacency edge carries one
> route (parallel doorways between the same two rooms collapse -- they are not
> meaningfully different at room resolution)."

`pvp_heist.py:413-415`:
> "Every breach opening must connect two resolvable spaces (room<->room or
> room<->outdoors), never open into solid/void."

`pvp_heist.py:35-36`:
> "Network-agnostic by design: this validates markers and metadata only. It
> never prescribes how doors/breaches/objectives replicate at runtime."

### 1.15 Site scale: the run across open ground

`site_audit.py:5-26` is a compact design manifesto. Verbatim:
> "EXFIL SHAPE   PayDay: the escape should not rewind the entry. If the
>                extraction sits where the crew spawned AND the bearing home
>                is the bearing in, the second half of the heist is the
>                first half played backwards.
>  RESPONDER     PayDay: assault waves should arrive from spread directions.
>  PRESSURE      Responders bunched in one arc = every wave is the same
>                wave; a responder spawn on top of the exfil = spawn camping
>                by construction.
>  SAFE ANCHORS  L4D2: the run's endpoints (crew spawn, extraction) want a
>                backstop -- cover or a building edge to fight from. A naked
>                anchor in open ground is a shooting-gallery start/finish.
>  LEG RHYTHM    L4D2: every critical leg (spawn->objective, objective->
>                extraction) needs punctuation. A long leg with zero cover
>                in its corridor is an open-ground sprint, not a fight.
>  STREET CROSS  CQB, site-scale: a road is a long sightline both ways;
>                every critical-leg crossing is an exposure moment. Reported
>                so the author places cover or accepts the dash."

`site_audit.py:30-32` — calibration by a known-good artefact:
> "Report-only, like combat_audit: severities HIGH / MED / INFO, and a walked
> site that plays well should sweep clean (gs_heist is the calibration site)."

`site_audit.py:215-219`:
> "the {kind} at ({x},{y}) has no cover or building edge within {r} m: a naked
> anchor in open ground -- the hold there is a shooting gallery. Give it a
> backstop (cover cluster, alcove, or wall)."

`site_audit.py:232-236`:
> "the {label} leg is {L} m with zero cover in its {r} m corridor: an
> open-ground sprint, not a fight. One or two cover pieces along the line give
> the leg a rhythm."

`site_tactical.py:96-100` — honesty about the proxy:
> "Count edge-distinct first hops that can still reach `target` -- a cheap proxy
> for 'multiple independent approaches' (the site echo of an assault objective
> room needing >=2 access). Not full max-flow; intentionally simple and honest"

`site_tactical.py:316-320`:
> "protected hold: defenders spawn in the objective building itself, or in a
> building with a declared route to it that avoids the attacker staging
> building (they must be able to reach their post without crossing the attacker
> approach)."

### 1.16 site_cover.py — the richest single statement of the theory

`site_cover.py:1`:
> "Something to hide behind, so the floor is not open for across-the-site sniping."

`site_cover.py:3-10` — the diagnosis-vs-symptom argument, quoted at length
because it is the clearest "why" in the whole area:
> "Lot's answer to an unfair opening engagement used to be arithmetic on
> distance: if an enemy could see the crew, move the enemy. That is the cheapest
> possible response and almost never the right one. Push a spawn far enough out
> and the map still grades badly -- now for a first contact past the ceiling and
> a crew that walks a minute before it meets anything -- and the site is no
> better than it was. What made the opening unfair was that two markers could
> see each other across ninety metres of empty ground. The distance was the
> symptom; the empty ground was the defect, and the fix for empty ground is to
> put something in it."

`site_cover.py:12-16` — the soft-gate doctrine:
> "Laser Tag can say the map plays badly and it cannot place a crate, because it
> does not own the geometry. Lot owns the geometry. So a firefight evaluator's
> finding is a *soft* gate here: it never refuses a build, it changes what the
> build contains."

`site_cover.py:26-33` — cover height derived from the duel, not chosen:
> "a sightline is two lines, not one. Each side sights from its own eye at the
> other's chest, so the crew's outgoing line descends and the enemy's incoming
> line climbs, and they cross in the middle. A solid tall enough to break one can
> sit under the other, and half a broken sightline is not half a fix -- Laser Tag
> stamps first contact on the first shot fired by *either* side, so the free shot
> that remains starts the clock exactly where it was. `MIN_COVER_HEIGHT` is where
> the two lines cross, which is why it is derived here rather than chosen."

`site_cover.py:136-141` — cover placement has a *direction of play*:
> "Where in the usable interval to sit, 0 being the crew's end. A third of the
> way from the crew is deliberate: it gives the crew something to move between on
> its approach rather than handing the far end a wall to hold."

`site_cover.py:466-475` — the same idea as a bug story:
> "``bias`` is measured from the crew's end, which has to be established rather
> than assumed... A bias applied to the wrong end is worse than none -- it hands
> the enemy the wall to hold and leaves the crew crossing the open part."

`site_cover.py:131-134`:
> "Clearance between pieces. Two crates in contact are one wall, and a wall
> across a street is a route that no longer exists."

`site_cover.py:686-687`:
> "Cover the crew has to walk around is an obstacle; cover it can walk behind is
> cover."

`site_cover.py:548-565` — the opening vs the transit, and the measurement that
proved they are different problems:
> "That function asks about the OPENING: pairs of markers further apart than the
> range at which the fight starts, because a long open line between two spawns
> means somebody fires at t=0. This one asks about TRANSIT: stretches of the
> crew's path that lie WITHIN an enemy's reach with nothing in between. A route
> point 20 m from an enemy with clear ground between them is not a standoff
> problem, it is the crew walking through somebody's field of fire...
> Measured on `category5_baie_dore_001` seed 5017: the crew crossed 74 m from
> spawn to objective with all four pieces of cover clustered at the far end,
> 10.8-19.3 m from an enemy spawn. Every marker pair was answered and the
> approach was still bare, because no marker pair was ever on it."

`site_cover.py:816-819` (LOT_ROUTE_EXPOSED message):
> "This is not a standoff problem -- the crew is inside the firing envelope while
> it walks, so the bot takes hits it cannot answer and its cover-seek has nothing
> in reach to break for."

`site_cover.py:733-741` — the advisory doctrine, with one exception:
> "All advisory. A site with an open sightline is a site Laser Tag will play and
> mark down, which is a design signal and not a build failure... The one thing
> worth saying loudly is a line nothing could break, because that is a request
> for a building and no amount of street furniture will answer it."

`site_cover.py:249-256`:
> "the building you are standing in is not cover from the building you are
> standing in, and counting it lets a marker that landed indoors pass every
> sightline test on the site."

`site_cover.py:305-312`:
> "``limit`` is the range at which the engagement opens, so what comes back is
> the set of lines along which somebody can fire the moment the run starts.
> Longest first: the worst line on a site is usually the one whose fix also
> shortens three others."

### 1.17 Fairness of the opening (site_spawns, cited by site_cover)

`lot/site_spawns.py:42-49`:
> "Nearer than this and the crew is in contact before it has moved. Laser Tag
> grades that as INSTANT_CONTACT and NO_REACTION_TIME. A floor, not the rule. It
> was written as the rule, and it was chosen by eye"

`lot/site_spawns.py:80-84`:
> "The distance was never the mechanism though -- an enemy 20 m away around a
> corner is a fair fight and an enemy 30 m away down an open street is not -- so
> distance alone is not what the search below tests"

`lot/site_spawns.py:96-107`:
> "`OPENING_RANGE` on its own says "neither side can open fire from here", and an
> enemy standing at exactly that distance satisfies it while buying the crew
> nothing: both sides acquire on the same frame the map starts... The crew needs
> the fight to start after it has had a chance to move, so the standoff is the
> range plus the ground the crew covers in the time it is being given. One second
> is the floor, not a target. It is roughly a human reaction plus a step, and it
> is what separates "the map opened with a shot" from "the map opened"."

### 1.18 Readability, visual sense (`probe_fights.py`)

This module is about z-fighting, i.e. whether the *surface* of the level reads
cleanly — the only "readability" measure in the assigned set.

`probe_fights.py:4-6`:
> "A name pair says WHICH solids meet; it does not say HOW, and the fix for a
> junction depends entirely on how."

`probe_fights.py:11-16`:
> "It classifies the overlap by SHAPE only -- how many axes the two boxes are
> flush on, and how deep the interpenetration runs -- and prints that
> classification as a word, because "corner", "buried_end" and "duplicate" are
> descriptions of an overlap, not diagnoses of a cause. The cause belongs in the
> reply where it can be argued with."

`probe_fights.py:18-24` — two questions that must not be merged:
> "the gate asks "could this ever flicker", this asks "is anything currently in
> front of it". Where they disagree, that disagreement is the finding."

### 1.19 "A gate that cannot run is not a gate that passed"

A cross-cutting principle discovered by two separate twelve-day outages.

`pvp_heist.py:364-372`:
> "A GATE THAT CANNOT RUN IS NOT A GATE THAT PASSED. This used to be
> `except Exception: return errors, pairs` -- an empty findings list,
> indistinguishable from a clean level. Between 2026-07-24 and 2026-08-05 the
> sightline pass raised on every real spec... and this swallowed it, so
> PVP-SPAWN-LOS reported nothing while opposing spawns could stare straight at
> each other. Now the inability to check IS the finding"

`combat_audit.py:851-861`:
> "THIS BLOCK NEVER PRODUCED A FINDING. `sightlines.check` returns the tuple
> `(ok, report_lines)`, so `sl.get("warnings")` raised AttributeError on a tuple
> every single time, straight into `except Exception: pass`... the bare `pass`
> made both look like "no intent mismatches found"."

`combat_audit.py:872-875`:
> "Silence and "nothing found" must not look the same." / "every sightline/cover
> finding is MISSING, not absent"

`sightlines.py:24-28`:
> "It used to call `fp._opening_gaps` across the module boundary; that name was
> refactored away on 2026-07-24 and this whole pass raised AttributeError into
> four `except Exception` handlers for twelve days without a single red light."

`site_cover.py:400-410` (the read-back principle):
> "the search decides where a thing MAY go and the report describes the search,
> so a defect in the search reports itself as fine. Measuring the emitted
> rectangles is the only check that can disagree with the placer."

---

## 2. MEASURED, WITH NUMBERS

### 2.1 combat_audit.py — hardcoded module constants

All four are hardcoded at the top of the file; none come from `agent_contract.json`.

| constant | value | line | comment |
|---|---|---|---|
| `WIDE_DOOR` | 1.4 m | `:53` | ">= passes two agents / a loot carry comfortably" |
| `CRAMP_MIN_DIM` | 2.2 m | `:61` | "a combat room narrower than this can't hold a fight" |
| `KILLBOX_AREA` | 35.0 m² | `:62` | "combat room bigger than this with no cover = flag" |
| `COVER_MIN_H` | 0.6 m | `:63` | ">= waist high; taller solids block sight = also cover" |
| `KIND_DEFAULT_W` | door 1.2, window 1.6, garage 3.5, breach 1.5, vault 1.4, teller 2.0, safe_deposit 2.0 | `:54-55` | fallback opening widths when `op.width` is None |
| `UTILITY_ROLES` | {utility, restroom, storage, closet} | `:64` | exempt from DEAD_END |

Derived / structural thresholds inside `audit()`:

- **Loops** = `n_edges - n_nodes + comps` (cyclomatic number), `:711`.
  - `loops == 0 and n_nodes >= 4` → **HIGH `NO_LOOPS`** (`:717-722`)
  - `n_nodes >= 6 and loops == 1` → MED `ONE_LOOP` (`:723-727`)
- **Dead ends**: graph degree `<= 1`, excluding utility rooms and rooms
  <8 m² with no `combat_range` (`_is_utility`, `:150-153`), and excluding
  outdoor rooms (<10% of area inside the footprint, `_is_outdoor`, `:156-164`).
  HIGH if the room is an objective, MED otherwise (`:728-733`).
- **Chokepoints**: Tarjan articulation points (`:90-116`) restricted to rooms
  ≥ 4.0 m² (`:715`). Flags MED `CHOKE_HEAVY` when
  `n_nodes >= 5 and len(chokes) >= max(2, n_nodes // 3)` (`:734-738`) — i.e.
  **a third or more of rooms being chokepoints is "a slog"**.
- **Entry faces**: `len(faces) <= 1` and footprint ≥ 10 m on both axes →
  HIGH `ONE_FACE` (`:743-748`). Exactly 2 faces that are not {N,S} or {E,W} →
  INFO `ADJACENT_FACES` (`:749-752`).
- **Objective openings**: exactly 1 opening → HIGH `OBJ_ONE_DOOR` (`:761-765`);
  widest opening `< 1.4` → MED `OBJ_NARROW` (`:766-770`).
- **Objective depth** (BFS hops from entry rooms): `d == 0` → INFO `OBJ_AT_DOOR`;
  `d > 4` → INFO `OBJ_DEEP` (`:771-780`).
- **Vertical**: exactly 1 link between consecutive stories → MED
  `VERT_DEAD_END` (`:786-795`). `0` links is deliberately *not* flagged here
  ("navigability check owns unreachable stories", `:789`).
- **Cramp**: `_room_min_dim(r) < 2.2` on any room with `combat_range` → MED
  `CRAMPED` (`:802-806`).
- **Killbox**: `area >= 35.0` and `_cover_in_room == 0` → MED `KILLBOX` (`:807-812`).
  Cover counts volumes with `size_z >= 0.6` and `min(size_x, size_y) >= 0.3`
  within room bounds and within one storey height of the room's floor
  (`:238-249`), plus `cover_low` / `cover_high` markers inside bounds (`:250-254`).
- **Axis-swap lint**: HIGH `AXIS_SWAP` when every door on a partition opens
  within one room as authored but connects two rooms with the axis flipped
  (`:840-849`). Provenance note at `:817-818`: "This exact bug shipped in five
  presets before this check existed."
- **Sightline pass failure**: any exception in the `sightlines.analyze` loop →
  HIGH `SIGHT_DEAD` (`:871-875`).

### 2.2 combat_audit.py — genre rule pack thresholds (hardcoded)

**Heist (`_pack_heist`, `:459-528`)**
- `_disjoint_paths2` returns 1 and graph has ≥ 4 rooms → MED `H_ONE_ROUTE` (`:465-471`).
  (Greedy 2-path search: one BFS path, delete its interior, search again, `:430-455`.)
- Holdout candidate = objective room or a graph neighbour with
  **2 ≤ entries ≤ 3**, **area ≥ 12 m²**, and (`_cover_in_room > 0` or
  `role == "fortifiable"`); none found → MED `H_NO_HOLDOUT` (`:474-492`).
- Loot carry: BFS on `_width_graph(spec, 1.2)` must reach a room with an
  exterior opening **≥ 1.4 m**; else MED `H_CARRY_PINCH` (`:494-519`).
  Open-plan edges count as carry-wide when the shared edge is **≥ 1.2 m**
  (`:415`); stairs carry bags, ladders do not (`:399-400`, `:418-426`).
- `mode == "heist"` with zero `camera_socket` and zero `patrol_point` markers →
  INFO `H_NO_STEALTH` (`:520-528`).

**CQB (`_pack_cqb`, `:532-603`)** — applies only to `hot` rooms: objective rooms
plus rooms with `role == "fortifiable"` (`:534-536`).
- **Feed type**: distance from door to nearest corner along its wall
  **≤ 1.5 m = "corner"-fed, otherwise "center"-fed** (`:544-547`, `:596`).
- **Pie standoff**: approach room's min depth `< 1.6 m` → MED `C_NO_PIE` (`:552-560`).
- **Threshold visibility** (`_threshold_visibility`, `:345-381`): 8×8 = 64-sample
  floor grid; blockers are volumes with `size_z >= 0.9` whose base is within
  1.0 m of the room's floor; vantage sits 0.5 m inside the threshold, then is
  nudged **0.8 m** toward the room centroid.
  - best door visibility **> 0.97** and area **≥ 25 m²** and zero cover → MED
    `C_NAKED_ROOM` (`:572-578`)
  - best door visibility **< 0.35** → MED `C_BLIND_ROOM` (`:579-584`); the
    prescribed target is stated in the message as **~50-90%**.
- **Feed census**: ≥ 6 interior doors and all one type → INFO
  `C_FEED_MONOTONE` (`:598-603`).

**Flow (`_pack_flow`, `:607-677`)**
- **Rhythm**: on an entry→objective BFS path of length **≥ 4**, if every
  consecutive area ratio satisfies `|log(a[i+1]/a[i])| < 0.35`
  (**±42% area change**), → MED `F_FLAT_RHYTHM` (`:629-639`).
- **Branch overload**: a path room with **≥ 5** connections → INFO
  `F_BRANCH_OVERLOAD` (`:640-645`).
- **Arena ingress**: `finale` rooms always; `fortifiable`/objective rooms only
  when `mode in ("survival","assault")`; **< 3** ways in (openings + touching
  stairs) → MED `F_ARENA_STARVED` (`:651-670`).
- **Horde spawns**: `mode == "survival"` and **< 3** `horde_spawn` markers →
  INFO `F_FEW_HORDE_SPAWNS` (`:671-677`).

**Pack selection** (`packs_for`, `:683-692`): `auto` → heist+cqb+flow for
`mode in ("heist","pvp_heist")`, else flow+cqb.

### 2.3 tactical.py — the hard gates

`MIN_OPENING_WIDTH = 0.8` m (`:27`, "below this a passage is too tight").
Note this is *below* `agent_contract.json`'s `min_door_width_m = 1.25`; tactical
does not read the contract.

**Assault mode errors (block the build via `validate.py:132-134`):**
- exterior entry openings **< 2** → "only {n} attacker entry opening(s); need >= 2" (`:451-458`)
- any room unreachable from an entry (`:461-464`)
- objective room graph degree **< 2** → "need >= 2" (`:469-474`)
- any storey with no stair/vertical link, when `len(stories) > 1` (`:510-512`)
- any door/garage/breach opening with resolved width `< 0.8` m (`:515-520`)

**Warnings (never block):** missing breach class/material metadata (`:521-523`);
objectives without `attacker_spawn` / `defender_spawn` markers (`:530-534`);
"non-tactical spec (no rooms defined)" (`:437-438`).

**Traversal steepness** (`_traversal_warnings`, `:387-412`), warnings only:
- ramp slope `> rp.max_slope_deg`
- stair pitch **≥ 44.0°** → "at/over the 45deg walkable limit -- the ramp
  collider won't be climbable"
- stair pitch **> 38.0°** → "steep (walkable but uncomfortable)"
- recommended run: `story_height * 1.4` ("gives a gentler ~35deg")

**Route counting** (`_count_independent_routes`, `:286-355`): max-flow on a
node-split graph, node capacity 1 for intermediate rooms, uncapped for
starts/target and for inter-room edges; **counting stops at 8** —
`while flow < 8: # cap the count; "several" is enough` (`:350`).

**Heist mode** (`_analyze_heist`, `:565-666`): errors = no extraction zone
(`:578`), zero exterior entries (`:583-586`), objectives in unreachable rooms
(`:622-623`). Warnings = no objectives, no required objective ("extraction would
be valid immediately", `:589-592`), loot yielding 0 bags, loot with no
secure/drop/extraction zone (`:596-601`).

**Survival mode** (`_analyze_survival`, `:669-789`): errors = no safe_room zone
*and* no `survivor_spawn` marker (`:694-698`), no finale zone (`:699-700`),
finale unreachable from start (`:751-756`). Warnings = no exterior entry, zero
`horde_spawn` markers, **fewer than 3** horde spawns (`:708-714`).

### 2.4 sightlines.py — geometry constants (all hardcoded, `:41-49`)

| constant | value | meaning |
|---|---|---|
| `EYE` | 1.6 m | standing eye height (matches `agent_contract.json.characters.player.eye_height_m`, but is **not read from it**) |
| `SIGHT_BLOCK_H` | 1.6 m | a volume must be this tall to block standing sight |
| `COVER_R` | 2.5 m | a cover marker covers points within this radius |
| `CLOSE_M` | 8.0 m | ≤ this = "close" combat range |
| `LONG_M` | 20.0 m | > this = "long" combat range; between = "medium" |
| `GRID` | 1.5 m | reachable-sample spacing |
| `MAX_PTS` | 240 | per-storey sample cap (the O(n²) budget) |
| `ROUTE_STEP` | 0.5 m | exposed-run march step |

Computed per storey (`analyze_story`, `:170-234`):
- `death_lane_m` — longest clear pairwise sightline among sampled standing
  positions (`:180-187`); bucketed in the report against `LONG_M` / `CLOSE_M`
  (`:322-324`). **No threshold, no finding.**
- per-room `max_sightline_m` → computed `close`/`medium`/`long` (`:202`),
  compared against authored `combat_range` → `mismatch` boolean (`:206`).
- `exposed_run_m` — longest contiguous stretch of the **straight segment**
  `attacker_spawn → objective` with no cover marker within 2.5 m (`:208-219`,
  `_exposed_run` `:237-258`).
- `weak_cover` — cover markers with a clear ray from *any* `attacker_spawn`
  (`:222-229`), reported as `seen_from`/`of`.
- `objective_entries` — openings on the objective room's boundary, tolerance
  `eps = 0.4` m; the report marks `<= 1` as "**<- FUNNEL (single entry)**"
  (`:261-307`, `:329`).

Occluders (`_occluders`, `:67-106`): exterior walls and partitions minus their
opening gaps, plus footprints of volumes with `size_z >= 1.6` that straddle
`story*story_height + 1.6`.

`check()` returns `(True, lines)` **unconditionally** (`:343-345`).

### 2.5 pvp_heist.py — the numbers that block

- `SPAWN_MARGIN = 8.0` m outside the footprint, `ROOM_MARGIN = 0.5` m outside a
  declared room; beyond both = out of the playable envelope (`:43-48`, `:76-87`).
- **PVP-ROUTES**: `_disjoint_route_count` (Menger via unit-node-capacity
  max-flow, `:118-170`, `max_routes = 8`); `0` → error "no route at all",
  `< 2` → error (`:280-290`).
- **PVP-SPAWN-LOS**: any clear 2D ray between an attacker and a defender spawn
  on the same storey → error, one per pair (`:402-409`). Occluders are borrowed
  from `sightlines._occluders`.
- **PVP-FLANK**: `len(entry_faces) >= 2` passes; else if
  `ladders exist or len(stairs) > 1` it passes with a warning; else **error**
  (`:336-348`).
- **PVP-ROTATE**: BFS from defender rooms to objective rooms with
  `blocked = entry_rooms - defender_rooms - objective_rooms`; no path → error
  (`:325-333`).
- **PVP-EXTRACT**: BFS objective→extraction, falling back to entry rooms as the
  extraction (`:293-318`).
- **PVP-BREACH**: exterior breach must resolve to a room inside; interior breach
  must resolve to rooms on *both* sides (`:413-461`).
- **PVP-SPAWN-LOS-UNAVAILABLE**: import failure or occluder-build failure is
  itself an **error**, named per storey (`:373-401`).

### 2.6 guards.py + agent_contract.json — the body

`guards.py`: `MAX_STEP_UP = 0.5` m (`:108`, hard gate — "physically unclimbable:
a broken model", `:14-16`), `STEP_RISE_WARN = 0.4` m (`:109`),
`DEFAULT_STEP_RISE = 0.2` m (`:112`). Per-step rise is reconstructed as
`H / n` where `n = n_steps or max(6, min(40, round(H/target)))` (`:115-125`).

`agent_contract.json` — the declared single source of truth (`:3`: "THE single
source of truth for character/agent dimensions and every clearance derived from
them"):
- `player`: `radius_m 0.35`, `height_m 1.8`, `eye_height_m 1.6`,
  `crouch_height_m 1.2`, `max_step_up_m 0.5`, `walk_speed_mps 4.0` (`:5-12`)
- `nav_bake`: `agent_radius_m 0.4`, `agent_max_climb_m 0.15`,
  `agent_max_slope_deg 55.0`, `cell_size_m 0.1`, `cell_height_m 0.15` (`:19-28`)
- `clearances`: `min_door_width_m 1.25`, `min_corridor_width_m 1.1`,
  `min_headroom_m 2.0`, `unassisted_step_max_m 0.1025` (`:30-37`)
- `review.gameplay_camera_eye_m 1.6` (`:47`)

`agent_contract.py:6-8` states the degradation rule: "every consumer keeps a
hardcoded fallback equal to the ratified values, so a missing file degrades
gracefully instead of failing the pipeline."

**None of `combat_audit.py`, `sightlines.py`, `tactical.py` or `pvp_heist.py`
imports `agent_contract`.** `lot/site_cover.py` carries a copy
(`_NAV_BAKE_FALLBACK`, `:74-78`) and explicitly names it as such.

### 2.7 lot/site_cover.py — derived numbers with stated derivations

| constant | value | line | derivation |
|---|---|---|---|
| `EYE_HEIGHT` | 1.4 m | `:52` | read off `LT_BotPlayerController` (`body.global_position + UP*1.4`) |
| `CHEST_HEIGHT` | 1.0 m | `:53` | `LT_LineOfSightTester.CHEST_OFFSET = UP*1.0` |
| `MIN_COVER_HEIGHT` | **1.2 m** | `:59` | `(EYE + CHEST)/2` — where outgoing and incoming lines cross |
| `COVER_HEIGHT` | 2.0 m | `:66` | deliberately above the crossing height so the feasible interval is wide |
| `COVER_SIZE` | 3.0 m | `:72` | "a 3 m block in a 12 m street leaves better than three metres of navmesh on each side" at 0.4 m agent radius |
| `min_passable_gap()` | **1.2 m** | `:81-105` | `2*ceil(radius/cell)*cell + 2*cell` = `2*ceil(0.4/0.15)*0.15 + 0.3`; the agent contract's own door derivation applied to street furniture |
| `building_clearance()` | 1.2 + size/2 = **2.7 m** | `:108-119` | replaced a flat 2.0 measured to the centre; seed 5118 "went from zero stuck events to one player and one enemy stuck in all 25 runs" |
| `MARKER_CLEARANCE` | 3.0 m | `:129` | "A crate on a spawn is a spawn inside a solid" |
| `COVER_SEPARATION` | 6.0 m | `:134` | "Two crates in contact are one wall" |
| `APPROACH_BIAS` | 0.35 | `:141` | a third of the way from the crew's end |
| `SEARCH_STEP` | 0.02 m | `:143` | line-walk resolution |
| `GAP_TOLERANCE` | 1e-6 | `:350` | so an exactly-passable lane is not reported as a pinch |
| `PERIMETER_THICKNESS` | 0.3 m | `:376` | mirrors `lot.WALL_THICK` |
| `ROUTE_SAMPLE_SPACING` | 15.0 m | `:518` | "The crew moves at 4.5 m/s, so 15 m is about three seconds of walking" |
| `ROUTE_METRES_PER_PIECE` | 25.0 m | `:523` | budget scales with route length, "or it is a constant pretending to be a rule" |
| `limit` (marker pass) | 12 pieces | `:588` | flat allowance for the marker pass |

`break_interval(height)` (`:229-246`) returns `None` when
`height < MIN_COVER_HEIGHT`; otherwise `t ∈ [max(0,(EYE-h)/drop),
min(1,(h-CHEST)/drop)]` with `drop = EYE - CHEST = 0.4`.

`opening_range` comes from the caller; the value in use is
`lot/site_spawns.py:84`: **`OPENING_RANGE = 45.0`** m ("the crew's reach and not
the enemy's -- the crew sees ten metres further and shoots first, so the enemy's
35 m answers the wrong question", `:300-302`). Related:
`MIN_STANDOFF = 8.0` (`:49`), `CREW_SPEED = 4.5` (`:92`),
`REACTION_SECONDS = 1.0` (`:107`),
`OPENING_CLEARANCE = CREW_SPEED * REACTION_SECONDS = 4.5` m (`:111`).
The fair-opening test is `dist >= 45.0 + 4.5` or occluded (`:288-307`).

### 2.8 lot/site_audit.py — site grammar constants (all hardcoded, `:46-52`)

| constant | value | rule |
|---|---|---|
| `LEG_COVER_RADIUS` | 6.0 m | corridor half-width when counting cover on a leg |
| `LEG_BARE_MIN_LEN` | 20.0 m | legs shorter than this are exempt from S_BARE_LEG |
| `ANCHOR_RADIUS` | 8.0 m | backstop search radius around spawn / extraction |
| `BACKTRACK_ANGLE` | 35.0° | "tighter than this = same bearing" |
| `BACKTRACK_NEAR` | 18.0 m | spawn and extraction "basically co-located" |
| `RESPONDER_ARC` | 150.0° | responder spread `< 360 - 150 = 210°` flags |
| `CAMP_RADIUS` | 12.0 m | responder spawn nearer than this to an anchor = camping |
| horde arc | 120.0° | `spread < 120` → MED `S_HORDE_ARC` (`:264-267`) |
| horde count | 3 | `< 3` horde spawns → INFO `S_FEW_HORDE` (`:254-258`) |
| building box | r = 8.0 m | conservative footprint proxy for backstop tests (`:91-98`) |

### 2.9 lot/site_tactical.py

- `DEFAULT_MIN_SPAWN_SEPARATION = 25.0` m (`:258`), overridable per project via
  `site_spec["pvp"]["min_spawn_separation"]` — **raises** `SiteTacticalError`
  when violated: "attackers would start on top of the defense" (`:309-313`).
- `assault` mode gate: `_distinct_routes_to(obj, spawn) >= 2` (`:190-194`).
- `pvp_heist` mode gate: spawn→objective and objective→extraction routes must
  exist, `>= 2` distinct attacker approaches, and at least one
  `attacker_spawn`/`crew_spawn` site marker (`:217-244`).
- `gate_merged` also requires a defender spawn somewhere in the merged site and
  a "protected hold" — defenders in the objective building, or in a building
  that reaches it without passing through the attacker staging building
  (`:276-338`).

### 2.10 probe_fights.py

Reads gate constants from `zfight_gate` rather than defining its own:
`TOL`, `AREA_MIN`, `PEN_MIN`, `OCCLUDE_MARGIN`, printed at `:104-105`.
Classifies each overlap by shape only (`_shape`, `:42-59`): `duplicate`
(flush on all 3 axes), `contained`, `crossing` (2 axes), `corner` (1 axis),
`partial`. Writes nothing (`:30`).

---

## 3. MEASURED BUT ADVISORY

### 3.1 The whole of combat_audit.py

`combat_audit.py` is **not invoked by `check.py` or `validate.py`.**
`check.py:33-71` runs pytest, `validate.py --all`, `audit_specs.py`,
`layout_lint.py`, `stair_regression.py --quick`, `nav_gate.py --all`,
`catalog.py --check` — and nothing else. `validate.py` calls `tactical`,
`guards`, `enterability`, `navigability`, ladder review and (mode-gated)
`pvp_heist`, but never `combat_audit` or `sightlines`.

Consequence: every finding in combat_audit — including the six labelled
**HIGH** (`NO_LOOPS`, `DEAD_END` on an objective, `ONE_FACE`, `OBJ_ONE_DOOR`,
`AXIS_SWAP`, `SIGHT_DEAD`) — is advisory in practice. `main()` prints
`"== {n} audited: {high} HIGH, {med} MED =="` and exits 0 (`:979-988`).
The severity vocabulary is HIGH / MED / INFO, defined at `:35-36` as
"HIGH structural combat problems; MED costs fun but playable; INFO context".

The one mechanism that changes a severity is author acceptance, which only ever
*downgrades*: accepted non-INFO findings become INFO with the reason appended
(`:883-901`).

### 3.2 sightlines.py — advisory by explicit design

`sightlines.py:20-22`: "This is INTEL, never a gate: it never fails a build...
It is a GUIDE to authoring better buildings, not a pass/fail."
`check()` returns `(True, lines)` unconditionally (`:343-345`).

Advisory measures with no threshold at all: `death_lane_m`, `exposed_run_m`,
`weak_cover`, `n_cover`. Only `mismatch` and the report-level "FUNNEL" label
(`:329`) carry any judgement, and `mismatch` is the only one combat_audit
consumes (as **INFO** `SIGHT_INTENT`, `:867-870`).

The SVG overlay (`:349-393`) is pure communication: death lane drawn in `#e11`
dashed, exposed run in `#f90` at 45% opacity, weak cover circled in red.

### 3.3 tactical.py — the intel/judgement split, stated three times

Route counts and chokepoints are computed, put in the scorecard, and never
compared to a threshold. `tactical.py:476-480`: "intel for the gameplay
engineer, NOT judgments -- the tool makes models, not gameplay... we report it,
we don't flag it. Only reachability (above) is a hard model-integrity gate."
Same at `:629-631` (heist) and `:758-762` (survival).

Scorecard fields that are pure intel: `min_routes_to_objective`,
`single_route_objectives`, `chokepoints`, `run_hops`, `run_routes`,
`run_chokepoints`, `phases`, `loot_value`, `loot_bags`.

Advisory word used: **warning** (`TACTICAL-WARN` in `validate.py:127`).
Traversal steepness (44°/38°) is warning-only despite the 44° message saying
"the ramp collider won't be climbable" — i.e. a claim of unplayability that does
not block.

Also advisory by accident: `validate.py:135-136` swallows any exception from
`tactical.analyze` into `print("TACTICAL: analysis skipped")` and **continues**,
where the pvp_heist block at `:243-245` returns False on the same failure. The
"a gate that cannot run is not a gate that passed" principle is applied to
pvp_heist and to combat_audit's sightline block, but not to tactical itself.

### 3.4 lot/site_audit.py — report-only

`site_audit.py:30-31`: "Report-only, like combat_audit". Severity vocabulary is
**HIGH / MED / INFO**, and the counts dict is initialised with a `HIGH` slot
(`:283`) — but **no finding in the file is ever emitted at HIGH**. The seven
MED codes are `S_BACKTRACK`, `S_RESPONDER_ARC`, `S_RESPONDER_CAMP`,
`S_NAKED_ANCHOR`, `S_BARE_LEG`, `S_HORDE_ARC`, `S_ONE_APPROACH`; the three INFO
codes are `S_NO_RESPONDERS`, `S_STREET_CROSS`, `S_FEW_HORDE`.

The clean message repeats the epistemic caveat (`:299-300`):
"clean -- structural estimate, not a measure of fun; walk it".

The route-diversity check is wrapped in `except Exception: pass` (`:270-281`) —
the one place in this area where a silent failure survives.

### 3.5 lot/site_cover.py — soft gate: changes the build instead of refusing it

`site_cover.py:12-16`: "a firefight evaluator's finding is a *soft* gate here:
it never refuses a build, it changes what the build contains."
`site_cover.py:733-736`: "All advisory. A site with an open sightline is a site
Laser Tag will play and mark down, which is a design signal and not a build
failure."

Severity vocabulary here is different from every other module in this area —
**minor / moderate / major** (a Level Factory finding schema), with a
`category` field:

| code | severity | category | line |
|---|---|---|---|
| `LOT_COVER_PLACED` | minor | cover | `:744-756` |
| `LOT_SIGHTLINE_UNBREAKABLE` | **moderate** | cover | `:757-772` |
| `LOT_COVER_PINCH` | **moderate** | navigation | `:773-789` |
| `LOT_ROUTE_COVER_PLACED` | minor | cover | `:790-803` |
| `LOT_ROUTE_EXPOSED` | **moderate** | cover | `:804-820` |
| `LOT_SIGHTLINE_OPEN` | minor | cover | `:821-833` |

Note the asymmetry the module argues for at `:738-741`: an *open* sightline is
minor (the budget was spent on worse ones); an *unbreakable* one is moderate,
"because that is a request for a building and no amount of street furniture will
answer it."

### 3.6 lot/site_tactical.py — the split

`analyze()` is "Pure analysis, never raises" (`:113`) — connectivity, isolated
buildings, `spawn_to_objective_dist`, `objective_approaches`, attacker/defender
site marker counts, plus a `warnings` list.
`gate()` and `gate_merged()` **raise** `SiteTacticalError` — but only when a
site `mode` is declared: "No mode => no gates (pure intel)" (`:162-167`).

### 3.7 probe_fights.py — diagnostic only

"Reads a .glb and prints. Writes nothing." (`:30`). It emits no severities and
no findings; it exists to make an existing gate's output *interpretable*. Its
one judgement-adjacent output is the outward-cover column, deliberately printed
"next to the gate's verdict rather than instead of it" (`:22-24`).

---

## 4. CONSPICUOUSLY ABSENT

Each item below is grounded in a comment in this area that asserts the thing
matters, plus the absence of any code that measures it.

### 4.1 Flanking is the headline value and is never measured as geometry

The word carries the file's thesis — `combat_audit.py:10` "players can never
flank", `:18` "no exterior flank", `:750-752` "opposite-face entries create the
strongest flank geometry" — yet nothing computes an approach *bearing* or
*angle* inside a building. What exists is:
- a **face-set** test (`_entry_faces`, `:188-194`; ONE_FACE / ADJACENT_FACES),
- a **room-count** proxy explicitly labelled as such
  (`tactical.py:287` "a proxy for 'flanking options'"),
- and in PvP a **boolean**: `len(faces) >= 2 or has_ladder or len(stairs) > 1`
  (`pvp_heist.py:336-348`).

`ADJACENT_FACES` knows that opposite faces beat adjacent ones, but nothing
downstream ranks or scores that; two routes arriving at an objective from the
same 10° of arc through different rooms count as two flanks.

The bearing/arc mathematics **exists in this codebase** — `site_audit.py:126-133`
(`_bearing`, `_arc_between`) and its `RESPONDER_ARC = 150°` / horde `120°`
spread checks — and is never lifted to the building layer, despite
`site_tactical.py:6-11` framing the two layers as the same two ideas at two
scales.

### 4.2 Cover is counted, never positioned

`_cover_in_room` (`combat_audit.py:238-255`) returns an integer, and `KILLBOX`
tests only `== 0` (`:808`). A single 0.6 m crate in one corner clears a 200 m²
room. The comment itself asks for more than the code checks:
`:812` "Two or three 0.9-1.2 m volumes fix it" — the count "two or three" is in
the advice string and not in the predicate.

Nothing measures cover **spacing** (can you bound between pieces?), cover
**distribution** (are all pieces on one side?), or cover **orientation**
relative to the threat. The same file's own CQB pack proves the geometry is
available: `_threshold_visibility` already ray-casts against volumes.

The gap is stark against `site_cover.py`, which does all of this at site scale —
`COVER_SEPARATION = 6.0` because "two crates in contact are one wall" (`:131-134`),
`APPROACH_BIAS = 0.35` so cover sits on the crew's approach (`:136-141`), and
"Cover the crew has to walk around is an obstacle; cover it can walk behind is
cover" (`:686-687`). None of that reasoning is applied indoors.

### 4.3 "What counts as cover" is three different numbers, none shared

- `combat_audit.COVER_MIN_H = 0.6` ("waist high", `:63`)
- `sightlines.SIGHT_BLOCK_H = 1.6` (blocks *standing* sight, `:44`)
- `combat_audit._threshold_visibility` blockers: `size_z >= 0.9` (`:357`)
- `site_cover.MIN_COVER_HEIGHT = 1.2`, **derived** from the eye/chest crossing (`:59`)

Only the last is derived, and its derivation argument — "half a broken sightline
is not half a fix" (`site_cover.py:26-33`) — directly contradicts the 0.6 m and
0.9 m thresholds used indoors, where a 0.6 m volume counts as cover against an
eye at 1.6 m. Nothing reconciles them and nothing tests for drift.

### 4.4 Eye height disagrees across the area and nothing checks it

`agent_contract.json:8` `eye_height_m: 1.6`; `:47` `gameplay_camera_eye_m: 1.6`;
`sightlines.EYE = 1.6` (`:43`) — but hardcoded, since **`sightlines.py` never
imports `agent_contract`** (nor do `combat_audit.py`, `tactical.py`,
`pvp_heist.py`). Meanwhile `site_cover.EYE_HEIGHT = 1.4` / `CHEST_HEIGHT = 1.0`
(`:52-53`), sourced from the Laser Tag scripts.

`site_cover.py:48-51` is candid that it cannot verify its own numbers ("Lot
cannot read the Laser Tag checkout, so it carries the numbers and names where
they came from. Level Factory's `packages.validation.lasertag_contract` reads
the real files and reports drift against what is written here") — but there is
no equivalent drift check for the *building* layer, and no reconciliation
between 1.6 and 1.4. `agent_contract.json:3` claims to be "THE single source of
truth"; for combat geometry it is not consulted.

Similarly `tactical.MIN_OPENING_WIDTH = 0.8` m gates below the contract's own
`min_door_width_m = 1.25` and `min_corridor_width_m = 1.1`, without reference to
either.

### 4.5 The death lane is computed and thrown away

`sightlines.py:11-12` calls it "the angle that dominates every fight near it" —
the strongest claim about threat in the module — and `death_lane_m` has **no
threshold anywhere**. It is bucketed for the printed report (`:322-324`) and
that is all. `combat_audit`'s consumption of `sightlines.analyze` reads only
`rm["mismatch"]` (`:863-870`) and discards `death_lane_m`, `exposed_run_m`,
`weak_cover`, `n_cover` and `objective_entries` entirely.

So `objective_entries` — described as "1 = a funnel into the holdable point"
(`:262-263`) and printed with "<- FUNNEL (single entry)" (`:329`) — is computed
twice by two modules and never turned into a finding by either. (combat_audit's
`OBJ_ONE_DOOR` uses its own `_openings_into`, not this.)

### 4.6 The "exposed run" is measured along a straight line, not along the route

`_exposed_run` (`sightlines.py:237-258`) marches the straight segment from an
`attacker_spawn` marker to an `objective` marker at 0.5 m steps — **through
walls**, ignoring the room graph `tactical.build_graph` produces in the same
package. The header calls it "the longest stretch of the spawn->objective
approach" (`:12-13`), but the approach the players actually walk is never
sampled.

This is exactly the defect `site_cover.py` diagnosed and fixed at site scale,
with a measurement to prove it (`:558-565`): "Measured on
`category5_baie_dore_001` seed 5017: the crew crossed 74 m from spawn to
objective with all four pieces of cover clustered at the far end... Every marker
pair was answered and the approach was still bare, because no marker pair was
ever on it." No `route_samples` / `route_sightlines` equivalent exists indoors.

### 4.7 No cross-storey line of sight, despite verticality being a stated lever

`sightlines.py:6-7` casts rays "in 2D at eye height"; `analyze` loops
storey-by-storey (`:310-311`); occluders are gathered per storey (`:67-106`).
Nothing can express a mezzanine overlooking a lobby, an atrium, or a stairwell
sightline — the classic FPS height advantage.

The intent that this matters is on record: `combat_audit.py:21-22` "Two+ links
make it a level"; `:794-795` "A second link (ladder, second stair, roof hatch)
turns it into a level"; `pvp_heist.py:337-344` accepts a vertical route as the
*sole* flanking opportunity. And the geometry exists —
`tactical.py:188-194` handles `floor_hole` and `hatch` vertical links. But
`_vertical_links` (`combat_audit.py:258-273`) only **counts** connections; no
check asks whether the upper floor can *shoot down into* the lower one, which is
what makes a vertical link a flank rather than a corridor.

### 4.8 CQB threshold analysis runs on almost no rooms

`_pack_cqb` restricts `hot` to objective rooms plus `role == "fortifiable"`
(`combat_audit.py:534-536`). The header sells threshold visibility as *the*
Ready or Not number (`:346-349`) and the feed-type reasoning as a general truth
about entries (`:541-543`), but `C_NO_PIE`, `C_NAKED_ROOM` and `C_BLIND_ROOM`
never fire on an ordinary combat room. Only the feed **census**
(`C_FEED_MONOTONE`, `:586-603`) walks every room, and it is INFO.

### 4.9 AI/threat placement is counted, never located

Inside a building, every enemy-side check is a marker **count**:
- `H_NO_STEALTH` — `cams == 0 and pats == 0` (`combat_audit.py:520-528`)
- `F_FEW_HORDE_SPAWNS` — `hs < 3` (`:671-677`), message asserts "director has
  few ingress choices"
- `tactical.py:711-714` — "only {n} horde_spawn marker(s); survival runs usually
  want spawns spread along the route"

That last comment says **spread**, and nothing measures spread. Three
`horde_spawn` markers in the same room satisfy both checks. `site_audit.py`
measures exactly this at site scale (`S_HORDE_ARC`, spread `< 120°`, `:259-267`;
`S_RESPONDER_ARC`, `:182-191`). Nothing checks whether a `patrol_point` observes
the approach, whether a `camera_socket` covers anything, or whether any AI
position has line of sight to the objective — even though `sightlines._clear`
would make all three cheap.

### 4.10 No opposing-spawn separation *distance* indoors

`pvp_heist.py` gates on spawn **line of sight** (`PVP-SPAWN-LOS`, `:402-409`)
but never on spawn **distance**. The site layer has the number and the argument:
`site_tactical.DEFAULT_MIN_SPAWN_SEPARATION = 25.0` m, "attackers would start on
top of the defense" (`:256-258`, `:309-313`). Two spawns 3 m apart on opposite
sides of one partition pass every `pvp_heist` check.

Likewise, nothing indoors carries a reaction-time budget. `site_spawns.py:96-107`
argues at length that "a distance *equal* to the acquisition threshold is not a
standoff, it is the threshold, and it starts the fight on frame one", and derives
`OPENING_CLEARANCE = CREW_SPEED * REACTION_SECONDS`. The building layer's
`CLOSE_M = 8.0` / `LONG_M = 20.0` (`sightlines.py:45-46`) are bare constants with
no comment on where they came from and no relation to weapon reach, movement
speed (`agent_contract` has `walk_speed_mps: 4.0`) or time-to-contact.

### 4.11 Weak cover is judged only from attacker spawns, and silently not at all otherwise

`sightlines.py:222-229`: `weak = [...]` only populates `if spawns and seen` —
where `spawns = _markers(spec, story, "attacker_spawn")`. A spec with no
`attacker_spawn` marker on a storey produces an **empty** `weak_cover` list,
indistinguishable from "all cover is good". Given `tactical.py:530-532` only
*warns* when objectives exist without an `attacker_spawn`, this is a reachable
state. It is the same silence-vs-nothing-found failure mode the area elsewhere
takes seriously (`combat_audit.py:872` "Silence and 'nothing found' must not
look the same") — applied here to a metric, not an exception.

The docstring also says "clear line of sight **from the attack direction**"
(`:14-15`), but the computed quantity is LOS from a spawn *point*; direction is
never used, and cover is never evaluated against the defender's side.

### 4.12 Player count is load-bearing and never a parameter

"4-player PvE co-op" (`:5`), "four capsules + enemies do not fit" (`:26`, `:805`),
"passes two agents" (`:53`), "lets the squad enter as a unit" (`:769`). The
number 4 sets `CRAMP_MIN_DIM`, `WIDE_DOOR` and the killbox area implicitly, and
appears nowhere as a constant, a spec field, or a contract entry —
`agent_contract.json` describes one body and no team.

### 4.13 Nothing connects lighting or visual legibility to combat readability

The only "readability" measure in this area is `probe_fights.py`, which is about
z-fighting between solids. `combat_audit`'s cover model counts volumes but never
asks whether the room is lit, whether cover is visually distinguishable, or
whether a threshold is readable on approach — despite `C_BLIND_ROOM`'s advice
("Open the first slice from at least one threshold to ~50-90%", `:583-584`)
being a claim about what a player can *see*. `deli_counter/lights.py` exists and
is never consulted by any module in this area.

### 4.14 site_audit declares a HIGH severity it never uses

`site_audit.py:283` initialises `counts = {"HIGH": 0, "MED": 0, "INFO": 0}` and
`:30-31` advertises "severities HIGH / MED / INFO", but every `F(...)` call in
the file emits `MED` or `INFO`. There is no site-level condition the module
considers a structural combat problem — including a naked anchor, which its own
docstring calls "a shooting-gallery start/finish" (`:20-22`).
