extends SceneTree
## The walker's first windowed run (0.256.0): the panel restarted mid-walk and lost it, and nothing opened a walk
## already built. A panel re-attaches to the operation it recorded -- a finished one is shown at once, a running one
## when its result lands -- and "Open the last walk" appears when a walk record names a preview.
##
##     godot --headless --path <this project> --script res://tests/test_panel_resume.gd

const LevelPanel := preload("res://addons/gabagool_factory/level_panel.gd")

var _failures := 0


func _initialize() -> void:
	_run.call_deferred()


func _check(ok: bool, what: String) -> void:
	print(("PASS " if ok else "FAIL ") + what)
	if not ok:
		_failures += 1


func _run_dir(name: String) -> String:
	var dir := ProjectSettings.globalize_path("user://factory_runs").path_join(name)
	DirAccess.make_dir_recursive_absolute(dir)
	return dir


func _write(path: String, data: Variant) -> void:
	var f := FileAccess.open(path, FileAccess.WRITE)
	f.store_string(JSON.stringify(data))
	f.close()


func _walk_result(label: String) -> Dictionary:
	return {"schema": "gabagool.service.result.v1", "status": "ok", "error": null, "data": {"label": label,
		"self_check": "passed", "preview": "C:/x/preview", "godot": "C:/Godot/godot.exe"}}


func _run() -> void:
	var record := ProjectSettings.globalize_path("user://factory_runs").path_join("current_level.json")

	# a walk that finished while no panel watched: shown at once
	var done := _run_dir("test_resume_done")
	_write(done.path_join("result.json"), _walk_result("Done While Away, revision 1, layout seed 9205"))
	_write(record, {"run_dir": done, "operation": "walk_level"})
	var panel: Control = LevelPanel.new()
	panel.launch_previews = false
	root.add_child(panel)
	await process_frame
	panel._resume()
	for i in 20:
		await process_frame
		if not panel.client.is_running():
			break
	await create_timer(0.6).timeout
	_check(panel._walk_status.text.contains("Done While Away"), "a walk that finished meanwhile is shown: %s"
		% panel._walk_status.text)
	_check(not FileAccess.file_exists(record), "and its record is cleared")
	_check(panel._open_walk.visible, "Open the last walk is offered")

	# a walk still running: followed until its result lands, Stop reaching it
	var running := _run_dir("test_resume_running")
	_write(record, {"run_dir": running, "operation": "walk_level"})
	panel._resume()
	_check(panel.client.is_running() and panel._walk_status.text.begins_with("Still running"),
		"a running walk is re-attached: %s" % panel._walk_status.text)
	_check(panel.client.cancel() and FileAccess.file_exists(running.path_join("cancel")), "Stop reaches it")
	_write(running.path_join("result.json"), _walk_result("Finished Later, revision 2, layout seed 9003"))
	await create_timer(0.8).timeout
	_check(not panel.client.is_running() and panel._walk_status.text.contains("Finished Later"),
		"and its answer is shown when it lands: %s" % panel._walk_status.text)

	# nothing recorded: nothing to re-attach
	_check(panel.client.resume() == "", "with nothing recorded there is nothing to resume")

	# a reopened level with a walk record offers it
	panel.show_standing({"walk": {"label": "x", "current": true, "preview": "C:/x/preview", "godot": "C:/g.exe"}})
	_check(panel._open_walk.visible and panel.walk_result.get("preview") == "C:/x/preview",
		"a reopened level offers its last walk")
	panel.show_standing({})
	_check(not panel._open_walk.visible, "and a level never walked does not")

	for d in [done, running]:
		for f in DirAccess.get_files_at(d):
			DirAccess.remove_absolute(d.path_join(f))
		DirAccess.remove_absolute(d)
	panel.queue_free()
	print("DONE failures=%d" % _failures)
	quit(1 if _failures else 0)
