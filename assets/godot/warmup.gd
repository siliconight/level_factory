extends Node3D

## Pay the shader compile bill at load, where a loading screen belongs, rather
## than in the first ninety seconds of play.
##
## WHAT THE STALL IS. On GL Compatibility a scene shader program is compiled
## and linked the first time something it draws is submitted, and that lands
## inside one frame while the player is walking. Measured on cold run 9066's
## package, 2026-09-21, Godot 4.7.stable, NVIDIA RTX 2060, a camera following
## a six-leg route twice at 3 m/s:
##
##     lap 1   mean 15.64 ms   2.43% over 16.7 ms   worst 8,564 ms
##     lap 2   mean  7.16 ms   0.22% over 16.7 ms   worst    24 ms
##
## Same route, same draw calls (944/492/2031 against 978/499/2050), same
## objects. The three renderer memory monitors and the resource count do not
## move on ANY of the multi-second frames, so nothing is being loaded or
## uploaded; what differs between the laps is only whether it had been
## compiled. The decisive control is that moving the DRIVER's own program
## cache -- `%LOCALAPPDATA%\\NVIDIA\\GLCache`, a directory the project cannot
## see -- aside took lap 1's worst frame from 376 ms to 8,564 ms with nothing
## in the package altered.
##
## WHY IT IS NOT ENOUGH TO DRAW EVERY MATERIAL ONCE. Two refuted approaches,
## kept because each looks obviously sufficient and is not:
##
##   every material on a quad at spawn      8,564 ms -> 5,151 ms
##   every mesh surface on a speck at spawn (2,433 surfaces, same result)
##   one camera, six directions, at spawn   8,564 ms -> 4,395 ms
##
## A GL Compatibility program is specialized on the LIGHTING CONTEXT of the
## draw as well as on the material -- which light types reach the object,
## whether an additive pass is needed, whether shadows are being rendered --
## and the renderable-light set is chosen by distance to the CAMERA. A prop
## warmed under the two lights that reach spawn compiles a fresh program under
## the six that reach it where it stands. So the warm-up has to stand where
## the player will stand.
##
##   light clusters only                    8,564 ms -> 2,730 ms
##   light clusters + a grid over the level 8,564 ms ->   155 ms
##
## The residue is the grid: the leg that looks down the open street is a
## long-sightline context no fixture makes.
##
## AND THE FLOOR UNDER ALL OF THAT, measured 2026-09-21 by sweeping the
## station set properly (see `grid_spacing_m`): on a cold driver cache no
## station set reaches a good frame. Sixteen stations and seventy-nine both
## land at 148-159 ms, and the load is 47.8 s either way. The warm-up moves
## the bill; it does not shrink it, and the last 150 ms of it is not a
## coverage problem. What a recipient can actually tune is the WARM launch --
## 5.9 s to 8.7 s across the same range -- which is the one every player pays
## on every level after their first.
##
## WHAT IT COSTS. 21 stations on that package at the defaults, 126 frames, and
## the whole compile bill moves to load. The 3D render scale is dropped to a
## tenth for the sweep, so the frames cost submission and not fill; the
## pipeline is otherwise identical, which is the point.
##
## Ordinary scene data and one script: no addon, no autoload, no editor
## plugin. A recipient who does not want it deletes this node.

## Emitted once the sweep is finished and everything it touched is restored.
## A host with its own loading screen can await this before handing over.
signal warmup_finished(frames: int, msec: float)

## Off makes this node inert. Kept as a switch rather than as a deletion so a
## recipient can A/B it against the stall without editing the package.
@export var enabled: bool = true

## The radius within which two lights count as one lighting context. Smaller
## keeps more clusters apart and costs more frames.
##
## 0.100.0 spelled the GRID's stride as this number doubled, so one knob moved
## two independent things and neither could be priced separately. They are
## separate now. Measured on cold run 9066's package with the grid at 24 m,
## dropping the 12 light-cluster stations entirely (41 -> 29 stations) moved
## lap 1's worst frame 153 -> 157 ms cold and 25.3 -> 25.3 ms warm: on that
## package the clusters are worth nothing measurable, and the grid is doing
## all of it. They stay on because the level they were reasoned about -- one
## whose fixtures are its only lighting variety -- has not been built yet, and
## 12 stations is 1.0 s of warm load to keep a hypothesis alive that costs
## nothing else.
@export var station_spacing_m: float = 12.0

## Grid stride, metres, over the level's own extent. Zero or less turns the
## grid off, which is not a tuning: 13 stations with no grid measured a
## 1,788 ms worst frame on a cold driver cache.
##
## THIS IS THE KNOB THAT MATTERS. Priced on cold run 9066's package,
## 2026-09-21, one cold launch and one warm launch per configuration, both
## shader caches empty per run (`tools/warmup_spacing_sweep.py`). Stations
## include the spawn and 12 light clusters. Repeated readings of one
## configuration are all listed, because the cold worst frame turned out to
## carry enough spread to be read as a plateau rather than as a ranking:
##
##     stride   stations   load cold   lap1 cold   load warm   lap1 warm
##     none           13      45.3 s     1,788 ms      5.9 s      154 ms
##     64 m           16      47.8 s       152 ms      6.2 s     22.2 ms
##     48 m           21      48.1 s       159 ms      6.4 s     20.5 ms
##     40 m           21      48.6 s       284 ms      6.5 s     20.3 ms
##     40 m again     21      47.8 s       156 ms      6.5 s     20.1 ms
##     32 m           31      49.0 s       148 ms      7.0 s     21.3 ms
##     24 m           41      51.2 s       153 ms      8.7 s     25.3 ms
##     24 m again     41      49.0 s       151 ms      7.1 s     22.8 ms
##     16 m           79      50.2 s       150 ms      8.2 s     19.1 ms
##     (no warm-up)    0           -     6,172 ms          -      382 ms
##
## Three things in that table decide this number.
##
## COLD LOAD BARELY MOVES: 40.7 to 52.1 s across every configuration measured,
## because what the load pays for is the compile bill and not the frames --
## 79 stations is 6.3x the frames of 13 for 4.9 s more load. Most of a cold
## first launch is not this knob's to give back.
##
## THE COLD FRAME PLATEAUS: above about 16 stations it sits at 148-159 ms
## however fine the grid gets, and below it collapses (13 stations 1,788 ms,
## 9 stations 2,926 ms). There is a coverage requirement and it is met early.
##
## THE WARM LAUNCH IS WHAT IS LEFT TO TUNE, and it is the one a player pays on
## every level after their first: 5.9 to 8.7 s, monotone in station count.
##
## 40.0 rather than 0.100.0's effective 24.0 because 21 stations measured
## 6.4-6.5 s of warm load against 7.1-8.7 s and 20.1-20.5 ms against
## 22.8-25.3 ms, across three runs each -- cheaper AND slightly better, with
## the spread of both configurations inside the gap. Not 64.0, which was
## another 0.3 s cheaper and equally clean HERE: its grid is 3 stations on
## this package, and the configuration one station thinner measured 2,926 ms.
## A stride in metres is a different station count on a level of a different
## size, and 64 m sits one station from that cliff where 40 m sits five above
## it. 48 m measures the same 21 stations on this package, which is the
## evidence that the choice is a band and not a point.
@export var grid_spacing_m: float = 40.0

## Hard ceiling on stations, so a large level cannot turn a load into a hang.
##
## A level that trips it is warmed COARSELY, which is what 0.100.0's comment
## promised and its code did not do: that version walked the extent at a fixed
## stride and returned the instant the cap was reached, leaving one corner of
## a large level warmed and the rest cold, with a station count that looks the
## same either way. The stride is widened to fit the budget instead.
@export var max_stations: int = 96

## Stand at each light cluster as well as on the grid. Off drops those
## stations and keeps the grid. On cold run 9066's package that is 41 -> 29
## stations for 153 -> 157 ms cold and no change at all warm, so the clusters
## are the half of the sweep that is not earning its keep there. See
## `station_spacing_m` for why they are still on by default.
@export var warm_light_clusters: bool = true

## Draw an opaque rectangle over the screen for the duration. Off shows the
## sweep, which is how it was checked; a shipped package wants it on.
@export var cover_screen: bool = true

## The six headings a station is sampled at. Not four: a level has a ceiling
## and a floor, and the two near-vertical entries are tilted off the pole so
## `look_at` has a usable up vector.
const HEADINGS: Array[Vector3] = [
	Vector3(1, 0, 0), Vector3(-1, 0, 0), Vector3(0, 0, 1), Vector3(0, 0, -1),
	Vector3(0, 0.999, 0.045), Vector3(0, -0.999, 0.045),
]

## Far plane for the sweep. The warm-up wants everything submitted, including
## the far end of a street, and a level larger than this gets warmed for the
## part of it within range rather than not at all.
const SWEEP_FAR_M := 4000.0
const SWEEP_FOV_DEG := 90.0

## A tenth of the linear resolution: 1% of the pixels, same shader, same
## variant, same specialization.
const SWEEP_3D_SCALE := 0.1

var _cam: Camera3D = null
var _was_current: Camera3D = null
var _cover: CanvasLayer = null
var _stations: Array[Vector3] = []
var _step := 0
var _t0 := 0
var _bounds := AABB()
var _have_bounds := false
var _running := false
var _saved_occlusion := true
var _saved_3d_scale := 1.0
## What the grid actually did, as opposed to what it was asked for: the stride
## is widened when the budget is tight, and a run that cannot say so leaves a
## reader comparing a request with a result.
var _grid_stride := 0.0
var _grid_stations := 0


func _ready() -> void:
	if not enabled:
		return
	if Engine.is_editor_hint():
		return
	# A headless run draws nothing, so there is nothing to compile and the
	# sweep would be 252 frames of pure cost. The QA walkers run headless.
	if DisplayServer.get_name() == "headless":
		return
	# One frame, so the level this is parented into has finished entering the
	# tree and its lights and geometry can be found.
	await get_tree().process_frame
	_begin()


func _begin() -> void:
	var vp := get_viewport()
	if vp == null:
		print("[warmup] no viewport -- nothing warmed")
		return
	_was_current = vp.get_camera_3d()
	var eye_y := 1.6
	if _was_current != null:
		eye_y = _was_current.global_position.y
	_build_stations(eye_y)
	if _stations.is_empty():
		print("[warmup] no geometry found -- nothing warmed")
		return

	_cam = Camera3D.new()
	_cam.far = SWEEP_FAR_M
	_cam.fov = SWEEP_FOV_DEG
	add_child(_cam)
	_cam.global_position = _stations[0]
	_cam.make_current()

	if cover_screen:
		_cover = CanvasLayer.new()
		_cover.layer = 128
		var rect := ColorRect.new()
		rect.color = Color(0, 0, 0, 1)
		rect.set_anchors_preset(Control.PRESET_FULL_RECT)
		_cover.add_child(rect)
		add_child(_cover)

	# Occlusion culling is OFF for the sweep on purpose: the point is to draw
	# what a wall is hiding, because the player walks round that wall in a
	# moment and the program has to exist by then.
	_saved_occlusion = vp.use_occlusion_culling
	_saved_3d_scale = vp.scaling_3d_scale
	vp.use_occlusion_culling = false
	vp.scaling_3d_scale = SWEEP_3D_SCALE

	_t0 = Time.get_ticks_usec()
	_step = 0
	_running = true
	var line := ("[warmup] %d station(s), %d on a %.1f m grid, %d frame(s)"
		+ " (cluster radius %.1f m)")
	print(line % [_stations.size(), _grid_stations, _grid_stride,
		_stations.size() * HEADINGS.size(), station_spacing_m])


func _process(_delta: float) -> void:
	if not _running:
		return
	var total := _stations.size() * HEADINGS.size()
	if _step >= total:
		_end(total)
		return
	var s: Vector3 = _stations[_step / HEADINGS.size()]
	var h: Vector3 = HEADINGS[_step % HEADINGS.size()]
	_cam.global_position = s
	_cam.look_at(s + h, Vector3.UP)
	_step += 1


func _end(total: int) -> void:
	_running = false
	var vp := get_viewport()
	# Restored from what was read at _begin, not from the engine defaults: a
	# host that had turned the culler off keeps it off, and one rendering at
	# half scale on a handheld keeps that too.
	vp.use_occlusion_culling = _saved_occlusion
	vp.scaling_3d_scale = _saved_3d_scale
	if _was_current != null and is_instance_valid(_was_current):
		_was_current.make_current()
	if _cam != null:
		_cam.queue_free()
		_cam = null
	if _cover != null:
		_cover.queue_free()
		_cover = null
	var ms := float(Time.get_ticks_usec() - _t0) / 1000.0
	print("[warmup] %d frame(s) in %.0f ms" % [total, ms])
	warmup_finished.emit(total, ms)


## Stations are the lighting contexts the level actually has, plus a grid so a
## long exterior sightline is one of them. Greedy clustering, not k-means: the
## question is coverage, and a station too many costs one frame.
func _build_stations(eye_y: float) -> void:
	_measure_bounds(get_tree().root)
	if not _have_bounds:
		return
	if _was_current != null:
		_stations.append(_was_current.global_position)
	if warm_light_clusters:
		var lights: Array[Vector3] = []
		_collect_lights(get_tree().root, lights)
		for p in lights:
			if _stations.size() >= max_stations:
				break
			var near := false
			for s in _stations:
				if s.distance_to(p) < station_spacing_m:
					near = true
					break
			if not near:
				_stations.append(p)
	_add_grid(eye_y)


## Cell centres over the level's extent, at a stride that FITS the budget.
##
## Cell centres rather than a walk from one edge, because the walk vanished.
## `x = min_x + stride/2` stepping while `x < max_x` yields NOTHING once the
## stride passes twice the extent, so a coarse setting stopped being a coarse
## grid and became no grid at all, with no way to tell the two apart from the
## station count -- which is the shape of 0.100.0's note that "24.0 left it at
## 2,730 ms", the same figure as light clusters with no grid. Cell counts
## floored at one cannot do that: the coarsest grid this can produce is one
## station in the middle of the level.
func _add_grid(eye_y: float) -> void:
	if grid_spacing_m <= 0.0:
		return
	var budget := max_stations - _stations.size()
	if budget <= 0:
		return
	var w: float = maxf(_bounds.size.x, 0.001)
	var d: float = maxf(_bounds.size.z, 0.001)
	var stride := grid_spacing_m
	var nx := maxi(1, int(round(w / stride)))
	var nz := maxi(1, int(round(d / stride)))
	# Widen rather than truncate. 1.25 per step because the count falls as the
	# square of the stride, so a handful of steps covers any real overshoot
	# without jumping past a stride that would have fitted.
	while nx * nz > budget and stride < w + d:
		stride *= 1.25
		nx = maxi(1, int(round(w / stride)))
		nz = maxi(1, int(round(d / stride)))
	if nx * nz > budget:
		nx = 1
		nz = 1
	_grid_stride = stride
	_grid_stations = nx * nz
	for i in range(nx):
		var x: float = _bounds.position.x + (float(i) + 0.5) * (w / float(nx))
		for j in range(nz):
			var z: float = _bounds.position.z + (float(j) + 0.5) * (d / float(nz))
			_stations.append(Vector3(x, eye_y, z))


func _measure_bounds(n: Node) -> void:
	if n is VisualInstance3D:
		var v := n as VisualInstance3D
		var b: AABB = v.global_transform * v.get_aabb()
		if _have_bounds:
			_bounds = _bounds.merge(b)
		else:
			_bounds = b
			_have_bounds = true
	for c in n.get_children():
		_measure_bounds(c)


func _collect_lights(n: Node, out: Array) -> void:
	if n is Light3D:
		out.append((n as Light3D).global_position)
	for c in n.get_children():
		_collect_lights(c, out)
