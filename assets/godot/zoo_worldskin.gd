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

## Skin the greybox base's stairs with the building's concrete, as
## world-projected as the walls beside them (roadmap 144).
##
## The stairs are boxes with NORMAL and POSITION only -- no UVs, so the kit
## pass above has no density to read and would skip them -- in Deli Counter's
## flat `gb_stair`. World triplanar needs no UVs at all: the texture is
## projected from world position, which is the whole reason it is the right
## tool for a surface nobody unwrapped.
##
## THE MATERIAL COMES FROM A KIT MODULE'S IMPORTED SCENE, NOT FROM A FILE.
## The first version looked for `*_concrete_*_albedo.png` under `art/zoo/`
## and worked on a walk copy that happened to carry loose PNGs; the cold-run
## export (LF 0.71.0, `_write_import_sidecars` mode 3) EMBEDS every texture
## in its GLB and ships no PNG at all, so on a real package that version
## skinned nothing and said so. A `wall_*` module's imported material is
## the concrete the walls wear, textures included, at the tile period the
## kit pass already resolved -- so the stair's texel density equals the
## wall's by construction. Visual meshes only: `stair<n>col_*` and `*ramp*`
## are collision.
##
## Returns [surfaces, meshes, note].
func _skin_stairs(scene: Node, base_dir: String) -> Array:
	var art: String = base_dir.path_join("art").path_join("zoo")
	var dir := DirAccess.open(art)
	if dir == null:
		return [0, 0, "; no art/zoo beside the base, stairs left alone"]
	var files: PackedStringArray = dir.get_files()
	files.sort()
	# A plain wall's module first; `breach_*` sorts earlier and wears the
	# BREACHED variant of the pack (the first run of the file-name version
	# put rubble edges on every stair).
	var modules: Array = []
	for f in files:
		if f.ends_with(".glb") and f.begins_with("wall_"):
			modules.append(f)
	for f in files:
		if f.ends_with(".glb") and not f.begins_with("wall_"):
			for p in KIT_PREFIXES:
				if f.begins_with(p) and not f.begins_with("breach_"):
					modules.append(f)
	var found: Array = []   # [material, module file]
	for f in modules:
		var ps: PackedScene = load(art.path_join(f)) as PackedScene
		if ps == null:
			continue
		var inst: Node = ps.instantiate()
		var m: BaseMaterial3D = _kit_material(inst, STAIR_KIND)
		if m != null:
			found = [m.duplicate(), f]
		inst.free()
		if not found.is_empty():
			break
	if found.is_empty():
		return [0, 0, "; no imported kit module wearing %s under art/zoo (import order?), stairs left alone" % STAIR_KIND]
	var mat: BaseMaterial3D = found[0]
	mat.resource_name = "M_Skin_%s_stairs" % STAIR_KIND
	var note: String = "; material from %s" % String(found[1])
	if not mat.uv1_world_triplanar:
		# The module imported before the kit pass touched it: its uv1_scale
		# is still the authored tile period. World-project it the way
		# `_apply` does, at that period (the kit's meshes measure a UV
		# density of ~1.0, so world == authored to four decimals).
		mat.uv1_triplanar = true
		mat.uv1_world_triplanar = true
		note += " (world-projected here; the module's own pass had not run)"
	var counts: Array = _assign_stairs(scene, mat)
	return [counts[0], counts[1], note]


## The first textured material of `kind` in an instanced kit module.
func _kit_material(n: Node, kind: String) -> BaseMaterial3D:
	var mi: MeshInstance3D = n as MeshInstance3D
	if mi != null and mi.mesh != null:
		for i in range(mi.mesh.get_surface_count()):
			var bm: BaseMaterial3D = mi.mesh.surface_get_material(i) as BaseMaterial3D
			if bm != null and bm.albedo_texture != null \
					and String(bm.resource_name).contains("_" + kind):
				return bm
	for c in n.get_children():
		var m: BaseMaterial3D = _kit_material(c, kind)
		if m != null:
			return m
	return null


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

