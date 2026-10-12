@tool
extends EditorPlugin
## Level Factory's light bake (0.131.0, `packages/exporting/light_bake.py`),
## from roadmap item 31's probe: bake `res://bake.tscn`'s LightmapGI with the
## editor's own Bake Lightmaps button (Godot 4.7 exposes no script call),
## save, write `res://bake_result.json`, and quit. Every wait is counted in
## frames and bounded; a failure writes what it saw and quits all the same.
##
## THE EDITOR STAYS AWAKE, AND THE SCENE IS ASKED FOR UNTIL IT OPENS (0.178.5).
## Cold run 9242's bake wrote `bake.tscn did not open` after 83.7 s, and a
## re-run of it 371.8 s: an editor whose window has no focus sleeps 100 ms a
## frame (Godot's unfocused low-processor mode), so 3,180 counted frames came to
## minutes while the editor's first open -- which re-imports every texture it
## finds used in 3D -- crawled at the same pace. The same plugin with the mode
## held off, the open asked once the file scan is idle and again until it
## lands, and the wait judged on a clock, opened 9242's scene in 21 s and baked
## it. The bake's own wait (BAKE_LIMIT_MS) was always a clock.
##
## THE EDITOR'S CLOCK IS STOPPED, AND THE OPEN IS LOOKED FOR AT ONCE (0.192.0).
## Two exports of one level baked different lightmaps, and the difference was
## not the bake's. Lux's failing fixtures keep their clocks in this editor too
## (`_fail_t += delta`) and dim their lenses with their lamps, and a lens's
## emission is baked: the lightmap kept each failing lens at whatever level it
## had when Bake was pressed. With `Engine.time_scale` 0 from the start every
## such clock stays at 0, and cold run 9257's level baked the same `bake.exr`,
## `bake.lmbake` and `bake.exr.import`, byte for byte, whether Bake was pressed
## 4.4 s earlier or not -- where two bakes with the clock running differed in
## all three every time (the factory's docs/findings/grader_speed/README.md).
## Frames still advance, and every wait here counts frames or reads
## `Time.get_ticks_msec()`, which is not scaled. Which level a failing lens
## should bake at is a look, not settled here: at 0 a stuttering tube is at
## full, a filament at about 0.97, and a cycling streetlight wherever its own
## seed puts it in its cycle.
##
## The scene was open at the first look in every bake (cold runs 9254 to 9257
## logged it open at frame 240, the floor itself): the editor draws the opened
## level's first frame in about 10 s and the 239 after it in about 4. The
## floor is one frame now; an open that has not landed is still asked again.

const SCENE := "res://bake.tscn"
const OUT := "res://light_bake_result.json"
const BAKE_LIMIT_MS := 800000

var _phase: int = 0
var _frames: int = 0
var _t0: int = 0
## When the scene was first asked for, and how long it may take to open (0.178.5).
var _open_t0: int = 0
const OPEN_LIMIT_MS := 300000
## The frames before the opened scene is first looked for (0.192.0). It was
## 240, and the scene was open at that first look in every bake.
const OPEN_FLOOR_FRAMES := 1
var _lm: LightmapGI = null
## A bake and a save each show a progress bar that pumps the editor's main
## loop, which calls `_process` again from inside them; the control run's
## save recursed until the stack overflowed. Nothing runs while this is set.
var _busy: bool = false
## THE ROOMS' FLOOR (0.151.0). Lux >= 0.68.0 lays bake-only fills over the
## level's room probes (`LuxLightLoader.add_bake_fills`), because a
## lightmapped wall takes no light from a room probe's ambient. The lightmap
## must keep their light and the saved scene must not keep them: laid after
## the scene opens and before Bake is pressed, freed before the save.
## `_fill_count` is -1 when the level's Lux has no such call.
var _fill: Node = null
var _fill_count: int = -1


func _enter_tree() -> void:
	# An unfocused editor sleeps between frames; a bake on someone's desktop
	# rarely has the focus. Held off here and every frame (0.178.5).
	OS.low_processor_usage_mode = false
	# Every clock a script keeps from its frames stops here, before the scene
	# opens: the failing fixtures' lenses bake at one level whenever Bake is
	# pressed (0.192.0, the header says why).
	Engine.time_scale = 0.0
	set_process(true)


func _done(result: Dictionary) -> void:
	set_process(false)
	var f := FileAccess.open(OUT, FileAccess.WRITE)
	if f != null:
		f.store_string(JSON.stringify(result, " "))
		f.close()
	print("BAKE ", JSON.stringify(result))
	var tree := EditorInterface.get_base_control().get_tree()
	tree.quit()
	await tree.process_frame
	await tree.process_frame
	OS.kill(OS.get_process_id())


## Where the bake writes. A LightmapGI with no data file yet makes the
## editor ASK, in a file dialog titled "Select lightmap bake file:" (found by
## the control run); that one dialog is answered with this path.
const DATA_PATH := "res://bake.lmbake"


func _visible_dialogs() -> Array:
	var out: Array = []
	var root: Node = EditorInterface.get_base_control().get_tree().root
	for d in root.find_children("*", "AcceptDialog", true, false):
		var dlg := d as AcceptDialog
		if dlg == null or not dlg.visible:
			continue
		if dlg is EditorFileDialog and dlg.title.begins_with("Select lightmap bake file"):
			dlg.hide()
			_busy = true
			(dlg as EditorFileDialog).file_selected.emit(DATA_PATH)
			_busy = false
			print("BAKE answered the save dialog with ", DATA_PATH)
			continue
		out.append({"title": dlg.title, "text": dlg.dialog_text})
		dlg.hide()
	return out


func _find_button(n: Node) -> Button:
	if n is Button and (n as Button).text.contains("Bake Lightmaps"):
		return n
	for c in n.get_children():
		var b := _find_button(c)
		if b != null:
			return b
	return null


## The level's Lux loader sits beside its LuxRoot's script, in a package
## (`res://runtime/lux/runtime/`) and in Lux's own repo alike. Its
## `add_bake_fills` lays the fill under `root` and returns the container.
func _lay_room_fill(root: Node) -> Node:
	if root == null:
		return null
	for n in root.get_tree().get_nodes_in_group(&"lux_root"):
		if n != root and not root.is_ancestor_of(n):
			continue
		var s: Script = n.get_script()
		if s == null:
			continue
		var path := s.resource_path.get_base_dir().path_join("lux_light_loader.gd")
		if not ResourceLoader.exists(path):
			continue
		var loader: Script = load(path)
		if loader == null or not loader.has_method("add_bake_fills"):
			return null
		var fill: Node = loader.call("add_bake_fills", root)
		_fill_count = fill.get_child_count() if fill != null else 0
		print("BAKE room fills: ", _fill_count)
		return fill
	return null


func _free_room_fill() -> void:
	if _fill != null and is_instance_valid(_fill):
		_fill.free()
	_fill = null


func _process(_delta: float) -> void:
	OS.low_processor_usage_mode = false
	if _busy:
		return
	_frames += 1
	match _phase:
		0:
			if _frames < 180 or EditorInterface.get_resource_filesystem().is_scanning():
				return
			EditorInterface.open_scene_from_path(SCENE)
			_open_t0 = Time.get_ticks_msec()
			print("BAKE asked to open the scene at frame ", _frames)
			_phase = 1
			_frames = 0
		1:
			if _frames < OPEN_FLOOR_FRAMES:
				return
			var root := EditorInterface.get_edited_scene_root()
			if root == null or root.scene_file_path != SCENE:
				# asked again until it lands: an open asked during the editor's
				# first scan or re-import can be dropped
				if _frames % 300 == 0 and not EditorInterface.get_resource_filesystem().is_scanning():
					print("BAKE asked again at frame ", _frames)
					EditorInterface.open_scene_from_path(SCENE)
				var waited: int = Time.get_ticks_msec() - _open_t0
				if waited > OPEN_LIMIT_MS:
					_done({"ok": false, "error": "bake.tscn did not open",
						"waited_ms": waited, "frames": _frames})
				return
			print("BAKE the scene opened after ", Time.get_ticks_msec() - _open_t0, " ms, frame ", _frames)
			_lm = root.get_node_or_null("Lightmap") as LightmapGI
			if _lm == null:
				_done({"ok": false, "error": "no Lightmap node"})
				return
			EditorInterface.get_selection().clear()
			EditorInterface.get_selection().add_node(_lm)
			EditorInterface.edit_node(_lm)
			_phase = 2
			_frames = 0
		2:
			if _frames < 90:
				return
			var b := _find_button(EditorInterface.get_base_control())
			if b == null:
				_done({"ok": false, "error": "no Bake Lightmaps button"})
				return
			_fill = _lay_room_fill(EditorInterface.get_edited_scene_root())
			_t0 = Time.get_ticks_msec()
			_busy = true
			b.pressed.emit()
			_busy = false
			_phase = 3
			_frames = 0
		3:
			var took: int = Time.get_ticks_msec() - _t0
			# A REFUSED BAKE RAISES A MODAL DIALOG AND RETURNS AT ONCE. The
			# first run of this probe waited 25 minutes for light data behind
			# one. Read any visible dialog's text, close it, and stop.
			if _frames % 15 == 0:
				var said := _visible_dialogs()
				if not said.is_empty():
					_done({"ok": false, "error": "the bake raised a dialog", "dialogs": said,
						"after_ms": took})
					return
			if _lm.light_data == null:
				if took > BAKE_LIMIT_MS:
					_done({"ok": false, "error": "no light data after %d ms" % took})
				return
			if _frames < 30:
				return
			_free_room_fill()
			_busy = true
			EditorInterface.save_scene()
			_busy = false
			var d: LightmapGIData = _lm.light_data
			var tex: Array = []
			for t in d.get_lightmap_textures():
				if t != null:
					tex.append({"path": t.resource_path, "w": t.get_width(), "h": t.get_height()})
			_done({"ok": true, "bake_ms": took, "users": d.get_user_count(),
				"room_fills": _fill_count,
				"data_path": d.resource_path, "textures": tex,
				"quality": _lm.quality, "bounces": _lm.bounces})
