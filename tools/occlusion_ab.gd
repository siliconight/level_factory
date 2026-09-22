extends SceneTree
## `perf_probe.gd` plus the three figures the occlusion question needs:
## objects-in-frame (the counter culling moves), and the render CPU/GPU
## split, which is the one that says whether a saving landed on the side
## that was actually loaded. Stations, camera, warmup and sample are
## unchanged from that file, so its numbers and these are comparable; the
## bounds are printed so two runs can be shown to have stood in the same
## place rather than assumed to.
##
## Occlusion culling is NOT toggled here. It comes from the package's own
## project.godot, because that is what a recipient will run and a runtime
## override would measure a configuration nobody ships. Which way it was set
## is printed in the header of every run.
##
## RETRACTED, kept above what replaced it. Until 0.102.0 this loaded
## `res://site.tscn` directly -- a named literal, not the package's entry --
## and every occlusion figure this repo published came out of it. On cold run
## 9066's package that scene is a Lux-less sibling nothing runs: the package's
## `run/main_scene` is `res://mission.tscn`, which instances
## `presentation/lux.applied.tscn` and the dressing layer and never names
## `site.tscn` at all. So the A/B was real and it described a scene the
## mission does not load -- unlit, undressed, and, before 0.102.0, the only
## scene in the package that could reach the occluders.
##
## It now loads whatever `application/run/main_scene` names, prints that name
## into every row, and finds its reference building by SEARCHING the tree
## rather than by `get_node("b0")` on the root, because the entry scene
## instances its content a level down. A run against a scene whose name is
## not in the output is not comparable with one that is.
##
## AND IT WAITS FOR THE WARM-UP, which moving to the entry scene is what put
## in the way. `warmup.gd` is wired into `mission.tscn` and into nothing else,
## so the old probe never met it; the entry scene's tree carries it. For the
## length of its sweep -- up to `max_stations` (96) x 6 = 576 frames -- it
## sets `use_occlusion_culling = FALSE` and `scaling_3d_scale = 0.1` ON THE
## VIEWPORT and restores them when it ends. Sampling before that lands reads
## the culler off in BOTH arms at a tenth of the linear resolution, which is
## an A/B that cannot move. So this awaits `warmup_finished`, on a frame
## budget, and every row carries the viewport's OWN `use_occlusion_culling`
## as it stood while that row was sampled -- the project setting is what the
## package asks for, and this is what the frame got.
##
## Usage: godot --path <pkg> --script res://occlusion_ab.gd -- <out_json> <tag>

const W := 1280
const H := 720
const EYE := 1.6
const WARMUP := 120
const SAMPLE := 300

#: Frames to give the warm-up before measuring without it. Its sweep is
#: `stations * 6` and `max_stations` is 96, so 576 is the ceiling it can ask
#: for; this is that with room for the frames it spends building its station
#: list. Exceeding it is printed and recorded rather than waited out forever.
const WARM_BUDGET := 900


func _initialize() -> void:
	var args: PackedStringArray = OS.get_cmdline_user_args()
	# A WINDOWED run that errors out of `_initialize` does not quit: the
	# SceneTree keeps going and the window sits on somebody's desktop looking
	# like a hang. CLAUDE.md, twice on 2026-09-21.
	if args.size() < 2:
		print("[occ-ab] USAGE: <out_json> <tag>")
		quit(2)
		return
	_run(args[0], args[1])


func _walk(n: Node, out: Array) -> void:
	out.append(n)
	for c in n.get_children():
		_walk(c, out)


func _find(n: Node, want: String) -> Node:
	## The entry scene instances the level a level down, so the reference
	## building is not a direct child of the root any more. Breadth-first, so
	## the SHALLOWEST match wins and the station set stays where it was when
	## the same building was reached by name off `site.tscn`.
	var queue: Array = [n]
	while not queue.is_empty():
		var cur: Node = queue.pop_front()
		if String(cur.name) == want:
			return cur
		for c in cur.get_children():
			queue.append(c)
	return null


func _bounds(n: Node) -> AABB:
	var nodes: Array = []
	_walk(n, nodes)
	var box := AABB()
	var first := true
	for x in nodes:
		var v: VisualInstance3D = x as VisualInstance3D
		if v == null:
			continue
		var a: AABB = v.global_transform * v.get_aabb()
		if first:
			box = a
			first = false
		else:
			box = box.merge(a)
	return box


func _run(out_path: String, tag: String) -> void:
	await process_frame
	DisplayServer.window_set_size(Vector2i(W, H))
	root.content_scale_size = Vector2i(W, H)
	Engine.max_fps = 0
	DisplayServer.window_set_vsync_mode(DisplayServer.VSYNC_DISABLED)

	var vp: RID = root.get_viewport_rid()
	RenderingServer.viewport_set_measure_render_time(vp, true)
	var occ_setting: bool = bool(ProjectSettings.get_setting(
		"rendering/occlusion_culling/use_occlusion_culling"))
	print("SETTING %s use_occlusion_culling=%s" % [tag, str(occ_setting)])

	var main_scene: String = String(ProjectSettings.get_setting(
		"application/run/main_scene", ""))
	if main_scene == "":
		print("MAIN_SCENE %s <none> -- project.godot names no entry scene"
			% [tag])
		quit(2)
		return
	print("MAIN_SCENE %s %s" % [tag, main_scene])
	var packed: PackedScene = load(main_scene) as PackedScene
	if packed == null:
		print("MAIN_SCENE %s CANNOT LOAD %s" % [tag, main_scene])
		quit(2)
		return
	var site: Node = packed.instantiate()
	root.add_child(site)
	# The entry scene instances its content from `_ready()`, so nothing below
	# is true of the tree until it has had frames to become what it will be.
	for i in range(10):
		await physics_frame

	# THE WARM-UP OWNS THE VIEWPORT UNTIL IT IS DONE. See the header: it turns
	# the culler off and renders at a tenth scale for the length of its sweep,
	# so a station sampled during it is not the configuration the package
	# ships. Waited for by its own signal; a package with no warm-up, or one
	# that returned early with nothing to warm, is not waited for at all.
	var warm: Node = _find(site, "Warmup")
	var done: Array = [false]
	var have_warm: bool = warm != null and warm.has_signal("warmup_finished")
	if have_warm:
		warm.connect("warmup_finished",
			func(_frames, _ms): done[0] = true)
	var waited: int = 0
	while have_warm and not bool(done[0]) and waited < WARM_BUDGET:
		await process_frame
		waited += 1
	var warm_ok: bool = (not have_warm) or bool(done[0])
	print("WARMUP %s present=%s finished=%s frames=%d"
		% [tag, str(have_warm), str(warm_ok), waited])

	var occ_nodes: Array = []
	var all_nodes: Array = []
	_walk(site, all_nodes)
	for x in all_nodes:
		if x is OccluderInstance3D:
			occ_nodes.append(x)
	print("OCCLUDER_NODES %s %d" % [tag, occ_nodes.size()])

	var shop: Node = _find(site, "b0")
	if shop == null:
		print("STATIONS %s NO b0 IN %s -- nothing to place them against"
			% [tag, main_scene])
		quit(3)
		return
	var b: AABB = _bounds(shop)
	print("BOUNDS %s pos=%.6f,%.6f,%.6f size=%.6f,%.6f,%.6f"
		% [tag, b.position.x, b.position.y, b.position.z,
		   b.size.x, b.size.y, b.size.z])

	var c: Vector3 = b.get_center()
	var d: float = maxf(b.size.x, b.size.z)
	var fy: float = b.position.y + EYE
	var stations: Array = [
		{"n": "exterior_ne", "eye": c + Vector3(d * 0.75, b.size.y * 0.55,
			d * 0.75), "look": c},
		{"n": "exterior_sw", "eye": c + Vector3(-d * 0.75, b.size.y * 0.35,
			-d * 0.75), "look": c},
		{"n": "interior_c", "eye": Vector3(c.x, fy, c.z),
			"look": Vector3(c.x + d, fy, c.z)},
		{"n": "interior_x", "eye": Vector3(c.x - d * 0.3, fy, c.z - d * 0.3),
			"look": Vector3(c.x + d, fy, c.z + d)},
		{"n": "interior_z", "eye": Vector3(c.x + d * 0.3, fy, c.z + d * 0.3),
			"look": Vector3(c.x - d, fy, c.z - d)},
		{"n": "wall_close", "eye": Vector3(c.x, fy, c.z),
			"look": Vector3(c.x, fy, c.z + d)},
		# THE OPEN VIEW, and the six above did not have one. Every station
		# there looks INTO the block, where an occluder has something to
		# reject; the culler's raster and its per-object test are paid every
		# frame whether or not they reject anything, and a set with no station
		# that can read that cost can only ever report a saving. Same eye as
		# `exterior_ne` and the opposite gaze, so the pair differs in where it
		# looks and in nothing else.
		{"n": "exterior_open", "eye": c + Vector3(d * 0.75, b.size.y * 0.55,
			d * 0.75), "look": c + Vector3(d * 4.0, b.size.y * 0.55, d * 4.0)},
	]

	var cam := Camera3D.new()
	var env := Environment.new()
	env.background_mode = Environment.BG_COLOR
	env.background_color = Color(1.0, 0.0, 1.0, 1.0)
	env.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	env.ambient_light_color = Color(1.0, 1.0, 1.0)
	env.ambient_light_energy = 1.6
	env.tonemap_mode = Environment.TONE_MAPPER_LINEAR
	cam.environment = env
	cam.far = 400.0
	cam.current = true
	root.add_child(cam)

	var result: Dictionary = {
		"tag": tag, "occlusion_setting": occ_setting,
		# WHICH SCENE THESE NUMBERS DESCRIBE, in the artefact rather than in
		# whoever reports it. Two runs over different entry scenes are not an
		# A/B and there was no way to tell from the old file.
		"main_scene": main_scene,
		# WHETHER THE WARM-UP HAD FINISHED, in the artefact. A run that hit
		# the budget was sampled with the culler forced off and the viewport
		# at a tenth scale, and is not comparable with one that was not.
		"warmup_present": have_warm, "warmup_finished": warm_ok,
		"warmup_wait_frames": waited,
		"occluder_nodes": occ_nodes.size(), "stations": [],
	}
	for s in stations:
		cam.global_transform = Transform3D(Basis(), s["eye"])
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
		var sum: float = 0.0
		for x in samples:
			sum += float(x)
		var n: float = float(samples.size())
		var row: Dictionary = {
			"station": String(s["n"]),
			# READ OFF THE VIEWPORT, not off ProjectSettings, and read AFTER
			# the samples. The project setting is what the package asks for;
			# this is what the frames that produced the numbers beside it
			# actually had. They differ whenever something in the level has
			# taken the viewport -- which the warm-up does, by design.
			"viewport_occlusion": bool(root.use_occlusion_culling),
			"objects": int(RenderingServer.get_rendering_info(
				RenderingServer.RENDERING_INFO_TOTAL_OBJECTS_IN_FRAME)),
			"draw_calls": int(RenderingServer.get_rendering_info(
				RenderingServer.RENDERING_INFO_TOTAL_DRAW_CALLS_IN_FRAME)),
			"primitives": int(RenderingServer.get_rendering_info(
				RenderingServer.RENDERING_INFO_TOTAL_PRIMITIVES_IN_FRAME)),
			"mean_ms": sum / n,
			"median_ms": float(samples[samples.size() / 2]),
			"p95_ms": float(samples[int(n * 0.95)]),
			"render_cpu_ms": cpu_sum / n,
			"render_gpu_ms": gpu_sum / n,
		}
		result["stations"].append(row)
		print("STATION %s %-14s vpocc=%-5s objects=%5d draws=%5d prims=%8d mean=%.3fms median=%.3fms p95=%.3fms cpu=%.3fms gpu=%.3fms"
			% [tag, row["station"], str(row["viewport_occlusion"]),
			   row["objects"], row["draw_calls"],
			   row["primitives"], row["mean_ms"], row["median_ms"],
			   row["p95_ms"], row["render_cpu_ms"], row["render_gpu_ms"]])
	var fh: FileAccess = FileAccess.open(out_path, FileAccess.WRITE)
	fh.store_string(JSON.stringify(result, "  "))
	fh.close()
	quit(0)
