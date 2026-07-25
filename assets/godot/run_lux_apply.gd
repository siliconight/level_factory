extends SceneTree
## Headless Lux apply driver for Level Factory (TDD 24.7, open decision #10).
##
## Godot only exposes Lux in-engine (LuxRoot + dock); there is no `--lux-apply`
## flag. This driver applies a look preset headlessly and saves the applied
## presentation scene + a quality/validation record. It uses the REAL Lux
## runtime API: LuxRoot auto-loads its preset library from
## res://addons/lux/presets/ on _ready, then apply/blend by preset name.
##
## Usage:
##   godot --headless --path <project> -s res://run_lux_apply.gd -- \
##     --scene res://level.tscn --preset <preset_name> [--out <abs_dir>]
##
## NOTE: preview PNG capture (calm/alarm/extraction) needs a rendering context,
## which --headless does not provide. This driver writes the applied scene +
## JSON headlessly; capturing previews is a windowed/offscreen follow-up.

func _parse_args() -> Dictionary:
	var out := {}
	var argv := OS.get_cmdline_user_args()
	var i := 0
	while i < argv.size():
		var a: String = argv[i]
		if a.begins_with("--"):
			var key := a.substr(2)
			if i + 1 < argv.size() and not argv[i + 1].begins_with("--"):
				out[key] = argv[i + 1]
				i += 1
			else:
				out[key] = true
		i += 1
	return out

func _initialize() -> void:
	var args := _parse_args()
	var scene_path: String = args.get("scene", "")
	var preset_name: String = args.get("preset", "")
	var out_dir: String = args.get("out", "user://lux")

	if scene_path.is_empty():
		push_error("run_lux_apply: --scene res://... is required")
		quit(2)
		return

	var packed: PackedScene = load(scene_path)
	if packed == null:
		push_error("run_lux_apply: could not load scene %s" % scene_path)
		quit(2)
		return
	var scene: Node = packed.instantiate()
	get_root().add_child(scene)

	# Attach LuxRoot; its _ready loads the preset library from the addon.
	# Load the script BY PATH (same pattern as run_fixture_gate.gd): the
	# class_name TYPE resolves only from an editor-generated global class
	# cache, which a fresh checkout staged headlessly does not have -- and a
	# failed construction here aborts _initialize() before quit(), leaving
	# the headless process hung with no output.
	var lux_root_script: GDScript = load("res://addons/lux/runtime/lux_root.gd")
	if lux_root_script == null:
		push_error("run_lux_apply: lux addon script missing at res://addons/lux/runtime/lux_root.gd")
		quit(2)
		return
	var lux: Node = lux_root_script.new()
	lux.name = "LuxRoot"
	scene.add_child(lux)
	lux.owner = scene
	await process_frame  # let _ready populate the preset library

	var applied_ok := true
	var preset_known := true
	if not preset_name.is_empty():
		# The library keys presets by DISPLAY name; a wrong name makes
		# blend_to_preset a silent no-op. Check and report instead.
		var lib: Variant = lux.get("_preset_library")
		if typeof(lib) == TYPE_DICTIONARY:
			preset_known = (lib as Dictionary).has(String(preset_name))
			# Pin the preset resource on the node BEFORE packing: blend_to_preset
			# only mutates runtime state, so a packed scene without active_preset
			# set would reload with no look. With it set, apply_on_ready restores
			# the applied look in any project that carries the lux addon.
			if preset_known:
				lux.set("active_preset", (lib as Dictionary)[String(preset_name)])
		lux.blend_to_preset(StringName(preset_name), 0.0)
	await process_frame

	# Save the applied presentation scene.
	var applied := PackedScene.new()
	if applied.pack(scene) != OK:
		applied_ok = false
	DirAccess.make_dir_recursive_absolute(out_dir)
	ResourceSaver.save(applied, out_dir + "/lux.applied.tscn")

	var quality := {"preset": preset_name, "applied": applied_ok,
		"driver": "run_lux_apply", "note": "previews need a render context"}
	_write_json(out_dir + "/lux.quality.json", quality)
	var issues := []
	if not preset_known:
		issues.append({"code": "LUX_PRESET_UNKNOWN", "severity": "moderate",
			"category": "presentation",
			"message": "preset '%s' is not in the registered library; look not applied" % preset_name})
	_write_json(out_dir + "/lux.validation.json", {"issues": issues})

	print("[lux] applied preset '%s' -> %s" % [preset_name, out_dir])
	quit(0 if applied_ok else 1)

func _write_json(path: String, data: Dictionary) -> void:
	var f := FileAccess.open(path, FileAccess.WRITE)
	if f != null:
		f.store_string(JSON.stringify(data, "  "))
		f.close()
