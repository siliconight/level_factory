extends SceneTree
## DID THE OCCLUDERS REMOVE ANYTHING A PLAYER CAN SEE?
##
## The submission measurement says interior_c fell from 4,635 draw calls to
## 422. That is only good news if the 4,213 that stopped being submitted were
## all behind a wall. This renders each station twice -- occlusion off, then
## on -- and compares the two images.
##
## THE CONTROL, WHICH IS THE WHOLE REASON THIS FILE IS LONGER THAN IT LOOKS.
## The merge's first render probe reported "pixel-identical" from frames that
## were 99.7% black, and a known geometry change measured zero through it. So
## every row here also carries:
##
##   coverage   the share of pixels that are not the background magenta. A
##              comparison over an empty frame proves nothing, and this says
##              so in the row rather than in a footnote.
##   control    one visible MeshInstance3D is hidden and the frame captured a
##              third time. `control_diff` is the comparator being shown a
##              difference it must find. A station where control_diff is 0 has
##              a blind comparator and its `diff` of 0 is worth nothing.
##
## `diff` counts pixels differing by more than TOL on any channel, so the
## renderer's own frame-to-frame noise does not read as a culling error.
##
## Prints what it measured. It does not say why.
##
## Usage: godot --path <pkg> --script res://occ_visual.gd -- <out.json> [dump_dir]

const W := 1280
const H := 720
const EYE := 1.6
const TOL := 8

var _cam: Camera3D = null
var _rows: Array = []
var _dump := ""


func _initialize() -> void:
	var args: PackedStringArray = OS.get_cmdline_user_args()
	var out_path: String = args[0] if args.size() > 0 else "res://occ_visual.json"
	if args.size() > 1:
		_dump = args[1]
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

func _grab() -> Image:
	await RenderingServer.frame_post_draw
	return root.get_texture().get_image()


func _compare(a: Image, b: Image) -> int:
	var n := 0
	for y in range(a.get_height()):
		for x in range(a.get_width()):
			var ca: Color = a.get_pixel(x, y)
			var cb: Color = b.get_pixel(x, y)
			if absi(int(ca.r8) - int(cb.r8)) > TOL \
					or absi(int(ca.g8) - int(cb.g8)) > TOL \
					or absi(int(ca.b8) - int(cb.b8)) > TOL:
				n += 1
	return n


func _coverage(img: Image) -> int:
	## Pixels that are not the magenta background. A frame of nothing has to
	## be visible as a frame of nothing.
	var n := 0
	for y in range(img.get_height()):
		for x in range(img.get_width()):
			var c: Color = img.get_pixel(x, y)
			if not (c.r8 > 200 and c.g8 < 60 and c.b8 > 200):
				n += 1
	return n


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
	# The package's OWN occluders, as the exporter emitted them -- not a set
	# this script builds. The prototype measured a shape; this measures the
	# artefact that ships, which is the only one a recipient will ever see.
	var found: Array = []
	var all_nodes: Array = []
	_walk(site, all_nodes)
	for x in all_nodes:
		if x is OccluderInstance3D:
			found.append(x)
	print("OCCLUDERS in_package=%d" % [found.size()])
	if found.is_empty():
		print("OCCLUDERS NONE IN PACKAGE -- this run compares nothing")

	var shop: Node = site.get_node_or_null("b0")
	var b: AABB = _bounds(shop)
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

	_cam = Camera3D.new()
	var env := Environment.new()
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

	var vp: RID = root.get_viewport_rid()
	var total: int = W * H

	for s in stations:
		var sn: String = String(s["n"])
		var eye: Vector3 = s["eye"]
		var look: Vector3 = s["look"]
		_cam.global_transform = Transform3D(Basis(), eye)
		_cam.look_at(look, Vector3.UP)

		RenderingServer.viewport_set_use_occlusion_culling(vp, false)
		for i in range(20):
			await process_frame
		var img_off: Image = await _grab()

		RenderingServer.viewport_set_use_occlusion_culling(vp, true)
		for i in range(20):
			await process_frame
		var img_on: Image = await _grab()

		# The control. FIRST ATTEMPT, RETRACTED, kept above what replaced it:
		# hide `_nearest_visible`, the closest large MeshInstance3D to the eye.
		# It picked by distance to an AABB centre and never checked the thing
		# was in frustum, so at interior_x and wall_close it hid something off
		# screen and reported control_diff=0 -- a blind comparator, whose
		# diff=0 on the row above it proved nothing. exterior_sw reported 1.
		#
		# What replaced it: hide the whole b0 branch. The station census
		# measured b0 submitting 265-768 draw calls at every one of these six
		# stations, so it is on screen everywhere by measurement rather than
		# by hope, and the comparator has to see it go.
		var victim: Node3D = site.get_node_or_null("b0") as Node3D
		var control_diff := -1
		if victim != null:
			victim.visible = false
			for i in range(20):
				await process_frame
			var img_ctl: Image = await _grab()
			victim.visible = true
			control_diff = _compare(img_on, img_ctl)

		var diff: int = _compare(img_off, img_on)
		var cov_off: int = _coverage(img_off)
		var cov_on: int = _coverage(img_on)
		var row: Dictionary = {
			"station": sn,
			"diff_pixels": diff,
			"diff_pct": 100.0 * float(diff) / float(total),
			"coverage_off_pct": 100.0 * float(cov_off) / float(total),
			"coverage_on_pct": 100.0 * float(cov_on) / float(total),
			"control_diff_pixels": control_diff,
			"control_node": String(victim.name) if victim != null else "",
		}
		_rows.append(row)
		print("VIS %-13s diff=%7d (%.4f%%)  coverage off=%.1f%% on=%.1f%%  control_diff=%7d (%s)"
			% [sn, diff, row["diff_pct"], row["coverage_off_pct"],
			   row["coverage_on_pct"], control_diff, row["control_node"]])
		if _dump != "":
			img_off.save_png("%s/%s_off.png" % [_dump, sn])
			img_on.save_png("%s/%s_on.png" % [_dump, sn])

	var fh: FileAccess = FileAccess.open(out_path, FileAccess.WRITE)
	fh.store_string(JSON.stringify({"rows": _rows}, "  "))
	fh.close()
	quit(0)
