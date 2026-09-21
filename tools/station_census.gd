extends SceneTree
## WHAT IS EACH STATION ACTUALLY SUBMITTING, and which branch it comes from.
##
## Not "what is in the scene" -- `draw_audit.gd` already answers that, and it
## is a property of the file, not of where the camera stands. This answers the
## question the brief asks: standing inside the shop, is the street being
## drawn, and if so whose street is it.
##
## METHOD. Attribution by subtraction. At each station the baseline is
## measured, then one group of top-level branches is made invisible and the
## frame is measured again. The drop is that group's contribution to THAT
## view -- an actual submission count, not an AABB-in-frustum estimate, and
## it costs nothing to be right about glass, because a mesh the renderer
## decided to submit is counted whether or not this script understands why.
##
## The groups are the top-level children of `site.tscn`, bucketed by name:
## the three buildings by their own node names, street props by `cover_`,
## and the ground plane / roads / sidewalks / kerbs / markings together,
## since none of them is separately actionable.
##
## THE CONTROL. `_hide_all` hides every group at once. If objects-in-frame
## does not fall to approximately zero there, the visibility switch is not
## doing what this script believes and no other row is evidence.
##
## Stations are derived from b0's AABB by the same arithmetic as
## `perf_probe.gd` and the bounds are printed, so the two can be shown to
## have stood in the same place.
##
## Prints what it measured. It does not say why.
##
## Usage: godot --path <pkg> --script res://census_station.gd -- <out.json>

const W := 1280
const H := 720
const EYE := 1.6
const SETTLE := 4

var _cam: Camera3D = null
var _groups: Dictionary = {}
var _rows: Array = []


func _initialize() -> void:
	var args: PackedStringArray = OS.get_cmdline_user_args()
	var out_path: String = args[0] if args.size() > 0 else "res://census.json"
	_run(out_path)


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


func _bucket(node_name: String) -> String:
	if node_name == "b0" or node_name == "b1" or node_name == "b2":
		return node_name
	if node_name.begins_with("cover_"):
		return "street_props"
	for p in ["Ground", "road", "sidewalk", "kerbcut", "path", "perim",
			"frontage", "mark"]:
		if node_name.begins_with(p):
			return "site_surface"
	return "other"


func _run(out_path: String) -> void:
	await process_frame
	DisplayServer.window_set_size(Vector2i(W, H))
	root.content_scale_size = Vector2i(W, H)
	Engine.max_fps = 0
	DisplayServer.window_set_vsync_mode(DisplayServer.VSYNC_DISABLED)

	var site: Node = (load("res://site.tscn") as PackedScene).instantiate()
	root.add_child(site)
	for i in range(10):
		await physics_frame

	# Bucket the top-level branches, and count the VisualInstance3D each one
	# holds so a station's submission can be read against what was available.
	var held: Dictionary = {}
	for child in site.get_children():
		var b: String = _bucket(String(child.name))
		if not _groups.has(b):
			_groups[b] = []
			held[b] = 0
		var arr: Array = _groups[b]
		arr.append(child)
		var nodes: Array = []
		_walk(child, nodes)
		var vis: int = 0
		for x in nodes:
			if x is VisualInstance3D:
				vis += 1
		held[b] = int(held[b]) + vis

	var shop: Node = site.get_node_or_null("b0")
	var b0: AABB = _bounds(shop)
	print("BOUNDS census pos=%.6f,%.6f,%.6f size=%.6f,%.6f,%.6f"
		% [b0.position.x, b0.position.y, b0.position.z,
		   b0.size.x, b0.size.y, b0.size.z])
	for g in _groups:
		var arr2: Array = _groups[g]
		print("GROUP %-14s branches=%3d visual_instances=%5d"
			% [g, arr2.size(), int(held[g])])

	var c: Vector3 = b0.get_center()
	var d: float = maxf(b0.size.x, b0.size.z)
	var fy: float = b0.position.y + EYE
	var stations: Array = [
		{"n": "exterior_ne", "eye": c + Vector3(d * 0.75, b0.size.y * 0.55,
			d * 0.75), "look": c},
		{"n": "exterior_sw", "eye": c + Vector3(-d * 0.75, b0.size.y * 0.35,
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

	_cam = Camera3D.new()
	var env: Environment = Environment.new()
	env.background_mode = Environment.BG_COLOR
	env.background_color = Color(1.0, 0.0, 1.0, 1.0)
	env.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	env.ambient_light_color = Color(1.0, 1.0, 1.0)
	env.ambient_light_energy = 1.6
	env.tonemap_mode = Environment.TONE_MAPPER_LINEAR
	_cam.environment = env
	_cam.far = 400.0
	_cam.current = true
	root.add_child(_cam)

	var names: Array = _groups.keys()
	names.sort()

	for s in stations:
		var sn: String = String(s["n"])
		var eye: Vector3 = s["eye"]
		var look: Vector3 = s["look"]
		_cam.global_transform = Transform3D(Basis(), eye)
		_cam.look_at(look, Vector3.UP)
		var base: Array = await _sample()
		var base_obj: int = int(base[0])
		var base_draw: int = int(base[1])
		print("STATION %-13s baseline objects=%5d draws=%5d"
			% [sn, base_obj, base_draw])
		for g in names:
			var gname: String = String(g)
			_set_group(gname, false)
			var cut: Array = await _sample()
			_set_group(gname, true)
			var row: Dictionary = {
				"station": sn,
				"group": gname,
				"held_visual_instances": int(held[gname]),
				"baseline_objects": base_obj,
				"baseline_draws": base_draw,
				"objects_without": int(cut[0]),
				"draws_without": int(cut[1]),
				"objects_attributed": base_obj - int(cut[0]),
				"draws_attributed": base_draw - int(cut[1]),
			}
			_rows.append(row)
			print("  %-13s %-14s submits objects=%5d draws=%5d  of %5d held"
				% [sn, gname, row["objects_attributed"],
				   row["draws_attributed"], row["held_visual_instances"]])
		# The control. Everything off: if this is not ~0 the switch is not
		# doing what the rows above assume, and they are not evidence.
		for g2 in names:
			_set_group(String(g2), false)
		var allcut: Array = await _sample()
		for g3 in names:
			_set_group(String(g3), true)
		print("  %-13s CONTROL all-hidden objects=%5d draws=%5d (must be ~0)"
			% [sn, int(allcut[0]), int(allcut[1])])
		_rows.append({
			"station": sn, "group": "_control_all_hidden",
			"held_visual_instances": 0,
			"baseline_objects": base_obj, "baseline_draws": base_draw,
			"objects_without": int(allcut[0]), "draws_without": int(allcut[1]),
			"objects_attributed": base_obj - int(allcut[0]),
			"draws_attributed": base_draw - int(allcut[1]),
		})

	var fh: FileAccess = FileAccess.open(out_path, FileAccess.WRITE)
	fh.store_string(JSON.stringify({"rows": _rows}, "  "))
	fh.close()
	quit(0)


func _set_group(gname: String, vis: bool) -> void:
	var arr: Array = _groups[gname]
	for n in arr:
		var n3: Node3D = n as Node3D
		if n3 != null:
			n3.visible = vis


func _sample() -> Array:
	for i in range(SETTLE):
		await process_frame
	var objects: int = int(RenderingServer.get_rendering_info(
		RenderingServer.RENDERING_INFO_TOTAL_OBJECTS_IN_FRAME))
	var draws: int = int(RenderingServer.get_rendering_info(
		RenderingServer.RENDERING_INFO_TOTAL_DRAW_CALLS_IN_FRAME))
	return [objects, draws]
