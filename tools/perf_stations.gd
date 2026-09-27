extends SceneTree
## THE FIXED-STATION PERFORMANCE HARNESS.
##
##     godot --path <package> --script res://perf_stations.gd -- [--out FILE]
##
## Windowed on purpose. Headless draws nothing, so it cannot answer a
## question about frame time; this opens a window, measures, and quits
## itself. A watchdog ends the run whatever happens, because a probe that can
## sit on somebody's desktop is a defect in the probe.
##
## ============================ WHY IT EXISTS ============================
##
## `docs/PERFORMANCE_CONTRACT.md` §10 asks for a permanent benchmark set and
## records that it does not exist. `docs/DRAW_CALL_BUDGET.md` names that as
## the gap which makes every other performance item checkable, because today
## a frame cost is only known when a person walks the level and reads the F4
## overlay out loud. Cold run 9088 was measured exactly that way: eight
## numbers, transcribed from screenshots.
##
## This replaces that with a report per package.
##
## ========================== WHAT IT MEASURES ===========================
##
## Stations come FROM THE PACKAGE, never typed in: `gameplay_anchors.json`
## already carries the places a player will be -- spawns, objectives,
## extraction, camera sockets -- with world positions. A station typed into a
## probe goes stale the first time the generator moves something, and this
## repo has already spent a session believing coordinates carried forward on
## faith.
##
## At each station the camera takes HEADINGS, because cost depends far more
## on facing than on standing: cold run 9088 read 1,091 draw calls in one
## direction and 5,739 in another, in the same level. A station reported as
## one number is a station measured facing an arbitrary way. The worst
## heading is what gets reported, and the median across headings beside it.
##
## Per sample:
##
##   * FRAME TIME measured HERE, off `_process` deltas, over a window --
##     median, p95 and worst. `Performance.TIME_FPS` and
##     `Engine.get_frames_per_second()` refresh ONCE A SECOND (measured:
##     one value held across 300 consecutive frames), so anything built on
##     them is up to a second stale and cannot show a stutter.
##     `Performance.TIME_PROCESS` is not this frame's CPU time either -- it
##     is the worst idle step in the last completed second, and a 60 ms stall
##     was still being reported 285 frames later.
##   * DRAW CALLS, PRIMITIVES, OBJECTS from the render monitors, which DO
##     work in Compatibility (verified moving 2 -> 2,900 objects).
##   * GPU and RENDER-CPU from
##     `RenderingServer.viewport_get_measured_render_time_{gpu,cpu}`, which
##     return real figures in Compatibility once
##     `viewport_set_measure_render_time` is on.
##
## Both facts above are `assets/godot/debug_overlay.gd`'s, measured there and
## reused here rather than rediscovered.
##
## Once per package, not per station: the LIGHTS-PER-OBJECT histogram against
## the renderer's `max_lights_per_object`. Merging and instancing both trade
## draw calls for lighting fidelity, so a change that improves this report's
## draw column can silently darken interiors; the two belong in one report.
## Cold run 9088: 34 of 4,625 meshes over the cap of 8, worst a 47 m roof
## reached by 47 lights.
##
## ============================== NOT THIS ===============================
##
## It does not decide whether a package passes. It prints what it measured
## and the budget it was given, and the caller decides -- the same split
## every other instrument in this repo keeps.

const WATCHDOG_SEC := 600.0
const W := 1280
const H := 720
const WARMUP := 30        ## frames discarded at each sample before measuring
const WINDOW := 60        ## frames measured per sample
## HOW MANY STATIONS. The first run took 29 x 4 x 210 = 24,360 frames
## and hit the watchdog. Capped, and spread ACROSS anchor types rather
## than truncated, so the sample stays representative instead of
## becoming whichever twelve happen to come first in the file.
const MAX_STATIONS := 12
## Frames for the GPU/CPU split, taken with the render timers ON and
## therefore NOT comparable with `ms_*` above. Short on purpose.
const SPLIT_WINDOW := 20
const HEADINGS := 4       ## yaw samples per station
const EYE_H := 1.6        ## a standing body's eye height above the anchor
const EPS := 0.0001

## Which anchor types are worth standing at. `cover` is excluded: there are 27
## of them and they are prop slots, not places a player stands.
const STATION_TYPES := {
	"player_start": true, "crew_spawn": true, "objective": true,
	"extraction": true, "attacker_spawn": true, "defender_spawn": true,
	"camera_socket": true, "patrol_point": true,
}

var _vp_rid: RID
var _rows: Array = []
var _complete: bool = false
var _geometry: Dictionary = {}
var _all_candidates: Array = []
var _out_path: String = "user://perf_stations.json"


func _initialize() -> void:
	_run()
	_watchdog()


func _watchdog() -> void:
	var t0: int = Time.get_ticks_msec()
	while true:
		await process_frame
		if Time.get_ticks_msec() - t0 > int(WATCHDOG_SEC * 1000.0):
			print("[perf] WATCHDOG: %.0f s elapsed, quitting" % WATCHDOG_SEC)
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


## The nearest point of `mi`'s box to `p`, in world metres, computed in the
## mesh's own frame -- transforming eight corners and re-boxing them inflates
## the box under rotation. An AABB is a SUPERSET of the mesh, so this can
## under-report a distance and never over-report one, which is the safe
## direction for "does this light reach this mesh".
func _surface_dist(mi: MeshInstance3D, p: Vector3) -> float:
	var lp: Vector3 = mi.global_transform.affine_inverse() * p
	var ab: AABB = mi.get_aabb()
	var q := Vector3(
		clampf(lp.x, ab.position.x, ab.position.x + ab.size.x),
		clampf(lp.y, ab.position.y, ab.position.y + ab.size.y),
		clampf(lp.z, ab.position.z, ab.position.z + ab.size.z))
	return (mi.global_transform * q).distance_to(p)


func _reach(l: Light3D) -> float:
	var sp: SpotLight3D = l as SpotLight3D
	if sp != null:
		return sp.spot_range
	var om: OmniLight3D = l as OmniLight3D
	if om != null:
		return om.omni_range
	return 0.0


func _pct(sorted_vals: Array, q: float) -> float:
	if sorted_vals.is_empty():
		return 0.0
	var i: int = clampi(int(float(sorted_vals.size() - 1) * q), 0,
		sorted_vals.size() - 1)
	return float(sorted_vals[i])


## Read the package's own station list. Returns [{name, pos}].
func _stations() -> Array:
	var out: Array = []
	if not FileAccess.file_exists("res://gameplay_anchors.json"):
		return out
	var txt: String = FileAccess.get_file_as_string("res://gameplay_anchors.json")
	var doc = JSON.parse_string(txt)
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
		# one station per place: several anchor types land on one spot and
		# measuring the same view four times is not four measurements
		var key: String = "%.1f_%.1f_%.1f" % [v.x, v.y, v.z]
		if seen.has(key):
			continue
		seen[key] = true
		out.append({"name": "%s_%d" % [t, out.size()], "pos": v, "type": t})
	_all_candidates = out.duplicate()
	return _spread(out)


## Take at most MAX_STATIONS, round-robin across anchor types, so a
## level with 27 attacker spawns and one player start does not report
## twelve attacker spawns.
func _spread(all: Array) -> Array:
	if all.size() <= MAX_STATIONS:
		return all
	var by: Dictionary = {}
	for s in all:
		var k: String = String(s["type"])
		if not by.has(k):
			by[k] = []
		(by[k] as Array).append(s)
	var keys: Array = by.keys()
	keys.sort()
	var out: Array = []
	var i: int = 0
	while out.size() < MAX_STATIONS:
		var took := false
		for k in keys:
			var lst: Array = by[k]
			if i < lst.size() and out.size() < MAX_STATIONS:
				out.append(lst[i])
				took = true
		if not took:
			break
		i += 1
	return out


## The highest position a player can stand at, from the anchors -- the
## package ships no navmesh, and a rooftop nobody can reach is not a
## vantage. Ties go to the first found, which is deterministic because
## the anchor file is.
func _highest_vantage(cands: Array) -> Dictionary:
	var best: Dictionary = {}
	for c in cands:
		if best.is_empty() or (c["pos"] as Vector3).y > (best["pos"] as Vector3).y:
			best = c
	if best.is_empty():
		return {}
	return {"name": "highest_vantage", "pos": best["pos"],
		"type": "derived", "from": best["name"]}


## From every candidate, on 16 headings at eye height, the longest clear
## ray against the package's own collision. The station and heading that
## see furthest ARE the sightline. Glass has no collider, so a window
## reads as open; a wall reads as a wall. Reported with the distance so a
## reader can tell a 40 m street from a 200 m boundary-to-boundary view.
func _longest_sightline(cands: Array, scene: Node) -> Dictionary:
	var space: PhysicsDirectSpaceState3D = (scene.get_viewport() as Viewport) \
		.find_world_3d().direct_space_state
	var best_d: float = -1.0
	var best: Dictionary = {}
	var reach: float = 500.0
	var escapes: int = 0
	for c in cands:
		var eye: Vector3 = (c["pos"] as Vector3) + Vector3.UP * EYE_H
		for h in range(16):
			var yaw: float = 360.0 * float(h) / 16.0
			var dir := Vector3(-sin(deg_to_rad(yaw)), 0.0, -cos(deg_to_rad(yaw)))
			var q := PhysicsRayQueryParameters3D.create(eye, eye + dir * reach)
			var hit: Dictionary = space.intersect_ray(q)
			# A MISS IS AN ESCAPE, NOT A SIGHTLINE. The first run ranked a 500 m
			# ray from a camera socket at yaw 0 as the longest sightline: it hit
			# nothing, because a 4.6 m eye clears the perimeter wall, and it
			# measured 260 draws of void. A sightline is the longest ray that
			# LANDS on something. Escapes are counted and reported apart, since a
			# ray leaving the map is a finding about the boundary, not a view.
			if hit.is_empty():
				escapes += 1
				continue
			var d: float = eye.distance_to(hit["position"] as Vector3)
			if d > best_d:
				best_d = d
				best = {"name": "longest_sightline", "pos": c["pos"],
					"type": "derived", "from": c["name"], "yaw": yaw,
					"sightline_m": d}
	if not best.is_empty():
		print("[perf] longest sightline: %.1f m from %s at yaw %.0f  (%d ray(s) left the map)"
			% [best_d, String(best["from"]), float(best["yaw"]), escapes])
		best["rays_escaped"] = escapes
	return best


func _sample(cam: Camera3D, eye: Vector3, yaw: float) -> Dictionary:
	cam.global_position = eye
	cam.rotation = Vector3(0.0, deg_to_rad(yaw), 0.0)
	await _settle(WARMUP)
	# PASS A -- TIMERS OFF. `viewport_set_measure_render_time` inserts GPU
	# timestamp queries every frame and costs real time: with it on, this
	# harness read 109 ms p95 at 3,025 draws where a walk copy of the same
	# level read 23 ms at 5,287. `debug_overlay.gd` turns it on only while
	# its panel is up, for the same reason. Frame time is the number the
	# budget is spent against, so it is the one measured undisturbed.
	RenderingServer.viewport_set_measure_render_time(_vp_rid, false)
	await _settle(4)
	var ms: Array = []
	var gpu_tot := 0.0
	var rcpu_tot := 0.0
	var draws := 0
	var prims := 0
	var objs := 0
	var last: int = Time.get_ticks_usec()
	for i in range(WINDOW):
		await process_frame
		var now: int = Time.get_ticks_usec()
		ms.append(float(now - last) / 1000.0)
		last = now
		draws = maxi(draws, int(Performance.get_monitor(
			Performance.RENDER_TOTAL_DRAW_CALLS_IN_FRAME)))
		prims = maxi(prims, int(Performance.get_monitor(
			Performance.RENDER_TOTAL_PRIMITIVES_IN_FRAME)))
		objs = maxi(objs, int(Performance.get_monitor(
			Performance.RENDER_TOTAL_OBJECTS_IN_FRAME)))
	# PASS B -- TIMERS ON, short. The GPU/CPU split is worth having and is
	# only available through the perturbing path, so it is taken
	# separately and labelled. Do not add these two to compare them
	# against `ms_p95`: they were measured in a different world.
	RenderingServer.viewport_set_measure_render_time(_vp_rid, true)
	await _settle(8)
	for i in range(SPLIT_WINDOW):
		await process_frame
		gpu_tot += RenderingServer.viewport_get_measured_render_time_gpu(_vp_rid)
		rcpu_tot += RenderingServer.viewport_get_measured_render_time_cpu(_vp_rid)
	RenderingServer.viewport_set_measure_render_time(_vp_rid, false)
	ms.sort()
	return {
		"yaw": yaw,
		"ms_median": _pct(ms, 0.5), "ms_p95": _pct(ms, 0.95),
		"ms_worst": float(ms[ms.size() - 1]),
		"gpu_ms": gpu_tot / float(SPLIT_WINDOW),
		"render_cpu_ms": rcpu_tot / float(SPLIT_WINDOW),
		"split_perturbed": true,
		"draws": draws, "primitives": prims, "objects": objs,
	}


## Lights per mesh against the renderer's cap. One pass for the package.
func _light_census(nodes: Array, cap: int) -> Dictionary:
	var lights: Array = []
	var meshes: Array = []
	for n in nodes:
		var l: Light3D = n as Light3D
		if l != null:
			if not (l is DirectionalLight3D):
				lights.append(l)
			continue
		var mi: MeshInstance3D = n as MeshInstance3D
		if mi != null and mi.visible and mi.mesh != null:
			meshes.append(mi)
	var over: int = 0
	var worst: int = 0
	var worst_name: String = "-"
	for m in meshes:
		var mi2: MeshInstance3D = m as MeshInstance3D
		var n_reach: int = 0
		for o in lights:
			var ol: Light3D = o as Light3D
			if _surface_dist(mi2, ol.global_position) <= _reach(ol):
				n_reach += 1
		if n_reach > cap:
			over += 1
		if n_reach > worst:
			worst = n_reach
			worst_name = String(mi2.name)
	return {"cap": cap, "lights": lights.size(), "meshes": meshes.size(),
		"over_cap": over, "worst": worst, "worst_mesh": worst_name}


func _write() -> void:
	var f := FileAccess.open(_out_path, FileAccess.WRITE)
	if f == null:
		print("[perf] REFUSED: cannot write %s" % _out_path)
		return
	# `complete` IS THE POINT OF THIS FIELD. The first run's watchdog fired,
	# this wrote what it had, and the caller printed 'every station inside
	# budget' over a truncated report. A partial result that cannot say it
	# is partial is worse than no result.
	f.store_string(JSON.stringify({"schema": "level_factory.perf_stations.v1",
		"complete": _complete, "geometry": _geometry, "rows": _rows}, "  "))
	f.close()
	print("[perf] wrote %s" % ProjectSettings.globalize_path(_out_path))


func _run() -> void:
	await process_frame
	_out_path = _arg("--out", _out_path)
	DisplayServer.window_set_size(Vector2i(W, H))
	root.content_scale_size = Vector2i(W, H)
	# VSYNC OFF, or every station under the refresh rate reports the refresh
	# rate and the report says the level is fine at exactly 60 FPS everywhere.
	DisplayServer.window_set_vsync_mode(DisplayServer.VSYNC_DISABLED)
	_vp_rid = root.get_viewport_rid()
	RenderingServer.viewport_set_measure_render_time(_vp_rid, true)

	var main_path: String = String(ProjectSettings.get_setting(
		"application/run/main_scene", ""))
	var packed: PackedScene = load(main_path) as PackedScene
	if packed == null:
		print("[perf] REFUSED: no main scene at %s" % main_path)
		_exit(2)
		return
	var scene: Node = packed.instantiate()
	current_scene = scene
	root.add_child(scene)
	await _settle(60)

	var nodes: Array = []
	_walk(scene, nodes)
	# A PACKAGE HAS NO PLAYER, but a walk copy does, and its camera stays
	# current however many times a probe calls make_current() on its own --
	# measured on three separate copies, each reporting the view from the
	# spawn while the probe believed it stood elsewhere. Remove the body so
	# the probe's camera is the only one left.
	for n in nodes:
		var body: CharacterBody3D = n as CharacterBody3D
		if body != null:
			body.get_parent().remove_child(body)
			body.queue_free()
			print("[perf] removed a walk player so its camera stops winning")
			break

	var stations: Array = _stations()
	# THE TWO THE BIBLE NAMES AND ANCHORS DO NOT GIVE. Appended after the
	# spread so the cap never displaces them.
	var vantage: Dictionary = _highest_vantage(_all_candidates)
	if not vantage.is_empty():
		stations.append(vantage)
	var sight: Dictionary = await _longest_sightline(_all_candidates, scene)
	if not sight.is_empty():
		stations.append(sight)
	if stations.is_empty():
		print("[perf] REFUSED: no stations -- gameplay_anchors.json absent or")
		print("[perf] carried no anchor of a type worth standing at. A report")
		print("[perf] over zero stations is not a clean report.")
		_exit(2)
		return

	var cam := Camera3D.new()
	cam.fov = 75.0
	cam.far = 500.0
	cam.current = true
	root.add_child(cam)
	cam.make_current()
	cam.global_position = (stations[0]["pos"] as Vector3) + Vector3.UP * EYE_H
	await _settle(60)
	if root.get_camera_3d() != cam:
		print("[perf] REFUSED: the rendering camera is not the probe's")
		_exit(2)
		return
	# A FRAME THAT NEVER DREW is not a fast frame. The first read of a run is
	# black regardless of how long you wait, and this repo has twice nearly
	# proved a false answer from one.
	var drew := false
	for i in range(30):
		await _settle(10)
		if int(Performance.get_monitor(
				Performance.RENDER_TOTAL_DRAW_CALLS_IN_FRAME)) > 0:
			drew = true
			break
	if not drew:
		print("[perf] REFUSED: no draw calls recorded; nothing was rendered")
		_exit(2)
		return

	# DID THE LEVEL ACTUALLY LOAD? A portable package ships sidecars and
	# no import cache; run without importing it once and every GLB fails
	# to load silently, leaving the dressing MultiMeshes alone on screen.
	# That is what the first run measured: 4 draw calls and 844,430
	# primitives at all 29 stations, reported as a pass. No threshold is
	# needed to catch it -- a level with no MeshInstance3D at all is
	# broken, not fast.
	var n_mesh: int = 0
	var n_multi: int = 0
	for n in nodes:
		if n is MeshInstance3D:
			n_mesh += 1
		elif n is MultiMeshInstance3D:
			n_multi += 1
	_geometry = {"mesh_instances": n_mesh, "multimesh_instances": n_multi,
		"nodes": nodes.size()}
	print("[perf] geometry: %d MeshInstance3D, %d MultiMeshInstance3D, %d nodes"
		% [n_mesh, n_multi, nodes.size()])
	if n_mesh == 0:
		print("[perf] REFUSED: not one MeshInstance3D in the scene. A")
		print("[perf] portable package ships sidecars and no import cache;")
		print("[perf] run `godot --headless --path <pkg> --import` once")
		print("[perf] before measuring it, or nothing but the dressing")
		print("[perf] MultiMeshes will load and the report will read fast.")
		_write()
		_exit(2)
		return
	var cap: int = int(ProjectSettings.get_setting(
		"rendering/limits/opengl/max_lights_per_object", 8))
	var census: Dictionary = _light_census(nodes, cap)

	# WARM EVERY STATION FIRST. Without this each station is measured on
	# first sight and pays for whatever it reveals -- shader variants,
	# texture residency, the package's own warm-up stations. The contract
	# (§3) separates cold launch from warm repeat, and this harness is the
	# warm-repeat instrument. The worst frame seen while warming is kept
	# rather than thrown away, because a first-sight stall is something a
	# player feels.
	RenderingServer.viewport_set_measure_render_time(_vp_rid, false)
	var cold_worst := 0.0
	var t_prev: int = Time.get_ticks_usec()
	for s0 in stations:
		for h0 in range(HEADINGS):
			cam.global_position = (s0["pos"] as Vector3) + Vector3.UP * EYE_H
			cam.rotation = Vector3(0.0, TAU * float(h0) / float(HEADINGS), 0.0)
			for i in range(10):
				await process_frame
				var t_now: int = Time.get_ticks_usec()
				cold_worst = maxf(cold_worst, float(t_now - t_prev) / 1000.0)
				t_prev = t_now
	print("[perf] warmed %d station(s); worst frame while warming %.1f ms"
		% [stations.size(), cold_worst])
	_geometry["cold_worst_ms"] = cold_worst
	print("[perf] %d station(s) x %d heading(s), %d frames each after %d warmup"
		% [stations.size(), HEADINGS, WINDOW, WARMUP])
	for s in stations:
		var eye: Vector3 = (s["pos"] as Vector3) + Vector3.UP * EYE_H
		var per: Array = []
		# a derived station may carry the ONE heading that defines it
		var yaws: Array = [float(s["yaw"])] if s.has("yaw") else []
		if yaws.is_empty():
			for h in range(HEADINGS):
				yaws.append(360.0 * float(h) / float(HEADINGS))
		for yaw in yaws:
			per.append(await _sample(cam, eye, yaw))
		# THE WORST HEADING IS THE STATION. A player looks where they like,
		# and the median across headings hides the view that drops the frame.
		per.sort_custom(func(a, b): return float(a["ms_p95"]) > float(b["ms_p95"]))
		var worst: Dictionary = per[0]
		var med_ms: float = 0.0
		for p in per:
			med_ms += float(p["ms_p95"])
		med_ms /= float(per.size())
		_rows.append({"station": s["name"], "type": s["type"],
			"pos": [eye.x, eye.y, eye.z], "worst_heading": worst,
			"mean_p95_over_headings": med_ms, "headings": per,
			"light_census": census})
		print("  %-22s worst yaw %3.0f  p95 %6.2f ms  draws %5d  prim %9d  gpu %5.2f  rcpu %5.2f"
			% [String(s["name"]).left(22), worst["yaw"], worst["ms_p95"],
				worst["draws"], worst["primitives"], worst["gpu_ms"],
				worst["render_cpu_ms"]])

	print("[perf] lights per object: cap %d, %d of %d mesh(es) over it, worst %d (%s)"
		% [census["cap"], census["over_cap"], census["meshes"],
			census["worst"], census["worst_mesh"]])
	_complete = true
	_write()
	_exit(0)
