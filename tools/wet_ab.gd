extends SceneTree

## PRICE A WET `next_pass` ON THE SCENE A PACKAGE ACTUALLY RUNS.
##
## Roadmap 157 slice 2, and `docs/proposals/RAIN_WETNESS.md` item 2: "cost of a
## wet `next_pass` over the exterior surfaces of a real package, the way the CRT
## pass was priced: on/off, several stations, with the no-rain control."
##
## THIS MEASURES A COST, NOT A LOOK. The fragment below is deliberately the
## cheap shape the proposal calls the default -- a per-pixel darken and sheen on
## surfaces already being drawn, with no screen read, no depth read and no
## per-frame CPU. What a wet Delco street should LOOK like is Pixelcoat's
## grammar to author and the walker's to judge; nothing here is that. What this
## answers is the only question that can gate it: what does one extra raster of
## the same triangles cost on the renderer packages ship on.
##
## THE INSTRUMENT PROVES ITSELF, and this is the part the CRT measurement had to
## learn the hard way -- its first render probe reported "pixel-identical" from
## frames that were 99.7% black. A `next_pass` rasterises the SAME triangles a
## second time, so DRAW CALLS MUST RISE between the dry and wet arms. If they do
## not, the pass did not attach and no frame-time figure in the row means
## anything. The runner refuses such a row rather than tabulating it.
##
## A WINDOW IS OPENED ON PURPOSE. Headless draws nothing, so every
## `RENDERING_INFO_*` counter reads 0 and no frame time exists to measure. The
## run quits itself.
##
## Usage:
##   godot --path <pkg> --script res://wet_ab.gd -- <out.json> <arm> <wetness>
##     arm: dry | wet_ground | wet | wet_all

## THE SAME FRAME THE OCCLUSION FIGURES WERE TAKEN IN. Fill cost scales
## with pixels, so a wet figure measured at a different window size is
## not comparable to the numbers this repo already published.
const W := 1280
const H := 720
const EYE := 1.6
const WARMUP := 120
const SAMPLE := 300

## The cheap shape. No `hint_screen_texture`, no `hint_depth_texture`: both are
## the expensive reference (B) in the proposal and neither is measured here.
const WET_SHADER := """
shader_type spatial;
render_mode blend_mix, depth_draw_never, cull_back, specular_schlick_ggx;

// LIFTED OFF ITS OWN SURFACE, or it is not drawn at all. A next_pass
// rasterises the same triangles at the same depth the base pass already
// wrote, and GL Compatibility's depth test rejects it -- measured by
// `assets/godot/zoo_worldskin.gd` in the club at 1600x900: blend_mix with
// depth_draw_never and no offset produced NO drawn pixels. 2 mm along the
// normal is the value that file settled on, the largest of four that changed
// nothing about occlusion (39.53 from behind against a 39.55 baseline) while
// leaving least residue at a curved silhouette.
//
// The first version of THIS probe had no offset, so its 2026-09-24 figures
// priced submission with a fragment that never ran.
const float PROUD_M = 0.002;

uniform float wetness : hint_range(0.0, 1.0) = 0.85;
uniform float sky_bias : hint_range(0.0, 8.0) = 2.0;

varying vec3 world_n;

void vertex() {
	world_n = (MODEL_MATRIX * vec4(NORMAL, 0.0)).xyz;
	// MODEL space, not view space. `zoo_worldskin.gd` records biasing
	// VERTEX.z on the assumption vertex() runs in view space, which drew the
	// overlay from behind the set at every magnitude tried. Along the normal.
	VERTEX += NORMAL * PROUD_M;
}

void fragment() {
	// RAIN FALLS DOWNWARD, so a wet response belongs on what faces the sky.
	// A wall gets a little, a road gets all of it, a soffit gets none -- and
	// this is the whole of the "is it raining here" term in the cost probe.
	// The shipped version would take that from Lux's rain colliders instead,
	// which already keep interiors dry (Lux 0.35.0).
	float up = clamp(dot(normalize(world_n), vec3(0.0, 1.0, 0.0)), 0.0, 1.0);
	float w = wetness * pow(up, sky_bias);
	ALBEDO = vec3(0.0);
	ALPHA = w * 0.35;
	ROUGHNESS = 0.08;
	SPECULAR = 0.9;
	METALLIC = 0.0;
}
"""


## THE DRIP FRAGMENT, priced rather than guessed at -- and read from the file
## that ships it, `assets/godot/rain_drip.gdshader`, so the text this probe
## measured and the text a package runs cannot differ. It is staged into the
## arm by `wet_ab_run.py` beside the atlas; a missing file is a refusal below,
## not a silent dry arm.
##
## The shader itself documents the drop atlas it samples and why there is no
## screen read. Pixelcoat 0.50.0's `core/droplets.py` produces the atlas.
const DRIP_SHADER_PATH := "res://rain_drip.gdshader"


func _initialize() -> void:
	var a: PackedStringArray = OS.get_cmdline_user_args()
	if a.size() < 3:
		print("[wet_ab] USAGE: <out.json> <arm> <wetness>")
		quit(2)
		return
	_run(a[0], a[1], float(a[2]))


func _walk(n: Node, out: Array) -> void:
	out.append(n)
	for c in n.get_children():
		_walk(c, out)


## Is this material a surface the weather can reach?
##
## NAMED EVIDENCE, NOT A GUESS, which is what the proposal asks for and what the
## vertex-colour pass already does. Lot's ground, road and sidewalk slabs and
## Zoo's exterior wall families carry their role in the material name, so the
## test is a name test. `wet_all` exists to bound the cost from above when that
## naming is wrong or incomplete -- an upper bound that cannot flatter the
## answer is worth more than a selective one that might.
func _is_exterior(nm: String) -> bool:
	var s: String = nm.to_lower()
	for p in ["ground", "road", "sidewalk", "kerb", "curb", "walk", "asphalt",
			"concrete", "paint", "roof", "slab_", "ext_", "perim"]:
		if s.contains(p):
			return true
	return false


## The surfaces a player looks DOWN at. Road, sidewalk, kerb, asphalt, ground
## slabs and road paint -- not walls, not roofs.
##
## THIS ARM EXISTS BECAUSE THE COST IS PER SUBMISSION, and that was measured,
## not assumed: the marginal cost of the pass is 2.91-4.02 us per added draw
## call, median 3.52, flat across stations spanning 44 to 2,006 added draws.
## Flat per draw and NOT per pixel -- `ground_near`, where the road fills the
## frame, costs 2.91 us per draw while the distant aerial costs 4.02. So the
## bill scales with how many materials take the pass, and dropping the walls
## and roofs should cut it in proportion. That is the claim this arm measures
## rather than extrapolates.
func _is_ground(nm: String) -> bool:
	var s: String = nm.to_lower()
	for p in ["ground", "road", "sidewalk", "kerb", "curb", "walk", "asphalt",
			"paint", "slab_"]:
		if s.contains(p):
			return true
	return false


## A VERTICAL face's material. Drips run DOWN something; the wet variant
## already owns the ground. Named families rather than a normal test, because
## a material is attached to a mesh and does not know which way any one of its
## triangles faces -- the shader's own `up` term does that per fragment.
func _is_wall(nm: String) -> bool:
	var s: String = nm.to_lower()
	for p in ["brick", "concrete", "cinder", "stucco", "plaster", "siding",
			"drywall", "panel", "glass", "wall", "shingle", "corrugated",
			"metal_painted", "paint_block"]:
		if s.contains(p):
			return true
	return false


## THE SET A SHIPPING DRIP WOULD ACTUALLY USE. `_is_wall` above is the wide
## net and it caught 250 materials on cold run 9080's package -- nearly every
## wall-ish kind in the theme. Water running down a face is worth paying for
## on the EXTERIOR surfaces a player walks past, not on every interior
## partition and shelf, so this is the narrow arm: the street-facing families
## and nothing else.
##
## Measured rather than divided. The wide arm's cost is not divided by a ratio
## to get this one -- assuming proportionality is what produced the withdrawn
## figure in LF 0.115.0.
func _is_wall_few(nm: String) -> bool:
	var s: String = nm.to_lower()
	for p in ["brick", "siding", "stucco", "corrugated", "shingle"]:
		if s.contains(p):
			return true
	return false


func _attach(scene: Node, arm: String, wetness: float) -> int:
	if arm == "dry":
		return 0
	var drip: bool = arm == "drip" or arm == "drip_few"
	var shader := Shader.new()
	if drip:
		# LOADED, not embedded. `load()` on a .gdshader returns the Shader
		# resource itself, so the code string is never reconstructed here.
		var res: Shader = load(DRIP_SHADER_PATH) as Shader
		if res == null:
			push_error("[wet_ab] the drip arm needs %s staged into the arm"
				% DRIP_SHADER_PATH)
			return 0
		shader = res
	else:
		shader.code = WET_SHADER
	var atlas: Texture2D = null
	if drip:
		var img: Image = Image.load_from_file("res://drop_atlas.png")
		if img == null:
			push_error("[wet_ab] drip arm needs res://drop_atlas.png")
			return 0
		atlas = ImageTexture.create_from_image(img)
	var nodes: Array = []
	_walk(scene, nodes)
	var seen: Dictionary = {}
	var count: int = 0
	for n in nodes:
		var mi: MeshInstance3D = n as MeshInstance3D
		if mi == null or mi.mesh == null:
			continue
		for i in range(mi.mesh.get_surface_count()):
			var bm: BaseMaterial3D = mi.mesh.surface_get_material(i) as BaseMaterial3D
			if bm == null or seen.has(bm.get_instance_id()):
				continue
			seen[bm.get_instance_id()] = true
			var mat_name: String = String(bm.resource_name)
			if arm == "drip" and not _is_wall(mat_name):
				continue
			if arm == "drip_few" and not _is_wall_few(mat_name):
				continue
			if arm == "wet" and not _is_exterior(mat_name):
				continue
			if arm == "wet_ground" and not _is_ground(mat_name):
				continue
			if bm.next_pass != null:
				continue           # idempotent, as the CRT pass is
			var sm := ShaderMaterial.new()
			sm.shader = shader
			sm.resource_name = String(bm.resource_name) + ("_drip" if drip else "_wet")
			if drip:
				sm.set_shader_parameter("drops", atlas)
				sm.set_shader_parameter("amount", wetness)
			else:
				sm.set_shader_parameter("wetness", wetness)
				sm.set_shader_parameter("sky_bias", 2.0)
			bm.next_pass = sm
			count += 1
	return count


func _run(out_path: String, arm: String, wetness: float) -> void:
	await process_frame
	# THE FIRST RUN OF THIS PROBE OMITTED ALL FOUR OF THESE LINES, and three of
	# its six stations came back pinned at 6.07 ms -- the refresh interval of
	# the machine it ran on, not a frame time. `occlusion_ab.gd` has had them
	# since it was written; they were missed by modelling this on the memory of
	# that file rather than re-reading it. Without `measure_render_time` the
	# CPU and GPU fields read 0.00 and the run cannot say whether an extra pass
	# costs submission or fill -- which is the whole question when deciding
	# whether narrowing the surface set would help.
	DisplayServer.window_set_size(Vector2i(W, H))
	root.content_scale_size = Vector2i(W, H)
	Engine.max_fps = 0
	DisplayServer.window_set_vsync_mode(DisplayServer.VSYNC_DISABLED)
	RenderingServer.viewport_set_measure_render_time(root.get_viewport_rid(),
		true)
	var report: Dictionary = {
		"schema": "lf.wet_ab.v1", "ok": false, "error": "",
		"arm": arm, "wetness": wetness, "materials_wet": 0, "stations": [],
	}
	var main_scene: String = String(ProjectSettings.get_setting(
		"application/run/main_scene", ""))
	var ps: PackedScene = load(main_scene) as PackedScene
	if ps == null:
		report["error"] = "main_scene %s did not load" % main_scene
		_write(out_path, report)
		quit(0)
		return
	report["main_scene"] = main_scene
	var scene: Node = ps.instantiate()
	root.add_child(scene)
	for i in range(30):
		await process_frame

	report["materials_wet"] = _attach(scene, arm, wetness)

	var nodes: Array = []
	_walk(scene, nodes)
	var box: AABB = AABB()
	var got: bool = false
	for n in nodes:
		var v3: VisualInstance3D = n as VisualInstance3D
		if v3 == null:
			continue
		var b: AABB = v3.global_transform * v3.get_aabb()
		box = b if not got else box.merge(b)
		got = true
	if not got:
		report["error"] = "nothing drawable in the scene"
		_write(out_path, report)
		quit(0)
		return

	var c: Vector3 = box.get_center()
	var d: float = maxf(box.size.x, box.size.z)
	var fy: float = box.position.y + EYE
	# THE GROUND STATIONS ARE THE POINT. A wet pass costs where wet surfaces
	# fill the frame, so the set is weighted toward views down the street --
	# and keeps two interior views, which must read ~0 extra cost or the pass
	# is reaching surfaces the rain cannot.
	var stations: Array = [
		{"n": "street_down", "eye": Vector3(c.x, box.position.y + EYE, c.z),
			"look": Vector3(c.x + d, box.position.y, c.z)},
		{"n": "street_along", "eye": Vector3(c.x - d * 0.4, fy, c.z),
			"look": Vector3(c.x + d, box.position.y + 1.0, c.z)},
		{"n": "ground_near", "eye": Vector3(c.x, box.position.y + 2.5, c.z),
			"look": Vector3(c.x + 4.0, box.position.y, c.z)},
		{"n": "exterior_high", "eye": c + Vector3(d * 0.7, box.size.y * 0.6,
			d * 0.7), "look": c},
		{"n": "interior_a", "eye": Vector3(c.x, fy, c.z),
			"look": Vector3(c.x + d, fy, c.z)},
		{"n": "interior_b", "eye": Vector3(c.x - d * 0.3, fy, c.z - d * 0.3),
			"look": Vector3(c.x + d, fy, c.z + d)},
	]

	var cam := Camera3D.new()
	cam.fov = 70.0
	cam.far = 4000.0
	root.add_child(cam)
	cam.make_current()
	var vp: RID = root.get_viewport_rid()

	for s in stations:
		cam.global_position = s["eye"]
		cam.look_at(s["look"], Vector3.UP)
		for i in range(WARMUP):
			await process_frame
		var samples: Array = []
		var cpu_sum: float = 0.0
		var gpu_sum: float = 0.0
		var last: int = Time.get_ticks_usec()
		for i in range(SAMPLE):
			await process_frame
			var now: int = Time.get_ticks_usec()
			samples.append(float(now - last) / 1000.0)
			last = now
			cpu_sum += RenderingServer.viewport_get_measured_render_time_cpu(vp)
			gpu_sum += RenderingServer.viewport_get_measured_render_time_gpu(vp)
		samples.sort()
		var total: float = 0.0
		for x in samples:
			total += float(x)
		var n_s: float = float(samples.size())
		# DID IT DRAW? Draw calls rising proves a submission, not a shaded
		# pixel, and the first run of this probe could not tell them apart.
		# The frame's own mean luminance can: a wet arm whose frame matches
		# the dry one is a pass nobody can see, and the runner refuses to
		# tabulate a cost for it.
		var img: Image = root.get_texture().get_image()
		var lum: float = 0.0
		var step_px: int = maxi(1, img.get_width() / 160)
		var taken: int = 0
		for py in range(0, img.get_height(), step_px):
			for px in range(0, img.get_width(), step_px):
				var texel: Color = img.get_pixel(px, py)
				lum += 0.2126 * texel.r + 0.7152 * texel.g + 0.0722 * texel.b
				taken += 1
		report["stations"].append({
			"frame_luma": snappedf(lum / maxf(float(taken), 1.0), 0.0001),
			"station": String(s["n"]),
			"draw_calls": int(RenderingServer.get_rendering_info(
				RenderingServer.RENDERING_INFO_TOTAL_DRAW_CALLS_IN_FRAME)),
			"primitives": int(RenderingServer.get_rendering_info(
				RenderingServer.RENDERING_INFO_TOTAL_PRIMITIVES_IN_FRAME)),
			"ms_mean": snappedf(total / n_s, 0.001),
			"ms_median": snappedf(float(samples[int(n_s / 2.0)]), 0.001),
			"cpu_ms": snappedf(cpu_sum / n_s, 0.001),
			"gpu_ms": snappedf(gpu_sum / n_s, 0.001),
		})

	report["ok"] = true
	_write(out_path, report)
	print("[wet_ab] arm=%s materials_wet=%d stations=%d"
		% [arm, int(report["materials_wet"]), report["stations"].size()])
	quit(0)


func _write(out_path: String, report: Dictionary) -> void:
	var fh: FileAccess = FileAccess.open(out_path, FileAccess.WRITE)
	if fh == null:
		push_error("[wet_ab] could not write %s" % out_path)
		return
	fh.store_string(JSON.stringify(report, "  "))
	fh.close()
