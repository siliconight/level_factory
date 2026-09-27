extends SceneTree
## WHERE DO THE DRAW CALLS COME FROM? Attribute them, do not guess.
##
##     godot --path <package> --script res://draw_attrib.gd -- [--out FILE]
##
## Windowed: the draw-call monitor counts what was submitted, and headless
## submits nothing. A watchdog quits the run whatever happens.
##
## ============================== THE QUESTION ==========================
##
## `perf_stations_run.py` reports cold run 9088's package at 2,056-3,710 draw
## calls across twelve stations, every one over the 2,000 guardrail in
## `docs/DRAW_CALL_BUDGET.md`. Nothing says WHAT is submitting them.
## `CLAUDE.md`: account for every item in a gate's output before patching
## it -- a count split three ways looked like one defect with one number
## wrong, and fixing the obvious third of it would have left two findings
## after a 58-minute sweep.
##
## ============================== THE MODEL =============================
##
## A draw call is, to a first approximation, one SURFACE of one visible
## object. So for each station this counts the surfaces of every
## MeshInstance3D whose world AABB survives the camera frustum, plus one per
## surface per MultiMesh, and groups them by where they came from.
##
## THE MODEL IS CHECKED, NOT TRUSTED. Every station reports PREDICTED
## against the engine's own `RENDER_TOTAL_DRAW_CALLS_IN_FRAME`. A model that
## does not track the instrument is not an attribution, it is a story, and
## the ratio is printed on every row so a reader can see how much of the
## frame it explains. Two reasons it will not reach 1.00, both worth knowing
## rather than hiding:
##
##   * OCCLUSION CULLING removes objects the frustum keeps, so the frustum
##     count is a SUPERSET -- predicted should run HIGH.
##   * SHADOW PASSES resubmit geometry per shadow-casting light, so the real
##     count can run high instead.
##
## Which way the gap falls is therefore itself a finding, and the run prints
## the shadow-caster count beside it so the two can be told apart.
##
## THE GROUPING IS BY ORIGIN, because that is what a fix acts on: the GLB a
## node was instanced from, else the nearest named ancestor. "37% of this
## frame is cover props" is actionable; "4,625 meshes" is not.

const WATCHDOG_SEC := 600.0
const W := 1280
const H := 720
const HEADINGS := 4
const EYE_H := 1.6
const SETTLE := 12
const MAX_STATIONS := 3
const TOP_N := 10

const STATION_TYPES := {
	"player_start": true, "crew_spawn": true, "objective": true,
	"extraction": true, "attacker_spawn": true, "camera_socket": true,
}

var _out_path: String = "user://draw_attrib.json"
var _rows: Array = []
var _complete: bool = false


func _initialize() -> void:
	_run()
	_watchdog()


func _watchdog() -> void:
	var t0: int = Time.get_ticks_msec()
	while true:
		await process_frame
		if Time.get_ticks_msec() - t0 > int(WATCHDOG_SEC * 1000.0):
			print("[attrib] WATCHDOG")
			_write()
			_exit(2)
			return


func _settle(n: int) -> void:
	for i in range(n):
		await process_frame


func _walk(n: Node, out: Array) -> void:
	out.append(n)
	for c in n.get_children():
		_walk(c, out)




## AN EXIT THAT CANNOT BE REFUSED. `quit()` asks the main loop to stop at
## the end of the frame; it cannot close an in-engine modal dialog, and a
## probe has raised one on the walker's desktop twice (CLAUDE.md, GDScript
## section). So: ask, allow two frames for the loop to honour it, and if a
## third frame ever arrives, end the process outright. A normal exit never
## gets past the awaits -- the loop has stopped -- so this costs nothing
## on the path that works and is the only thing that works on the path
## that does not.
##
## The exit code is lost on the kill path. Callers that need a verdict
## read the report's `complete` flag, not the code, for exactly this
## reason.
func _exit(code: int) -> void:
	quit(code)
	await process_frame
	await process_frame
	OS.kill(OS.get_process_id())

func _arg(name: String, fallback: String) -> String:
	var args: PackedStringArray = OS.get_cmdline_user_args()
	for i in range(args.size()):
		if args[i] == name and i + 1 < args.size():
			return args[i + 1]
	return fallback


## Where a node came from, as something a person can act on. The scene file
## it was instanced from is the best answer; a node with none takes the
## nearest ancestor that has one, then its own top-level parent name.
func _origin(n: Node) -> String:
	var p: Node = n
	while p != null:
		var sp: String = String(p.scene_file_path)
		if not sp.is_empty():
			var f: String = sp.get_file().get_basename()
			# prop_streetlight_delco_1997_01_w70_d30_h600 -> prop_streetlight
			var parts: PackedStringArray = f.split("_")
			if parts.size() >= 2 and parts[0] == "prop":
				return "prop_" + parts[1]
			return f
		p = p.get_parent()
	# no instanced ancestor: name the branch it hangs off
	var q: Node = n
	var last: String = String(n.name)
	while q != null and q.get_parent() != null:
		last = String(q.name)
		q = q.get_parent()
	return "scene:" + last


## SUBMISSIONS, NOT SURFACES. A surface whose material carries `next_pass`
## is drawn again for every pass in the chain, and this project ships them
## -- the CRT screen-roll pass, Patina's decal work. Counting mesh surfaces
## alone predicted 0.44 of the frame at the dearest station while shadows
## accounted for only 13% of it, and the guide the walker supplied names
## exactly this: "count actual passes, not only mesh nodes".
##
## Also tallies the chain depth so the report can say how much of the gap
## the passes explain rather than leaving it as a correction nobody can see.
var _pass_extra: int = 0


func _passes(gi: GeometryInstance3D, mesh: Mesh) -> int:
	var n: int = maxi(1, mesh.get_surface_count())
	var total: int = 0
	for i in range(n):
		var m: Material = gi.get_active_material(i)
		var depth: int = 1
		while m != null and m.next_pass != null and depth < 8:
			depth += 1
			m = m.next_pass
		total += depth
		_pass_extra += depth - 1
	return total


## Is any part of `ab` on the inside of every frustum plane? Godot's planes
## face inward, so a box wholly behind any one of them is out. This is the
## standard conservative test: it can keep a box the camera cannot quite
## see, never drop one it can.
## CALIBRATED, NOT ASSUMED. Godot's frustum plane normals point inward or
## outward depending on which corner of the docs you read, and getting it
## backwards rejects the entire level silently -- the first run of this probe
## reported "predicted 0 surfaces on 0 objects" at all eight stations while
## the engine was drawing four thousand. `_inside_sign` is worked out from a
## point that MUST be inside the frustum, so the test cannot be wrong about
## a convention it never states.
var _sign: float = 0.0


func _calibrate(cam: Camera3D, planes: Array) -> void:
	# a point on the camera's axis, comfortably between near and far
	var ref: Vector3 = cam.global_position 		+ (-cam.global_transform.basis.z) * (cam.near + cam.far) * 0.05
	var pos := 0
	for pl in planes:
		if (pl as Plane).distance_to(ref) >= 0.0:
			pos += 1
	# inside means the same sign against every plane; whichever sign the
	# reference point scores is the inside
	_sign = 1.0 if pos >= planes.size() - pos else -1.0
	print("[attrib] frustum calibration: reference point is positive against "
		+ "%d of %d plane(s) -> inside is %s"
		% [pos, planes.size(), "positive" if _sign > 0.0 else "negative"])


func _in_frustum(planes: Array, ab: AABB) -> bool:
	for pl in planes:
		var p: Plane = pl
		# the box vertex furthest toward the inside of this plane; if even
		# that one is on the outside, every vertex is
		if _sign * p.distance_to(ab.get_support(p.normal * _sign)) < 0.0:
			return false
	return true


func _write() -> void:
	var f := FileAccess.open(_out_path, FileAccess.WRITE)
	if f == null:
		print("[attrib] REFUSED: cannot write %s" % _out_path)
		return
	f.store_string(JSON.stringify({"schema": "level_factory.draw_attrib.v1",
		"complete": _complete, "rows": _rows}, "  "))
	f.close()
	print("[attrib] wrote %s" % ProjectSettings.globalize_path(_out_path))


func _stations() -> Array:
	var out: Array = []
	if not FileAccess.file_exists("res://gameplay_anchors.json"):
		return out
	var doc = JSON.parse_string(
		FileAccess.get_file_as_string("res://gameplay_anchors.json"))
	if typeof(doc) != TYPE_DICTIONARY or not doc.has("anchors"):
		return out
	var seen: Dictionary = {}
	for a in doc["anchors"]:
		if typeof(a) != TYPE_DICTIONARY:
			continue
		var t: String = String(a.get("anchor_type", ""))
		if not STATION_TYPES.has(t):
			continue
		var tr = a.get("transform")
		if typeof(tr) != TYPE_DICTIONARY:
			continue
		var p = tr.get("pos")
		if typeof(p) != TYPE_ARRAY or (p as Array).size() < 3:
			continue
		var v := Vector3(float(p[0]), float(p[1]), float(p[2]))
		var key: String = "%.1f_%.1f_%.1f" % [v.x, v.y, v.z]
		if seen.has(key):
			continue
		seen[key] = true
		out.append({"name": "%s_%d" % [t, out.size()], "pos": v})
		if out.size() >= MAX_STATIONS:
			break
	return out


func _run() -> void:
	await process_frame
	_out_path = _arg("--out", _out_path)
	DisplayServer.window_set_size(Vector2i(W, H))
	root.content_scale_size = Vector2i(W, H)
	DisplayServer.window_set_vsync_mode(DisplayServer.VSYNC_DISABLED)

	var packed: PackedScene = load(String(ProjectSettings.get_setting(
		"application/run/main_scene", ""))) as PackedScene
	if packed == null:
		print("[attrib] REFUSED: no main scene")
		_exit(2)
		return
	# THE ENGINE'S OWN LOAD PATH. `current_scene = scene` before `add_child`
	# is REFUSED outright -- "Condition p_scene->get_parent() != root is
	# true" -- so the assignment silently did nothing, and several probes in
	# this investigation drew conclusions from a scene whose current_scene
	# was null. `change_scene_to_packed` is how a main scene is loaded and
	# it sets current_scene itself.
	change_scene_to_packed(packed)
	await _settle(90)
	var scene: Node = current_scene
	if scene == null:
		print("[attrib] REFUSED: the scene never became current")
		_exit(2)
		return

	var nodes: Array = []
	_walk(scene, nodes)
	for n in nodes:
		var body: CharacterBody3D = n as CharacterBody3D
		if body != null:
			body.get_parent().remove_child(body)
			body.queue_free()
			break

	# the geometry, gathered once with its origin resolved once
	var items: Array = []
	var shadow_casters: int = 0
	for n in nodes:
		var l: Light3D = n as Light3D
		if l != null and not (l is DirectionalLight3D) and l.shadow_enabled:
			shadow_casters += 1
		var gi: GeometryInstance3D = n as GeometryInstance3D
		if gi == null or not gi.visible:
			continue
		var surfaces: int = 0
		var mi: MeshInstance3D = gi as MeshInstance3D
		var mm: MultiMeshInstance3D = gi as MultiMeshInstance3D
		if mi != null and mi.mesh != null:
			surfaces = _passes(mi, mi.mesh)
		elif mm != null and mm.multimesh != null and mm.multimesh.mesh != null:
			surfaces = _passes(mm, mm.multimesh.mesh)
		else:
			continue
		items.append({"node": gi, "surf": surfaces, "origin": _origin(gi)})
	# built first, then formatted -- a format split across `+` is a gdcheck trap
	var _summary := "[attrib] %d drawable(s), %d shadow-casting local light(s), %d extra pass(es) from next_pass chains"
	print(_summary % [items.size(), shadow_casters, _pass_extra])
	if items.is_empty():
		print("[attrib] REFUSED: nothing drawable. A portable package ships")
		print("[attrib] sidecars and no import cache -- import it once first.")
		_write()
		_exit(2)
		return

	var stations: Array = _stations()
	if stations.is_empty():
		print("[attrib] REFUSED: no stations in gameplay_anchors.json")
		_write()
		_exit(2)
		return

	var cam := Camera3D.new()
	cam.fov = 75.0
	cam.far = 500.0
	root.add_child(cam)
	cam.make_current()
	cam.global_position = (stations[0]["pos"] as Vector3) + Vector3.UP * EYE_H
	await _settle(40)
	if root.get_camera_3d() != cam:
		print("[attrib] REFUSED: the rendering camera is not the probe's")
		_exit(2)
		return

	for s in stations:
		var eye: Vector3 = (s["pos"] as Vector3) + Vector3.UP * EYE_H
		# the costliest heading is the one worth attributing
		var best_draws: int = -1
		var best_yaw: float = 0.0
		for h in range(HEADINGS):
			var yaw: float = 360.0 * float(h) / float(HEADINGS)
			cam.global_position = eye
			cam.rotation = Vector3(0.0, deg_to_rad(yaw), 0.0)
			await _settle(SETTLE)
			var d: int = int(Performance.get_monitor(
				Performance.RENDER_TOTAL_DRAW_CALLS_IN_FRAME))
			if d > best_draws:
				best_draws = d
				best_yaw = yaw
		cam.global_position = eye
		cam.rotation = Vector3(0.0, deg_to_rad(best_yaw), 0.0)
		await _settle(SETTLE)
		var actual: int = int(Performance.get_monitor(
			Performance.RENDER_TOTAL_DRAW_CALLS_IN_FRAME))

		# WHAT THE SHADOWS COST, by switching them off rather than by
		# inferring it from the gap. The frustum model explains 1.04 of the
		# frame at the cheapest station and 0.44 at the dearest, and the
		# excess grows exactly where cost grows -- which points at extra
		# passes, but pointing is not measuring. Twelve local lights is a
		# cheap thing to toggle, unlike the 4,625 meshes.
		# LOCAL LIGHTS FIRST, then the DIRECTIONAL on its own. The first
		# version excluded the directional and found local shadows worth only
		# 10-13% while half the frame stayed unexplained -- and the ratio of
		# actual-without-local-shadows to visible surfaces came out at 1.95,
		# 1.95, 1.97 across three unrelated views. A clean factor of two is
		# every object being drawn a second time, and the sun's shadow map
		# resubmits every caster in the level. Measured apart so the two
		# cannot be confused.
		var shadow_on: Array = []
		for n2 in nodes:
			var l2: Light3D = n2 as Light3D
			if l2 != null and not (l2 is DirectionalLight3D) and l2.shadow_enabled:
				l2.shadow_enabled = false
				shadow_on.append(l2)
		await _settle(SETTLE)
		var no_shadow: int = int(Performance.get_monitor(
			Performance.RENDER_TOTAL_DRAW_CALLS_IN_FRAME))
		var suns: Array = []
		for n3 in nodes:
			var d3: DirectionalLight3D = n3 as DirectionalLight3D
			if d3 != null and d3.shadow_enabled:
				d3.shadow_enabled = false
				suns.append(d3)
		await _settle(SETTLE)
		var no_sun_shadow: int = int(Performance.get_monitor(
			Performance.RENDER_TOTAL_DRAW_CALLS_IN_FRAME))
		for d4 in suns:
			(d4 as DirectionalLight3D).shadow_enabled = true
		for l3 in shadow_on:
			(l3 as Light3D).shadow_enabled = true
		await _settle(SETTLE)
		var back: int = int(Performance.get_monitor(
			Performance.RENDER_TOTAL_DRAW_CALLS_IN_FRAME))
		# THE CONTROL: restoring must restore. If it does not, the delta is
		# measuring drift rather than shadows and the row says so.
		var drifted: bool = absi(back - actual) > maxi(20, actual / 50)

		var planes: Array = cam.get_frustum()
		if _sign == 0.0:
			_calibrate(cam, planes)
		var by: Dictionary = {}
		var predicted: int = 0
		var visible_objs: int = 0
		for it in items:
			var gi: GeometryInstance3D = it["node"]
			if not is_instance_valid(gi):
				continue
			var ab: AABB = gi.global_transform * gi.get_aabb()
			if not _in_frustum(planes, ab):
				continue
			visible_objs += 1
			predicted += int(it["surf"])
			var k: String = String(it["origin"])
			by[k] = int(by.get(k, 0)) + int(it["surf"])
		var ranked: Array = []
		for k in by.keys():
			ranked.append({"origin": k, "surfaces": int(by[k])})
		ranked.sort_custom(func(a, b): return int(a["surfaces"]) > int(b["surfaces"]))

		_rows.append({"station": s["name"], "yaw": best_yaw,
			"actual_draws": actual, "predicted_surfaces": predicted,
			"visible_objects": visible_objs,
			"draws_without_shadows": no_shadow,
			"draws_without_any_shadows": no_sun_shadow,
			"draws_restored": back, "restore_drifted": drifted,
			"shadow_casters": shadow_casters, "groups": ranked})
		print("")
		# BUILT FIRST, then formatted: `%` binds tighter than `+`, and a format
		# split across a `+` is one of the four traps gdcheck refuses on sight.
		var _line := "[attrib] %s yaw %.0f -- actual %d draws, predicted %d surfaces on %d object(s), model/actual %.2f"
		print(_line % [String(s["name"]), best_yaw, actual, predicted,
			visible_objs, float(predicted) / maxf(float(actual), 1.0)])
		print("[attrib]   local shadows off: %d (%d fewer, %.0f%%)"
			% [no_shadow, actual - no_shadow,
				100.0 * float(actual - no_shadow) / maxf(float(actual), 1.0)])
		print("[attrib]   + sun shadow off: %d (%d fewer, %.0f%% of the frame)%s"
			% [no_sun_shadow, no_shadow - no_sun_shadow,
				100.0 * float(no_shadow - no_sun_shadow) / maxf(float(actual), 1.0),
				"   RESTORE DRIFTED" if drifted else ""])
		print("[attrib]   remaining %d vs %d visible surfaces -- ratio %.2f"
			% [no_sun_shadow, predicted,
				float(no_sun_shadow) / maxf(float(predicted), 1.0)])
		for i in range(mini(TOP_N, ranked.size())):
			var r: Dictionary = ranked[i]
			print("    %6d  %5.1f%%  %s"
				% [int(r["surfaces"]),
					100.0 * float(r["surfaces"]) / maxf(float(predicted), 1.0),
					String(r["origin"]).left(46)])
	_complete = true
	_write()
	_exit(0)
