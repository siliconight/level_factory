@tool
extends VBoxContainer
## The Gabagool Factory panel (`docs/AUTHORING_LOOP.md` at the factory root). The Setup tab finds the factory, checks
## whether Blender, Godot and the tools are ready, and records the executables the user picks (roadmap 311); the
## Level tab starts and opens levels (`level_panel.gd`, roadmap 312 and 313). Every action is a service operation
## (`service_client.gd`), never a terminal.
##
## The factory folder is found by walking up from this project for `factory.manifest.json`; Browse overrides it and
## the choice is kept in the editor settings, which belong to this machine rather than to the project.

const SETTING_ROOT := "gabagool_factory/factory_root"
const ServiceClient := preload("res://addons/gabagool_factory/service_client.gd")
const LevelPanel := preload("res://addons/gabagool_factory/level_panel.gd")
## How far above the project the factory is looked for.
const FIND_DEPTH := 8
const COLOURS := {"ready": Color(0.45, 0.8, 0.45), "warning": Color(0.95, 0.75, 0.3),
	"missing": Color(0.95, 0.45, 0.35), "problem": Color(0.95, 0.35, 0.35)}

var client: Node
## The Level tab; it has its own client, so a level's work and a setup check do not queue behind each other.
var level_panel: Control
var _tabs: TabContainer
var _setup: VBoxContainer
var _root_edit: LineEdit
var _status: Label
var _checks: Tree
var _check_button: Button
var _prepare_button: Button
var _downloads: Label
var _dialog: FileDialog
var _picking: String = ""


func _ready() -> void:
	name = "Gabagool Factory"
	custom_minimum_size = Vector2(320, 360)
	client = ServiceClient.new()
	add_child(client)
	client.event_received.connect(_on_event)
	client.finished.connect(_on_finished)
	_build()
	var root := _setting(SETTING_ROOT)
	if root == "":
		root = find_factory_root(ProjectSettings.globalize_path("res://"))
	_set_root(root)


func _build() -> void:
	_tabs = TabContainer.new()
	_tabs.size_flags_vertical = Control.SIZE_EXPAND_FILL
	add_child(_tabs)
	_setup = VBoxContainer.new()
	_setup.name = "Setup"
	_tabs.add_child(_setup)
	level_panel = LevelPanel.new()
	_tabs.add_child(level_panel)

	var title := Label.new()
	title.text = "Set up the factory"
	title.add_theme_font_size_override("font_size", 16)
	_setup.add_child(title)

	var row := HBoxContainer.new()
	var lbl := Label.new()
	lbl.text = "Factory folder"
	row.add_child(lbl)
	_root_edit = LineEdit.new()
	_root_edit.editable = false
	_root_edit.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	row.add_child(_root_edit)
	var browse := Button.new()
	browse.text = "Browse..."
	browse.pressed.connect(_pick.bind("factory"))
	row.add_child(browse)
	_setup.add_child(row)

	var actions := HBoxContainer.new()
	_check_button = Button.new()
	_check_button.text = "Check setup"
	_check_button.pressed.connect(check_setup)
	actions.add_child(_check_button)
	for which in ["blender", "godot"]:
		var b := Button.new()
		b.text = "Find %s..." % which.capitalize()
		b.pressed.connect(_pick.bind(which))
		actions.add_child(b)
	_setup.add_child(actions)

	# shown only when the tools' Python is what blocks (increment 2): it downloads, so it is never pressed for you
	_prepare_button = Button.new()
	_prepare_button.text = "Prepare environment (downloads once)"
	_prepare_button.tooltip_text = "Gives the factory's tools a Python of their own, the same as `factory setup --venv`. " \
		+ "It downloads once; after that the factory works offline."
	_prepare_button.visible = false
	_prepare_button.pressed.connect(prepare_environment)
	_setup.add_child(_prepare_button)
	# what it downloads and under which licences, read before it is pressed (0.255.0)
	_downloads = Label.new()
	_downloads.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_downloads.visible = false
	_setup.add_child(_downloads)

	_status = Label.new()
	_status.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_setup.add_child(_status)

	_checks = Tree.new()
	_checks.columns = 3
	_checks.hide_root = true
	_checks.set_column_title(0, "")
	_checks.set_column_title(1, "Check")
	_checks.set_column_title(2, "What to do")
	_checks.column_titles_visible = true
	_checks.set_column_expand(0, false)
	_checks.set_column_custom_minimum_width(0, 70)
	_checks.size_flags_vertical = Control.SIZE_EXPAND_FILL
	_setup.add_child(_checks)

	_dialog = FileDialog.new()
	_dialog.access = FileDialog.ACCESS_FILESYSTEM
	_dialog.file_selected.connect(_on_picked)
	_dialog.dir_selected.connect(_on_picked)
	_setup.add_child(_dialog)


## The nearest folder at or above `start` holding `factory.manifest.json`, or "".
static func find_factory_root(start: String) -> String:
	var dir := start.simplify_path().trim_suffix("/")
	for i in range(FIND_DEPTH):
		if FileAccess.file_exists(dir.path_join("factory.manifest.json")):
			return dir
		var up := dir.get_base_dir()
		if up == dir or up == "":
			break
		dir = up
	return ""


func _set_root(root: String) -> void:
	client.factory_root = root
	level_panel.set_factory_root(root)
	_root_edit.text = root if root != "" else "(not found -- Browse to the factory folder)"
	_check_button.disabled = root == ""
	if root != "":
		check_setup()


## Ask the factory what this machine has (`discover_installation`).
func check_setup() -> void:
	_run("discover_installation", {}, "Checking Blender, Godot and the factory's tools...")


## Give the tools a Python of their own (`prepare_environment`); downloads once.
func prepare_environment() -> void:
	_run("prepare_environment", {}, "Preparing the tools' Python. This downloads once and can take a few minutes...")


func _run(operation: String, arguments: Dictionary, message: String) -> void:
	var why: String = client.start(operation, arguments)
	if why != "":
		_status.text = "Could not start: %s" % why
		return
	_check_button.disabled = true
	_prepare_button.disabled = true
	_status.text = message


func _on_event(event: Dictionary) -> void:
	var msg: String = event.get("message", "")
	if msg != "":
		_status.text = msg


func _on_finished(result: Dictionary) -> void:
	_check_button.disabled = client.factory_root == ""
	_prepare_button.disabled = false
	if result.get("status", "") != "ok":
		var err: Dictionary = result.get("error", {})
		_status.text = "The factory could not answer: %s" % err.get("message", "unknown error")
		return
	show_installation(result.get("data", {}))


## Fill the checks list from a `discover_installation` answer.
func show_installation(data: Dictionary) -> void:
	_checks.clear()
	var root := _checks.create_item()
	for c in data.get("checks", []):
		var check: Dictionary = c
		var item := _checks.create_item(root)
		var readiness: String = check.get("readiness", "unknown")
		item.set_text(0, readiness)
		item.set_custom_color(0, COLOURS.get(readiness, Color.WHITE))
		item.set_text(1, check.get("label", check.get("name", "")))
		item.set_tooltip_text(1, check.get("technical", ""))
		var fix: Variant = check.get("fix")
		item.set_text(2, fix if fix is String else "")
	var blocking: Array = data.get("blocking", [])
	_prepare_button.visible = blocking.has("tools_python")
	_downloads.text = str(data.get("downloads_said", ""))
	_downloads.visible = _prepare_button.visible and _downloads.text != ""
	if data.get("ready", false):
		_status.text = "Ready: the factory can build levels on this machine."
	else:
		_status.text = "Not ready: %d check(s) need attention. Each says what to do." % blocking.size()


func _pick(which: String) -> void:
	_picking = which
	if which == "factory":
		_dialog.file_mode = FileDialog.FILE_MODE_OPEN_DIR
		_dialog.title = "Choose the factory folder (it holds factory.manifest.json)"
	else:
		_dialog.file_mode = FileDialog.FILE_MODE_OPEN_FILE
		_dialog.title = "Choose %s's executable" % which.capitalize()
	_dialog.popup_centered_ratio(0.6)


func _on_picked(path: String) -> void:
	if _picking == "factory":
		if not FileAccess.file_exists(path.path_join("factory.manifest.json")):
			_status.text = "%s holds no factory.manifest.json; choose the factory's own folder." % path
			return
		_set_setting(SETTING_ROOT, path)
		_set_root(path)
	elif _picking in ["blender", "godot"]:
		_run("configure_installation", {_picking: path}, "Recording %s..." % _picking.capitalize())


func _setting(key: String) -> String:
	if not Engine.is_editor_hint():
		return ""
	var es := EditorInterface.get_editor_settings()
	return str(es.get_setting(key)) if es.has_setting(key) else ""


func _set_setting(key: String, value: String) -> void:
	if Engine.is_editor_hint():
		EditorInterface.get_editor_settings().set_setting(key, value)
