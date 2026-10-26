@tool
extends VBoxContainer
## The Level tab: start a level from a template, open a saved one, and see every control it has -- what each is
## set to and whether it drives generation or only records intent (increment 3 of the no-AI authoring loop;
## roadmap 312 and 313). A level is a design saved by the factory under `<factory>/levels/<name>/design.json`,
## outside this project; the panel never writes it itself.
##
## Every action is a service operation through this panel's own client, one at a time: a request made while one is
## running waits its turn (`_queue`). The last design opened is kept in the editor settings and opened again when
## the panel next starts.

const ServiceClient := preload("res://addons/gabagool_factory/service_client.gd")
const SETTING_LAST := "gabagool_factory/last_design"
const SUPPORT_TEXT := {"supported": "drives generation", "conditional": "drives generation, with a condition",
	"intent": "intent only: saved, not built"}
const SUPPORT_COLOURS := {"supported": Color(0.45, 0.8, 0.45), "conditional": Color(0.95, 0.75, 0.3),
	"intent": Color(0.65, 0.65, 0.7)}

var client: Node
## The design shown, as the factory last returned it ({} before one is opened).
var design: Dictionary = {}
var design_path: String = ""
var _templates: OptionButton
var _template_ids: Array = []
var _name: LineEdit
var _designs: OptionButton
var _design_paths: Array = []
var _info: Label
var _form: Tree
var _queue: Array = []
var _pending: Callable


func _ready() -> void:
	name = "Level"
	client = ServiceClient.new()
	add_child(client)
	client.finished.connect(_on_finished)
	_build()


func _build() -> void:
	var new_row := HBoxContainer.new()
	_templates = OptionButton.new()
	new_row.add_child(_templates)
	_name = LineEdit.new()
	_name.placeholder_text = "Level name"
	_name.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	new_row.add_child(_name)
	var create := Button.new()
	create.text = "New level"
	create.pressed.connect(new_level)
	new_row.add_child(create)
	add_child(new_row)

	var open_row := HBoxContainer.new()
	_designs = OptionButton.new()
	_designs.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	open_row.add_child(_designs)
	var open := Button.new()
	open.text = "Open"
	open.pressed.connect(_open_selected)
	open_row.add_child(open)
	add_child(open_row)

	_info = Label.new()
	_info.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	add_child(_info)

	_form = Tree.new()
	_form.columns = 3
	_form.hide_root = true
	_form.column_titles_visible = true
	_form.set_column_title(0, "Control")
	_form.set_column_title(1, "Set to")
	_form.set_column_title(2, "What it does")
	_form.size_flags_vertical = Control.SIZE_EXPAND_FILL
	add_child(_form)


## Point the panel at a factory and load its templates and saved levels.
func set_factory_root(root: String) -> void:
	client.factory_root = root
	if root == "":
		_info.text = "Set up the factory first."
		return
	_call("list_templates", {}, _on_templates)
	_refresh_designs()
	var last := _setting(SETTING_LAST)
	if last != "":
		open_design(last)


func _refresh_designs() -> void:
	_call("list_designs", {}, _on_designs)


## Start a level from the chosen template, named from the name field (the template's name when blank).
func new_level() -> void:
	if _template_ids.is_empty():
		_info.text = "No templates yet: the factory has not answered."
		return
	var template: String = _template_ids[_templates.selected]
	var level_name := _name.text.strip_edges()
	if level_name == "":
		level_name = _templates.get_item_text(_templates.selected)
	_info.text = "Creating %s..." % level_name
	_call("create_design", {"template": template, "name": level_name}, _on_design)


## Open the design at `path` (its folder or its design.json).
func open_design(path: String) -> void:
	_info.text = "Opening %s..." % path
	_call("open_design", {"path": path}, _on_design)


func _open_selected() -> void:
	if _design_paths.is_empty():
		_info.text = "No saved levels yet: start one with New level."
		return
	open_design(_design_paths[_designs.selected])


func _call(operation: String, arguments: Dictionary, done: Callable) -> void:
	_queue.append([operation, arguments, done])
	_next()


func _next() -> void:
	if client.is_running() or _queue.is_empty():
		return
	var item: Array = _queue.pop_front()
	_pending = item[2]
	var why: String = client.start(item[0], item[1])
	if why != "":
		_info.text = "Could not start: %s" % why
		_pending = Callable()
		_next()


func _on_finished(result: Dictionary) -> void:
	var done := _pending
	_pending = Callable()
	if result.get("status", "") != "ok":
		var err: Dictionary = result.get("error", {}) if result.get("error") is Dictionary else {}
		_info.text = "The factory could not do that: %s" % err.get("message", "unknown error")
	elif done.is_valid():
		done.call(result.get("data", {}))
	_next()


func _on_templates(data: Dictionary) -> void:
	_templates.clear()
	_template_ids.clear()
	for t in data.get("templates", []):
		var row: Dictionary = t
		_templates.add_item(row.get("label", row.get("template_id", "")))
		_template_ids.append(row.get("template_id", ""))


func _on_designs(data: Dictionary) -> void:
	_designs.clear()
	_design_paths.clear()
	for d in data.get("designs", []):
		var row: Dictionary = d
		var label := "%s (revision %s)" % [row.get("name", "?"), str(row.get("revision", "?"))]
		if row.get("problem") != null:
			label += " -- cannot be used: %s" % row.get("problem")
		_designs.add_item(label)
		_design_paths.append(row.get("path", ""))


func _on_design(data: Dictionary) -> void:
	design = data.get("design", {})
	design_path = data.get("path", "")
	_set_setting(SETTING_LAST, design_path)
	var problems: Array = data.get("problems", [])
	var unknown: Array = data.get("unknown_fields", [])
	var text := "%s -- revision %s, from %s. Saved at %s." % [design.get("name", "?"), str(design.get("revision", "?")),
		design.get("template", "?"), design_path]
	if not problems.is_empty():
		text += "\nCannot be built: %s" % "; ".join(problems)
	if not unknown.is_empty():
		text += "\nFields this factory does not know (kept as they are): %s" % ", ".join(unknown)
	_info.text = text
	_refresh_designs()
	_call("describe_template", {"template": design.get("template", "")}, _on_controls)


func _on_controls(data: Dictionary) -> void:
	_form.clear()
	var root := _form.create_item()
	var choices: Dictionary = design.get("choices", {})
	var intent: Dictionary = design.get("intent", {})
	for c in data.get("controls", []):
		var control: Dictionary = c
		var key: String = control.get("key", "")
		var item := _form.create_item(root)
		item.set_text(0, control.get("label", key))
		var value: Variant = design.get("name", "") if key == "name" else choices.get(key, intent.get(key, ""))
		item.set_text(1, _shown(control, value))
		var support: String = control.get("support", "")
		var what: String = SUPPORT_TEXT.get(support, support)
		item.set_text(2, what)
		item.set_custom_color(2, SUPPORT_COLOURS.get(support, Color.WHITE))
		var tip: String = str(control.get("note", control.get("consumer", "")))
		item.set_tooltip_text(2, tip)


## A control's value as the form shows it: an option's label, yes/no, a list joined.
static func _shown(control: Dictionary, value: Variant) -> String:
	if value is Array:
		return ", ".join(value)
	if value is bool:
		return "yes" if value else "no"
	for o in control.get("options", []):
		var option: Dictionary = o
		if option.get("value") == value:
			return str(option.get("label", value))
	return str(value)


func _setting(key: String) -> String:
	if not Engine.is_editor_hint():
		return ""
	var es := EditorInterface.get_editor_settings()
	return str(es.get_setting(key)) if es.has_setting(key) else ""


func _set_setting(key: String, value: String) -> void:
	if Engine.is_editor_hint():
		EditorInterface.get_editor_settings().set_setting(key, value)
