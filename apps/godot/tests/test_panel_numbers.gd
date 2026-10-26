extends SceneTree
## The walker's first windowed run (0.256.0): whole numbers read "revision 1.0" and "Seed 9003.0", and the Setup tab
## cut every column off with nothing to show the rest. Numbers are shown as people write them; every check cell
## carries its whole text as a tooltip.
##
##     godot --headless --path <this project> --script res://tests/test_panel_numbers.gd

const LevelPanel := preload("res://addons/gabagool_factory/level_panel.gd")
const FactoryDock := preload("res://addons/gabagool_factory/factory_dock.gd")

var _failures := 0


func _initialize() -> void:
	_run.call_deferred()


func _check(ok: bool, what: String) -> void:
	print(("PASS " if ok else "FAIL ") + what)
	if not ok:
		_failures += 1


func _run() -> void:
	_check(LevelPanel.whole(9003.0) == "9003" and LevelPanel.whole(1.0) == "1", "whole numbers lose the .0")
	_check(LevelPanel.whole(0.5) == "0.5" and LevelPanel.whole("?") == "?", "anything else is shown as it is")

	var panel: Control = LevelPanel.new()
	root.add_child(panel)
	await process_frame
	var parsed: Variant = JSON.parse_string('{"candidates": [{"candidate_id": "m.candidate.seed_9003", "seed": 9003, '
		+ '"state": "valid", "out_for": [], "plan": null}], "recommended": "m.candidate.seed_9003", "every_out": false}')
	panel.show_layouts(parsed)
	var row: TreeItem = panel._layouts.get_root().get_child(0)
	_check(row.get_text(0) == "Seed 9003", "a seed parsed from JSON reads as written: %s" % row.get_text(0))
	# a stage that counts nothing moves the bar instead of leaving the last number on it
	panel._on_event({"operation": "walk_level", "stage": "art", "status": "running", "message": "89 of 90", "progress": 0.99})
	panel._on_event({"operation": "walk_level", "stage": "preview", "status": "running",
		"message": "Stage 5 of 5: Building the walk preview and checking it"})
	_check(panel._progress.indeterminate, "a stage that cannot count shows motion, not 99%")
	_check(panel._walk_status.text.begins_with("Stage 5 of 5"), "and says which stage it is")
	panel._on_event({"operation": "walk_level", "stage": "art", "status": "running", "message": "1 of 9", "progress": 0.1})
	_check(not panel._progress.indeterminate and is_equal_approx(panel._progress.value, 0.1), "a count shows the count")
	panel.queue_free()

	var dock: Control = FactoryDock.new()
	root.add_child(dock)
	await process_frame
	dock.show_installation({"ready": false, "blocking": [], "checks": [{"name": "tool:lot", "readiness": "warning",
		"label": "Lot (sites and streets)", "technical": "lot 0.130.0 vs certified 0.126.0",
		"fix": "This tool is newer than the certified set. Levels build; the combination is not certified yet."}]})
	var item: TreeItem = dock._checks.get_root().get_child(0)
	_check(item.get_tooltip_text(0) == "warning", "the readiness has its whole word as a tooltip")
	_check(item.get_tooltip_text(1).begins_with("Lot (sites and streets)") and item.get_tooltip_text(1).contains("0.126.0"),
		"the check's tooltip is its whole name and the technical detail")
	_check(item.get_tooltip_text(2).ends_with("not certified yet."), "and what to do is whole in its tooltip")
	dock.queue_free()
	print("DONE failures=%d" % _failures)
	quit(1 if _failures else 0)
