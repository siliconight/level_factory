extends SceneTree
## The Level tab's plan, headless: the selected layout's plan is shown from the SVG its row names, with the key; a
## layout with no plan says why, and nothing selected says to select one. The plans themselves are drawn from real
## builds by `generate_layouts`, proven in the factory's `patches/lf_plan/` records.
##
##     godot --headless --path <this project> --script res://tests/test_level_plan.gd

const LevelPanel := preload("res://addons/gabagool_factory/level_panel.gd")

const SVG := "<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"40\" height=\"20\" viewBox=\"0 0 40 20\">" \
	+ "<rect width=\"40\" height=\"20\" fill=\"#c9b48f\"/></svg>"

var _failures := 0


func _initialize() -> void:
	_run.call_deferred()


func _check(ok: bool, what: String) -> void:
	print(("PASS " if ok else "FAIL ") + what)
	if not ok:
		_failures += 1


func _run() -> void:
	var path := OS.get_user_data_dir().path_join("test_level_plan.svg")
	var f := FileAccess.open(path, FileAccess.WRITE)
	f.store_string(SVG)
	f.close()
	var panel: Control = LevelPanel.new()
	root.add_child(panel)
	await process_frame

	panel.show_layouts({"candidates": [
		{"candidate_id": "m.candidate.seed_1", "seed": 1, "state": "valid", "out_for": [], "plan": path},
		{"candidate_id": "m.candidate.seed_2", "seed": 2, "state": "valid", "out_for": [], "plan": null,
			"plan_problem": "the build left no drawn site for this layout"}],
		"recommended": "m.candidate.seed_1", "every_out": false, "recommendation": "Ranked.",
		"plan_key": "Green: crew spawn. The bar is 10 m; north is up."})
	var tex: Texture2D = panel._plan.texture
	_check(tex != null and tex.get_size() == Vector2(40, 20), "the recommended layout's plan is shown at its size")
	_check(panel._plan_note.text.contains("Seed 1") and panel._plan_note.text.contains("10 m"),
		"with the key: %s" % panel._plan_note.text)

	var rows: Array = panel._layouts.get_root().get_children()
	rows[1].select(0)
	await process_frame
	_check(panel._plan.texture == null, "a layout with no plan shows none")
	_check(panel._plan_note.text.contains("no drawn site"), "and says why: %s" % panel._plan_note.text)

	panel.show_layouts({"candidates": [
		{"candidate_id": "m.candidate.seed_1", "seed": 1, "state": "failed", "out_for": ["no walktest"], "plan": path}],
		"recommended": "m.candidate.seed_1", "every_out": true, "recommendation": "not a recommendation"})
	_check(panel._plan.texture == null and panel._plan_note.text.contains("Select a layout"),
		"nothing selected asks for a selection")

	DirAccess.remove_absolute(path)
	panel.queue_free()
	print("DONE failures=%d" % _failures)
	quit(1 if _failures else 0)
