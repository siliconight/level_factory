extends SceneTree
## Headless VISUAL PASS over a composed package: renders canonical stations and
## measures two defects that a physics walk cannot see, then leaves the frames
## behind for a human.
##
## Usage:
##   godot --path <walk_preview_dir> --script res://shot_bot.gd \
##       -- <out_json> <shots_dir> [scene_res_path]
##
## (needs a display; under CI wrap in xvfb-run. --headless renders nothing.)
##
## No golden baselines. Baselines rot: every mission is different geometry, so a
## per-mission reference image is a file nobody regenerates and everybody
## ignores. Both measurements here are self-referential -- the frame is compared
## against another frame of the SAME build -- so the pass is meaningful the
## first time it ever runs on a level nobody has seen.
##
## VOID FRACTION. The camera's environment is overridden to a flat unmistakable
## background (pure magenta, a colour no material produces), so every pixel that
## is still background is a pixel where the camera looked at the world and found
## nothing. From an interior station that is a hole: a missing wall, an
## unplaced module, a slab that never got cut in.
##
## JITTER DIFF. Each station renders twice, one millimetre apart. Solid geometry
## is unchanged at that scale -- a millimetre of parallax moves nothing by a
## whole pixel. Coplanar surfaces are not: which of the two wins the depth test
## flips, so a z-fighting pair lights up as a large block of changed pixels
## while an honest frame changes almost none. This is the visual counterpart to
## the analytic z-fight gate: that one reasons about authored planes, this one
## catches whatever actually reached the renderer.

const W := 640
const H := 360
const EYE := 1.6
const JITTER := 0.001        # metres; a millimetre of camera parallax
const DIFF_TOL := 12         # per-channel 0-255 delta that counts as "changed"
# Calibrated, not guessed. On a correctly composed package the worst honest
# station measured 0.68% (edge aliasing along a ladder's rungs -- thin
# high-contrast geometry is where sub-pixel motion legitimately shows). The same
# package rebuilt with un-stripped greybox walls under the themed modules -- a
# real double-wall z-fight -- measured 30.67%. The defect signal is ~45x the
# noise floor, so the threshold sits well clear of both.
const JITTER_FAIL_PCT := 2.0
const VOID := Color(1.0, 0.0, 1.0, 1.0)
const VOID_TOL := 0.06

var _out_path := ""
var _shots_dir := "res://shots"
var _scene_path := "res://site.tscn"
var _result := {"ok": false, "stations": [], "error": ""}
var _cam: Camera3D = null


func _initialize() -> void:
	var args := OS.get_cmdline_user_args()
	if args.size() >= 1:
		_out_path = args[0]
	if args.size() >= 2:
		_shots_dir = args[1]
	if args.size() >= 3:
		_scene_path = args[2]
	_run()


func _run() -> void:
	await process_frame
	DisplayServer.window_set_size(Vector2i(W, H))
	root.content_scale_size = Vector2i(W, H)

	var packed: PackedScene = load(_scene_path)
	if packed == null:
		_fail("cannot load scene %s" % _scene_path)
		return
	var site: Node = packed.instantiate()
	root.add_child(site)
	for i in range(5):
		await physics_frame

	DirAccess.make_dir_recursive_absolute(_shots_dir)

	_cam = Camera3D.new()
	# Own the look completely: a camera-level Environment override beats
	# whatever WorldEnvironment the content carries (Lux ships one), so the
	# measurement does not change when the lighting pass does.
	var env := Environment.new()
	env.background_mode = Environment.BG_COLOR
	env.background_color = VOID
	env.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	env.ambient_light_color = Color(0.85, 0.86, 0.9)
	env.ambient_light_energy = 1.5
	env.tonemap_mode = Environment.TONE_MAPPER_LINEAR
	_cam.environment = env
	_cam.far = 400.0
	_cam.current = true
	root.add_child(_cam)

	var bounds: AABB = _scene_bounds(site)
	var stations: Array = _stations(bounds)
	if stations.is_empty():
		_fail("no renderable stations (empty scene bounds)")
		return

	var all_ok := true
	for s in stations:
		var st: Dictionary = await _shoot(s)
		_result["stations"].append(st)
		all_ok = all_ok and st.get("ok", false)
	_result["ok"] = all_ok
	_finish()


func _scene_bounds(site: Node) -> AABB:
	var box := AABB()
	var first := true
	for n in _walk(site):
		if n is VisualInstance3D:
			var a: AABB = (n as VisualInstance3D).global_transform \
				* (n as VisualInstance3D).get_aabb()
			if first:
				box = a
				first = false
			else:
				box = box.merge(a)
	return box


func _walk(n: Node) -> Array:
	var out: Array = [n]
	for c in n.get_children():
		out.append_array(_walk(c))
	return out


func _stations(b: AABB) -> Array:
	## Canonical viewpoints. Exterior proves the massing reads; each ladder gets
	## an approach shot and a top-of-climb shot, because the two places a
	## package most often looks broken are the wall a ladder is bolted to and
	## the floor you arrive on.
	var c: Vector3 = b.get_center()
	var out: Array = []
	if b.size.length() < 0.01:
		return out
	var d: float = maxf(b.size.x, b.size.z)
	out.append({
		"name": "exterior",
		"eye": c + Vector3(d * 0.8, b.size.y * 0.6, d * 0.8),
		"look": c,
		"interior": false,
	})
	for node in get_nodes_in_group("ladder_area3d"):
		var l: Area3D = node as Area3D
		if l == null:
			continue
		var lt: Transform3D = l.global_transform
		var climb_h: float = float(l.get_meta("climb_height", 3.0))
		var outv: Vector3 = lt.basis.z.normalized()
		out.append({
			"name": "%s_base" % l.name,
			"eye": lt.origin + outv * 3.0 + Vector3.UP * EYE,
			"look": lt.origin + Vector3.UP * (climb_h * 0.5),
			"interior": true,
		})
		out.append({
			"name": "%s_top" % l.name,
			"eye": lt.origin + outv * 1.2 + Vector3.UP * (climb_h + EYE),
			"look": lt.origin + outv * 8.0 + Vector3.UP * (climb_h + EYE),
			"interior": true,
		})
	return out


func _shoot(s: Dictionary) -> Dictionary:
	var st := {"station": String(s["name"]), "ok": false,
			   "interior": bool(s["interior"])}
	var eye: Vector3 = s["eye"]
	var look: Vector3 = s["look"]

	var a: Image = await _frame(eye, look)
	var b: Image = await _frame(eye + Vector3(JITTER, JITTER, JITTER), look)
	if a == null or b == null:
		st["error"] = "no frame captured"
		return st

	var png: String = "%s/%s.png" % [_shots_dir, s["name"]]
	a.save_png(png)
	st["png"] = png
	st["void_pct"] = snappedf(_void_fraction(a) * 100.0, 0.01)
	var jd: Dictionary = _jitter_diff(a, b)
	st["jitter_pct"] = snappedf(float(jd["pct"]) * 100.0, 0.01)
	if float(jd["pct"]) > 0.0:
		st["jitter_worst_px"] = jd["worst"]
	# Only jitter is a verdict. Void is reported, never gated: an open rooftop
	# station is legitimately most sky, and a threshold that has to know which
	# is which would be guessing.
	st["ok"] = float(jd["pct"]) * 100.0 <= JITTER_FAIL_PCT
	if not st["ok"]:
		st["reason"] = ("%.2f%% of pixels flip when the camera moves 1 mm -- "
			+ "coplanar surfaces are fighting for the depth test here; open "
			+ "%s and look for a shimmering face") % [
				float(jd["pct"]) * 100.0, png]
	return st


func _frame(eye: Vector3, look: Vector3) -> Image:
	_cam.global_position = eye
	var to: Vector3 = look - eye
	if to.length() > 0.001:
		var up: Vector3 = Vector3.UP
		if absf(to.normalized().dot(Vector3.UP)) > 0.98:
			up = Vector3.FORWARD
		_cam.look_at(look, up)
	await process_frame
	await RenderingServer.frame_post_draw
	var tex: ViewportTexture = root.get_texture()
	return tex.get_image() if tex else null


func _void_fraction(img: Image) -> float:
	var w: int = img.get_width()
	var h: int = img.get_height()
	var n := 0
	var y := 0
	while y < h:
		var x := 0
		while x < w:
			var p: Color = img.get_pixel(x, y)
			if absf(p.r - VOID.r) < VOID_TOL and absf(p.g - VOID.g) < VOID_TOL \
					and absf(p.b - VOID.b) < VOID_TOL:
				n += 1
			x += 2
		y += 2
	return float(n) / float(int(w / 2.0) * int(h / 2.0))


func _jitter_diff(a: Image, b: Image) -> Dictionary:
	var w: int = mini(a.get_width(), b.get_width())
	var h: int = mini(a.get_height(), b.get_height())
	var changed := 0
	var total := 0
	var worst := [-1, -1]
	var worst_d := 0
	var y := 0
	while y < h:
		var x := 0
		while x < w:
			var pa: Color = a.get_pixel(x, y)
			var pb: Color = b.get_pixel(x, y)
			var d: int = int(maxf(maxf(absf(pa.r - pb.r), absf(pa.g - pb.g)),
								  absf(pa.b - pb.b)) * 255.0)
			if d > DIFF_TOL:
				changed += 1
				if d > worst_d:
					worst_d = d
					worst = [x, y]
			total += 1
			x += 2
		y += 2
	return {"pct": float(changed) / float(maxi(total, 1)), "worst": worst}


func _fail(msg: String) -> void:
	_result["error"] = msg
	_finish()


func _finish() -> void:
	var text := JSON.stringify(_result, "  ")
	if _out_path != "":
		var f := FileAccess.open(_out_path, FileAccess.WRITE)
		if f:
			f.store_string(text)
			f.close()
	print("[shotbot] " + ("OK" if _result.get("ok", false) else "FAIL"))
	print(text)
	quit(0 if _result.get("ok", false) else 1)
