@tool
extends EditorPlugin
## Level Factory's light bake (0.131.0, `packages/exporting/light_bake.py`),
## from roadmap item 31's probe: bake `res://bake.tscn`'s LightmapGI with the
## editor's own Bake Lightmaps button (Godot 4.7 exposes no script call),
## save, write `res://bake_result.json`, and quit. Every wait is counted in
## frames and bounded; a failure writes what it saw and quits all the same.

const SCENE := "res://bake.tscn"
const OUT := "res://light_bake_result.json"
const BAKE_LIMIT_MS := 800000

var _phase: int = 0
var _frames: int = 0
var _t0: int = 0
var _lm: LightmapGI = null
## A bake and a save each show a progress bar that pumps the editor's main
## loop, which calls `_process` again from inside them; the control run's
## save recursed until the stack overflowed. Nothing runs while this is set.
var _busy: bool = false


func _enter_tree() -> void:
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


func _process(_delta: float) -> void:
	if _busy:
		return
	_frames += 1
	match _phase:
		0:
			if _frames < 180:
				return
			EditorInterface.open_scene_from_path(SCENE)
			_phase = 1
			_frames = 0
		1:
			if _frames < 240:
				return
			var root := EditorInterface.get_edited_scene_root()
			if root == null or root.scene_file_path != SCENE:
				if _frames > 3000:
					_done({"ok": false, "error": "bake.tscn did not open"})
				return
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
			_busy = true
			EditorInterface.save_scene()
			_busy = false
			var d: LightmapGIData = _lm.light_data
			var tex: Array = []
			for t in d.get_lightmap_textures():
				if t != null:
					tex.append({"path": t.resource_path, "w": t.get_width(), "h": t.get_height()})
			_done({"ok": true, "bake_ms": took, "users": d.get_user_count(),
				"data_path": d.resource_path, "textures": tex,
				"quality": _lm.quality, "bounces": _lm.bounces})
