@tool
extends EditorScenePostImport
## World-space UVs on kit modules, applied AT IMPORT and baked into the .scn.
##
## WHY THIS IS AN IMPORT SCRIPT. Zoo bakes UVs into the mesh (box projection
## from each module's own centre-pivot local box) and glTF carries UV sets and
## nothing else -- there is no way to express "project from world position" in a
## .glb. So it can only be a material property set after import. The runtime
## version of this (`walk_triplanar.gd`) proved the effect in a scratch project;
## this is the same change made where it PERSISTS.
##
## AND WHY NOT A SCENE PASS. Setting the property on a composed scene means
## either mutating shared material resources (which does not survive being
## saved) or writing `surface_material_override` per MeshInstance3D -- and that
## is a separate material per placement, which is Deli Counter's one-mesh-in-
## VRAM discipline undone at the material layer for the sake of a boolean. At
## import the material is edited once, inside the imported scene, and every
## instance of that GLB shares it. Roadmap 80.
##
## WHAT IT FIXES, both measured before this was written:
##   * every module's texture restarts at its own edges, drawing a hard seam at
##     every 2.00 m boundary the length of a facade (roadmap 76);
##   * a `wallEnd` scaled 0.15 x 3.30 to fill a remainder stretches its texture
##     11:1 or worse, at 46 placements per building (roadmap 88).
## Both are the same defect -- appearance derived from the module rather than
## from the world -- and world projection removes the module from the equation.
##
## SCOPED BY ASSET NAME, because at import time there is no scene to read. The
## runtime script scoped to nodes under Deli Counter's `ext_*` / `int_*` slots;
## those slots instance exactly the five families below. Props and dressing are
## deliberately excluded: world projection on a small movable object is wrong --
## it swims when the object moves -- and the dressing path already varies
## between instances.

const KIT_PREFIXES: Array = ["wall_", "wallEnd_", "window_", "doorway_",
	"breach_"]

## The greybox base the composer keeps whole (floors, collision, STAIRS).
## Its stairs are Deli Counter's `stair<n>_*` boxes in the flat `gb_stair`
## material -- "the stairs ship in the greybox's fallback yellow", walked on
## cold run 9005 (roadmap 144). Zoo has no stair species and every plate and
## wall around them is skinned, so the base is the one place in a shipped
## level the yellow still shows.
const BASE_PREFIX: String = "site_base"
const STAIR_PREFIX: String = "stair"

## REFUTED 2026-09-16, kept above the rule that replaced it.
##
## 0.72.0 wrote `STAIR_KIND = "concrete"` and looked for a kit module whose
## material name carried `_concrete`. "The stairs are concrete in every 1990s
## hospital there is" was true and the lookup was not: it asks a building for
## a finish it may not own. Measured on cold run 9061's package, four
## `site_base.glb` imports, four different notes, and `0 stair surface(s)
## skinned` on every one of them:
##
##   lot/pharmacy_a01     found concrete in wall_delco_1997_01_w200.glb -- and
##                        that base has no stair mesh at all. Correct no-op,
##                        indistinguishable in the log from a failure.
##   lot/strip_retail_a02 the same.
##   site_base.glb (root) no `art/zoo` beside it: an export leftover no scene
##                        references, carrying 24 visual stair meshes.
##   lot/card_shop_a01    24 visual stair meshes, and its kit is brick, glass
##                        facade, drywall and wood panel. A CARD SHOP HAS NO
##                        CONCRETE WALL. "no imported kit module wearing
##                        concrete under art/zoo", and the walker photographed
##                        the yellow flight between skinned brick walls.
##
## So the pack is chosen by FAMILY, not by finish name. Every building has a
## floor and a wall family by construction, and `site.tscn` instances both --
## which is what makes this free: the material duplicated here points at a
## texture that is already resident, so no texture memory and no draw call is
## added. Within a family, sort order picks the module, and sort order is a
## derivation rather than an accident: Zoo's `kit.module_stem` writes
## `{typ}_{theme}_{style:02d}` with the style index at a fixed position, and a
## style index is the 1-based position in `spec.materials`, whose first entry
## is the spec's default finish (`floors.FINISH_PALETTE` is APPENDED, so
## authored styles keep their numbers -- roadmap 146). Lowest style = the
## building's default surface. Measured on the same package: card_shop
## floor 05 concrete / 08 tile / 09 carpet, pharmacy and strip_retail floor 01
## default / 06 carpet / 07 tile -- the default in all three.
##
## A TREAD IS A FLOOR, so the flight takes the floor family.
const STAIR_FLIGHT_FAMILY: Array = ["floor_"]
## THE GUARDS ARE NOT THIS PASS'S BUSINESS, and that was a plan before it was
## a rule -- the rule is what the artefact said when it was asked.
##
## `stairwell.stair_guards` bakes `side`, `back` and `rail` volumes beside the
## flight and `Builder._stair_guards` gives each one "the geometry, collision,
## recorded slot and surface material every volume gets". RECORDED SLOT is the
## operative half. The intended change here was to skin `stair_guard_*` with
## the wall family, on the reading that a 1.07 m by 0.10 m guard is a wall
## rather than a balustrade. Measured on cold run 9061's card_shop_a01 before
## writing it, and it is wrong twice over:
##
##  * The themed scene already fills those six slots, with better packs than
##    this could pick. `lot/card_shop_a01/site.tscn` lines 661-676 instance
##    `prop_delco_1997_01_w385_d40_h315_mbrick` on the two sides and the back
##    and `prop_delco_1997_07_*_mwood` on the three rails -- the building's
##    own wall for the sides and wood for the rails, from its palette, exactly
##    as `_stair_guards`' docstring says. Painted metal would have replaced a
##    palette-driven choice with a hardcoded one.
##  * The base's guard meshes are not drawn at all. In the GLB the six meshes
##    `stair_guard_side_0` .. `stair_guard_back_5` (all `gb_prop`) are
##    referenced by NO node; the only nodes carrying a guard mesh are the
##    `*_col-convcolonly` bodies. The composer drops the greybox mesh for a
##    slot it fills. Same shape on four more buildings: bank_branch_a02 48
##    stair-named meshes / 38 instanced, construction_site_a01 24 / 19,
##    strip_club_a03 25 / 19, twin_a01 80 / 60 -- every orphan a guard.
##
## So a guard mesh is COUNTED and LEFT ALONE. One that is actually instanced
## means a slot the composer did not fill, and skinning it here would hide
## that rather than report it.
const STAIR_GUARD_PREFIX: String = "stair_guard_"

## The greybox slab's CUT EDGE, which theming never reaches (roadmap 168).
##
## Walked 2026-09-23: on a ladder, looking down reads grey and untextured and
## the real floor appears on the way down; the walker reported the same on the
## stairs independently. Measured on cold run 9070's package before a line of
## this was written, because four cheaper explanations were on the table and
## every one of them is wrong:
##
##  * NOT draw distance. Every mesh in that column reports
##    `visibility_range_begin/end = 0`, `lod_bias = 1.0` and no distance fade.
##    Nothing in the scene changes with camera distance at all.
##  * NOT occlusion culling. Two package copies differing only in
##    `use_occlusion_culling` in `project.godot` drew identical counts at four
##    eye heights (52/38/82/12).
##  * NOT z-fighting. The themed floor's top and the slab's top are 20 mm
##    apart and a 24-bit buffer separates about 0.03 mm at that range. The
##    coplanar pair is the floor's UNDERSIDE against the slab's top, which
##    backface culling never draws.
##  * NOT a gap in the floor. Themed floor area equals slab area to 0.1 m2
##    (3192.0 against 3192.0), and the ladder hole is cut through BOTH to the
##    same rectangle -- slab x 53.45..54.55 z 21.9..23.2, themed floor the
##    same to the raster's own 5 cm cell.
##
## What is left is the only untextured surface in the column. Theming skins a
## slab's TOP (as a floor) and its BOTTOM (as a ceiling) and never touches the
## faces that a hole cut through it CREATES. `deli_counter._slab_holes_cut`
## boolean-subtracts the opening and the new interior faces inherit the slab's
## flat `gb_floor`. A slab is `floor_thick` deep, so a 1.10 x 1.30 m ladder
## hole is ringed by 1.44 m2 of bare greybox -- the same area as the opening it
## surrounds, which is why it fills the view from anywhere but straight down.
## 8 of 344 slabs in that package are cut, carrying 10.44 m2 between them:
## every ladder shaft and every stairwell.
##
## THE WHOLE SLAB IS SKINNED, NOT THE COLLAR. The buried top and bottom cost
## nothing to dress -- it is one mesh with one material either way, so the
## submission count does not move -- and picking the interior faces out of a
## boolean result would mean trusting normals that the cut generated.
##
## A BOOLEAN'S NEW FACES CARRY NO USABLE UVs, which is the same problem
## `_skin_stairs` was written for and takes the same answer: world triplanar
## projects from position and needs none.
const SLAB_PREFIX: String = "slab_"
## Deli Counter's collision slabs are `slab_col_<story>`; its visual ones are
## `slab_<story>` and `slab_<story>_t<j>_<i>`. One spelling of the test, shared
## with the stair pass's shape rather than written a second way.
const SLAB_COLLISION_MARK: String = "col"
## A REVEAL TAKES THE FAMILY OF THE SURFACE IT MEETS. The collar's top edge
## abuts the themed floor plane, so sharing that family makes the one seam a
## walker actually sees continuous. The wall family was considered and left:
## it would match a seam that is not there. Same value as
## `STAIR_FLIGHT_FAMILY` and written out rather than aliased to it, so the two
## can diverge later without one silently moving the other.
const SLAB_REVEAL_FAMILY: Array = ["floor_"]

## Families whose module is ONE TILE of a surface that repeats: the kit above,
## and the panels a floor, ceiling or roof is laid from, and Patina's building
## dressing (`<building>_dressing.glb`, runs of edge strips and base courses
## laid end to end). Their vertex colour stays off -- see
## `_vertex_colour_albedo`.
const TILED_PREFIXES: Array = ["ceiling_", "floor_", "roof_"]
const TILED_SUFFIXES: Array = ["_dressing.glb"]
## A vertex is white when every channel is at least this. Zoo writes an
## untouched `Wear` corner as exactly 1.0.
const VERTEX_WHITE: float = 0.99

## ---------------------------------------------------------------------------
## CRT MOTION (0.89.0)
##
## Zoo 0.90.0 lights the club's bracket TVs: a ballgame painted into a texture,
## worn as albedo AND emission on a `M_CRT_Screen_<art>_Face` StandardMaterial3D
## at emission energy 1.5. Measured on walk 9059_rain's strip_club_a03: 7 screen
## surfaces, 5 distinct materials, 224x168 picture, face 0.4450 x 0.3328 m on
## five sets and 0.3953 x 0.2960 m on two, UV spanning the full 0..1 on both
## axes. A still picture reads as a photograph of a TV rather than a TV.
##
## WHY THIS IS A NEXT PASS AND NOT A REPLACEMENT MATERIAL, which is the whole
## design and was settled by measurement, not by preference. Lux's power cut
## (`LuxEmissiveBinder`, `LuxLighting.set_fixtures_powered`) finds lit faces by
## walking the scene and casting each material to BaseMaterial3D, then zeroes
## `emission_energy_multiplier`. A ShaderMaterial is not a BaseMaterial3D and
## has no such property. MEASURED with the walk copy's own vendored binder --
## content-identical to lux's -- over three materials all named to the lit-face
## contract: `bind` collected 2 of 3, and the one it silently dropped was the
## ShaderMaterial. Swapping the screen material for a shader would have left the
## club's TVs glowing through a power cut, with nothing reporting it.
##
##     shape                                   bound   after set_fixtures_powered(false)
##     StandardMaterial3D (ships today)         yes     energy 1.5 -> 0.0000
##     ShaderMaterial (full replacement)        NO      no such property
##     StandardMaterial3D + shader next_pass    yes     energy 1.5 -> 0.0000
##
## So the picture keeps its StandardMaterial3D untouched -- same textures, same
## emission, same energy, still bound by Lux -- and the motion rides a second
## pass over it. Two consequences worth stating:
##
##   * The picture is unchanged when time stands still in the strongest sense
##     available: at ALPHA 0 the base material draws exactly the frame 0.88.0
##     drew, because nothing about it moved.
##   * The overlay DARKENS ONLY -- `blend_mix` with ALBEDO 0, so the face is
##     multiplied by (1 - ALPHA). That is a real gain modulation, which is what
##     a CRT's brightness actually does, and it is what makes the power cut
##     safe without the shader having to know about it: a screen Lux has taken
##     to black is still black after being multiplied down. An additive overlay
##     would have glowed on a dead set.
##
## NOT IN LOCKSTEP, and a per-material seed cannot do it. Two of the five
## materials are worn by two sets each (`wall_tv_r1d196568_7` with
## `wall_tv_r420234d8_6`, and `wall_tv_r1d196568_10` with `wall_tv_ra07f4e1a_7`
## -- the second pair 7.67 m apart on one wall run, so both can be in frame).
## The phase therefore comes from `NODE_POSITION_WORLD`, a per-instance
## built-in: same material, different set, different roll. The seven faces stand
## at seven distinct positions, the closest two 5.520 m apart.

## The sync bar's half-width as a fraction of the picture height. NTSC blanks 21
## lines of a 262.5-line field, so the bar a vertical-hold error walks over the
## picture is that fraction of it. Not a number anyone chose.
const ROLL_BAND_FRAC: float = 21.0 / 262.5

## A set rolls when its vertical oscillator misses the 59.94 Hz field rate, and
## the bar crosses the face once per beat -- so the traverse period is one over
## the error. THE CONSTRAINT IS THE WALKER'S: it must read as "the game is on",
## never as a set rolling out of sync. A set a person calls broken tumbles at
## about 1 Hz and up; 0.2 Hz is five times below the slowest of that, one
## traverse every 5 s, and across the 0.3328 m face that is 0.0666 m/s -- 1.9
## degrees per second at 2 m. Drift, not tumble.
const VHOLD_ERROR_HZ: float = 0.2
const ROLL_PERIOD_S: float = 1.0 / VHOLD_ERROR_HZ

## Which sign walks the bar UP the face depends on the UV orientation Zoo
## painted, so it was read off the frames rather than reasoned about. At +1 the
## darkest row of the screen region, measured on four captures a quarter period
## apart at the 2 m station, ran 0.543 -> 0.762 -> 0.962 -> 0.276 of the way
## DOWN the face (row 0 is the top row of the region), advancing 0.20-0.31 per
## 1.25 s against the 0.25 the period predicts. Down is not what was asked for,
## so the sign is -1.
const ROLL_UP: float = -1.0

## How far the bar pulls the face down at its centre, and how far the flicker
## and the snow do. These three are the taste knobs and none of them is derived
## -- there is no physical quantity that says how visible "faint" is. They were
## set here and then MEASURED in the frames; what they produce on the club's
## brightest screen region at 2 m is in the 0.89.0 changelog entry, so a reader
## who wants a different look knows what they are moving from. Their sum bounds
## the worst dimming at ROLL_DEPTH + FLICKER_DEPTH + NOISE_DEPTH.
const ROLL_DEPTH: float = 0.10
const FLICKER_DEPTH: float = 0.035
const NOISE_DEPTH: float = 0.04

## Two flicker rates rather than one, so the brightness never settles into a
## pulse a viewer can count. They share no short common period.
const FLICKER_HZ_A: float = 1.3
const FLICKER_HZ_B: float = 2.1

## The snow is renewed this many times a second. A CRT renews it per field at
## 59.94 Hz, which at a 60 Hz display beats against the refresh into a strobe
## instead of a shimmer, so it is deliberately NOT the physical rate. 12 Hz is
## one new grain field every five frames at 60 fps.
const NOISE_HZ: float = 12.0

## The picture size to assume when a face somehow carries no albedo texture, so
## the snow's grain still lands at picture scale. Zoo paints 224x168.
const PICTURE_PX_FALLBACK: Vector2 = Vector2(224.0, 168.0)

## HOW FAR PROUD OF THE GLASS THE OVERLAY SITS, and it is not cosmetic -- without
## it the pass does not draw at all.
##
## A next_pass rasterises the SAME triangles at the SAME depth the base pass has
## already written, and in GL Compatibility the depth test rejects it. MEASURED
## in the club at 1600x900, each variant painting the face solid black, mean
## luminance of the face's projected rect against a control rect beside it:
##
##     variant                                   in front    from behind
##     no next pass (baseline)                     99.15         39.55
##     unshaded                                       --         (not drawn)
##     unshaded, blend_mix                            --         (not drawn)
##     + depth_draw_never                             --         (not drawn)
##     + depth_test_disabled                        1.41          1.08  LEAKS
##     + VERTEX along NORMAL, 0.2 mm                2.18         39.59
##     + VERTEX along NORMAL, 0.5 mm                2.01         39.57
##     + VERTEX along NORMAL, 1 mm                  1.78         39.53
##     + VERTEX along NORMAL, 2 mm                  1.49         39.53
##
## `depth_test_disabled` draws, and draws through the set's own cabinet -- the
## column on the right is a camera behind the TV, where it still blacked the
## region out. A pass with no depth test hangs on whatever is in front of it,
## which on a level this size means faint rolling bands on walls with no TV
## behind them. So the depth test stays ON and the overlay is lifted a hair
## along the surface normal instead, which is the ordinary decal offset: it
## wins the depth test against its own picture and loses it, correctly, to a
## wall.
##
## 2 mm: the largest of the four that changes nothing about occlusion (39.53
## against a 39.55 baseline from behind) while leaving the least residue at the
## curved face's silhouette, where the normal is across the view and no offset
## helps. It is 3.2% of the 0.063 m glass box, so the overlay stays well inside
## the cabinet's own volume, and at 2 m it moves the silhouette by about a tenth
## of a pixel.
##
## REFUTED ON THE WAY, kept because the retraction is the useful part: the first
## fix biased `VERTEX.z`, on the assumption that vertex() works in view space.
## It works in MODEL space, so `.z` was the set's own axis -- the overlay drew
## from behind the TV and not from in front of it, exactly backwards, at every
## magnitude tried.
const SCREEN_PROUD_M: float = 0.002

## Exactly the lit bracket face and nothing else. Zoo's stand set wears
## `M_CRT_screen` -- no `_Face`, lowercase, and deliberately dark because a set
## on a surface is off -- and the vending machine's lit panel is `_Face` and
## `_Lens` too, so `_Face` alone is not the test and neither is `CRT`.
const CRT_FACE_MARK: String = "CRT_Screen"
const CRT_FACE_SUFFIX: String = "_Face"
const CRT_FACE_PREFIX: String = "M_"

const MOTION_SHADER: String = """
shader_type spatial;
render_mode unshaded, blend_mix, depth_draw_never, cull_disabled,
	shadows_disabled, fog_disabled;

// A DARKENING PASS OVER A PICTURE THAT IS ALREADY DRAWN. ALBEDO is black and
// blending is mix, so the face is multiplied by (1 - ALPHA): a gain, which is
// what a CRT's brightness is, and which leaves a screen Lux has blacked out
// black. Nothing here samples the picture -- a flat gain modulates it exactly.

uniform float roll_period_s;
uniform float roll_band_frac;
uniform float roll_depth;
uniform float roll_dir;
uniform float flicker_depth;
uniform float flicker_hz_a;
uniform float flicker_hz_b;
uniform float noise_depth;
uniform float noise_hz;
uniform vec2 picture_pixels;
uniform float proud_m;

const float TAU_ = 6.2831853;

// A HAIR PROUD OF THE GLASS, or the depth test throws the whole pass away --
// it draws the same triangles at the same depth as the picture under it. Along
// the NORMAL, in model space, which is where vertex() works: that means "out
// of the screen" from wherever anybody is standing, so the pass still loses
// the depth test to a wall in front of the set.
void vertex() {
	VERTEX += NORMAL * proud_m;
}

float hash11(float x) {
	return fract(sin(x) * 43758.5453123);
}

float hash21(vec2 p) {
	return fract(sin(dot(p, vec2(12.9898, 78.233))) * 43758.5453123);
}

void fragment() {
	// ONE PHASE PER SET, not per material. NODE_POSITION_WORLD is a
	// per-instance built-in, so the two sets that share a material still roll
	// apart. Deterministic: the same set is the same phase every run.
	float phase = hash11(dot(NODE_POSITION_WORLD, vec3(12.9898, 78.233, 37.719)));

	// the sync bar, walking the face, wrapping at the edges
	float bar = fract(TIME / roll_period_s * roll_dir + phase);
	float d = abs(fract(UV.y - bar + 0.5) - 0.5);
	float roll = roll_depth * smoothstep(roll_band_frac, 0.0, d);

	// brightness flicker, two rates so it never reads as a pulse
	float ph = phase * TAU_;
	float fa = 0.5 + 0.5 * sin(TIME * flicker_hz_a * TAU_ + ph);
	float fb = 0.5 + 0.5 * sin(TIME * flicker_hz_b * TAU_ + ph * 1.7);
	float flicker = flicker_depth * 0.5 * (fa + fb);

	// snow: one grain per PICTURE pixel, so it reads as the picture's own
	// grain and not as the display's
	vec2 cell = floor(UV * picture_pixels);
	float snow = hash21(cell + vec2(floor(TIME * noise_hz) + phase * 977.0));

	ALBEDO = vec3(0.0);
	ALPHA = clamp(roll + flicker + noise_depth * snow, 0.0, 1.0);
}
"""

## One Shader per imported GLB rather than one per material: the five club
## materials would otherwise compile five identical pipelines.
var _motion_shader: Shader = null

## SHUTTERS (0.127.0) -- screens that run. The walker, 2026-10-02: the lit
## screens are "just fixed with nothing dynamic/alive about them". Zoo 1.45.0
## stands black quads a hair proud of a lit screen, each over one part of its
## picture -- a dealt card, a line that takes its turn -- on a material of this
## name, exported fully transparent, with a schedule in the quad's UV sets:
##
##     UV  = (open_from, open_to)   fractions of the period
##     UV2 = (period_s, phase_s)
##
## The shutter is ABSENT while fract((TIME + phase_s) / period_s + instance)
## is in [open_from, open_to) and its CLOSED COLOUR otherwise: the base colour
## of the placeholder material Zoo exports, which is the screen's own
## background -- a hidden card is empty screen. (Black was the first cut and
## read as holes in the poker's blue tube.) The name BEGINS `SHUTTER_MATERIAL`
## and ends in that colour.
##
## THE INSTANCE TERM IS PER NODE, from NODE_POSITION_WORLD, as the CRT pass's
## is: two cabinets side by side do not deal in step, and every shutter of one
## cabinet is one mesh on one node, so one cabinet's cards still come up in
## order.
const SHUTTER_MATERIAL: String = "M_Shutter_Screen"

const SHUTTER_SHADER: String = """
shader_type spatial;
render_mode unshaded, blend_mix, depth_draw_never, cull_back,
	shadows_disabled, fog_disabled;

uniform vec3 closed_color : source_color = vec3(0.0);

float shutter_hash(float x) {
	return fract(sin(x) * 43758.5453123);
}

void fragment() {
	float inst = shutter_hash(dot(NODE_POSITION_WORLD, vec3(12.9898, 78.233, 37.719)));
	float t = fract((TIME + UV2.y) / max(UV2.x, 0.001) + inst);
	float open = step(UV.x, t) * (1.0 - step(UV.y, t));
	ALBEDO = closed_color;
	ALPHA = 1.0 - open;
}
"""

## One Shader per imported GLB and one ShaderMaterial per placeholder: every
## shutter reads its own schedule off its own vertices, and the only thing
## set per material is the closed colour.
var _shutter_shader: Shader = null
var _shutter_materials: Dictionary = {}


## TURNING PARTS (0.129.0) -- small things that move. The walker, 2026-10-02:
## "start with the roller grill". Zoo 1.55.0 builds a part that turns (the
## grill's rollers, its dogs) as a surface of its own, every vertex carrying
## the AXLE in its second UV set, in this engine's axes, and names the
## material for its axis and rate:
##
##     M_<species>_<kind>_turn_x36      36 degrees a second about +X
##     M_<species>_<kind>_turn_xn36     the other way
##
## The surface's own material is REPLACED by a shader that reproduces a flat
## material -- albedo times the vertex colour, roughness, metallic; Zoo keeps
## a turning kind off the skin library for exactly this, so there is no
## texture to carry -- and turns the vertices and their normals about the
## axle on the shader clock. No node moves, no script ticks, no draw is
## added here: the surface was one draw as a standard material and is one
## as a shader. The phase is per node from NODE_POSITION_WORLD, as the CRT
## pass's and the shutters' are, so two grills do not turn in step. A part
## whose name names no rate is left alone: only `_turn_` names are read.
const TURN_MARK: String = "_turn_"
const TURN_PATTERN: String = "_turn_([xyz])(n?)(\\d+)$"

const TURN_SHADER: String = """
shader_type spatial;
render_mode cull_back, depth_draw_opaque;

uniform vec4 albedo : source_color = vec4(1.0);
uniform float roughness : hint_range(0.0, 1.0) = 0.5;
uniform float metallic : hint_range(0.0, 1.0) = 0.0;
uniform float rate_rad_s = 0.0;
uniform int axis = 0;

float turn_hash(float x) {
	return fract(sin(x) * 43758.5453123);
}

vec2 turn_about(vec2 v, vec2 pivot, float c, float s) {
	vec2 q = v - pivot;
	return pivot + vec2(c * q.x - s * q.y, s * q.x + c * q.y);
}

void vertex() {
	// ONE PHASE PER PROP: two grills side by side are not in step, and every
	// roller of one grill shares its node and so its phase.
	float inst = turn_hash(dot(NODE_POSITION_WORLD, vec3(12.9898, 78.233, 37.719)));
	float a = rate_rad_s * TIME + inst * 6.2831853;
	float c = cos(a);
	float s = sin(a);
	// the axle, in model space, from the second UV set: the two coordinates
	// of the axis in the plane the part turns in
	vec2 pivot = UV2;
	if (axis == 0) {
		VERTEX.yz = turn_about(VERTEX.yz, pivot, c, s);
		NORMAL.yz = turn_about(NORMAL.yz, vec2(0.0), c, s);
	} else if (axis == 1) {
		VERTEX.zx = turn_about(VERTEX.zx, pivot, c, s);
		NORMAL.zx = turn_about(NORMAL.zx, vec2(0.0), c, s);
	} else {
		VERTEX.xy = turn_about(VERTEX.xy, pivot, c, s);
		NORMAL.xy = turn_about(NORMAL.xy, vec2(0.0), c, s);
	}
}

void fragment() {
	ALBEDO = albedo.rgb * COLOR.rgb;
	ROUGHNESS = roughness;
	METALLIC = metallic;
}
"""

var _turn_shader: Shader = null
var _turn_materials: Dictionary = {}
var _turn_re: RegEx = null

## THE CHURN (0.129.0). The walker, 2026-10-02: "i want some motion on the
## slurpee stuff too". Zoo 1.55.0's slush tile is the flavour and its ice;
## the diagonal bands it used to paint are drawn HERE, moving: a pass over
## the barrel's glow surface, a hair proud like the CRT pass, that darkens
## the same diagonal (three bands round, one and a half up; 1.15.0's
## `(x // 2 + y // 4) % 16`, the dark band two steps of sixteen) and walks it
## round the barrel once every CHURN_PERIOD_S. The facets say where they are
## round the barrel in their second UV set -- (u round, v up), both 0..1 --
## and every other corner of the glow surface carries v = 2, which this
## pass reads as "not slush" and discards.
##
## DARKENS ONLY, for the CRT pass's reason: ALBEDO is black and the blend is
## mix, so the barrel is multiplied by (1 - ALPHA), and a barrel Lux has cut
## the power to -- emission zero, black -- stays black under it. The light
## band the tile used to paint is what that costs; a pass that could lighten
## would glow on a dead machine. The base material is NOT replaced, so Lux's
## binder still finds the `_Face` it cuts. Cost: one draw a slush machine,
## the pass over its one glow surface, priced in this version's changelog.
const CHURN_PREFIX: String = "M_Slush_"
const CHURN_SUFFIX: String = "_Face"
const CHURN_PERIOD_S: float = 6.0
const CHURN_BAND_DARK: float = 0.42
## 2/16 painted; 3/16 moving, because a band two steps wide at 96 texels
## is four pixels and vanishes under motion at a metre.
const CHURN_BAND_FRAC: float = 3.0 / 16.0

const CHURN_SHADER: String = """
shader_type spatial;
render_mode unshaded, blend_mix, depth_draw_never, cull_back,
	shadows_disabled, fog_disabled;

uniform float period_s = 6.0;
uniform float band_dark = 0.42;
uniform float band_frac = 0.1875;
uniform float proud_m = 0.002;

void vertex() {
	VERTEX += NORMAL * proud_m;
}

float churn_hash(float x) {
	return fract(sin(x) * 43758.5453123);
}

void fragment() {
	// not a churn facet: the cap, the topper, the panels
	if (UV2.y > 1.5) {
		discard;
	}
	float inst = churn_hash(dot(NODE_POSITION_WORLD, vec3(12.9898, 78.233, 37.719)));
	// three bands round and one and a half up, walking once round a period
	float b = fract(3.0 * UV2.x + 1.5 * UV2.y - 3.0 * TIME / period_s + inst);
	float band = step(0.5, b) * (1.0 - step(0.5 + band_frac, b));
	ALBEDO = vec3(0.0);
	ALPHA = band * band_dark;
}
"""

var _churn_shader: Shader = null

## THE REGISTER'S DISPLAY HAD A FLICKER (0.127.0) AND DOES NOT (0.128.0).
## It was the CRT pass's overlay under `M_Register_<art>_Face` with no roll
## and no snow, depth 0.07. Kept here because it is cheaper to keep than to
## rediscover: measured, the display's green swung 5.3 % between its
## brightest and dimmest frame, the pass cost the register one more draw, and
## it never reached the tills on store and bar counters, whose material is
## `M_Counter_VFD_<art>_Face`. The walker's call: off, everywhere.


func _post_import(scene: Node) -> Object:
	var base: String = get_source_file().get_file()
	# EVERY GLB: a far wall shimmers into moire without a mip chain, and props
	# (a car, a container) are seen at distance as much as kit walls are.
	var mipped: int = _mip_chains(scene, {})
	if mipped > 0:
		print("[worldskin] %s  %d texture(s) given a mip chain" % [base, mipped])
	# EVERY GLB, kit or not: the glass is in props (teller line, bus shelter,
	# car) as much as in windows.
	var glass: int = _glass_casts_no_shadow(scene, {})
	if glass > 0:
		print("[worldskin] %s  %d blended material(s) moved out of the shadow pass"
			% [base, glass])
	# EVERY GLB. A lit CRT face arrives in a prop GLB, which the kit/non-kit
	# branch below returns early for, so this cannot sit after it.
	var crt: int = _crt_motion(scene, {})
	if crt > 0:
		print("[worldskin] %s  %d CRT face(s) given a motion pass" % [base, crt])
	# EVERY GLB, and before the kit branch for the CRT pass's reason: a
	# shutter arrives in a prop GLB.
	var shut: int = _shutters(scene)
	if shut > 0:
		print("[worldskin] %s  %d shutter surface(s) given their clock" % [base, shut])
	# EVERY GLB, before the kit branch for the same reason: a turning part
	# and a churning barrel arrive in prop GLBs.
	var turned: int = _turning_parts(scene)
	if turned > 0:
		print("[worldskin] %s  %d turning surface(s) given their axle" % [base, turned])
	var churned: int = _churn_passes(scene, {})
	if churned > 0:
		print("[worldskin] %s  %d churn surface(s) given their bands" % [base, churned])
	var is_kit: bool = false
	for p in KIT_PREFIXES:
		if base.begins_with(p):
			is_kit = true
	# EVERY GLB THAT IS AN OBJECT RATHER THAN A TILE: a car, a container, a
	# chair, a lamp. Zoo's wear and form shading ride COLOR_0 and nothing
	# drew them.
	if not is_kit and not _is_tiled(base):
		var vc: Array = _vertex_colour_albedo(scene)
		if int(vc[0]) + int(vc[1]) + int(vc[2]) > 0:
			print("[worldskin] %s  %d material(s) draw vertex colour, %d all-white left off, %d with a surface lacking colours left off"
				% [base, int(vc[0]), int(vc[1]), int(vc[2])])
	if not is_kit:
		if base.begins_with(BASE_PREFIX):
			var n: Dictionary = _skin_stairs(scene, get_source_file().get_base_dir())
			print("[worldskin] %s  stairs: %d flight surface(s) skinned on %d mesh(es), %d mesh(es) left flat%s"
				% [base, int(n["flight_surfaces"]), int(n["flight_meshes"]),
					int(n["unskinned_meshes"]), String(n["note"])])
			var sl: Dictionary = _skin_slabs(scene, get_source_file().get_base_dir())
			print("[worldskin] %s  slabs: %d surface(s) skinned on %d mesh(es), %d mesh(es) left flat%s"
				% [base, int(sl["slab_surfaces"]), int(sl["slab_meshes"]),
					int(sl["unskinned_meshes"]), String(sl["note"])])
			return scene
		print("[worldskin] %s  not a kit module, left alone" % base)
		return scene
	var seen: Dictionary = {}
	var changed: int = 0
	var no_density: int = 0
	var counts: Array = _apply(scene, seen)
	changed = counts[0]
	no_density = counts[1]
	print("[worldskin] %s  %d material(s) world-projected, %d without a UV density"
		% [base, changed, no_density])
	return scene


## Every texture on an imported material gets a mip chain.
##
## THE KIT'S TEXTURES HAD NONE. The export pins `gltf/embedded_image_handling=3`
## (Embed as Uncompressed -- `packages/exporting/export.py`, chosen for ship size),
## and an embedded uncompressed image keeps no mipmaps. Measured by headless
## readback on cold run 9051's walk copy: 138 of 138 metal-skin surfaces ask
## for TEXTURE_FILTER_NEAREST_WITH_MIPMAPS and carry `get_mipmap_count() == 0`,
## so a distant pixel samples one full-resolution texel among several of a
## corrugated wall's 5 cm ribs, and the ribs and the pixel grid beat into moire
## bands (the walker, cold run 9052: the far end of a corrugated wall; roadmap
## 89 is the same defect reached through a different setting).
##
## MEASURED as an A/B on two copies of that walk copy, same station, the only
## difference this pass: mean |Laplacian| over the corrugated wall 22.32 -> 12.58
## and the arcs gone in the frame; a grazing station elsewhere 9.40 -> 9.40. The
## filter stays NEAREST, so a texture up close is exactly as Pixelcoat drew it.
## Normal maps renormalise their mips. Cost: the import cache, about a third
## more texture memory; the shipped package is unchanged.
func _mip_chains(n: Node, seen: Dictionary) -> int:
	var count: int = 0
	var mi: MeshInstance3D = n as MeshInstance3D
	if mi != null and mi.mesh != null:
		for i in range(mi.mesh.get_surface_count()):
			var bm: BaseMaterial3D = mi.mesh.surface_get_material(i) as BaseMaterial3D
			if bm == null or seen.has(bm.get_instance_id()):
				continue
			seen[bm.get_instance_id()] = true
			var a: Texture2D = _with_mips(bm.albedo_texture, false)
			if a != bm.albedo_texture:
				bm.albedo_texture = a
				count += 1
			var nm: Texture2D = _with_mips(bm.normal_texture, true)
			if nm != bm.normal_texture:
				bm.normal_texture = nm
				count += 1
			var r: Texture2D = _with_mips(bm.roughness_texture, false)
			if r != bm.roughness_texture:
				bm.roughness_texture = r
				count += 1
	for c in n.get_children():
		count += _mip_chains(c, seen)
	return count


func _with_mips(tex: Texture2D, normal_map: bool) -> Texture2D:
	if tex == null:
		return tex
	var img: Image = tex.get_image()
	if img == null or img.has_mipmaps():
		return tex
	img = img.duplicate()
	if img.is_compressed():
		img.decompress()
	img.generate_mipmaps(normal_map)
	return ImageTexture.create_from_image(img)


## Blended glass stops casting an opaque shadow.
##
## Godot's glTF importer maps alphaMode BLEND to TRANSPARENCY_ALPHA_DEPTH_PRE_PASS,
## and a depth-prepass material is drawn into the shadow map as if it were
## solid. MEASURED in GL Compatibility (Godot 4.7, RTX 2060) with a delco_1997
## window module laid flat under a shadowed DirectionalLight3D, ground
## luminance under the pane over open ground:
##
##     opaque pane (Pixelcoat 0.39.0 glass)                  0.463
##     blended pane, as imported (ALPHA_DEPTH_PRE_PASS)      0.463
##     blended pane, hidden (the dial check)                 1.000
##     blended pane, cast_shadow OFF                         1.000
##     blended pane, TRANSPARENCY_ALPHA                      1.000
##
## So a see-through window still threw a window-shaped shadow into the room it
## was supposed to light. The material is changed rather than the mesh's
## `cast_shadow`, for the reason the header gives for world projection: one
## edit to the shared material at import, not a setting per placement. On the
## same stage with the sun's shadow switched off, the two transparency modes
## render byte-identical frames (0 of 360,000 pixels differ), so there the
## switch changes the shadow and not the pane. That is one camera over one
## flat pane; self-overlapping glass (a car's greenhouse) is where a depth
## prepass could matter for sorting, and it was not measured.
func _glass_casts_no_shadow(n: Node, seen: Dictionary) -> int:
	var changed: int = 0
	var mi: MeshInstance3D = n as MeshInstance3D
	if mi != null and mi.mesh != null:
		for i in range(mi.mesh.get_surface_count()):
			var bm: BaseMaterial3D = mi.mesh.surface_get_material(i) as BaseMaterial3D
			if bm == null or seen.has(bm.get_instance_id()):
				continue
			seen[bm.get_instance_id()] = true
			if bm.transparency == BaseMaterial3D.TRANSPARENCY_ALPHA_DEPTH_PRE_PASS:
				bm.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
				changed += 1
	for c in n.get_children():
		changed += _glass_casts_no_shadow(c, seen)
	return changed


## An object's vertex colour multiplies its albedo, as Zoo authored it.
##
## Zoo bakes wear, and on some species form shading, into COLOR_0 and says to
## draw it with "Vertex Color > Use as Albedo" (its README, and
## `bpylayer/materials.py`). Godot 4.7's glTF importer never sets that flag.
## MEASURED by headless readback on walk 9052_rain: 0 of 1,650 imported
## BaseMaterial3D surfaces that carry COLOR_0 draw it -- all 181 cover
## surfaces among them, every car, container and box truck -- so baking a
## container's rib shading into vertex colour moved nothing in the frame (Zoo
## 0.82.0 records it).
##
## PER MATERIAL, decided over every surface that wears it. On when some
## surface under it carries a vertex darker than VERTEX_WHITE; left off when
## every vertex is white (the multiply is 1.0 and the flag would change
## nothing but the material) and when any surface wearing it has no colour
## array at all, which this does not assume draws as white.
##
## NOT ON A TILE. The caller skips the kit and TILED_PREFIXES / _SUFFIXES.
## Zoo computes wear per module, so on a module laid edge to edge it repeats
## per module by construction: measured on a delco elevation (Zoo 0.54.0,
## roadmap 84), turning it on multiplied the 2 m module signature 3.8x. A
## car or a chair is not laid against a copy of itself. Floors, ceilings,
## roofs and Patina's edge strips were not measured either way; they are
## kept off on the kit's evidence because they are built the same way.
##
## Returns [turned on, all-white left off, colour array missing left off].
func _vertex_colour_albedo(scene: Node) -> Array:
	var by_mat: Dictionary = {}
	_collect_vertex_colour(scene, by_mat)
	var on: int = 0
	var white: int = 0
	var missing: int = 0
	for key in by_mat:
		var e: Dictionary = by_mat[key]
		if bool(e["missing"]):
			missing += 1
			continue
		if not bool(e["tinted"]):
			white += 1
			continue
		var bm: BaseMaterial3D = e["mat"]
		bm.vertex_color_use_as_albedo = true
		on += 1
	return [on, white, missing]


func _collect_vertex_colour(n: Node, by_mat: Dictionary) -> void:
	var mi: MeshInstance3D = n as MeshInstance3D
	if mi != null and mi.mesh != null:
		for i in range(mi.mesh.get_surface_count()):
			var bm: BaseMaterial3D = mi.mesh.surface_get_material(i) as BaseMaterial3D
			if bm == null:
				continue
			var key: int = bm.get_instance_id()
			if not by_mat.has(key):
				by_mat[key] = {"mat": bm, "tinted": false, "missing": false}
			var e: Dictionary = by_mat[key]
			var arrays: Array = mi.mesh.surface_get_arrays(i)
			var cols: PackedColorArray = PackedColorArray()
			if arrays.size() > Mesh.ARRAY_COLOR and arrays[Mesh.ARRAY_COLOR] != null:
				cols = arrays[Mesh.ARRAY_COLOR]
			if cols.is_empty():
				e["missing"] = true
			elif _has_tint(cols):
				e["tinted"] = true
	for c in n.get_children():
		_collect_vertex_colour(c, by_mat)


func _has_tint(cols: PackedColorArray) -> bool:
	for col in cols:
		if col.r < VERTEX_WHITE or col.g < VERTEX_WHITE or col.b < VERTEX_WHITE:
			return true
	return false


## A lit CRT face gets a darkening motion pass hung off its `next_pass`.
##
## The design, the measurement that settled it and the constants are all in the
## CRT MOTION block at the top of this file. What happens here: the screen's own
## StandardMaterial3D is not touched at all -- no texture, no emission, no
## energy, no transparency -- and a ShaderMaterial is attached under it.
##
## IDEMPOTENT on a re-import: a face that already carries a next_pass is left
## alone rather than given a second one.
func _crt_motion(n: Node, seen: Dictionary) -> int:
	var count: int = 0
	var mi: MeshInstance3D = n as MeshInstance3D
	if mi != null and mi.mesh != null:
		for i in range(mi.mesh.get_surface_count()):
			var bm: BaseMaterial3D = mi.mesh.surface_get_material(i) as BaseMaterial3D
			if bm == null or seen.has(bm.get_instance_id()):
				continue
			seen[bm.get_instance_id()] = true
			if not _is_crt_face(String(bm.resource_name)):
				continue
			if bm.next_pass != null:
				continue
			bm.next_pass = _motion_material(bm)
			count += 1
	for c in n.get_children():
		count += _crt_motion(c, seen)
	return count


## All three tests, because no one of them is the contract on its own: the
## vending machine's lit panel ends `_Face`, and Zoo's dark stand-set glass
## carries `CRT` without being lit.
func _is_crt_face(nm: String) -> bool:
	return nm.begins_with(CRT_FACE_PREFIX) and nm.ends_with(CRT_FACE_SUFFIX) \
		and nm.contains(CRT_FACE_MARK)


func _motion_material(bm: BaseMaterial3D) -> ShaderMaterial:
	if _motion_shader == null:
		_motion_shader = Shader.new()
		_motion_shader.code = MOTION_SHADER
	var sm: ShaderMaterial = ShaderMaterial.new()
	sm.shader = _motion_shader
	sm.resource_name = String(bm.resource_name) + "_motion"
	# The snow's grain is ONE PICTURE PIXEL, read off the picture rather than
	# assumed, so a screen Zoo paints at another size grains at its own scale.
	var px: Vector2 = PICTURE_PX_FALLBACK
	if bm.albedo_texture != null:
		px = Vector2(float(bm.albedo_texture.get_width()),
			float(bm.albedo_texture.get_height()))
	sm.set_shader_parameter("picture_pixels", px)
	sm.set_shader_parameter("roll_period_s", ROLL_PERIOD_S)
	sm.set_shader_parameter("roll_band_frac", ROLL_BAND_FRAC)
	sm.set_shader_parameter("roll_depth", ROLL_DEPTH)
	sm.set_shader_parameter("roll_dir", ROLL_UP)
	sm.set_shader_parameter("flicker_depth", FLICKER_DEPTH)
	sm.set_shader_parameter("flicker_hz_a", FLICKER_HZ_A)
	sm.set_shader_parameter("flicker_hz_b", FLICKER_HZ_B)
	sm.set_shader_parameter("noise_depth", NOISE_DEPTH)
	sm.set_shader_parameter("noise_hz", NOISE_HZ)
	sm.set_shader_parameter("proud_m", SCREEN_PROUD_M)
	return sm


## Every surface wearing Zoo's shutter material gets the one shader that reads
## its schedule. The surface's own material is REPLACED, which the CRT pass
## must not do and this may: a shutter is not a lit face, Lux's power cut has
## no business with it, and its exported material is a transparent
## placeholder with nothing to keep.
##
## IDEMPOTENT on a re-import: a surface already wearing the shader is left.
func _shutters(n: Node) -> int:
	var count: int = 0
	var mi: MeshInstance3D = n as MeshInstance3D
	if mi != null and mi.mesh != null:
		for i in range(mi.mesh.get_surface_count()):
			var mat: Material = mi.mesh.surface_get_material(i)
			if mat == null or not String(mat.resource_name).begins_with(SHUTTER_MATERIAL):
				continue
			var bm: BaseMaterial3D = mat as BaseMaterial3D
			if bm == null:
				continue                      # already the shader: a re-import
			mi.mesh.surface_set_material(i, _shutter_shader_material(bm))
			count += 1
	for c in n.get_children():
		count += _shutters(c)
	return count


func _shutter_shader_material(bm: BaseMaterial3D) -> ShaderMaterial:
	var key: int = bm.get_instance_id()
	if _shutter_materials.has(key):
		return _shutter_materials[key] as ShaderMaterial
	if _shutter_shader == null:
		_shutter_shader = Shader.new()
		_shutter_shader.code = SHUTTER_SHADER
	var sm: ShaderMaterial = ShaderMaterial.new()
	sm.shader = _shutter_shader
	sm.resource_name = String(bm.resource_name)
	var c: Color = bm.albedo_color
	sm.set_shader_parameter("closed_color", Color(c.r, c.g, c.b, 1.0))
	_shutter_materials[key] = sm
	return sm


## Every surface whose material is named for a rate gets the shader that
## turns it. The surface's own material is REPLACED (a second pass cannot
## move the first) by a shader carrying the flat material's own numbers.
## IDEMPOTENT on a re-import: a surface already wearing the shader is left.
func _turning_parts(n: Node) -> int:
	var count: int = 0
	var mi: MeshInstance3D = n as MeshInstance3D
	if mi != null and mi.mesh != null:
		for i in range(mi.mesh.get_surface_count()):
			var mat: Material = mi.mesh.surface_get_material(i)
			if mat == null or not String(mat.resource_name).contains(TURN_MARK):
				continue
			var bm: BaseMaterial3D = mat as BaseMaterial3D
			if bm == null:
				continue                      # already the shader: a re-import
			var spec: Array = _turn_spec(String(bm.resource_name))
			if spec.is_empty():
				push_warning("[worldskin] %s carries %s but names no axis and rate; left alone"
					% [bm.resource_name, TURN_MARK])
				continue
			mi.mesh.surface_set_material(i, _turn_material(bm, int(spec[0]), float(spec[1])))
			count += 1
	for c in n.get_children():
		count += _turning_parts(c)
	return count


## ``[axis, degrees a second]`` off a material name, or ``[]``: `_turn_x36`
## is 36 degrees a second about +X, `_turn_xn36` the other way.
func _turn_spec(nm: String) -> Array:
	if _turn_re == null:
		_turn_re = RegEx.new()
		_turn_re.compile(TURN_PATTERN)
	var m: RegExMatch = _turn_re.search(nm)
	if m == null:
		return []
	var axis: int = {"x": 0, "y": 1, "z": 2}[m.get_string(1)]
	var deg: float = float(m.get_string(3))
	if m.get_string(2) == "n":
		deg = -deg
	return [axis, deg]


func _turn_material(bm: BaseMaterial3D, axis: int, deg_s: float) -> ShaderMaterial:
	var key: int = bm.get_instance_id()
	if _turn_materials.has(key):
		return _turn_materials[key] as ShaderMaterial
	if _turn_shader == null:
		_turn_shader = Shader.new()
		_turn_shader.code = TURN_SHADER
	var sm: ShaderMaterial = ShaderMaterial.new()
	sm.shader = _turn_shader
	sm.resource_name = String(bm.resource_name)
	# the flat material's own numbers; the vertex colour is multiplied in
	# whatever the material said, because a roller's grease and a dog's
	# colour ride it (Zoo's `tint_wear`)
	sm.set_shader_parameter("albedo", Color(bm.albedo_color.r, bm.albedo_color.g, bm.albedo_color.b, 1.0))
	sm.set_shader_parameter("roughness", bm.roughness)
	sm.set_shader_parameter("metallic", bm.metallic)
	sm.set_shader_parameter("rate_rad_s", deg_to_rad(deg_s))
	sm.set_shader_parameter("axis", axis)
	_turn_materials[key] = sm
	return sm


## Every slush glow face gets the churn pass as its next_pass; the face's
## own material is kept (Lux cuts it). Once per material, once per import.
func _churn_passes(n: Node, seen: Dictionary) -> int:
	var count: int = 0
	var mi: MeshInstance3D = n as MeshInstance3D
	if mi != null and mi.mesh != null:
		for i in range(mi.mesh.get_surface_count()):
			var bm: BaseMaterial3D = mi.mesh.surface_get_material(i) as BaseMaterial3D
			if bm == null or seen.has(bm.get_instance_id()):
				continue
			seen[bm.get_instance_id()] = true
			var nm: String = String(bm.resource_name)
			if not (nm.begins_with(CHURN_PREFIX) and nm.ends_with(CHURN_SUFFIX)):
				continue
			if bm.next_pass != null:
				continue
			bm.next_pass = _churn_material(bm)
			count += 1
	for c in n.get_children():
		count += _churn_passes(c, seen)
	return count


func _churn_material(bm: BaseMaterial3D) -> ShaderMaterial:
	if _churn_shader == null:
		_churn_shader = Shader.new()
		_churn_shader.code = CHURN_SHADER
	var sm: ShaderMaterial = ShaderMaterial.new()
	sm.shader = _churn_shader
	sm.resource_name = String(bm.resource_name) + "_churn"
	sm.set_shader_parameter("period_s", CHURN_PERIOD_S)
	sm.set_shader_parameter("band_dark", CHURN_BAND_DARK)
	sm.set_shader_parameter("band_frac", CHURN_BAND_FRAC)
	sm.set_shader_parameter("proud_m", SCREEN_PROUD_M)
	return sm


func _is_tiled(base: String) -> bool:
	for p in TILED_PREFIXES:
		if base.begins_with(p):
			return true
	for s in TILED_SUFFIXES:
		if base.ends_with(s):
			return true
	return false


func _apply(n: Node, seen: Dictionary) -> Array:
	var changed: int = 0
	var no_density: int = 0
	var mi: MeshInstance3D = n as MeshInstance3D
	if mi != null and mi.mesh != null:
		var mesh: Mesh = mi.mesh
		for i in range(mesh.get_surface_count()):
			var mat: Material = mesh.surface_get_material(i)
			if mat == null:
				continue
			var bm: BaseMaterial3D = mat as BaseMaterial3D
			if bm == null:
				continue
			var key: int = bm.get_instance_id()
			if seen.has(key):
				continue
			seen[key] = true
			var density: float = _uv_density(mesh, i)
			if density <= 0.0:
				no_density += 1
				continue
			# The AUTHORED tile period, which is Pixelcoat's
			# `meters_per_tile` arriving as the glTF
			# `KHR_texture_transform` scale. Read it before overwriting it:
			# `uv1_scale` is where the importer put it, and dropping it
			# rendered the whole library at one density. See `_uv_density`.
			var authored: float = bm.uv1_scale.x
			if authored <= 0.0:
				authored = 1.0
			var world: float = density * authored
			bm.uv1_triplanar = true
			bm.uv1_world_triplanar = true
			bm.uv1_scale = Vector3(world, world, world)
			changed += 1
	for c in n.get_children():
		var sub: Array = _apply(c, seen)
		changed += int(sub[0])
		no_density += int(sub[1])
	return [changed, no_density]


## Texels per metre, read off the surface's own vertices and UVs.
##
## THE SCALE IS MEASURED, NOT GUESSED, and the guess was wrong once already.
## The first runtime version multiplied by Zoo's `texel=1.2` assuming the
## material still carried Pixelcoat's tiling as a UV scale, and the stone came
## out twice its proper size. Multiplying by a CONSTANT is what was wrong
## there; the caller now multiplies by the material's own authored
## `uv1_scale`, which is a different operation and not that mistake.
##
## REFUTED 2026-09-06, and the refutation is kept because it is what this
## function's result means. The paragraph above used to continue "because
## Godot's glTF importer bakes `KHR_texture_transform` into the mesh UVs", and
## concluded that re-applying the measured density alone "reproduces the old
## density exactly". BOTH HALVES ARE FALSE. If the transform were baked into
## the mesh UVs, this function would return a DIFFERENT number for skins with
## different tile periods. Measured on `precinct_yard_001`, four skins whose
## transforms are 0.4, 0.6667, 0.3333 and 1.0 -- concrete at 2.5 m, metal at
## 1.5 m, drywall at 3.0 m, glass at 1.0 m -- every one returned 1.2000, which
## is Zoo's texel constant and does not vary with the field. The importer puts
## the transform in the MATERIAL's `uv1_scale`, not in the mesh.
##
## So what this returns is the mesh's own UV density and NOT the on-mesh
## density, which is that times the material's `uv1_scale`. Setting
## `uv1_scale` to this value alone discarded every skin's authored tile period
## and rendered the whole library at one density -- roadmap 104, shipped in
## every world-projected package from level_factory 0.57.0 until it was found.
##
## Median rather than mean: a bevelled box carries degenerate edges, and one of
## those in a mean drags the whole material to the wrong scale.
func _uv_density(mesh: Mesh, surface: int) -> float:
	var arrays: Array = mesh.surface_get_arrays(surface)
	if arrays.size() <= Mesh.ARRAY_TEX_UV:
		return 0.0
	var verts: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
	var uvs: PackedVector2Array = arrays[Mesh.ARRAY_TEX_UV]
	if verts.size() < 2 or uvs.size() != verts.size():
		return 0.0
	var ratios: Array = []
	var limit: int = mini(verts.size() - 1, 400)
	for i in range(limit):
		var dp: float = verts[i].distance_to(verts[i + 1])
		var du: float = uvs[i].distance_to(uvs[i + 1])
		if dp > 0.001 and du > 0.00001:
			ratios.append(du / dp)
	if ratios.is_empty():
		return 0.0
	ratios.sort()
	return float(ratios[ratios.size() / 2])

## Skin the greybox base's stairs with packs the building already loads, as
## world-projected as the walls beside them (roadmap 144).
##
## The stairs are boxes with NORMAL and POSITION only -- no UVs, so the kit
## pass above has no density to read and would skip them -- in Deli Counter's
## flat `gb_stair` and `gb_prop`. World triplanar needs no UVs at all: the
## texture is projected from world position, which is the whole reason it is
## the right tool for a surface nobody unwrapped.
##
## ONE PACK, AND IT DRESSES THE FLIGHT ONLY: the flight takes the floor family
## and a `stair_guard_*` mesh is counted and left alone, for the reasons
## written on `STAIR_FLIGHT_FAMILY` and `STAIR_GUARD_PREFIX` above.
##
## THE MATERIAL COMES FROM A KIT MODULE'S IMPORTED SCENE, NOT FROM A FILE.
## The first version looked for `*_concrete_*_albedo.png` under `art/zoo/`
## and worked on a walk copy that happened to carry loose PNGs; the cold-run
## export (LF 0.71.0, `_write_import_sidecars` mode 3) EMBEDS every texture
## in its GLB and ships no PNG at all, so on a real package that version
## skinned nothing and said so. A kit module's imported material carries its
## textures and the tile period the kit pass already resolved -- so a stair's
## texel density equals its neighbours' by construction.
##
## AND IT REFUSES OUT LOUD. A visual stair mesh this cannot find a pack for is
## counted and pushed as an error naming the base, because the failure this
## replaces was a `print` nobody read for five days while the level shipped
## yellow. Visual meshes only: `stair<n>col_*` and `*ramp*` are collision, and
## a base with no stair mesh at all is a no-op that says which it is.
##
## Returns {flight_surfaces, flight_meshes, guard_meshes, unskinned_meshes,
## note}. `guard_meshes` is a census, not work done: see `STAIR_GUARD_PREFIX`.
func _skin_stairs(scene: Node, base_dir: String) -> Dictionary:
	var out: Dictionary = {"flight_surfaces": 0, "flight_meshes": 0,
		"guard_meshes": 0, "unskinned_meshes": 0, "note": ""}
	# The census and the work use ONE definition of a visual stair mesh,
	# because two would drift: a null material counts instead of assigning.
	var present: Array = _assign_stairs(scene, null)
	var flights: int = int(present[2])
	out["guard_meshes"] = int(present[3])
	if flights == 0:
		out["note"] = ("; no flight mesh in this base, nothing to skin (%d guard mesh(es) instanced)"
			% int(present[3]))
		return out
	var art: String = base_dir.path_join("art").path_join("zoo")
	var dir := DirAccess.open(art)
	if dir == null:
		out["unskinned_meshes"] = flights
		out["note"] = "; NO art/zoo BESIDE THE BASE -- %d flight mesh(es) left in the greybox material" % flights
		push_error("[worldskin] %s%s" % [get_source_file(), String(out["note"])])
		return out
	var flight: Array = _family_material(art, dir, STAIR_FLIGHT_FAMILY, "stair_flight")
	if flight.is_empty():
		out["unskinned_meshes"] = flights
		# `%` binds tighter than `+`, so the formatted piece is built whole
		# before it is joined (the trap `tools/gdcheck.py` exists to catch).
		out["note"] = ("; NO MODULE UNDER art/zoo IN FAMILIES %s -- %d flight mesh(es) left in the greybox material"
			% [str(STAIR_FLIGHT_FAMILY), flights])
		push_error("[worldskin] %s%s" % [get_source_file(), String(out["note"])])
		return out
	var counts: Array = _assign_stairs(scene, flight[0] as Material)
	out["flight_surfaces"] = int(counts[0])
	out["flight_meshes"] = int(counts[1])
	out["unskinned_meshes"] = int(counts[4])
	out["note"] = "; flight from %s" % String(flight[1])
	if int(counts[3]) > 0:
		out["note"] += ("; %d stair_guard_* mesh(es) INSTANCED in the base and left alone -- the composer fills those slots"
			% int(counts[3]))
	return out


## A kit family's material: the first module of the first family that carries
## a textured material, in sort order. `part` names the half it dresses, so
## the duplicate is identifiable in a material list. Returns [] or
## [material, module file].
##
## No `breach_` exclusion is needed here and none is written: `breach_*` is
## its own family and cannot begin with `floor_`, `wall_` or `wallEnd_`. The
## 0.72.0 version needed one because it scanned all of `KIT_PREFIXES`.
func _family_material(art: String, dir: DirAccess, families: Array,
		part: String) -> Array:
	var files: PackedStringArray = dir.get_files()
	files.sort()
	for fam in families:
		for f in files:
			if not f.ends_with(".glb") or not f.begins_with(String(fam)):
				continue
			var ps: PackedScene = load(art.path_join(f)) as PackedScene
			if ps == null:
				continue
			var inst: Node = ps.instantiate()
			var m: BaseMaterial3D = _kit_material(inst)
			var dup: BaseMaterial3D = null
			if m != null:
				dup = m.duplicate()
			inst.free()
			if dup == null:
				continue
			dup.resource_name = "M_Skin_%s" % part
			if not dup.uv1_world_triplanar:
				# The module imported before the kit pass touched it: its
				# uv1_scale is still the authored tile period. World-project
				# it the way `_apply` does, at that period (the kit's meshes
				# measure a UV density of ~1.0, so world == authored to four
				# decimals).
				dup.uv1_triplanar = true
				dup.uv1_world_triplanar = true
			return [dup, f]
	return []


## The first textured material in an instanced kit module.
func _kit_material(n: Node) -> BaseMaterial3D:
	var mi: MeshInstance3D = n as MeshInstance3D
	if mi != null and mi.mesh != null:
		for i in range(mi.mesh.get_surface_count()):
			var bm: BaseMaterial3D = mi.mesh.surface_get_material(i) as BaseMaterial3D
			if bm != null and bm.albedo_texture != null:
				return bm
	for c in n.get_children():
		var m: BaseMaterial3D = _kit_material(c)
		if m != null:
			return m
	return null


## A mesh named for the stair that is drawn rather than collided with.
## `stair<n>col_*` and `stair<n>ramp_*` are Deli Counter's collision bodies.
func _is_visual_stair(nm: String) -> bool:
	return nm.begins_with(STAIR_PREFIX) and not nm.contains("col") \
		and not nm.contains("ramp")


## Assign the flight material. A null `flight_mat` counts the meshes it would
## have dressed as unskinned instead of assigning -- so a null call is the
## census `_skin_stairs` takes before it goes looking for a pack, and there is
## one definition of "a visual stair mesh" rather than two that can drift.
## A `stair_guard_*` mesh is counted and never assigned (`STAIR_GUARD_PREFIX`).
##
## Returns [flight_surfaces, flight_meshes, flight_seen, guard_seen,
## unskinned_meshes].
func _assign_stairs(n: Node, flight_mat: Material) -> Array:
	var fs: int = 0
	var fm: int = 0
	var seen: int = 0
	var guards: int = 0
	var flat: int = 0
	var mi: MeshInstance3D = n as MeshInstance3D
	if mi != null and mi.mesh != null and _is_visual_stair(String(mi.name)):
		if String(mi.name).begins_with(STAIR_GUARD_PREFIX):
			guards += 1
		else:
			seen += 1
			if flight_mat == null:
				flat += 1
			else:
				for i in range(mi.mesh.get_surface_count()):
					mi.mesh.surface_set_material(i, flight_mat)
					fs += 1
				fm += 1
	for c in n.get_children():
		var sub: Array = _assign_stairs(c, flight_mat)
		fs += int(sub[0])
		fm += int(sub[1])
		seen += int(sub[2])
		guards += int(sub[3])
		flat += int(sub[4])
	return [fs, fm, seen, guards, flat]


## Skin the greybox base's floor slabs, for the reasons written on
## `SLAB_PREFIX` above.
##
## Mirrors `_skin_stairs` deliberately, including refusing OUT LOUD: a base
## whose slabs this cannot dress ships bare grey around every ladder and
## stairwell in it, which is exactly the failure that reached the walker and
## exactly the kind that a `print` nobody reads does not stop.
##
## Returns {slab_surfaces, slab_meshes, unskinned_meshes, note}.
func _skin_slabs(scene: Node, base_dir: String) -> Dictionary:
	var out: Dictionary = {"slab_surfaces": 0, "slab_meshes": 0,
		"unskinned_meshes": 0, "note": ""}
	# The census and the work use ONE definition of a visual slab mesh: a null
	# material counts instead of assigning (see `_assign_stairs`).
	var present: Array = _assign_slabs(scene, null)
	var slabs: int = int(present[2])
	if slabs == 0:
		out["note"] = "; no visual slab in this base, nothing to skin"
		return out
	var art: String = base_dir.path_join("art").path_join("zoo")
	var dir := DirAccess.open(art)
	if dir == null:
		out["unskinned_meshes"] = slabs
		out["note"] = "; NO art/zoo BESIDE THE BASE -- %d slab mesh(es) left in the greybox material" % slabs
		push_error("[worldskin] %s%s" % [get_source_file(), String(out["note"])])
		return out
	var reveal: Array = _family_material(art, dir, SLAB_REVEAL_FAMILY, "slab_reveal")
	if reveal.is_empty():
		out["unskinned_meshes"] = slabs
		# `%` binds tighter than `+`, so the formatted piece is built whole
		# before it is joined (the trap `tools/gdcheck.py` exists to catch).
		out["note"] = ("; NO MODULE UNDER art/zoo IN FAMILIES %s -- %d slab mesh(es) left in the greybox material"
			% [str(SLAB_REVEAL_FAMILY), slabs])
		push_error("[worldskin] %s%s" % [get_source_file(), String(out["note"])])
		return out
	var counts: Array = _assign_slabs(scene, reveal[0] as Material)
	out["slab_surfaces"] = int(counts[0])
	out["slab_meshes"] = int(counts[1])
	out["unskinned_meshes"] = int(counts[3])
	out["note"] = "; reveal from %s" % String(reveal[1])
	return out


## A mesh named for a floor slab that is DRAWN rather than collided with.
func _is_visual_slab(nm: String) -> bool:
	return nm.begins_with(SLAB_PREFIX) and not nm.contains(SLAB_COLLISION_MARK)


## Assign the reveal material. A null `mat` counts the meshes it would have
## dressed as unskinned instead of assigning, so the census `_skin_slabs`
## takes before it goes looking for a pack and the work it does afterwards
## share one definition rather than two that can drift.
##
## Returns [slab_surfaces, slab_meshes, slab_seen, unskinned_meshes].
func _assign_slabs(n: Node, mat: Material) -> Array:
	var fs: int = 0
	var fm: int = 0
	var seen: int = 0
	var flat: int = 0
	var mi: MeshInstance3D = n as MeshInstance3D
	if mi != null and mi.mesh != null and _is_visual_slab(String(mi.name)):
		seen += 1
		if mat == null:
			flat += 1
		else:
			for i in range(mi.mesh.get_surface_count()):
				mi.mesh.surface_set_material(i, mat)
				fs += 1
			fm += 1
	for c in n.get_children():
		var sub: Array = _assign_slabs(c, mat)
		fs += int(sub[0])
		fm += int(sub[1])
		seen += int(sub[2])
		flat += int(sub[3])
	return [fs, fm, seen, flat]

