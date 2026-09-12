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

## The greybox base the composer keeps whole (floors, collision, STAIRS).
## Its stairs are Deli Counter's `stair<n>_*` boxes in the flat `gb_stair`
## material -- "the stairs ship in the greybox's fallback yellow", walked on
## cold run 9005 (roadmap 144). Zoo has no stair species and every plate and
## wall around them is skinned, so the base is the one place in a shipped
## level the yellow still shows.
const BASE_PREFIX: String = "site_base"
const STAIR_PREFIX: String = "stair"
## What a stair wears: the building's own concrete pack, found beside the
## base under `art/zoo/` as the albedo Zoo copied next to a concrete kit
## module. The stairs are concrete in every 1990s hospital there is; a stair
## species with its own pack is the later, dearer answer.
const STAIR_KIND: String = "concrete"


func _post_import(scene: Node) -> Object:
	var base: String = get_source_file().get_file()
	var is_kit: bool = false
	for p in KIT_PREFIXES:
		if base.begins_with(p):
			is_kit = true
	if not is_kit:
		if base.begins_with(BASE_PREFIX):
			var n: Array = _skin_stairs(scene, get_source_file().get_base_dir())
			print("[worldskin] %s  %d stair surface(s) skinned on %d mesh(es)%s"
				% [base, int(n[0]), int(n[1]), String(n[2])])
			return scene
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

## Skin the greybox base's stairs with the building's concrete pack, as
## world-projected as the walls beside them (roadmap 144).
##
## The stairs are boxes with NORMAL and POSITION only -- no UVs, so the kit
## pass above has no density to read and would skip them -- in Deli Counter's
## flat `gb_stair`. World triplanar needs no UVs at all: the texture is
## projected from world position, which is the whole reason it is the right
## tool for a surface nobody unwrapped. The tile period comes from the kit
## module the albedo was copied beside, so a stair's texel density equals the
## wall's (measured on the kit at `uv1_scale` 0.5 for a 2.0 m pack); when
## that module cannot be read the period is assumed 2.0 m and the report
## says so. Visual meshes only: `stair<n>col_*` and `*ramp*` are collision.
##
## Returns [surfaces, meshes, note].
func _skin_stairs(scene: Node, base_dir: String) -> Array:
	var art: String = base_dir.path_join("art").path_join("zoo")
	var albedo: String = ""
	var dir := DirAccess.open(art)
	if dir == null:
		return [0, 0, "; no art/zoo beside the base, stairs left alone"]
	var files: PackedStringArray = dir.get_files()
	files.sort()
	# A plain wall's concrete before anything else's: sorted, `breach_*`
	# comes first and its albedo is the BREACHED variant of the pack (the
	# first run of this skinned every stair in rubble-edged concrete).
	var candidates: Array = []
	for f in files:
		if f.ends_with("_albedo.png") and f.contains("_" + STAIR_KIND + "_"):
			candidates.append(f)
	for f in candidates:
		if f.begins_with("wall_") and not f.contains("breached"):
			albedo = f
			break
	if albedo == "":
		for f in candidates:
			if not f.contains("breached"):
				albedo = f
				break
	if albedo == "" and not candidates.is_empty():
		albedo = candidates[0]
	if albedo == "":
		return [0, 0, "; no %s albedo under art/zoo, stairs left alone" % STAIR_KIND]
	var rough: String = albedo.replace("_albedo.png", "_roughness.png")
	var mat := StandardMaterial3D.new()
	mat.resource_name = "M_Skin_%s_stairs" % STAIR_KIND
	mat.albedo_texture = load(art.path_join(albedo))
	if mat.albedo_texture == null:
		return [0, 0, "; %s not loadable yet (import order), stairs left alone" % albedo]
	if files.has(rough):
		mat.roughness_texture = load(art.path_join(rough))
	mat.roughness = 1.0
	mat.uv1_triplanar = true
	mat.uv1_world_triplanar = true
	# the kit module this albedo was copied beside: `<module>_<profile>_albedo`
	var period_note: String = ""
	var scale: float = 0.5
	var stem: String = albedo.get_slice("_" + STAIR_KIND + "_", 0)
	var module: PackedScene = load(art.path_join(stem + ".glb")) as PackedScene
	var got: float = _kit_uv_scale(module)
	if got > 0.0:
		scale = got
	else:
		period_note = "; tile period assumed 2.0 m (kit module %s.glb unreadable)" % stem
	mat.uv1_scale = Vector3(scale, scale, scale)
	var counts: Array = _assign_stairs(scene, mat)
	return [counts[0], counts[1], period_note]


func _kit_uv_scale(module: PackedScene) -> float:
	if module == null:
		return 0.0
	var n: Node = module.instantiate()
	var s: float = _first_uv_scale(n)
	n.free()
	return s


func _first_uv_scale(n: Node) -> float:
	var mi: MeshInstance3D = n as MeshInstance3D
	if mi != null and mi.mesh != null:
		for i in range(mi.mesh.get_surface_count()):
			var bm: BaseMaterial3D = mi.mesh.surface_get_material(i) as BaseMaterial3D
			if bm != null and bm.albedo_texture != null and bm.uv1_scale.x > 0.0:
				return bm.uv1_scale.x
	for c in n.get_children():
		var s: float = _first_uv_scale(c)
		if s > 0.0:
			return s
	return 0.0


func _assign_stairs(n: Node, mat: Material) -> Array:
	var surfaces: int = 0
	var meshes: int = 0
	var mi: MeshInstance3D = n as MeshInstance3D
	if mi != null and mi.mesh != null:
		var nm: String = String(mi.name)
		if nm.begins_with(STAIR_PREFIX) and not nm.contains("col") and not nm.contains("ramp"):
			for i in range(mi.mesh.get_surface_count()):
				mi.mesh.surface_set_material(i, mat)
				surfaces += 1
			meshes += 1
	for c in n.get_children():
		var sub: Array = _assign_stairs(c, mat)
		surfaces += int(sub[0])
		meshes += int(sub[1])
	return [surfaces, meshes]

