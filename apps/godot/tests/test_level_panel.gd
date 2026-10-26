extends SceneTree
## The Level tab, headless, against the real factory: it lists the templates, starts a level, shows every control
## with whether it drives generation or only records intent, and opens the saved level again.
##
##     godot --headless --path <this project> --script res://tests/test_level_panel.gd -- [<python> <cli main.py>]
##
## The level it makes is its own: named for this run, under `<factory>/levels/`, and deleted at the end. Prints PASS
## or FAIL lines; quits 0 only when every case passed.

const LevelPanel := preload("res://addons/gabagool_factory/level_panel.gd")
const FactoryDock := preload("res://addons/gabagool_factory/factory_dock.gd")

var _failures := 0


func _initialize() -> void:
	_run.call_deferred()


func _check(ok: bool, what: String) -> void:
	print(("PASS " if ok else "FAIL ") + what)
	if not ok:
		_failures += 1


func _settle(panel: Node) -> void:
	# until the panel's queue is empty and its client idle
	for i in range(2400):
		await process_frame
		if not panel.client.is_running() and panel._queue.is_empty():
			return


func _run() -> void:
	var factory := FactoryDock.find_factory_root(ProjectSettings.globalize_path("res://"))
	var panel: Control = LevelPanel.new()
	root.add_child(panel)
	var user_args := OS.get_cmdline_user_args()
	if user_args.size() >= 2:
		panel.client.launch_prefix = PackedStringArray([user_args[0], user_args[1]])
	panel.set_factory_root(factory)
	await _settle(panel)
	_check(panel._template_ids.has("restaurant_row"), "the templates include Restaurant Row: %s" % [panel._template_ids])

	var level_name := "godot test level %d" % Time.get_ticks_usec()
	panel._name.text = level_name
	panel.new_level()
	await _settle(panel)
	var made: Dictionary = panel.design
	_check(made.get("revision") == 1 and made.get("name") == level_name, "a new level is revision 1: %s" % made.get("name"))
	_check(FileAccess.file_exists(panel.design_path), "it is saved by the factory: %s" % panel.design_path)
	var rows: Array = panel._form.get_root().get_children() if panel._form.get_root() != null else []
	_check(rows.size() >= 10, "the form shows every control (%d)" % rows.size())
	var said: Array = rows.map(func(it: TreeItem) -> String: return it.get_text(2))
	_check(said.has("drives generation") and said.has("intent only: saved, not built"),
		"each control says whether it drives generation or only records intent")
	var time_row: Array = rows.filter(func(it: TreeItem) -> bool: return it.get_text(0) == "Time of day")
	_check(time_row.size() == 1 and time_row[0].get_text(1) == "Evening", "Time of day shows the template's Evening")

	var path: String = panel.design_path
	panel.design = {}
	panel.open_design(path)
	await _settle(panel)
	_check(panel.design.get("design_id") == made.get("design_id"), "opening it again gives the same level")
	_check(panel._design_paths.has(path), "it is listed among the saved levels")

	# the level is this test's: remove its folder
	var folder := path.get_base_dir()
	for f in DirAccess.get_files_at(folder):
		DirAccess.remove_absolute(folder.path_join(f))
	DirAccess.remove_absolute(folder)
	_check(not DirAccess.dir_exists_absolute(folder), "the test's level is removed")
	panel.queue_free()
	print("DONE failures=%d" % _failures)
	quit(1 if _failures else 0)
