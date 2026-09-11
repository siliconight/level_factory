extends SceneTree

# One Mesh resource per built GLB, so a MultiMesh can draw it.
#
# THE QUESTION THIS ANSWERS ONCE. `packages/exporting/dressing_scene.py`
# refuses to guess how a .glb becomes an addressable Mesh: a .glb imports as
# a PackedScene, a MultiMesh needs a Mesh, and which path names one depends
# on import settings. The A/B project that settled the MultiMesh buffer
# layout sidestepped it with placeholder BoxMeshes and left "the real mesh
# wiring" as a question to answer afterwards, on its own. This is that
# answer: load the imported scene, walk it for every MeshInstance3D, append
# each surface -- in the node's transform relative to the scene root, with
# its material -- onto one ArrayMesh, and save that as a self-contained
# `.res` (FLAG_BUNDLE_RESOURCES, so materials and textures ride inside it
# and the package needs nothing else to resolve the path).
#
# ONE ARRAYMESH PER ASSET, however many parts Zoo built. `rubble_frag`
# measures as two components; a MultiMesh draws one mesh, so the parts are
# merged with their placement baked in. Surfaces are kept separate so each
# keeps its own material.
#
# Driven by `extract.json` in the project root: {"assets": {"<id>":
# "res://<id>.glb"}, "out_dir": "res://dressing"}. Writes
# `extract.report.json` beside it -- what was extracted, how many surfaces
# and vertices, and what failed and why -- so the Python side verifies
# rather than trusts.
#
#   godot --headless --path <project> --import
#   godot --headless --path <project> --script res://extract_meshes.gd


func _initialize() -> void:
	var report := {"extracted": {}, "failed": {}}
	var spec_text := FileAccess.get_file_as_string("res://extract.json")
	if spec_text.is_empty():
		report["failed"]["extract.json"] = "missing or empty"
		_finish(report, 1)
		return
	var spec: Variant = JSON.parse_string(spec_text)
	if typeof(spec) != TYPE_DICTIONARY:
		report["failed"]["extract.json"] = "not a JSON object"
		_finish(report, 1)
		return
	var out_dir := String(spec.get("out_dir", "res://dressing"))
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(out_dir))
	var assets: Dictionary = spec.get("assets", {})
	var rc := 0
	for asset_id in assets:
		var glb_path := String(assets[asset_id])
		var result := _extract_one(String(asset_id), glb_path, out_dir)
		if result.has("error"):
			report["failed"][asset_id] = result["error"]
			rc = 1
		else:
			report["extracted"][asset_id] = result
	_finish(report, rc)


func _extract_one(asset_id: String, glb_path: String, out_dir: String) -> Dictionary:
	var packed: Resource = load(glb_path)
	if packed == null or not (packed is PackedScene):
		return {"error": "could not load %s as a PackedScene (imported?)" % glb_path}
	var root: Node = (packed as PackedScene).instantiate()
	if root == null:
		return {"error": "instantiate() returned null for %s" % glb_path}
	var instances: Array = []
	_collect_mesh_instances(root, instances)
	if instances.is_empty():
		root.free()
		return {"error": "no MeshInstance3D in %s" % glb_path}
	# The instance is never added to a tree, so `global_transform` is not
	# available (it returns identity with an error); the placement is the
	# product of the local transforms up to the scene root, walked here.
	var mesh := ArrayMesh.new()
	var surfaces := 0
	var vertices := 0
	for mi in instances:
		var m: Mesh = mi.mesh
		if m == null:
			continue
		var xform: Transform3D = _transform_relative_to(mi, root)
		for s in range(m.get_surface_count()):
			var st := SurfaceTool.new()
			st.append_from(m, s, xform)
			var mat: Material = mi.get_active_material(s)
			if mat != null:
				st.set_material(mat)
			mesh = st.commit(mesh)
			surfaces += 1
			vertices += m.surface_get_arrays(s)[Mesh.ARRAY_VERTEX].size()
	root.free()
	if surfaces == 0:
		return {"error": "%s carried MeshInstance3D nodes but no surfaces" % glb_path}
	var out_path := "%s/%s.res" % [out_dir, asset_id]
	var err := ResourceSaver.save(mesh, out_path, ResourceSaver.FLAG_BUNDLE_RESOURCES)
	if err != OK:
		return {"error": "ResourceSaver.save(%s) returned %d" % [out_path, err]}
	var aabb := mesh.get_aabb()
	return {
		"path": out_path,
		"surfaces": surfaces,
		"vertices": vertices,
		"parts": instances.size(),
		"aabb_size": [aabb.size.x, aabb.size.y, aabb.size.z],
		"aabb_position": [aabb.position.x, aabb.position.y, aabb.position.z],
	}


func _transform_relative_to(node: Node, root: Node) -> Transform3D:
	var xform := Transform3D.IDENTITY
	var cur: Node = node
	while cur != null and cur != root:
		if cur is Node3D:
			xform = (cur as Node3D).transform * xform
		cur = cur.get_parent()
	return xform


func _collect_mesh_instances(node: Node, out: Array) -> void:
	if node is MeshInstance3D:
		out.append(node)
	for child in node.get_children():
		_collect_mesh_instances(child, out)


func _finish(report: Dictionary, rc: int) -> void:
	var f := FileAccess.open("res://extract.report.json", FileAccess.WRITE)
	if f != null:
		f.store_string(JSON.stringify(report, "  "))
		f.close()
	for asset_id in report["extracted"]:
		var r: Dictionary = report["extracted"][asset_id]
		# `.get` throughout: a script error inside _extract_one leaves an
		# empty dictionary here, and a second error in the reporting would
		# stop this function before quit() -- which is how the first run of
		# this script hung Godot until the caller's timeout.
		print("[extract] %s -> %s (%s surfaces, %s vertices, %s parts)" % [
			asset_id, r.get("path", "?"), str(r.get("surfaces", "?")),
			str(r.get("vertices", "?")), str(r.get("parts", "?"))])
	for asset_id in report["failed"]:
		print("[extract] FAILED %s: %s" % [asset_id, report["failed"][asset_id]])
	quit(rc)
