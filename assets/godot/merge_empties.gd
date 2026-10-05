extends SceneTree
## THE EMPTIES, MERGED ONE MESH A SIDE PER MATERIAL (0.143.0, roadmap 182).
##
##     godot --headless --path <package> --script res://merge_empties.gd \
##         -- <report_fs_path> <res://lot/<id>/site.tscn> [...]
##
## Run by `packages/exporting/merge_empties.py` during the export, after the
## occluder bake and before the light bake; the Python half verifies the
## report this writes, never the exit code.
##
## An Empty's scene (Deli Counter's composer, `themed_tscn`): a root, its
## `GreyboxBase` (the collision base), one child per slot named for the slot
## and instancing a kit module GLB, and `Dressing` (the covers, merged per
## side since roadmap 180). For each scene handed in:
##   * every slot child whose name gives a side -- `ext_<storey>_<N|E|S|W>_*`,
##     `parapet_<N|E|S|W>_*`, `roof_*` (side R) -- is taken apart. Its
##     StaticBody3D colliders are copied out whole under `KitCollision`, in
##     the root's frame. Every surface of its other MeshInstance3D nodes is
##     appended, in the root's frame, to the group keyed by (side, material
##     name, uv1 scale and triplanar flags, surface format): each module GLB
##     imports its own material instances, so the name is the identity and
##     the flags keep visually different ones apart.
##   * each group becomes one ArrayMesh, wearing a DUPLICATE of its first
##     material -- the light bake re-imports the module GLBs, and a merged
##     mesh must not hold their sub-resources -- unwrapped for its lightmap
##     at `TEXEL_M`, and saved as `res://lot/<id>/merged/<side>_<n>.res`;
##   * the slot children are removed and one MeshInstance3D a group added,
##     named `Merged<side>_<n>`; the scene is saved back over itself.
## GreyboxBase and Dressing are left as they are.
##
## The unit is ONE SIDE OF ONE EMPTY: the largest thing that enters and
## leaves view as one. Never across Empties.

const SCHEMA := "lf.merge_empties.v1"
## Godot's import default for `meshes/lightmap_texel_size`, which is what the
## light bake's `mark_imports` gets on every module GLB it unwraps.
const TEXEL_M := 0.2

var _report: Dictionary = {"schema": SCHEMA, "ok": false, "error": null, "scenes": []}
var _report_path: String = ""


func _initialize() -> void:
	_run()


func _write() -> void:
	var f := FileAccess.open(_report_path, FileAccess.WRITE)
	if f != null:
		f.store_string(JSON.stringify(_report, "  "))
		f.close()


func _fail(msg: String) -> void:
	_report["ok"] = false
	_report["error"] = msg
	_write()
	quit(2)


func _side(slot_name: String) -> String:
	var parts: PackedStringArray = slot_name.split("_")
	if slot_name.begins_with("roof"):
		return "R"
	if slot_name.begins_with("parapet_") and parts.size() > 1 and parts[1] in ["N", "E", "S", "W"]:
		return parts[1]
	if slot_name.begins_with("ext_") and parts.size() > 2 and parts[2] in ["N", "E", "S", "W"]:
		return parts[2]
	return ""


func _walk(n: Node, out: Array) -> void:
	out.append(n)
	for c in n.get_children():
		_walk(c, out)


func _key(side: String, mat: Material, fmt: int) -> String:
	var k: String = "%s|%s|%d" % [side, (mat.resource_name if mat != null else "<none>"), fmt]
	var bm: BaseMaterial3D = mat as BaseMaterial3D
	if bm != null:
		k += "|%s|%s|%s" % [str(bm.uv1_scale), str(bm.uv1_triplanar), str(bm.uv1_world_triplanar)]
	return k


func _merge_scene(path: String) -> Dictionary:
	var row: Dictionary = {"scene": path, "meshes_in": 0, "surfaces_in": 0, "merged": 0,
		"unwrapped": 0, "colliders": 0, "doors_dropped": 0, "error": null}
	var packed: PackedScene = load(path) as PackedScene
	if packed == null:
		row["error"] = "cannot load"
		return row
	var scene: Node3D = packed.instantiate() as Node3D
	if scene == null:
		row["error"] = "root is not a Node3D"
		return row
	root.add_child(scene)
	await process_frame
	var inv: Transform3D = scene.global_transform.affine_inverse()
	var tools: Dictionary = {}
	var mats: Dictionary = {}
	var collision := Node3D.new()
	collision.name = "KitCollision"
	scene.add_child(collision)
	collision.owner = scene
	var gone: Array = []
	for child in scene.get_children():
		var side: String = _side(String(child.name))
		if side == "":
			continue
		if (child as Node).has_meta("interactive_id"):
			row["doors_dropped"] = int(row["doors_dropped"]) + 1
		var nodes: Array = []
		_walk(child, nodes)
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
			for s in range(mi.mesh.get_surface_count()):
				var mat: Material = mi.get_active_material(s)
				var fmt: int = (mi.mesh as ArrayMesh).surface_get_format(s) if mi.mesh is ArrayMesh else 0
				var key: String = _key(side, mat, fmt)
				if not tools.has(key):
					tools[key] = SurfaceTool.new()
					mats[key] = mat
				(tools[key] as SurfaceTool).append_from(mi.mesh, s, xf)
				row["surfaces_in"] = int(row["surfaces_in"]) + 1
		gone.append(child)
	if tools.is_empty():
		scene.queue_free()
		row["error"] = "no side to merge"
		return row
	for g in gone:
		scene.remove_child(g)
		(g as Node).queue_free()
	var dir: String = path.get_base_dir() + "/merged"
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(dir))
	var keys: Array = tools.keys()
	keys.sort()
	var k: int = 0
	for key in keys:
		var side_tag: String = String(key).split("|")[0]
		var am: ArrayMesh = (tools[key] as SurfaceTool).commit()
		var src: Material = mats[key]
		if src != null:
			am.surface_set_material(0, src.duplicate(true) as Material)
		if am.lightmap_unwrap(Transform3D.IDENTITY, TEXEL_M) == OK:
			row["unwrapped"] = int(row["unwrapped"]) + 1
		var mesh_path: String = "%s/%s_%d.res" % [dir, side_tag, k]
		var err: int = ResourceSaver.save(am, mesh_path)
		if err != OK:
			scene.queue_free()
			row["error"] = "cannot save %s (%d)" % [mesh_path, err]
			return row
		var out := MeshInstance3D.new()
		out.name = "Merged%s_%d" % [side_tag, k]
		out.mesh = load(mesh_path) as ArrayMesh
		out.gi_mode = GeometryInstance3D.GI_MODE_STATIC
		scene.add_child(out)
		out.owner = scene
		k += 1
	row["merged"] = k
	# the root was instantiated FROM this path; packed with it set, the saved
	# scene would inherit from itself
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
		_report_path = args[0] if args.size() == 1 else "user://merge_empties.json"
		_fail("usage: <report path> <scene> [...]")
		return
	_report_path = args[0]
	for i in range(1, args.size()):
		var row: Dictionary = await _merge_scene(args[i])
		(_report["scenes"] as Array).append(row)
		print("[merge_empties] %s: %s" % [args[i], (row["error"] if row["error"] != null
			else "%d meshes, %d surfaces -> %d merged (%d unwrapped), %d colliders kept"
				% [row["meshes_in"], row["surfaces_in"], row["merged"], row["unwrapped"], row["colliders"]])])
	var bad: Array = (_report["scenes"] as Array).filter(func(r): return r["error"] != null)
	_report["ok"] = bad.is_empty()
	if not bad.is_empty():
		_report["error"] = "%d scene(s) failed" % bad.size()
	_write()
	quit(0 if bad.is_empty() else 2)
