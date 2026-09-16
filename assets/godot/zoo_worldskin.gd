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
## What a stair wears: the building's own concrete pack, found beside the
## base under `art/zoo/` as the albedo Zoo copied next to a concrete kit
## module. The stairs are concrete in every 1990s hospital there is; a stair
## species with its own pack is the later, dearer answer.
const STAIR_KIND: String = "concrete"

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
			var n: Array = _skin_stairs(scene, get_source_file().get_base_dir())
			print("[worldskin] %s  %d stair surface(s) skinned on %d mesh(es)%s"
				% [base, int(n[0]), int(n[1]), String(n[2])])
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

## Skin the greybox base's stairs with the building's concrete, as
## world-projected as the walls beside them (roadmap 144).
##
## The stairs are boxes with NORMAL and POSITION only -- no UVs, so the kit
## pass above has no density to read and would skip them -- in Deli Counter's
## flat `gb_stair`. World triplanar needs no UVs at all: the texture is
## projected from world position, which is the whole reason it is the right
## tool for a surface nobody unwrapped.
##
## THE MATERIAL COMES FROM A KIT MODULE'S IMPORTED SCENE, NOT FROM A FILE.
## The first version looked for `*_concrete_*_albedo.png` under `art/zoo/`
## and worked on a walk copy that happened to carry loose PNGs; the cold-run
## export (LF 0.71.0, `_write_import_sidecars` mode 3) EMBEDS every texture
## in its GLB and ships no PNG at all, so on a real package that version
## skinned nothing and said so. A `wall_*` module's imported material is
## the concrete the walls wear, textures included, at the tile period the
## kit pass already resolved -- so the stair's texel density equals the
## wall's by construction. Visual meshes only: `stair<n>col_*` and `*ramp*`
## are collision.
##
## Returns [surfaces, meshes, note].
func _skin_stairs(scene: Node, base_dir: String) -> Array:
	var art: String = base_dir.path_join("art").path_join("zoo")
	var dir := DirAccess.open(art)
	if dir == null:
		return [0, 0, "; no art/zoo beside the base, stairs left alone"]
	var files: PackedStringArray = dir.get_files()
	files.sort()
	# A plain wall's module first; `breach_*` sorts earlier and wears the
	# BREACHED variant of the pack (the first run of the file-name version
	# put rubble edges on every stair).
	var modules: Array = []
	for f in files:
		if f.ends_with(".glb") and f.begins_with("wall_"):
			modules.append(f)
	for f in files:
		if f.ends_with(".glb") and not f.begins_with("wall_"):
			for p in KIT_PREFIXES:
				if f.begins_with(p) and not f.begins_with("breach_"):
					modules.append(f)
	var found: Array = []   # [material, module file]
	for f in modules:
		var ps: PackedScene = load(art.path_join(f)) as PackedScene
		if ps == null:
			continue
		var inst: Node = ps.instantiate()
		var m: BaseMaterial3D = _kit_material(inst, STAIR_KIND)
		if m != null:
			found = [m.duplicate(), f]
		inst.free()
		if not found.is_empty():
			break
	if found.is_empty():
		return [0, 0, "; no imported kit module wearing %s under art/zoo (import order?), stairs left alone" % STAIR_KIND]
	var mat: BaseMaterial3D = found[0]
	mat.resource_name = "M_Skin_%s_stairs" % STAIR_KIND
	var note: String = "; material from %s" % String(found[1])
	if not mat.uv1_world_triplanar:
		# The module imported before the kit pass touched it: its uv1_scale
		# is still the authored tile period. World-project it the way
		# `_apply` does, at that period (the kit's meshes measure a UV
		# density of ~1.0, so world == authored to four decimals).
		mat.uv1_triplanar = true
		mat.uv1_world_triplanar = true
		note += " (world-projected here; the module's own pass had not run)"
	var counts: Array = _assign_stairs(scene, mat)
	return [counts[0], counts[1], note]


## The first textured material of `kind` in an instanced kit module.
func _kit_material(n: Node, kind: String) -> BaseMaterial3D:
	var mi: MeshInstance3D = n as MeshInstance3D
	if mi != null and mi.mesh != null:
		for i in range(mi.mesh.get_surface_count()):
			var bm: BaseMaterial3D = mi.mesh.surface_get_material(i) as BaseMaterial3D
			if bm != null and bm.albedo_texture != null \
					and String(bm.resource_name).contains("_" + kind):
				return bm
	for c in n.get_children():
		var m: BaseMaterial3D = _kit_material(c, kind)
		if m != null:
			return m
	return null


func _assign_stairs(n: Node, mat: Material) -> Array:
	var surfaces: int = 0
	var meshes: int = 0
	var mi: MeshInstance3D = n as MeshInstance3D
	if mi != null and mi.mesh != null:
		var nm: String = String(mi.name)
		if nm.begins_with(STAIR_PREFIX) and not nm.contains("col") and not nm.contains("ramp"):
			for i in range(mi.mesh.get_surface_count()):
				mi.mesh.surface_set_material(i, mat)
				surfaces += 1
			meshes += 1
	for c in n.get_children():
		var sub: Array = _assign_stairs(c, mat)
		surfaces += int(sub[0])
		meshes += int(sub[1])
	return [surfaces, meshes]

