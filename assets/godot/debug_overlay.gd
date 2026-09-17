extends Node
## Level Factory walk preview -- DEV ONLY debug overlay.
## ----------------------------------------------------------------------------
## Says WHERE YOU ARE, WHAT YOU ARE LOOKING AT, and WHAT THE FRAME COSTS, so a
## screenshot of a defect carries its own coordinates and its own price instead
## of needing a conversation to locate.
##
## Written 2026-08-08, after an afternoon of screenshots that each showed a real
## defect and none of which said which of five buildings it was in. The answer
## had to be reconstructed from the site scene's node transforms every time, and
## once it was reconstructed against the WRONG building because nothing in the
## picture pinned it down.
##
## THREE LINES, and each one exists because a specific question was asked and
## could not be answered from a picture:
##
##   position  -- "which building is this?" The row runs along x; the building
##                id resolves that directly, and the raw coordinates let a
##                defect be found again after a rebuild.
##   building  -- the instanced package under the crosshair, by its own scene
##                path (`lot/construction_site_a03/site.tscn` -> b2
##                construction_site_a03). Read from `scene_file_path`, which is
##                the node's own record of where it came from, rather than
##                matched against a table this file would have to keep in step.
##   surface   -- the collider the crosshair is on, and its distance. "stairs
##                into collision" becomes "slab_1 at 2.4 m", which names the
##                thing to go and measure.
##
## It rides in the preview project with the player and the bots, never in the
## package: the package is content a stranger instances into their own project,
## and dev instrumentation is not content. Never exported.
##
## F3 toggles the position panel, F4 the perf panel. Both are on by default,
## because an overlay you have to remember to enable is one that is off in the
## screenshot you needed it in.
##
## DEBUG BUILDS ONLY. A release export of a project that carries this script
## removes the overlay on its first frame: players never see it, even when a
## walk project is exported as-is. Player exports are not meant to ship the
## script at all; this is the guard for when one does.
##
## ============================================================================
## THE PERF PANEL (2026-09-16)
## ============================================================================
## Added after the walker reported cold run 9062's card shop "chugging" and
## asked to be shown framerate while walking, so that "as we add more stuff"
## is a decision with a number under it rather than a feeling afterwards.
##
## TWO PANELS, TWO KEYS, and that is the whole reason perf is not folded into
## the F3 panel. Position and cost get asked in the same breath -- "it stutters
## HERE" is one finding, not two -- so a single key would make each readout
## cost the other. F3 keeps exactly the meaning it has had since 2026-08-08.
##
## WHAT IT SHOWS, AND WHY NOT THE OBVIOUS MONITORS. Measured on this machine,
## Godot 4.7.stable, gl_compatibility, RTX 2060, with a probe that stalled one
## known frame by 60 ms:
##
##   * `Engine.get_frames_per_second()` and `Performance.TIME_FPS` REFRESH ONCE
##     A SECOND. They held one value across 300 consecutive frames and then
##     stepped. A readout built on them is up to a second stale and cannot show
##     a stutter at all.
##   * `Performance.TIME_PROCESS` is not this frame's CPU time. It is the WORST
##     idle step within the last completed second: the 60 ms stall came back as
##     68.317 ms and was still being reported 285 frames later, while every
##     frame in between measured 1-4 ms. Useful, and labelled for what it is.
##   * So FPS AND FRAME TIME HERE ARE MEASURED IN THIS FILE, off `_process`
##     deltas, over a short window. That is the only figure available that can
##     move faster than 1 Hz.
##   * `RENDER_TOTAL_DRAW_CALLS_IN_FRAME`, `..._PRIMITIVES_...` and
##     `..._OBJECTS_...` DO work in Compatibility -- verified moving 2 -> 2900
##     objects and 24 -> 34,800 primitives under load.
##   * `RenderingServer.viewport_get_measured_render_time_gpu` RETURNS A REAL
##     GPU FIGURE in Compatibility, contrary to the usual expectation that GPU
##     timing is a Forward+/RenderingDevice feature: 0.020 ms on an empty view,
##     0.24-0.62 ms under the same load. It has to be switched on per viewport
##     (`viewport_set_measure_render_time`), which this does only while the
##     panel is visible.
##
## THE ROLLING MINIMUM IS THE POINT. "Chugging" is not a mean -- a mean of 60
## stutters badly -- so the second line is the WORST SINGLE FRAME in the
## window, in ms and as the instantaneous rate it implies. It is not a 1% low:
## a percentile needs every frame time kept and sorted, and the worst frame is
## both stricter and free. `PERF_WINDOW` is short enough that the number the
## walker reads is the stutter they just felt, and long enough to survive the
## moment it takes to look down.
##
## VSYNC IS ON THE CONTEXT LINE because without it the fps figure lies by
## omission: capped at the refresh rate, 60 fps means "not worse than the
## monitor" and says nothing about headroom. When vsync is on, the gpu and
## render-cpu figures are the ones that carry information.
##
## WHAT IT COSTS. Priced on cold run 9062's card block -- four stations, fixed
## view, 5 s of samples after a 2 s settle, vsync off, 1152x648, RTX 2060.
##
## THE ON/OFF FRAME-TIME A/B COULD NOT ANSWER IT, and that is a result rather
## than a failure of nerve. Run to run, with nothing changed, the same station
## in this package measured 23-96 ms of GPU time and 14-100 ms a frame: a
## no-change control pair differed by 29%. An effect of a third of a
## millisecond cannot be read off that, and a difference quoted from it would
## have been the noise, dressed up.
##
## So the overlay was made to time ITSELF instead -- its own `_process` bracket-
## ed by `Time.get_ticks_usec()`, in a generated copy of this exact file, in
## the real package. That measures the thing, not the level around it:
##
##     perf panel alone, ordinary frame         8.9 - 19.1 us
##     perf panel alone, sample frame (4/s)      215 - 385 us
##     F3 position panel, EVERY frame            268 - 351 us
##
## Two control runs of the perf-panel arm, taken either side of the others,
## bracket every figure above.
##
## So the panel costs `PERF_HZ * tick + fps * frame` -- about 1.1 ms of CPU a
## SECOND on the sample clock plus 14 us a frame, which at 60 fps is 1.9 ms a
## second, 0.03 ms a frame, 0.2% of a 16.7 ms frame. Most of it does not scale
## with framerate, which is the property that matters: it does not get louder
## as the level gets slower. In draw calls it is exactly +2, measured identical
## at all four stations (1392 -> 1394, 3419 -> 3421, 340 -> 342, 189 -> 191).
##
## THE F3 PANEL IS THE EXPENSIVE ONE, by a factor of 20, and it has been since
## 2026-08-08: it raycasts and rebuilds its Label every frame. That is not
## changed here -- it would be a second change wearing this one's clothes --
## but it is now measured, and a walker reading a frame time with F3 up is
## reading one about 0.3 ms worse than the level's own.
##
## The numbers are this rig's, not a client's. Measure again before quoting
## them anywhere a decision hangs on them.

const RAY_LENGTH := 60.0
const _VARIANT := "_a"

## Sample rate for the perf panel. Text that changes faster than about 4 Hz
## cannot be read -- the digits blur -- and every tick is the expensive half of
## this file, so the readable rate and the cheap rate are the same number.
const PERF_HZ := 4.0

## The window is `PERF_BUCKETS / PERF_HZ` seconds = 2.0 s. Two seconds is how
## long a stutter stays relevant: long enough that a walker who felt it and
## looked down still sees it, short enough that a stutter from the far end of
## the street is gone by the time they are somewhere else.
const PERF_BUCKETS := 8

var _label: Label
var _perf: Label
var _shown := true
var _perf_shown := true

# One bucket's worth of accumulation, added to on every frame.
var _acc_time := 0.0
var _acc_frames := 0
var _acc_worst := 0.0

# The ring of finished buckets. Fixed-size and preallocated: a window that
# appends and trims would allocate on every tick, which is a cost the thing
# measuring cost should not be paying.
var _b_time := PackedFloat32Array()
var _b_frames := PackedFloat32Array()
var _b_worst := PackedFloat32Array()
var _b_gpu := PackedFloat32Array()
var _b_rcpu := PackedFloat32Array()
var _b_at := 0
var _b_filled := 0
## Frames are timed off the WALL CLOCK, not off `_process`'s delta, and this is
## the difference between a stutter meter and a decoration. The engine CLAMPS
## the delta it hands out: measured in the card block, three stations reported
## 150.000 ms on the nose as their worst frame while the same frames, timed
## between two `Time.get_ticks_usec()` calls, were 191, 356 and 527 ms. A meter
## built on the delta would have told the walker their 0.5 s hitch was 0.15 s,
## and told it consistently.
var _last_usec := 0

var _vp_rid: RID
var _gpu_seen := false
var _context := ""


func _ready() -> void:
	if not OS.is_debug_build():
		set_process(false)
		set_process_input(false)
		queue_free()
		return
	var layer := CanvasLayer.new()
	layer.layer = 128
	add_child(layer)

	# A panel behind the text -- with an EXPLICIT light plate, not the theme
	# default. The first version was unreadable in exactly the shot it was
	# built for; the second relied on PanelContainer's default stylebox, which
	# is dark translucent grey, so near-black text sat on a near-black plate
	# and the walk screenshots of 2026-08-23 could not be read either. The
	# plate now paints its own ground: bright and mostly opaque, so the dark
	# text reads over a lit ceiling and a black basement alike.
	var panel := PanelContainer.new()
	panel.position = Vector2(12, 12)
	panel.add_theme_stylebox_override("panel", _plate())
	layer.add_child(panel)

	_label = Label.new()
	_label.add_theme_font_size_override("font_size", 15)
	_label.add_theme_color_override("font_color", Color(0.06, 0.06, 0.08))
	panel.add_child(_label)

	# The perf panel takes the opposite corner, so the two never overlap and
	# neither has to be dismissed to read the other.
	var pperf := PanelContainer.new()
	pperf.add_theme_stylebox_override("panel", _plate())
	pperf.anchor_left = 1.0
	pperf.anchor_right = 1.0
	pperf.offset_left = -12.0
	pperf.offset_right = -12.0
	pperf.offset_top = 12.0
	pperf.offset_bottom = 12.0
	pperf.grow_horizontal = Control.GROW_DIRECTION_BEGIN
	pperf.grow_vertical = Control.GROW_DIRECTION_END
	layer.add_child(pperf)

	_perf = Label.new()
	_perf.add_theme_font_size_override("font_size", 14)
	_perf.add_theme_color_override("font_color", Color(0.06, 0.06, 0.08))
	# A width floor, so the panel does not breathe in and out as the digits
	# change width in a proportional font. Wide enough for the longest line
	# this prints at font size 14.
	_perf.custom_minimum_size = Vector2(330.0, 0.0)
	pperf.add_child(_perf)

	_b_time.resize(PERF_BUCKETS)
	_b_frames.resize(PERF_BUCKETS)
	_b_worst.resize(PERF_BUCKETS)
	_b_gpu.resize(PERF_BUCKETS)
	_b_rcpu.resize(PERF_BUCKETS)
	_vp_rid = get_viewport().get_viewport_rid()
	_context = _context_line()
	_perf.text = "perf: sampling"
	_set_measuring(true)
	# Said out loud once, because the walk tools that copy this file in print
	# their own summary and a key nobody knows about is a key nobody presses.
	print("[debug_overlay] F3 position/building/surface, F4 perf. " + _context)


func _plate() -> StyleBoxFlat:
	var plate := StyleBoxFlat.new()
	plate.bg_color = Color(0.93, 0.94, 0.96, 0.92)
	plate.set_corner_radius_all(4)
	plate.content_margin_left = 10.0
	plate.content_margin_right = 10.0
	plate.content_margin_top = 6.0
	plate.content_margin_bottom = 6.0
	return plate


func _input(event: InputEvent) -> void:
	if event is InputEventKey and event.pressed and not event.echo:
		var key := event as InputEventKey
		if key.keycode == KEY_F3 and _label != null:
			_shown = not _shown
			_label.get_parent().visible = _shown
		elif key.keycode == KEY_F4 and _perf != null:
			_perf_shown = not _perf_shown
			_perf.get_parent().visible = _perf_shown
			# OFF MEANS OFF, not hidden. The GPU timer queries and the whole
			# sample path stop with the panel, so a measurement taken with the
			# panel down is not paying for a panel. The window is dropped for
			# the same reason: two seconds of frames from before the toggle
			# would be reported as if they were now.
			_set_measuring(_perf_shown)
			_reset_window()


func _set_measuring(on: bool) -> void:
	if _vp_rid.is_valid():
		RenderingServer.viewport_set_measure_render_time(_vp_rid, on)


func _reset_window() -> void:
	_acc_time = 0.0
	_acc_frames = 0
	_acc_worst = 0.0
	_b_at = 0
	_b_filled = 0
	_last_usec = 0


func _process(_delta: float) -> void:
	_perf_tick()
	if not _shown or _label == null:
		return
	var cam := get_viewport().get_camera_3d()
	if cam == null:
		_label.text = "no camera"
		return

	var eye: Vector3 = cam.global_transform.origin
	var lines: Array[String] = []
	lines.append("pos  x %.1f  y %.1f  z %.1f" % [eye.x, eye.y, eye.z])

	var hit := _look_at_hit(cam)
	if hit.is_empty():
		lines.append("look nothing within %.0f m" % RAY_LENGTH)
		_label.text = "\n".join(lines)
		return

	var collider: Node = hit.get("collider") as Node
	var point: Vector3 = hit.get("position", eye)
	var dist: float = eye.distance_to(point)

	# The building is whichever instanced package this collider sits inside.
	# `scene_file_path` is the node's OWN record of the scene it came from, so
	# this cannot drift out of step with the lot the way a name table would.
	var owner_node: Node = _instanced_ancestor(collider)
	if owner_node == null:
		lines.append("bldg (not inside an instanced package)")
	else:
		lines.append("bldg %s   %s" % [owner_node.name,
			_package_of(owner_node)])

	if collider == null:
		lines.append("look <no collider>")
	else:
		lines.append("look %s   %.2f m   y %.2f" % [collider.name, dist,
			point.y])
		var parent_name := "-"
		if collider.get_parent() != null:
			parent_name = collider.get_parent().name
		lines.append("under %s" % parent_name)
	_label.text = "\n".join(lines)


func _perf_tick() -> void:
	## The per-frame half: one clock read, three accumulations and a compare.
	## No allocation, no monitor reads, no string. Everything that costs
	## anything is behind the period test. Measured at 13 us a frame on this
	## rig -- see the header.
	if not _perf_shown or _perf == null:
		return
	var now := Time.get_ticks_usec()
	var prev := _last_usec
	_last_usec = now
	if prev <= 0:
		return          # first frame of a window has nothing to subtract from
	var frame := float(now - prev) * 0.000001
	_acc_time += frame
	_acc_frames += 1
	if frame > _acc_worst:
		_acc_worst = frame
	if _acc_time * PERF_HZ < 1.0:
		return
	_b_time[_b_at] = _acc_time
	_b_frames[_b_at] = float(_acc_frames)
	_b_worst[_b_at] = _acc_worst
	# The render times are read once per tick rather than once per frame, and
	# averaged across the window. Per frame they swing by an order of magnitude
	# on an unchanged view (0.020 -> 0.262 ms measured), so an instantaneous
	# figure is a number the walker cannot act on.
	var gpu := RenderingServer.viewport_get_measured_render_time_gpu(_vp_rid)
	if gpu > 0.0:
		_gpu_seen = true
	_b_gpu[_b_at] = gpu
	_b_rcpu[_b_at] = RenderingServer.viewport_get_measured_render_time_cpu(
		_vp_rid)
	_b_at = (_b_at + 1) % PERF_BUCKETS
	_b_filled = mini(_b_filled + 1, PERF_BUCKETS)
	_acc_time = 0.0
	_acc_frames = 0
	_acc_worst = 0.0
	_perf.text = _perf_text()


func _perf_text() -> String:
	var secs := 0.0
	var frames := 0.0
	var worst := 0.0
	var gpu := 0.0
	var rcpu := 0.0
	for i in range(_b_filled):
		secs += _b_time[i]
		frames += _b_frames[i]
		gpu += _b_gpu[i]
		rcpu += _b_rcpu[i]
		if _b_worst[i] > worst:
			worst = _b_worst[i]
	if secs <= 0.0 or frames <= 0.0:
		return "perf: sampling"
	var n := float(_b_filled)
	var lines: Array[String] = []
	lines.append("fps %5.1f avg   %5.2f ms/frame   (%.1f s)"
		% [frames / secs, 1000.0 * secs / frames, secs])
	lines.append("low %5.1f fps   %5.2f ms worst frame"
		% [1.0 / worst if worst > 0.0 else 0.0, 1000.0 * worst])
	var gpu_txt := "%5.2f ms" % (gpu / n)
	if not _gpu_seen:
		# Not "0.00". A GPU figure that never moved off zero is an unmeasured
		# one, and printing it as a measurement is how a ruler gets believed
		# that is not reading anything.
		gpu_txt = "  n/a  "
	lines.append("gpu %s   render-cpu %5.2f ms" % [gpu_txt, rcpu / n])
	lines.append("draw %s calls  %s tris  %s objects" % [
		_grouped(int(Performance.get_monitor(
			Performance.RENDER_TOTAL_DRAW_CALLS_IN_FRAME))),
		_grouped(int(Performance.get_monitor(
			Performance.RENDER_TOTAL_PRIMITIVES_IN_FRAME))),
		_grouped(int(Performance.get_monitor(
			Performance.RENDER_TOTAL_OBJECTS_IN_FRAME)))])
	# Not a frame time. These two are the engine's worst idle and physics step
	# within the last completed second, refreshed at 1 Hz -- measured, see the
	# header -- so they are labelled as the hitch they are.
	lines.append("1 s worst step: main %.1f ms  physics %.2f ms" % [
		1000.0 * Performance.get_monitor(Performance.TIME_PROCESS),
		1000.0 * Performance.get_monitor(Performance.TIME_PHYSICS_PROCESS)])
	lines.append(_context)
	return "\n".join(lines)


func _context_line() -> String:
	## WHOSE FIGURES THESE ARE. The walk copy runs the PACKAGE's project
	## settings -- its renderer, its light budget -- and only the main scene is
	## the harness's, so a number read here is the package's number. This line
	## says which package and under what, because a frame time with no
	## resolution or vsync state beside it is not comparable to anything.
	var name_s := str(ProjectSettings.get_setting(
		"application/config/name", "?"))
	var method := str(ProjectSettings.get_setting(
		"rendering/renderer/rendering_method", "?"))
	var lights := str(ProjectSettings.get_setting(
		"rendering/limits/opengl/max_renderable_lights", "-"))
	var size := DisplayServer.window_get_size()
	var vsync := "on"
	if DisplayServer.window_get_vsync_mode() == DisplayServer.VSYNC_DISABLED:
		vsync = "off"
	return "%s  %s  %s lights  vsync %s  %dx%d" % [name_s, method, lights,
		vsync, size.x, size.y]


func _grouped(n: int) -> String:
	## 318442 -> "318 442". A six-digit triangle count read off a screenshot is
	## a six-digit misreading waiting to happen.
	var s := str(n)
	var out := ""
	var c := 0
	for i in range(s.length() - 1, -1, -1):
		out = s[i] + out
		c += 1
		if c % 3 == 0 and i > 0:
			out = " " + out
	return out


func _look_at_hit(cam: Camera3D) -> Dictionary:
	var space := get_viewport().get_world_3d().direct_space_state
	var from: Vector3 = cam.global_transform.origin
	# -Z is forward in Godot. Reading the basis rather than `project_ray_normal`
	# keeps this correct when the preview runs without a mouse (the bots).
	var to: Vector3 = from - cam.global_transform.basis.z * RAY_LENGTH
	var q := PhysicsRayQueryParameters3D.create(from, to)
	q.collide_with_areas = false
	return space.intersect_ray(q)


func _instanced_ancestor(node: Node) -> Node:
	## The nearest ancestor that was instanced from its own scene file -- the
	## per-building package. Walks UP rather than searching down, because the
	## collider is many levels deep and only its ancestry knows which package
	## owns it.
	var n: Node = node
	while n != null:
		if n.scene_file_path != "":
			return n
		n = n.get_parent()
	return null


func _package_of(node: Node) -> String:
	## `lot/construction_site_a03/site.tscn` -> `construction_site_a03`.
	## Falls back to the raw path rather than inventing a name: an unexpected
	## layout should read as unexpected, not as a confident wrong answer.
	var p: String = node.scene_file_path
	var parts: PackedStringArray = p.replace("res://", "").split("/")
	if parts.size() >= 2:
		return parts[parts.size() - 2]
	return p
