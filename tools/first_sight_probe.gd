extends Node

## Does a package stall the first time it is seen, and is it compilation?
##
## Two laps of one route, so both questions get answered by one run. If lap 2
## over the same ground is materially smoother than lap 1, the hitching
## belongs to first sight and to a warm-up, not to the level's content. If
## both laps hitch in the same places, it is the content and the fix is fewer
## things drawn (see the draw-call rule in CLAUDE.md).
##
## Per frame it also samples the three renderer memory monitors, the resource
## count and all five PIPELINE_COMPILATIONS_* counters, and the report prints
## the worst frames with the DELTA in each across that frame. A multi-second
## frame that moves texture memory is a resource upload; one that moves
## nothing the counters can see is compilation or a structure build. Under GL
## Compatibility the PIPELINE_COMPILATIONS_* counters read 0 always -- they
## are printed anyway, because a column of zeroes is a reader's evidence that
## they were asked and could not answer.
##
## HOW TO RUN IT, and the part that is easy to get wrong.
##
## Wire it as an autoload in a COPY of the package (never the package -- it
## ships no `.godot` cache, and a walk copy is what `--import` is for):
##
##     [application]
##     run/main_scene="res://<a scene with a current Camera3D>"
##     [autoload]
##     FirstSight="*res://first_sight_probe.gd"
##
## then `godot --path <copy> --resolution 1280x720`. It needs a window --
## headless draws nothing and there is nothing to measure -- so it quits
## itself, and has a watchdog, and must never be launched with `--script`:
## this extends Node, and `--script` demands a SceneTree, which puts a modal
## alert on whoever's desktop this is.
##
## THERE ARE TWO SHADER CACHES AND BOTH HAVE TO BE EMPTY, or the number is
## 20x too small. Measured 2026-09-21 on cold run 9066's package, one probe,
## one package, three cache states:
##
##     both warm                                      worst frame   172 ms
##     Godot's user://shader_cache wiped                            376 ms
##     that, and the NVIDIA driver's GL program cache too         8,641 ms
##
## Godot's lives at `%APPDATA%/Godot/app_userdata/<config/name>/shader_cache`
## and is per PROJECT NAME, so every generated level starts with an empty one.
## The driver's is machine-global; on NVIDIA, redirect it per run with
## `__GL_SHADER_DISK_CACHE_PATH` pointed at an empty directory rather than
## deleting it -- the display driver keeps a handle open on the global one and
## a delete fails with "Device or resource busy" after any hard-killed GL
## process, which reads as a broken harness and is really a run that silently
## was not cold. Check afterwards that the private directory GREW; a cold run
## that wrote no cache was not cold.
##
## Moves the camera rather than driving a body, deliberately: the question is
## what the renderer does as geometry enters view, and a body snagging on a
## kerb would ruin the sample. The six legs sum to zero displacement, so the
## teleport home at the end of a lap is a no-op and lap 2 retraces lap 1.

const WARMUP_FRAMES := 120
const SPEED_MPS := 3.0
const LEG_SECONDS := 6.0
const LAPS := 2
const WATCHDOG_SEC := 420.0

## Performance monitor ids, by number: `Performance.get_monitor_name` does not
## exist, so a run cannot print what it sampled and these are written down
## instead.
const MON_OBJS := 11          # RENDER_TOTAL_OBJECTS_IN_FRAME
const MON_DRAWS := 13         # RENDER_TOTAL_DRAW_CALLS_IN_FRAME
const MON_VIDMEM := 14        # RENDER_VIDEO_MEM_USED
const MON_TEXMEM := 15        # RENDER_TEXTURE_MEM_USED
const MON_BUFMEM := 16        # RENDER_BUFFER_MEM_USED
const MON_RESOURCES := 8      # OBJECT_RESOURCE_COUNT
const MON_PIPE := [34, 35, 36, 37, 38]   # PIPELINE_COMPILATIONS_*

var _cam: Camera3D = null
var _last_usec := 0
var _frames := 0
var _elapsed := 0.0
var _leg := 0
var _lap := 0
var _started := 0.0
var _gate := false
var _gate_frames := 0
var _leg_ms: Array[float] = []
var _leg_calls: Array[float] = []
var _leg_objs: Array[float] = []
var _rows: Array = []
var _worst: Array = []
var _prev: Dictionary = {}

var _legs: Array[Vector3] = [
	Vector3(1, 0, 0), Vector3(0, 0, 1), Vector3(-1, 0, 0), Vector3(0, 0, -1),
	Vector3(1, 0, 1), Vector3(-1, 0, -1),
]
var _home := Vector3.ZERO


func _ready() -> void:
	_started = float(Time.get_ticks_msec()) / 1000.0
	_last_usec = Time.get_ticks_usec()
	await get_tree().process_frame
	_cam = _find_camera(get_tree().root)
	if _cam == null:
		print("[fs] NO CAMERA -- refusing rather than reporting a fast scene")
		get_tree().quit(2)
		return
	_home = _cam.global_position
	# A package that ships its own warm-up owns the frames before play. Wait
	# for it, and keep its sweep out of lap 1: the load cost is the warm-up's
	# own report, and folding the two together would make a fix that moved
	# the cost look like a fix that removed it.
	var w := get_tree().root.find_child("Warmup", true, false)
	if w != null and w.has_signal("warmup_finished"):
		print("[fs] package ships a warm-up; waiting for it")
		w.warmup_finished.connect(_on_package_warm)
		_gate = true
	_prev = _sample()
	print("[fs] camera %s at %s, %d laps of %d legs"
		% [_cam.name, str(_home), LAPS, _legs.size()])


func _on_package_warm(frames: int, msec: float) -> void:
	print("[fs] package warm-up reported %d frame(s) in %.0f ms" % [frames, msec])
	_gate = false
	_last_usec = Time.get_ticks_usec()
	# The warm-up made its own camera current and handed it back; re-find it
	# rather than trusting the one read before the sweep.
	var again := _find_camera(get_tree().root)
	if again != null:
		_cam = again
		_home = _cam.global_position


func _find_camera(n: Node) -> Camera3D:
	if n is Camera3D and (n as Camera3D).current:
		return n as Camera3D
	for c in n.get_children():
		var found := _find_camera(c)
		if found != null:
			return found
	return null


func _sample() -> Dictionary:
	var pipe: float = 0.0
	for m in MON_PIPE:
		pipe += Performance.get_monitor(int(m))
	return {
		"vid": Performance.get_monitor(MON_VIDMEM),
		"tex": Performance.get_monitor(MON_TEXMEM),
		"buf": Performance.get_monitor(MON_BUFMEM),
		"res": Performance.get_monitor(MON_RESOURCES),
		"pipe": pipe,
		"draws": Performance.get_monitor(MON_DRAWS),
	}


func _process(delta: float) -> void:
	var now := Time.get_ticks_usec()
	var ms := float(now - _last_usec) / 1000.0
	_last_usec = now
	if _cam == null:
		return
	if float(Time.get_ticks_msec()) / 1000.0 - _started > WATCHDOG_SEC:
		print("[fs] WATCHDOG -- quitting with a partial report")
		_report()
		get_tree().quit(3)
		return
	if _gate:
		_gate_frames += 1
		# A warm-up that never reports is a defect, not a reason to hang.
		if _gate_frames > 60000:
			print("[fs] warm-up never reported after %d frames -- measuring anyway"
				% _gate_frames)
			_gate = false
		return
	_frames += 1
	if _frames <= WARMUP_FRAMES:
		return
	if _frames == WARMUP_FRAMES + 1:
		# REFUTED, 2026-09-21, and kept: without this the first sampled frame
		# reported +257 MiB of texture memory and read as a resource upload
		# inside the stall. The baseline had been taken in _ready(), so that
		# one delta covered all 120 standing frames. The upload is real and
		# happens at scene load; it is not in the walk.
		_prev = _sample()
		return

	var dir := _legs[_leg].normalized()
	_cam.global_position += dir * SPEED_MPS * delta
	_cam.look_at(_cam.global_position + dir, Vector3.UP)
	_leg_ms.append(ms)
	_leg_calls.append(Performance.get_monitor(MON_DRAWS))
	_leg_objs.append(Performance.get_monitor(MON_OBJS))
	_note_frame(ms)
	_elapsed += delta
	if _elapsed < LEG_SECONDS:
		return
	_close_leg()
	_elapsed = 0.0
	_leg += 1
	if _leg < _legs.size():
		return
	_leg = 0
	_lap += 1
	_cam.global_position = _home
	if _lap >= LAPS:
		_report()
		get_tree().quit()


func _note_frame(ms: float) -> void:
	var s := _sample()
	_worst.append({
		"lap": _lap + 1, "leg": _leg + 1, "ms": ms,
		"d_vid": float(s["vid"]) - float(_prev["vid"]),
		"d_tex": float(s["tex"]) - float(_prev["tex"]),
		"d_buf": float(s["buf"]) - float(_prev["buf"]),
		"d_res": float(s["res"]) - float(_prev["res"]),
		"d_pipe": float(s["pipe"]) - float(_prev["pipe"]),
		"draws": float(s["draws"]),
	})
	_prev = s
	if _worst.size() > 400:
		_worst.sort_custom(_by_ms)
		_worst.resize(200)


func _by_ms(a: Dictionary, b: Dictionary) -> bool:
	return float(a["ms"]) > float(b["ms"])


func _close_leg() -> void:
	var s: Array = _leg_ms.duplicate()
	s.sort()
	var n := s.size()
	if n == 0:
		return
	var total: float = 0.0
	for v in s:
		total += v
	var calls: float = 0.0
	for v in _leg_calls:
		calls += v
	var objs: float = 0.0
	for v in _leg_objs:
		objs += v
	var over := 0
	for v in s:
		if v > 16.7:
			over += 1
	_rows.append({
		"lap": _lap + 1, "leg": _leg + 1, "n": n,
		"mean": total / float(n),
		"median": float(s[n / 2]),
		"low1": float(s[int(float(n) * 0.99)]),
		"worst": float(s[n - 1]),
		"over": over,
		"calls": calls / float(_leg_calls.size()),
		"objs": objs / float(_leg_objs.size()),
	})
	_leg_ms.clear()
	_leg_calls.clear()
	_leg_objs.clear()


func _report() -> void:
	print("[fs] lap leg  frames    mean  median   1%low     worst  >16.7ms   draws   objects")
	for r in _rows:
		var line := "[fs]  %d   %d   %5d  %6.2f  %6.2f  %6.2f  %8.2f   %5.1f%%  %6.0f   %7.0f"
		print(line % [r["lap"], r["leg"], r["n"], r["mean"], r["median"],
			r["low1"], r["worst"],
			100.0 * float(r["over"]) / float(r["n"]), r["calls"], r["objs"]])
	for lap in range(1, LAPS + 1):
		var t: float = 0.0
		var n := 0
		var over := 0
		var worst: float = 0.0
		for r in _rows:
			if int(r["lap"]) != lap:
				continue
			t += float(r["mean"]) * float(r["n"])
			n += int(r["n"])
			over += int(r["over"])
			worst = max(worst, float(r["worst"]))
		if n > 0:
			var lp := "[fs] LAP %d: %d frames, mean %.2f ms, %.2f%% over 16.7 ms, worst %.2f ms"
			print(lp % [lap, n, t / float(n),
				100.0 * float(over) / float(n), worst])
	_worst.sort_custom(_by_ms)
	print("[fs] worst frames, and what the engine's counters did across each:")
	print("[fs]   lap leg      ms   d_video_KiB  d_texture_KiB  d_buffer_KiB  d_res  d_pipeline   draws")
	var shown := 0
	for r in _worst:
		if shown >= 14:
			break
		shown += 1
		var wl := "[fs]    %d   %d  %8.2f   %11.1f  %13.1f  %12.1f  %5.0f  %10.0f  %6.0f"
		print(wl % [r["lap"], r["leg"], r["ms"],
			float(r["d_vid"]) / 1024.0, float(r["d_tex"]) / 1024.0,
			float(r["d_buf"]) / 1024.0, r["d_res"], r["d_pipe"], r["draws"]])
	print("[fs] END")
