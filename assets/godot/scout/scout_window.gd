extends Node
class_name LFScoutWindow
## Level Factory's scout window: the screen a player scouts a level's buildings on (the factory's roadmap 295).
## ---------------------------------------------------------------------------------------------------------------
## The walker: "Goal is we have the ability to open up a 'window' at runtime that shows the various buildings and
## their 3d schematics", in "the style of a 1990s palm pilot...but with a little more backlight and color", showing
## "the 'score' location and key props of interest". The handheld itself is the game's asset; this is its SCREEN.
##
## THE SEAM -- everything the gameplay layer calls, and nothing else:
##
##     var scout := preload("res://scout/scout_window.gd").new()
##     add_child(scout)
##     scout.open()                        # builds the screen and starts drawing it
##     $Handheld/Screen.texture = scout.get_screen_texture()   # onto the game's own handheld
##     scout.open(true)                    # or: shown centred over the game, no handheld needed
##     scout.select("deli_a03")            # a building by its id in buildings.json
##     scout.set_points("deli_a03", [{"label": "SCORE", "kind": "score", "at": Vector3(...)}])   # gameplay's own
##     scout.close()                       # stops drawing; costs nothing until opened again
##
##   signals: opened, closed, building_selected(id)
##
## While open it takes its own input: left/right (ui_left/ui_right) the building; up/down (ui_up/ui_down) the floor
## it focuses -- the floors above it step aside, the ones below dim, the view centres on it, so no corner of it stays
## covered as it turns (0.236.0) -- and past the top the whole building again; a mouse drag turns it and tilts it, a
## flick keeps it turning, and left alone it turns itself slowly; ui_cancel closes it. A caller that wants its own
## controls turns that off with `handle_input = false` and calls `select`, `focus`, `turn`, `tilt` and
## `set_spread`.
##
## WHAT IT READS: the package's `buildings.json` (Level Factory 0.232.0 on) and each building's
## `drawings/scout.glb` (Deli Counter 0.259.0 on), loaded with GLTFDocument when the screen opens -- kept, never
## imported, so no level pays for them until a player looks. A building with no model is listed and says so.
##
## WHAT IT COSTS: nothing while closed -- no nodes, no viewport drawing. Open, one small 3D view of one building
## (deli_a03: four draws a storey with its points, under 3,500 triangles) and a 2D screen.

signal opened
signal closed
signal building_selected(id: String)

## Where the package's root is, for buildings.json and the models it names.
@export var package_root: String = "res://"
## The screen's size in pixels; the game's handheld samples it as a texture.
@export var screen_size: Vector2i = Vector2i(960, 640)
## Whether the window reads the keyboard and mouse itself while open.
@export var handle_input: bool = true
## Whether, left alone, it turns itself slowly.
@export var auto_turn: bool = true

const LCD := Color(0.56, 0.68, 0.53)
const LCD_GLOW := Color(0.78, 0.95, 0.82)
const INK := Color(0.08, 0.12, 0.08)
const INK_SOFT := Color(0.20, 0.28, 0.19)
const LEGEND := [["SCORE", Color(1.00, 0.22, 0.22)], ["SAFE / CAMERA", Color(0.80, 0.55, 1.00)],
		["ENTRY", Color(1.00, 0.55, 0.20)], ["STAIRS", Color(1.00, 0.85, 0.35)], ["LADDER", Color(0.55, 1.00, 0.75)],
		["HOLE", Color(1.00, 0.40, 0.70)], ["WINDOW", Color(0.45, 0.85, 0.95)]]
## How far apart the storeys stand when spread, metres.
const SPREAD_M := 6.0
## The slow turn when it is left alone, degrees a second, and how long alone first, seconds.
const AUTO_TURN_DPS := 10.0
const IDLE_S := 3.0
## How far the view tilts: from nearly overhead to nearly level, degrees above the horizon.
const PITCH_MIN := 12.0
const PITCH_MAX := 80.0
## How quickly a flick's turn dies away, per second.
const SPIN_DAMP := 2.5
## How much a floor under the focused one is dimmed.
const DIM := 0.4

const SCREEN_SHADER := """
shader_type canvas_item;
uniform vec4 lcd : source_color;
uniform vec4 glow : source_color;
void fragment() {
	float d = distance(UV, vec2(0.58, 0.42));
	vec3 c = mix(glow.rgb, lcd.rgb, smoothstep(0.0, 0.8, d));
	vec2 px = fract(FRAGCOORD.xy / 3.0);
	c *= 1.0 - 0.07 * min(step(0.8, px.x) + step(0.8, px.y), 1.0);
	COLOR = vec4(c, 1.0);
}
"""
## The model's colours are in its vertex data; alpha below one marks what glows (its accents).
const BODY_SHADER := """
shader_type spatial;
uniform float pulse = 0.0;
uniform float dim = 1.0;
void fragment() {
	ALBEDO = COLOR.rgb * dim;
	ROUGHNESS = 0.9;
	float lit = (1.0 - COLOR.a) * 2.4 + pulse * (0.9 + 0.6 * sin(TIME * 4.0));
	EMISSION = COLOR.rgb * lit;
}
"""

var _entries: Array = []          # [{id, scout_model}] in buildings.json order, one per building id
var _index: int = -1
var _points_override: Dictionary = {}
var _open: bool = false
var _overlay: CanvasLayer
var _shown: TextureRect           # the screen as the overlay shows it
var _rows: Array = []             # [{id, node}] each listed building's row; its rect is in the screen's own pixels
var _screen: SubViewport
var _view3d: SubViewport
var _pivot: Node3D
var _model: Node3D
var _floors: Array = []
var _cam: Camera3D
var _list: VBoxContainer
var _title: Label
var _note: Label
var _yaw: float = 35.0
var _pitch: float = 36.0
var _spin: float = 0.0            # degrees a second, what a flick left behind
var _idle: float = 0.0            # seconds since the player last touched it
var _focus: int = -1              # the floor in focus, by order from the lowest; -1 the whole building
var _spread: float = 1.0
var _radius: float = 10.0
var _dragging: bool = false
var _body_mat: ShaderMaterial
var _dim_mat: ShaderMaterial
var _point_mat: ShaderMaterial


func open(as_overlay: bool = false) -> void:
	"""Build the screen if it is not built, and start drawing it. `as_overlay` also shows it centred over the game."""
	if _screen == null:
		_read_index()
		_build()
		if not _entries.is_empty():
			select(String(_entries[0]["id"]))
	_screen.render_target_update_mode = SubViewport.UPDATE_ALWAYS
	_view3d.render_target_update_mode = SubViewport.UPDATE_ALWAYS
	_overlay.visible = as_overlay
	_open = true
	opened.emit()


func close() -> void:
	"""Stop drawing. The screen keeps its state for the next `open`."""
	if _screen != null:
		_screen.render_target_update_mode = SubViewport.UPDATE_DISABLED
		_view3d.render_target_update_mode = SubViewport.UPDATE_DISABLED
		_overlay.visible = false
	_open = false
	closed.emit()


func is_open() -> bool:
	return _open


func buildings() -> PackedStringArray:
	"""The ids the screen lists, as buildings.json names them."""
	if _entries.is_empty():
		_read_index()
	var out := PackedStringArray()
	for e in _entries:
		out.append(String(e["id"]))
	return out


func get_screen_texture() -> ViewportTexture:
	"""The screen, for the game's handheld to show. Valid after the first `open`."""
	return _screen.get_texture() if _screen != null else null


func select(id: String) -> void:
	"""Show a building by its id."""
	for i in range(_entries.size()):
		if String(_entries[i]["id"]) == id:
			_index = i
			_show()
			building_selected.emit(id)
			return


func set_points(id: String, points: Array) -> void:
	"""The gameplay layer's own points for a building, shown instead of the ones its model carries: each
	{"label": String, "kind": "score" or "poi", "at": Vector3 in the model's frame (metres, y up), "storey": int}.
	With "storey" a point rides its floor when the floors spread apart. An empty Array clears it."""
	if points.is_empty():
		_points_override.erase(id)
	else:
		_points_override[id] = points
	if _index >= 0 and String(_entries[_index]["id"]) == id:
		_show()


func click(screen_pos: Vector2) -> bool:
	"""A click at ``screen_pos``, in the screen's own pixels (0..screen_size): on a building's row, show it. For a
	game whose handheld shows `get_screen_texture()` on a mesh -- turn the hit's UV into pixels (uv * screen_size)
	and pass it here. Returns whether the click landed on something."""
	for r in _rows:
		# the row's own laid-out rect: inside the screen's viewport, global is the screen's pixels
		if is_instance_valid(r["node"]) and (r["node"] as Control).get_global_rect().has_point(screen_pos):
			select(String(r["id"]))
			return true
	return false


func turn(degrees: float) -> void:
	_yaw = fmod(_yaw + degrees, 360.0)
	_aim()


func tilt(degrees: float) -> void:
	"""Raise the view towards overhead (positive) or lower it towards level, within PITCH_MIN..PITCH_MAX."""
	_pitch = clampf(_pitch + degrees, PITCH_MIN, PITCH_MAX)
	_aim()


func focus(floor_index: int) -> void:
	"""Focus one floor, by order from the lowest (0), -1 the whole building: the floors above it step aside, the
	ones below dim, the view centres on it."""
	_focus = clampi(floor_index, -1, _floors.size() - 1)
	_place_floors()


func focused() -> int:
	return _focus


func set_spread(t: float) -> void:
	"""0, the storeys stacked as built; 1, lifted apart."""
	_spread = clampf(t, 0.0, 1.0)
	_place_floors()


# ------------------------------------------------------------------------------------------------- internals

func _read_index() -> void:
	_entries.clear()
	var path: String = package_root.path_join("buildings.json")
	if not FileAccess.file_exists(path):
		push_warning("scout: no %s" % path)
		return
	var idx: Variant = JSON.parse_string(FileAccess.get_file_as_string(path))
	if typeof(idx) != TYPE_DICTIONARY or not (idx as Dictionary).has("buildings"):
		push_warning("scout: %s is not a buildings index" % path)
		return
	var seen := {}
	for e in (idx as Dictionary)["buildings"]:
		var d: Dictionary = e
		if String(d.get("kind", "")) != "building" or seen.has(d["id"]):
			continue
		seen[d["id"]] = true
		_entries.append({"id": String(d["id"]), "scout_model": d.get("scout_model")})


func _box(bg: Color, r: int, border: Color, bw: int) -> StyleBoxFlat:
	var s := StyleBoxFlat.new()
	s.bg_color = bg
	s.set_corner_radius_all(r)
	s.border_color = border
	s.set_border_width_all(bw)
	return s


func _label(text: String, size: int, color: Color, lifted: bool) -> Label:
	var l := Label.new()
	l.text = text
	l.add_theme_font_size_override("font_size", size)
	l.add_theme_color_override("font_color", color)
	if lifted:
		# a hard one-pixel offset in the backlight's tone under the ink
		l.add_theme_color_override("font_shadow_color", Color(LCD_GLOW.r, LCD_GLOW.g, LCD_GLOW.b, 0.85))
		l.add_theme_constant_override("shadow_offset_x", 1)
		l.add_theme_constant_override("shadow_offset_y", 1)
	return l


func _shader_mat(code: String) -> ShaderMaterial:
	var m := ShaderMaterial.new()
	m.shader = Shader.new()
	m.shader.code = code
	return m


func _build() -> void:
	_screen = SubViewport.new()
	_screen.size = screen_size
	_screen.render_target_update_mode = SubViewport.UPDATE_DISABLED
	add_child(_screen)
	var w: float = float(screen_size.x)
	var h: float = float(screen_size.y)
	var lcd := ColorRect.new()
	var sm := _shader_mat(SCREEN_SHADER)
	sm.set_shader_parameter("lcd", LCD)
	sm.set_shader_parameter("glow", LCD_GLOW)
	lcd.material = sm
	lcd.size = Vector2(w, h)
	_screen.add_child(lcd)
	var bar := ColorRect.new()
	bar.color = INK
	bar.size = Vector2(w, 40)
	lcd.add_child(bar)
	var head := _label(" SCOUT", 20, LCD_GLOW, false)
	head.position = Vector2(8, 6)
	lcd.add_child(head)
	_list = VBoxContainer.new()
	_list.position = Vector2(16, 58)
	_list.size = Vector2(w * 0.26, h - 140)
	_list.add_theme_constant_override("separation", 6)
	lcd.add_child(_list)
	var svc := SubViewportContainer.new()
	svc.stretch = true
	svc.position = Vector2(w * 0.29, 52)
	svc.size = Vector2(w * 0.69, h - 150)
	lcd.add_child(svc)
	_view3d = SubViewport.new()
	_view3d.own_world_3d = true
	_view3d.transparent_bg = true
	_view3d.msaa_3d = Viewport.MSAA_4X
	_view3d.render_target_update_mode = SubViewport.UPDATE_DISABLED
	svc.add_child(_view3d)
	var env := WorldEnvironment.new()
	var e := Environment.new()
	e.background_mode = Environment.BG_CLEAR_COLOR
	e.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	e.ambient_light_color = Color(1, 1, 1)
	e.ambient_light_energy = 0.55
	env.environment = e
	_view3d.add_child(env)
	var sun := DirectionalLight3D.new()
	sun.rotation_degrees = Vector3(-55, -35, 0)
	sun.light_energy = 0.6
	sun.shadow_enabled = true
	_view3d.add_child(sun)
	_pivot = Node3D.new()
	_view3d.add_child(_pivot)
	_cam = Camera3D.new()
	_cam.fov = 30.0
	_view3d.add_child(_cam)
	_title = _label("", 22, INK, true)
	_title.position = Vector2(w * 0.29 + 10, h - 96)
	lcd.add_child(_title)
	_note = _label("", 13, INK_SOFT, false)
	_note.position = Vector2(w * 0.29 + 10, h - 66)
	lcd.add_child(_note)
	var leg := HBoxContainer.new()
	leg.position = Vector2(16, h - 34)
	leg.add_theme_constant_override("separation", 6)
	lcd.add_child(leg)
	for item in LEGEND:
		var chip := PanelContainer.new()
		chip.add_theme_stylebox_override("panel", _box(INK, 4, INK, 0))
		chip.add_child(_label(" %s " % item[0], 11, item[1], false))
		leg.add_child(chip)
	_body_mat = _shader_mat(BODY_SHADER)
	_dim_mat = _shader_mat(BODY_SHADER)
	_dim_mat.set_shader_parameter("dim", DIM)
	_point_mat = _shader_mat(BODY_SHADER)
	_point_mat.set_shader_parameter("pulse", 1.0)
	_overlay = CanvasLayer.new()
	_overlay.layer = 90
	_overlay.visible = false
	add_child(_overlay)
	_shown = TextureRect.new()
	_shown.texture = _screen.get_texture()
	_shown.set_anchors_preset(Control.PRESET_CENTER)
	_shown.position = -Vector2(w, h) * 0.5
	_shown.size = Vector2(w, h)
	_overlay.add_child(_shown)


func _show() -> void:
	if _screen == null or _index < 0:
		return
	for c in _list.get_children():
		c.free()
	_list.add_child(_label("BUILDINGS", 15, INK_SOFT, false))
	_rows.clear()
	for j in range(_entries.size()):
		var sel: bool = j == _index
		var row := PanelContainer.new()
		row.add_theme_stylebox_override("panel", _box(INK if sel else Color(0, 0, 0, 0), 3, INK_SOFT, 0 if sel else 1))
		var shown_name: String = String(_entries[j]["id"]).to_upper().replace("_", " ")
		row.add_child(_label("  %s %s" % [">" if sel else " ", shown_name], 15, LCD_GLOW if sel else INK, false))
		_list.add_child(row)
		_rows.append({"id": String(_entries[j]["id"]), "node": row})
	if _model != null:
		_model.free()
		_model = null
	_floors.clear()
	var id: String = String(_entries[_index]["id"])
	_title.text = id.to_upper().replace("_", " ")
	var rel: Variant = _entries[_index]["scout_model"]
	if rel == null:
		_note.text = "NO SCHEMATIC FOR THIS BUILDING"
		return
	var doc := GLTFDocument.new()
	var state := GLTFState.new()
	if doc.append_from_file(ProjectSettings.globalize_path(String(rel)), state) != OK:
		_note.text = "SCHEMATIC WOULD NOT LOAD"
		return
	_model = doc.generate_scene(state)
	_pivot.add_child(_model)
	var meshes: Array = []
	_collect(_model, meshes)
	for n in meshes:
		var mi: MeshInstance3D = n as MeshInstance3D
		var is_points: bool = String(mi.name).ends_with("_points")
		mi.material_override = _point_mat if is_points else _body_mat
		mi.visible = not (is_points and _points_override.has(id))
		if not is_points:
			_floors.append({"node": mi, "y": mi.position.y})
	_floors.sort_custom(func(a: Dictionary, b: Dictionary) -> bool: return float(a["y"]) < float(b["y"]))
	_focus = -1
	if _points_override.has(id):
		for p in _points_override[id]:
			_add_override_point(p)
	_place_floors()


func _add_override_point(p: Dictionary) -> void:
	var m := MeshInstance3D.new()
	var b := BoxMesh.new()
	b.size = Vector3(0.6, 2.8, 0.6) if String(p.get("kind", "poi")) == "score" else Vector3(0.6, 0.6, 0.6)
	m.mesh = b
	var mat := StandardMaterial3D.new()
	var c: Color = LEGEND[0][1] if String(p.get("kind", "poi")) == "score" else LEGEND[1][1]
	mat.albedo_color = c
	mat.emission_enabled = true
	mat.emission = c
	m.material_override = mat
	var at: Vector3 = p.get("at", Vector3.ZERO)
	var floor_node: Node3D = null
	if p.has("storey"):
		floor_node = _model.find_child("storey_%d" % int(p["storey"]), true, false) as Node3D
	if floor_node != null:
		# a point on a storey rides it: placed under the floor, at its height over the storey's own elevation
		var built_y: float = 0.0
		for f in _floors:
			if f["node"] == floor_node:
				built_y = float(f["y"])
		m.position = Vector3(at.x, at.y - built_y, at.z)
		floor_node.add_child(m)
	else:
		m.position = at
		_model.add_child(m)


func _place_floors() -> void:
	if _model == null or _floors.is_empty():
		return
	# FOCUS (0.236.0): the floors above the focused one step aside -- hidden, their points with them -- and the ones
	# below dim, so turning shows every side of the focused floor with nothing standing over it; the view frames it
	var box := AABB()
	var first: bool = true
	for k in range(_floors.size()):
		var mi: MeshInstance3D = _floors[k]["node"]
		mi.position.y = float(_floors[k]["y"]) + k * SPREAD_M * _spread
		mi.visible = _focus < 0 or k <= _focus
		mi.material_override = _dim_mat if (_focus >= 0 and k < _focus) else _body_mat
		if _focus >= 0 and k != _focus:
			continue
		var b: AABB = mi.transform * mi.get_aabb()
		box = b if first else box.merge(b)
		first = false
	_model.position = -box.get_center()
	_radius = maxf(box.size.length() * 0.5, 4.0)
	var where: String = "WHOLE BUILDING" if _focus < 0 else "FLOOR %d OF %d" % [_focus + 1, _floors.size()]
	_note.text = "%s  -  DRAG TO TURN AND TILT  -  UP/DOWN: FLOOR" % where
	_aim()


func _aim() -> void:
	if _cam == null:
		return
	var r: float = deg_to_rad(_yaw)
	var el: float = deg_to_rad(_pitch)
	var d: float = _radius / sin(deg_to_rad(_cam.fov * 0.5))
	_cam.position = Vector3(cos(r) * cos(el), sin(el), sin(r) * cos(el)) * d
	_cam.look_at(Vector3.ZERO, Vector3.UP)


func _collect(n: Node, out: Array) -> void:
	if n is MeshInstance3D:
		out.append(n)
	for c in n.get_children():
		_collect(c, out)


func _process(delta: float) -> void:
	if not _open or _cam == null:
		return
	_idle += delta
	if _dragging:
		return
	# a flick keeps turning and dies away; left alone, it turns itself slowly
	if absf(_spin) > 0.5:
		turn(_spin * delta)
		_spin *= exp(-SPIN_DAMP * delta)
	elif auto_turn and _idle > IDLE_S:
		turn(AUTO_TURN_DPS * delta)


func _to_screen(viewport_pos: Vector2) -> Vector2:
	"""A point of the game's viewport, as the overlay shows the screen, in the screen's own pixels."""
	var r: Rect2 = _shown.get_global_rect()
	return (viewport_pos - r.position) * Vector2(screen_size) / r.size


func _wheel(event: InputEvent, button: MouseButton) -> bool:
	"""One notch of the scroll wheel, the walker's: "scroll wheel should be the up down as well (floors)"."""
	var b: InputEventMouseButton = event as InputEventMouseButton
	return b != null and b.pressed and b.button_index == button


func _unhandled_input(event: InputEvent) -> void:
	if not _open or not handle_input or _entries.is_empty():
		return
	var n: int = _floors.size()
	if event.is_action_pressed("ui_cancel"):
		close()
	elif event.is_action_pressed("ui_right"):
		select(String(_entries[(_index + 1) % _entries.size()]["id"]))
	elif event.is_action_pressed("ui_left"):
		select(String(_entries[(_index - 1 + _entries.size()) % _entries.size()]["id"]))
	elif event.is_action_pressed("ui_down") or _wheel(event, MOUSE_BUTTON_WHEEL_DOWN):
		# down through the building: the whole of it, then the top floor, then each one below -- the arrow or the wheel
		focus(n - 1 if _focus < 0 else maxi(_focus - 1, 0))
	elif event.is_action_pressed("ui_up") or _wheel(event, MOUSE_BUTTON_WHEEL_UP):
		# up through it, and past the top floor the whole building again
		focus(-1 if (_focus < 0 or _focus >= n - 1) else _focus + 1)
	elif event is InputEventMouseButton and (event as InputEventMouseButton).button_index == MOUSE_BUTTON_LEFT \
			and (event as InputEventMouseButton).pressed and _overlay.visible \
			and click(_to_screen((event as InputEventMouseButton).position)):
		pass                         # a row clicked in the overlay: it shows that building, and no drag starts
	elif event is InputEventMouseButton and (event as InputEventMouseButton).button_index == MOUSE_BUTTON_LEFT:
		_dragging = (event as InputEventMouseButton).pressed
		if _dragging:
			_spin = 0.0
	elif event is InputEventMouseMotion and _dragging:
		var rel: Vector2 = (event as InputEventMouseMotion).relative
		turn(rel.x * 0.4)
		tilt(rel.y * 0.25)
		# what the turn would carry on at if let go now: this motion's degrees over a frame's time
		_spin = rel.x * 0.4 / maxf(get_process_delta_time(), 1.0 / 240.0)
	else:
		return
	_idle = 0.0
	get_viewport().set_input_as_handled()
