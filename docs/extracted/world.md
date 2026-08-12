# World Feel — visual density, materials, lighting, props, wear, readability

Recovered from `zoo/`, `patina/`, `pixelcoat/`, `lux/` and the named `deli_counter/`
modules. Everything below is quoted or measured from the repos; nothing is invented.

Paths are relative to `C:\Projects\gabagool_studios\gabagool_factory`.

**Provenance note.** Files were staged read-only via `device_stage_files` into
`/mnt/user-data/uploads/gabagool_factory/…`; line numbers are of the staged copies,
which are byte-identical to the device files. `deli_counter/themes/` contains exactly
one entry: `themes/gasstation/wall_gasstation_01.glb` (a single 3.1 KB GLB — there is
no theme *data*, only one sample module).

---

## 1. ASSERTED DESIGN INTENT

*What the pipeline says a real-feeling place is. Verbatim, cited.*

### 1.1 The governing statement — what "alive" means

> "A living environment is not one that contains the most objects. It is one
> where architecture, props, textures, light, wear, sound and movement all
> suggest that the space has a purpose, has been used, and is changing over
> time."
> — `patina/docs/DRESSING_CHECKLIST.md:453-456` (Final principle)

> "The goal is spaces that feel functional, inhabited and visually distinctive
> without becoming cluttered or difficult to read."
> — `patina/docs/DRESSING_CHECKLIST.md:11-12`

> "…richer because details relate to each other, not because every surface is
> full."
> — `patina/docs/DRESSING_CHECKLIST.md:431-432`

> "**Empty space is an intentional design tool.**"
> — `patina/docs/DRESSING_CHECKLIST.md:332`

> "**Quiet zone** — at least one area intentionally restrained: a broad wall,
> open floor, dark upper space, fogged background, empty structural bay. Quiet
> zones are what make the dressed areas work."
> — `patina/docs/DRESSING_CHECKLIST.md:124-126`

### 1.2 Architecture first — dressing cannot rescue a bad shell

> "**Do not use props to hide weak architecture.** Fix the shell first."
> — `patina/docs/DRESSING_CHECKLIST.md:94`

> "Before adding small props, confirm the room works on architecture alone:
> readable silhouette · visible entrance and exit · understandable floor levels ·
> clearly located stairs and ramps · a dominant axis · major shapes readable at
> thumbnail size · clean backgrounds behind important gameplay positions ·
> areas of negative space · no dependence on clutter to feel complete."
> — `patina/docs/DRESSING_CHECKLIST.md:88-92`

> "Lock the level first. Dress it second. Never break collision."
> — `patina/README.md:39-40`

### 1.3 What a player reads in three seconds

> "**Intended player read** — what they understand within three seconds.
> *"This is a damaged repair bay. The suspended vehicle is the landmark. The
> illuminated door behind it is the route forward."*"
> — `patina/docs/DRESSING_CHECKLIST.md:62-64`

> "**Room name** — a functional name. `Vehicle Maintenance Bay`, `Security
> Checkpoint`, `Cold Storage`… Never `Room 04`, `Large Room`, `Hallway B`."
> — `patina/docs/DRESSING_CHECKLIST.md:36-40`

> "**Primary visual idea** — one dominant graphic concept. *A large vehicle
> suspended over a maintenance pit. A glowing generator dividing the room
> vertically. Repeating freezer doors making a horizontal rhythm. A broken
> ceiling exposing rain and city light. One red emergency light punctuating an
> otherwise dark room.*"
> — `patina/docs/DRESSING_CHECKLIST.md:53-58`

> "**Primary landmark** — the object or feature the player should remember."
> — `patina/docs/DRESSING_CHECKLIST.md:60`

### 1.4 Landmarks as navigation-by-eye

> "Landmarks are orientation anchors: they let a crew call "vault", "lobby",
> "extraction" and read the space at a glance instead of burning attention on
> navigation (Foreman: landmarks first; thesis 6.1.6: distinct callout areas
> stop people calling the wrong room). The marker is just the anchor + a label
> -- the art team makes it visually distinct."
> — `deli_counter/level_design.py:200-206`

> "  * Foreman   -- a level is ambiguity management; SIGHTLINES are the biggest
>                  lever, every sightline needs a risk/reward, LANDMARKS go in
>                  first so players spend attention on opponents, not navigation…
>   * Epic (Fortnite) -- aim for ~3-5 quickly-recognizable POINTS OF ENGAGEMENT
>                  per space (cover / window / ledge), and distinct CALLOUT
>                  landmarks you can read from a distance.
>   * SMU mid-area thesis -- DON'T over-cover (it destroys enemy-position
>                  readability), keep callout areas visually distinct…"
> — `deli_counter/level_design.py:12-23`

> "Applies validated FPS level-design principles to a finished preset spec so
> buildings come out *better by construction*, not merely measurable after the
> fact."
> — `deli_counter/level_design.py:4-6`

### 1.5 Route legibility — routes are announced by multiple signals

> "Important routes are recognizable through multiple signals: structural frame,
> floor transition, light, material change, sign, colour accent, clear negative
> space, prop orientation, repeated lines leading toward the opening.
>
> **Never place bright decorative clusters beside false routes.**"
> — `patina/docs/DRESSING_CHECKLIST.md:301-307`

### 1.6 What lighting is FOR (beyond visibility)

> "Add lighting *after* the prop composition works. Every light performs a role:
> general visibility, navigation, landmark emphasis, functional explanation,
> mood, gameplay readability, faction identification, narrative state. **Remove
> lights with no role.**"
> — `patina/docs/DRESSING_CHECKLIST.md:216-221`

> "Pattern: broad environmental light · localized functional light · one
> controlled accent · darkness or lower contrast around unimportant areas."
> — `patina/docs/DRESSING_CHECKLIST.md:222-223`

> "Confirm: the brightest area supports gameplay or the landmark · decorative
> lights do not overpower objectives · common enemy backgrounds stay readable ·
> prop clusters feel grouped by light · lighting does not flatten material
> differences · the room varies between light and dark."
> — `patina/docs/DRESSING_CHECKLIST.md:225-228`

**Light must have a physical source:**

> "Light in DELCO comes from the sun or from physical fixtures — never from
> nowhere."
> — `zoo/README.md:121-122` and `zoo/zoo_keeper/core/fixtures.py:3-4`

> "…it turns the SAME manifest into fixture *placements* — the visible hardware
> (troffer housings, streetlight poles) the light appears to come from — so the
> GLB Zoo bakes agrees exactly with the lamps Lux spawns."
> — `zoo/zoo_keeper/core/fixtures.py:6-9`

> "This repo owns the lighting pass over the composed scene, and the
> light-fixture gate (whose findings DO block: a floating light is broken
> output)."
> — `lux/README.md:10`

> "**A ceiling or wall fixture may not sit over a void.** Lights, vents, signs and
> cameras anchor to a SURFACE; a hole is not a surface. A fluorescent hanging in a
> stairwell opening reads as a bug on sight, and no amount of dressing quality
> survives it -- the player sees an object attached to nothing."
> — `patina/docs/DRESSING_CHECKLIST.md:518-521`

> "A FIXTURE MUST BE MOUNTED TO SOMETHING. A hole is not a surface, and a
> fluorescent hanging in a stairwell opening reads as a bug on sight…
> SPLIT, DO NOT DROP. A run that stops short of a stairwell and resumes past
> it is what a real ceiling does… because deleting the run removes light from
> the part of the room that still has a ceiling."
> — `deli_counter/lights.py:67-80`

> "Emitters sit PROUD of the wall, in free air, so the lamp Lux spawns is never
> inside the hardware Zoo bakes"
> — `deli_counter/lights.py:38-40`

> "`window` anchors are daylight through glass: no hardware, by design."
> — `zoo/README.md:150-151`; cf. `zoo/zoo_keeper/core/fixtures.py:51-52`
> ("anchor types that are light without hardware, by design")

**Lighting colour is physically grounded, for identity:**

> "Color-temperature helpers so light rigs use physically-grounded colors instead
> of eyeballed RGB. Kelvin values and the fluorescent green cast come from real
> light-source behavior (mercury-phosphor fluorescents sit ~3500-4100K with a
> slight green spike; high-pressure sodium ~2000K amber…)"
> — `lux/addons/lux/resources/lux_color_temp.gd:4-9`

> "Light-rig colors are grounded in real color temperatures via `LuxColorTemp`
> …so a scene's fixtures read as the real thing."
> — `lux/addons/lux/docs/getting_started.md:210-212`

**Lighting names moods, not settings:**

> "Per the design pillars, name presets as **scene moods**, not technical settings:
> *Wawa Parking Lot*, *Gas Station Fluorescent*, *Row Home Interior*,
> *Mission Goes Hot*. This keeps the dock readable for level designers."
> — `lux/addons/lux/docs/preset_authoring.md:35-37`

**Lighting is a gameplay-state channel:**

> "Building power on/off: kills every non-alarm rig light and the fixture
> glow bound by bind_fixture_emissives(). Alarm-group lights stay (battery
> strobes). The classic heist beat — cut the power, the block goes dark."
> — `lux/addons/lux/runtime/lux_root.gd:344-347`

> "Both on building power (`reacts_to_alarm: true`) — cutting the power kills the
> facade with the interiors, the classic heist beat."
> — `deli_counter/lights.py:259-261`

> "**Flat ambient.** `ambient_mode` (Sky / Flat Color / Disabled) lets a preset
> drop Godot's sky-sampled ambient for a single uniform fill — the honest way
> PS2-era scenes were lit (a key light plus flat ambient, no GI)."
> — `lux/addons/lux/docs/getting_started.md:204-207`

> "Skip spherical-harmonics baked GI (Halo 3's costly lightmaps) — PS2 had none,
> and Lux's banding + baked ambient is the correct era substitute. Chasing SH GI
> pulls *away* from the PS2 look toward a 360-era one."
> — `lux/addons/lux/lookdev/lookdev.md:79-81`

> "**Separation** — the real trick: keep the *subject* warm and bright while the
> *background* goes cool and hazy… Warm-bright-near vs cool-hazy-far is what
> makes the foreground pop, more than any single grade value."
> — `lux/addons/lux/lookdev/lookdev.md:74-77`

### 1.7 What dressing should EXPRESS — clusters, not scatter

> "A procedural system must not scatter props uniformly. It uses **semantic
> zones, cluster rules and budgets**."
> — `patina/docs/DRESSING_CHECKLIST.md:341-342`

> "Each cluster describes **one** activity or system.
> - **Anchor prop** — one dominant object…
> - **Supporting props** — two to four related objects…
> - **Activity evidence** — one detail showing recent use: open drawer,
>   pulled-out chair, active screen, loose tool, spilled liquid, missing
>   component, temporary cable, half-loaded container.
> - **Contact detail** — one grounding element: shadow, floor stain, wheel mark,
>   dust boundary, cable connection, wall attachment, anchor bolts.
> - **Accent** — no more than one…"
> — `patina/docs/DRESSING_CHECKLIST.md:128-142`

> "Validate: the props relate to one another · the cluster has one dominant
> silhouette · it does not block movement · it contains a size hierarchy · it has
> negative space around it · it contains no unrelated filler."
> — `patina/docs/DRESSING_CHECKLIST.md:144-146`

> "Every important dressed area contains three scales… A room filled with only
> small props feels noisy and lacks structure."
> — `patina/docs/DRESSING_CHECKLIST.md:150-158`

> "Remove props that repeat information already communicated · do not relate to
> nearby objects · block navigation · compete with gameplay · break the palette ·
> create excessive edge density · add collision without value · exist only
> because a surface looked empty."
> — `patina/docs/DRESSING_CHECKLIST.md:328-330`

**Dressing hierarchy — five tiers, tier 4/5 must never compete:**

> "1. **Gameplay-critical** … Strongest contrast, saturation, luminance, animation,
> silhouette separation.
> 2. **Landmark** … Memorable, but never overpowering active gameplay.
> 3. **Functional dressing** … These explain how the room operates.
> 4. **Narrative dressing** — repairs, damage, personal objects, activity residue,
> faction occupation, improvised changes.
> 5. **Background support** — quiet wall surfaces, structural repeats,
> noninteractive background props, distant machinery, low-contrast inserts.
>
> Tier 4 and Tier 5 must never compete with Tier 1."
> — `patina/docs/DRESSING_CHECKLIST.md:68-84`

**Rhythm, then interruption:**

> "```
> repeat · repeat · repeat · INTERRUPT · resume
> ```
> Interruptions: missing panel, different material, damage, bright insert, open
> bay, faction modification, active terminal, structural collapse. **Do not
> interrupt every repetition.**"
> — `patina/docs/DRESSING_CHECKLIST.md:165-172`

**Controlled asymmetry:**

> "One damaged side · uneven prop distribution · different equipment states · one
> active workstation · one blocked bay · one faction-modified corner · uneven
> lighting · different storage amounts. Never random asymmetry without a
> functional reason."
> — `patina/docs/DRESSING_CHECKLIST.md:319-323`

**Dress the whole vertical volume:**

> "**Floor** — drainage, floor markings, traffic wear… **Interaction** — controls,
> handles, signs, work surfaces… **Upper wall** — pipes, cable trays, ventilation…
> **Ceiling** — major supports, suspended equipment, maintenance access…
>
> Do not place detail in every zone. Use vertical distribution for depth."
> — `patina/docs/DRESSING_CHECKLIST.md:288-299`

**Dressing is forbidden where the player's body and eye go:**

> "THE RULE. Dressing never sits where the player will stand, shelter, or look.
> An objective is a place a body plants itself for several seconds; a cover
> marker is a place a body crouches and a silhouette gets read against whatever
> is behind it; a landmark is the thing the room is supposed to be remembered
> for; a spawn is where a body appears. None of those want decorative geometry
> in them."
> — `patina/patina/gameplay.py:3-8`

> "THE RULE. A door, window, garage or breach is a hole a player walks or shoots
> through. Nothing decorative may sit in one. The ``frame`` cover is the SOLE
> exemption, because surrounding an opening is the entire point of a frame."
> — `patina/patina/openings.py:3-5`

> "CONDUIT IS SHORTENED, NOT DROPPED. Every other cover is discarded when it
> collides: a curb that stops at a threshold and resumes past it is what a real
> curb does."
> — `patina/patina/openings.py:31-33`

**Never dressing in walkable space — and why the fix had to be subtractive:**

> "A module's collider is built from the same slab as its visual, so the wall's
> collision volume ends exactly at the wall's face, and anything proud of that
> face is by construction non-collision geometry sitting in space a body can
> occupy. That is the standing rule -- no dressing in walkable space -- broken by
> the shape of the solution, not by a placement mistake.
>
> It cannot be fixed by aiming the covers better. Pointing them into the
> building put 546 panel fields inside rooms; pointing them out put the same
> 546 into the gaps between buildings, which Lot makes into routes. Both are
> walkable. There is no third direction.
>
> So the relief is SUBTRACTIVE and lives inside the module."
> — `zoo/zoo_keeper/core/arch.py:315-327`

### 1.8 Silhouette protection (readability during play)

> "From every major combat position confirm: enemies visible · doors readable ·
> cover shapes clear · pickups not blending into debris · objectives not hidden ·
> hazards visible during effects · stairs and ladders cleanly outlined ·
> decorative elements not resembling interactive objects.
>
> Reduce background detail where silhouettes fail."
> — `patina/docs/DRESSING_CHECKLIST.md:309-316`

> "§11: *"Environment surfaces near combat spaces should avoid ... repeated panel
> lines ... Busy edge patterns behind enemies create visual camouflage."* Brick
> and tile are what walls and floors are made of, so the busiest materials we own
> are the ones with the largest screen area."
> — `pixelcoat/docs/CONTRAST_DIRECTION.md:75-79`

> "§5: *"The brightest white in the scene should normally belong to energy, an
> objective, a critical gameplay state."*"
> — `pixelcoat/docs/CONTRAST_DIRECTION.md:40-41`

> "…`ceiling_tile_delco` is in **every single theme**, which means every interior
> ceiling in every building is competing for the same luminance a muzzle
> flash needs. This is the finding with the most direct gameplay cost: it is
> §12 figure-ground, and it fires on interiors, where the combat is."
> — `pixelcoat/docs/CONTRAST_DIRECTION.md:56-59`

> "In a CQB map the doorway is the choke point, so it is the most reliable
> predictor of where a silhouette will be read"
> — `pixelcoat/docs/CONTRAST_DIRECTION.md:225-227`

### 1.9 How materials communicate FUNCTION

> "- **Quiet environment** — higher roughness, restrained saturation, broad value
>   regions, limited specular, minimal emissive.
> - **Functional props** — moderate roughness variation, clear material
>   boundaries, controlled highlights, small functional emissives, stronger local
>   contrast.
> - **Hero and faction props** — lower roughness, glossy or reflective inserts,
>   stronger saturation, distinct response, iridescence, animated emissive,
>   strong silhouette lighting.
>
> Do not give every prop a premium material response."
> — `patina/docs/DRESSING_CHECKLIST.md:191-200`

> "**Reserved gameplay colours** — protected for enemies, pickups, objectives,
> hazards, interactive objects, faction technology.
>
> Confirm: the most saturated element has a reason · decorative props do not
> borrow gameplay colours · accents appear in clusters, not everywhere · rooms
> use controlled accent variation · **the room reads in grayscale**."
> — `patina/docs/DRESSING_CHECKLIST.md:207-213`

> "The standard is a set of claims about the ENVIRONMENT layer specifically: it
> should be low-chroma, value-compressed, matte, quiet, and almost never
> emissive, so that the gameplay layer owns saturation, gloss, peak luminance and
> edge density. Every one of those is a property of a synthesized albedo /
> roughness map, so every one of them is measurable -- which means the standard
> can be enforced instead of remembered."
> — `pixelcoat/tools/art_standard_audit.py:4-9`

> "the first emissive material we ever ship should be signage, and it should be
> brighter than anything else in the environment and dimmer than anything in the
> gameplay layer. This reframes the open signage work: the target is not "make
> the signs prettier", it is "the sign is the only environmental thing allowed to
> glow, so it has to earn it.""
> — `pixelcoat/docs/CONTRAST_DIRECTION.md:233-237`

> "Neon signs, backlit panels (EXIT and friends), CRT/LCD screens, hazard stripes,
> and directional arrows — the placed, often-glowing art that makes an
> environment read as a *place* rather than a textured greybox."
> — `pixelcoat/core/signage.py:3-6`

> "Roughness is derived as exactly `1 - gloss`. Metallic is only ever produced by
> a preset rule (painted metal exposes steel where wear cuts through) — never
> guessed from luminance."
> — `pixelcoat/README.md:60-63`

> "Brightness is NOT assumed to mean physical height — each preset weights the
> bands itself"
> — `pixelcoat/core/material_response.py:11-12`

**Material variety must be intentional, not one skin for everything:**

> "Before this module, every emission site hard-coded ``style: 1`` -- so every
> building funnelled Pixelcoat's whole library through ONE skin. Now the style
> follows the MATERIAL the greybox already assigns to each surface (brick_ext vs
> drywall vs metal ...), so skin variety is intentional -- exteriors read as
> brick, interiors as drywall -- deterministic, and stable across rebuilds."
> — `deli_counter/skin_style.py:10-15`

> "Why kind-level, not species-level: every Zoo mesh already carries
> deterministic world-meter cube-projected UVs… A *tiling* pack therefore lands
> on every metal part of every species at uniform physical density with zero
> per-species work"
> — `zoo/zoo_keeper/core/skins.py:3-8`

> "Kinds without a pack stay flat vertex color — progressive art pass."
> — `zoo/README.md:70`

> "A pack is only *applied* when a Zoo species asks for that `material_kind`… so
> enabling a wall to be brick is a pure genome edit"
> — `pixelcoat/docs/MATERIAL_COVERAGE.md:66-69`

### 1.10 Cohesion comes from CONSTRAINT, not polish

> "The cohesion in Quake 2 wasn't per-texture polish — it was *constraint*… A
> **family** makes the palette the unit of reuse and *locks* every surface to it."
> — `patina/patina/families.py:3-9`

> "Cohesion becomes *literal*: after a lock, the entire tile set draws from N
> colours… And the family is the reusable unit **across areas** — point every
> shell at the same `family.json` and the whole game reads as one place, which is
> the actual source of Q2's cohesion"
> — `patina/README.md:271-276`

> "Zoo owns module geometry + a flat base style colour; Patina owns the rich
> nuance pass (family cohesion, banding, decals, PS1 posterize). When a build's
> slot manifest names a theme, Patina reconciles it to the matching family…so the
> two tools describe one world instead of fighting."
> — `patina/README.md:420-424`

> "Variation colours come from the reconciled family, so breaking repetition
> never breaks cohesion."
> — `patina/README.md:446-447`

### 1.11 Breaking modular repetition

> "the payoff is the repetition-breaking DC's docs call the #1 aesthetic lever.
> `--slot-variation` computes a deterministic per-slot brightness factor (seeded
> by `slot_id`)… so identical `wall_delco_01` copies stop reading as mechanically
> repeated"
> — `patina/README.md:438-444`

> "Real buildings rarely use one material top-to-bottom — a base course of brick,
> painted concrete in the middle, metal flashing at the cap. That "material
> variation / colour blocking" is the highest-ROI *no-geometry* art-pass move…
> it reads as a building instead of a box, and it costs *no geometry*"
> — `patina/README.md:335-340` / `patina/patina/banding.py:3-8`

> "Big flat walls read as one tone until something varies their *interior*…
> `--mottle` adds coherent world-space value noise (3 octaves, smooth so it's
> weathering not speckle) that breaks up the flats… This is the finishing texture
> pass: form was never the problem, flatness was."
> — `patina/README.md:526-536`

> "Adding this offset before projecting makes the projection continuous across
> covers that share a wall… Bloodborne's set-dressing writeup calls the
> underlying technique "mixing tileables with simple inserts" -- inserts only
> read as inserts when the tileable behind them is continuous."
> — `zoo/zoo_keeper/core/dressing.py:125-129`

> "Every panel then sampled the identical patch of concrete, and the facade read
> as a grid of stamped tiles. The seams a player sees are not the 3 cm gaps; they
> are the texture restarting in every cell."
> — `zoo/zoo_keeper/core/dressing.py:121-124`

> "Facade relief defaults. Overridable per style through the genome's params,
> which is where the VARIATION belongs -- one rhythm on every wall of every
> building is the failure mode this replaces, not a goal."
> — `zoo/zoo_keeper/core/arch.py:296-298`

> "the most ORDINARY patch, because a unique landmark repeated 8 times per meter
> reads instantly as tiling."
> — `pixelcoat/core/detail_texture.py:10-12`

### 1.12 How WEAR and AGE are reasoned about

> "Add wear based on cause. **Never randomly.**
> - **Foot traffic** — between doors, around workstations, near stairs, at queue
>   areas, beside frequently used machinery.
> - **Hand contact** — handles, around switches, railings, terminal edges,
>   cabinet doors.
> - **Vehicle contact** — bumper height, narrow turns, loading bays…
> - **Water** — streaks below leaks, pools at low points, corrosion at joints…
> - **Heat** — discoloration near exhausts, soot above vents, burn marks near
>   failures, faded paint around hot machinery."
> — `patina/docs/DRESSING_CHECKLIST.md:256-270`

> "Every major damage event answers: what caused it · from which direction · what
> material failed · where debris travelled · what was exposed · how occupants
> responded… **Avoid damage decals without supporting evidence.**"
> — `patina/docs/DRESSING_CHECKLIST.md:274-279`

> "Repairs should look **less integrated** than the original construction."
> — `patina/docs/DRESSING_CHECKLIST.md:285-286`

> "In chronological order — and only the layers the room's state supports.
> 1. **Original construction**… 2. **Normal use**… 3. **Long-term change**…
> 4. **Recent event** — fresh damage, open doors, active alarms, displaced props,
>    temporary barricades, unfinished work, abandoned equipment."
> — `patina/docs/DRESSING_CHECKLIST.md:242-254`

> "Nothing here is uniform noise slapped on top. Wear grows from height
> gradients on RAISED transitions; grime accumulates IN cavities; streaks
> run a decaying recurrence along a chosen direction; wetness darkens,
> glosses, and softens micro response only inside its own mask."
> — `pixelcoat/core/weathering.py:3-6`

> "wear favors raised transitions, never flats or recesses"
> — `pixelcoat/core/weathering.py:62-63`

> "**Textures** — small posterized RGBA stamps (stains, scuffs, streaks)…
> Algorithmic stand-ins… honest grime, not forged art."
> — `patina/patina/decals.py:5-9`

> "materials create the base look, decals create the lived-in feel"
> — `patina/patina/decals.py:3-4`

> "vertical banding… reads as a building instead of a box"; grime is a
> **height gradient**: "times a height grime gradient, darker toward each mesh's
> local floor (``GRIME 0.25`` over ``0.6 m``)."
> — `patina/patina/nuance.py:14-15`

**Wear is known-broken end-to-end (self-reported):**

> "``tools/vertex_variation.py`` measured a shipped dressing GLB and found COLOR_0
> uniformly 1.0 on every vertex of all 1884 covers -- zero spread between covers
> and zero spread inside one -- while the ``rockay`` style declares ``wear: 0.29``."
> — `zoo/tools/wear_probe.py:3-7`

> "Wear has to cross three boundaries to reach a file, and each fails silently"
> — `zoo/tools/wear_probe.py:12`

> "**Wear is not cause-driven.** §15 wants wear at contact points. Patina's
> weathering is procedural over the whole surface."
> — `patina/docs/DRESSING_CHECKLIST.md:578-579`

### 1.13 Depth / form — why flat multiplies are a mistake

> "Patina's nuance AO/grime darken *value* only — a flat multiply, which is
> exactly the "mix black into the shadow, smudge the in-between, get a grey dull
> result" mistake… Painters get depth from colour moves, not brightness moves"
> — `patina/patina/depth.py:3-6`

> "**Saturated shadow gradients** … the transition into shadow/cavity should
> *gain saturation* and shift a touch warm or cool, not just go darker. A blended
> midtone looks lifeless; a saturated one reads as form."
> — `patina/patina/depth.py:8-11`

> "**Atmospheric perspective** … surfaces that recede… drift toward a
> desaturated, cool, slightly lighter tint… This separates planes so a facade
> reads as depth rather than a flat wall."
> — `patina/patina/depth.py:12-16`

> "A PS1-era look has no real-time GI, so these cues are baked into vertex colour
> and tiles on purpose — a deliberate departure from a strict unlit PBR *albedo*."
> — `patina/README.md:516-518`

> "Directional **form** (soft cool-up/warm-down) | Zoo ambient (vertex) | The
> depth a surface has *before* light"
> — `patina/docs/LOOK_PIPELINE.md:45`

> "That tint is the one variation lever that costs no extra elements: it changes
> how a surface reads by face orientation rather than by adding geometry."
> — `zoo/zoo_keeper/core/dressing.py:189-191`

**The composition law — who owns which cue:**

> "The principle: **bake the cues that must live in the albedo/vertex data because
> nothing at runtime can derive them; defer the cues that depend on runtime light
> to Lux.**"
> — `patina/docs/LOOK_PIPELINE.md:31-33`

> "Everything is multiplicative and cumulative. That makes the division of labour
> a correctness issue, not just taste: bake a cue Lux also applies, and it
> double-counts or crosses."
> — `patina/docs/LOOK_PIPELINE.md:24-26`

> "a latent bug the Lux review surfaced: the saturation gain was *additive*,
> which on a **neutral grey** (Zoo's default concrete) invented a red hue from
> HSV's undefined-hue-at-zero. Made it **multiplicative** — it now amplifies the
> chroma already present and leaves neutrals neutral."
> — `patina/docs/LOOK_PIPELINE.md:64-67`

### 1.14 Texture-authored depth beats geometric depth

> "*"Would the detail alter the silhouette, collision, or shadow in a meaningful
> way? When the answer is no, it may be better represented in the texture."*"
> — `pixelcoat/docs/CONTRAST_DIRECTION.md:415-417`

> "**The 5 cm step fails the test outright.** It does not alter silhouette. It
> cannot alter collision — the collider comes from `slab`, never from `visual`…
> At 3 m eye height it casts no contact shadow worth the seven boxes it costs."
> — `pixelcoat/docs/CONTRAST_DIRECTION.md:439-443`

> "the recommendation upgrades from *tier the relief* to **stop paying for the
> 5 cm in geometry and repay the whole articulation in texture**. The bands are
> worth keeping; their depth is not."
> — `pixelcoat/docs/CONTRAST_DIRECTION.md:450-453`

> "A quiet field, a frame, one or two inserts, one accent. That is a
> **composition with internal placement**, and a tiling field generator cannot
> produce one no matter how good the generator gets. The missing subsystem is not
> a better field — it is a **panel composer**"
> — `pixelcoat/docs/CONTRAST_DIRECTION.md:340-345`

> "**22 of 51 grammars have all their value mass in a single contiguous run.**
> A continuous band of four adjacent value bins is a material field. It is not a
> bevel… This is why the buildings read as flat: the palette is disciplined, but
> the palette has no *depth vocabulary*."
> — `pixelcoat/docs/CONTRAST_DIRECTION.md:308-318`

> "the gaps between panels are where a sixth-gen facade gets its shadow lines"
> — `patina/patina/paneling.py:5-6`

> "0.03 -> 0.012: a panel field's proud depth IS its seam. Every cell has four
> edge faces, and across 1032 cells those edges draw a lattice on any
> sky-dominant ambient -- the "tiles" that kept reading as tiles after the UV fix"
> — `zoo/zoo_keeper/core/dressing.py:43-46`

> "Dressing detail is capped against the surface it sits on: on a 3.7 m storey
> base_course was 1/11 and pilaster 1/15, coarse enough to read as structure
> rather than trim. Both halved… the instinct that dressing was too chunky was
> right"
> — `zoo/zoo_keeper/core/dressing.py:30-34`

### 1.15 Texture-based dressing — shallow detail lives in the pixels

> "Use pixel art and low-resolution textures for shallow detail instead of
> geometry: panel divisions, painted bevels, rivets, vents, access hatches,
> grilles, fasteners, signs, labels, material transitions, shallow recesses,
> warning stripes, small lights, repair plates.
>
> Each texture contains a broad quiet field, a structural frame, one or two
> medium details, one optional accent, and controlled wear. Never fill the whole
> texture with equal contrast."
> — `patina/docs/DRESSING_CHECKLIST.md:175-186`

> "Pixel cluster check: pixels form intentional clusters · single-pixel noise is
> limited · shading uses a small value range · important edges read at distance ·
> material cues are exaggerated enough to read · painted depth does not conflict
> with the mesh."
> — `patina/docs/DRESSING_CHECKLIST.md:185-187`

> "Structure is what makes a surface read as a material instead of tinted noise,
> and per-cell colour jitter is what fakes the hand-set variety of a real texture
> set."
> — `patina/patina/patterns.py:7-9`

> "**Never fill the whole texture with equal contrast**" is the texture-level
> restatement of "Empty space is an intentional design tool."

### 1.16 Honesty about what a tool cannot do

> "It does **not** pretend to automate art. Turning a blockout into a
> production-final, hand-modeled, hand-textured building is irreducible creative
> labor. Patina automates the mechanical steps that bracket that labor…and marks
> the seams where a modeler or texture artist takes over."
> — `patina/README.md:22-26`

> "**Explicit non-promise:** Patina ships zero detailed building geometry. The
> blockout-plus look comes from *style*, not modeled detail."
> — `patina/docs/SEAMS.md:23-25`

> "**Governing principle (carried over, do not relitigate):** minimal /
> readability-first, never "beauty". Just enough to communicate the space."
> — `patina/patina/nuance.py:29-30`

> "the hard, automatable part isn't the mesh; it's *placement*… This is the
> intended **division of labour**: Patina decides *where*, downstream tools supply
> *what*."
> — `patina/README.md:369-390`

---

## 2. MEASURED, WITH NUMBERS

*Computed values and their thresholds. Every one blocks or reports.*

### 2.1 Polygon budget — `deli_counter/polybudget.py`

| Constant | Value | Line |
|---|---|---|
| `BOX_TRIS` | 12 (a plain box) | `:34` |
| `HOLE_TRIS` | 24 extra tris per boolean-cut opening (calibrated: `corner_deli` 30 openings + 1 slab hole ≈ 762 tris → ~24-25/cut) | `:35-38` |
| `ENV_TARGET_LO` / `ENV_TARGET_HI` | 50 / 500 tris per Environment/Module piece | `:41-42` |
| `ENV_CAP` | 1000 tris per piece (hard art-director ceiling) | `:43` |

Estimation model (`:21-29`): stair = `12 * n_steps`; ladder = `12 * (2 + n_rungs)`;
markers = 0 tris. Default step rise 0.18 m, `n_steps = max(6, min(40, H/rise))`
(`:99`); rung spacing 0.3 m (`:108`).

### 2.2 Coplanarity / z-fight gate — `deli_counter/zfight_gate.py`

| Constant | Value | Line |
|---|---|---|
| `TOL` | 0.0015 m same-plane tolerance | `:35` |
| `AREA_MIN` | 0.05 m² smallest shared face area worth flagging | `:36` |
| `PEN_MIN` | 0.0005 m minimum interpenetration on **every** axis | `:37` |
| `OCCLUDE_MARGIN` | 0.003 m solid cover needed on BOTH sides of a buried plane | `:38` |

A pair z-fights iff **all** of: real volume interpenetration > `PEN_MIN` on every
axis; a same-facing coplanar face pair within `TOL` (max-vs-max or min-vs-min);
shared area ≥ `AREA_MIN` (`:14-21`). Abutting faces (max-vs-min) are never flagged.
**Blocking**: "A composed package must ship with ZERO such pairs" (`:11-12`);
`main()` exits 1 on findings (`:284`); the LF compose driver fails the job.
Greybox-internal pairs and entombed pairs are intel only, never gated (`:259-264`).

### 2.3 Light anchor placement — `deli_counter/lights.py`

| Constant | Value | Line |
|---|---|---|
| `LIGHT_MANIFEST_VERSION` | `"1.1.0"` | `:12` |
| `_TARGET_SPACING` | 3.0 m between ceiling fixtures | `:19` |
| `_MAX_FIXTURES` | 5 — cap on a single room's ceiling row | `:20` |
| `_CEILING_GAP` | 0.1 m — hang fixtures this far below the ceiling PLANE | `:21` |
| `_WALL_PACK_OUT` / `_WALL_PACK_RISE` | 0.15 m proud of wall / 0.25 m above door head | `:41-42` |
| `_SIGN_OUT` / `_SIGN_RISE` | 0.2 m face plane proud / 0.35 m above door head | `:43-44` |
| `_SIGN_PAD` / `_SIGN_H` | sign width = door width + 0.8 m; height 0.6 m | `:45-46` |

Derived counts: one fluorescent **row** per interior room; `count =
max(1, min(5, round(length / 3.0)))` along the room's **longer** axis (`:59`);
one area light per window opening; one wall pack over every exterior door;
**exactly one** derived storefront sign — "above the widest door on the facade
with the most windows… a building with no exterior windows gets no derived sign"
(`:153-157`).

`cap_thick` is REQUIRED with no default: "a default of zero would silently
reproduce the defect it exists to fix, and this kit does not ship guards that pass
by omission" (`:200-204`). The defect it fixes was measured: on
`category5_baie_dore_001`, "all 28 fluorescent anchors sat at 3.90 / 7.90 / -0.10
-- 0.10 below the floor ABOVE, and so buried 0.20 m inside a 0.30 m slab"
(`:26-30`).

Void split measured: `art_probe_001` seed 5017, 1 of 20 fluorescents at
`(-10.50, 6.50, 3.20)` inside the `ceiling_manager_office` void spanning
`x −13.0..−9.0, y 4.2..9.3` (`:69-73`, restated `patina/docs/DRESSING_CHECKLIST.md:523-527`).

### 2.4 Lux light budgets — `lux/addons/lux/resources/lux_quality_profile.gd`

| Tier | `max_dynamic_lights` | `max_shadow_casters` | `shadow_max_distance` | post/glow/dither |
|---|---|---|---|---|
| High (0) | 24 | 8 | 100.0 | all on |
| Medium (1) | 16 | 8 | 45.0 | volumetric fog off |
| Low (2) | 8 | 0 | 45.0→100 default | post FX, glow, sun shadows off |
| Compatibility (3) | 6 | 0 | — | + dithering off |

`:18-20` defaults, `:23-49` tier table.

`lux_validator.gd` enforces:
- omni+spot count > `max_dynamic_lights` → WARN (`:60-69`)
- shadow casters > `max_shadow_casters` → WARN (`:70-80`)
- omni+spot+area > **128** → INFO ("the Forward+ default cluster budget is 512") (`:100-116`)
- `color_levels < 8` with per-pixel dither → INFO "muddy in motion" (`:191-206`)
- glow + dither on tier ≥ 2 → WARN (`:207-213`)

**The fixture co-location gate (blocking, ERROR severity)** — `lux_validator.gd:287-346`:
- tolerance **0.1 m** (default arg, `:295`)
- every `LuxEmit_*` marker must have a lamp within tolerance, else **"dark hardware"** (ERROR)
- every lamp under `LuxFixtureLights` must sit within tolerance of a marker, else **"floating light"** (ERROR)
- manifest-baked `LuxLights` are explicitly exempt ("window/area lamps legitimately sit far from any hardware", `:292-293`)

### 2.5 Colour temperature constants — `lux/addons/lux/resources/lux_color_temp.gd:13-20`

`SODIUM_VAPOR 2000K` · `INCANDESCENT 2700` · `HALOGEN 3000` · `WARM_FLUORESCENT 3000`
· `COOL_FLUORESCENT 4100` · `MERCURY_VAPOR 5000` · `DAYLIGHT 6500` · `OVERCAST 7000`.
Fluorescent green-cast nudge default `amount = 0.06`, and `cool_fluorescent()` uses
`0.07` (`:58-69`).

### 2.6 Lux light rig defaults — `lux/addons/lux/resources/lux_light_rig.gd:12-27`

`light_color (1.0, 0.96, 0.88)` · `energy 2.0` (0–16) · `light_range 12.0` (0.5–60)
· `shadows_enabled false` · `count 4` (1–32) · `spacing 6.0 m` · `mount_height 4.0 m`
· `flicker_amount 0.0` (0–1) · `flicker_speed 8.0`.
`LuxRole.LEVEL` profile: `band_count 3.0`, `band_softness 0.1`, `shade_min 0.2`,
`specular_strength 0.1` (`lux_role.gd:65-70`).

### 2.7 Preset-authoring numeric guidance — `lux/addons/lux/docs/preset_authoring.md:18-20`

Fog density 0.003–0.012 · dither strength 0.2–0.35 · `color_levels ≥ 20`.
CRT mask strength 0.15–0.25 (`getting_started.md:197-203`).
*Gas Station Fluorescent* ships `render_scale = 0.75` (`getting_started.md:86-91`).
*Delco Arcade*: exposure 1.15, glow threshold 1.25, saturation 1.22, contrast 1.1,
fog 0.006 (`patina/docs/LOOK_PIPELINE.md:108-112`).

### 2.8 Environment material budget — `pixelcoat/tools/art_standard_audit.py:55-89`

| Metric | Budget | Clause |
|---|---|---|
| `chroma_mean` (Oklab C) | **0.030** (recalibrated down from 0.060 on 2026-08-05) | §6 |
| `chroma_p95` | 0.120 | §6 tail |
| `value_range` (L p95−p5) | 0.500 | §5 |
| `crushed_frac` (L < 0.06) | 0.010 | §19 |
| `blown_frac` (L > 0.94) | 0.010 | §19 |
| `rough_mean_min` | 0.45 | §7 |
| `emissive_allowed` | **False** | §8 |

Tier scale multipliers (`:96-101`): `foundation 1.00` · `functional 1.25` ·
`identity 1.75` · `accent None` (exempt).
Tertiary kinds judged (`:104-107`): brick, concrete, drywall, plaster, ceiling_tile,
tile, carpet, wood, glass_facade, metal. Secondary: glass (`:110`).

**Neighbour-pair (adjacent-material) rules** — `:279-297`, calibrated on 387 pairs:
`PAIR_VALUE_STEP 0.12` · `PAIR_HF_DIFF 0.010` · `PAIR_CHROMA_DIFF 0.015` ·
`PAIR_HUE_DIFF 30.0°` · `HUE_FLOOR 0.004`. A pair need satisfy **only one** of
structure / chroma / hue to justify its value step.
Determinism tolerance `_TOLERANCE 0.002` (`:503`).

### 2.9 Measured library state — `pixelcoat/docs/CONTRAST_DIRECTION.md`

- Oklab chroma over 38 environment grammars: `min 0.006 p25 0.011 p50 0.023
  p75 0.049 p90 0.074 max 0.109` (`:18-20`). Worst: `metal_brass_casino` 0.109.
- **Zero grammars in the entire library emit** (`:29`).
- Blown-highlight fraction (L > .94): `subway_tile_white` **44.7%** (rough 0.13),
  `travertine_warm` 14.2%, `stucco_warm` 13.2%, `ceiling_tile_delco` 12.3%,
  `brick_painted_white` 7.0%, `vct_floor_beige` 5.2%, `tile_delco` 1.5% (`:44-51`).
  `crushed_frac` is **0.000 across the whole library** (`:53`).
- Edge-density proxy `hf`: `brick_glazed_green 0.178`, `terrazzo 0.145`,
  `concrete_delco 0.119`, `tile_delco 0.118`, `brick_delco 0.118`,
  `subway_tile_white 0.107`; distribution `p25 .038 p50 .051 p75 .074 p90 .118`
  (`:65-73`).
- Roughness offenders: `glass_facade_mirror_blue 0.08`, `glass_facade_bronze 0.10`,
  `glass_facade_spandrel_green 0.12`, `subway_tile_white 0.13`,
  `brick_glazed_green 0.20`, `marble_bank_floor 0.22` (`:84-89`).
- Value economy: unique colours per grammar `min 4 median 14 max 948`; occupied
  L-bins (>2% each) `min 1 median 4 max 10` (`:294-297`).
- Texel density: `meters_per_tile` 1.00→512 px/m (11 grammars), 1.50→341 (7),
  2.00→256 (22), 2.50→205 (4), 3.00→171 (6). **Spread 3.0×** (`:353-359`).
  Target 128 px/m; power-of-two derivation cuts spread to 1.67×, worst deviation
  1.33× (`:374-381`).
- `recipes/dress_cover.py` sets `texel = 1.2` → every dressing cover sits at 20%
  higher texel density than the wall behind it (`:404-407`).

### 2.10 Zoo facade relief — `zoo/zoo_keeper/core/arch.py:299-306`

```python
RELIEF = {"bay": 2.4, "pier": 0.14, "reveal": 0.05, "base": 0.45,
          "cap": 0.12, "min_field": 0.40}
```
- `bay` 2.4 m target pier-to-pier spacing
- `pier` 0.14 m full-depth strip between bays
- `reveal` 0.05 m recess **per face** — clamped to `d * 0.35` (`:352`)
- `base` 0.45 m plinth, clamped to `h * 0.35` (`:348`)
- `cap` 0.12 m cornice, clamped to `h * 0.15` (`:349`)
- `min_field` 0.40 m — "narrower than this and a bay is noise, not rhythm"

Degenerate (quiet) path at `:359-361`: if `fh <= _EPS` **or** `bw - pier < min_field`
**or** `reveal <= _EPS`, returns a single `("Panel", …)`. Measured: "56 relief parts
collapse to 8 plain panels, a 7× reduction, with collision untouched"
(`pixelcoat/docs/CONTRAST_DIRECTION.md:127-131`). Measured relief depth on a 4.8 m
module at d 0.35: Base/Pier/Cap d = 0.350, Field d = 0.250 → **one** relief depth in
the whole system, 5 cm (`CONTRAST_DIRECTION.md:426-436`).

Jamb clamp: `jamb = 0.12` default, clamped to `(w - 0.20)/2` for w > 0.24, else 0.02
(`arch.py:123-127`). Doorway header `min(0.22, h*0.40)` (`:136`).

### 2.11 Zoo dressing cover dimensions — `zoo/zoo_keeper/core/dressing.py:35-52`

| cover | proud (m) | cross (m) | span (m) |
|---|---|---|---|
| `edge_strip` | 0.06 | 0.10 | 2.0 |
| `base_course` | 0.04 | 0.18 | 2.0 |
| `curb` | 0.05 | 0.12 | 2.0 |
| `conduit_run` | 0.04 | 0.05 | 1.6 |
| `panel_field` | **0.012** (was 0.03) | 1.2 | 1.2 |
| `gutter_run` | 0.10 | 0.14 | 2.0 |
| `pilaster` | 0.05 | 0.12 | 4.2 |
| `frame` | 0.05 | 0.12 | 1.0 |

Span formula: `span = max(0.2, _COVER[cover]["span"] * max(size_hint, 0.1) / 0.6)`
(`:80`). Ratios cited as the sizing law: on a 3.7 m storey, base_course was 1/11 and
pilaster 1/15 (too coarse, both halved); gutter 1/26, curb 1/31, edge_strip 1/37,
conduit 1/74 left alone (`:30-34`).

### 2.12 Patina placement densities and budgets

**Anchors** — `patina/patina/anchors.py:66-71`:
`roofline_spacing 2.5 m` · `wall_base_spacing 3.5 m` · `light_spacing 5.0 m` ·
`ground_spacing 2.0 m` · `max_per_kind 64` (deterministic clamp, first N in emission
order, `:403-410`). Jitter is `spacing * 0.3` for roofline/wall_base and `* 0.2` for
ground (`:389-398`). Anchor size hints: roofline 0.6, wall_base 0.8, ground 0.4.
Example emission on a real building: `roofline:20, wall_base:16, exterior_light:12,
ground_edge:28` (`patina/README.md:377`).

**Decals** — `patina/patina/themes.py:158-172` (delco_1997_gas_station pool),
count = `round(area/100 * per_100m2 * density_scale)`, clamped to `spec.max_count`
(`decals.py:206-207`):

| decal | roles | per 100 m² | size (m) |
|---|---|---|---|
| water_stain | wall, ceiling | 6.0 | 0.5–1.2 |
| paint_chip | wall, exterior_wall | 5.0 | 0.2–0.6 |
| rust_streak | exterior_wall | 5.0 | 0.25–0.6, aspect 2.2–3.5, **vertical** |
| oil_stain | floor | 4.0 | 0.6–1.4 |
| scuff_marks | floor | 8.0 | 0.3–0.8 |
| gum_spot | floor | 10.0 | 0.08–0.18 |

Decal stamp texture size `_TEX_SIZE = 96 px` — "decals are small stamps, not tiling
materials" (`decals.py:36`). Grime anchor `#2a241f` = `(0.165, 0.141, 0.122)` (`:37`).

**Panel fields** — `patina/patina/paneling.py:33`: `_MIN_PANEL = 0.25 m` —
"Panels smaller than this on either axis read as noise, not paneling." Measured on
`category5_baie_dore_001`: 299 wall slots, all 299 with `facing` set, 74 `int_`
prefixed (`:44-45`) — facing is NOT an exterior signal.

**Dressing order counts, real building** (`patina/README.md:476`):
211 orders = `edge_strip:64, curb:64, base_course:50, conduit_run:33`.
Slot variation run: "10041 faces, 84 instances" over 84 slots (`:451`).
Slot variation strength default **0.12**, range 0–0.5 (`patina/README.md:129`).

### 2.13 Patina keep-out volumes — `patina/patina/gameplay.py:79-114`

- `_AGENT_RADIUS = 0.40` m — from Lot's `site_walk.tscn` NavigationMesh
- `_PROUDEST_COVER = 0.10` m — Zoo's `gutter_run`
- `STANCE = 0.50` m (derived floor)
- `_HEAD = 2.20` m

| marker kind | extra radius | z_lo | z_hi |
|---|---|---|---|
| objective | 1.50 | −0.50 | 2.20 |
| cover_low / cover_high | 1.00 | −0.50 | 2.20 |
| landmark | **2.00** | −1.00 | 3.50 |
| crew_spawn / responder_spawn | 1.00 | −0.50 | 2.20 |

Deliberately unprotected (`IGNORED`, `:118-123`): `camera_socket` ("a camera mount IS
dressing; it wants company"), `ladder`, `hatch`, `extraction`, `loot`.
Total reach = `STANCE + extra`, so a landmark is protected to 2.50 m radius.

### 2.14 Patina opening keep-out — `patina/patina/openings.py:43-72`

Traversable kinds: `door, garage, window, breach`. Exempt cover: **`frame` only**.
Zoo cross-axis mirror `_ZOO_CROSS`: edge_strip 0.10, base_course 0.18, curb 0.12,
conduit_run 0.05, panel_field 1.20, gutter_run 0.14, pilaster 0.12, frame 0.12.
Measured on `category5_baie_dore_001` (19 openings: 9 door, 6 window, 3 breach,
1 garage): **25 non-frame orders had their ORIGIN inside a hole** — 14 pilasters
across windows, 5 base courses + 5 curbs through door thresholds (`:13-16`).
Also measured: 3 base courses reached 0.32 m into openings a declared-span-only
test called clean (`:55-57`).

### 2.15 Patina vertex nuance constants — `patina/patina/nuance.py:41-70`

Base tints: floor `(0.62, 0.60, 0.58)` · wall `(0.74, 0.74, 0.76)` ·
ceiling `(0.66, 0.66, 0.64)` · trim `(0.68, 0.66, 0.64)` · unknown `(0.72,)*3`.
`_AO_STRENGTH 0.45` · `_GRIME_STRENGTH 0.25` · `_GRIME_HEIGHT 0.6 m` ·
`target_edge 0.75 m` · `max_subdiv 4` · `bevel_offset 0.015 m` ·
`mottle_scale 1.5 m` (3 octaves). Shell tri budget ~150–2500 (`docs/DESIGN.md:76`).
Posterize default 16 levels ≈ PS1 (`palette.py:62`); tiles 128–256 px (`:61`).
Depth preset composite on delco measured at ~0.54 mean luma
(`docs/LOOK_PIPELINE.md:95`).

### 2.16 Zoo material response — `zoo/zoo_keeper/bpylayer/materials.py:46-52`

`ROUGHNESS`: laminate 0.55, wood 0.65, metal 0.35, plastic 0.45 (+ from
`MATERIAL_COVERAGE.md:59-60`: brick 0.90, tile 0.35, drywall 0.90, ceiling_tile 0.92,
carpet 0.98, dirt 0.97). `METALLIC`: metal 0.85, carbon 0.30 — nothing else.
Texture interpolation forced to `"Closest"` — "pixel art stays pixel art" (`:252`).
Sign faces set `extension = "EXTEND"` — "a sign face never tiles" (`:171`).
`KNOWN_KINDS` is 19 kinds (`core/skins.py:38-41`).
Emissive material default strength 2.0 (flat) / 2.2 (textured) (`:119, :150`).

### 2.17 Zoo scatter (pile primitive) — `zoo/zoo_keeper/core/scatter.py:13-14`

`layer_rise 0.006 m` per item · `scale_range (0.85, 1.15)` · `max_rot π` ·
disk-uniform placement via `sqrt(rng.random())` "so the pile reads evenly; each
successive item rises slightly so a heap builds height instead of a flat sheet"
(`:18-20`).

### 2.18 Deli Counter felt-space / prop seeding — `deli_counter/level_design.py:59-65, 254-256`

| Constant | Value | Meaning |
|---|---|---|
| `_COVER_MIN_Z` | 0.6 m | below this it's a kerb, not cover |
| `_COVER_MAX_Z` | 2.4 m | above this it's a wall, not cover |
| `_COVER_HIGH_Z` | 1.4 m | ≥ this is high cover, else low |
| `_COVER_MAX_FOOTPRINT` | 7.0 m | if BOTH plan dims exceed this it's massing |
| `_COVER_DEDUPE_R` | 1.6 m | no cover marker within this of another |
| `_COVER_PER_ROOM_CAP` | **5** | "readability ceiling (thesis: don't over-cover)" |
| `_COVER_PER_ROOM_FLOOR` | 2 | a contested room wants at least this many |
| `_SEED_MIN_AREA` | 30.0 m² | "below this a bare room still reads fine" |
| `_SEED_MAX_PIECES` | **4** | "thesis: don't over-cover" |

Landmark rule: one per room whose `role` is in `_LANDMARK_ROLES`, at the room
centroid, z = `story*story_height + 1.0`, skipped if an existing landmark is within
2.0 m in x and y on the same story (`:199-239`).
Prop archetypes by room-name keyword (`:244-254`): office/manager/exec → desk
(1.6×0.8×0.75) + cabinet (0.9×0.5×1.4); storage/stock/back → shelf_run
(2.6×0.6×1.7) + pallet_stack (1.2×1.2×1.0); bay/garage/loading → crate_stack +
pallet_stack; lobby/hall/concourse → counter_island (2.2×0.8×1.05) + planter_box
(1.4×0.7×0.9); default crate_stack (1.1×1.1×0.95).
55 cover-name hints, 8 skip-names (`:46-57`).

### 2.19 Rarity colour table — `deli_counter/rarity.py:29-39`

Ordered tiers `common, uncommon, rare, very_rare, legendary` mapping to
`#FFFFFF` white · `#1EFF00` green · `#0070DD` blue · `#A335EE` purple ·
`#FFD700` gold. "Colours follow the design proposal's tier → colour names… using
the genre-standard loot-rarity hues, so a player reads the tier from the colour
with no legend" (`:32-34`). Unknown tier raises `ValueError` "so a typo fails
loudly offline rather than silently shipping a building the door reveal can't
colour" (`:60-62`). `rarity_color` is emitted on gameplay.json top level and on
every breachable door/breach anchor (`:5-8`).

### 2.20 Interactive fixture state machines — `deli_counter/interactives.py:38-124`

Six fixture kinds with declared states:
`door {closed, open}` reversible · `breach_wall {intact, breached}` terminal ·
`window {intact, broken}` terminal · `vault_door {locked, unlocked, open, breached}`
· `teller_window {intact, shattered}` · `safe_deposit_boxes {intact, drilled}`.
`state_geometry` maps a state to the Zoo module that backs it — e.g.
`{"intact": "wall", "breached": "breach"}`, `vault_door → {open: doorway,
breached: breach}`. `collision_per_state` and `reversible` are **ADVISORY**
descriptions, never instructions to netcode (`:36-37`).
Ids are `sha1(building|wall|story|kind|round(pos,4))[:8]` — place-derived, not
index-derived, "so re-greyboxing a building… never renumbers this fixture"
(`:140-151`).
Where a non-default state has no distinct art, `state_geometry` is omitted and Zoo
falls back to the base module — the progressive art pass (`:34-37`).

### 2.21 Skin style index — `deli_counter/skin_style.py:23-39`

Style index = 1-based order of the spec's `materials` list, first wins. Fallback
chain: surface material → spec default material → style 1. Module stems are
`{type}_{theme}_{style:02d}_...`.

### 2.22 Fixture hardware placement — `zoo/zoo_keeper/core/fixtures.py:38-52, 94-124`

`FIXTURES` map: `fluorescent → fluorescent_fixture` mount **above** ·
`streetlight → streetlight` mount **below** · `sign → sign_box` mount **center** ·
`wall_pack → wall_pack` mount above. `DAYLIGHT = {window, sun}` — no hardware.
Row expansion mirrors `LuxFluorescentRig` exactly: `start = -(count-1)/2 * spacing`
(`:111`). Streetlight pole stretches to grade z=0, clamped to genome min/max
(`:117-124`); Lot writes pole-top anchors at z=6 (`:21-22`).
Marker contract: `LuxEmit_<type>` empties carrying
`lux_type / lux_anchor_id / lux_slot / lux_reacts_to_alarm` as glTF extras
(`:54-65`). Consumers match by **prefix** and read type from metadata first, name
second (Blender dedupes `.001`, Godot swaps dot for underscore).

### 2.23 Zoo validation (per specimen) — `zoo/README.md:358-362`

"Every build is checked: dimensions vs genome range, tri budget (warn), UVs, wear
colors, materials, named parts, collision presence, applied transforms. Status
PASS / WARN / FAIL is printed and stored in the sidecar."
Species count: 31 props + 8 architectural modules (`:269-271`).
Kit-planning finding: "A real 128-slot building needs only ~9 modules — that's the
whole art-pass workload" (`:93`).

### 2.24 Dressing density budgets (specified, machine-readable) — `patina/docs/DRESSING_CHECKLIST.md:378-386`

Approximate maximum **coverage of visual and floor area** — explicitly *not* prop count:

| Zone | Coverage |
|---|---|
| Main path | 0–5% |
| Combat space | 5–15% |
| Functional edge | 15–30% |
| Narrative corner | 25–45% |
| Hero cluster | manual or custom template |

Placement priority order (`:353-361`): landmark → functional anchor props →
supporting cluster props → utility connections → narrative variation → decals →
small clutter → ambient effects.
Prop tagging axes (`:390-403`), seven: function, scale, placement, state, visual
priority, collision, faction.
Scorecard (`:405-419`): score 0–2 on ten axes (function, composition, gameplay
readability, prop relationships, colour control, material hierarchy, story,
density, vertical dressing, cohesion). 17–20 strong · 13–16 functional ·
9–12 inconsistent · **0–8 rebuild the dressing concept**.
Environmental-motion budget (`:236-237`): "one primary ambient motion, two or three
secondary, minimal background."

### 2.25 Shipped-building census — `patina/docs/DRESSING_CHECKLIST.md:496-505`

Measured on `lot_demo_001.deli_generate.candidate.seed_5017` (86,358-byte
`shell.gameplay.json`):
```
markers      14   cover_low 7 · cover_high 2 · landmark 2 · crew_spawn 1
                  responder_spawn 1 · camera_socket 1
objectives    2   with room, position, duration, required
zones         2   extraction · secure, each with bounds and centre
rooms         4   with bounds, role, combat_range, fortifiable, objective
surface_roles 303  wall 189 · stair 57 · window 30 · prop 11 · doorway 7
                   floor 4 · breach 4 · ceiling 1
```
**11 props total across 4 rooms** (`:576-577`).
Of §23's twelve required room-metadata fields: **3 present, 3 partial, 6 absent**
(`:468-484`).

### 2.26 Keep-out sensitivity (measured, currently inert) — `patina/patina/gameplay.py:33-56`

Run over `category5_baie_dore_001` (253 orders): the gameplay keep-out filter
removed **0** orders, all 22 boxes unhit. Zero orders overlap in plan even with z
ignored. Nearest approach from any order to any keep-out: **1.68 m**, against a
`cover_*` reach of 1.50 m. Sensitivity sweep: first drop at 1.5× the per-kind
allowance (8 orders), 18 orders at 2.0×.
Room-bounds variant was tried and rejected: on the same building it flagged
**1034 of 2098** orders including 603 of 1315 panel fields, "because a room's
bounds include the wall plane and every facade cover sits on it. A rule that flags
half the dressing is measuring the wall, not an intrusion" (`:25-31`).

---

## 3. MEASURED BUT ADVISORY

*Computed, reported, never blocking.*

1. **Poly budget** — `deli_counter/polybudget.py:11-14`: "This reports tri counts
   as INTEL… The numbers are informational. The one thing it can flag is the
   art-director **Environment/Module cap** — pieces that bust the hard ceiling are
   worth a designer's eye — but it's a warning, never a build-blocking error."
   `budget_warnings()` (`:172-176`) returns "neutral-but-worth-noting strings…
   surfaced as warnings (never errors)". Imported assets are recorded as
   unestimatable (`tris = -1`) and excluded from totals (`:124-133`).
   "Counts are estimates; the authoritative number comes from Blender. Treat these
   as a guardrail, not gospel." (`:28-29`)

2. **Zoo per-specimen tri budget** — "tri budget (warn)" in the validation list
   (`zoo/README.md:359`); dimension range, UVs, wear colours, materials, named
   parts, collision presence and applied transforms produce PASS / WARN / FAIL
   stored in the sidecar, but the CLI does not gate on WARN.

3. **z-fight: greybox-internal and entombed pairs** — `zoo`… sorry,
   `deli_counter/zfight_gate.py:259-271`: "Greybox-internal coincidences (stair
   treads flush with a floor slab, etc.)… are reported for intel, never gated on.
   Entombed pairs (visible_fights' suppression) are likewise intel only."
   `check_package` returns `greybox_internal_pairs` and `buried_pairs` counts
   alongside the blocking `findings`.

4. **Lux validator WARN/INFO tiers** — `lux/addons/lux/runtime/lux_validator.gd`:
   over-budget dynamic lights, over-budget shadow casters, glow+dither on a low
   tier are `Severity.WARN`; clustered-element count > 128, AreaLight3D on
   Compatibility, low `color_levels` with dithering, height fog on Compatibility,
   native-vertex-shading shadow caveats and Sun-Link status are `Severity.INFO`.
   Only *missing preset* and the two fixture-co-location failures are `ERROR`.
   The dock surfaces all of them; nothing in the addon refuses to run.

5. **Patina `--preview` luma headroom** — `patina/README.md:513-514`: "it renders
   the composite and reports a luma headroom verdict; on delco the full stack sits
   at ~0.54 mean (fine)." It "flags over-darkening (the risk from three
   multiplicative bakes feeding Lux's `× vertex_colour`) as a number" — a verdict,
   not a gate. Guidance on failure is explicitly "If it does, reduce strengths,
   don't clamp" (`docs/LOOK_PIPELINE.md:93-94`).

6. **Pixelcoat art-standard audit** — recommended as a *baseline*, not a gate:
   "Not as a red-on-main test of the current 30 offenders — that gets ignored
   within a week. As a *baseline*: snapshot today's numbers, fail on regression,
   and burn the baseline down deliberately." (`pixelcoat/docs/CONTRAST_DIRECTION.md:190-194`).
   Its thresholds are self-described as "a proposal, not a measurement, and the
   report prints the distribution next to them so the calibration is auditable"
   (`tools/art_standard_audit.py:30-33`). Nothing in the shipped pipeline consumes it.

7. **Pixelcoat mip / shimmer previews** — `pixelcoat/README.md:83-91`: "linear-space
   mip strips with per-level normal renormalization and a **shimmer warning** when
   high-frequency normals average short at distance"; block-compression previews
   with "per-map family suggestions and error stats in the build report";
   "Tiled builds also flag unique landmarks that would read as obvious repeats."
   All written under `<asset>/previews/`; "never alter canonical PNGs".

8. **Patina keep-out filters that currently drop nothing** —
   `patina/patina/gameplay.py:48-56`: "So this is a TRIPWIRE, and it starts doing
   work the day interior dressing arrives. Stated here because a filter reporting
   zero is indistinguishable from a filter that was never wired… THE RADII ARE
   THEREFORE UNVALIDATED. Nothing in the shipped data exercises them… this
   measurement cannot tell "correct" from "slightly too small"."

9. **Patina anchors are purely advisory metadata** —
   `patina/README.md:392-395`: "Anchors are **visual-only metadata** — the styled
   `.glb` is byte-identical whether or not `--anchors` is set… Off by default;
   it's a handoff artifact." `docs/SEAMS.md:84-86`: "a tool is free to ignore any
   anchor."

10. **Zoo `wear_probe`** — `zoo/tools/wear_probe.py:41-44`: "It does not fix
    anything… WHAT A NONZERO EXIT MEANS. Blender was not the interpreter (exit 2),
    or the build/export raised (exit 2). **White wear is a finding and exits 0.**"
    i.e. the diagnostic for the single largest known wear defect is advisory by
    construction.

11. **The dressing scorecard** — `patina/docs/DRESSING_CHECKLIST.md:405-419` is a
    human 0–2 score across ten axes with band verdicts; there is no code that
    computes it. "A deliberately quiet room does not need a perfect score, but it
    must still pass gameplay, composition, function and cohesion."

12. **Lot §22 review tests (thumbnail / grayscale / blur)** —
    `pixelcoat/docs/CONTRAST_DIRECTION.md:241-256` specifies three numpy tests over
    a walk frame ("Uniform contrast lands near 0.10; a scene with a real focal
    point lands far above it. This is the single number that answers *does the
    scene have equal contrast everywhere*"). Proposed as `walktest_contrast`;
    **not implemented** — see §4.

---

## 4. CONSPICUOUSLY ABSENT

*What "a detailed living world" needs that nothing here measures, supported by the
code's own admissions.*

### 4.1 SOUND — nothing. Named once, then never again.

The single canonical statement of what "alive" means includes sound:

> "architecture, props, textures, light, wear, **sound** and movement all suggest
> that the space has a purpose" — `patina/docs/DRESSING_CHECKLIST.md:453-456`

and §13 requires it as a gate on animated props:

> "Confirm: motion has a visible cause · … · **animated props have appropriate
> sound**" — `patina/docs/DRESSING_CHECKLIST.md:239-241`

There is **no audio vocabulary anywhere in these four repos**. No emitter type, no
anchor kind, no manifest field, no rig, no validator. Lux ships environment,
lighting, materials, atmosphere, post FX, palettes, presets, a runtime API and
editor tooling (`lux/README.md:23-25`) — and no audio module. `deli_counter/lights.py`
derives *where lights belong*; there is no `sounds.py` deriving where sound belongs,
even though the same rooms/openings data would support it. `rarity.py:8-9` explicitly
punts the audio half of the reveal to the game: "the light burst, **the sound cue**,
the HUD banner… is game code that reads this value. The tool carries the number; the
game does the show." The one place a sound *is* required by the design (§13) is
unenforceable because motion itself does not exist (§4.2).

### 4.2 MOVING / ANIMATED ELEMENTS — specified in prose, zero mechanism.

§13 "Add environmental motion" (`patina/docs/DRESSING_CHECKLIST.md:231-241`) asks for
"Fan rotation, belt movement, blinking display, dripping fluid, steam vent, swinging
cable, moving shadow, electrical flicker, scrolling pixel display, distant machinery,
floating dust", with a budget of "one primary ambient motion, two or three secondary"
and the rule "repeated animation is not perfectly synchronized". The owner column
assigns §13 to **"Lux / Zoo"** (`:26`).

What actually exists:
- **Zoo has no animation at all.** Species are static meshes; `exhaust_fan` and
  `satellite_dish` are geometry recipes. Outputs per specimen are meshes, UVs,
  vertex colours, collision siblings, `ATT_*` empties, optional LODs
  (`zoo/README.md:334-341`) — no armatures, no animation channels.
- **Lux's only motion is light flicker**: `flicker_amount` / `flicker_speed`
  (`lux_light_rig.gd:24-27`), plus `pulse_alarm_lights` and preset blending
  (`lux/README.md:106-108`). Even that is disabled when a rig bakes Static: "Flicker
  on a Static light only shows on dynamic objects (the lightmap is frozen), so rigs
  disable flicker when Static" (`lux_light_rig.gd:37-38`).
- **Interactives are state swaps, not animation.** `deli_counter/interactives.py`
  models a door as `{closed, open}` with a per-state *art variant* — the game
  "spawns one replicated node per id and drives which art variant renders"
  (`:204-206`). A door does not swing; it changes which mesh is drawn.

Nothing counts, budgets, de-synchronises or validates ambient motion. The §13
budget ("one primary, two or three secondary") has no consumer.

### 4.3 NPC LIFE — absent as a concept.

There is no NPC, no crowd, no idle actor, no ambient life anywhere in these four
repos. `deli_counter` emits `crew_spawn` and `responder_spawn` **markers**
(`patina/patina/gameplay.py:15-16`) and `LuxRole.CHARACTER` exists as a *material
profile* (`lux_role.gd:14-16`) — a shading path for a mesh someone else supplies.
The checklist's entire "inhabited" vocabulary is **residue, not occupants**:
"activity evidence — open drawer, pulled-out chair, active screen, loose tool,
spilled liquid" (`DRESSING_CHECKLIST.md:135-137`); "abandoned lunch, open locker,
emergency repair… recent struggle" (`:117-119`). The design's theory of "inhabited"
is deliberately *the trace of a person who has left*. That is a coherent position,
but it means nothing in the pipeline ever measures or places a living thing, and
"faction occupation" (§14.3) has no expression: **`faction` is one of the six absent
room-metadata fields** (`:472`).

### 4.4 TIME OF DAY — an API surface with no pipeline behind it.

`LuxRuntimeAPI` exposes `set_time_of_day` and `set_weather`
(`lux/README.md:106-108`), and Sun Link relights the vertex world as a sun moves
(`docs/getting_started.md:133-157`). But:
- **Time-of-day blending is on the roadmap, not shipped**: "Weather profiles +
  wet-surface response, **time-of-day blending**, an emergency-light system…"
  (`lux/README.md:145-147`).
- `LuxWeatherProfile` is a stub: "In the MVP this resource exists so set_weather()
  has a stable type and presets can reference it; **full wet-surface / particle
  response is a post-MVP roadmap item**" (`lux_weather_profile.gd:4-6`).
- The sun is borrowed from **SkyMint** if present, with "no hard dependency"
  (`lux_root.gd:49-52`) — so a level built by this pipeline has no time of day
  unless a separate addon supplies one.
- Nothing upstream is time-aware: `deli_counter/lights.py` emits `window` anchors
  as "daylight through glass" with no hour, azimuth, or intensity; Patina's depth
  presets bake a *fixed* recession; Pixelcoat's `lighting_flatten` explicitly
  removes directional illumination from source photos (`lighting_flatten.py:3-6`).
- **Time as a dimension of dressing does not exist either.** §14's story layers
  ("original construction / normal use / long-term change / recent event") and
  §15's `age` field are unimplemented: "**Everything in §14–17 is blocked on
  `state` alone**" (`DRESSING_CHECKLIST.md:560-561`), and `state` and `age` are
  both listed as absent (`:473-474`).

### 4.5 SIGHTLINE LANDMARKS FOR ORIENTATION — the marker exists, the *visibility* is never checked.

This is the sharpest gap in my area, because both halves are present and neither
touches the other.

- A landmark **marker** is placed at each major zone's centroid
  (`deli_counter/level_design.py:199-239`), and a 2.50 m keep-out sphere protects
  its "visual breathing space" (`patina/patina/gameplay.py:107`).
- The design requires it be *seen*: "the landmark is at least partly visible"
  (`DRESSING_CHECKLIST.md:105`); "distinct CALLOUT landmarks **you can read from a
  distance**" (`level_design.py:19-20`); "major shapes readable at thumbnail size"
  (`:91`).
- **Nothing computes whether a landmark is visible from anywhere.** The landmark
  pass is centroid arithmetic with a 2.0 m dedupe; it never raycasts, never
  consults `sightlines.py`, never asks whether a wall stands between the entry
  point and the landmark. `level_design.py:206` hands the whole visual half over:
  "The marker is just the anchor + a label -- **the art team makes it visually
  distinct.**" There is no mechanism that makes it distinct, and no check that it
  is.
- The three tests that would measure it are specified and **not built**:
  "**Thumbnail** — downsample to 64px, check the focal marker still separates from
  its local background… **Grayscale** — drop chroma, re-run the same separation
  check… **Blur** — … Uniform contrast lands near 0.10; a scene with a real focal
  point lands far above it." Their status: "That **becomes** a `walktest_contrast`
  step alongside `walktest_navqa`" (`pixelcoat/docs/CONTRAST_DIRECTION.md:241-256`),
  ordered fifth on a list whose step 0 has not been done (`:474-495`).
- Consequently the checklist's own §4 composition checks — "Confirm the focal point
  is not centred by accident · the path is visible · important silhouettes do not
  overlap · large forms create framing" (`:102-105`) — are pure prose. Nothing in
  the pipeline stands at the entry point.

### 4.6 The other structural absences, stated by the pipeline itself

`patina/docs/DRESSING_CHECKLIST.md:566-579`, "What this sheet does not yet have a
mechanism for… Stated plainly so it is not mistaken for done":

> - "**No quiet tier in the kit.** §2 tier 5 and §5's quiet zone have no module to
>   point at until the `relief: {reveal: 0}` style is proven in a build.
> - **No accent mechanism.** §6's "one accent per cluster" and §11's reserved
>   gameplay colours need an emissive path. **Zero grammars in the library emit.**
> - **No cluster concept anywhere.** §6 and §23's cluster rules describe an anchor
>   plus supports plus evidence. **Patina places single covers.**
> - **No three-scale rule.** §7 needs a size hierarchy in the prop set; the demo
>   building carries **11 props total across 4 rooms**.
> - **Wear is not cause-driven.** §15 wants wear at contact points. Patina's
>   weathering is procedural over the whole surface."

And the three-way independent failure of the quiet tier:

> "§18 is the clause we fail hardest, and we fail it three times independently…
> **There is structurally no way to have a quiet brick and a hero brick in the same
> theme.** Every brick wall in a building wears the same brick by construction…
> **Every wall we ship is a hero asset.**… Dressing is applied per eligible wall
> face, not against a budget. §3's 70/20/10 is a compositional target; a per-face
> rule cannot express it."
> — `pixelcoat/docs/CONTRAST_DIRECTION.md:105-136`

Six of §23's twelve required room-metadata fields are absent —
`faction`, `current state`, `age`, `secondary route`, **`quiet zones`**, `accent
colour`, `dressing density` — and "The absent six are exactly what §23's cluster,
exclusion and density rules consume" (`DRESSING_CHECKLIST.md:466-486`). Of these,
quiet zones are singled out: "**and this is the one everything else waits on**"
(`:478`).

Additional absences visible in the code but not in a summary list:

- **No visibility/occlusion input to any art decision.** Patina's §Pa1 target —
  "Dressing density becomes a fraction of eligible faces, **ranked by visibility**"
  (`CONTRAST_DIRECTION.md:217-219`) — has no visibility term to rank by. Every
  placement in the pipeline is arithmetic over geometry: `_points_along` on wall
  segments, a grid per slot, a row per room.
- **No ordering fix for firing-lane quiet zones.** "Patina cannot do that today:
  it runs per-building, before Lot places anything on the site, so the firing lanes
  do not exist yet. That is an ordering problem, not a missing feature, and it
  should be recorded as such rather than half-solved" (`:219-222`). Partially
  corrected later — per-building combat data *is* present and unread
  (`DRESSING_CHECKLIST.md:507-515`) — but the site-level lanes remain out of reach.
- **No silhouette-background rule.** `patina/patina/gameplay.py:58-68`: "A radius
  protects the volume AT a marker. Checklist §11 and §20 are about what sits BEHIND
  a body from the shooter's side… That is a SIGHTLINE, not a sphere… That one needs
  `spawn -> objective` route geometry the schema does not carry yet, and calling it
  done because a radius shipped would be the "designed correctly, never wired"
  pattern with extra steps."
- **Vertical banding is single-storey only.** "The fraction uses the **global**
  visual-AABB Z range… (correct for the single-storey blockouts Deli Counter emits;
  multi-storey shells would want per-wall normalisation, **noted as future work**)"
  (`patina/patina/banding.py:24-28`). Per-band *pattern* variation (brick base vs
  concrete body, not just tint) is deferred: "Bands vary colour; the shared pattern
  is tinted per band" (`patina/README.md:360-363`).
- **No floor / ceiling / ground material path.** `carpet`, `dirt`, `ceiling_tile`
  and tiled floors are registered kinds with no species to request them:
  "`build_slab` makes a *vertical* slab, and Zoo has no floor/ceiling/ground
  module… **Spec, not shipped.**" (`pixelcoat/docs/MATERIAL_COVERAGE.md:80-87`).
- **No theme data.** `deli_counter/themes/` contains one directory (`gasstation/`)
  holding one 3,188-byte GLB. There is no per-theme dressing profile, no accent
  colour, no density setting in the tree the task pointed at.
- **The in-engine walk is still owed on every visual claim.** Patina's status table
  marks the Godot decal instantiation, the PS1 shader and the addon as
  "**First-run-in-engine**" (`patina/README.md:147, 161`); the dressing-cover render
  over DC collision is "the standing caveat" (`docs/DRESSING_CONTRACT.md:88-91`).
  Every number in §2 above is an offline measurement of a file, not of a frame.
