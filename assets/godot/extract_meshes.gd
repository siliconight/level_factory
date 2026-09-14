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
# `.res` (FLAG_BUNDLE_RESOURCES, so materials ride inside it and the package
# needs nothing else to resolve the path -- textures only because `_prepare`
# turns each into an ImageTexture first; an imported one does not bundle).
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

## A vertex is white when every channel is at least this; the same bound as
## `zoo_worldskin.gd`'s VERTEX_WHITE.
const VERTEX_WHITE: float = 0.99


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
	var vertex_colour := 0
	var embedded: Array = [0]
	var held_by: Dictionary = {}   # imported texture id -> the ImageTexture that ships
	var prepared: Dictionary = {}   # "<material id>:<tinted>" -> the copy that ships
	for mi in instances:
		var m: Mesh = mi.mesh
		if m == null:
			continue
		var xform: Transform3D = _transform_relative_to(mi, root)
		for s in range(m.get_surface_count()):
			var st := SurfaceTool.new()
			st.append_from(m, s, xform)
			var mat: Material = mi.get_active_material(s)
			var arrays: Array = m.surface_get_arrays(s)
			if mat is BaseMaterial3D:
				var tinted: bool = _has_tint(arrays)
				var key: String = "%d:%s" % [mat.get_instance_id(), str(tinted)]
				if not prepared.has(key):
					prepared[key] = _prepare(mat as BaseMaterial3D, tinted, embedded, held_by)
				mat = prepared[key]
				if tinted:
					vertex_colour += 1
			if mat != null:
				st.set_material(mat)
			mesh = st.commit(mesh)
			surfaces += 1
			vertices += arrays[Mesh.ARRAY_VERTEX].size()
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
		"vertex_colour_surfaces": vertex_colour,
		"embedded_textures": int(embedded[0]),
		"vertices": vertices,
		"parts": instances.size(),
		"aabb_size": [aabb.size.x, aabb.size.y, aabb.size.z],
		"aabb_position": [aabb.position.x, aabb.position.y, aabb.position.z],
	}


## Whether a surface's COLOR_0 holds anything but white -- the rule
## `zoo_worldskin.gd`'s `_vertex_colour_albedo` applies to every object GLB.
##
## THE CLUTTER NEVER PASSES THROUGH THAT SCRIPT. This runs in a scratch
## project with no import script, so the extracted surfaces carry Godot's
## glTF import as-is, and that import never sets
## `vertex_color_use_as_albedo`. MEASURED on walk 9052_rain's
## `dressing/*.res`: 4 of 4 surfaces carry a non-white COLOR_0 and 0 draw it,
## litter_scrap's at a median of 0.32 -- a scrap of paper Zoo aged to a third
## of its colour, drawn at full brightness. A dressing mesh is an object laid
## at scattered placements, never one tile of a surface, so the kit's
## exception does not arise and every tinted surface draws its colour. The
## material is copied rather than edited so the import cache is untouched.
func _has_tint(arrays: Array) -> bool:
	if arrays.size() <= Mesh.ARRAY_COLOR or arrays[Mesh.ARRAY_COLOR] == null:
		return false
	var cols: PackedColorArray = arrays[Mesh.ARRAY_COLOR]
	for col in cols:
		if col.r < VERTEX_WHITE or col.g < VERTEX_WHITE or col.b < VERTEX_WHITE:
			return true
	return false


## The material a dressing surface ships with: a copy of the imported one,
## drawing its vertex colour when `tinted`, with every texture held in the
## copy itself.
##
## THE TEXTURES DID NOT RIDE INSIDE THE `.res`. `FLAG_BUNDLE_RESOURCES`
## bundles sub-resources that have no path of their own, and an imported
## texture has one: `res://.godot/imported/<name>.ctex` in the SCRATCH
## project, which is deleted and was never shipped. MEASURED on clutter built
## with a skin library (Zoo --skins, the delco_1997 gravel, vegetation and
## paper packs): pebble.res 11,298 bytes with its 256 px albedo "bundled",
## and loading it in a walk copy prints `Unable to open file:
## res://.godot/imported/..._albedo.png-....ctex` and reads back
## `albedo_texture == null` on 4 of 4 surfaces -- a skinned pebble renders as
## its white factor. An ImageTexture made from the pixels has no path, so the
## bundle carries it. The chain is generated here for the reason
## `zoo_worldskin.gd`'s `_mip_chains` gives: embedded images keep none, and
## a scattered pebble is seen at distance.
func _prepare(src: BaseMaterial3D, tinted: bool, embedded: Array,
		held_by: Dictionary) -> BaseMaterial3D:
	var mat: BaseMaterial3D = src.duplicate() as BaseMaterial3D
	if tinted:
		mat.vertex_color_use_as_albedo = true
	# Every slot, not a chosen few: the importer sets the metallic slot to the
	# same image as roughness, and a slot left out still names the scratch
	# project's cache. One image in two slots is embedded once (`held_by`).
	for slot in range(BaseMaterial3D.TEXTURE_MAX):
		var tex: Texture2D = mat.get_texture(slot)
		if tex == null or tex is ImageTexture:
			continue
		var key: String = "%d:%s" % [tex.get_instance_id(), str(slot == BaseMaterial3D.TEXTURE_NORMAL)]
		if not held_by.has(key):
			held_by[key] = _embed(tex, slot == BaseMaterial3D.TEXTURE_NORMAL)
			embedded[0] = int(embedded[0]) + 1
		mat.set_texture(slot, held_by[key])
	return mat


func _embed(tex: Texture2D, normal_map: bool) -> Texture2D:
	if tex == null or tex is ImageTexture:
		return tex
	var img: Image = tex.get_image()
	if img == null:
		return tex
	img = img.duplicate()
	if img.is_compressed():
		img.decompress()
	if not img.has_mipmaps():
		img.generate_mipmaps(normal_map)
	return ImageTexture.create_from_image(img)


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
