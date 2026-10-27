extends SceneTree
## AN ENTERABLE BUILDING'S STATIC MODULES, MERGED PER ROOM CELL AND MATERIAL (0.223.0, the factory's roadmap 266).
##
##     godot --headless --path <package> --script res://merge_buildings.gd \
##         -- <report_fs_path> <res://lot/<id>/site.tscn> [...]
##
## Run by `packages/exporting/merge_buildings.py` during the export, after the Empties' merge and before the light
## bake; the Python half writes `rooms.json` beside each scene first and verifies the report this writes, never the
## exit code.
##
## A building's scene (Deli Counter's composer, `themed_tscn`): a root, its `GreyboxBase`, one child per slot
## instancing a kit module GLB, `Dressing` (the covers). Each slot child is either LEFT AS IT IS --
##   * `interactive`: it carries `interactive_id` meta -- a door, a breachable wall, a hatch: its states swap;
##   * moving: a subtree holding an AnimationPlayer or any node with a script;
##   * a light fixture: a module wearing a lens or a diffuser (`FIXTURE_SUFFIXES`) -- its housing hangs at its lamp;
##   * shader-driven: a module with any ShaderMaterial surface -- a screen that runs reads its schedule from UV2
##     (`zoo_keeper/recipes/_card_atlas.build_shutters`), and the merge's lightmap unwrap would overwrite it;
##   * holding what the merge cannot carry (0.227.0, `_cannot_carry`): outside a StaticBody3D, a node that is neither
##     a MeshInstance3D nor a bare Node3D, or any node in a group of its own or with metadata -- Deli Counter's
##     `Ladders`, the climb volumes the walk's player and bot use, and its `Markers`, the spawns, objectives and cover
##     a game finds by group; the report names each slot it kept so (`kept_carrying`);
##   * the `GreyboxBase`, whose slabs are tiled to the light budget on purpose (Deli Counter, roadmap 54), and the
##     `Dressing`, merged per side already (roadmap 180) --
## or TAKEN APART: its StaticBody3D colliders copied out whole under `KitCollision`, in the root's frame, and every
## surface of its other MeshInstance3D nodes appended to the group keyed by (unit, material name, uv1 scale and
## triplanar flags, surface format), the key `merge_empties.gd` uses. The UNIT:
##   * `ext_<storey>_<side>_*` -- one side of one storey; `parapet_<side>_*` -- one side of the parapet; `roof*`;
##   * `int_<storey>_<k>_*` -- one partition run;
##   * a room's own floor and ceiling, `floor_<room>` and `ceiling_<room>` -- that room, by its name;
##   * anything else: the room it stands in -- Deli Counter's rooms, `rooms.json` beside the scene, in its plan frame
##     (a local Godot point (x, y, z) is (x, -z) on the plan) with each room's floor height; the room whose plan holds
##     the piece (or comes within `ROOM_SLACK_M`) and whose floor is the highest at or under its origin;
## and every room unit is CUT INTO `CELL_M` CELLS of the plan (failing a room, a cell alone).
## A LIT FACE THAT IS NOT A FIXTURE'S (a screen, a sign: `M_*_Face`) STAYS ITS OWN INSTANCE'S (0.224.0): every lit
## surface of one MeshInstance3D goes into one mesh of its own, `LitR_<n>`, where that instance stood, and the rest
## of its module merges. Lux finds lit faces by material and by place -- its binder for the power cut, its failing
## fixture the lit face NEAREST ITS LAMP (`LuxFailing.find_lens`, by AABB) -- so each stays a mesh where it was.
## 0.223.0 left every module with a lit face whole; a fixture still is.
## AN OPENING'S SURROUND MERGES WITH ITS WALL, AND ITS GLASS STAYS ITS OWN INSTANCE'S (0.258.0). Until 0.258.0 every
## `*_open<n>` slot was left whole because "a window's pane may be glass, which Godot sorts per mesh" -- so every
## doorway, window and breach panel kept its own mesh and its own lightmap chart beside a merged wall, and the walker,
## on seed 9205's first windowed walk, saw it as seams: "lot of seams visible on these doors", "highly visible seams
## and pieces here", "not consistent: textures" (the factory's `docs/findings/walk_2026-10-26_panel/`, L5-L7). The
## reason was a pane's, not a surround's: now a TRANSPARENT surface (`_glass`) goes into one mesh of its own,
## `GlassR_<n>`, where its instance stood -- sorted as it always was -- and the rest of the slot merges with its unit.
## A slot carrying `interactive_id` -- a door that opens, a breachable panel, a window that breaks -- still stays whole.
## Each group becomes one ArrayMesh wearing a duplicate of its first material, unwrapped for its lightmap at
## `TEXEL_M`, saved as `res://lot/<id>/merged/r<n>.res` under one MeshInstance3D `MergedR_<n>`; the slot children go
## and the scene is saved back over itself.
##
## WHY CELLS, measured before it shipped (the factory's `docs/findings/interior_merge_266/`, cold run 9347's package,
## both arms re-baked and priced, the control twice): a merged mesh is ONE object to Godot's per-object light limit
## (`max_lights_per_object`, 8 on GL Compatibility). One unit a storey paired up to 14 lights, and the meshes over the
## cap went 9 -> 19; whole rooms, 9 -> 11 (one 15 x 20 m room's shelving, 14); 6 m cells of the plan, 9 -> 9, the
## control's own nine. They cost a lightmap of 2048 x 1024 where the control's was 1024 x 1024 and bought 11 % of the
## draws: -79.6 a heading, -420 at the most, the level's worst heading 10.05 -> 9.14 ms p95.

const SCHEMA := "lf.merge_buildings.v1"
## Godot's import default for `meshes/lightmap_texel_size`, as `merge_empties.gd` has it.
const TEXEL_M := 0.2
const LIT_SUFFIXES: Array[String] = ["_Lens", "_Diffuser", "_Face"]
## A LIGHT FIXTURE'S lit faces: a module wearing one stays whole (0.224.0). Its housing hangs at its own lamp, and
## housings merged into a room cell pair with every lamp round the cell -- measured on cold run 9349's package, two
## cells' housings at 10 lights against Godot's 8 (`max_lights_per_object`), the meshes over the cap 9 -> 11.
const FIXTURE_SUFFIXES: Array[String] = ["_Lens", "_Diffuser"]
## MEASURED, not derived: the cell that kept cold run 9347's light pairing at the control's (the header). Another
## level's fixture spacing could want another; the report's lights-per-object census is where that shows.
const CELL_M := 6.0
## How far outside a room's plan a piece may stand and still be that room's -- a counter against its wall.
const ROOM_SLACK_M := 1.5
## Float allowed between a piece's origin and the floor it stands on. Small on purpose: a storey's ceiling hangs a
## slab's half-thickness under the next floor, and must not be read as standing on it.
const FLOOR_SLACK_M := 0.05

var _report: Dictionary = {"schema": SCHEMA, "ok": false, "error": null, "scenes": []}
var _report_path: String = ""


func _initialize() -> void:
	_run()


func _write() -> void:
	var f := FileAccess.open(_report_path, FileAccess.WRITE)
	if f != null:
		f.store_string(JSON.stringify(_report, "  "))
		f.close()


## The shipped probes' exit (the factory's docs/COMMANDS.md): quit, two frames, then the kill a modal cannot stop.
func _exit(code: int) -> void:
	quit(code)
	await process_frame
	await process_frame
	OS.kill(OS.get_process_id())


func _walk(n: Node, out: Array) -> void:
	out.append(n)
	for c in n.get_children():
		_walk(c, out)


func _lit(mat: Material) -> bool:
	if mat == null:
		return false
	var nm: String = mat.resource_name
	if not nm.begins_with("M_"):
		return false
	for s in LIT_SUFFIXES:
		if nm.ends_with(s):
			return true
	return false


## A surface Godot draws transparent: sorted per mesh, so it keeps its own (0.258.0).
func _glass(mat: Material) -> bool:
	var bm: BaseMaterial3D = mat as BaseMaterial3D
	return bm != null and bm.transparency != BaseMaterial3D.TRANSPARENCY_DISABLED


func _cell(px: float, py: float) -> String:
	return "%d %d" % [int(floor(px / CELL_M)), int(floor(py / CELL_M))]


func _room_unit(origin: Vector3, rooms: Array) -> String:
	var px: float = origin.x
	var py: float = -origin.z
	var best := ""
	var best_floor := -INF
	var best_d := INF
	for r in rooms:
		var b: Array = r.get("bounds", [])
		if b.size() != 4:
			continue
		var fl: float = float(r.get("floor", 0.0))
		if fl > origin.y + FLOOR_SLACK_M:
			continue
		var dx: float = maxf(maxf(float(b[0]) - px, px - float(b[2])), 0.0)
		var dy: float = maxf(maxf(float(b[1]) - py, py - float(b[3])), 0.0)
		var d: float = sqrt(dx * dx + dy * dy)
		if d > ROOM_SLACK_M:
			continue
		# the highest floor at or under the piece, then the nearest plan
		if fl > best_floor + 0.01 or (absf(fl - best_floor) <= 0.01 and d < best_d):
			best_floor = fl
			best_d = d
			best = String(r.get("id", ""))
	if best != "":
		return "room %s %s" % [best, _cell(px, py)]
	return "cell %d %s" % [int(floor(origin.y)), _cell(px, py)]


func _unit(name: String, origin: Vector3, rooms: Array) -> String:
	var parts: PackedStringArray = name.split("_")
	for pre in ["floor_", "ceiling_"]:
		if name.begins_with(pre):
			var rid: String = name.substr(pre.length())
			for r in rooms:
				if String(r.get("id", "")) == rid:
					return "room %s %s" % [rid, _cell(origin.x, -origin.z)]
	if name.begins_with("ext_") and parts.size() > 2:
		return "ext %s %s" % [parts[1], parts[2]]
	if name.begins_with("int_") and parts.size() > 2:
		return "int %s %s" % [parts[1], parts[2]]
	if name.begins_with("parapet_") and parts.size() > 1:
		return "roof %s" % parts[1]
	if name.begins_with("roof"):
		return "roof"
	return _room_unit(origin, rooms)


func _key(unit: String, mat: Material, fmt: int) -> String:
	var k: String = "%s|%s|%d" % [unit, (mat.resource_name if mat != null else "<none>"), fmt]
	var bm: BaseMaterial3D = mat as BaseMaterial3D
	if bm != null:
		k += "|%s|%s|%s" % [str(bm.uv1_scale), str(bm.uv1_triplanar), str(bm.uv1_world_triplanar)]
	return k


func _mergeable(child: Node, nodes: Array) -> bool:
	var name := String(child.name)
	if name == "GreyboxBase" or name == "Dressing" or name == "KitCollision" or name.begins_with("Merged"):
		return false
	if child.has_meta("interactive_id"):
		return false
	for n in nodes:
		if n is AnimationPlayer or (n as Node).get_script() != null:
			return false
		var mi: MeshInstance3D = n as MeshInstance3D
		if mi != null and mi.mesh != null:
			for s in range(mi.mesh.get_surface_count()):
				var m: Material = mi.get_active_material(s)
				if m is ShaderMaterial or _fixture(m):
					return false
	return true


## WHAT THE MERGE CANNOT CARRY (0.227.0): why node `n` of slot `child` keeps the slot whole, or "". The merge keeps a
## StaticBody3D whole, with everything under it, and a MeshInstance3D's surfaces, and removes the rest with its slot. A
## bare Node3D -- a module's root, Zoo's `ATT_*` sockets -- holds only its transform, which its meshes already carry.
## Anything else, and any node in a group not starting "_" (Godot's own do) or with metadata, would go: 0.223.0 to
## 0.226.2 removed every building's `Ladders` -- Deli Counter's Area3D climb volumes, group `ladder_area3d` -- and its
## `Markers`, the grouped Node3D spawns, objectives and cover a recipient game finds with `get_nodes_in_group` (Deli
## Counter's `portable_building._marker_nodes`). Found by the factory's install test 11's walk, "no ladder_area3d in
## scene". Its `docs/findings/merge_ladders_227/` counted on two levels what else went: bare Node3Ds, and one Lux
## emitter marker -- an indoor payphone's `LuxEmit_payphone_hood`, its payload glTF extras read as metadata, which
## Lux's runtime `LuxFixtureSpawner.spawn` lights a lamp from; that payphone now stays whole, 2 surfaces unmerged.
func _cannot_carry(n: Node, child: Node) -> String:
	var p: Node = n
	while p != null:
		if p is StaticBody3D:
			return ""
		if p == child:
			break
		p = p.get_parent()
	if not (n is MeshInstance3D) and n.get_class() != "Node3D":
		return n.get_class()
	# sorted: Godot does not keep a node's groups in order, and the report is diffed between runs
	var own: Array = []
	for g in n.get_groups():
		if not String(g).begins_with("_"):
			own.append(String(g))
	if not own.is_empty():
		own.sort()
		return "group %s" % own[0]
	var metas: Array = []
	for m in n.get_meta_list():
		metas.append(String(m))
	if not metas.is_empty():
		metas.sort()
		return "metadata %s" % metas[0]
	return ""


## The first node of a slot's subtree the merge cannot carry, "<its path> (<why>)", or "" when it can carry it all.
func _held(child: Node, nodes: Array) -> String:
	for n in nodes:
		var node: Node = n as Node
		var why: String = _cannot_carry(node, child)
		if why != "":
			var at: String = "." if node == child else String(child.get_path_to(node))
			return "%s (%s)" % [at, why]
	return ""


func _fixture(mat: Material) -> bool:
	if mat == null or not mat.resource_name.begins_with("M_"):
		return false
	for s in FIXTURE_SUFFIXES:
		if mat.resource_name.ends_with(s):
			return true
	return false


func _merge_scene(path: String) -> Dictionary:
	var row: Dictionary = {"scene": path, "slots_merged": 0, "meshes_in": 0, "surfaces_in": 0, "merged": 0,
		"unwrapped": 0, "colliders": 0, "units": {}, "lit_surfaces": 0, "lit_meshes": 0, "glass_surfaces": 0,
		"glass_meshes": 0, "kept_carrying": [], "error": null}
	var rooms_path: String = path.get_base_dir() + "/rooms.json"
	if not FileAccess.file_exists(rooms_path):
		row["error"] = "no rooms.json beside the scene"
		return row
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(rooms_path))
	if not (parsed is Dictionary) or not ((parsed as Dictionary).get("rooms") is Array):
		row["error"] = "rooms.json is not {rooms: [...]}"
		return row
	var rooms: Array = (parsed as Dictionary)["rooms"]
	var packed: PackedScene = load(path) as PackedScene
	if packed == null:
		row["error"] = "cannot load"
		return row
	var scene: Node3D = packed.instantiate() as Node3D
	if scene == null:
		row["error"] = "root is not a Node3D"
		return row
	root.add_child(scene)
	# a frame first: before it, a freshly added scene's slots report the identity for their transforms (measured on
	# the census that preceded this, `docs/findings/interior_merge_266/`)
	await process_frame
	var inv: Transform3D = scene.global_transform.affine_inverse()
	var tools: Dictionary = {}
	var mats: Dictionary = {}
	# one entry a lit instance: its lit surfaces, each [SurfaceTool, material], in its own mesh (0.224.0)
	var lit: Array = []
	# ...and a glazed one: its transparent surfaces, the same way (0.258.0)
	var glazed: Array = []
	var collision := Node3D.new()
	collision.name = "KitCollision"
	scene.add_child(collision)
	collision.owner = scene
	var gone: Array = []
	for child in scene.get_children():
		if child == collision:
			continue
		var nodes: Array = []
		_walk(child, nodes)
		if not _mergeable(child, nodes):
			continue
		# before any collider is copied out: a slot kept whole keeps its own (0.227.0)
		var held: String = _held(child, nodes)
		if held != "":
			(row["kept_carrying"] as Array).append("%s: %s" % [String(child.name), held])
			continue
		var origin: Vector3 = (inv * (child as Node3D).global_transform).origin if child is Node3D else Vector3.ZERO
		var unit := _unit(String(child.name), origin, rooms)
		for n in nodes:
			var body: StaticBody3D = n as StaticBody3D
			if body != null:
				var copy: StaticBody3D = body.duplicate() as StaticBody3D
				collision.add_child(copy)
				copy.transform = inv * body.global_transform
				copy.owner = scene
				var kids: Array = []
				_walk(copy, kids)
				for d in kids:
					if d != copy:
						(d as Node).owner = scene
				row["colliders"] = int(row["colliders"]) + 1
				continue
			var mi: MeshInstance3D = n as MeshInstance3D
			if mi == null or mi.mesh == null:
				continue
			var under_body: bool = false
			var p: Node = mi.get_parent()
			while p != null and p != child:
				if p is StaticBody3D:
					under_body = true
				p = p.get_parent()
			if under_body:
				continue
			row["meshes_in"] = int(row["meshes_in"]) + 1
			var xf: Transform3D = inv * mi.global_transform
			var mine: Dictionary = {}
			var panes: Dictionary = {}
			for s in range(mi.mesh.get_surface_count()):
				var mat: Material = mi.get_active_material(s)
				if _lit(mat):
					var lk: String = mat.resource_name
					if not mine.has(lk):
						mine[lk] = [SurfaceTool.new(), mat]
					((mine[lk] as Array)[0] as SurfaceTool).append_from(mi.mesh, s, xf)
					row["lit_surfaces"] = int(row["lit_surfaces"]) + 1
					continue
				if _glass(mat):
					var gk: String = mat.resource_name if mat.resource_name != "" else "<glass %d>" % s
					if not panes.has(gk):
						panes[gk] = [SurfaceTool.new(), mat]
					((panes[gk] as Array)[0] as SurfaceTool).append_from(mi.mesh, s, xf)
					row["glass_surfaces"] = int(row["glass_surfaces"]) + 1
					continue
				var fmt: int = (mi.mesh as ArrayMesh).surface_get_format(s) if mi.mesh is ArrayMesh else 0
				var key: String = _key(unit, mat, fmt)
				if not tools.has(key):
					tools[key] = SurfaceTool.new()
					mats[key] = mat
				(tools[key] as SurfaceTool).append_from(mi.mesh, s, xf)
				row["surfaces_in"] = int(row["surfaces_in"]) + 1
			if not mine.is_empty():
				lit.append(mine)
			if not panes.is_empty():
				glazed.append(panes)
		gone.append(child)
		row["slots_merged"] = int(row["slots_merged"]) + 1
	if tools.is_empty():
		scene.queue_free()
		row["error"] = "nothing to merge"
		return row
	for g in gone:
		scene.remove_child(g)
		(g as Node).queue_free()
	var units: Dictionary = {}
	for key in tools.keys():
		var kind: String = String(key).split("|")[0].split(" ")[0]
		units[kind] = int(units.get(kind, 0)) + 1
	row["units"] = units
	var dir: String = path.get_base_dir() + "/merged"
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(dir))
	var keys: Array = tools.keys()
	keys.sort()
	var k: int = 0
	for key in keys:
		var am: ArrayMesh = (tools[key] as SurfaceTool).commit()
		var src: Material = mats[key]
		if src != null:
			am.surface_set_material(0, src.duplicate(true) as Material)
		if am.lightmap_unwrap(Transform3D.IDENTITY, TEXEL_M) == OK:
			row["unwrapped"] = int(row["unwrapped"]) + 1
		var mesh_path: String = "%s/r%d.res" % [dir, k]
		var err: int = ResourceSaver.save(am, mesh_path)
		if err != OK:
			scene.queue_free()
			row["error"] = "cannot save %s (%d)" % [mesh_path, err]
			return row
		var out := MeshInstance3D.new()
		out.name = "MergedR_%d" % k
		out.mesh = load(mesh_path) as ArrayMesh
		out.gi_mode = GeometryInstance3D.GI_MODE_STATIC
		scene.add_child(out)
		out.owner = scene
		k += 1
	row["merged"] = k
	# THE LIT FACES, one mesh an instance where it stood (0.224.0): a surface a lit material
	var li: int = 0
	for mine in lit:
		var lam := ArrayMesh.new()
		var names: Array = (mine as Dictionary).keys()
		names.sort()
		for lk in names:
			var pair: Array = (mine as Dictionary)[lk]
			(pair[0] as SurfaceTool).commit(lam)
			lam.surface_set_material(lam.get_surface_count() - 1, (pair[1] as Material).duplicate(true) as Material)
		if lam.lightmap_unwrap(Transform3D.IDENTITY, TEXEL_M) == OK:
			row["unwrapped"] = int(row["unwrapped"]) + 1
		var lpath: String = "%s/l%d.res" % [dir, li]
		var lerr: int = ResourceSaver.save(lam, lpath)
		if lerr != OK:
			scene.queue_free()
			row["error"] = "cannot save %s (%d)" % [lpath, lerr]
			return row
		var lout := MeshInstance3D.new()
		lout.name = "LitR_%d" % li
		lout.mesh = load(lpath) as ArrayMesh
		lout.gi_mode = GeometryInstance3D.GI_MODE_STATIC
		scene.add_child(lout)
		lout.owner = scene
		li += 1
	row["lit_meshes"] = li
	# THE PANES, one mesh an instance where it stood (0.258.0), the lit faces' way
	var gi: int = 0
	for panes in glazed:
		var gam := ArrayMesh.new()
		var gnames: Array = (panes as Dictionary).keys()
		gnames.sort()
		for gk in gnames:
			var gpair: Array = (panes as Dictionary)[gk]
			(gpair[0] as SurfaceTool).commit(gam)
			gam.surface_set_material(gam.get_surface_count() - 1, (gpair[1] as Material).duplicate(true) as Material)
		if gam.lightmap_unwrap(Transform3D.IDENTITY, TEXEL_M) == OK:
			row["unwrapped"] = int(row["unwrapped"]) + 1
		var gpath: String = "%s/g%d.res" % [dir, gi]
		var gerr: int = ResourceSaver.save(gam, gpath)
		if gerr != OK:
			scene.queue_free()
			row["error"] = "cannot save %s (%d)" % [gpath, gerr]
			return row
		var gout := MeshInstance3D.new()
		gout.name = "GlassR_%d" % gi
		gout.mesh = load(gpath) as ArrayMesh
		gout.gi_mode = GeometryInstance3D.GI_MODE_STATIC
		scene.add_child(gout)
		gout.owner = scene
		gi += 1
	row["glass_meshes"] = gi
	# the root was instantiated FROM this path; packed with it set, the saved scene would inherit from itself
	scene.scene_file_path = ""
	var repacked := PackedScene.new()
	var perr: int = repacked.pack(scene)
	if perr != OK:
		scene.queue_free()
		row["error"] = "pack failed (%d)" % perr
		return row
	perr = ResourceSaver.save(repacked, path)
	scene.queue_free()
	if perr != OK:
		row["error"] = "save failed (%d)" % perr
	return row


func _run() -> void:
	await process_frame
	var args: PackedStringArray = OS.get_cmdline_user_args()
	if args.size() < 2:
		_report_path = args[0] if args.size() == 1 else "user://merge_buildings.json"
		_report["error"] = "usage: <report path> <scene> [...]"
		_write()
		_exit(2)
		return
	_report_path = args[0]
	for i in range(1, args.size()):
		var row: Dictionary = await _merge_scene(args[i])
		(_report["scenes"] as Array).append(row)
		var said: String = ""
		if row["error"] != null:
			said = String(row["error"])
		else:
			# joined BEFORE the format: `%` binds tighter than `+`
			var fmt: String = ("%d slots, %d meshes, %d surfaces -> %d merged, %d lit surfaces in %d meshes of "
				+ "their own, %d glass surfaces in %d (%d unwrapped), %d colliders kept; %d slots kept whole, "
				+ "holding what it cannot carry")
			said = fmt % [row["slots_merged"], row["meshes_in"], row["surfaces_in"], row["merged"],
				row["lit_surfaces"], row["lit_meshes"], row["glass_surfaces"], row["glass_meshes"],
				row["unwrapped"], row["colliders"], (row["kept_carrying"] as Array).size()]
		print("[merge_buildings] %s: %s" % [args[i], said])
	var bad: Array = (_report["scenes"] as Array).filter(func(r): return r["error"] != null)
	_report["ok"] = bad.is_empty()
	if not bad.is_empty():
		_report["error"] = "%d scene(s) failed" % bad.size()
	_write()
	_exit(0 if bad.is_empty() else 2)
