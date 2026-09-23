# Probe: does the package's art arrive with textures BOUND, and what do they cost?
#
# Runs as the main loop (`godot --script`), so it extends SceneTree and drives
# itself. It opens a window on purpose: headless draws nothing, so
# RENDERING_INFO_TEXTURE_MEM_USED cannot answer there. It quits itself and
# never stops on a dialog.
#
# It prints what it measured. It names no cause.
#
#     godot --headless --path <pkg> --import          (once)
#     godot --path <pkg> --resolution 1280x720 --script res://texture_binding_probe.gd
#
# RENDERING_INFO_TEXTURE_MEM_USED IS NOT THE LEVEL'S TEXTURES. It counts
# render targets and shadow atlases too, so a package binding twelve 512x512
# images reads 293 MB of it. That part is constant for one scene at one window
# size, so a DIFFERENCE between two builds of the same scene is attributable
# to the images and the absolute figure is not. Compare rows; do not quote one.
#
# Measured 2026-09-22, Godot 4.7, GL Compatibility, 1280x720, on
# `LF_club_block_007.portable-godot`:
#
#     0.104.0's shipped package      12 RIDs     681/4,019 mats   293,271,227
#     0.105.0 externalised          214 RIDs   3,529/4,019 mats   334,970,954
#     the same, re-embedded       2,392 RIDs   3,529/4,019 mats   671,644,529
#
# The first row is the defect: twelve bound textures in a level of 4,019
# materials is what a walker called "around 90% graybox".
#
# Reports, in this order:
#   baseline_texture_mem    an empty tree, before the scene is loaded
#   loaded_texture_mem      after the entry scene has been in the tree N frames
#   distinct_texture_rids   distinct Texture2D RIDs reachable from the scene's
#                           materials -- a file present is not a file bound
#   materials               how many surface materials were walked
#   textured_materials      how many of them hold at least one texture
extends SceneTree

const FRAMES := 45

var _frames := 0
var _baseline := 0
var _root_node: Node = null


func _initialize() -> void:
	_baseline = RenderingServer.get_rendering_info(
		RenderingServer.RENDERING_INFO_TEXTURE_MEM_USED)
	var main_path: String = ProjectSettings.get_setting("application/run/main_scene", "")
	if main_path == "":
		print("PROBE_ERROR no application/run/main_scene")
		quit(2)
		return
	var packed: PackedScene = load(main_path)
	if packed == null:
		print("PROBE_ERROR cannot load " + main_path)
		quit(2)
		return
	_root_node = packed.instantiate()
	root.add_child(_root_node)
	print("PROBE_SCENE " + main_path)


func _process(_delta: float) -> bool:
	_frames += 1
	if _frames < FRAMES:
		return false
	_report()
	quit(0)
	return true


func _collect(node: Node, mats: Array, meshes: Array) -> void:
	if node is MeshInstance3D:
		var mi := node as MeshInstance3D
		var mesh: Mesh = mi.mesh
		if mesh != null:
			meshes.append(mesh)
			for i in range(mesh.get_surface_count()):
				var m: Material = mi.get_active_material(i)
				if m != null:
					mats.append(m)
	if node is MultiMeshInstance3D:
		var mm := (node as MultiMeshInstance3D).multimesh
		if mm != null and mm.mesh != null:
			meshes.append(mm.mesh)
			for i in range(mm.mesh.get_surface_count()):
				var m2: Material = mm.mesh.surface_get_material(i)
				if m2 != null:
					mats.append(m2)
	for child in node.get_children():
		_collect(child, mats, meshes)


func _textures_of(m: Material) -> Array:
	var out: Array = []
	if m is BaseMaterial3D:
		var bm := m as BaseMaterial3D
		var slots: Array = [
			BaseMaterial3D.TEXTURE_ALBEDO,
			BaseMaterial3D.TEXTURE_ROUGHNESS,
			BaseMaterial3D.TEXTURE_METALLIC,
			BaseMaterial3D.TEXTURE_NORMAL,
			BaseMaterial3D.TEXTURE_EMISSION,
		]
		for s in slots:
			var t: Texture2D = bm.get_texture(s)
			if t != null:
				out.append(t)
	return out


func _report() -> void:
	var loaded := RenderingServer.get_rendering_info(
		RenderingServer.RENDERING_INFO_TEXTURE_MEM_USED)
	var mats: Array = []
	var meshes: Array = []
	if _root_node != null:
		_collect(_root_node, mats, meshes)
	var rids := {}
	var textured := 0
	for m in mats:
		var ts: Array = _textures_of(m)
		if ts.size() > 0:
			textured += 1
		for t in ts:
			rids[t.get_rid()] = true
	var mesh_ids := {}
	for mesh in meshes:
		mesh_ids[mesh.get_rid()] = true
	print("PROBE_BASELINE_TEXTURE_MEM " + str(_baseline))
	print("PROBE_LOADED_TEXTURE_MEM " + str(loaded))
	print("PROBE_DELTA_TEXTURE_MEM " + str(loaded - _baseline))
	print("PROBE_DISTINCT_TEXTURE_RIDS " + str(rids.size()))
	print("PROBE_MATERIALS " + str(mats.size()))
	print("PROBE_TEXTURED_MATERIALS " + str(textured))
	print("PROBE_DISTINCT_MESHES " + str(mesh_ids.size()))
	print("PROBE_NODES " + str(_count(_root_node)))


func _count(node: Node) -> int:
	if node == null:
		return 0
	var n := 1
	for c in node.get_children():
		n += _count(c)
	return n
