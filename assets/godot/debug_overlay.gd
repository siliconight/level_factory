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
##   * THE `PIPELINE_COMPILATIONS_*` MONITORS EXIST AND STAY ZERO. All five are
##     in the enum, and they are the obvious instrument for a hitch caused by
##     shader compilation -- which is what a 491 ms frame during load looks
##     like. Measured in the card block, warm and with `.godot` stripped, both
##     runs reported 0 across all five: they are a RenderingDevice feature and
##     Compatibility does not feed them. So they are NOT on the panel. A
##     counter that reads zero because nothing writes it is indistinguishable
##     from a level that compiled nothing, and the second is the answer a
##     reader would take.
##   * `RenderingServer.viewport_get_measured_render_time_gpu` RETURNS A REAL
##     GPU FIGURE in Compatibility, contrary to the usual expectation that GPU
##     timing is a Forward+/RenderingDevice feature: 0.020 ms on an empty view,
##     0.24-0.62 ms under the same load. It has to be switched on per viewport
##     (`viewport_set_measure_render_time`), which this does only while the
##     panel is visible.
##
## THE ROLLING MINIMUM IS THE POINT, and the measurement that prompted the
## panel says why. Cold run 9062's walk copy, wall-clock probe at spawn, 600
## frames after a 240-frame warmup:
##
##     mean 10.40 ms (96.2 fps)   median 10.35   1% low 18.54 ms (53.9 fps)
##     worst 34.07 ms   342 draw calls   1,386,518 primitives   395 objects
##
## The absolute figure moved afterwards -- the same station on a quiet machine
## is 1.53 ms, and the draw calls, primitives and objects match to the digit,
## so the two probes were looking at the same view on a differently loaded
## computer. THE SHAPE DID NOT MOVE, which is the part the panel is built on:
## on the quiet machine the mean was 1.9 ms and the worst frame the panel held
## was 491.72 ms. Whatever the average is, this level's problem is the tail.
##
## The level does not run slowly. It HITCHES -- a 96 fps mean with a 54 fps 1%
## low -- which is exactly the shape a mean cannot carry and exactly what the
## walker meant by "not staying smooth". So three of the panel's numbers are
## about the tail and only one is about the average:
##
##   * the WORST SINGLE FRAME in the window, in ms and as the rate it implies.
##     Not a 1% low: a percentile needs every frame kept and sorted, and the
##     worst frame is both stricter and free.
##   * a HITCH COUNT, frames over `HITCH_FACTOR` x the window's own mean. A
##     count is what a walker can report -- "it did it four times crossing the
##     street" -- where a single worst figure cannot say whether it happened
##     once or constantly.
##   * a HELD WORST, with its age, because a hitch that ages out of a 2 s
##     window is gone before the walker has finished looking down, and then
##     the panel and the person disagree about what just happened.
##
## WHAT IS NOT THE CAUSE, recorded here so the panel is not read as pointing at
## it: measured on this package on 2026-09-16, disabling all 12 shadow casters
## made the frame time WORSE, and so did capping lights per object at 8.
## Neither moved the primitive count. The light budget on the context line is
## provenance, not a diagnosis.
##
## VSYNC IS ON THE CONTEXT LINE because without it the fps figure lies by
## omission: capped at the refresh rate, 60 fps means "not worse than the
## monitor" and says nothing about headroom. When vsync is on, the gpu and
## render-cpu figures are the ones that carry information.
##
## WHAT IT COSTS. Priced on cold run 9062's card block -- fixed view, 6 s of
## samples after a 3 s settle, vsync off, 1152x648, RTX 2060, arms interleaved
## a-b-c-a-b-c so drift shows up as a disagreement between the two runs of one
## arm.
##
## RETRACTED, AND KEPT HERE BECAUSE IT WAS NEARLY SHIPPED AS FACT: the first
## pricing of this panel was taken while a SECOND Godot was on the same GPU --
## the walker's own walk copy, open in front of them. Those runs measured this
## station at 14-100 ms a frame with a no-change control pair differing by 29%,
## and the conclusion drawn was "the A/B cannot resolve an overlay, so time the
## script instead". The A/B was fine. The machine was busy. On a quiet machine
## the same station repeats to better than 0.5%, and the A/B answers directly.
## A frame time is a measurement of a whole computer, and nothing in the
## artefact says who else was using it.
##
##     station     no overlay      F3 panel        F3 + perf panel
##     shop floor  5.945, 5.900    6.045, 6.110    6.105, 6.086 ms
##     spawn       1.528, 1.541    1.671, 1.671    1.677, 1.671 ms
##
## So the F3 panel costs +0.14 to +0.16 ms a frame, and THE PERF PANEL ADDS
## +0.003 to +0.02 ms on top of it -- smaller than the 0.045 ms spread between
## the two runs of the no-overlay arm, which is to say bounded by this rig's
## noise rather than resolved by it. In draw calls it is exactly +2, and that
## one IS exact: 1392 -> 1394 -> 1396 and 340 -> 342 -> 344, identical in both
## rounds.
##
## The same file timing ITSELF -- its own `_process` bracketed by
## `Time.get_ticks_usec()` in a generated copy -- splits that between the two
## panels, on the same quiet machine, control runs either side:
##
##     perf panel alone, ordinary frame          2.1 - 4.0 us
##     perf panel alone, sample frame (4/s)       94 - 110 us
##     F3 position panel, EVERY frame           49.3 - 107.6 us
##
## The perf panel is therefore `PERF_HZ * tick + fps * frame`: about 0.4 ms of
## CPU a SECOND, mostly on the sample clock rather than the framerate, which is
## the property that matters -- it does not get louder as the level gets
## slower. At 60 fps that is 0.006 ms a frame, 0.04% of a 16.7 ms frame.
##
## The self-timing is smaller than the A/B for both panels, and the gap is
## real work rather than an error: the Label reshape, the CanvasLayer redraw
## and the two extra draw calls all happen outside `_process` and are counted
## by the A/B alone. Quote the A/B when the question is what a frame costs, and
## the self-timing when the question is which panel to blame.
##
## THE F3 PANEL IS THE EXPENSIVE ONE, by a factor of 25 in script time, and it
## has been since 2026-08-08: it raycasts and rebuilds its Label every frame,
## and it costs more indoors (107.6 us in the shop against 49.3 at spawn)
## because that is where the raycast has something to hit. That is not changed
## here -- it would be a second change wearing this one's clothes -- but it is
## now measured, and a walker reading a frame time with F3 up is reading one
## about 0.15 ms worse than the level's own.
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

## A frame counts as a HITCH when it costs this multiple of the prevailing
## frame time. Derived from what vsync does with a late frame rather than
## picked: a frame that overruns its interval does not arrive late, it arrives
## at the NEXT interval, so an overrun of half an interval is already a whole
## dropped frame on screen. 1.5x is the smallest overrun that is certainly
## visible, and it scales itself -- the threshold is recomputed from the
## window's own mean every tick, so it means the same thing at 30 fps and at
## 144. Checked against the measurement that prompted the panel: cold run
## 9062's spawn, mean 10.40 ms with a 1% low of 18.54 ms, gives a threshold of
## 15.6 ms and counts that 1% as hitches, which is the point. At 2.0x it would
## have counted none of them and read as a smooth level.
const HITCH_FACTOR := 1.5

var _label: Label
var _perf: Label
var _shown := true
var _perf_shown := true

# One bucket's worth of accumulation, added to on every frame.
var _acc_time := 0.0
var _acc_frames := 0
var _acc_worst := 0.0
var _acc_hitch := 0

## The worst frame the panel has seen since it came up or was last reset, and
## how long it has been watching. The 2 s window is what the walker felt; this
## is what they felt a minute ago and have already stopped being able to
## describe. A hitch that ages out of the window leaves its mark here.
var _worst_held := 0.0
var _held_secs := 0.0

## The hitch threshold in seconds, recomputed each tick from the window's own
## mean. INF until there is a window to derive it from -- a threshold of zero
## would count every frame of the first quarter-second as a hitch and open the
## panel on a number that means nothing.
var _hitch_at := INF

# The ring of finished buckets. Fixed-size and preallocated: a window that
# appends and trims would allocate on every tick, which is a cost the thing
# measuring cost should not be paying.
var _b_time := PackedFloat32Array()
var _b_frames := PackedFloat32Array()
var _b_worst := PackedFloat32Array()
var _b_hitch := PackedFloat32Array()
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
	_b_hitch.resize(PERF_BUCKETS)
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
	_acc_hitch = 0
	_b_at = 0
	_b_filled = 0
	_last_usec = 0
	_hitch_at = INF
	_worst_held = 0.0
	_held_secs = 0.0


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
	## The per-frame half: one clock read, three accumulations and two compares.
	## No allocation, no monitor reads, no string. Everything that costs
	## anything is behind the period test. Measured at 2-4 us a frame on this
	## rig, against 94-110 us on the tick -- see the header.
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
	if frame > _hitch_at:
		_acc_hitch += 1
	if _acc_time * PERF_HZ < 1.0:
		return
	if _acc_worst > _worst_held:
		_worst_held = _acc_worst
	_held_secs += _acc_time
	_b_time[_b_at] = _acc_time
	_b_frames[_b_at] = float(_acc_frames)
	_b_worst[_b_at] = _acc_worst
	_b_hitch[_b_at] = float(_acc_hitch)
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
	_acc_hitch = 0
	_perf.text = _perf_refresh()


func _perf_refresh() -> String:
	## The panel's text, AND the hitch threshold for the next window -- which is
	## why this is not called `_perf_text`. The threshold is a function of the
	## window mean, the window mean is summed here, and a second pass over the
	## ring to keep this function pure would cost more than the honesty of the
	## name does.
	var secs := 0.0
	var frames := 0.0
	var worst := 0.0
	var hitches := 0.0
	var gpu := 0.0
	var rcpu := 0.0
	for i in range(_b_filled):
		secs += _b_time[i]
		frames += _b_frames[i]
		hitches += _b_hitch[i]
		gpu += _b_gpu[i]
		rcpu += _b_rcpu[i]
		if _b_worst[i] > worst:
			worst = _b_worst[i]
	if secs <= 0.0 or frames <= 0.0:
		return "perf: sampling"
	var mean := secs / frames
	_hitch_at = HITCH_FACTOR * mean
	var n := float(_b_filled)
	var lines: Array[String] = []
	lines.append("fps %5.1f avg   %5.2f ms/frame   (%.1f s)"
		% [1.0 / mean, 1000.0 * mean, secs])
	lines.append("low %5.1f fps   %5.2f ms worst frame"
		% [1.0 / worst if worst > 0.0 else 0.0, 1000.0 * worst])
	# THE LINE THE PANEL WAS ASKED FOR. The complaint was "chugging ... not
	# staying smooth", and a mean cannot carry that: measured at 9062's spawn,
	# 96.2 fps mean with a 1% low of 53.9 fps and single frames at 34.07 ms. A
	# count of frames that missed, and the worst one since the panel came up,
	# are what a walker can report; an average of 96 is what makes them doubt
	# what they felt.
	lines.append("hitch %d over %.1f ms   held %.2f ms  %s" % [
		int(hitches), 1000.0 * _hitch_at, 1000.0 * _worst_held,
		_mmss(_held_secs)])
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
	# "light budget", not "lights": it is the project's `max_renderable_lights`
	# setting, which is provenance and not a diagnosis. Measured 2026-09-16 on
	# this same package, disabling all 12 shadow casters and capping lights per
	# object at 8 each made the frame time WORSE, and neither moved the
	# primitive count -- so a panel that let this number read as the cause
	# would be pointing the next person at the thing already ruled out.
	return "%s  %s  light budget %s  vsync %s  %dx%d" % [name_s, method,
		lights, vsync, size.x, size.y]


func _mmss(secs: float) -> String:
	## How long the held worst has been held. A worst frame with no age on it is
	## ambiguous between "just now" and "four minutes ago", and those are
	## different findings.
	var t := int(secs)
	return "%d:%02d" % [t / 60, t % 60]


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
