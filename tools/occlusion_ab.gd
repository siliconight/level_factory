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
## Usage: godot --path <pkg> --script res://perf_probe2.gd -- <out_json> <tag>

const W := 1280
const H := 720
const EYE := 1.6
const WARMUP := 120
const SAMPLE := 300


func _initialize() -> void:
	var args: PackedStringArray = OS.get_cmdline_user_args()
	_run(args[0], args[1])


func _walk(n: Node, out: Array) -> void:
	out.append(n)
	for c in n.get_children():
		_walk(c, out)


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

	var site: Node = (load("res://site.tscn") as PackedScene).instantiate()
	root.add_child(site)
	for i in range(10):
		await physics_frame

	var occ_nodes: Array = []
	var all_nodes: Array = []
	_walk(site, all_nodes)
	for x in all_nodes:
		if x is OccluderInstance3D:
			occ_nodes.append(x)
	print("OCCLUDER_NODES %s %d" % [tag, occ_nodes.size()])

	var shop: Node = site.get_node_or_null("b0")
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
		print("STATION %s %-13s objects=%5d draws=%5d prims=%8d mean=%.3fms median=%.3fms p95=%.3fms cpu=%.3fms gpu=%.3fms"
			% [tag, row["station"], row["objects"], row["draw_calls"],
			   row["primitives"], row["mean_ms"], row["median_ms"],
			   row["p95_ms"], row["render_cpu_ms"], row["render_gpu_ms"]])
	var fh: FileAccess = FileAccess.open(out_path, FileAccess.WRITE)
	fh.store_string(JSON.stringify(result, "  "))
	fh.close()
	quit(0)
