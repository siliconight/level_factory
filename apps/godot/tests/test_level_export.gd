extends SceneTree
## The Level tab's Export, headless: an export answer is shown with where the snapshot went and its checklist, each
## line's state coloured, and the panel says how many lines are not ok. The export itself is proven against the real
## pipeline by the factory's `patches/lf_export/` records.
##
##     godot --headless --path <this project> --script res://tests/test_level_export.gd

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
	panel.show_export({"snapshot": "D:/levels/ship_it_v1", "checklist": [
		{"item": "Package complete", "state": "ok", "detail": "2786 files"},
		{"item": "Opens without the factory", "state": "ok", "detail": "portability PASS"},
		{"item": "Lights baked", "state": "unknown", "detail": "no light_bake.json: not baked"},
		{"item": "Findings left", "state": "problem", "detail": "1 major on the chosen layout"}]})
	var rows: Array = panel._checklist.get_root().get_children()
	_check(rows.size() == 4, "every checklist line is shown")
	_check(rows[2].get_text(0) == "unknown" and rows[2].get_text(2).contains("not baked"), "an unknown line says why")
	var said: String = panel._export_status.text
	_check(said.contains("D:/levels/ship_it_v1"), "it says where the snapshot went")
	_check(said.contains("2 item(s) on the checklist are not ok"), "and how many lines are not ok: %s" % said)
	_check(panel._export_dialog.file_mode == FileDialog.FILE_MODE_OPEN_DIR, "the destination is chosen as a folder")
	panel.queue_free()
	print("DONE failures=%d" % _failures)
	quit(1 if _failures else 0)
