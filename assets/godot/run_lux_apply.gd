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
##     [--lights <abs path to site.site.lights.json>]   (window anchors -> area lights;
##          rooms -> ambient probes, Lux 0.38.0; club anchors -> the club set, 0.37.0)
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

	# Light the windows (roadmap 96). Deli Counter derives one `window`
	# anchor per opening, Lot merges them into `site.site.lights.json`, and
	# until Lux 0.30.0 / this driver nothing in a built level ever made one
	# a light: the spawner above skips daylight by design (no hardware, no
	# marker) and the manifest path's only caller was the dock button.
	# Measured on cold run 9005's site before this: 18 window anchors of 35,
	# 0 lights. Same ownership rule as the fixtures -- re-own or pack() drops
	# them silently.
	var lights_path: String = String(args.get("lights", ""))
	var daylight_count := 0
	var daylight_in_manifest := 0
	var daylight_msg := "no --lights given"
	var daylight_ok := true
	if not lights_path.is_empty():
		var loader_script: GDScript = load("res://addons/lux/runtime/lux_light_loader.gd")
		if loader_script != null and loader_script.has_method("bake_daylight"):
			var dres: Dictionary = loader_script.bake_daylight(lights_path, scene)
			daylight_ok = bool(dres.get("ok", false))
			daylight_count = int(dres.get("count", 0))
			daylight_in_manifest = int(dres.get("in_manifest", 0))
			daylight_msg = String(dres.get("msg", ""))
			var dcontainer: Node = scene.get_node_or_null(NodePath("LuxDaylight"))
			if dcontainer != null:
				_own_recursive(dcontainer, scene)
		else:
			daylight_ok = false
			daylight_msg = "lux addon has no bake_daylight (Lux < 0.30.0)"
		print("[lux] %s" % daylight_msg)
		await process_frame

	# Darken the rooms (Lux 0.38.0). Interiors read dark by default, lit by
	# their own fixtures: one interior ReflectionProbe per room the manifest
	# names, sized by the `room_box_local` Deli Counter writes on the room's
	# ceiling anchors, replaces the sky's ambient inside it. A manifest that
	# names rooms and boxes none of them (Deli Counter before the field) bakes
	# nothing and says so: `room_probe_rooms` against `room_probes` is the
	# number a run reads that on. Same ownership rule as the rigs above.
	var room_probes := 0
	var room_rooms := 0
	var room_without: Array = []
	var room_msg := "no --lights given"
	var room_ok := true
	if not lights_path.is_empty():
		var room_loader: GDScript = load("res://addons/lux/runtime/lux_light_loader.gd")
		if room_loader != null and room_loader.has_method("bake_room_ambient"):
			var rres: Dictionary = room_loader.bake_room_ambient(lights_path, scene)
			room_ok = bool(rres.get("ok", false))
			room_probes = int(rres.get("count", 0))
			room_rooms = int(rres.get("rooms", 0))
			room_without = rres.get("without_box", [])
			room_msg = String(rres.get("msg", ""))
			var rocontainer: Node = scene.get_node_or_null(NodePath("LuxRoomAmbient"))
			if rocontainer != null:
				_own_recursive(rocontainer, scene)
		else:
			room_ok = false
			room_msg = "lux addon has no bake_room_ambient (Lux < 0.38.0)"
		print("[lux] %s" % room_msg)
		await process_frame

	# Light the club (Lux 0.37.0), only when the manifest carries one. The
	# club types -- club_wash, stage_light, neon, room_ambient -- have no
	# hardware and no marker, so like the windows they reach a level only
	# through the manifest. The list of types is READ OFF THE LOADER, not
	# spelled here: a fifth type Lux adds is baked and counted the day it
	# lands. `refused` names the anchors the loader would not build (an
	# unknown colour, a stage light with no target); a refusal is a finding,
	# a manifest with no club anchors is not.
	var club_lights := 0
	var club_in_manifest := 0
	var club_refused: Array = []
	var club_msg := "no --lights given"
	var club_ok := true
	if not lights_path.is_empty():
		var club_loader: GDScript = load("res://addons/lux/runtime/lux_light_loader.gd")
		var club_types: Variant = club_loader.get("CLUB_TYPES") if club_loader != null else null
		if typeof(club_types) == TYPE_ARRAY:
			club_in_manifest = _count_anchor_types(lights_path, club_types)
		if club_in_manifest == 0:
			club_msg = "manifest carries no club anchors"
		elif club_loader != null and club_loader.has_method("bake_club"):
			var cres: Dictionary = club_loader.bake_club(lights_path, scene)
			club_ok = bool(cres.get("ok", false))
			club_refused = cres.get("refused", [])
			club_msg = String(cres.get("msg", ""))
			var ccontainer: Node = scene.get_node_or_null(NodePath("LuxClub"))
			if ccontainer != null:
				_own_recursive(ccontainer, scene)
				club_lights = _count_lights(ccontainer)
		else:
			club_ok = false
			club_msg = "lux addon has no bake_club (Lux < 0.37.0)"
		print("[lux] club: %s" % club_msg)
		await process_frame

	# THE CENSUS THE LIGHT BUDGET IS WRITTEN FROM. `count_package_lights`
	# counts `type="OmniLight3D"` declarations in scene text, and roadmap 56
	# measured the running tree at 272 against a written 136: an instanced
	# rig counts once, a lamp a rig builds in _ready counts zero. This is the
	# tree as it stands after every bake above, before pack -- every
	# Light3D, the sun included, whichever path spawned it, a `vending` rig
	# the loader learns tomorrow included. `packages.core.godot_project`
	# takes the larger of the two numbers.
	var lights_in_tree := _count_lights(scene)

	# Keep the rain out of the buildings (Lux 0.35.0). The applied preset's
	# weather decides: LuxRoot builds the falling rain from it at load, and
	# particles pass through geometry unless a particle COLLIDER stops them,
	# so without these boxes it rains in every lobby. One box per building
	# from its lowest surface to its roof, plus the ground; the boxes are plain
	# engine nodes, so they are packed here and cost nothing to load.
	#
	# Buildings are matched as `b<index>` because that is the id this
	# pipeline writes into Lot's site spec (`_write_site_spec`), and Lot names
	# each building node after its id. Same ownership rule as the rigs above.
	#
	# Only when rain is asked for: a dry preset builds nothing, so every dry
	# level's applied scene is unchanged by this block. A game that switches
	# a dry level to rain at runtime has no colliders and rains indoors.
	var rain_drops := 0
	var rain_colliders := 0
	var rain_msg := "preset has no rain"
	var rain_ok := true
	var rain_asked := false
	var weather: Object = null
	if lux.has_method("get_current_preset"):
		var cur_p: Object = lux.get_current_preset()
		if cur_p != null:
			weather = cur_p.get("weather")
	if weather != null and bool(weather.get("rain_enabled")):
		rain_asked = true
		if lux.has_method("get_rain_drops"):
			rain_drops = int(lux.get_rain_drops())
		var coll_script: GDScript = load("res://addons/lux/runtime/lux_rain_collision.gd")
		if coll_script != null and coll_script.has_method("build") and scene is Node3D:
			var rres: Dictionary = coll_script.build(scene, weather, "^b\\d+$", 0.0)
			rain_ok = bool(rres.get("ok", false))
			rain_colliders = int(rres.get("boxes", 0))
			rain_msg = String(rres.get("msg", ""))
			var rcontainer: Node = scene.get_node_or_null(NodePath("LuxRainColliders"))
			if rcontainer != null:
				_own_recursive(rcontainer, scene)
		else:
			rain_ok = false
			rain_msg = "lux addon has no LuxRainCollision.build (Lux < 0.35.0)"
		print("[lux] rain: %d drop(s); %s" % [rain_drops, rain_msg])
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
		"fixture_lights": fixture_count, "fixture_msg": fixture_msg,
		"daylight_lights": daylight_count,
		"daylight_anchors_in_manifest": daylight_in_manifest,
		"daylight_msg": daylight_msg,
		"rain_asked": rain_asked, "rain_drops": rain_drops,
		"rain_colliders": rain_colliders, "rain_msg": rain_msg,
		"room_probes": room_probes, "room_probe_rooms": room_rooms,
		"room_probe_rooms_without_box": room_without, "room_probe_msg": room_msg,
		"club_lights": club_lights, "club_anchors_in_manifest": club_in_manifest,
		"club_refused": club_refused, "club_msg": club_msg,
		"lights_in_tree": lights_in_tree}
	_write_json(out_dir + "/lux.quality.json", quality)
	var issues := []
	# The manifest names rooms and none of them got a probe -- Deli Counter
	# wrote no `room_box_local`, or the bake could not run. Moderate: the
	# level ships, and its interiors keep the sky's ambient through the roof,
	# which is the look the walker decided against (Lux 0.38.0).
	if not lights_path.is_empty() and (not room_ok or (room_rooms > 0 and room_probes == 0)):
		issues.append({"code": "LUX_NO_ROOM_PROBES", "severity": "moderate",
			"category": "presentation",
			"message": "rooms did not get an ambient probe: %s" % room_msg})
	# A club anchor the loader refused is a typo in a colour or a stage light
	# with no target; the manifest asked for a light that was not built.
	if not lights_path.is_empty() and club_in_manifest > 0 and (not club_ok or not club_refused.is_empty()):
		issues.append({"code": "LUX_CLUB_REFUSED", "severity": "moderate",
			"category": "presentation",
			"message": "club anchors did not all become light: %s" % club_msg})
	# The manifest asked for daylight and none was made -- or could not be
	# read at all. Moderate: the level ships, darker than it was specified.
	if not lights_path.is_empty() and (not daylight_ok or (daylight_in_manifest > 0 and daylight_count == 0)):
		issues.append({"code": "LUX_NO_DAYLIGHT", "severity": "moderate",
			"category": "presentation",
			"message": "window anchors did not become light: %s" % daylight_msg})
	# Rain was asked for and the buildings are not covered, or no rain was
	# built at all. Moderate: the level ships, and it rains indoors or not at
	# all, which a person walking it will see and nothing else will.
	if rain_asked and (not rain_ok or rain_drops == 0):
		issues.append({"code": "LUX_RAIN_NOT_CONTAINED", "severity": "moderate",
			"category": "presentation",
			"message": "preset asks for rain: %d drop(s); %s" % [rain_drops, rain_msg]})
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


## How many anchors of `path` carry one of `types`. Reads the manifest
## itself rather than asking the loader, so "no club anchors" can be told
## apart from "the loader refused every one".
func _count_anchor_types(path: String, types: Array) -> int:
	if not FileAccess.file_exists(path):
		return 0
	var data: Variant = JSON.parse_string(FileAccess.get_file_as_string(path))
	if typeof(data) != TYPE_DICTIONARY or typeof(data.get("anchors")) != TYPE_ARRAY:
		return 0
	var n := 0
	for a in data["anchors"]:
		if typeof(a) == TYPE_DICTIONARY and types.has(String(a.get("type", ""))):
			n += 1
	return n


## Every Light3D under `node`, itself included: the running tree's census.
func _count_lights(node: Node) -> int:
	var n := 1 if node is Light3D else 0
	for c in node.get_children():
		n += _count_lights(c)
	return n
## Give every node under `node` the same owner, so PackedScene.pack keeps them.
## Nodes created at runtime have a null owner and pack() drops those without a
## word; the spawner only sets owners in the editor.
func _own_recursive(node: Node, owner_node: Node) -> void:
	node.owner = owner_node
	for c in node.get_children():
		_own_recursive(c, owner_node)
