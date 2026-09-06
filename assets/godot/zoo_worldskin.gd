@tool
extends EditorScenePostImport
## World-space UVs on kit modules, applied AT IMPORT and baked into the .scn.
##
## WHY THIS IS AN IMPORT SCRIPT. Zoo bakes UVs into the mesh (box projection
## from each module's own centre-pivot local box) and glTF carries UV sets and
## nothing else -- there is no way to express "project from world position" in a
## .glb. So it can only be a material property set after import. The runtime
## version of this (`walk_triplanar.gd`) proved the effect in a scratch project;
## this is the same change made where it PERSISTS.
##
## AND WHY NOT A SCENE PASS. Setting the property on a composed scene means
## either mutating shared material resources (which does not survive being
## saved) or writing `surface_material_override` per MeshInstance3D -- and that
## is a separate material per placement, which is Deli Counter's one-mesh-in-
## VRAM discipline undone at the material layer for the sake of a boolean. At
## import the material is edited once, inside the imported scene, and every
## instance of that GLB shares it. Roadmap 80.
##
## WHAT IT FIXES, both measured before this was written:
##   * every module's texture restarts at its own edges, drawing a hard seam at
##     every 2.00 m boundary the length of a facade (roadmap 76);
##   * a `wallEnd` scaled 0.15 x 3.30 to fill a remainder stretches its texture
##     11:1 or worse, at 46 placements per building (roadmap 88).
## Both are the same defect -- appearance derived from the module rather than
## from the world -- and world projection removes the module from the equation.
##
## SCOPED BY ASSET NAME, because at import time there is no scene to read. The
## runtime script scoped to nodes under Deli Counter's `ext_*` / `int_*` slots;
## those slots instance exactly the five families below. Props and dressing are
## deliberately excluded: world projection on a small movable object is wrong --
## it swims when the object moves -- and the dressing path already varies
## between instances.

const KIT_PREFIXES: Array = ["wall_", "wallEnd_", "window_", "doorway_",
	"breach_"]


func _post_import(scene: Node) -> Object:
	var base: String = get_source_file().get_file()
	var is_kit: bool = false
	for p in KIT_PREFIXES:
		if base.begins_with(p):
			is_kit = true
	if not is_kit:
		print("[worldskin] %s  not a kit module, left alone" % base)
		return scene
	var seen: Dictionary = {}
	var changed: int = 0
	var no_density: int = 0
	var counts: Array = _apply(scene, seen)
	changed = counts[0]
	no_density = counts[1]
	print("[worldskin] %s  %d material(s) world-projected, %d without a UV density"
		% [base, changed, no_density])
	return scene


func _apply(n: Node, seen: Dictionary) -> Array:
	var changed: int = 0
	var no_density: int = 0
	var mi: MeshInstance3D = n as MeshInstance3D
	if mi != null and mi.mesh != null:
		var mesh: Mesh = mi.mesh
		for i in range(mesh.get_surface_count()):
			var mat: Material = mesh.surface_get_material(i)
			if mat == null:
				continue
			var bm: BaseMaterial3D = mat as BaseMaterial3D
			if bm == null:
				continue
			var key: int = bm.get_instance_id()
			if seen.has(key):
				continue
			seen[key] = true
			var density: float = _uv_density(mesh, i)
			if density <= 0.0:
				no_density += 1
				continue
			# The AUTHORED tile period, which is Pixelcoat's
			# `meters_per_tile` arriving as the glTF
			# `KHR_texture_transform` scale. Read it before overwriting it:
			# `uv1_scale` is where the importer put it, and dropping it
			# rendered the whole library at one density. See `_uv_density`.
			var authored: float = bm.uv1_scale.x
			if authored <= 0.0:
				authored = 1.0
			var world: float = density * authored
			bm.uv1_triplanar = true
			bm.uv1_world_triplanar = true
			bm.uv1_scale = Vector3(world, world, world)
			changed += 1
	for c in n.get_children():
		var sub: Array = _apply(c, seen)
		changed += int(sub[0])
		no_density += int(sub[1])
	return [changed, no_density]


## Texels per metre, read off the surface's own vertices and UVs.
##
## THE SCALE IS MEASURED, NOT GUESSED, and the guess was wrong once already.
## The first runtime version multiplied by Zoo's `texel=1.2` assuming the
## material still carried Pixelcoat's tiling as a UV scale, and the stone came
## out twice its proper size. Multiplying by a CONSTANT is what was wrong
## there; the caller now multiplies by the material's own authored
## `uv1_scale`, which is a different operation and not that mistake.
##
## REFUTED 2026-09-06, and the refutation is kept because it is what this
## function's result means. The paragraph above used to continue "because
## Godot's glTF importer bakes `KHR_texture_transform` into the mesh UVs", and
## concluded that re-applying the measured density alone "reproduces the old
## density exactly". BOTH HALVES ARE FALSE. If the transform were baked into
## the mesh UVs, this function would return a DIFFERENT number for skins with
## different tile periods. Measured on `precinct_yard_001`, four skins whose
## transforms are 0.4, 0.6667, 0.3333 and 1.0 -- concrete at 2.5 m, metal at
## 1.5 m, drywall at 3.0 m, glass at 1.0 m -- every one returned 1.2000, which
## is Zoo's texel constant and does not vary with the field. The importer puts
## the transform in the MATERIAL's `uv1_scale`, not in the mesh.
##
## So what this returns is the mesh's own UV density and NOT the on-mesh
## density, which is that times the material's `uv1_scale`. Setting
## `uv1_scale` to this value alone discarded every skin's authored tile period
## and rendered the whole library at one density -- roadmap 104, shipped in
## every world-projected package from level_factory 0.57.0 until it was found.
##
## Median rather than mean: a bevelled box carries degenerate edges, and one of
## those in a mean drags the whole material to the wrong scale.
func _uv_density(mesh: Mesh, surface: int) -> float:
	var arrays: Array = mesh.surface_get_arrays(surface)
	if arrays.size() <= Mesh.ARRAY_TEX_UV:
		return 0.0
	var verts: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
	var uvs: PackedVector2Array = arrays[Mesh.ARRAY_TEX_UV]
	if verts.size() < 2 or uvs.size() != verts.size():
		return 0.0
	var ratios: Array = []
	var limit: int = mini(verts.size() - 1, 400)
	for i in range(limit):
		var dp: float = verts[i].distance_to(verts[i + 1])
		var du: float = uvs[i].distance_to(uvs[i + 1])
		if dp > 0.001 and du > 0.00001:
			ratios.append(du / dp)
	if ratios.is_empty():
		return 0.0
	ratios.sort()
	return float(ratios[ratios.size() / 2])
