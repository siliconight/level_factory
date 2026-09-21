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
## WHAT IT COSTS. 42 stations on that package, 252 frames, and the whole
## compile bill moves to load. The 3D render scale is dropped to a tenth for
## the sweep, so the frames cost submission and not fill; the pipeline is
## otherwise identical, which is the point.
##
## Ordinary scene data and one script: no addon, no autoload, no editor
## plugin. A recipient who does not want it deletes this node.

## Emitted once the sweep is finished and everything it touched is restored.
## A host with its own loading screen can await this before handing over.
signal warmup_finished(frames: int, msec: float)

## Off makes this node inert. Kept as a switch rather than as a deletion so a
## recipient can A/B it against the stall without editing the package.
@export var enabled: bool = true

## Station spacing, metres. Also the radius within which two lights count as
## one lighting context. Smaller covers more contexts and costs more frames;
## the cost is linear in stations and the coverage is not, so this is the knob
## to turn if a level still hitches. 12.0 is what took cold run 9066's package
## to a 155 ms worst frame; 24.0 left it at 2,730 ms.
@export var station_spacing_m: float = 12.0

## Hard ceiling on stations, so a large level cannot turn a load into a hang.
## A level that trips this is warmed coarsely rather than not at all.
@export var max_stations: int = 96

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
	var line := "[warmup] %d station(s) at %.1f m, %d frame(s)"
	print(line % [_stations.size(), station_spacing_m,
		_stations.size() * HEADINGS.size()])


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
	var lights: Array[Vector3] = []
	_collect_lights(get_tree().root, lights)
	if _was_current != null:
		_stations.append(_was_current.global_position)
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
	var stride := station_spacing_m * 2.0
	if stride <= 0.0:
		return
	var x: float = _bounds.position.x + stride * 0.5
	while x < _bounds.position.x + _bounds.size.x:
		var z: float = _bounds.position.z + stride * 0.5
		while z < _bounds.position.z + _bounds.size.z:
			if _stations.size() >= max_stations:
				return
			_stations.append(Vector3(x, eye_y, z))
			z += stride
		x += stride


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
