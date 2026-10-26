extends SceneTree
## The Level tab reopening a level, headless: its layouts come back with the chosen one selected, the last walk and
## export are shown and say when the level has changed since, and a level opened after another shows none of the
## other's. The records are read by `open_design`, proven in the factory's `patches/lf_standing/` records.
##
##     godot --headless --path <this project> --script res://tests/test_level_reopen.gd

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
	panel.design = {"name": "Back Again", "revision": 2}
	panel.show_standing({"layouts": {"candidates": [
			{"candidate_id": "m.candidate.seed_9003", "seed": 9003, "state": "valid", "out_for": [], "plan": null,
				"plan_problem": "none drawn"},
			{"candidate_id": "m.candidate.seed_9205", "seed": 9205, "state": "valid", "out_for": [], "plan": null,
				"plan_problem": "none drawn"}],
			"recommended": "m.candidate.seed_9205", "every_out": false, "recommendation": "Ranked.",
			"design_revision": 1},
		"layouts_stale": [], "chosen": "m.candidate.seed_9003",
		"walk": {"label": "Back Again, revision 1, layout seed 9003", "current": false},
		"export": {"snapshot": "D:/levels/back_v1", "design_revision": 1, "current": false, "snapshot_present": false,
			"checklist": [{"item": "Package complete", "state": "ok", "detail": "2 files"}]},
		"problems": []})
	var selected: TreeItem = panel._layouts.get_selected()
	_check(selected != null and selected.get_metadata(0) == "m.candidate.seed_9003",
		"the chosen layout is selected, not the recommended one")
	_check(panel._build_status.text.contains("Using seed 9003, chosen earlier"), "and said: %s" % panel._build_status.text)
	_check(not panel._use.disabled, "the layouts can be chosen again")
	_check(panel._walk_status.text.contains("seed 9003") and panel._walk_status.text.contains("walk it to see revision 2"),
		"an old walk says the level changed since: %s" % panel._walk_status.text)
	_check(panel._export_status.text.begins_with("Last export, revision 1: Exported to D:/levels/back_v1")
		and panel._export_status.text.contains("changed since that export")
		and panel._export_status.text.contains("no longer there"), "and so does an old export, gone: %s"
		% panel._export_status.text)
	_check(panel._checklist.get_root().get_children().size() == 1, "with its checklist")

	panel.design = {"name": "Brand New", "revision": 1}
	panel.show_standing({"layouts": null, "layouts_stale": [], "chosen": null, "walk": null, "export": null,
		"problems": []})
	_check(panel._layouts.get_root() == null, "a level opened after another shows none of its layouts")
	_check(panel._walk_status.text == "" and panel._export_status.text == "" and panel._use.disabled,
		"nor its walk, its export or a layout to use")
	_check(panel._checklist.get_root() == null, "nor its checklist")

	panel.queue_free()
	print("DONE failures=%d" % _failures)
	quit(1 if _failures else 0)
