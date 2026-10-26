extends SceneTree
## The Level tab's layouts, headless: the list shows each layout's state and why; when every layout failed the
## recommendation says it is not one and nothing is pre-selected; otherwise the recommended layout is selected and
## Use this layout is offered; and Stop writes the run's cancel file.
##
##     godot --headless --path <this project> --script res://tests/test_level_layouts.gd
##
## Prints PASS or FAIL lines; quits 0 only when every case passed. The generation itself is proven against the real
## pipeline by the factory's `patches/lf_layouts/` records, not here: it takes minutes.

const LevelPanel := preload("res://addons/gabagool_factory/level_panel.gd")
const FactoryDock := preload("res://addons/gabagool_factory/factory_dock.gd")

var _failures := 0


func _initialize() -> void:
	_run.call_deferred()


func _check(ok: bool, what: String) -> void:
	print(("PASS " if ok else "FAIL ") + what)
	if not ok:
		_failures += 1


func _rows(panel: Node) -> Array:
	var root_item: TreeItem = panel._layouts.get_root()
	return root_item.get_children() if root_item != null else []


func _run() -> void:
	var panel: Control = LevelPanel.new()
	root.add_child(panel)
	await process_frame

	panel.show_layouts({"candidates": [
		{"candidate_id": "m.candidate.seed_1", "seed": 1, "state": "failed", "out_for": ["walktest not ok"]},
		{"candidate_id": "m.candidate.seed_2", "seed": 2, "state": "failed", "out_for": ["no walktest"]}],
		"recommended": "m.candidate.seed_1", "every_out": true,
		"recommendation": "Every layout failed a check; the one listed first failed least. It is not a recommendation."})
	var rows: Array = _rows(panel)
	_check(rows.size() == 2, "both layouts are listed")
	_check(rows[0].get_text(1) == "failed" and rows[0].get_text(2).begins_with("fails: walktest not ok"),
		"a failed layout says why: %s" % rows[0].get_text(2))
	_check(panel._layouts.get_selected() == null, "when every layout failed, none is pre-selected")
	_check(panel._recommendation.text.contains("not a recommendation"), "and the panel says it is not a recommendation")

	panel.show_layouts({"candidates": [
		{"candidate_id": "m.candidate.seed_1", "seed": 1, "state": "needs attention", "out_for": [], "major_findings": 2},
		{"candidate_id": "m.candidate.seed_2", "seed": 2, "state": "valid", "out_for": [], "major_findings": 0}],
		"recommended": "m.candidate.seed_2", "every_out": false, "recommendation": "Ranked by fewest major findings."})
	rows = _rows(panel)
	var selected: TreeItem = panel._layouts.get_selected()
	_check(selected != null and selected.get_metadata(0) == "m.candidate.seed_2", "the recommended layout is selected")
	_check(rows[0].get_text(2) == "2 major finding(s)", "a layout needing attention counts its findings")
	_check(not panel._use.disabled, "Use this layout is offered")

	# Stop: start a real, quick operation and ask it to stop at once
	panel.client.factory_root = FactoryDock.find_factory_root(ProjectSettings.globalize_path("res://"))
	var why: String = panel.client.start("discover_installation", {})
	_check(why == "", "an operation starts: %s" % why)
	_check(panel.client.cancel(), "Stop asks it to stop")
	_check(FileAccess.file_exists(panel.client.run_dir.path_join("cancel")), "by writing the run's cancel file")
	await panel.client.finished
	_check(not panel.client.cancel(), "and there is nothing to stop once it has finished")

	panel.queue_free()
	print("DONE failures=%d" % _failures)
	quit(1 if _failures else 0)
