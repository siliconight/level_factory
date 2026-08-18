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

	# WHAT LUX HAS, NOT WHAT IT WAS ASKED FOR.
	#
	# `_current` is assigned in exactly one place -- `_apply_immediate`,
	# from the library resource -- so this string cannot be the argument
	# arriving back round. The quality record's `preset` field always was
	# that argument, which made comparing it against Level Factory's
	# `_preset_for` a comparison of a string with itself.
	#
	# It also covers what the dictionary check above cannot. `apply_preset`
	# RETURNS EARLY when `_initialized` is false, assigning active_preset
	# and applying nothing. The name is in the library, so the request looks
	# honoured, no issue is raised, and the level ships with no look. The
	# dictionary says the preset exists; only LuxRoot says it arrived.
	#
	# `get`/`has_method` rather than a typed call: `lux` is a Node here and
	# LuxRoot's script is loaded BY PATH, so the class type does not exist
	# to the compiler. This is the same idiom the lines above already use
	# for `_preset_library` and `active_preset`.
	var reported := ""
	if lux.has_method("get_current_preset"):
		var cur: Object = lux.get_current_preset()
		if cur != null:
			reported = String(cur.get("preset_name"))

	# Spawn the fixture lights Zoo already marked.
	#
	# Zoo exports one `LuxEmit_<type>` empty per lamp at the emitter point and
	# Lux ships `LuxFixtureSpawner` to turn those into rigs, and nothing had
	# ever called it -- so every wall pack and fluorescent in a shipped level
	# was an emissive material with no light behind it. Measured on
	# `category5_baie_dore_001` with `tools/light_census.py`, which counts the
	# RUNNING tree rather than the scene file:
	#
	#     DirectionalLight3D 1 (LuxSun)   OmniLight3D 0   SpotLight3D 0
	#
	# One sun four degrees above the horizon was the entire light budget of a
	# night level whose fixtures are supposed to BE the lighting.
	#
	# OWNERSHIP IS LOAD-BEARING HERE. The spawner sets `rig.owner` only under
	# `Engine.is_editor_hint()`, and `PackedScene.pack()` silently drops every
	# node whose owner is null. Spawning without re-owning would write a
	# lux.applied.tscn with no lights in it and report success -- the same
	# shape of silent loss this driver already guards against for the preset.
	var fixture_count := 0
	var fixture_msg := "spawner not found"
	var spawner_script: GDScript = load("res://addons/lux/runtime/lux_fixture_spawner.gd")
	if spawner_script != null:
		var res: Dictionary = spawner_script.spawn(scene)
		fixture_count = int(res.get("count", 0))
		fixture_msg = String(res.get("msg", ""))
		var container: Node = scene.get_node_or_null(NodePath("LuxFixtureLights"))
		if container != null:
			_own_recursive(container, scene)
		print("[lux] %s" % fixture_msg)
	else:
		push_warning("run_lux_apply: %s" % fixture_msg)
	await process_frame

	# Save the applied presentation scene.
	var applied := PackedScene.new()
	if applied.pack(scene) != OK:
		applied_ok = false
	DirAccess.make_dir_recursive_absolute(out_dir)
	# The return was discarded. `applied_ok` tracked only pack(), so a save
	# that failed -- read-only dir, bad path, no space -- reported
	# `applied: true` for a scene that was never written.
	if ResourceSaver.save(applied, out_dir + "/lux.applied.tscn") != OK:
		applied_ok = false

	# `preset` stays the REQUEST, unchanged, because that is what it has
	# always meant and nothing should have to guess which release it is
	# reading. `preset_applied` is the new one and is the one worth
	# comparing against anything.
	var quality := {"preset": preset_name, "preset_applied": reported,
		"applied": applied_ok,
		"driver": "run_lux_apply", "note": "previews need a render context",
		"fixture_lights": fixture_count, "fixture_msg": fixture_msg}
	_write_json(out_dir + "/lux.quality.json", quality)
	var issues := []
	if not preset_known:
		issues.append({"code": "LUX_PRESET_UNKNOWN", "severity": "moderate",
			"category": "presentation",
			"message": "preset '%s' is not in the registered library; look not applied" % preset_name})
	elif not preset_name.is_empty() and reported != String(preset_name):
		# The name resolved and the look still did not land. Moderate, not
		# blocker: a level with the wrong look is shippable and a level that
		# nobody was told about is not.
		issues.append({"code": "LUX_PRESET_NOT_APPLIED", "severity": "moderate",
			"category": "presentation",
			"message": "requested preset '%s' but LuxRoot reports '%s'" % [preset_name, reported]})
	# A night level with zero fixture lights is the defect this stage exists to
	# prevent, and it is invisible in a screenshot because emissive materials
	# still glow. Report the number rather than leaving it to somebody walking
	# the level and wondering why the floor under a lamp is dark.
	if fixture_count == 0:
		issues.append({"code": "LUX_NO_FIXTURE_LIGHTS", "severity": "moderate",
			"category": "presentation",
			"message": "no fixture lights spawned (%s); fixtures will glow but emit nothing" % fixture_msg})
	_write_json(out_dir + "/lux.validation.json", {"issues": issues})

	print("[lux] requested '%s' applied '%s' -> %s" % [preset_name, reported, out_dir])
	quit(0 if applied_ok else 1)

func _write_json(path: String, data: Dictionary) -> void:
	var f := FileAccess.open(path, FileAccess.WRITE)
	if f != null:
		f.store_string(JSON.stringify(data, "  "))
		f.close()
## Give every node under `node` the same owner, so PackedScene.pack keeps them.
## Nodes created at runtime have a null owner and pack() drops those without a
## word; the spawner only sets owners in the editor.
func _own_recursive(node: Node, owner_node: Node) -> void:
	node.owner = owner_node
	for c in node.get_children():
		_own_recursive(c, owner_node)
