extends SceneTree
## The Level tab's Walk level, headless: a walk answer is shown with the design revision and layout it is of and the
## self-check's verdict, and the command that opens the preview is `godot --path <preview>` -- or, with no Godot
## recorded, the panel says where the preview is instead. No window is opened: `launch_previews` is off.
##
##     godot --headless --path <this project> --script res://tests/test_level_walk.gd
##
## Prints PASS or FAIL lines; quits 0 only when every case passed. The walk itself is proven against the real pipeline
## by the factory's `patches/lf_walk/` records: it takes minutes.

const LevelPanel := preload("res://addons/gabagool_factory/level_panel.gd")

var _failures := 0


func _initialize() -> void:
	_run.call_deferred()


func _check(ok: bool, what: String) -> void:
	print(("PASS " if ok else "FAIL ") + what)
	if not ok:
		_failures += 1


func _run() -> void:
	var panel: Control = LevelPanel.new()
	root.add_child(panel)
	await process_frame
	panel.launch_previews = false

	var walked := {"preview": "C:/levels/x/workspace/.level_factory/preview/x_001_walk", "godot": "C:/Godot/godot.exe",
		"self_check": "findings", "label": "X, revision 3, layout seed 9205"}
	panel.show_walk(walked)
	var said: String = panel._walk_status.text
	_check(said.contains("revision 3") and said.contains("9205"), "the walk names its revision and layout: %s" % said)
	_check(said.contains("self-check found something"), "and says when its self-check found something")
	var command: Array = LevelPanel.preview_command(walked)
	_check(command.size() == 2 and command[0] == "C:/Godot/godot.exe", "the preview opens with the recorded Godot")
	_check(Array(command[1]) == ["--path", walked["preview"]], "pointed at the preview project: %s" % [command[1]])

	walked["godot"] = ""
	panel.show_walk(walked)
	_check(panel._walk_status.text.contains("open %s in Godot" % walked["preview"]),
		"with no Godot recorded it says where the preview is")
	_check(LevelPanel.preview_command(walked).is_empty(), "and offers no command")

	panel.queue_free()
	print("DONE failures=%d" % _failures)
	quit(1 if _failures else 0)
