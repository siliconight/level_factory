extends SceneTree
## The Level tab's form, headless: every control's value is editable in the form and read back exactly as the
## factory takes it -- a choice by its value, not its label; a whole number; yes/no; words -- and a changed choice
## reads back changed. After a save, the panel says what comes next from what the change rebuilds.
##
##     godot --headless --path <this project> --script res://tests/test_level_edit.gd
##
## Prints PASS or FAIL lines; quits 0 only when every case passed. Saving against the real factory is proven by the
## factory's `patches/lf_revise/` records.

const LevelPanel := preload("res://addons/gabagool_factory/level_panel.gd")

var _failures := 0
const CONTROLS := [
	{"key": "name", "label": "Level name", "type": "text", "support": "supported"},
	{"key": "time_of_day", "label": "Time of day", "type": "choice", "support": "supported",
		"options": [{"value": "morning", "label": "Morning"}, {"value": "evening", "label": "Evening"},
			{"value": "midnight", "label": "Midnight"}]},
	{"key": "candidate_count", "label": "Layouts to generate", "type": "integer", "min": 1, "max": 8,
		"support": "supported"},
	{"key": "roof_props", "label": "Roof clutter", "type": "boolean", "support": "supported"},
	{"key": "objective_hypotheses", "label": "Objective steps", "type": "list", "support": "intent"},
	{"key": "notes", "label": "Notes", "type": "longtext", "support": "intent"},
]


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
	panel.design = {"name": "Late Shift", "revision": 3, "template": "restaurant_row",
		"choices": {"time_of_day": "evening", "candidate_count": 3, "roof_props": true},
		"intent": {"objective_hypotheses": ["reach_office", "crack_safe"], "notes": "after closing"}}
	panel._on_controls({"controls": CONTROLS})
	var values: Dictionary = panel.form_values()
	_check(values["name"] == "Late Shift", "the name reads back")
	_check(values["choices"] == {"time_of_day": "evening", "candidate_count": 3, "roof_props": true},
		"choices read back by value: %s" % [values["choices"]])
	_check(values["intent"] == {"objective_hypotheses": ["reach_office", "crack_safe"], "notes": "after closing"},
		"intent reads back as the factory takes it: %s" % [values["intent"]])

	var rows: Array = panel._form.get_root().get_children()
	rows[1].set_range(1, 2)            # Time of day -> Midnight
	rows[2].set_range(1, 5)            # five layouts
	rows[3].set_checked(1, false)      # no roof clutter
	values = panel.form_values()
	_check(values["choices"] == {"time_of_day": "midnight", "candidate_count": 5, "roof_props": false},
		"changed values read back changed: %s" % [values["choices"]])

	var saved: Dictionary = panel.design.duplicate(true)
	saved["revision"] = 4
	panel._on_saved({"design": saved, "path": "", "rebuilds": ["lighting"]}, {"revision": 3})
	_check(panel._walk_status.text.contains("Walk the level to see it (rebuilds the lighting)"),
		"a lighting change says to walk: %s" % panel._walk_status.text)
	_check(not panel._undo.disabled, "and Undo is offered")
	saved = saved.duplicate(true)
	saved["revision"] = 5
	panel._on_saved({"design": saved, "path": "", "rebuilds": ["layout"]}, {})
	_check(panel._walk_status.text.contains("generate layouts again"), "a layout change says to generate again")
	_check(panel._undo.disabled, "and an undone save offers no second undo")

	panel.queue_free()
	print("DONE failures=%d" % _failures)
	quit(1 if _failures else 0)
